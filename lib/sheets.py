"""
Data client — อ่าน/เขียนทุกแท็บ (Phase 1: SQLite backend แทน Google Sheets).

หน้าตา public เหมือนเดิมทุกอย่าง (lib/bills.py + pages เรียกใช้ผ่าน surface นี้)
แต่ข้างในต่อกับ lib/db.py (sqlite3). ที่ระดับโมดูลไม่มี dependency แบบ hard
ต่อ Streamlit หรือ gspread. เปิด connection ใหม่ต่อทุกการเรียก (WAL +
busy_timeout) แล้วปิดเสมอ; ไม่ cache connection (Streamlit rerun ข้าม thread +
sqlite3 check_same_thread=True).
"""
from __future__ import annotations

from contextlib import closing
from typing import Any

from lib import db


# --- Reads -----------------------------------------------------------------

def all_records(tab_key: str) -> list[dict[str, Any]]:
    """อ่านทุกแถวเป็น list of dicts (header ไทย → value), เรียงตามลำดับเพิ่ม (_id)."""
    with closing(db.ensure_db()) as conn:
        return db.all_rows(conn, tab_key)


# --- Writes ----------------------------------------------------------------

def append(tab_key: str, row: list[Any]) -> None:
    """เพิ่มแถวต่อท้ายตาราง."""
    with closing(db.ensure_db()) as conn:
        db.append(conn, tab_key, row)
    _invalidate()


def append_many(tab_key: str, rows: list[list[Any]]) -> None:
    """เพิ่มหลายแถวพร้อมกัน (1 transaction)."""
    if not rows:
        return
    with closing(db.ensure_db()) as conn:
        db.append_many(conn, tab_key, rows)
    _invalidate()


def replace_bill_items(rows: list[list[Any]], bill_id: str) -> None:
    """แทนที่รายการสินค้าของบิลนี้ทั้งหมดใน 1 transaction (DELETE WHERE bill_id + INSERT)."""
    with closing(db.ensure_db()) as conn:
        db.replace_bill_items(conn, rows, bill_id)
    _invalidate()


def update_row(tab_key: str, row_number: int, row: list[Any]) -> None:
    """อัปเดตทั้งแถว (row_number = 1-indexed sheet row; header=1, แถวข้อมูลแรก=2)."""
    with closing(db.ensure_db()) as conn:
        db.update_row(conn, tab_key, row_number, row)
    _invalidate()


def delete_row(tab_key: str, row_number: int) -> None:
    """ลบแถว (row_number = 1-indexed sheet row)."""
    with closing(db.ensure_db()) as conn:
        db.delete_row(conn, tab_key, row_number)
    _invalidate()


def find_row_by_key(tab_key: str, key_value: str, key_col: int = 1) -> int | None:
    """หาเลข row ที่คอลัมน์ key_col = key_value (เริ่มที่ row 2 เพราะ row 1 = header)."""
    with closing(db.ensure_db()) as conn:
        return db.find_row_number(conn, tab_key, key_value, key_col)


# --- Cache invalidation ----------------------------------------------------

def clear_caches() -> None:
    """ล้าง cache ระดับหน้า (Streamlit) หลังเขียนข้อมูล — ไม่พึ่ง streamlit แบบ hard.

    soft optional import: ถ้ารันใต้ Streamlit ก็เคลียร์ st.cache_data (รวม cache
    ระดับหน้าเช่น pages/2 ที่ ttl=30); ถ้ารัน headless ก็เงียบ ๆ ไม่ throw.
    เรียกบ่อยใน bills.py — ต้องไม่ raise.
    """
    try:
        import importlib

        importlib.import_module("streamlit").cache_data.clear()
    except Exception:
        pass


_invalidate = clear_caches


# --- Convenience wrappers (เรียกใช้ใน pages) ---
def customers() -> list[dict]:
    return all_records("customer")


def active_customers() -> list[dict]:
    return [c for c in customers() if c.get("active") in (True, "TRUE", "true", 1, "1")]


def products() -> list[dict]:
    return all_records("product")


def active_products() -> list[dict]:
    return [p for p in products() if p.get("active") in (True, "TRUE", "true", 1, "1")]


def bills() -> list[dict]:
    return all_records("bill")


def bill_items() -> list[dict]:
    return all_records("bill_item")


def bill_lines() -> list[dict]:
    return all_records("bill_lines")


def stocks() -> list[dict]:
    return all_records("stock")


def wholesale_prices() -> list[dict]:
    return all_records("wholesale")
