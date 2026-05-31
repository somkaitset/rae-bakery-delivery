# secrets/

⚠️ **ไฟล์ในโฟลเดอร์นี้ถูก gitignored ทั้งหมด** (ยกเว้น `.gitkeep` และ `README.md`)

## ไฟล์ที่ต้องมีก่อนรันแอป

| ไฟล์ | ที่มา | คำสั่ง |
|---|---|---|
| `service_account.json` | Google Cloud Console | ดู `docs/google_setup.md` |
| `Sarabun-Regular.ttf` | Google Fonts (Cadson Demak) | `wget https://github.com/cadsondemak/Sarabun/raw/master/fonts/Sarabun-Regular.ttf` |
| `Sarabun-Bold.ttf` | เหมือนกัน | `wget https://github.com/cadsondemak/Sarabun/raw/master/fonts/Sarabun-Bold.ttf` |

## ห้าม commit อะไรไว้ในที่นี่
หากคุณรู้สึกว่าต้องการ commit ไฟล์ใน secrets/ — แสดงว่าออกแบบผิด เช่น
- ฟอนต์ใหม่ → ย้ายไป `assets/fonts/` แล้ว commit
- Public key → ย้ายไป `deploy/` แล้ว commit
