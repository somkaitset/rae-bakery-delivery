"""
Tests for lib/pdf.py (formatter + line assembly + PDF/HTML renderers) and
lib/pdf_archive.py (local-disk PDF archive). Headless — no Streamlit runtime.

PDF value parity is asserted via the `_bill_table_data` seam (pdfminer is not
installed), plus a real `%PDF` build smoke. HTML parity is asserted on the
returned string. Both renderers consume the same assemble_lines + fmt_int_cell.
"""
from __future__ import annotations

import pytest
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm

from lib import config, pdf, pdf_archive


# ---------- fmt_int_cell ----------

def test_fmt_int_cell_integers_no_decimals_no_baht():
    assert pdf.fmt_int_cell(12) == "12"
    assert pdf.fmt_int_cell(12.0) == "12"
    assert pdf.fmt_int_cell(12.4) == "12"
    assert pdf.fmt_int_cell("36") == "36"
    # no decimals, no "บาท" suffix anywhere
    assert "." not in pdf.fmt_int_cell(12.4)
    assert "บาท" not in pdf.fmt_int_cell(12)


def test_fmt_int_cell_blank_zero_default():
    # cells: 0 / blank / None / non-numeric / negative -> ""
    assert pdf.fmt_int_cell(0) == ""
    assert pdf.fmt_int_cell(0.0) == ""
    assert pdf.fmt_int_cell("") == ""
    assert pdf.fmt_int_cell(None) == ""
    assert pdf.fmt_int_cell("garbage") == ""
    assert pdf.fmt_int_cell(-5) == ""


def test_fmt_int_cell_total_never_blank():
    # total row passes blank_zero=False -> a 0 total still shows "0"
    assert pdf.fmt_int_cell(0, blank_zero=False) == "0"
    assert pdf.fmt_int_cell(0.0, blank_zero=False) == "0"
    assert pdf.fmt_int_cell(572, blank_zero=False) == "572"
    assert pdf.fmt_int_cell("garbage", blank_zero=False) == "0"


# ---------- assemble_lines ----------

def test_assemble_lines_label_synthesis():
    out = pdf.assemble_lines([{"qty": 3, "price_group": "15", "unit_price": 12, "amount": 36}])
    assert out[0]["label"] == "15 บาท"


def test_assemble_lines_label_keeps_existing_baht():
    out = pdf.assemble_lines([{"qty": 3, "price_group": "15 บาท", "unit_price": 12, "amount": 36}])
    assert out[0]["label"] == "15 บาท"


def test_assemble_lines_filters_zero_qty():
    out = pdf.assemble_lines([
        {"qty": 0, "price_group": "10", "unit_price": 8, "amount": 0},
        {"qty": 3, "price_group": "15", "unit_price": 12, "amount": 36},
    ])
    assert len(out) == 1
    assert out[0]["label"] == "15 บาท"


def test_assemble_lines_sorted_ascending_by_price_group():
    out = pdf.assemble_lines([
        {"qty": 1, "price_group": "20", "unit_price": 16, "amount": 16},
        {"qty": 1, "price_group": "5", "unit_price": 4, "amount": 4},
        {"qty": 1, "price_group": "15", "unit_price": 12, "amount": 12},
    ])
    assert [r["label"] for r in out] == ["5 บาท", "15 บาท", "20 บาท"]


# ---------- value-level renderer parity (PDF seam + HTML) ----------

# fixture: tiers {15: qty13 @unit12, 20: qty26 @unit16} -> amounts 156, 416, total 572
FIXTURE_LINES = [
    {"qty": 13, "price_group": "15", "unit_price": 12, "amount": 156},
    {"qty": 26, "price_group": "20", "unit_price": 16, "amount": 416},
]
FIXTURE_TOTAL = 572
FIXTURE_CUSTOMER = {"code": "C002", "name": "พป."}
FIXTURE_BILL = {"bill_id": "D0001", "date": "29/5/2026"}

EXPECTED_VALUES = ["13", "26", "12", "16", "156", "416", "572"]


