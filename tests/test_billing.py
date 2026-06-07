"""
Unit tests for lib/billing.py (day aggregation, per-year numbering, invoice/
receipt lifecycle) and the lib/pdf.py billing renderers (table seam + %PDF smoke).

DB-backed tests use the fresh_db fixture (temp SQLite). PDF/format tests are pure.
"""
from __future__ import annotations

from datetime import date

import pytest

from lib import billing, pdf, sheets


# --- day_lines aggregation -------------------------------------------------

def _seed_two_days(extra_draft: bool = True):
    """C006: two delivered bills on 4/6 (231) + one on 5/6 (160), one draft on 6/6."""
    sheets.append("bill", ["D1", "4/6/2026", "C006", "", "ส่งแล้ว"])
    sheets.append_many("bill_item", [
        ["I1", "D1", "P1", "10", "15", "12", "120"],
        ["I2", "D1", "P2", "5", "20", "15", "75"],
    ])
    sheets.append("bill", ["D2", "4/6/2026", "C006", "", "ส่งแล้ว"])
    sheets.append_many("bill_item", [["I3", "D2", "P1", "3", "15", "12", "36"]])
    sheets.append("bill", ["D3", "5/6/2026", "C006", "", "ส่งแล้ว"])
    sheets.append_many("bill_item", [["I4", "D3", "P3", "8", "25", "20", "160"]])
    if extra_draft:
        sheets.append("bill", ["D4", "6/6/2026", "C006", "", "ร่าง"])
        sheets.append_many("bill_item", [["I5", "D4", "P1", "100", "15", "12", "1200"]])


def test_day_lines_groups_by_day_and_sums(fresh_db):
    fresh_db()
    _seed_two_days()
    lines = billing.day_lines("C006", date(2026, 6, 1), date(2026, 6, 30))
    assert [(ln["date_str"], ln["amount"]) for ln in lines] == [
        ("4/6/2026", 231.0),
        ("5/6/2026", 160.0),
    ]
    assert billing.grand_total(lines) == 391.0


def test_day_lines_excludes_drafts_by_default(fresh_db):
    fresh_db()
    _seed_two_days()
    # the 6/6 draft (1200) must not appear
    lines = billing.day_lines("C006", date(2026, 6, 1), date(2026, 6, 30))
    assert all(ln["date_str"] != "6/6/2026" for ln in lines)
    # opting in to every status surfaces it
    lines_all = billing.day_lines("C006", date(2026, 6, 1), date(2026, 6, 30), statuses=())
    assert any(ln["date_str"] == "6/6/2026" for ln in lines_all)


def test_day_lines_respects_date_range(fresh_db):
    fresh_db()
    _seed_two_days(extra_draft=False)
    lines = billing.day_lines("C006", date(2026, 6, 5), date(2026, 6, 5))
    assert [ln["date_str"] for ln in lines] == ["5/6/2026"]


def test_day_lines_filters_other_customers(fresh_db):
    fresh_db()
    _seed_two_days(extra_draft=False)
    sheets.append("bill", ["D9", "4/6/2026", "C001", "", "ส่งแล้ว"])
    sheets.append_many("bill_item", [["I9", "D9", "P1", "50", "15", "12", "600"]])
    lines = billing.day_lines("C006", date(2026, 6, 1), date(2026, 6, 30))
    assert billing.grand_total(lines) == 391.0  # C001's 600 excluded


# --- numbering (reset per year) --------------------------------------------

def test_next_invoice_no_resets_per_year(fresh_db):
    fresh_db()
    assert billing.next_invoice_no(date(2026, 6, 7)) == "INV-2026-0001"
    billing.create_invoice("C006", date(2026, 6, 7), date(2026, 6, 1), date(2026, 6, 30))
    assert billing.next_invoice_no(date(2026, 6, 8)) == "INV-2026-0002"
    # a different year restarts at 0001
    assert billing.next_invoice_no(date(2027, 1, 2)) == "INV-2027-0001"


def test_next_receipt_no_resets_per_year(fresh_db):
    fresh_db()
    assert billing.next_receipt_no(date(2026, 6, 7)) == "RCP-2026-0001"


# --- invoice / receipt lifecycle -------------------------------------------

def test_create_invoice_records_unpaid(fresh_db):
    fresh_db()
    no = billing.create_invoice("C006", date(2026, 6, 7), date(2026, 6, 1), date(2026, 6, 30), "x")
    inv = billing.get_invoice(no)
    assert inv is not None
    assert inv["customer_code"] == "C006"
    assert inv["period_start"] == "1/6/2026"
    assert inv["period_end"] == "30/6/2026"
    assert inv["status"] == billing.INVOICE_STATUS_UNPAID
    assert inv["note"] == "x"


def test_create_receipt_copies_invoice_and_marks_paid(fresh_db):
    fresh_db()
    inv_no = billing.create_invoice("C006", date(2026, 6, 7), date(2026, 6, 1), date(2026, 6, 30))
    rcp_no = billing.create_receipt(inv_no, date(2026, 6, 9), "เงินสด")

    rcp = billing.get_receipt(rcp_no)
    assert rcp["invoice_no"] == inv_no
    assert rcp["customer_code"] == "C006"
    assert rcp["period_start"] == "1/6/2026"
    assert rcp["period_end"] == "30/6/2026"
    assert rcp["payment_method"] == "เงินสด"
    # the invoice flips to paid
    assert billing.get_invoice(inv_no)["status"] == billing.INVOICE_STATUS_PAID


