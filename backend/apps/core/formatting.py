from decimal import ROUND_HALF_UP, Decimal


def format_brl(value) -> str:
    """Decimal -> "R$ 1.234,50", the same as the frontend's Intl.NumberFormat("pt-BR", BRL)."""
    amount = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    integer, _, cents = f"{abs(amount):.2f}".partition(".")
    groups = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    return f"{sign}R$ {'.'.join(groups)},{cents}"
