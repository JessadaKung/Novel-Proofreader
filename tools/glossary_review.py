#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from glossary_common import CATEGORY_FILES, GLOSSARY_DIR, entry_to_row, parse_active_file, read_text, write_report


QUEUE_PATH = GLOSSARY_DIR / "review_queue.md"


def write_queue() -> int:
    rows: list[str] = []
    count = 0
    for category, file_name in CATEGORY_FILES.items():
        for entry in parse_active_file(GLOSSARY_DIR / file_name):
            if entry.status == "needs_review":
                count += 1
                rows.append(
                    f"| {entry.id} | {category} | {entry.source_text} | {entry.th} | {entry.source} | {entry.notes} | pending |  |"
                )

    content = """# Glossary Review Queue

รายการนี้สร้างจาก entry ที่มี status `needs_review` ใน `glossary/`

| id | category | source_text | th | source | notes | review_status | reviewer_notes |
|---|---|---|---|---|---|---|---|
"""
    content += "\n".join(rows) + ("\n" if rows else "")
    QUEUE_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {QUEUE_PATH} ({count} items)")
    return 0


def approve(entry_id: str, new_th: str | None, notes: str | None) -> int:
    found = False
    for file_name in CATEGORY_FILES.values():
        path = GLOSSARY_DIR / file_name
        entries = parse_active_file(path)
        changed = False
        approved_entry = None
        old_th = ""
        for entry in entries:
            if entry.id == entry_id:
                found = True
                old_th = entry.th
                entry.status = "approved"
                if new_th:
                    entry.th = new_th
                if notes:
                    entry.notes = notes
                approved_entry = entry
                changed = True
        if changed:
            header = "\n".join(read_text(path).splitlines()[:4])
            body = "\n".join(entry_to_row(entry) for entry in entries)
            path.write_text(header + "\n" + body + "\n", encoding="utf-8")
            changed_row = (
                f"| {approved_entry.source_text} | {approved_entry.category} | {old_th} | "
                f"{approved_entry.th} | approved review item {entry_id} | approved |"
            )
            write_report([], [changed_row], "glossary_review.py approve", [], [f"approved {entry_id}"])
            print(f"Approved {entry_id} in {path}")
            return 0
    print(f"Entry id not found: {entry_id}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage glossary needs_review queue.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("queue", help="Regenerate glossary/review_queue.md")
    approve_parser = sub.add_parser("approve", help="Approve one needs_review entry")
    approve_parser.add_argument("id")
    approve_parser.add_argument("--th", help="Replace Thai translation before approving")
    approve_parser.add_argument("--notes", help="Replace notes before approving")
    args = parser.parse_args()

    if args.command == "queue":
        return write_queue()
    if args.command == "approve":
        return approve(args.id, args.th, args.notes)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
