"""
Integration tests over the SQLite-backed lib/sheets surface.

Exercises the positional Sheets-emulation contract (AC5/M1), delete isolation
(AC6), the bill_lines VIEW (AC7), the active filter (AC8), create/delete
round-trip (AC9), cache no-raise + read-after-write freshness, concurrency
under WAL (AC10), and append length-mismatch behavior.
"""
from __future__ import annotations

from datetime import date

import pytest

from lib import bills, db, sheets


# --- AC5 positional fidelity + M1 first-match ------------------------------

def test_positional_fidelity_and_first_match(fresh_db):
    fresh_db()
    sheets.append("customer", ["C001", "ก", "มาตรฐาน", "a1", "p1", True])
    sheets.append("customer", ["C002", "ข", "มาตรฐาน", "a2", "p2", True])
    sheets.append("customer", ["C003", "ค", "ศว.", "a3", "p3", True])

    rows = sheets.customers()
    assert [r["รหัสลูกค้า"] for r in rows] == ["C001", "C002", "C003"]
    # Appended values come back byte-identical under the right Thai keys.
    assert rows[1] == {
        "รหัสลูกค้า": "C002", "ชื่อลูกค้า": "ข", "ชุดราคา": "มาตรฐาน",
        "ที่อยู่": "a2", "เบอร์โทร": "p2", "ใช้งาน": "1",  # bool True -> TEXT "1"
    }

    # find_row_by_key returns the offset update_row consumes (idx+2).
    idx = next(i for i, r in enumerate(rows) if r["รหัสลูกค้า"] == "C002")
    row_number = idx + 2
    assert sheets.find_row_by_key("customer", "C002") == row_number

    # update_row(row_number, ...) changes ONLY that row.
    sheets.update_row("customer", row_number,
                      ["C002", "ข-edited", "ศว.", "a2b", "p2b", False])
    rows2 = sheets.customers()
    assert rows2[0]["ชื่อลูกค้า"] == "ก"      # untouched
    assert rows2[2]["ชื่อลูกค้า"] == "ค"      # untouched
    assert rows2[1] == {
        "รหัสลูกค้า": "C002", "ชื่อลูกค้า": "ข-edited", "ชุดราคา": "ศว.",
        "ที่อยู่": "a2b", "เบอร์โทร": "p2b", "ใช้งาน": "0",  # bool False -> "0"
    }

    # delete_row removes the right one and shifts addressing.
    sheets.delete_row("customer", row_number)
    rows3 = sheets.customers()
    assert [r["รหัสลูกค้า"] for r in rows3] == ["C001", "C003"]

    # DUPLICATE code -> find_row_by_key returns the FIRST match.
    sheets.append("customer", ["C001", "dup", "มาตรฐาน", "", "", True])
    dup_rows = sheets.customers()
    assert [r["รหัสลูกค้า"] for r in dup_rows] == ["C001", "C003", "C001"]
    # First C001 is at offset 0 -> row_number 2.
    assert sheets.find_row_by_key("customer", "C001") == 2


# --- AC6 delete isolation (the critical one) -------------------------------

def test_delete_bill_isolation_surviving_items_byte_identical(fresh_db):
    fresh_db()
    # Two bills whose bill_item rows are INTERLEAVED in insertion order.
    # Insertion order (by _id): D0001, D0002, D0001, D0002, D0001.
    sheets.append("bill_item", ["I0001", "D0001", "P101", "1", "15", "12", "12"])
    sheets.append("bill_item", ["I0002", "D0002", "P201", "2", "20", "15", "30"])
    sheets.append("bill_item", ["I0003", "D0001", "P102", "3", "15", "12", "36"])
    sheets.append("bill_item", ["I0004", "D0002", "P202", "4", "20", "15", "60"])
    sheets.append("bill_item", ["I0005", "D0001", "P103", "5", "15", "12", "60"])
    # Bill header rows for both (delete_bill removes the header too).
    sheets.append("bill", ["D0001", "1/5/2026", "C001", "", "ร่าง"])
    sheets.append("bill", ["D0002", "2/5/2026", "C002", "", "ร่าง"])

    # Snapshot the SURVIVING bill's items (full dicts) before deletion.
    surviving_before = [
        it for it in sheets.bill_items()
        if it["รหัสใบส่ง"] == "D0002"
    ]
    assert len(surviving_before) == 2

    # Delete the interleaved bill D0001 (reverse-delete against _id offsets).
    bills.delete_bill("D0001")

    items_after = sheets.bill_items()
    # D0001 fully gone.
    assert all(it["รหัสใบส่ง"] != "D0001" for it in items_after)
    # D0002 items are BYTE-IDENTICAL (full dict compare), not merely count==2.
    surviving_after = [it for it in items_after if it["รหัสใบส่ง"] == "D0002"]
    assert surviving_after == surviving_before
    # Bill header for D0002 also survives; D0001 header gone.
    bill_ids = [b["รหัสใบส่ง"] for b in sheets.bills()]
    assert bill_ids == ["D0002"]


