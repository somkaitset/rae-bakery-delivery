"""
คลังเก็บ PDF บิลที่พิมพ์แล้ว — เก็บบน disk ของเครื่อง (เหมือน lib/storage.py)

ชื่อไฟล์ deterministic = "{bill_id}.pdf" (เขียนทับได้) → ไม่ต้องเก็บ path/flag ใน DB.
"สถานะพิมพ์/ส่งแล้ว" อยู่ที่ bill.status; ไฟล์นี้คือ artifact ตัวจริง (ดาวน์โหลด/พิมพ์ซ้ำ).
อ่าน BILLS_PDF_DIR จาก lib.config เท่านั้น (ไม่อ่าน env ที่อื่น). ไม่ import streamlit
→ headless-safe + test ได้.
"""
from __future__ import annotations

from pathlib import Path

from lib.config import BILLS_PDF_DIR


def archive_path(bill_id: str) -> Path:
    """path เต็มของ PDF ที่เก็บไว้สำหรับ bill นี้ (BILLS_PDF_DIR/{bill_id}.pdf)."""
    return BILLS_PDF_DIR / f"{bill_id}.pdf"


def is_archived(bill_id: str) -> bool:
    """มีไฟล์ PDF เก็บไว้แล้วหรือยัง (ใช้เช็ค self-heal / affordance ดาวน์โหลด;
    ไม่ใช่ flag 'พิมพ์แล้ว' — flag นั้นอยู่ที่ bill.status)."""
    return archive_path(bill_id).exists()


def save_pdf(bill_id: str, pdf_bytes: bytes) -> str:
    """เขียน PDF ลง disk (เขียนทับถ้ามีอยู่) แล้วคืนชื่อไฟล์ '{bill_id}.pdf'."""
    BILLS_PDF_DIR.mkdir(parents=True, exist_ok=True)
    path = archive_path(bill_id)
    path.write_bytes(pdf_bytes)
    return path.name


def read_pdf(bill_id: str) -> bytes | None:
    """คืน bytes ของ PDF ที่เก็บไว้ ถ้ามี; ไม่มีไฟล์ → None."""
    path = archive_path(bill_id)
    if path.exists():
        return path.read_bytes()
    return None


def delete_pdf(bill_id: str) -> None:
    """ลบ PDF ที่เก็บไว้ (ใช้ตอน revert→ร่าง เพื่อให้พิมพ์ครั้งหน้า regenerate).
    missing_ok=True load-bearing: bill ที่ไม่เคยมีไฟล์ต้องไม่ throw."""
    archive_path(bill_id).unlink(missing_ok=True)
