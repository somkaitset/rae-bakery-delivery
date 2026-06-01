# Proxmox LXC Deploy — Setup Guide

Deploy แอปลง Proxmox LXC + Tailscale (เข้าจาก 4G ได้)

---

## Step 1 — สร้าง LXC Container ใน Proxmox

ในหน้า Proxmox UI:

1. คลิก node ของ Proxmox → **`Create CT`** (มุมขวาบน)
2. หน้า General:
   - Hostname: `rae-bakery`
   - Password: (ตั้งรหัส root)
3. หน้า Template: เลือก **Debian 12** standard template
4. หน้า Disks: 8 GB (พอ)
5. หน้า CPU: 2 cores
6. หน้า Memory: 1 GB RAM + 512 MB swap
7. หน้า Network: DHCP ใน bridge `vmbr0`
8. หน้า DNS: เว้นว่าง (ใช้ของ host)
9. **Confirm** → start container

---

## Step 2 — Login + Update LXC

```bash
# จาก Proxmox host
pct exec <CTID> -- bash
# (หรือเปิด console ใน UI)

# ใน LXC
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip git curl sudo

# สร้าง user (อย่ารัน Streamlit ในชื่อ root)
adduser raebakery
usermod -aG sudo raebakery
su - raebakery
```

---

## Step 3 — ติดตั้ง Tailscale (เพื่อเข้าจาก 4G)

```bash
curl -fsSL https://tailscale.com/install.sh | sudo sh
sudo tailscale up
# จะแสดงลิงก์ — เปิดในเบราว์เซอร์ ล็อกอินบัญชี Tailscale (มี Google login)
# กด Authorize
```

หลัง authorize:
```bash
tailscale ip -4
# จะได้ IP เช่น 100.x.x.x — IP นี้เข้าได้จากทุกที่ผ่าน Tailscale
```

ติดตั้ง Tailscale ในมือถือ:
- iOS / Android: ติดตั้ง app "Tailscale" → login บัญชีเดียวกัน
- เข้าแอปได้ที่ `http://100.x.x.x:8501`

---

## Step 4 — Clone repo + ติดตั้ง dependencies

```bash
# ใน LXC, เป็น user raebakery
cd /opt
sudo mkdir rae-bakery-delivery
sudo chown raebakery:raebakery rae-bakery-delivery
cd rae-bakery-delivery

# ถ้า remote = GitHub private — สร้าง SSH key + add ใน GitHub
ssh-keygen -t ed25519 -C "rae-bakery-lxc"
cat ~/.ssh/id_ed25519.pub
# ก๊อปปี้ key → GitHub Settings → SSH keys → Add

# clone
git clone git@github.com:USER/rae-bakery-delivery.git .
# หรือ HTTPS: git clone https://github.com/USER/rae-bakery-delivery.git .

# venv + deps
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

---

## Step 5 — Config

```bash
cp .env.example .env
nano .env
# แก้ค่า SHEET_ID, DRIVE_FOLDER_ID, COOKIE_KEY ให้ตรง

cp auth_config.yaml.example auth_config.yaml
# สร้าง user (ดู docs/auth_setup.md)

# วาง service_account.json
# scp จาก laptop:
# scp -r secrets/service_account.json raebakery@100.x.x.x:/opt/rae-bakery-delivery/secrets/

# วาง Sarabun font (จำเป็นสำหรับ PDF ภาษาไทย)
cd secrets
wget https://github.com/cadsondemak/Sarabun/raw/master/fonts/Sarabun-Regular.ttf
wget https://github.com/cadsondemak/Sarabun/raw/master/fonts/Sarabun-Bold.ttf
cd ..
```

---

## Step 5b — โฟลเดอร์เก็บรูป (local) + Backup

รูปสินค้า/สต็อก **เก็บบน disk ของ LXC** ไม่ได้อัปโหลดขึ้น Google Drive
(เพราะ Service Account ไม่มี storage quota และบัญชีเป็น personal Gmail จึงใช้
Shared Drive ไม่ได้ — ดู `lib/storage.py`)

```bash
# สร้าง volume ถาวรสำหรับรูป (แยกจาก repo เพื่อให้ git pull ไม่แตะ)
sudo mkdir -p /mnt/data/rae-bakery/images
sudo chown -R raebakery:raebakery /mnt/data/rae-bakery

# ชี้แอปมาที่ path นี้ใน .env
echo 'IMAGES_DIR=/mnt/data/rae-bakery/images' >> /opt/rae-bakery-delivery/.env
```

> ถ้าไม่ตั้ง `IMAGES_DIR` แอปจะใช้ดีฟอลต์ `./data/images` ในโฟลเดอร์ repo — ใช้ได้
> แต่ควรชี้ออกมานอก repo เพื่อความชัดเจนและให้ backup ครอบง่าย

**Backup:** ตั้ง Proxmox **vzdump** ให้ backup ทั้ง container (รวม volume รูป) เป็นประจำ
— Datacenter → Backup → Add → เลือก CT `rae-bakery` → schedule รายวัน/รายสัปดาห์
(ข้อมูลธุรกรรมอยู่ใน Google Sheets แล้ว ส่วนนี้ backup เฉพาะ "รูป" ที่อยู่บนเครื่อง)

---

## Step 6 — ติดตั้ง systemd service

```bash
sudo cp deploy/streamlit.service /etc/systemd/system/rae-bakery.service
sudo systemctl daemon-reload
sudo systemctl enable rae-bakery
sudo systemctl start rae-bakery

# ดู status
sudo systemctl status rae-bakery
# ดู log
sudo journalctl -u rae-bakery -f
```

ทดสอบ:
```bash
curl http://localhost:8501
# ควรได้ HTML กลับมา
```

จากมือถือ (Tailscale active):
- เปิด `http://100.x.x.x:8501`
- ควรเห็นหน้า login

---

## Step 7 — Update workflow

เวลามี code ใหม่ใน main:
```bash
cd /opt/rae-bakery-delivery
./deploy/update.sh
```

`update.sh` ทำ:
1. `git pull`
2. `pip install -r requirements.txt --upgrade`
3. `sudo systemctl restart rae-bakery`

---

## Troubleshooting

| Error | แก้ |
|---|---|
| `Permission denied (publickey)` ตอน clone | SSH key ยังไม่ add ใน GitHub |
| `streamlit: command not found` | `.venv/bin/streamlit run app.py` (ไม่ใช่ `streamlit run` ตรงๆ) |
| `Address already in use :8501` | มี Streamlit ตัวอื่นรันอยู่ — `sudo lsof -i :8501` → kill |
| มือถือเข้าไม่ได้ | ดู `tailscale status` ทั้ง 2 ฝั่ง online ไหม |
| `sudo systemctl status rae-bakery` แดง | `sudo journalctl -u rae-bakery -n 50` ดู error |
| กล้องใช้ไม่ได้ (`getUserMedia`) | ต้องเข้าผ่าน **HTTPS** หรือ `localhost` — ตั้ง reverse proxy (Nginx Proxy Manager) ให้ TLS |
| บันทึกรูปแล้ว error / `storageQuotaExceeded` | โค้ดเก่าใช้ Drive — เวอร์ชันนี้เก็บ local แล้ว เช็ก `IMAGES_DIR` เขียนได้ (`chown`) |
| รูปหายหลังรีสตาร์ท/redeploy | `IMAGES_DIR` ชี้เข้าโฟลเดอร์ที่ถูกลบ — ต้องชี้ออกนอก repo เช่น `/mnt/data/...` |
