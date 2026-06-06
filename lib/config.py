"""
Load config from environment variables (.env).
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
# Image folder (replaces Google Drive — see lib/storage.py).
# On Proxmox, set the IMAGES_DIR env to a persistent volume covered by backups,
# e.g. IMAGES_DIR=/mnt/data/rae-bakery/images
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", str(BASE_DIR / "data" / "images")))
# Downscale before storing: longest side <= N px + JPEG quality (shrinks 3-5MB
# phone photos to ~100-300KB).
IMAGE_MAX_SIDE = int(os.getenv("IMAGE_MAX_SIDE", "1600"))
IMAGE_JPEG_QUALITY = int(os.getenv("IMAGE_JPEG_QUALITY", "85"))

# --- SQLite database (Phase 1: replaces Google Sheets) ---
# SQLite database file — see lib/db.py, lib/schema.py.
# On Proxmox, set the DB_PATH env to a local volume covered by backups,
# e.g. DB_PATH=/mnt/data/rae-bakery/app.db (WAL needs a local fs — no NFS/CIFS).
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "app.db")))

# --- PDF archive storage ---
# Folder for printed bill PDFs (one file per bill: {bill_id}.pdf — see lib/pdf_archive.py).
# On Proxmox, set the BILLS_PDF_DIR env to a persistent volume covered by backups,
# e.g. BILLS_PDF_DIR=/mnt/data/rae-bakery/bills_pdf
BILLS_PDF_DIR = Path(os.getenv("BILLS_PDF_DIR", str(BASE_DIR / "data" / "bills_pdf")))

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