# --- AC7 VIEW (R3/R4/R6) ----------------------------------------------------

def _seed_two_group_bill(fresh_db):
    fresh_db()
    sheets.append("wholesale", ["มาตรฐาน-15", "มาตรฐาน", "15", "12"])
    sheets.append("wholesale", ["มาตรฐาน-20", "มาตรฐาน", "20", "15"])
    sheets.append("customer", ["C001", "ก", "มาตรฐาน", "", "", True])
    sheets.append("product", ["P301", "ขนม15", "15", "", "1", True])
    sheets.append("product", ["P401", "ขนม20", "20", "", "2", True])
    return bills.create_bill("C001", date(2026, 5, 21), {"P301": 3, "P401": 2})


def test_bill_lines_view_shape_and_sum(fresh_db):
    bid = _seed_two_group_bill(fresh_db)

    lines = bills.lines_for_bill(bid)
    assert len(lines) == 2  # one row per price group

    for ln in lines:
        # R3: รหัสใบส่ง present so lines_for_bill can filter on it.
        assert "รหัสใบส่ง" in ln
        assert ln["รหัสใบส่ง"] == bid
        assert "กลุ่มราคา" in ln
        # จำนวน is int-valued so pdf.py str(qty) renders "3" not "3.0".
        assert isinstance(ln["จำนวน"], int)
        assert str(ln["จำนวน"]) == str(int(ln["จำนวน"]))

    # R6: sum of line amounts equals bill_total (both qty>0).
    assert sum(ln["จำนวนเงิน"] for ln in lines) == bills.bill_total(bid)

    # sheets.bill_lines() returns the same Thai-keyed rows for this bill.
    raw = [l for l in sheets.bill_lines() if l["รหัสใบส่ง"] == bid]
    assert {l["กลุ่มราคา"] for l in raw} == {"15", "20"}


def test_bill_lines_view_uses_max_on_dirty_duplicate_price(fresh_db):
    fresh_db()
    # Two items, same (bill, group) but DIFFERENT หน่วยละ (dirty history).
    sheets.append("bill_item", ["I0001", "D0001", "P301", "3", "15", "12", "36"])
    sheets.append("bill_item", ["I0002", "D0001", "P302", "2", "15", "99", "198"])
    lines = bills.lines_for_bill("D0001")
    assert len(lines) == 1
    ln = lines[0]
    # R4: MAX(หน่วยละ) -> 99.0, no crash; qty SUM=5, amount SUM=234.
    assert ln["หน่วยละ"] == 99.0
    assert ln["จำนวน"] == 5
    assert ln["จำนวนเงิน"] == 234.0


# --- AC8 active filter ------------------------------------------------------

def test_active_customers_tolerant_filter(fresh_db):
    fresh_db()
    # ใช้งาน written as "1", "TRUE", python True (-> TEXT "1"), and "0"/"FALSE".
    sheets.append("customer", ["C001", "one", "s", "", "", "1"])
    sheets.append("customer", ["C002", "true", "s", "", "", "TRUE"])
    sheets.append("customer", ["C003", "pybool", "s", "", "", True])
    sheets.append("customer", ["C004", "zero", "s", "", "", "0"])
    sheets.append("customer", ["C005", "false", "s", "", "", "FALSE"])

    active_codes = {c["รหัสลูกค้า"] for c in sheets.active_customers()}
    assert active_codes == {"C001", "C002", "C003"}
    assert "C004" not in active_codes
    assert "C005" not in active_codes


