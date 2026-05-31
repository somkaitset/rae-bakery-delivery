"""
Google Sheets client — อ่าน/เขียนทุกแท็บ
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from lib.config import GOOGLE_SERVICE_ACCOUNT_PATH, SHEET_ID, TABS


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@lru_cache(maxsize=1)
def _client() -> gspread.Client:
    creds = Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_PATH, scopes=SCOPES
    )
    return gspread.authorize(creds)


@lru_cache(maxsize=1)
def _spreadsheet() -> gspread.Spreadsheet:
    return _client().open_by_key(SHEET_ID)


def _ws(tab_key: str) -> gspread.Worksheet:
    """Get worksheet by key (e.g. 'customer' → 'ลูกค้า')."""
    return _spreadsheet().worksheet(TABS[tab_key])


def all_records(tab_key: str) -> list[dict[str, Any]]:
    """อ่านทุกแถวเป็น list of dicts (header → value)."""
    return _ws(tab_key).get_all_records()


def append(tab_key: str, row: list[Any]) -> None:
    """เพิ่มแถวต่อท้ายตาราง."""
    _ws(tab_key).append_row(row, value_input_option="USER_ENTERED")


def update_row(tab_key: str, row_number: int, row: list[Any]) -> None:
    """อัปเดตทั้งแถว (row_number = 1-indexed sheet row)."""
    sh = _ws(tab_key)
    end_col = chr(ord("A") + len(row) - 1)
    sh.update(
        f"A{row_number}:{end_col}{row_number}",
        [row],
        value_input_option="USER_ENTERED",
    )


def find_row_by_key(tab_key: str, key_value: str, key_col: int = 1) -> int | None:
    """หาเลข row ที่คอลัมน์ key_col = key_value (เริ่มที่ row 2 เพราะ row 1 = header)."""
    sh = _ws(tab_key)
    try:
        cell = sh.find(key_value, in_column=key_col)
        return cell.row if cell else None
    except gspread.exceptions.CellNotFound:
        return None


def delete_row(tab_key: str, row_number: int) -> None:
    _ws(tab_key).delete_rows(row_number)


def clear_caches() -> None:
    """ใช้หลังเขียนข้อมูลเสร็จ เพื่อให้รอบหน้าอ่านข้อมูลใหม่."""
    _client.cache_clear()
    _spreadsheet.cache_clear()


# --- Convenience wrappers (เรียกใช้ใน pages) ---
def customers() -> list[dict]:
    return all_records("customer")


def active_customers() -> list[dict]:
    return [c for c in customers() if c.get("ใช้งาน") in (True, "TRUE", "true", 1, "1")]


def products() -> list[dict]:
    return all_records("product")


def active_products() -> list[dict]:
    return [p for p in products() if p.get("ใช้งาน") in (True, "TRUE", "true", 1, "1")]


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
