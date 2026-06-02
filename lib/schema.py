"""
SQLite schema + authoritative column contract (Phase 1 migration).

Phase 1 swaps the data store from Google Sheets to SQLite WITHOUT changing the
read contract: every row is still returned as a dict keyed by the **live Thai
header** the pages/lib already use. Internally each table uses clean English
column names (mapped here), plus an addressing-only autoincrement `_id`.

DO NOT rename the Thai keys here from lib/models.py field names — they MUST be
the exact strings the code looks up (a typo silently returns empty). The English
side is internal and gets simplified away in Phase 2.

Columns are declared TEXT for behavioral equivalence with gspread's
``get_all_records()`` output; the tolerant helpers in lib/bills.py
(``_to_float``, the ``active`` checks, ``parse_date``) keep working unchanged.
Typing/foreign-keys are deliberately deferred to Phase 2.
"""
from __future__ import annotations

# Per-tab column contract: ordered list of (english_column, thai_header).
# Order mirrors the positional write lists in lib/bills.py (append/update_row),
# so a positional ``append([...])`` from a page lands in the right columns.
COLUMNS: dict[str, list[tuple[str, str]]] = {
    "price_group": [
        ("price_group", "กลุ่มราคา"),
        ("retail_price", "ราคาปลีก"),
        ("display_order", "ลำดับ"),
    ],
    "wholesale": [
        ("price_id", "รหัสราคา"),
        ("price_set", "ชุดราคา"),
        ("price_group", "กลุ่มราคา"),
        ("wholesale_price", "ราคาส่ง"),
    ],
    "customer": [
        ("code", "รหัสลูกค้า"),
        ("name", "ชื่อลูกค้า"),
        ("price_set", "ชุดราคา"),
        ("address", "ที่อยู่"),
        ("phone", "เบอร์โทร"),
        ("active", "ใช้งาน"),
    ],
    "product": [
        ("code", "รหัสสินค้า"),
        ("name", "ชื่อสินค้า"),
        ("price_group", "กลุ่มราคา"),
        ("image", "รูปสินค้า"),
        ("display_order", "ลำดับแสดง"),
        ("active", "ใช้งาน"),
    ],
    "bill": [
        ("bill_id", "รหัสใบส่ง"),
        ("date", "วันที่"),
        ("customer_code", "รหัสลูกค้า"),
        ("note", "หมายเหตุ"),
        ("status", "สถานะ"),
    ],
    "bill_item": [
        ("item_id", "รหัสรายการ"),
        ("bill_id", "รหัสใบส่ง"),
        ("product_code", "รหัสสินค้า"),
        ("qty", "จำนวน"),
        ("price_group", "กลุ่มราคา"),
        ("unit_price", "หน่วยละ"),
        ("amount", "จำนวนเงิน"),
    ],
    "stock": [
        ("stock_id", "รหัสสต็อก"),
        ("date", "วันที่"),
        ("customer_code", "รหัสลูกค้า"),
        ("product_code", "รหัสสินค้า"),
        ("remaining", "จำนวนคงเหลือ"),
        # NOTE: live header has a literal space — "รูปจาก LINE" — keep it exact.
        ("image", "รูปจาก LINE"),
        ("note", "หมายเหตุ"),
    ],
}

# bill_lines is a derived VIEW (NOT a base table). english -> thai for its reads.
BILL_LINES_COLUMNS: list[tuple[str, str]] = [
    ("item_id", "รหัสรายการ"),
    ("bill_id", "รหัสใบส่ง"),
    ("price_group", "กลุ่มราคา"),
    ("qty", "จำนวน"),
    ("unit_price", "หน่วยละ"),
    ("amount", "จำนวนเงิน"),
]

# Headers the running code actually reads per tab. The migration ABORTS if any
# of these is missing from the live sheet headers (header-drift guard, C2).
REQUIRED_KEYS: dict[str, list[str]] = {
    "wholesale": ["รหัสราคา", "ราคาส่ง"],
    "customer": ["รหัสลูกค้า", "ชื่อลูกค้า", "ชุดราคา", "ใช้งาน"],
    "product": ["รหัสสินค้า", "ชื่อสินค้า", "กลุ่มราคา", "รูปสินค้า", "ลำดับแสดง", "ใช้งาน"],
    "bill": ["รหัสใบส่ง", "วันที่", "รหัสลูกค้า", "สถานะ"],
    "bill_item": ["รหัสใบส่ง", "รหัสสินค้า", "จำนวน", "กลุ่มราคา", "หน่วยละ", "จำนวนเงิน"],
    "stock": ["รหัสลูกค้า", "รหัสสินค้า", "วันที่", "จำนวนคงเหลือ", "รูปจาก LINE"],
    # price_group is not read by Python today — warn-only, no required keys.
    "price_group": [],
}

# Base tabs to migrate (EXCLUDES bill_lines — that is a VIEW, never a source).
BASE_TABS: list[str] = [
    "price_group",
    "wholesale",
    "customer",
    "product",
    "bill",
    "bill_item",
    "stock",
]


def english_columns(tab_key: str) -> list[str]:
    return [eng for eng, _ in COLUMNS[tab_key]]


def thai_headers(tab_key: str) -> list[str]:
    return [thai for _, thai in COLUMNS[tab_key]]


def create_table_sql(tab_key: str) -> str:
    """CREATE TABLE with addressing-only autoincrement `_id` + all-TEXT columns."""
    cols = ",\n    ".join(f'"{eng}" TEXT' for eng in english_columns(tab_key))
    return (
        f'CREATE TABLE IF NOT EXISTS "{tab_key}" (\n'
        f"    _id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        f"    {cols}\n"
        f");"
    )


# bill_lines VIEW: aggregate bill_item by (bill_id, price_group), qty>0.
#   - item_id  = bill_id || '-' || price_group   (matches models.BillLine.line_id)
#   - bill_id  REQUIRED so bills.lines_for_bill can filter on รหัสใบส่ง (R3)
#   - qty      SUM, returned as INTEGER so pdf.py:126 str(qty) shows "3" not "3.0"
#   - unit_price MAX (constant within a (bill,group) via the app; MAX survives
#                dirty historical data without silently picking a wrong price, R4)
#   - amount   SUM as REAL (pdf wraps it in float()/:.2f)
CREATE_BILL_LINES_VIEW = """
CREATE VIEW IF NOT EXISTS "bill_lines" AS
SELECT
    "bill_id" || '-' || "price_group"      AS "item_id",
    "bill_id"                              AS "bill_id",
    "price_group"                          AS "price_group",
    CAST(SUM(CAST("qty" AS REAL)) AS INTEGER) AS "qty",
    MAX(CAST("unit_price" AS REAL))        AS "unit_price",
    SUM(CAST("amount" AS REAL))            AS "amount"
FROM "bill_item"
WHERE CAST("qty" AS REAL) > 0
GROUP BY "bill_id", "price_group";
""".strip()
