#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from glossary_common import load_active_entries, load_raw_entries, read_text
from extract_terms import TOKEN_RE


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a per-chapter translation report.")
    parser.add_argument("chapter", help="Source chapter file")
    parser.add_argument("--translated", help="Translated chapter file")
    parser.add_argument("--out", help="Output report path")
    args = parser.parse_args()

    chapter = Path(args.chapter)
    source_text = read_text(chapter)
    translated_text = read_text(Path(args.translated)) if args.translated else ""
    candidates = sorted(set(match.group(0).strip() for match in TOKEN_RE.finditer(source_text)))
    active = load_active_entries()
    raw = load_raw_entries()

    active_hits: list[str] = []
    raw_candidates: list[str] = []
    missing: list[str] = []
    needs_review_used: list[str] = []

    for term in candidates:
        needle = term.casefold()
        active_matches = [entry for entry in active if needle in entry.key_values()]
        if active_matches:
            active_hits.append(f"{term}: " + "; ".join(f"{e.th} ({e.category}, {e.status})" for e in active_matches[:3]))
            needs_review_used.extend(
                f"{term}: {e.th} ({e.id})" for e in active_matches if e.status == "needs_review"
            )
            continue
        raw_matches = [entry for entry in raw if needle in entry.key_values()]
        if raw_matches:
            raw_candidates.append(f"{term}: " + "; ".join(f"{e.th or '?'} ({e.category})" for e in raw_matches[:3]))
        else:
            missing.append(term)

    translated_note = f"- translated file: {Path(args.translated) if args.translated else '-'}"
    translated_stats = ""
    if translated_text:
        translated_stats = f"\n- translated characters: {len(translated_text)}"

    content = f"""# Chapter Translation Report

- source chapter: {chapter}
{translated_note}
- source characters: {len(source_text)}
{translated_stats}
- candidate terms: {len(candidates)}
- active glossary hits: {len(active_hits)}
- raw glossary candidates: {len(raw_candidates)}
- missing terms: {len(missing)}
- needs-review terms used: {len(needs_review_used)}

## Active Glossary Hits

{chr(10).join(f"- {item}" for item in active_hits) or "-"}

## Raw Glossary Candidates

{chr(10).join(f"- {item}" for item in raw_candidates) or "-"}

## Missing Terms

{chr(10).join(f"- {item}" for item in missing) or "-"}

## Needs Review Used

{chr(10).join(f"- {item}" for item in needs_review_used) or "-"}

## Notes

-
"""
    out = Path(args.out) if args.out else Path("chapters/notes") / f"{chapter.stem}.report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

