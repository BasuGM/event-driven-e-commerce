# Money as decimals

## What it is

Most numbers in programs are **binary floating point** (IEEE 754): Python's `float`, JavaScript's
`Number`, Postgres's `double precision`. They store a binary fraction, and most decimal fractions
(0.1, 0.01) have no exact binary representation, so they're stored approximately. Python's own
tutorial shows `0.1 + 0.1 + 0.1 == 0.3` evaluating to `False`
([floating-point arithmetic](https://docs.python.org/3.13/tutorial/floatingpoint.html)).

Money needs exact cents. The tools for that:

| Where | Exact type | Notes |
|---|---|---|
| Python | `decimal.Decimal` | Decimal arithmetic: `0.1 + 0.1 + 0.1 - 0.3` is exactly zero. The default context rounds `ROUND_HALF_EVEN`; `quantize()` rounds to a given exponent (two places for cents) with a chosen rounding mode ([decimal](https://docs.python.org/3.13/library/decimal.html)) |
| Postgres | `numeric(p, s)` | Exact for addition, subtraction and multiplication; `real`/`double precision` are inexact. Ties round **away from zero** for `numeric`, but (on most machines) **to the nearest even** for floats ([numeric types](https://www.postgresql.org/docs/17/datatype-numeric.html)) |
| JSON / JavaScript | A **string** such as `"75.01"` | JS `Number` is an IEEE 754 double; integers are exact only up to 2^53 − 1 ([MDN: Number](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number)), and RFC 8259 says JSON numbers interoperate well only within binary64's precision ([RFC 8259, section 6](https://www.rfc-editor.org/rfc/rfc8259#section-6)) |
| Alternative | Integer minor units (cents) | Exact and fast, but every input, output and currency with a different number of decimals needs a conversion |

**Rounding is a decision, not a detail.** "Half up" (ties away from zero) and "half even"
(banker's rounding, ties to the even digit) differ only on ties, but ties are common with
two-decimal money: R$ 2.665 → 2.67 or 2.66. Pick one, write it down, and use it everywhere a value
is rounded.

## The problem it solves

```python
>>> price = 0.1                     # a float "10 cents"
>>> sum([price] * 3)
0.30000000000000004
>>> round(2.675, 2)                 # looks like a tie, isn't one in binary
2.67
>>> from decimal import Decimal
>>> sum([Decimal("0.1")] * 3)
Decimal('0.3')
```

The errors are tiny, but money is compared (`total == paid`), summed over thousands of rows
(revenue), and shown to customers. A float that is off by 10⁻¹⁷ fails an equality check, and a
rounding that goes the other way on a tie changes a total by a cent.

There are three places it typically goes wrong:
1. **Storage:** a `float` column.
2. **Computation:** a float function in the middle of exact data. Postgres's `percentile_cont`
   works on `double precision`.
3. **Transport:** a JSON number parsed by JavaScript into a `Number`.

## In this project

Rules from [ADR 0010](../adr/0010-money-as-decimal-strings.md) and CLAUDE.md:

- **Storage:** `DecimalField(max_digits=12, decimal_places=2)` (the `MONEY` dict in
  [catalog/models.py](../../backend/apps/catalog/models.py)). The analytics sums use
  `max_digits=14` for headroom ([analytics/models.py](../../backend/apps/analytics/models.py)).
- **Computation stays exact:**
  - **Offer prices.** They are the exact median of each (product, seller) pair's item prices,
    computed in `numeric` as the mean of the two middle values (`percentile_disc` twice), never
    `percentile_cont`, which goes through `float8` (`OFFERS_SQL` in
    [stats.py](../../backend/apps/catalog/stats.py)).
  - **Order totals** are `Decimal` sums of the price and freight snapshots.
  - **Average order value** is `gmv / paid`, quantized to cents with `ROUND_HALF_UP`
    ([queries.py](../../backend/apps/analytics/queries.py)).
- **Transport: decimal strings.**
  - **The API.** DRF serialises `DecimalField` as strings by default (`COERCE_DECIMAL_TO_STRING`
    is `True` unless changed; [DRF settings](https://www.django-rest-framework.org/api-guide/settings/#coerce_decimal_to_string)),
    and this project doesn't change it, so the API sends `"75.01"`.
  - **Events and the outbox.** `DjangoJSONEncoder` turns a `Decimal` into the same string. The
    generated TypeScript types say `string`, which makes it obvious.
- **Display, not arithmetic, in the browser:**
  - **The frontend.** `formatBRL()` in [format.ts](../../frontend/src/lib/format.ts) formats with
    `Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })`; no money arithmetic
    happens in JavaScript.
  - **Emails.** `format_brl()` in [formatting.py](../../backend/apps/core/formatting.py) produces
    the same text ("R$ 1.234,50") with `ROUND_HALF_UP`. That matches `Intl`'s default rounding
    mode, `halfExpand` (ties away from zero) ([MDN: NumberFormat options](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat#roundingmode)).
- **A detail worth knowing:** `formatBRL()` converts the string with `Number()` before formatting.
  MDN documents that `format()` also accepts a numeric string and then uses its exact value,
  avoiding a `Number` conversion ([format()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/format)),
  with the caveat that older implementations parsed strings as `Number`s.
  - **Why it's harmless here:** the values are at most 12 digits with 2 decimals (under ten
    billion reais). A double holds about 15–17 significant decimal digits, so it stores them
    closely enough that formatting to two decimals shows the same cents. **Unverified** against the
    pages cited here: this is the standard IEEE 754 binary64 property, not a quote.
  - **Where that reasoning ends:** that's reasoned, not tested; passing the string would remove the
    question.
- **Checked end to end:** on 2026-11-09 the replay's projected GMV equalled the imported one to the
  cent (R$ 316.909,40) ([replay.md](../flows/replay.md#throughput)).

## Pitfalls

- **Constructing a `Decimal` from a float.** `Decimal(2.675)` captures the float's binary error
  (`2.67499999…`); construct from strings or integers.
- **A float function in a decimal pipeline.** One `percentile_cont`, `avg()` over `double
  precision`, or `float()` in Python reintroduces binary error.
- **Different rounding in different places.** Postgres `numeric` rounds ties away from zero,
  Python's default context rounds half-even, `Intl` defaults to half-expand. Choose explicitly
  wherever you round.
- **Money as a JSON number.** Fine for small values in practice, wrong in principle; a string keeps
  every digit and makes the type obvious.
- **Summing rounded values vs rounding the sum.** They differ by cents; decide which one is the
  official figure (here: sum exact values, round once for display).
- **Arithmetic in the browser.** Totals shown in the UI should come from the server, computed once,
  exactly.

## Interview follow-ups

- **Why not floats for money?** Binary floats can't represent most decimal fractions exactly, so
  sums drift and ties round unexpectedly. Money needs exact decimal arithmetic.
- **Decimal or integer cents?** Both are exact. Decimals match how amounts are written and imported
  (and currencies with different minor units); integer cents are faster and simpler to store, at the
  cost of conversions at every boundary.
- **How do you send money in JSON?** As a decimal string (`"75.01"`), possibly with a currency code;
  never as a float, because JavaScript parses JSON numbers as doubles.
- **Which rounding mode?** Whatever the business or regulation requires. Commonly half-up for
  display and invoices, half-even for statistical aggregation. The important part is choosing one
  and applying it consistently.
- **Where can exactness leak out of a "decimal" system?** Float-based SQL functions, constructing
  decimals from floats, JSON numbers, and client-side arithmetic.

Project-specific questions: [interview-guide.md](../interview-guide.md).

## Exercises

### 1. Floats, decimals and ties

**Runs on: A** (lab stack; `lab exec backend python`, plain Python, no database).

```python
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
print(0.1 + 0.1 + 0.1 == 0.3, sum([0.1] * 3))
print(sum([Decimal("0.1")] * 3) == Decimal("0.3"))
print(round(2.675, 2), Decimal(2.675))
for v in ("2.665", "2.675"):
    d = Decimal(v)
    print(v, d.quantize(Decimal("0.01"), ROUND_HALF_UP), d.quantize(Decimal("0.01"), ROUND_HALF_EVEN))
```

**Expected:** `False 0.30000000000000004`, then `True`. Then `2.67` followed by a long decimal
starting `2.67499999…`. Then `2.665 2.67 2.66` and `2.675 2.68 2.68`.

<details><summary>Solution</summary>

`round(2.675, 2)` gives 2.67 because the float isn't 2.675: it's slightly below, as `Decimal(2.675)`
reveals, so it isn't a tie at all. With decimals built from strings, 2.665 and 2.675 are true ties,
and the two rounding modes disagree on 2.665: half-up goes away from zero (2.67), half-even goes to
the even digit (2.66). On 2.675 both give 2.68, since 8 is even. That's why a test with no tie in it
can't tell the modes apart (exercise 4).
</details>

### 2. Postgres numeric vs float

**Runs on: B** (dev database, read-only: `SELECT` only).

```sql
SELECT round(2.5::numeric) AS numeric_25, round(2.5::float8) AS float_25,
       round(3.5::numeric) AS numeric_35, round(3.5::float8) AS float_35,
       0.1::float8 + 0.2::float8 = 0.3::float8 AS float_equal,
       0.1::numeric + 0.2::numeric = 0.3::numeric AS numeric_equal;
```

**Expected:** `3, 2, 4, 4` (numeric away from zero, float to even), then `false` and `true`.

<details><summary>Solution</summary>

The docs describe exactly this: `numeric` rounds ties away from zero, the float types (on most
machines) to the nearest even number, and only `numeric` adds 0.1 and 0.2 exactly. A query mixing
the two types quietly mixes the two behaviours, which is why the project keeps money in `numeric`
from the column to the median.
</details>

### 3. The API sends strings

**Runs on: A** (lab stack; the public catalog through the lab proxy).

```sh
curl -s 'http://localhost:3101/api/products/?page_size=1' | jq '.results[0] | {min_price, type: (.min_price | type)}'
```

**Expected:** `min_price` is a string with two decimals (on 2026-11-12: `"49.90"`), and its `type`
is `"string"`.

<details><summary>Solution</summary>

DRF's `DecimalField` serialises as a string by default, and the value keeps its two decimal places
(`"35.90"`, not `35.9`). The TypeScript client therefore types it as `string`, and the UI only
formats it. Any arithmetic, such as a cart total, comes from the API, computed in `Decimal`.
</details>

### 4. A mutation the tests don't catch

**Runs on: C** ([mutation protocol](lab.md#c-the-test-suite-mutation-exercises)).

0. Check the file is unmodified, or stop and commit or stash first:
   `git diff --quiet -- backend/apps/core/formatting.py && git diff --cached --quiet -- backend/apps/core/formatting.py && echo clean`
1. In [backend/apps/core/formatting.py](../../backend/apps/core/formatting.py), change
   `rounding=ROUND_HALF_UP` to `rounding=ROUND_HALF_EVEN` (and import `ROUND_HALF_EVEN`).
2. `docker compose exec backend pytest tests/test_notifications.py -k format_brl`
3. While the mutation is in place:
   `docker compose exec backend python -c "from decimal import Decimal; from apps.core.formatting import format_brl; print(format_brl(Decimal('2.665')))"`
4. Restore and prove it: `git checkout -- backend/apps/core/formatting.py`, then
   `git diff --quiet -- backend/apps/core/formatting.py && echo restored` and `git status --short`.
   Never commit the mutated file.

**Expected:** step 2 **passes**: the mutation survives. Step 3 prints `R$ 2,66`, where the original
prints `R$ 2,67`.

<details><summary>Solution</summary>

`test_format_brl_matches_the_storefront` checks `0`, `75.01`, `1234.5` and `1234567.891`. None of them
is a tie at the cent, so half-up and half-even give the same text, and the test can't tell which
mode is used. The rounding rule the code claims ("the same as the frontend's `Intl.NumberFormat`")
is untested. Adding a tie such as `2.665 → R$ 2,67` would pin it. This is what mutation testing is
for: a passing test suite says nothing about the lines no test can distinguish.
</details>

**Run status:** all four run on 2026-11-12, and every result matched. Venue A on the lab stack
(`make lab-up`), venue B read-only, venue C with the
[mutation protocol](lab.md#c-the-test-suite-mutation-exercises). As predicted, exercise 4's mutation
**survived**: 4 tests passed under half-even, and only the tie showed the difference (`R$ 2,66` vs
`R$ 2,67`). That's a real gap in `test_format_brl_matches_the_storefront`, reported, not fixed here.

## Further reading

- Python 3.13: [decimal](https://docs.python.org/3.13/library/decimal.html), [floating-point arithmetic: issues and limitations](https://docs.python.org/3.13/tutorial/floatingpoint.html)
- PostgreSQL 17: [numeric types](https://www.postgresql.org/docs/17/datatype-numeric.html)
- MDN: [Number](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number), [Intl.NumberFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat#roundingmode), [format()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/format)
- [RFC 8259, section 6: numbers](https://www.rfc-editor.org/rfc/rfc8259#section-6); [DRF: COERCE_DECIMAL_TO_STRING](https://www.django-rest-framework.org/api-guide/settings/#coerce_decimal_to_string)
- Project: [ADR 0010](../adr/0010-money-as-decimal-strings.md), [api.md: conventions](../api.md#conventions)

**Verified** 2026-11-12 against the Python 3.13, PostgreSQL 17, MDN, RFC 8259 and DRF pages linked above.
