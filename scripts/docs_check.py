#!/usr/bin/env python3
"""Check README.md and docs/**/*.md against the repo (`make docs-check`). Standard library only.

1. Links and images: every relative target exists, and every #anchor matches a heading in the
   target Markdown file (GitHub's slug rules). External URLs are not fetched.
2. Code references: a backticked token that looks like a file path, a `make` target, a setting
   or constant (UPPER_CASE with an underscore), or a code identifier (snake_case, CamelCase,
   name(), dotted.name) must exist in the repo. Framework names are written fully qualified
   (`django.middleware.csrf.rotate_token()`) and are not checked. Anything else in backticks (values, URLs, SQL,
   header names, placeholders like <id>) is not checked.

   In docs/concepts/ only, names listed in scripts/docs_external_names.txt (Postgres settings
   and catalogs, SQL functions, framework and browser APIs: things the tutorials explain but
   this repo doesn't define) are accepted too. The list is not part of the code index.

Links to documents that a later batch will write are listed in scripts/docs_pending.txt. They
are reported as pending, not failures. Fenced code blocks (including Mermaid) are skipped.
Exit status 1 if anything fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PENDING_FILE = ROOT / "scripts" / "docs_pending.txt"
EXTERNAL_FILE = ROOT / "scripts" / "docs_external_names.txt"
EXTERNAL_SCOPE = "docs/concepts/"  # the only docs where external names are accepted

# Where code identifiers may be defined or used
CODE_DIRS = ["backend/apps", "backend/config", "backend/tests", "frontend/src", "frontend/e2e", "scripts"]
CODE_FILES = ["Makefile", "docker-compose.yml", ".env.example", "frontend/next.config.ts",
              "frontend/package.json", "backend/pytest.ini"]
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".yml", ".yaml", ".json", ".sh", ".html", ".txt", ".css", ".ini", ".toml"}
SKIP_DIRS = {"node_modules", ".next", "__pycache__", ".git", "staticfiles"}

LINK = re.compile(r"(!?)\[(?:[^\]\[]|\[[^\]]*\])*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
FENCE = re.compile(r"^(```|~~~)")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# A path: has a known file extension, starts at a top-level folder, or ends with "/".
# (Not "America/Sao_Paulo" or "a/b" shorthand.) data/ is gitignored, so it isn't checked.
PATH_LIKE = re.compile(
    r"^[\w.\-/]+\.(py|ts|tsx|md|yml|yaml|json|sh|html|txt|css|ini|toml)$"
    r"|^(backend|frontend|docs|scripts)/[\w.\-/]*$"
    r"|^[\w.\-/]+/$"
)
SETTING = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
CAMEL = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+$|^[A-Z][a-z]+[A-Z0-9][A-Za-z0-9]*$")
CALL = re.compile(r"^([A-Za-z_][\w.]*)\(\)$")
DOTTED = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")
MAKE = re.compile(r"^make ([a-z][a-z0-9-]*)(\s.*)?$")


def doc_files() -> list[Path]:
    files = [ROOT / "README.md"] if (ROOT / "README.md").exists() else []
    return files + sorted((ROOT / "docs").rglob("*.md"))


def strip_fences(text: str) -> list[tuple[int, str]]:
    """Lines outside fenced code blocks, with their 1-based numbers."""
    out, fenced = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line.strip()):
            fenced = not fenced
            continue
        if not fenced:
            out.append((number, line))
    return out


def github_slug(heading: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", heading)  # inline code keeps its text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links keep their text
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)  # drop punctuation (unicode letters stay)
    return text.replace(" ", "-")


def anchors(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path not in cache:
        seen: dict[str, int] = {}
        result = set()
        for _, line in strip_fences(path.read_text(encoding="utf-8")):
            match = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
            if not match:
                continue
            slug = github_slug(match.group(1))
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            result.add(slug if count == 0 else f"{slug}-{count}")
        cache[path] = result
    return cache[path]


def code_index() -> tuple[set[str], list[str]]:
    words: set[str] = set()
    paths: list[str] = []
    files = [ROOT / f for f in CODE_FILES if (ROOT / f).exists()]
    for d in CODE_DIRS:
        for p in (ROOT / d).rglob("*"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.is_file():
                paths.append(p.relative_to(ROOT).as_posix())
                if p == EXTERNAL_FILE:  # its names must not count as "defined in the repo"
                    continue
                if p.suffix in CODE_SUFFIXES:
                    files.append(p)
    for p in files:
        try:
            words.update(WORD.findall(p.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            pass
    # Every repo path (files and directories), for path-like references
    for p in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts) or "data" == p.relative_to(ROOT).parts[0]:
            continue
        rel = p.relative_to(ROOT).as_posix()
        paths.append(rel + ("/" if p.is_dir() else ""))
    return words, sorted(set(paths))


def make_targets() -> set[str]:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    return set(re.findall(r"^([a-z][a-z0-9-]*):", text, flags=re.M))


def check_reference(token: str, words: set[str], paths: list[str], targets: set[str]) -> str | None:
    """None = fine or not checkable; otherwise a reason."""
    token = token.strip()
    if any(c in token for c in "<>{}*$ \"'=|,;") and not MAKE.match(token):
        return None
    if token.startswith(("/", "-", "http", ".", "#", ":", "~")) and token not in (".env.example",):
        return None
    if token.startswith("django."):  # a framework reference (written fully qualified), not our code
        return None
    if m := MAKE.match(token):
        return None if m.group(1) in targets else f"no Makefile target '{m.group(1)}'"
    if PATH_LIKE.match(token) and ("/" in token or "." in token):
        if token.startswith(("@", "data/")) or token.count(":"):  # npm scopes, gitignored data, URLs
            return None
        want = token.rstrip("/")
        hit = any(p.rstrip("/") == want or p.rstrip("/").endswith("/" + want) for p in paths)
        return None if hit else "no such file or directory"
    if m := CALL.match(token):
        name = m.group(1).split(".")[-1]
        return None if name in words else f"'{name}' not found in code"
    if DOTTED.match(token):
        if re.match(r"^[a-z]+\.[a-z]+$", token) and token.split(".")[1] in {"py", "ts", "tsx", "md", "yml", "json"}:
            return None
        parts = token.split(".")
        missing = [p for p in parts if p not in words]
        return None if not missing else f"'{'.'.join(missing)}' not found in code"
    if SETTING.match(token) or SNAKE.match(token) or CAMEL.match(token):
        return None if token in words else "not found in code"
    return None


def main() -> int:
    pending = set()
    if PENDING_FILE.exists():
        pending = {line.strip() for line in PENDING_FILE.read_text().splitlines() if line.strip() and not line.startswith("#")}
    external = set()
    if EXTERNAL_FILE.exists():
        external = {line.split("#", 1)[0].strip() for line in EXTERNAL_FILE.read_text().splitlines()} - {""}
    words, paths = code_index()
    targets = make_targets()
    anchor_cache: dict[Path, set[str]] = {}
    failures: list[str] = []
    pending_hits: list[str] = []
    counts = {"files": 0, "links": 0, "images": 0, "code refs": 0}

    for doc in doc_files():
        counts["files"] += 1
        rel_doc = doc.relative_to(ROOT).as_posix()
        for number, line in strip_fences(doc.read_text(encoding="utf-8")):
            where = f"{rel_doc}:{number}"
            for bang, target in LINK.findall(line):
                counts["images" if bang else "links"] += 1
                if re.match(r"^[a-z]+:", target):  # http:, https:, mailto:
                    continue
                path_part, _, anchor = target.partition("#")
                dest = doc if not path_part else (doc.parent / path_part).resolve()
                if path_part:
                    try:
                        dest_rel = dest.relative_to(ROOT).as_posix()
                    except ValueError:
                        failures.append(f"{where}: link leaves the repo: {target}")
                        continue
                    if not dest.exists():
                        if dest_rel in pending:
                            pending_hits.append(f"{where}: {dest_rel}")
                        else:
                            failures.append(f"{where}: missing {'image' if bang else 'link'} target: {target}")
                        continue
                if anchor and dest.suffix == ".md" and anchor not in anchors(dest, anchor_cache):
                    failures.append(f"{where}: no heading for #{anchor} in {dest.relative_to(ROOT).as_posix()}")
            # Inline code outside link texts
            for token in INLINE_CODE.findall(LINK.sub("", line)):
                counts["code refs"] += 1
                if rel_doc.startswith(EXTERNAL_SCOPE) and token.strip().removesuffix("()") in external:
                    continue
                reason = check_reference(token, words, paths, targets)
                if reason:
                    failures.append(f"{where}: `{token}`: {reason}")

    print("docs-check: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    if pending_hits:
        targets_pending = sorted(set(h.split(": ", 1)[1] for h in pending_hits))
        print(f"\n{len(pending_hits)} link(s) to {len(targets_pending)} document(s) not written yet "
              "(scripts/docs_pending.txt):")
        for hit in targets_pending:
            print(f"  pending  {hit}")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for failure in failures:
            print(f"  FAIL  {failure}")
        return 1
    print("\nOK: every link, anchor, image and code reference resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
