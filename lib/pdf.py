"""
PDF บิลส่งของ — ใช้ ReportLab + ฟอนต์ Sarabun (Thai)

วาง Sarabun-Regular.ttf และ Sarabun-Bold.ttf ไว้ที่ secrets/ (ดาวน์โหลดจาก Google Fonts)
ถ้าไม่มีฟอนต์ จะ fallback เป็น Helvetica (ภาษาไทยจะเป็นกล่อง)

ฟอนต์ตกแต่งตาม template Sheet (ทางเลือก): Charmonman = ชื่อร้าน, Chakra Petch = หัวบิล/หัวตาราง.
ขาดได้ — _register_fonts จะ fallback เป็น Sarabun. ดู secrets/README.md สำหรับคำสั่งดาวน์โหลด.

Layout ตรงตาม template จริง (ส่งโรงเรียน2022.xlsx ชีต "พิมพ์บิล พป."):
ชื่อร้านกลาง + "บิลส่งของ" / รหัสย่อลูกค้า ซ้าย + วันที่ ขวา /
ตาราง จำนวน|รายการ|หน่วยละ|จำนวนเงิน (เลขจำนวนเต็ม, ช่องว่างถ้า 0) /
แถว "รวมเป็นเงิน" / ลายเซ็น ผู้รับของ ซ้าย + ผู้ส่งของ ขวา

`render_bill_html` เป็น HTML สำหรับ auto-pop print dialog บนเครื่องเจ้าของ
(PDF คือ artifact ตัวจริง — HTML แค่ความสะดวกหน้าจอ) ทั้งสอง renderer
อ่านค่าจาก assemble_lines + fmt_int_cell ชุดเดียวกัน → ค่าตรงกันเสมอ
"""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


SHOP_NAME = "เรเบเกอรี่"

SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets"

# ฟอนต์ตาม template Google Sheet: ชื่อร้าน = Charmonman (ลายมือ), หัวบิล/หัวตาราง = Chakra Petch,
# เนื้อหา/แถวรวม/ลายเซ็น = Sarabun. ทุกบทบาทมี fallback (ดู _register_fonts) — deploy ที่ไม่มี
# ฟอนต์ตกแต่งก็ยัง render ได้ (ตกไป Sarabun; ไม่มี Sarabun → Helvetica).
_FONT_FILES = {
    "Sarabun": "Sarabun-Regular.ttf",
    "Sarabun-Bold": "Sarabun-Bold.ttf",
    "Charmonman": "Charmonman-Regular.ttf",
    "ChakraPetch": "ChakraPetch-Regular.ttf",
    "ChakraPetch-SemiBold": "ChakraPetch-SemiBold.ttf",
}

_fonts_registered = False


def _register_fonts() -> dict[str, str]:
    """Register every bundled font that exists (once), then return a role→name
    map with graceful fallbacks.

    roles: body/bold (Sarabun), title (Charmonman→bold), head (Chakra Petch→bold).
    A deploy with only Sarabun still works: title/head collapse to Sarabun-Bold.
    """
    global _fonts_registered
    available = {n for n, fn in _FONT_FILES.items() if (SECRETS_DIR / fn).exists()}
    if not _fonts_registered:
        for name in available:
            pdfmetrics.registerFont(TTFont(name, str(SECRETS_DIR / _FONT_FILES[name])))
        _fonts_registered = True

    body = "Sarabun" if "Sarabun" in available else "Helvetica"
    bold = (
        "Sarabun-Bold" if "Sarabun-Bold" in available
        else ("Helvetica-Bold" if body == "Helvetica" else body)
    )
    title = "Charmonman" if "Charmonman" in available else bold
    head = (
        "ChakraPetch-SemiBold" if "ChakraPetch-SemiBold" in available
        else ("ChakraPetch" if "ChakraPetch" in available else bold)
    )
    return {"body": body, "bold": bold, "title": title, "head": head}


# --- shared formatting + line assembly (used by BOTH the PDF and the HTML) ---

