# Glossary Lookup Protocol

ใช้ protocol นี้เมื่อต้องตัดสินคำแปลศัพท์เฉพาะ

## Search Targets

Active glossary:

- `glossary/characters.md`
- `glossary/pokemon.md`
- `glossary/moves.md`
- `glossary/abilities.md`
- `glossary/items.md`
- `glossary/locations.md`
- `glossary/terms.md`

Raw glossary:

- `glossary_raw/character_names.md`
- `glossary_raw/pokemon_names.md`
- `glossary_raw/moves.md`
- `glossary_raw/abilities.md`
- `glossary_raw/items.md`
- `glossary_raw/locations.md`
- `glossary_raw/others.md`
- `glossary_raw/pokemon.md`

## Matching

ค้นหาจากทุกภาษาที่มี:

- Chinese source text
- Japanese name
- English name
- Thai name

ถ้าพบหลายรายการ:

1. เลือกรายการที่ตรงกับ category ของคำในบริบท
2. ถ้ายังชนกัน ให้ใช้ source text หรือบริบทประโยคช่วยตัดสิน
3. ถ้ายังไม่แน่ใจ ให้เลือกชั่วคราวเป็น `needs_review`

## New Entry Example

```md
| char-0001 | 小智 | 小智 | サトシ | Ash | ซาโตชิ | character | glossary_raw | approved | พบใน character_names.md |
```

## LLM-Generated Entry Example

```md
| term-0001 | 御兽空间 | 御兽空间 |  |  | มิติควบคุมสัตว์อสูร | term | llm | needs_review | แปลจากบริบท ยังไม่พบใน raw |
```

