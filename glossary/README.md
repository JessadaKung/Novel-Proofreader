# Active Glossary

โฟลเดอร์นี้คือ glossary ที่ Agent ใช้จริงในการแปลนิยาย ข้อมูลในนี้มีความสำคัญกว่า `glossary_raw/`

## Lookup Order

1. ค้นไฟล์ในโฟลเดอร์นี้ก่อน
2. ถ้าไม่พบ ค้น `glossary_raw/`
3. ถ้า raw มีคำที่ตรงหรือใกล้เคียง ให้เลือกคำแปลและเพิ่มเข้าที่นี่
4. ถ้า raw ไม่มี ให้ LLM แปลเองจากบริบทและเพิ่มเข้าที่นี่
5. ทุกครั้งที่เพิ่มหรือแก้ข้อมูล ต้องทำ report ที่ `reports/glossary_updates/`

## Schema

ใช้ตารางรูปแบบเดียวกันทุกไฟล์:

| id | source_text | zh | ja | en | th | category | source | status | notes |
|---|---|---|---|---|---|---|---|---|---|

## Review Queue

คำที่มี `status = needs_review` ต้องถูกส่งเข้า `review_queue.md`

```powershell
python tools/glossary_review.py queue
```

เมื่อตรวจแล้วให้ approve:

```powershell
python tools/glossary_review.py approve <id> --th "<คำแปลไทย>" --notes "<เหตุผล>"
```

## Field Meaning

- `id`: รหัสรายการ ใช้รูปแบบสั้น เช่น `char-0001`, `poke-0025`, `move-0001`
- `source_text`: คำที่พบในนิยายต้นฉบับ
- `zh`: ชื่อภาษาจีน ถ้ามี
- `ja`: ชื่อภาษาญี่ปุ่น ถ้ามี
- `en`: ชื่อภาษาอังกฤษ ถ้ามี
- `th`: คำแปลไทยที่เลือกใช้จริง
- `category`: หมวด เช่น `character`, `pokemon`, `move`, `ability`, `item`, `location`, `term`
- `source`: `glossary_raw`, `llm`, `user`, หรือ `mixed`
- `status`: `approved`, `needs_review`, หรือ `deprecated`
- `notes`: เหตุผล บริบท หรือข้อควรระวัง
