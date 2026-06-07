"""
Unit tests for the bill-edit data layer: lib/bills.update_bill, the status
setters (set_status/finalize/revert_to_draft), the pinned next_item_seq
snapshot, and price_group_sort_key. Seeded against a fresh temp SQLite DB.
"""
from __future__ import annotations

from datetime import date

import pytest

from lib import bills, db, sheets


# --- helpers ---------------------------------------------------------------

def _seed_prices():
    # unit_price looks up "{price_set}-{group}"; the price-id cell IS that string.
    sheets.append_many("wholesale", [
        ["มาตรฐาน-15", "มาตรฐาน", "15", "12"],
        ["มาตรฐาน-20", "มาตรฐาน", "20", "15"],
        ["มาตรฐาน-10", "มาตรฐาน", "10", "8"],
    ])


def _seed_products():
    sheets.append_many("product", [
        ["P101", "ก", "10", "", "1", True],
        ["P301", "ข", "15", "", "2", True],
        ["P302", "ค", "15", "", "3", True],
        ["P401", "ง", "20", "", "4", True],
    ])


def _seed_customer(code="C001"):
    sheets.append("customer", [code, "พป.", "มาตรฐาน", "", "", True])


def _items_for(bill_id):
    return [
        it for it in sheets.bill_items()
        if str(it.get("bill_id", "")) == bill_id
    ]


# --- update_bill replaces items, other bills untouched ---------------------

def test_update_bill_replaces_items_and_leaves_other_bills_intact(fresh_db):
    fresh_db()
    _seed_prices()
    _seed_products()
    _seed_customer()

    # B1 (the one we edit) and B2 (a second bill that must stay intact).
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append("bill", ["D0002", "2/1/2026", "C001", "", "ร่าง"])
    sheets.append_many("bill_item", [
        ["I0001", "D0001", "P301", "3", "15", "12", "36"],
        ["I0002", "D0001", "P302", "2", "15", "12", "24"],
        ["I0003", "D0002", "P101", "9", "10", "8", "72"],
    ])

    bills.update_bill("D0001", "C001", date(2026, 1, 5), {"P301": 5, "P401": 1})

    b1 = _items_for("D0001")
    by_prod = {it["product_code"]: it for it in b1}
    assert set(by_prod) == {"P301", "P401"}        # P302 gone, P401 added
    assert int(float(by_prod["P301"]["qty"])) == 5
    assert int(float(by_prod["P401"]["qty"])) == 1

    # bill_id unchanged; date/customer updated on the bill row.
    bill = next(b for b in sheets.bills() if b["bill_id"] == "D0001")
    assert bill["bill_id"] == "D0001"
    assert bill["date"] == "5/1/2026"
    assert bill["customer_code"] == "C001"

    # B2's single item is intact (WHERE bill_id=? did not touch it).
    b2 = _items_for("D0002")
    assert len(b2) == 1
    assert b2[0]["item_id"] == "I0003"
    assert int(float(b2[0]["qty"])) == 9

    # bill_total reflects the new amounts: P301 5*12=60, P401 1*15=15.
    assert bills.bill_total("D0001") == 75.0


def test_update_bill_recomputes_price_and_amount(fresh_db):
    fresh_db()
    _seed_prices()
    _seed_products()
    _seed_customer()
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "", "ร่าง"])

    bills.update_bill("D0001", "C001", date(2026, 1, 1), {"P301": 4, "P401": 2})

    by_prod = {it["product_code"]: it for it in _items_for("D0001")}
    # P301 -> group 15 -> unit 12 -> amount 48
    assert float(by_prod["P301"]["unit_price"]) == 12.0
    assert float(by_prod["P301"]["amount"]) == 48.0
    # P401 -> group 20 -> unit 15 -> amount 30
    assert float(by_prod["P401"]["unit_price"]) == 15.0
    assert float(by_prod["P401"]["amount"]) == 30.0


def test_update_bill_empty_clears_only_this_bill(fresh_db):
    fresh_db()
    _seed_prices()
    _seed_products()
    _seed_customer()
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append("bill", ["D0002", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append_many("bill_item", [
        ["I0001", "D0001", "P301", "3", "15", "12", "36"],
        ["I0002", "D0002", "P101", "9", "10", "8", "72"],
    ])

    # rows=[] (all qty 0) clears D0001's items but leaves D0002's intact.
    bills.update_bill("D0001", "C001", date(2026, 1, 1), {"P301": 0})

    assert _items_for("D0001") == []
    assert len(_items_for("D0002")) == 1


def test_update_bill_refuses_non_draft(fresh_db):
    fresh_db()
    _seed_prices()
    _seed_products()
    _seed_customer()
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append("bill_item", ["I0001", "D0001", "P301", "3", "15", "12", "36"])

    bills.finalize("D0001")  # ร่าง -> ส่งแล้ว

    with pytest.raises(ValueError):
        bills.update_bill("D0001", "C001", date(2026, 1, 1), {"P301": 99})

    # Items unchanged by the refused edit.
    items = _items_for("D0001")
    assert len(items) == 1
    assert int(float(items[0]["qty"])) == 3


# --- pinned next_item_seq snapshot (M3) ------------------------------------

def test_next_item_seq_snapshot_collision_safe(fresh_db):
    fresh_db()
    _seed_prices()
    _seed_products()
    _seed_customer()
    # B1 holds I0001,I0002; B2 holds I0009 — the global max is 9.
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append("bill", ["D0002", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append_many("bill_item", [
        ["I0001", "D0001", "P301", "3", "15", "12", "36"],
        ["I0002", "D0001", "P302", "2", "15", "12", "24"],
        ["I0009", "D0002", "P101", "1", "10", "8", "8"],
    ])

    bills.update_bill("D0001", "C001", date(2026, 1, 1), {"P301": 5, "P401": 1})

    new_ids = sorted(it["item_id"] for it in _items_for("D0001"))
    # New batch is reserved from max(existing)+1 = I0010, no collision with I0009.
    assert new_ids == ["I0010", "I0011"]
    # And it doesn't reuse I0009 (still on B2).
    assert _items_for("D0002")[0]["item_id"] == "I0009"


# --- status setters preserve ALL fields (M4) -------------------------------

def test_finalize_idempotent_and_preserves_fields(fresh_db):
    fresh_db()
    _seed_customer()
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "x", "ร่าง"])

    bills.finalize("D0001")
    b = next(b for b in sheets.bills() if b["bill_id"] == "D0001")
    assert b["status"] == "ส่งแล้ว"
    assert b["note"] == "x"
    assert b["date"] == "1/1/2026"
    assert b["customer_code"] == "C001"

    # Idempotent: a second finalize keeps status, no extra rows.
    bills.finalize("D0001")
    rows = [b for b in sheets.bills() if b["bill_id"] == "D0001"]
    assert len(rows) == 1
    assert rows[0]["status"] == "ส่งแล้ว"
    assert rows[0]["note"] == "x"


def test_revert_to_draft_round_trips(fresh_db):
    fresh_db()
    _seed_customer()
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "x", "ร่าง"])

    bills.finalize("D0001")
    bills.revert_to_draft("D0001")
    b = next(b for b in sheets.bills() if b["bill_id"] == "D0001")
    assert b["status"] == "ร่าง"
    # Fields still preserved through the round-trip.
    assert b["note"] == "x"
    assert b["date"] == "1/1/2026"
    assert b["customer_code"] == "C001"