def test_pdf_table_data_value_parity():
    # the seam the PDF builds from — flatten to a string and assert values present
    data = pdf._bill_table_data(FIXTURE_LINES, FIXTURE_TOTAL)
    flat = [c for row in data for c in row]
    for v in EXPECTED_VALUES:
        assert v in flat, f"value {v} missing from PDF table_data {flat}"
    # total row: label sits in the รายการ column (col 1, per Sheet template),
    # integer total in the last column, never blank
    assert data[-1][1] == "รวมเป็นเงิน"
    assert data[-1][3] == "572"


def test_html_value_parity():
    html = pdf.render_bill_html(FIXTURE_BILL, FIXTURE_CUSTOMER, FIXTURE_LINES, FIXTURE_TOTAL)
    for v in EXPECTED_VALUES:
        assert v in html, f"value {v} missing from HTML"
    assert "รวมเป็นเงิน" in html


def test_renderers_use_customer_short_code_not_code():
    # short code comes from customer.name ("พป."), NOT code ("C002")
    html = pdf.render_bill_html(FIXTURE_BILL, FIXTURE_CUSTOMER, FIXTURE_LINES, FIXTURE_TOTAL)
    assert "พป." in html
    assert "C002" not in html
    # PDF: the customer field is the .name; assert the builder uses it (no raise)
    out = pdf.generate_bill_pdf(FIXTURE_BILL, FIXTURE_CUSTOMER, FIXTURE_LINES, FIXTURE_TOTAL)
    assert out[:4] == b"%PDF"


def test_html_has_a5_and_autoprint_markers():
    html = pdf.render_bill_html(FIXTURE_BILL, FIXTURE_CUSTOMER, FIXTURE_LINES, FIXTURE_TOTAL)
    assert "size: A5" in html
    assert "window.print()" in html


def test_html_signature_order_receiver_left_sender_right():
    html = pdf.render_bill_html(FIXTURE_BILL, FIXTURE_CUSTOMER, FIXTURE_LINES, FIXTURE_TOTAL)
    assert html.index("ผู้รับของ") < html.index("ผู้ส่งของ")


def test_generate_bill_pdf_smoke_builds_pdf():
    out = pdf.generate_bill_pdf(FIXTURE_BILL, FIXTURE_CUSTOMER, FIXTURE_LINES, FIXTURE_TOTAL)
    assert isinstance(out, bytes)
    assert out[:4] == b"%PDF"
    assert len(out) > 500


def test_generate_bill_pdf_zero_total_builds():
    # one tier totaling 0 still renders a valid PDF (total row never blank)
    out = pdf.generate_bill_pdf(FIXTURE_BILL, FIXTURE_CUSTOMER, [], 0)
    assert out[:4] == b"%PDF"


def test_generate_bill_pdf_five_tiers_builds():
    # max real bill = 5 price tiers; bounded table never collides with the
    # fixed-position signature — must still build a single valid PDF
    five = [
        {"qty": 1, "price_group": str(pg), "unit_price": up, "amount": up}
        for pg, up in [(10, 8), (12, 10), (15, 12), (20, 16), (25, 20)]
    ]
    out = pdf.generate_bill_pdf(FIXTURE_BILL, FIXTURE_CUSTOMER, five, 66)
    assert out[:4] == b"%PDF"


# ---------- signature position is row-count-independent ----------

class _RecordingCanvas:
    """Stub canvas capturing what _draw_signature draws (no pdfminer needed)."""
    def __init__(self):
        self.draws = []  # list of (kind, x, y, text)

    def saveState(self):
        pass

    def restoreState(self):
        pass

    def setFont(self, *args, **kwargs):
        pass

    def drawString(self, x, y, text):
        self.draws.append(("left", x, y, text))

    def drawRightString(self, x, y, text):
        self.draws.append(("right", x, y, text))


class _FakeDoc:
    pagesize = A5
    leftMargin = 12 * mm
    rightMargin = 12 * mm
    bottomMargin = 12 * mm


def test_pdf_signature_drawn_at_fixed_bottom_anchored_y():
    c = _RecordingCanvas()
    d = _FakeDoc()
    pdf._draw_signature(c, d, "Helvetica")

    # exactly the two signature strings, both at the SAME baseline Y
    assert len(c.draws) == 2
    ys = [y for (_, _, y, _) in c.draws]
    assert ys[0] == ys[1]
    # Y is anchored to the page bottom margin, not to the flowed table height
    assert ys[0] == d.bottomMargin + pdf.SIG_OFFSET_MM * mm
    # ผู้รับของ drawn left, ผู้ส่งของ drawn right
    by_kind = {kind: text for (kind, _, _, text) in c.draws}
    assert "ผู้รับของ" in by_kind["left"]
    assert "ผู้ส่งของ" in by_kind["right"]


