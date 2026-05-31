# Google Cloud Service Account — Setup Guide

ระบบใช้ Service Account (SA) เพื่อ:
- อ่าน/เขียน Google Sheet "เรเบเกอรี่-ฐานข้อมูลส่งสินค้า"
- อัปโหลดรูปสินค้า/รูปสต็อก/บิล PDF ลง Google Drive

ทำครั้งเดียว ใช้ตลอด

---

## Step 1 — สร้าง Google Cloud Project

1. ไปที่ https://console.cloud.google.com
2. ล็อกอินด้วยบัญชี Google ที่เป็นเจ้าของ Sheet (somkaitset@gmail.com)
3. มุมบนซ้าย → คลิก dropdown ที่แสดงโปรเจค → **`NEW PROJECT`**
4. Project name: `rae-bakery-delivery`
5. กด **`CREATE`** → รอประมาณ 10 วินาที → กลับมาเลือก project นี้

---

## Step 2 — เปิดใช้งาน API

ในเมนูซ้าย (☰) → `APIs & Services` → `Library`

1. ค้น **"Google Sheets API"** → คลิก → กด **`ENABLE`**
2. กลับไป Library → ค้น **"Google Drive API"** → คลิก → กด **`ENABLE`**

---

## Step 3 — สร้าง Service Account

`APIs & Services` → `Credentials` → กด **`+ CREATE CREDENTIALS`** → เลือก **`Service account`**

หน้า 1 (Service account details):
- Service account name: `rae-bakery-sa`
- Service account ID: auto-fill (ปล่อยไว้)
- กด **`CREATE AND CONTINUE`**

หน้า 2 (Grant access — ข้าม)
- กด **`CONTINUE`** ไม่ต้องตั้งค่า role

หน้า 3 (Grant user access — ข้าม)
- กด **`DONE`**

---

## Step 4 — Download JSON Key

1. กลับมาที่หน้า Credentials → คลิกที่ service account ที่เพิ่งสร้าง
2. แท็บ **`KEYS`** → กด **`ADD KEY`** → **`Create new key`**
3. เลือก **`JSON`** → กด **`CREATE`**
4. ไฟล์ `xxxx-yyyy-zzz.json` จะ download มา

**ย้ายไฟล์ + เปลี่ยนชื่อ:**
```bash
mv ~/Downloads/xxxx-yyyy-zzz.json \
   /home/raebakery/claude_code/project/rae-bakery-delivery/secrets/service_account.json
```

ตรวจ:
```bash
ls -l /home/raebakery/claude_code/project/rae-bakery-delivery/secrets/
# ควรเห็น service_account.json
```

> ⚠️ **ห้าม commit ไฟล์นี้** — `.gitignore` block ไว้แล้ว แต่ตรวจสอบให้แน่ใจ

---

## Step 5 — แชร์ Sheet + Drive folder ให้ Service Account

ก่อนอื่น — copy email ของ SA:

1. เปิดไฟล์ `secrets/service_account.json` ด้วย editor
2. หา field `"client_email"` ค่าจะเป็นเช่น:
   ```
   rae-bakery-sa@rae-bakery-delivery.iam.gserviceaccount.com
   ```
3. copy email นี้

### 5.1 แชร์ Google Sheet
1. เปิด Google Sheet "เรเบเกอรี่-ฐานข้อมูลส่งสินค้า" ใน browser
2. มุมขวาบน → กด **`Share`**
3. วาง email ของ SA
4. ตั้งสิทธิ์เป็น **`Editor`**
5. ❌ ปลดติ๊ก "Notify people" (SA ไม่มี mailbox)
6. กด **`Share`** หรือ **`Send`**

### 5.2 แชร์ Drive Folder
1. เปิดโฟลเดอร์ Drive โครงการ (`ระบบบันทึกส่งสินค้าเบเกอรี่`)
2. คลิกขวา → **`Share`** (หรือมุมขวาบน)
3. วาง email เดียวกัน → Editor → ❌ Notify people → Share

---

## Step 6 — ทดสอบ

```bash
cd /home/raebakery/claude_code/project/rae-bakery-delivery
source .venv/bin/activate
python -c "from lib.sheets import customers; print(customers()[:2])"
```

**ผลที่ควรได้:**
```python
[{'รหัสลูกค้า': 'C001', 'ชื่อลูกค้า': 'รณ.', 'ชุดราคา': 'มาตรฐาน', ...},
 {'รหัสลูกค้า': 'C002', 'ชื่อลูกค้า': 'พป.', 'ชุดราคา': 'มาตรฐาน', ...}]
```

---

## Troubleshooting

| Error | สาเหตุ + แก้ |
|---|---|
| `FileNotFoundError: service_account.json` | ลืมย้ายไฟล์ — ตรวจ `secrets/service_account.json` มีจริงไหม |
| `403: The caller does not have permission` | ลืม share Sheet/Drive ให้ SA — ทำ Step 5 |
| `403: Google Sheets API has not been used` | ลืม enable API — ทำ Step 2 |
| `400: Invalid project` | ลืมเลือก project ใน Cloud Console → กลับ Step 1 |
| `gspread.exceptions.SpreadsheetNotFound` | SHEET_ID ใน .env ผิด — ตรวจให้ตรง |
