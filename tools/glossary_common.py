from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GLOSSARY_DIR = ROOT / "glossary"
RAW_DIR = ROOT / "glossary_raw"
REPORT_DIR = ROOT / "reports" / "glossary_updates"

CATEGORY_FILES = {
    "character": "characters.md",
    "pokemon": "pokemon.md",
    "move": "moves.md",
    "ability": "abilities.md",
    "item": "items.md",
    "location": "locations.md",
    "term": "terms.md",
}

RAW_TO_CATEGORY = {
    "character_names.md": "character",
    "pokemon_names.md": "pokemon",
    "pokemon.md": "pokemon",
    "moves.md": "move",
    "abilities.md": "ability",
    "items.md": "item",
    "locations.md": "location",
    "others.md": "term",
}

VALID_SOURCES = {"glossary_raw", "llm", "user", "mixed"}
VALID_STATUSES = {"approved", "needs_review", "deprecated"}


@dataclass
class Entry:
    id: str
    source_text: str
    zh: str
    ja: str
    en: str
    th: str
    category: str
    source: str
    status: str
    notes: str

    def key_values(self) -> set[str]:
        return {v.casefold() for v in [self.source_text, self.zh, self.ja, self.en, self.th] if v}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def split_md_row(line: str) -> list[str]:
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return []
    return [cell.strip() for cell in line.strip("|").split("|")]


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def escape_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ").strip()


def entry_to_row(entry: Entry) -> str:
    cells = [
        entry.id,
        entry.source_text,
        entry.zh,
        entry.ja,
        entry.en,
        entry.th,
        entry.category,
        entry.source,
        entry.status,
        entry.notes,
    ]
    return "| " + " | ".join(escape_cell(cell) for cell in cells) + " |"


def parse_active_file(path: Path) -> list[Entry]:
    entries: list[Entry] = []
    if not path.exists():
        return entries
    for line in read_text(path).splitlines():
        cells = split_md_row(line)
        if len(cells) != 10 or is_separator_row(cells) or cells[0] == "id":
            continue
        entries.append(Entry(*cells))
    return entries


def load_active_entries() -> list[Entry]:
    entries: list[Entry] = []
    for file_name in CATEGORY_FILES.values():
        entries.extend(parse_active_file(GLOSSARY_DIR / file_name))
    return entries


def next_id(category: str) -> str:
    prefix = {
        "character": "char",
        "pokemon": "poke",
        "move": "move",
        "ability": "abil",
        "item": "item",
        "location": "loc",
        "term": "term",
    }[category]
    max_num = 0
    for entry in parse_active_file(GLOSSARY_DIR / CATEGORY_FILES[category]):
        match = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", entry.id)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"{prefix}-{max_num + 1:04d}"


def id_prefix(category: str) -> str:
    return {
        "character": "char",
        "pokemon": "poke",
        "move": "move",
        "ability": "abil",
        "item": "item",
        "location": "loc",
        "term": "term",
    }[category]


def next_id_number(category: str) -> int:
    prefix = id_prefix(category)
    max_num = 0
    for entry in parse_active_file(GLOSSARY_DIR / CATEGORY_FILES[category]):
        match = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", entry.id)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num + 1


def append_entry(entry: Entry) -> None:
    path = GLOSSARY_DIR / CATEGORY_FILES[entry.category]
    text = read_text(path) if path.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    text += entry_to_row(entry) + "\n"
    path.write_text(text, encoding="utf-8")


def parse_raw_file(path: Path) -> list[Entry]:
    category = RAW_TO_CATEGORY.get(path.name, "term")
    entries: list[Entry] = []
    header: list[str] | None = None

    for line in read_text(path).splitlines():
        cells = split_md_row(line)
        if not cells or is_separator_row(cells):
            continue
        if any("ชื่อภาษา" in cell or cell in {"ลำดับ", "หมวดหมู่", "หมายเหตุ"} for cell in cells):
            header = cells
            continue
        if header is None:
            continue

        zh = ja = en = th = notes = ""
        if len(cells) >= 5 and ("ลำดับ" in header[0] or "﻿ลำดับ" in header[0]):
            zh, ja, en, th = cells[1], cells[2], cells[3], cells[4]
        elif len(cells) >= 5 and "ชื่อภาษาไทย" in header[0]:
            th, en, ja, notes = cells[0], cells[1], cells[2], cells[4]
        else:
            continue

        if not any([zh, ja, en, th]):
            continue
        source_text = zh or ja or en or th
        entries.append(
            Entry(
                id="",
                source_text=source_text,
                zh=zh,
                ja=ja,
                en=en,
                th=th,
                category=category,
                source="glossary_raw",
                status="approved" if th else "needs_review",
                notes=f"import candidate from {path.name}" + (f"; {notes}" if notes and notes != "-" else ""),
            )
        )
    return entries


def load_raw_entries() -> list[Entry]:
    entries: list[Entry] = []
    for path in sorted(RAW_DIR.glob("*.md")):
        entries.extend(parse_raw_file(path))
    return entries


def find_raw_matches(term: str) -> list[Entry]:
    needle = term.casefold()
    return [entry for entry in load_raw_entries() if needle in entry.key_values()]


def active_has_match(entry: Entry) -> bool:
    active = load_active_entries()
    candidate_keys = entry.key_values()
    for current in active:
        if current.category == entry.category and current.key_values() & candidate_keys:
            return True
    return False


def write_report(added: list[Entry], changed: list[str], source_file: str, raw_files: list[str], notes: list[str]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    path = REPORT_DIR / f"{stamp}.md"
    counter = 1
    while path.exists():
        path = REPORT_DIR / f"{stamp}-{counter}.md"
        counter += 1

    added_rows = "\n".join(
        f"| {escape_cell(e.source_text)} | {e.category} | {escape_cell(e.th)} | {e.source} | {escape_cell(e.notes)} | {e.status} |"
        for e in added
    )
    changed_rows = "\n".join(changed)
    raw_list = "\n".join(f"- {item}" for item in raw_files) or "-"
    note_list = "\n".join(f"- {item}" for item in notes) or "-"
    content = f"""# Glossary Update Report

- datetime: {datetime.now().isoformat(timespec="minutes")}
- source chapter/file: {source_file or "-"}
- agent: Codex

## Added

| term | category | th | source | reason | status |
|---|---|---|---|---|---|
{added_rows or ""}

## Changed

| term | category | old_th | new_th | reason | status |
|---|---|---|---|---|---|
{changed_rows or ""}

## Raw Lookup

- searched files:
{raw_list}

## Notes

{note_list}
"""
    path.write_text(content, encoding="utf-8")
    return path


def read_terms_file(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [row[0].strip() for row in csv.reader(fh) if row and row[0].strip()]
    return [line.strip() for line in read_text(path).splitlines() if line.strip()]
