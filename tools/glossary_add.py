#!/usr/bin/env python3
from __future__ import annotations

import argparse

from glossary_common import Entry, append_entry, find_raw_matches, next_id, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Add one entry to active glossary and create a report.")
    parser.add_argument("term", help="Source term found in the novel")
    parser.add_argument("--category", required=True, choices=["character", "pokemon", "move", "ability", "item", "location", "term"])
    parser.add_argument("--th", required=True, help="Chosen Thai translation")
    parser.add_argument("--zh", default="")
    parser.add_argument("--ja", default="")
    parser.add_argument("--en", default="")
    parser.add_argument("--source", default="llm", choices=["glossary_raw", "llm", "user", "mixed"])
    parser.add_argument("--status", default="approved", choices=["approved", "needs_review", "deprecated"])
    parser.add_argument("--notes", default="")
    parser.add_argument("--source-file", default="")
    args = parser.parse_args()

    raw_matches = find_raw_matches(args.term)
    raw_files = sorted({match.notes.split(" from ", 1)[-1].split(";", 1)[0] for match in raw_matches})
    notes = [args.notes] if args.notes else []
    if raw_matches and args.source == "llm":
        notes.append("raw matches existed; verify whether llm translation should override raw")

    entry = Entry(
        id=next_id(args.category),
        source_text=args.term,
        zh=args.zh,
        ja=args.ja,
        en=args.en,
        th=args.th,
        category=args.category,
        source=args.source,
        status=args.status,
        notes=args.notes or "added via glossary_add.py",
    )
    append_entry(entry)
    report = write_report([entry], [], args.source_file, raw_files, notes)
    print(f"Added {entry.id} to glossary/{args.category}. Report: {report.relative_to(report.parents[2])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

