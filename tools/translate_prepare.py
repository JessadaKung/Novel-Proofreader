#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from glossary_common import load_active_entries, load_raw_entries, read_text
from extract_terms import TOKEN_RE


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare glossary lookup report before translating a chapter.")
    parser.add_argument("chapter")
    parser.add_argument("--out")
    args = parser.parse_args()

    chapter = Path(args.chapter)
    text = read_text(chapter)
    candidates = sorted(set(match.group(0).strip() for match in TOKEN_RE.finditer(text)))
    active = load_active_entries()
    raw_entries = load_raw_entries()

    active_hits: list[str] = []
    raw_hits: list[str] = []
    missing: list[str] = []
    for term in candidates:
        needle = term.casefold()
        if any(needle in entry.key_values() for entry in active):
            active_hits.append(term)
            continue
        matches = [entry for entry in raw_entries if needle in entry.key_values()]
        if matches:
            preview = "; ".join(f"{m.source_text}->{m.th or '?'}({m.category})" for m in matches[:3])
            raw_hits.append(f"{term}: {preview}")
        else:
            missing.append(term)

    content = f"""# Translation Prepare Report

- chapter: {chapter}

## Active Glossary Hits

{chr(10).join(f"- {item}" for item in active_hits) or "-"}

## Raw Glossary Candidates

{chr(10).join(f"- {item}" for item in raw_hits) or "-"}

## Missing / LLM Needed

{chr(10).join(f"- {item}" for item in missing) or "-"}
"""
    out = Path(args.out) if args.out else chapter.with_suffix(chapter.suffix + ".prepare.md")
    out.write_text(content, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
