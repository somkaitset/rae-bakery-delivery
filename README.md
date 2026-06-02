# rae-bakery-delivery

ระบบบันทึก/พิมพ์บิลส่งสินค้าเบเกอรี่ตามโรงเรียน — Streamlit + Google Sheet

## Stack
- **Frontend / Backend:** Streamlit (Python)
- **Database:** Google Sheet (`เรเบเกอรี่-ฐานข้อมูลส่งสินค้า`)
- **File storage:** Local disk — รูปสินค้า/สต็อก LINE เก็บบน disk ของเครื่องผ่าน `lib/storage.py` (Service Account ไม่มี Drive quota) โดยใน Sheet เก็บแค่ชื่อไฟล์; บิล PDF สร้างแล้วดาวน์โหลดทันที (ไม่อัปโหลด)
- **Auth:** streamlit-authenticator (bcrypt, แยก password รายคน)
- **Deploy:** Proxmox LXC (Debian 12) + Tailscale (เข้าจากนอกร้านได้)

## Features
1. บันทึกใบส่งสินค้า (กริดสินค้าทั้งหมด + ตัวเลขแนะนำจากประวัติขาย)
2. ฟอร์มแก้/เพิ่ม ลูกค้า + สินค้า (มีรูป)
3. บันทึกสต็อกคงเหลือจากรูปลูกค้าส่งทาง LINE
4. พิมพ์บิลส่งของเป็น PDF
5. สรุปยอดรายวัน/สัปดาห์ ทั้งหมด + รายลูกค้า

## Quick start (development)

```bash
# clone
git clone <repo-url> rae-bakery-delivery
cd rae-bakery-delivery

# venv + dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# config
cp .env.example .env
# แก้ .env: ใส่ path service_account.json + SHEET_ID
# (Drive IDs ไม่จำเป็นแล้ว — รูปเก็บ local; dev ปล่อย IMAGES_DIR ว่างได้ = ./data/images)

# Google Service Account
# วาง JSON key ลงใน secrets/service_account.json (ดู docs/google_setup.md)

# Thai font (สำหรับ PDF บิล)
# ดาวน์โหลด Sarabun-Regular.ttf + Sarabun-Bold.ttf จาก Google Fonts
# ไปวางที่ secrets/

# Auth — สร้าง user แรก
cp auth_config.yaml.example auth_config.yaml
.venv/bin/python scripts/gen_password.py "your-password"
# ก๊อปปี้ hash ที่ได้ ไปวางใน auth_config.yaml

# Run
streamlit run app.py
# เปิด http://localhost:8501
```

## Project structure
```
app.py                          # Streamlit entry (login + dashboard)
pages/                          # Streamlit auto-detect multipage
├── 1_📦_ใบส่งสินค้า.py
├── 2_📊_สรุปยอด.py
├── 3_📷_สต็อก_LINE.py
├── 4_🏪_ลูกค้า.py
└── 5_🍰_สินค้า.py
lib/
├── config.py                   # env vars + tab name mapping
├── auth.py                     # streamlit-authenticator wrapper
├── sheets.py                   # Google Sheets client (gspread) + read cache/invalidate
├── bills.py                    # domain logic: ID gen, ราคา, ยอดรวม, create/update/delete, suggest_qty
├── storage.py                  # เก็บรูป local (ย่อ/หมุน/JPEG) — แทน Drive
├── pdf.py                      # PDF บิลส่งของ (ฟอนต์ Sarabun)
├── drive.py                    # ⚠️ legacy/unused (เหลือไว้เผื่อ migrate กลับ Shared Drive)
└── models.py                   # dataclass อ้างอิงโครงสร้างแต่ละแท็บ (reference เฉยๆ)
scripts/
└── gen_password.py             # gen bcrypt hash สำหรับ auth_config
deploy/                         # Proxmox LXC deployment
├── streamlit.service           # systemd unit
├── install.sh                  # provision LXC ใหม่
└── update.sh                   # git pull + restart
docs/
├── google_setup.md             # สร้าง Service Account
├── auth_setup.md               # สร้าง user/password
├── proxmox_setup.md            # ติดตั้งใน LXC + Tailscale
└── git_workflow.md             # convention git
secrets/                        # ❌ gitignored — JSON key + ฟอนต์
└── service_account.json
```

## Git workflow
- branch `main` = production
- feature work: `feature/<name>` branch → PR → merge `main`
- ดูเพิ่มที่ `docs/git_workflow.md`

## License
Private — ใช้ภายในร้านเรเบเกอรี่
