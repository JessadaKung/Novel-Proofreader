#!/usr/bin/env python3
"""Search active and raw glossary markdown files.

Usage:
  python tools/glossary_lookup.py Pikachu
  python tools/glossary_lookup.py 小智 --raw-only
"""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DIR = ROOT / "glossary"
RAW_DIR = ROOT / "glossary_raw"


def iter_files(raw_only: bool, active_only: bool) -> list[Path]:
    files: list[Path] = []
    if not raw_only and ACTIVE_DIR.exists():
        files.extend(sorted(ACTIVE_DIR.glob("*.md")))
    if not active_only and RAW_DIR.exists():
        files.extend(sorted(RAW_DIR.glob("*.md")))
    return files


def search(term: str, raw_only: bool, active_only: bool) -> int:
    needle = term.casefold()
    found = 0

    for path in iter_files(raw_only, active_only):
        rel = path.relative_to(ROOT)
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

        for line_no, line in enumerate(lines, start=1):
            if needle in line.casefold():
                found += 1
                print(f"{rel}:{line_no}: {line}")

    if found == 0:
        print(f"No glossary match found for: {term}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Search glossary markdown files.")
    parser.add_argument("term", help="Term to search in any language")
    parser.add_argument("--raw-only", action="store_true", help="Search glossary_raw only")
    parser.add_argument("--active-only", action="store_true", help="Search glossary only")
    args = parser.parse_args()

    if args.raw_only and args.active_only:
        parser.error("--raw-only and --active-only cannot be used together")

    return search(args.term, args.raw_only, args.active_only)


if __name__ == "__main__":
    raise SystemExit(main())

