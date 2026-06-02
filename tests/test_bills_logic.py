"""
Unit tests for lib/bills.py pure logic against a seeded temp SQLite DB.

Covers ID generators, price lookup, the bill_total/bill_qty_total qty>0
asymmetry, suggest_qty, the tolerant _to_float, and parse_date/fmt_date.
"""
from __future__ import annotations

from datetime import date

import pytest

from lib import bills, sheets


# --- ID generators ---------------------------------------------------------

def test_next_bill_id_sequencing(fresh_db):
    fresh_db()
    assert bills.next_bill_id() == "D0001"
    sheets.append("bill", ["D0001", "1/1/2026", "C001", "", "ร่าง"])
    assert bills.next_bill_id() == "D0002"
    sheets.append("bill", ["D0009", "1/1/2026", "C001", "", "ร่าง"])
    # Max-seq based, not count based: D0009 present -> next is D0010.
    assert bills.next_bill_id() == "D0010"


def test_next_product_code_price_group_prefix_map(fresh_db):
    fresh_db()
    # group "10" -> P1xx, group "15" -> P3xx (prefix_map in bills.py).
    assert bills.next_product_code("10") == "P101"
    sheets.append("product", ["P101", "a", "10", "", "1", True])
    sheets.append("product", ["P103", "c", "10", "", "3", True])  # gap to 03
    # Max seq for P1 prefix is 03 -> next P104 (gaps don't fill).
    assert bills.next_product_code("10") == "P104"
    # group "15" maps to prefix P3 and is independent of the P1 series.
    assert bills.next_product_code("15") == "P301"
    # Unmapped group falls back to prefix P9.
    assert bills.next_product_code("99") == "P901"


def test_next_customer_code(fresh_db):
    fresh_db()
    assert bills.next_customer_code() == "C001"
    sheets.append("customer", ["C001", "ก", "มาตรฐาน", "", "", True])
    sheets.append("customer", ["C005", "ข", "มาตรฐาน", "", "", True])
    assert bills.next_customer_code() == "C006"


def test_next_stock_id(fresh_db):
    fresh_db()
    assert bills.next_stock_id() == "S0001"
    sheets.append("stock", ["S0001", "1/1/2026", "C001", "P101", "5", "", ""])
    assert bills.next_stock_id() == "S0002"


# --- Price lookup ----------------------------------------------------------

def test_price_map_and_unit_price(fresh_db):
    fresh_db()
    # price_map keys off รหัสราคา (col 1); unit_price looks up "{set}-{group}",
    # so the price-id cell itself must equal that composed string.
    sheets.append("wholesale", ["มาตรฐาน-15", "มาตรฐาน", "15", "12"])
    sheets.append("wholesale", ["ศว.-20", "ศว.", "20", "15"])
    pm = bills.price_map()
    assert pm["มาตรฐาน-15"] == 12.0
    assert pm["ศว.-20"] == 15.0
    assert bills.unit_price("มาตรฐาน", "15") == 12.0
    assert bills.unit_price("ศว.", "20") == 15.0
    # Missing combo -> 0.0 (default).
    assert bills.unit_price("ไม่มี", "99") == 0.0


# --- bill_total vs bill_qty_total asymmetry --------------------------------

def test_bill_total_filters_qty_but_qty_total_does_not(fresh_db):
    fresh_db()
    bid = "D0001"
    # Three items: two with qty>0, one with qty 0 (a returned/cancelled line).
    sheets.append_many("bill_item", [
        ["I0001", bid, "P101", "3", "15", "12", "36"],
        ["I0002", bid, "P102", "2", "15", "12", "24"],
        ["I0003", bid, "P103", "0", "15", "12", "0"],
    ])
    # bill_total filters qty>0: 36 + 24 (the qty=0 line excluded).
    assert bills.bill_total(bid) == 60.0
    # bill_qty_total does NOT filter on qty>0: 3 + 2 + 0.
    assert bills.bill_qty_total(bid) == 5

    # Make the asymmetry sharper: a qty=0 line carrying a nonzero amount
    # contributes to neither (qty filter on total) but to qty_total it adds 0.
    sheets.append("bill_item", ["I0004", bid, "P104", "0", "15", "12", "99"])
    assert bills.bill_total(bid) == 60.0      # 99 excluded (qty not > 0)
    assert bills.bill_qty_total(bid) == 5     # still 5 (adds 0)


# --- suggest_qty -----------------------------------------------------------

def test_suggest_qty_avg_minus_latest_stock(fresh_db):
    fresh_db()
    cust, prod = "C001", "P101"
    today = date.today()

    def dstr(days_ago):
        return bills.fmt_date(date.fromordinal(today.toordinal() - days_ago))

    # Two recent bills (within 7 days) for this customer+product: qty 4 and 6.
    sheets.append_many("bill", [
        ["D0001", dstr(1), cust, "", "ส่งแล้ว"],
        ["D0002", dstr(3), cust, "", "ส่งแล้ว"],
        # An OLD bill (>7 days) that must be ignored by the 7-day window.
        ["D0003", dstr(30), cust, "", "ส่งแล้ว"],
        # A bill for a DIFFERENT customer that must be ignored.
        ["D0004", dstr(1), "C999", "", "ส่งแล้ว"],
    ])
    sheets.append_many("bill_item", [
        ["I0001", "D0001", prod, "4", "15", "12", "48"],
        ["I0002", "D0002", prod, "6", "15", "12", "72"],
        ["I0003", "D0003", prod, "100", "15", "12", "1200"],  # old, ignored
        ["I0004", "D0004", prod, "100", "15", "12", "1200"],  # other cust, ignored
    ])
    # Latest stock within stock_max_age_days(=2): remaining 2.
    sheets.append("stock", ["S0001", dstr(1), cust, prod, "2", "", ""])

    # avg(4,6)=5 ; minus latest stock 2 -> 3.
    assert bills.suggest_qty(cust, prod) == 3

    # No history at all -> 0 (max(0, 0-0)).
    assert bills.suggest_qty(cust, "P999") == 0


# --- _to_float tolerance ---------------------------------------------------

def test_to_float_tolerance():
    # Documented (and slightly surprising) behavior: the guard returns
    # float(bool(x)); bool("FALSE") is True (non-empty string) -> 1.0.
    assert bills._to_float("TRUE") == 1.0
    assert bills._to_float("FALSE") == 1.0   # NOT 0.0 — non-empty string is truthy
    assert bills._to_float(True) == 1.0
    assert bills._to_float(False) == 0.0
    assert bills._to_float("") == 0.0
    assert bills._to_float(None) == 0.0
    assert bills._to_float("3.5") == 3.5
    assert bills._to_float(3) == 3.0
    # Unparseable -> 0.0, never raises.
    assert bills._to_float("abc") == 0.0


# --- parse_date / fmt_date round-trip --------------------------------------

def test_parse_fmt_date_round_trip():
    d = bills.parse_date("21/5/2026")
    assert d == date(2026, 5, 21)
    # No leading zeros on round-trip (matches the Sheet's d/m/yyyy text).
    assert bills.fmt_date(d) == "21/5/2026"
    # 2-digit year is normalized to 20xx.
    assert bills.parse_date("1/2/26") == date(2026, 2, 1)
    # Unparseable input -> None.
    assert bills.parse_date("not-a-date") is None
    assert bills.parse_date("") is None
