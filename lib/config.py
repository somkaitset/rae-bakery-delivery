"""
โหลด config จาก environment variables (.env)
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# --- Google ---
GOOGLE_SERVICE_ACCOUNT_PATH = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_PATH",
    str(BASE_DIR / "secrets" / "service_account.json"),
)
SHEET_ID = os.getenv("SHEET_ID", "")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")
SUBFOLDER_ID = os.getenv("SUBFOLDER_ID", "")

# --- App ---
TIMEZONE = os.getenv("TIMEZONE", "Asia/Bangkok")
APP_TITLE = os.getenv("APP_TITLE", "เรเบเกอรี่ — ระบบส่งสินค้า")

# --- Local image storage ---
# โฟลเดอร์เก็บรูป (แทน Google Drive — ดู lib/storage.py)
# บน Proxmox ให้ตั้ง env IMAGES_DIR ชี้ไป volume ถาวรที่ Proxmox backup ครอบไว้
# เช่น IMAGES_DIR=/mnt/data/rae-bakery/images
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", str(BASE_DIR / "data" / "images")))

# --- Auth ---
AUTH_CONFIG_PATH = os.getenv("AUTH_CONFIG_PATH", str(BASE_DIR / "auth_config.yaml"))
COOKIE_NAME = os.getenv("COOKIE_NAME", "rae_bakery_auth")
COOKIE_KEY = os.getenv("COOKIE_KEY", "change-me-to-a-random-string")
COOKIE_EXPIRY_DAYS = int(os.getenv("COOKIE_EXPIRY_DAYS", "30"))

# --- Sheet tab name mapping ---
TABS: dict[str, str] = {
    "price_group": "กลุ่มราคา",
    "wholesale": "ราคาส่ง",
    "customer": "ลูกค้า",
    "product": "สินค้า",
    "bill": "ใบส่งสินค้า",
    "bill_item": "รายการสินค้า",
    "bill_lines": "BillLines",
    "stock": "สต็อกคงเหลือ",
}
