# Translation Workflow

เอกสารนี้คือ wiki สำหรับ Agent/LLM เวลาทำงานแปลนิยาย

## Main Loop

1. อ่านตอนหรือย่อหน้าที่ต้องแปล
2. ดึงคำเฉพาะทั้งหมด เช่น ชื่อตัวละคร โปเกมอน ท่า ไอเทม สถานที่ องค์กร ฉายา และคำระบบ
   - ใช้ `python tools/extract_terms.py chapters/source/<file>.txt`
   - หรือใช้ `python tools/translate_prepare.py chapters/source/<file>.txt` เพื่อแยก active/raw/missing
3. ค้นคำเหล่านั้นใน `glossary/`
4. คำที่พบ ให้ใช้คำแปลไทยจาก `th`
5. คำที่ไม่พบ ให้ค้นใน `glossary_raw/`
6. ถ้าพบใน raw ให้เทียบหลายภาษาและเลือกคำแปลไทย
   - ใช้ `python tools/glossary_import_raw.py --term <term>` เพื่อเพิ่มจาก raw
7. ถ้าไม่พบใน raw ให้แปลเองโดยยึดบริบทและสไตล์เรื่อง
   - ใช้ `python tools/glossary_add.py <term> --category term --th "<thai>" --source llm --status needs_review`
8. บันทึกคำใหม่ลง `glossary/`
9. สร้าง report ใน `reports/glossary_updates/`
10. แปลเนื้อหาโดยใช้ glossary ที่อัปเดตแล้ว
11. ตรวจ glossary ด้วย `python tools/glossary_validate.py`
12. สร้าง chapter report ด้วย `python tools/chapter_report.py chapters/source/<file>.txt`
13. ถ้ามีคำ `needs_review` ให้รัน `python tools/glossary_review.py queue`

## Decision Rules

- ถ้าชื่อเป็นชื่อญี่ปุ่น/โปเกมอนที่มีชื่อไทยจาก raw อยู่แล้ว ให้ใช้ตาม raw ก่อน
- ถ้าชื่อไทยจาก raw ดูเป็นการแปลผิดความหมายหรือไม่เหมาะกับชื่อเฉพาะ ให้ใส่ `needs_review` และอธิบายใน notes
- ถ้าต้องเลือกทับศัพท์ ให้ใช้รูปแบบไทยที่อ่านง่ายและคงเสียงต้นฉบับ
- ถ้าคำเป็นชื่อท่า ความสามารถ หรือไอเทม ให้คงคำแปลเดียวกันทั้งเรื่อง
- ถ้าคำเป็นคำสามัญที่ไม่ใช่ศัพท์เฉพาะ ไม่จำเป็นต้องเพิ่ม glossary เว้นแต่มีผลต่อความต่อเนื่องของเรื่อง

## Report Trigger

ต้องทำ report เมื่อ:

- เพิ่มคำใหม่ใน `glossary/`
- แก้คำแปลไทยเดิม
- เปลี่ยน status เช่น `needs_review` เป็น `approved`
- รวมคำซ้ำหรือเลิกใช้คำเดิม

ไม่ต้องทำ report เมื่อ:

- แค่ค้นคำแล้วไม่เปลี่ยนไฟล์
- แปลประโยคทั่วไปโดยไม่มีศัพท์ใหม่

## Folder Flow

- ต้นฉบับ: `chapters/source/`
- ไฟล์เตรียมคำศัพท์: `chapters/prep/`
- ฉบับแปล: `chapters/translated/`
- note รายตอน: `chapters/notes/`

## Chapter Report

ใช้รายงานรายตอนเพื่อดูภาพรวมหลังเตรียมหรือแปลเสร็จ:

```powershell
python tools/chapter_report.py chapters/source/chapter001.txt --translated chapters/translated/chapter001.txt --out chapters/notes/chapter001.report.md
```

รายงานจะสรุป:

- จำนวน candidate terms
- คำที่เจอใน active glossary
- คำที่เจอเฉพาะ raw glossary
- คำที่ยัง missing
- คำ `needs_review` ที่ถูกใช้ในตอนนั้น

## Review Queue

เมื่อต้องจัดการคำที่ยังไม่มั่นใจ:

```powershell
python tools/glossary_review.py queue
```

คำสั่งนี้จะสร้าง/อัปเดต `glossary/review_queue.md`

เมื่อเลือกคำแปลได้แล้ว:

```powershell
python tools/glossary_review.py approve term-0001 --th "คำแปลที่ยืนยัน" --notes "ยืนยันจากบริบทตอน 12"
```
