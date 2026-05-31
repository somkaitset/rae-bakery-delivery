# Auth Setup — สร้าง user/password

ระบบใช้ **streamlit-authenticator** เก็บ user + bcrypt-hashed password ใน `auth_config.yaml`

## Step 1 — Copy template

```bash
cp auth_config.yaml.example auth_config.yaml
```

> 💡 `auth_config.yaml` (ไฟล์จริง) ถูก `.gitignore` ไว้แล้ว — รหัสจะไม่ commit ลง git

## Step 2 — สร้าง bcrypt hash ของรหัสผ่าน

```bash
source .venv/bin/activate
python scripts/gen_password.py "your-password-here"
```

ผลที่ได้จะเป็น:
```
$2b$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Step 3 — แก้ `auth_config.yaml`

เปิดไฟล์ แล้วแทนที่ `password:` ของแต่ละ user:

```yaml
credentials:
  usernames:
    admin:                       # ← ชื่อ login (พิมพ์ตอนเข้าระบบ)
      name: เจ้าของร้าน           # ← ชื่อจริง (แสดงในแอป)
      email: somkaitset@gmail.com
      role: admin                # admin/staff/viewer
      password: $2b$12$xxxxx...  # ← วาง hash ที่ได้จาก step 2

    delivery1:
      name: พนักงานส่ง #1
      email: ""
      role: staff
      password: $2b$12$yyyyy...

cookie:
  name: rae_bakery_auth
  key: random-string-อย่างน้อย-32-ตัว-แทนค่าจริงนี้
  expiry_days: 30
```

### Role ที่ใช้ได้
- **admin** — เห็น/แก้/ลบทุกอย่าง รวมถึงราคาส่ง
- **staff** — บันทึก/แก้บิล + สต็อก ลูกค้า สินค้า
- **viewer** — อ่านอย่างเดียว (ดูสรุปยอด)

(role-based access control implement ใน `lib/auth.py` → `require_role()`)

## Step 4 — สุ่ม cookie key

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
ก๊อปปี้ผลที่ได้ → แทน `key:` ใน `auth_config.yaml`

## Step 5 — ทดสอบ

```bash
streamlit run app.py
```

ไป http://localhost:8501 → ลองเข้าระบบด้วย username + password

## เพิ่ม user ใหม่

ทำ Step 2-3 ซ้ำ:
1. รัน `python scripts/gen_password.py "password"` ของ user ใหม่
2. เพิ่ม block ใหม่ใต้ `usernames:` ใน `auth_config.yaml`
3. Restart Streamlit (Ctrl+C → run ใหม่)

## ลืมรหัสผ่าน

1. รัน `python scripts/gen_password.py "new-password"` ใหม่
2. แทน hash เดิมใน `auth_config.yaml`
3. Restart Streamlit