def test_create_receipt_unknown_invoice_raises(fresh_db):
    fresh_db()
    with pytest.raises(ValueError):
        billing.create_receipt("INV-2026-9999", date(2026, 6, 9), "เงินสด")


def test_delete_invoice_refuses_when_receipt_exists(fresh_db):
    fresh_db()
    inv_no = billing.create_invoice("C006", date(2026, 6, 7), date(2026, 6, 1), date(2026, 6, 30))
    billing.create_receipt(inv_no, date(2026, 6, 9), "เงินสด")
    with pytest.raises(ValueError):
        billing.delete_invoice(inv_no)
    assert billing.get_invoice(inv_no) is not None  # still there


def test_delete_invoice_without_receipt(fresh_db):
    fresh_db()
    inv_no = billing.create_invoice("C006", date(2026, 6, 7), date(2026, 6, 1), date(2026, 6, 30))
    billing.delete_invoice(inv_no)
    assert billing.get_invoice(inv_no) is None


def test_delete_receipt_reverts_invoice_to_unpaid(fresh_db):
    fresh_db()
    inv_no = billing.create_invoice("C006", date(2026, 6, 7), date(2026, 6, 1), date(2026, 6, 30))
    rcp_no = billing.create_receipt(inv_no, date(2026, 6, 9), "เงินสด")
    billing.delete_receipt(rcp_no)
    assert billing.get_receipt(rcp_no) is None
    assert billing.get_invoice(inv_no)["status"] == billing.INVOICE_STATUS_UNPAID


# --- fmt_baht --------------------------------------------------------------

def test_fmt_baht_thousands_separator_no_decimals():
    assert pdf.fmt_baht(5451) == "5,451"
    assert pdf.fmt_baht(789) == "789"
    assert pdf.fmt_baht(1320.4) == "1,320"
    assert "." not in pdf.fmt_baht(1320.4)
    assert "บาท" not in pdf.fmt_baht(5451)


def test_fmt_baht_blank_zero():
    assert pdf.fmt_baht(0) == "0"                 # default: total cells never blank
    assert pdf.fmt_baht(0, blank_zero=True) == ""
    assert pdf.fmt_baht("garbage") == "0"


# --- billing PDF/HTML renderers --------------------------------------------

FIXTURE_LINES = [
    {"date_str": "25/5/2026", "amount": 1320},
    {"date_str": "26/5/2026", "amount": 789},
]
FIXTURE_TOTAL = 2109
SHOP = {"name": "เรเบเกอรี่", "address": "addr", "tax_id": "123", "signatory": "ผู้เซ็น",
        "bank": {"account_name": "acct", "bank_name": "ธ", "account_no": "1-2-3"}}
CUST = {"company_name": "บริษัท x", "tax_id": "999", "branch": "สำนักงานใหญ่", "billing_address": "ที่อยู่"}


def test_billing_table_data_value_parity():
    data = pdf._billing_table_data(FIXTURE_LINES, FIXTURE_TOTAL)
    flat = [c for row in data for c in row]
    for v in ["25/5/2026", "26/5/2026", "1,320", "789", "2,109"]:
        assert v in flat, f"{v} missing from {flat}"
    # last row is the grand total
    assert data[-1][1] == "รวมทั้งสิ้น"
    assert data[-1][2] == "2,109"
    # rows are numbered 1..n
    assert data[1][0] == "1" and data[2][0] == "2"


def test_generate_invoice_pdf_smoke():
    out = pdf.generate_invoice_pdf(SHOP, CUST, {"number": "INV-2026-0001", "date": "29/5/2026"},
                                   FIXTURE_LINES, FIXTURE_TOTAL)
    assert out[:4] == b"%PDF"
    assert len(out) > 500


def test_generate_receipt_pdf_smoke():
    out = pdf.generate_receipt_pdf(
        SHOP, CUST,
        {"number": "RCP-2026-0001", "date": "29/5/2026", "invoice_ref": "INV-2026-0001",
         "payment_method": "เงินสด"},
        FIXTURE_LINES, FIXTURE_TOTAL,
    )
    assert out[:4] == b"%PDF"


def test_invoice_html_has_title_and_bank():
    html = pdf.render_billing_html("invoice", SHOP, CUST,
                                   {"number": "INV-2026-0001", "date": "29/5/2026"},
                                   FIXTURE_LINES, FIXTURE_TOTAL)
    assert "ใบแจ้งหนี้" in html
    assert "size: A5" in html and "window.print()" in html
    assert "กรุณาชำระเงินโดยโอนเข้าบัญชี" in html
    for v in ["1,320", "789", "2,109"]:
        assert v in html


def test_receipt_html_marks_selected_payment_method():
    html = pdf.render_billing_html(
        "receipt", SHOP, CUST,
        {"number": "RCP-2026-0001", "date": "29/5/2026", "invoice_ref": "INV-2026-0001",
         "payment_method": "เงินสด"},
        FIXTURE_LINES, FIXTURE_TOTAL,
    )
    assert "ใบเสร็จรับเงิน" in html
    assert "อ้างถึงใบแจ้งหนี้" in html
    assert "[X] เงินสด" in html
    assert "[ ] โอนเข้าบัญชีธนาคาร" in html.replace("&nbsp;", " ")
