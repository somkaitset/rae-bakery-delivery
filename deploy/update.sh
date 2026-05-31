#!/usr/bin/env bash
# update.sh — pull code ใหม่ + restart service
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> 1/3 git pull"
git pull --ff-only

echo "==> 2/3 ตรวจ + ติดตั้ง dependencies ใหม่ (ถ้ามี)"
.venv/bin/pip install -r requirements.txt --quiet --upgrade

echo "==> 3/3 restart service"
sudo systemctl restart rae-bakery

sleep 2
sudo systemctl status rae-bakery --no-pager --lines=10
echo ""
echo "==> เสร็จ ✅"