def test_pdf_signature_not_in_flowed_table_data():
    # signature must NOT live in the flowed table seam (it's drawn on canvas);
    # this guards against regressing to a row-count-dependent flow element
    data = pdf._bill_table_data(FIXTURE_LINES, FIXTURE_TOTAL)
    flat = "".join(c for row in data for c in row)
    assert "ผู้รับของ" not in flat
    assert "ผู้ส่งของ" not in flat


def test_html_signature_bottom_anchored_for_print():
    html = pdf.render_bill_html(FIXTURE_BILL, FIXTURE_CUSTOMER, FIXTURE_LINES, FIXTURE_TOTAL)
    # print layout pins the signature to the page bottom regardless of row count
    assert "margin-top: auto" in html
    assert "flex-direction: column" in html


# ---------- font registration (graceful fallback is deploy-safety) ----------

def test_register_fonts_full_set_present():
    # the real secrets/ ships all bundled fonts -> roles map to the decorative ones
    roles = pdf._register_fonts()
    assert roles["body"] == "Sarabun"
    assert roles["title"] == "Charmonman"
    assert roles["head"] == "ChakraPetch-SemiBold"


def test_register_fonts_fallback_to_sarabun(tmp_path, monkeypatch):
    # deploy with ONLY Sarabun (no decorative fonts): title/head must collapse to
    # Sarabun-Bold — a REAL registered font, never an unregistered name (would crash build)
    (tmp_path / "Sarabun-Regular.ttf").write_bytes(b"x")
    (tmp_path / "Sarabun-Bold.ttf").write_bytes(b"x")
    monkeypatch.setattr(pdf, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(pdf, "_fonts_registered", True)  # skip parsing the dummy bytes
    roles = pdf._register_fonts()
    assert roles == {
        "body": "Sarabun", "bold": "Sarabun-Bold",
        "title": "Sarabun-Bold", "head": "Sarabun-Bold",
    }


def test_register_fonts_fallback_to_helvetica(tmp_path, monkeypatch):
    # no bundled fonts at all -> standard PDF fonts (always available), no crash
    monkeypatch.setattr(pdf, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(pdf, "_fonts_registered", True)
    roles = pdf._register_fonts()
    assert roles == {
        "body": "Helvetica", "bold": "Helvetica-Bold",
        "title": "Helvetica-Bold", "head": "Helvetica-Bold",
    }


# ---------- pdf_archive round-trip ----------

@pytest.fixture
def tmp_archive(tmp_path, monkeypatch):
    """Point BILLS_PDF_DIR at a temp dir. pdf_archive binds it at import time,
    so patch both the config attr and the module-level reference."""
    d = tmp_path / "bills_pdf"
    monkeypatch.setattr(config, "BILLS_PDF_DIR", d)
    monkeypatch.setattr(pdf_archive, "BILLS_PDF_DIR", d)
    return d


def test_pdf_archive_round_trip(tmp_archive):
    assert pdf_archive.is_archived("D0001") is False
    name = pdf_archive.save_pdf("D0001", b"hello-pdf")
    assert name == "D0001.pdf"
    assert pdf_archive.is_archived("D0001") is True
    assert pdf_archive.read_pdf("D0001") == b"hello-pdf"
    pdf_archive.delete_pdf("D0001")
    assert pdf_archive.is_archived("D0001") is False
    assert pdf_archive.read_pdf("D0001") is None


def test_pdf_archive_delete_missing_does_not_raise(tmp_archive):
    # missing_ok=True is load-bearing for revert-to-draft
    pdf_archive.delete_pdf("DOES_NOT_EXIST")  # must not raise


def test_pdf_archive_overwrite(tmp_archive):
    pdf_archive.save_pdf("D0002", b"first")
    pdf_archive.save_pdf("D0002", b"second")
    assert pdf_archive.read_pdf("D0002") == b"second"


def test_archive_path_under_bills_pdf_dir(tmp_archive):
    p = pdf_archive.archive_path("D0009")
    assert p == tmp_archive / "D0009.pdf"
