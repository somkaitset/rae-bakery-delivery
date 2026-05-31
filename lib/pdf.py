"""
PDF บิลส่งของ — ใช้ ReportLab + ฟอนต์ Sarabun (Thai)

วาง Sarabun-Regular.ttf และ Sarabun-Bold.ttf ไว้ที่ secrets/ (ดาวน์โหลดจาก Google Fonts)
ถ้าไม่มีฟอนต์ จะ fallback เป็น Helvetica (ภาษาไทยจะเป็นกล่อง)
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


FONT_REG = "Sarabun"
FONT_BOLD = "Sarabun-Bold"
SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets"

_font_registered = False


def _register_fonts() -> tuple[str, str]:
    """Register Thai fonts. คืน (font name regular, font name bold)."""
    global _font_registered
    if _font_registered:
        return FONT_REG, FONT_BOLD

    reg_path = SECRETS_DIR / "Sarabun-Regular.ttf"
    bold_path = SECRETS_DIR / "Sarabun-Bold.ttf"

    if reg_path.exists():
        pdfmetrics.registerFont(TTFont(FONT_REG, str(reg_path)))
    else:
        return "Helvetica", "Helvetica-Bold"

    if bold_path.exists():
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold_path)))
        _font_registered = True
        return FONT_REG, FONT_BOLD
    else:
        _font_registered = True
        return FONT_REG, FONT_REG


def generate_bill_pdf(
    bill: dict,
    customer: dict,
    lines: list[dict],
    total: float,
) -> bytes:
    """
    สร้าง PDF บิลส่งของ

    Args:
        bill: dict ของแถวใน "ใบส่งสินค้า" — มี รหัสใบส่ง, วันที่
        customer: dict ของแถวใน "ลูกค้า" — มี ชื่อลูกค้า, ที่อยู่
        lines: list ของ dict จาก "BillLines" — มี กลุ่มราคา, จำนวน, หน่วยละ, จำนวนเงิน
        total: ยอดรวม

    Returns:
        PDF เป็น bytes (พร้อม download/upload)
    """
    font_reg, font_bold = _register_fonts()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A5,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"บิล {bill.get('รหัสใบส่ง', '')}",
    )

    title_st = ParagraphStyle(
        "title", fontName=font_bold, fontSize=20, alignment=1, spaceAfter=4
    )
    sub_st = ParagraphStyle(
        "sub", fontName=font_reg, fontSize=14, alignment=1, spaceAfter=12
    )
    label_st = ParagraphStyle(
        "label", fontName=font_reg, fontSize=11, spaceAfter=6
    )
    total_st = ParagraphStyle(
        "total", fontName=font_bold, fontSize=14, alignment=2, spaceBefore=12
    )
    sig_st = ParagraphStyle(
        "sig", fontName=font_reg, fontSize=10, spaceBefore=24
    )

    story = [
        Paragraph("เรเบเกอรี่", title_st),
        Paragraph("บิลส่งของ", sub_st),
        Paragraph(
            f"ลูกค้า: <b>{customer.get('ชื่อลูกค้า', '')}</b>"
            f"&nbsp;&nbsp;&nbsp;&nbsp;"
            f"วันที่: <b>{bill.get('วันที่', '')}</b>",
            label_st,
        ),
        Spacer(1, 4),
    ]

    # Table of lines (sort by price group ascending)
    def _pg_key(line: dict) -> int:
        try:
            return int(line.get("กลุ่มราคา", 0))
        except (TypeError, ValueError):
            return 0

    table_data: list[list] = [["จำนวน", "รายการ (กลุ่มราคา)", "หน่วยละ", "จำนวนเงิน"]]
    for line in sorted(lines, key=_pg_key):
        table_data.append([
            str(line.get("จำนวน", "")),
            f"{line.get('กลุ่มราคา', '')} บาท",
            f"{float(line.get('หน่วยละ', 0)):.2f}",
            f"{float(line.get('จำนวนเงิน', 0)):,.2f}",
        ])

    table = Table(table_data, colWidths=[20 * mm, 50 * mm, 25 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, 1), (-1, -1), font_reg),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(table)
    story.append(Paragraph(f"รวมเป็นเงิน: {total:,.2f} บาท", total_st))
    story.append(Paragraph(
        "ผู้ส่งของ __________________"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "ผู้รับของ __________________",
        sig_st,
    ))

    doc.build(story)
    return buf.getvalue()