def fmt_int_cell(value, blank_zero: bool = True) -> str:
    """ค่า → สตริงจำนวนเต็ม (ไม่มีทศนิยม ไม่มี "บาท").

    blank_zero=True (ช่องในตาราง): 0 / ว่าง / None / ไม่ใช่ตัวเลข → "" (ตรงตาม template)
    blank_zero=False (แถวรวม): 0 → "0" (แถวรวมห้ามว่าง)
    """
    try:
        n = round(float(value))
    except (TypeError, ValueError):
        return "" if blank_zero else "0"
    if blank_zero and n <= 0:
        return ""
    return str(n)


def _pg_num(price_group) -> int:
    """เลขนำหน้าของกลุ่มราคา (เช่น '15' หรือ '15 บาท' → 15) สำหรับใช้ sort.
    parse ไม่ได้ → sentinel ใหญ่ (จมไปท้าย)."""
    s = str(price_group or "").strip()
    digits = ""
    for ch in s:
        if ch.isdigit():
            digits += ch
        else:
            break
    try:
        return int(digits)
    except ValueError:
        return 10 ** 6


def _pg_label(price_group) -> str:
    """label คอลัมน์ "รายการ": เลขเปล่า '15' → '15 บาท'; ถ้าลงท้าย 'บาท' อยู่แล้วคงเดิม."""
    s = str(price_group or "").strip()
    if not s:
        return ""
    if s.endswith("บาท"):
        return s
    return f"{s} บาท"


