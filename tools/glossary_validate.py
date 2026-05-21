#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict

from glossary_common import CATEGORY_FILES, GLOSSARY_DIR, VALID_SOURCES, VALID_STATUSES, load_active_entries, parse_active_file


def main() -> int:
    errors: list[str] = []
    seen_ids: dict[str, str] = {}
    seen_terms: defaultdict[tuple[str, str], list[str]] = defaultdict(list)

    for category, file_name in CATEGORY_FILES.items():
        path = GLOSSARY_DIR / file_name
        entries = parse_active_file(path)
        if not path.exists():
            errors.append(f"missing file: {path}")
        for entry in entries:
            if entry.category != category:
                errors.append(f"{file_name}: {entry.id} category is {entry.category}, expected {category}")
            if entry.id in seen_ids:
                errors.append(f"duplicate id {entry.id}: {seen_ids[entry.id]} and {file_name}")
            seen_ids[entry.id] = file_name
            if entry.source not in VALID_SOURCES:
                errors.append(f"{file_name}: {entry.id} invalid source {entry.source}")
            if entry.status not in VALID_STATUSES:
                errors.append(f"{file_name}: {entry.id} invalid status {entry.status}")
            if not entry.th:
                errors.append(f"{file_name}: {entry.id} missing Thai translation")
            for key in entry.key_values():
                seen_terms[(entry.category, key)].append(entry.id)

    for (category, key), ids in seen_terms.items():
        if len(ids) > 1 and key:
            errors.append(f"possible duplicate in {category}: {key} appears in {', '.join(ids)}")

    print(f"Active entries: {len(load_active_entries())}")
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

