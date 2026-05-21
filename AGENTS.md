# Thai Novel Proofreading Agent Guide

โปรเจกต์นี้ใช้สำหรับตรวจสำนวน ตรวจคำผิด และตรวจความสม่ำเสมอของคำเฉพาะในนิยายแปล โดยให้ Agent และ LLM ยึด glossary เป็นแหล่งอ้างอิงหลักก่อนแก้ชื่อเฉพาะหรือคำศัพท์เฉพาะทุกครั้ง

## Priority

1. ตรวจคำผิด เว้นวรรค วรรคตอน และตัวสะกดภาษาไทย
2. ตรวจสำนวนให้อ่านลื่นแบบนิยาย โดยรักษาความหมายเดิม
3. ตรวจความสม่ำเสมอของชื่อเฉพาะกับ `glossary/`
4. ถ้าพบคำเฉพาะที่ไม่อยู่ใน `glossary/` ให้ค้นหาใน `glossary_raw/`
5. ถ้าจำเป็นต้องเพิ่มหรือแก้ข้อมูลใน `glossary/` ต้องทำ report ใน `reports/glossary_updates/` ทุกครั้ง

## Proofreading Scope

- แก้คำผิด ตัวสะกดผิด พิมพ์ตก พิมพ์เกิน และการใช้ไม้ยมก/วรรณยุกต์ผิด
- ปรับเว้นวรรคและวรรคตอนให้อ่านเป็นธรรมชาติ
- เกลาประโยคที่แข็ง แปลก หรือสะดุด ให้เป็นภาษาไทยลื่นแบบนิยาย
- รักษาน้ำเสียง บรรยากาศ ลำดับเหตุการณ์ และข้อมูลเดิม
- ไม่เติมเหตุการณ์ใหม่ ไม่ตัดข้อมูลสำคัญ และไม่ตีความเกินจากต้นฉบับ
- ไม่เปลี่ยนชื่อเฉพาะหรือคำศัพท์เฉพาะโดยไม่ตรวจ glossary ก่อน

## Glossary Rules

- `glossary/` คือข้อมูลที่ผ่านการเลือกใช้แล้ว และถือเป็นคำแปล canonical
- `glossary_raw/` คือคลังอ้างอิงดิบ ใช้เพื่อค้นหาและเทียบคำเท่านั้น
- ชื่อเฉพาะ โปเกมอน ท่า ความสามารถ ไอเทม สถานที่ และชื่อตัวละคร ต้องคงเส้นคงวาตลอดเรื่อง
- หากพบคำในต้นฉบับที่ใช้ไม่ตรงกับ `glossary/` ให้แก้กลับเป็นคำ canonical จาก `glossary/`
- หากคำเดียวกันมีหลายคำแปล ให้เลือกคำที่เหมาะกับบริบทนิยาย แล้วบันทึกเหตุผลในช่อง notes
- ห้ามเปลี่ยนคำแปลเดิมใน `glossary/` แบบเงียบ ๆ ถ้าจำเป็นต้องแก้ ต้องทำ report พร้อมเหตุผล

## Required Lookup Flow

สำหรับชื่อเฉพาะและคำศัพท์เฉพาะทุกคำที่พบระหว่างตรวจ:

1. Search active glossary:
   - `glossary/characters.md`
   - `glossary/pokemon.md`
   - `glossary/moves.md`
   - `glossary/abilities.md`
   - `glossary/items.md`
   - `glossary/locations.md`
   - `glossary/terms.md`
2. If found, use the canonical Thai form from `glossary/`.
3. If not found, search matching files in `glossary_raw/`.
4. If found in raw, compare Chinese/Japanese/English/Thai columns and choose a Thai translation only when the current text needs a consistent term.
5. Add the chosen entry to the correct file in `glossary/` only when necessary for consistency.
6. If no raw match exists and the term must be standardized, infer from context and add it to `glossary/` with `source = llm`.
7. Create a report in `reports/glossary_updates/YYYY-MM-DD-HHMM.md` for every glossary update.

## Editing Rules

- แก้เฉพาะส่วนที่จำเป็นต่อคำผิด สำนวน ความลื่นไหล และความสม่ำเสมอ
- รักษารูปแบบไฟล์ ย่อหน้า เครื่องหมายคำพูด และโครงสร้างบทเดิมให้มากที่สุด
- หากประโยคเดิมถูกต้องและอ่านดีแล้ว ไม่ต้องแก้
- ถ้าต้องเลือกแก้สำนวน ให้เลือกแบบที่เป็นธรรมชาติในภาษาไทยมากกว่าการแปลตรงตัว
- ถ้าข้อความกำกวมหรือแก้แล้วเสี่ยงเปลี่ยนความหมาย ให้ใส่ note ในรายงานตรวจบทแทนการแก้เดา
- คำที่ยังไม่มั่นใจให้ทำเครื่องหมาย `needs review` ในรายงานที่เกี่ยวข้อง

## Helper Commands

- Search glossary: `python tools/glossary_lookup.py <term>`
- Add one entry and create report: `python tools/glossary_add.py <term> --category term --th "<thai>"`
- Import from raw: `python tools/glossary_import_raw.py --term <term>`
- Validate active glossary: `python tools/glossary_validate.py`
- Extract candidate terms: `python tools/extract_terms.py chapters/source/<file>.txt`
- Prepare chapter lookup: `python tools/translate_prepare.py chapters/source/<file>.txt`
- Create chapter report: `python tools/chapter_report.py chapters/source/<file>.txt`
- Regenerate review queue: `python tools/glossary_review.py queue`
- Approve review item: `python tools/glossary_review.py approve <id>`

## Report Requirement

Every glossary update report must include:

- date/time
- source chapter or file
- entries added
- entries changed
- lookup source: `glossary_raw`, `llm`, or both
- short reason for each decision

Chapter proofreading reports should include:

- source chapter or file
- summary of proofreading changes
- notable wording or consistency issues
- glossary mismatches fixed
- unresolved items marked `needs review`

## Proofreading Style

- ภาษาไทยต้องอ่านลื่นแบบนิยาย
- รักษาความหมายเดิม ไม่เติมเหตุการณ์ใหม่
- เกลาสำนวนให้เป็นธรรมชาติ แต่ไม่เปลี่ยนน้ำเสียงของผู้บรรยายหรือตัวละคร
- บทสนทนาต้องฟังเหมือนคนพูดจริงและเข้ากับบุคลิกตัวละคร
- ชื่อเฉพาะใช้ตาม glossary เสมอ
- ถ้าเจอคำที่ยังไม่มั่นใจ ให้ใส่ใน report ว่า `needs review`
- คำที่มี `status = needs_review` ต้องปรากฏใน `glossary/review_queue.md` หลังรัน `python tools/glossary_review.py queue`