def assemble_lines(lines: list[dict]) -> list[dict]:
    """จาก bill_lines-shaped rows (keys: qty, price_group, unit_price, amount)
    → list ของ dict {qty, label, unit_price, amount} เรียงตามกลุ่มราคาน้อย→มาก,
    เฉพาะ qty > 0 (VIEW กรองแล้ว แต่กันไว้)."""
    out: list[dict] = []
    for ln in lines:
        try:
            qty = float(ln.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            continue
        out.append({
            "qty": ln.get("qty", 0),
            "label": _pg_label(ln.get("price_group", "")),
            "unit_price": ln.get("unit_price", 0),
            "amount": ln.get("amount", 0),
        })
    out.sort(key=lambda r: (_pg_num(r["label"]), r["label"]))
    return out


def _bill_table_data(lines: list[dict], total) -> list[list[str]]:
    """สร้าง table_data (รวม header + แถวรายการ + แถวรวม) จาก assemble_lines.
    seam ที่ test ใช้ตรวจค่าใน PDF (เพราะไม่มี pdfminer)."""
    data: list[list[str]] = [["จำนวน", "รายการ", "หน่วยละ", "จำนวนเงิน"]]
    for ln in assemble_lines(lines):
        data.append([
            fmt_int_cell(ln["qty"]),
            ln["label"],
            fmt_int_cell(ln["unit_price"]),
            fmt_int_cell(ln["amount"]),
        ])
    # "รวมเป็นเงิน" อยู่คอลัมน์ "รายการ" (ชิดขวา) ตาม template — จำนวน/หน่วยละ เว้นว่าง
    data.append(["", "รวมเป็นเงิน", "", fmt_int_cell(total, blank_zero=False)])
    return data


# ลายเซ็นวาง baseline สูงจาก bottom margin เท่านี้ (mm) — ค่าคงที่ทุกใบ
SIG_OFFSET_MM = 14


def _draw_signature(canvas, doc, font_name: str) -> None:
    """วาดลายเซ็น ผู้รับของ (ซ้าย) / ผู้ส่งของ (ขวา) ที่ baseline Y คงที่จากขอบล่าง
    ของหน้า A5 ผ่าน page callback ของ ReportLab. เพราะไม่ flow ต่อท้ายตาราง
    ตำแหน่งจึงเท่ากันทุกบิล ไม่ว่าตารางจะมีกี่แถว (กลุ่มราคา ≤ 5 ตารางจึงไม่ชน)."""
    y = doc.bottomMargin + SIG_OFFSET_MM * mm
    canvas.saveState()
    canvas.setFont(font_name, 11)
    canvas.drawString(doc.leftMargin, y, "ผู้รับของ_____________")
    canvas.drawRightString(
        doc.pagesize[0] - doc.rightMargin, y, "ผู้ส่งของ_____________"
    )
    canvas.restoreState()


def generate_bill_pdf(
    bill: dict,
    customer: dict,
    lines: list[dict],
    total: float,
) -> bytes:
    """
    สร้าง PDF บิลส่งของ (A5) — layout ตรงตาม template

    Args:
        bill: dict ของแถว "ใบส่งสินค้า" — ใช้ date
        customer: dict ของแถว "ลูกค้า" — รหัสย่อมาจาก name (เช่น "พป."), ไม่ใช่ code ("C002")
        lines: list ของ dict จาก bill_lines — keys: qty, price_group, unit_price, amount
        total: ยอดรวม

    Returns:
        PDF เป็น bytes
    """
    fonts = _register_fonts()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A5,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"บิล {bill.get('bill_id', '')}",
    )

    # leading กว้างกว่า 1.2x ดีฟอลต์ เพราะ Charmonman/วรรณยุกต์ไทยซ้อนสูง — กันหัวบิลทับบรรทัดถัดไป
    title_st = ParagraphStyle(
        "title", fontName=fonts["title"], fontSize=24, leading=34, alignment=1, spaceAfter=4
    )
    sub_st = ParagraphStyle(
        "sub", fontName=fonts["head"], fontSize=18, leading=24, alignment=1, spaceAfter=10
    )
    meta_left_st = ParagraphStyle(
        "meta_left", fontName=fonts["head"], fontSize=16, alignment=0
    )
    meta_right_st = ParagraphStyle(
        "meta_right", fontName=fonts["head"], fontSize=14, alignment=2
    )
    # รหัสย่อลูกค้า = customer.name (เช่น "พป."), ไม่ใช่ code ("C002")
    short_code = str(customer.get("name", "") or "")
    date_str = str(bill.get("date", "") or "")

    story = [
        Paragraph(SHOP_NAME, title_st),
        Paragraph("บิลส่งของ", sub_st),
    ]

    # แถว meta: รหัสย่อ ซ้าย / วันที่ ขวา (borderless 2-col)
    meta = Table(
        [[Paragraph(escape(short_code), meta_left_st),
          Paragraph(escape(date_str), meta_right_st)]],
        colWidths=[60 * mm, 60 * mm],
    )
    meta.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.black),  # เส้นใต้ รหัสย่อ/วันที่ ตาม template
    ]))
    story.append(meta)
    story.append(Spacer(1, 2))

    # ตารางรายการ + แถวรวม
    table_data = _bill_table_data(lines, total)
    n = len(table_data) - 1  # index ของแถวรวม (แถวสุดท้าย)
    grey = colors.HexColor(0xCCCCCC)                      # เทาตาม template (#cccccc)
    table = Table(table_data, colWidths=[22 * mm, 48 * mm, 25 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), fonts["head"]),     # header = Chakra Petch
        ("FONTNAME", (0, 1), (-1, n - 1), fonts["body"]), # body = Sarabun
        ("FONTNAME", (0, n), (-1, n), fonts["bold"]),     # total row = Sarabun bold
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("FONTSIZE", (0, 0), (-1, 0), 14),                # header ใหญ่กว่า body
        ("FONTSIZE", (1, n), (1, n), 14),                 # "รวมเป็นเงิน" ใหญ่กว่า body
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),             # header centered
        ("ALIGN", (0, 1), (0, n), "CENTER"),              # จำนวน
        ("ALIGN", (1, 1), (1, n - 1), "LEFT"),            # รายการ (เฉพาะแถวสินค้า)
        ("ALIGN", (2, 1), (3, -1), "RIGHT"),              # หน่วยละ / จำนวนเงิน
        ("ALIGN", (1, n), (1, n), "RIGHT"),               # "รวมเป็นเงิน" ชิดขวาในคอลัมน์รายการ
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), grey),            # หัวตารางเทา
        ("BACKGROUND", (0, n), (-1, n), grey),            # แถวรวมเทาทั้งแถว
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)

    # ลายเซ็นไม่ flow ต่อท้ายตาราง แต่วาดที่ Y คงที่ผ่าน page callback
    # → ตำแหน่ง ผู้รับของ/ผู้ส่งของ อยู่ที่เดิมทุกใบ ไม่ขึ้นกับจำนวนแถว
    doc.build(
        story,
        onFirstPage=lambda canvas, d: _draw_signature(canvas, d, fonts["body"]),
    )
    return buf.getvalue()


