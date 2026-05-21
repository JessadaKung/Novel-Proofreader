#!/usr/bin/env python3
from __future__ import annotations

import argparse

from collections import defaultdict

from glossary_common import Entry, active_has_match, append_entry, id_prefix, load_raw_entries, next_id_number, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Import entries from glossary_raw into active glossary.")
    parser.add_argument("--category", choices=["character", "pokemon", "move", "ability", "item", "location", "term"])
    parser.add_argument("--term", help="Import only raw entries matching this term")
    parser.add_argument("--limit", type=int, default=0, help="Maximum entries to import")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-file", default="glossary_raw")
    args = parser.parse_args()

    imported: list[Entry] = []
    skipped = 0
    counters = defaultdict(int)
    for raw in load_raw_entries():
        if args.category and raw.category != args.category:
            continue
        if args.term and args.term.casefold() not in raw.key_values():
            continue
        if active_has_match(raw):
            skipped += 1
            continue
        if counters[raw.category] == 0:
            counters[raw.category] = next_id_number(raw.category)
        raw.id = f"{id_prefix(raw.category)}-{counters[raw.category]:04d}"
        counters[raw.category] += 1
        if args.dry_run:
            print(f"Would import {raw.id}: {raw.source_text} -> {raw.th} ({raw.category})")
        else:
            append_entry(raw)
        imported.append(raw)
        if args.limit and len(imported) >= args.limit:
            break

    if not args.dry_run and imported:
        write_report(imported, [], args.source_file, ["glossary_raw/*.md"], [f"skipped duplicates: {skipped}"])
    print(f"{'Would import' if args.dry_run else 'Imported'}: {len(imported)}; skipped duplicates: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
