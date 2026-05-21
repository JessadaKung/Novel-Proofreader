# Chapters

โฟลเดอร์สำหรับจัดงานแปลรายตอน

## Structure

- `source/`: ไฟล์ต้นฉบับ
- `prep/`: รายงานเตรียมคำศัพท์ก่อนแปล
- `translated/`: ฉบับแปลไทย
- `notes/`: note รายตอน เช่น จุดกำกวม สำนวน หรือรายการรอ review

## Suggested Flow

1. วางไฟล์ต้นฉบับใน `chapters/source/`
2. รัน `python tools/translate_prepare.py chapters/source/<file>.txt --out chapters/prep/<file>.prepare.md`
3. เพิ่มคำศัพท์ที่พบจาก raw หรือ LLM ลง `glossary/`
4. ตรวจ `reports/glossary_updates/`
5. แปลตอนลง `chapters/translated/`
6. สร้างรายงานรายตอน:
   `python tools/chapter_report.py chapters/source/<file>.txt --translated chapters/translated/<file>.txt --out chapters/notes/<file>.report.md`
7. รัน `python tools/glossary_validate.py`