# --- price_group_sort_key (AC4b) -------------------------------------------

def test_price_group_sort_key_orders_group_asc_then_code():
    products = [
        {"code": "P401", "price_group": "20"},
        {"code": "P101", "price_group": "10"},
        {"code": "P302", "price_group": "15 บาท"},  # tolerate trailing label
        {"code": "P201", "price_group": "12"},
        {"code": "P301", "price_group": "15"},
        {"code": "P501", "price_group": "25"},
    ]
    ordered = sorted(products, key=bills.price_group_sort_key)
    groups = [int("".join(c for c in p["price_group"] if c.isdigit())) for p in ordered]
    assert groups == [10, 12, 15, 15, 20, 25]
    # Within group 15, code A->Z: P301 before P302.
    g15 = [p["code"] for p in ordered if p["price_group"].startswith("15")]
    assert g15 == ["P301", "P302"]


def test_price_group_sort_key_unparseable_sinks_last():
    products = [
        {"code": "PX", "price_group": "ไม่มี"},
        {"code": "P101", "price_group": "10"},
    ]
    ordered = sorted(products, key=bills.price_group_sort_key)
    assert [p["code"] for p in ordered] == ["P101", "PX"]


# --- replace_bill_items primitive directly --------------------------------

def test_replace_bill_items_primitive_single_set(fresh_db):
    fresh_db()
    sheets.append_many("bill_item", [
        ["I0001", "D0001", "P301", "3", "15", "12", "36"],
        ["I0002", "D0002", "P101", "9", "10", "8", "72"],
    ])
    conn = fresh_db()  # fresh temp DB helper; re-runs ensure_db() and returns a live conn
    try:
        db.replace_bill_items(conn, [
            ["I0010", "D0001", "P401", "5", "20", "15", "75"],
        ], "D0001")
    finally:
        conn.close()

    b1 = _items_for("D0001")
    assert len(b1) == 1
    assert b1[0]["item_id"] == "I0010"
    # Other bill untouched.
    assert len(_items_for("D0002")) == 1


# --- delete_bill cascade (atomic, keyed by bill_id) ------------------------

def test_delete_bill_removes_bill_and_all_items(fresh_db):
    fresh_db()
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append("bill", ["D0002", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append_many("bill_item", [
        ["I0001", "D0001", "P301", "3", "15", "12", "36"],
        ["I0002", "D0001", "P302", "2", "15", "12", "24"],
        ["I0003", "D0002", "P101", "9", "10", "8", "72"],
    ])

    n = bills.delete_bill("D0001")

    # 2 items + 1 bill row deleted.
    assert n == 3
    assert [b["bill_id"] for b in sheets.bills()] == ["D0002"]
    assert _items_for("D0001") == []
    # The other bill and its item are untouched.
    assert len(_items_for("D0002")) == 1


def test_delete_bill_only_targets_matching_bill_id(fresh_db):
    fresh_db()
    # Interleave items across two bills so a row-position scheme would be fragile;
    # DELETE WHERE bill_id must remove exactly D0001's rows regardless of order.
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append("bill", ["D0002", "1/1/2026", "C001", "", "ร่าง"])
    sheets.append_many("bill_item", [
        ["I0001", "D0002", "P101", "1", "10", "8", "8"],
        ["I0002", "D0001", "P301", "3", "15", "12", "36"],
        ["I0003", "D0002", "P302", "2", "15", "12", "24"],
        ["I0004", "D0001", "P401", "1", "20", "15", "15"],
    ])

    n = bills.delete_bill("D0001")

    assert n == 3  # I0002 + I0004 + the D0001 bill row
    remaining = sorted(it["item_id"] for it in sheets.bill_items())
    assert remaining == ["I0001", "I0003"]  # only D0002's items survive
    assert [b["bill_id"] for b in sheets.bills()] == ["D0002"]


def test_delete_bill_missing_returns_zero(fresh_db):
    fresh_db()
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "", "ร่าง"])

    n = bills.delete_bill("D9999")

    assert n == 0
    assert len(sheets.bills()) == 1