def render_bill_html(
    bill: dict,
    customer: dict,
    lines: list[dict],
    total: float,
) -> str:
    """HTML สำหรับ auto-pop print dialog (A5) บนเครื่องเจ้าของ — ความสะดวกหน้าจอ;
    PDF คือ artifact ตัวจริง. อ่านค่าจาก assemble_lines + fmt_int_cell ชุดเดียวกับ PDF
    → ค่าตรงกันเสมอ. มี window.print() ตอน onload."""
    short_code = escape(str(customer.get("name", "") or ""))
    date_str = escape(str(bill.get("date", "") or ""))

    body_rows = []
    for ln in assemble_lines(lines):
        body_rows.append(
            "<tr>"
            f"<td class='num'>{escape(fmt_int_cell(ln['qty']))}</td>"
            f"<td class='item'>{escape(ln['label'])}</td>"
            f"<td class='num'>{escape(fmt_int_cell(ln['unit_price']))}</td>"
            f"<td class='num'>{escape(fmt_int_cell(ln['amount']))}</td>"
            "</tr>"
        )
    total_cell = escape(fmt_int_cell(total, blank_zero=False))
    body_rows.append(
        "<tr class='total'>"
        "<td class='num'></td>"
        "<td class='item label'>รวมเป็นเงิน</td>"
        "<td class='num'></td>"
        f"<td class='num'>{total_cell}</td>"
        "</tr>"
    )
    rows_html = "".join(body_rows)

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<title>{escape('บิล ' + str(bill.get('bill_id', '') or ''))}</title>
<style>
  /* ฟอนต์ตาม template Google Sheet — โหลดจาก Google Fonts (ต้องมีเน็ตตอนพิมพ์);
     ขาดเน็ต → fallback Sarabun/cursive/sans-serif */
  @import url('https://fonts.googleapis.com/css2?family=Charmonman:wght@700&family=Chakra+Petch:wght@500;600&family=Sarabun:wght@400;700&display=swap');
  @page {{ size: A5; margin: 12mm; }}
  body {{
    font-family: 'Sarabun', 'Noto Sans Thai', sans-serif;
    color: #000; margin: 0; padding: 8px;
    box-sizing: border-box;
  }}
  .shop {{ text-align: center; font-family: 'Charmonman', cursive; font-style: italic; font-size: 34px; font-weight: 700; }}
  .sub {{ text-align: center; font-family: 'Chakra Petch', sans-serif; font-size: 22px; font-weight: 600; margin-bottom: 8px; }}
  .meta {{ display: flex; justify-content: space-between; font-family: 'Chakra Petch', sans-serif; font-size: 16px; border-bottom: 1px solid #000; padding-bottom: 2px; margin-bottom: 8px; }}
  .meta .code {{ font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ border: 1px solid #000; padding: 6px 6px; }}
  th {{ font-family: 'Chakra Petch', sans-serif; background: #cccccc; text-align: center; }}
  td.num {{ text-align: right; }}
  td.item {{ text-align: left; }}
  th:first-child, td.num:first-child {{ text-align: center; }}
  tr.total td {{ background: #cccccc; font-weight: 700; }}
  tr.total td.label {{ text-align: right; }}
  .sig {{ display: flex; justify-content: space-between; margin-top: 28px; font-size: 14px; }}
  @media print {{
    .noprint {{ display: none; }}
    /* บิลเต็มความสูง A5 + ดันลายเซ็นไปล่างสุด → ตำแหน่งเดียวกันทุกใบ ไม่ขึ้นกับจำนวนแถว */
    body {{ min-height: calc(210mm - 24mm); display: flex; flex-direction: column; }}
    .sig {{ margin-top: auto; }}
  }}
</style>
</head>
<body onload="window.print()">
  <div class="shop">{escape(SHOP_NAME)}</div>
  <div class="sub">บิลส่งของ</div>
  <div class="meta"><span class="code">{short_code}</span><span>{date_str}</span></div>
  <table>
    <thead>
      <tr><th>จำนวน</th><th>รายการ</th><th>หน่วยละ</th><th>จำนวนเงิน</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
  <div class="sig"><span>ผู้รับของ_____________</span><span>ผู้ส่งของ_____________</span></div>
</body>
</html>"""


# ===========================================================================
# Billing documents (ใบวางบิล): ใบแจ้งหนี้ (invoice) + ใบเสร็จรับเงิน (receipt)
# ---------------------------------------------------------------------------
# Separate A5 layout from the delivery-bill renderer above (do NOT overload it):
# a "ส่งถึง" header block + one table row per delivery day + a kind-specific
# footer (bank block for the invoice, payment-method checkboxes for the receipt).
# Amounts are passed in already aggregated (see lib/billing.day_lines).
# ===========================================================================

DOC_TITLES = {"invoice": "ใบแจ้งหนี้", "receipt": "ใบเสร็จรับเงิน"}
NUMBER_LABELS = {"invoice": "เลขที่ใบแจ้งหนี้", "receipt": "เลขที่ใบเสร็จ"}


def fmt_baht(value, blank_zero: bool = False) -> str:
    """ค่า → จำนวนเงินมีคอมมาคั่นหลัก ไม่มีทศนิยม ไม่มี 'บาท' (เช่น 5451 → '5,451').

    blank_zero=True: 0 / ว่าง / ไม่ใช่ตัวเลข → "" (ใช้กับช่องในตาราง).
    """
    try:
        n = round(float(value))
    except (TypeError, ValueError):
        return "" if blank_zero else "0"
    if blank_zero and n == 0:
        return ""
    return f"{n:,}"


def _billing_table_data(lines: list[dict], total) -> list[list[str]]:
    """table_data (header + 1 แถว/วัน + แถวรวม) จาก day_lines.
    seam ที่ test ใช้ตรวจค่าใน PDF (ลำดับที่, วันที่, จำนวนเงิน)."""
    data: list[list[str]] = [["ลำดับที่", "รายละเอียด", "จำนวนเงิน"]]
    for i, ln in enumerate(lines, 1):
        data.append([str(i), str(ln.get("date_str", "")), fmt_baht(ln.get("amount", 0))])
    data.append(["", "รวมทั้งสิ้น", fmt_baht(total)])
    return data


def generate_billing_pdf(
    kind: str,
    shop: dict,
    customer: dict,
    doc: dict,
    lines: list[dict],
    total: float,
) -> bytes:
    """
    สร้าง PDF ใบวางบิล (A5) — ใช้ร่วมกันทั้งใบแจ้งหนี้/ใบเสร็จ ต่างกันที่หัวเรื่อง,
    ช่องเลขที่ และ footer.

    Args:
        kind: "invoice" หรือ "receipt"
        shop: dict ข้อมูลร้าน (name, address, tax_id, signatory, bank{...}) จาก billing_config
        customer: dict ข้อมูลลูกค้าสำหรับช่อง "ส่งถึง"
                  (company_name, billing_address, tax_id, branch) จาก billing_config
        doc: dict เมตาของเอกสาร — number, date; (receipt:) invoice_ref, payment_method
        lines: list ของ {date_str, amount} (จาก billing.day_lines)
        total: ยอดรวมทั้งสิ้น

    Returns:
        PDF เป็น bytes
    """
    fonts = _register_fonts()
    bank = shop.get("bank") or {}

    buf = BytesIO()
    doc_tpl = SimpleDocTemplate(
        buf,
        pagesize=A5,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{DOC_TITLES.get(kind, '')} {doc.get('number', '')}",
    )

    shop_name_st = ParagraphStyle(
        "b_shop", fontName=fonts["title"], fontSize=22, leading=30
    )
    small_st = ParagraphStyle("b_small", fontName=fonts["body"], fontSize=8.5, leading=12)
    title_st = ParagraphStyle(
        "b_title", fontName=fonts["bold"], fontSize=20, leading=24, alignment=2
    )
    label_st = ParagraphStyle("b_label", fontName=fonts["bold"], fontSize=11, leading=15)
    body_st = ParagraphStyle("b_body", fontName=fonts["body"], fontSize=10, leading=15)
    meta_label_st = ParagraphStyle("b_ml", fontName=fonts["body"], fontSize=9, leading=13)
    meta_val_st = ParagraphStyle(
        "b_mv", fontName=fonts["bold"], fontSize=9, leading=13, alignment=2
    )
    sig_st = ParagraphStyle(
        "b_sig", fontName=fonts["body"], fontSize=10, leading=15, alignment=1
    )

    # --- Header: shop block (left) + document title (right) ---
    shop_block = [
        Paragraph(escape(str(shop.get("name", "") or SHOP_NAME)), shop_name_st),
        Paragraph(escape(str(shop.get("address", "") or "")), small_st),
        Paragraph("เลขที่ผู้เสียภาษี : " + escape(str(shop.get("tax_id", "") or "")), small_st),
    ]
    header = Table(
        [[shop_block, Paragraph(DOC_TITLES.get(kind, ""), title_st)]],
        colWidths=[78 * mm, 46 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # --- "ส่งถึง" block: customer details (left) + document meta (right) ---
    sendto_left = [
        Paragraph("ชื่อบริษัท: " + escape(str(customer.get("company_name", "") or "")), body_st),
        Paragraph("ที่อยู่: " + escape(str(customer.get("billing_address", "") or "")), body_st),
        Paragraph("เลขประจำตัวผู้เสียภาษี : " + escape(str(customer.get("tax_id", "") or "")), body_st),
        Paragraph("สาขา : " + escape(str(customer.get("branch", "") or "")), body_st),
    ]
    meta_rows = [
        [Paragraph(NUMBER_LABELS.get(kind, "เลขที่"), meta_label_st),
         Paragraph(escape(str(doc.get("number", "") or "")), meta_val_st)],
        [Paragraph("วันที่", meta_label_st),
         Paragraph(escape(str(doc.get("date", "") or "")), meta_val_st)],
    ]
    if kind == "receipt":
        meta_rows.append([
            Paragraph("อ้างถึงใบแจ้งหนี้", meta_label_st),
            Paragraph(escape(str(doc.get("invoice_ref", "") or "")), meta_val_st),
        ])
    meta_tbl = Table(meta_rows, colWidths=[25 * mm, 25 * mm])
    meta_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    sendto = Table([[sendto_left, meta_tbl]], colWidths=[74 * mm, 50 * mm])
    sendto.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # --- Line-items table: one row per delivery day + grand-total row ---
    table_data = _billing_table_data(lines, total)
    n = len(table_data) - 1  # grand-total row index (last)
    grey = colors.HexColor(0xCCCCCC)
    items = Table(table_data, colWidths=[20 * mm, 74 * mm, 30 * mm])
    items.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), fonts["head"]),     # header
        ("FONTNAME", (0, 1), (-1, n - 1), fonts["body"]),  # body
        ("FONTNAME", (0, n), (-1, n), fonts["bold"]),      # total row
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("FONTSIZE", (0, 0), (-1, 0), 12),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),              # header centered
        ("ALIGN", (0, 1), (0, n), "CENTER"),               # ลำดับที่
        ("ALIGN", (1, 1), (1, n - 1), "LEFT"),             # รายละเอียด (day rows)
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),               # จำนวนเงิน
        ("ALIGN", (1, n), (1, n), "RIGHT"),                # "รวมทั้งสิ้น" label
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), grey),
        ("BACKGROUND", (0, n), (-1, n), grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    # --- Footer: bank block (invoice) / payment checkboxes (receipt) + signature ---
    if kind == "invoice":
        footer_left = [
            Paragraph("หมายเหตุ: กรุณาชำระเงินโดยโอนเข้าบัญชี", body_st),
            Paragraph("ชื่อบัญชี " + escape(str(bank.get("account_name", "") or "")), body_st),
            Paragraph(escape(str(bank.get("bank_name", "") or "")), body_st),
            Paragraph("เลขที่บัญชี " + escape(str(bank.get("account_no", "") or "")), body_st),
        ]
        sig_caption = escape(str(shop.get("name", "") or SHOP_NAME))
    else:
        method = str(doc.get("payment_method", "") or "")
        def _chk(m: str) -> str:
            return f"[{'X' if method == m else ' '}] {m}"
        footer_left = [
            Paragraph("รับชำระเงิน", body_st),
            Paragraph(_chk("เงินสด"), body_st),
            Paragraph(_chk("โอนเข้าบัญชีธนาคาร"), body_st),
        ]
        sig_caption = "ผู้รับเงิน"

    footer_right = [
        Paragraph(sig_caption, sig_st),
        Spacer(1, 20),
        Paragraph("____________________", sig_st),
        Paragraph(escape(str(shop.get("signatory", "") or "")), sig_st),
    ]
    footer = Table([[footer_left, footer_right]], colWidths=[74 * mm, 50 * mm])
    footer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    story = [
        header,
        HRFlowable(width="100%", thickness=0.8, color=colors.black,
                   spaceBefore=6, spaceAfter=6),
        Paragraph("ส่งถึง:", label_st),
        Spacer(1, 2),
        sendto,
        Spacer(1, 10),
        items,
        Spacer(1, 14),
        footer,
    ]
    doc_tpl.build(story)
    return buf.getvalue()


def generate_invoice_pdf(shop, customer, doc, lines, total) -> bytes:
    return generate_billing_pdf("invoice", shop, customer, doc, lines, total)


def generate_receipt_pdf(shop, customer, doc, lines, total) -> bytes:
    return generate_billing_pdf("receipt", shop, customer, doc, lines, total)


def render_billing_html(
    kind: str,
    shop: dict,
    customer: dict,
    doc: dict,
    lines: list[dict],
    total: float,
) -> str:
    """HTML A5 สำหรับ auto-pop print dialog (ความสะดวกหน้าจอ; PDF คือ artifact ตัวจริง).
    อ่านค่าจาก _billing_table_data ชุดเดียวกับ PDF → ค่าตรงกันเสมอ."""
    bank = shop.get("bank") or {}
    title = DOC_TITLES.get(kind, "")
    num_label = NUMBER_LABELS.get(kind, "เลขที่")

    body_rows = []
    for i, ln in enumerate(lines, 1):
        body_rows.append(
            "<tr>"
            f"<td class='c'>{i}</td>"
            f"<td class='l'>{escape(str(ln.get('date_str', '')))}</td>"
            f"<td class='r'>{escape(fmt_baht(ln.get('amount', 0)))}</td>"
            "</tr>"
        )
    body_rows.append(
        "<tr class='total'>"
        "<td class='c'></td>"
        "<td class='r'>รวมทั้งสิ้น</td>"
        f"<td class='r'>{escape(fmt_baht(total))}</td>"
        "</tr>"
    )
    rows_html = "".join(body_rows)

    meta_rows = (
        f"<tr><td>{num_label}</td><td class='r'>{escape(str(doc.get('number', '') or ''))}</td></tr>"
        f"<tr><td>วันที่</td><td class='r'>{escape(str(doc.get('date', '') or ''))}</td></tr>"
    )
    if kind == "receipt":
        meta_rows += (
            f"<tr><td>อ้างถึงใบแจ้งหนี้</td>"
            f"<td class='r'>{escape(str(doc.get('invoice_ref', '') or ''))}</td></tr>"
        )

    if kind == "invoice":
        footer_left = (
            "<div>หมายเหตุ: กรุณาชำระเงินโดยโอนเข้าบัญชี</div>"
            f"<div>ชื่อบัญชี {escape(str(bank.get('account_name', '') or ''))}</div>"
            f"<div>{escape(str(bank.get('bank_name', '') or ''))}</div>"
            f"<div>เลขที่บัญชี {escape(str(bank.get('account_no', '') or ''))}</div>"
        )
        sig_caption = escape(str(shop.get("name", "") or SHOP_NAME))
    else:
        method = str(doc.get("payment_method", "") or "")
        def _chk(m: str) -> str:
            mark = "X" if method == m else "&nbsp;"
            return f"<div>[{mark}] {escape(m)}</div>"
        footer_left = "<div>รับชำระเงิน</div>" + _chk("เงินสด") + _chk("โอนเข้าบัญชีธนาคาร")
        sig_caption = "ผู้รับเงิน"

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<title>{escape(title + ' ' + str(doc.get('number', '') or ''))}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Charmonman:wght@700&family=Sarabun:wght@400;700&display=swap');
  @page {{ size: A5; margin: 12mm; }}
  body {{ font-family: 'Sarabun', 'Noto Sans Thai', sans-serif; color: #000; margin: 0; padding: 8px; font-size: 13px; }}
  .head {{ display: flex; justify-content: space-between; align-items: flex-start; }}
  .shop {{ font-family: 'Charmonman', cursive; font-size: 30px; font-weight: 700; }}
  .addr {{ font-size: 11px; }}
  .title {{ font-size: 24px; font-weight: 700; text-align: right; }}
  hr {{ border: none; border-top: 1px solid #000; margin: 6px 0; }}
  .sendto {{ display: flex; justify-content: space-between; }}
  .meta td {{ padding: 1px 4px; }}
  .meta td.r {{ font-weight: 700; }}
  table.items {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  table.items th, table.items td {{ border: 1px solid #000; padding: 5px 6px; }}
  table.items th {{ background: #cccccc; }}
  td.c {{ text-align: center; }} td.r {{ text-align: right; }} td.l {{ text-align: left; }}
  tr.total td {{ background: #cccccc; font-weight: 700; }}
  .footer {{ display: flex; justify-content: space-between; margin-top: 16px; }}
  .sig {{ text-align: center; }}
  .sig .line {{ margin-top: 28px; }}
  @media print {{
    body {{ min-height: calc(210mm - 24mm); display: flex; flex-direction: column; }}
    .footer {{ margin-top: auto; }}
  }}
</style>
</head>
<body onload="window.print()">
  <div class="head">
    <div>
      <div class="shop">{escape(str(shop.get('name', '') or SHOP_NAME))}</div>
      <div class="addr">{escape(str(shop.get('address', '') or ''))}</div>
      <div class="addr">เลขที่ผู้เสียภาษี : {escape(str(shop.get('tax_id', '') or ''))}</div>
    </div>
    <div class="title">{title}</div>
  </div>
  <hr>
  <div><b>ส่งถึง:</b></div>
  <div class="sendto">
    <div>
      <div>ชื่อบริษัท: {escape(str(customer.get('company_name', '') or ''))}</div>
      <div>ที่อยู่: {escape(str(customer.get('billing_address', '') or ''))}</div>
      <div>เลขประจำตัวผู้เสียภาษี : {escape(str(customer.get('tax_id', '') or ''))}</div>
      <div>สาขา : {escape(str(customer.get('branch', '') or ''))}</div>
    </div>
    <table class="meta">{meta_rows}</table>
  </div>
  <table class="items">
    <thead><tr><th>ลำดับที่</th><th>รายละเอียด</th><th>จำนวนเงิน</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <div class="footer">
    <div>{footer_left}</div>
    <div class="sig">{sig_caption}<div class="line">____________________</div>{escape(str(shop.get('signatory', '') or ''))}</div>
  </div>
</body>
</html>"""