def test_active_products_tolerant_filter(fresh_db):
    fresh_db()
    sheets.append("product", ["P101", "a", "15", "", "1", "TRUE"])
    sheets.append("product", ["P102", "b", "15", "", "2", "FALSE"])
    sheets.append("product", ["P103", "c", "15", "", "3", True])
    active_codes = {p["รหัสสินค้า"] for p in sheets.active_products()}
    assert active_codes == {"P101", "P103"}


# --- AC9 round-trip (no orphan rows) ---------------------------------------

def test_create_then_delete_bill_leaves_counts_unchanged(fresh_db):
    fresh_db()
    sheets.append("wholesale", ["มาตรฐาน-15", "มาตรฐาน", "15", "12"])
    sheets.append("customer", ["C001", "ก", "มาตรฐาน", "", "", True])
    sheets.append("product", ["P301", "ขนม", "15", "", "1", True])

    bills_before = len(sheets.bills())
    items_before = len(sheets.bill_items())

    bid = bills.create_bill("C001", date(2026, 5, 21), {"P301": 4})
    assert len(sheets.bills()) == bills_before + 1
    assert len(sheets.bill_items()) == items_before + 1

    bills.delete_bill(bid)
    # No orphan bill_item rows left behind.
    assert len(sheets.bills()) == bills_before
    assert len(sheets.bill_items()) == items_before


# --- cache no-raise + read-after-write freshness ---------------------------

def test_clear_caches_and_invalidate_never_raise(fresh_db):
    fresh_db()
    # Both are aliased to the same headless-safe routine; must not raise.
    sheets.clear_caches()
    sheets._invalidate()


def test_read_after_write_returns_fresh_data(fresh_db):
    fresh_db()
    assert sheets.customers() == []
    sheets.append("customer", ["C001", "fresh", "s", "", "", True])
    rows = sheets.customers()
    assert len(rows) == 1 and rows[0]["ชื่อลูกค้า"] == "fresh"


# --- AC10 concurrency -------------------------------------------------------

def test_busy_timeout_pragma_applied_on_fresh_connection(fresh_db):
    fresh_db()
    conn = db.connect()
    try:
        timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert timeout > 0
    finally:
        conn.close()


def test_concurrent_write_during_read_no_lock_under_wal(fresh_db):
    fresh_db()
    # Two independent connections on the same temp DB (WAL allows a reader to
    # coexist with a writer without "database is locked").
    reader = db.connect()
    writer = db.connect()
    try:
        # journal_mode must actually be WAL for concurrency to hold.
        assert reader.execute("PRAGMA journal_mode;").fetchone()[0].lower() == "wal"

        # Begin a read transaction on `reader` and hold a cursor open.
        rcur = reader.execute('SELECT _id FROM "customer" ORDER BY _id')
        rcur.fetchall()  # snapshot established

        # Writer commits an INSERT while the reader's connection is live.
        writer.execute(
            'INSERT INTO "customer" ("code","name","price_set",'
            '"address","phone","active") VALUES (?,?,?,?,?,?)',
            ["C001", "ก", "s", "", "", "1"],
        )
        writer.commit()  # must NOT raise OperationalError: database is locked

        # The writer's row is visible to a fresh read on the reader connection.
        again = reader.execute('SELECT "code" FROM "customer"').fetchall()
        assert [r["code"] for r in again] == ["C001"]
    finally:
        reader.close()
        writer.close()


# --- length mismatch --------------------------------------------------------

def test_append_overlong_row_raises_value_error(fresh_db):
    fresh_db()
    with pytest.raises(ValueError):
        # customer has 6 data columns; 7 values is overlong.
        sheets.append("customer", ["C001", "n", "s", "a", "p", True, "EXTRA"])


def test_append_short_row_pads_with_empty_string(fresh_db):
    fresh_db()
    sheets.append("customer", ["C001", "n"])  # 2 of 6 columns
    row = sheets.customers()[0]
    assert row == {
        "รหัสลูกค้า": "C001", "ชื่อลูกค้า": "n", "ชุดราคา": "",
        "ที่อยู่": "", "เบอร์โทร": "", "ใช้งาน": "",
    }
