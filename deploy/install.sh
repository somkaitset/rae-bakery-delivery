#!/usr/bin/env bash
# install.sh — provision Proxmox LXC ใหม่ ครั้งเดียว
# รันจาก /opt/rae-bakery-delivery (หลัง git clone)
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> 1/5 ติดตั้ง system packages"
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl

echo "==> 2/5 ติดตั้ง Tailscale (ถ้ายังไม่มี)"
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sudo sh
fi

echo "==> 3/5 สร้าง venv + ติดตั้ง dependencies"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt

echo "==> 4/5 ติดตั้ง systemd service"
sudo cp deploy/streamlit.service /etc/systemd/system/rae-bakery.service
sudo systemctl daemon-reload
sudo systemctl enable rae-bakery

echo "==> 5/5 ตรวจ config"
if [[ ! -f .env ]]; then
    echo "   ⚠️  ยังไม่มี .env — ก๊อปจาก template:"
    echo "      cp .env.example .env && nano .env"
fi
if [[ ! -f auth_config.yaml ]]; then
    echo "   ⚠️  ยังไม่มี auth_config.yaml — ดู docs/auth_setup.md"
fi
if [[ ! -f secrets/service_account.json ]]; then
    echo "   ⚠️  ยังไม่มี secrets/service_account.json — ดู docs/google_setup.md"
fi
if [[ ! -f secrets/Sarabun-Regular.ttf ]]; then
    echo "   ⚠️  ยังไม่มีฟอนต์ Sarabun (สำหรับ PDF ภาษาไทย):"
    echo "      cd secrets && wget https://github.com/cadsondemak/Sarabun/raw/master/fonts/Sarabun-Regular.ttf"
    echo "                   wget https://github.com/cadsondemak/Sarabun/raw/master/fonts/Sarabun-Bold.ttf"
fi

echo ""
echo "==> เสร็จขั้นตอนติดตั้ง 🎉"
echo ""
echo "ขั้นถัดไป:"
echo "  1) sudo tailscale up      # ล็อกอิน Tailscale"
echo "  2) เตรียม .env + auth_config.yaml + secrets/* ตามรายการข้างบน"
echo "  3) sudo systemctl start rae-bakery"
echo "  4) เปิด http://\$(tailscale ip -4):8501"
