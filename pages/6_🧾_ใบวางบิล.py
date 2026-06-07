"""
ใบวางบิล — ออกใบแจ้งหนี้ (ใบแจ้งหนี้) + ใบเสร็จรับเงิน ให้ลูกค้ารายเดียว
โดยรวมยอด "บิลส่งสินค้า" ที่ส่งแล้ว ในช่วงวันที่ที่เลือก เป็นยอดรายวัน.

ข้อมูลหัวบิล (ร้าน + ลูกค้า) มาจาก billing_config.yaml (gitignore).
ยอดคำนวณใหม่ทุกครั้งจากตาราง bill — ตัวเอกสารเก็บแค่ระเบียน (เลขที่/ลูกค้า/ช่วงเวลา).
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from lib import billing, billing_config, bills, pdf, sheets
from lib.auth import require_auth

require_auth()

st.title("🧾 ใบวางบิล")

if not billing_config.config_exists():
    st.error(
        "ยังไม่มีไฟล์ `billing_config.yaml` — ก๊อปปี้ `billing_config.example.yaml` "
        "→ `billing_config.yaml` แล้วกรอกข้อมูลร้าน/ลูกค้าก่อน"
    )
    st.stop()

_cust_codes = billing_config.billing_customer_codes()
if not _cust_codes:
    st.warning("ยังไม่ได้ตั้งค่าลูกค้าใน `billing_config.yaml` (หัวข้อ `customers:`)")
    st.stop()

# code -> ชื่อลูกค้า (จากตาราง customer) สำหรับ label
_cust_names = {c.get("code"): c.get("name", "") for c in sheets.customers()}


def _fmt_customer(code: str) -> str:
    name = _cust_names.get(code, "")
    return f"{code} — {name}" if name else code


def _lines_total(customer_code: str, start: date, end: date,
                 bills_rows=None, items_rows=None):
    """รายการรายวัน + ยอดรวม (คำนวณสดจาก bill/bill_item)."""
    lines = billing.day_lines(customer_code, start, end, bills_rows, items_rows)
    return lines, billing.grand_total(lines)


def _lines_df(lines: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"ลำดับที่": i, "วันที่": ln["date_str"], "จำนวนเงิน": ln["amount"]}
         for i, ln in enumerate(lines, 1)]
    )


def _render_invoice_output(inv: dict, key: str) -> None:
    """ปุ่มดาวน์โหลด/พิมพ์ใบแจ้งหนี้ (regenerate สดจากระเบียน)."""
    shop = billing_config.shop()
    cust_b = billing_config.customer_billing(inv.get("customer_code", ""))
    start = bills.parse_date(inv.get("period_start"))
    end = bills.parse_date(inv.get("period_end"))
    lines, total = _lines_total(inv.get("customer_code", ""), start, end)
    meta = {"number": inv.get("invoice_no", ""), "date": inv.get("issue_date", "")}
    pdf_bytes = pdf.generate_invoice_pdf(shop, cust_b, meta, lines, total)
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ ดาวน์โหลด PDF", data=pdf_bytes,
                       file_name=f"{inv.get('invoice_no', 'invoice')}.pdf",
                       mime="application/pdf", key=f"dl_{key}")
    if c2.button("🖨️ พิมพ์", key=f"pr_{key}"):
        components.html(
            pdf.render_billing_html("invoice", shop, cust_b, meta, lines, total),
            height=0,
        )


def _render_receipt_output(rcp: dict, key: str) -> None:
    """ปุ่มดาวน์โหลด/พิมพ์ใบเสร็จ (regenerate สดจากระเบียน)."""
    shop = billing_config.shop()
    cust_b = billing_config.customer_billing(rcp.get("customer_code", ""))
    start = bills.parse_date(rcp.get("period_start"))
    end = bills.parse_date(rcp.get("period_end"))
    lines, total = _lines_total(rcp.get("customer_code", ""), start, end)
    meta = {
        "number": rcp.get("receipt_no", ""),
        "date": rcp.get("issue_date", ""),
        "invoice_ref": rcp.get("invoice_no", ""),
        "payment_method": rcp.get("payment_method", ""),
    }
    pdf_bytes = pdf.generate_receipt_pdf(shop, cust_b, meta, lines, total)
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ ดาวน์โหลด PDF", data=pdf_bytes,
                       file_name=f"{rcp.get('receipt_no', 'receipt')}.pdf",
                       mime="application/pdf", key=f"dl_{key}")
    if c2.button("🖨️ พิมพ์", key=f"pr_{key}"):
        components.html(
            pdf.render_billing_html("receipt", shop, cust_b, meta, lines, total),
            height=0,
        )


tab_new, tab_inv, tab_rcp = st.tabs(
    ["➕ ออกใบแจ้งหนี้", "📋 ใบแจ้งหนี้", "🧾 ใบเสร็จ"]
)


# --- ออกใบแจ้งหนี้ ---------------------------------------------------------
with tab_new:
    # หลังออกใบ: โชว์ผลลัพธ์ใบล่าสุด + ปุ่มเริ่มใหม่
    new_no = st.session_state.get("new_invoice_no")
    if new_no:
        inv = billing.get_invoice(new_no)
        if inv:
            st.success(f"ออกใบแจ้งหนี้ **{new_no}** แล้ว")
            _render_invoice_output(inv, key="new")
        if st.button("➕ ออกใบใหม่"):
            st.session_state.pop("new_invoice_no", None)
            st.rerun()
    else:
        code = st.selectbox("ลูกค้า", _cust_codes, format_func=_fmt_customer,
                            key="new_cust")
        today = date.today()
        c1, c2, c3 = st.columns(3)
        start = c1.date_input("ตั้งแต่วันที่", value=today - timedelta(days=30),
                              format="DD/MM/YYYY", key="new_start")
        end = c2.date_input("ถึงวันที่", value=today, format="DD/MM/YYYY",
                            key="new_end")
        issue = c3.date_input("วันที่ออกบิล", value=today, format="DD/MM/YYYY",
                              key="new_issue")

        if start > end:
            st.error("ช่วงวันที่ไม่ถูกต้อง (ตั้งแต่ > ถึง)")
        else:
            lines, total = _lines_total(code, start, end)
            if not lines:
                st.warning("ไม่มีบิลที่ส่งแล้วของลูกค้านี้ในช่วงวันที่ที่เลือก")
            else:
                st.dataframe(_lines_df(lines), hide_index=True,
                             use_container_width=True,
                             column_config={"จำนวนเงิน": st.column_config.NumberColumn(format="%.0f")})
                st.metric("รวมทั้งสิ้น", f"{round(total):,}")
                if billing_config.customer_billing(code):
                    if st.button("📄 ออกใบแจ้งหนี้", type="primary"):
                        no = billing.create_invoice(code, issue, start, end)
                        st.session_state["new_invoice_no"] = no
                        st.rerun()
                else:
                    st.warning(
                        f"ลูกค้า {code} ยังไม่มีข้อมูลใน `billing_config.yaml` "
                        "(หัวข้อ `customers:`) — เพิ่มก่อนจึงจะออกบิลได้"
                    )


# --- ประวัติใบแจ้งหนี้ -----------------------------------------------------
with tab_inv:
    invoices = sheets.invoices()
    if not invoices:
        st.info("ยังไม่มีใบแจ้งหนี้")
    else:
        bills_rows = sheets.bills()
        items_rows = sheets.bill_items()
        receipts = sheets.receipts()
        rcp_by_inv = {r.get("invoice_no"): r for r in receipts}

        rows = []
        for inv in invoices:
            _, total = _lines_total(inv.get("customer_code", ""),
                                    bills.parse_date(inv.get("period_start")),
                                    bills.parse_date(inv.get("period_end")),
                                    bills_rows, items_rows)
            rows.append({
                "เลขที่": inv.get("invoice_no", ""),
                "วันที่": inv.get("issue_date", ""),
                "ลูกค้า": _fmt_customer(inv.get("customer_code", "")),
                "ช่วงเวลา": f"{inv.get('period_start','')} - {inv.get('period_end','')}",
                "ยอดรวม": round(total),
                "สถานะ": inv.get("status", ""),
                "ใบเสร็จ": rcp_by_inv.get(inv.get("invoice_no"), {}).get("receipt_no", "-"),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        nos = [inv.get("invoice_no", "") for inv in invoices]
        sel = st.selectbox("เลือกใบแจ้งหนี้", nos, key="inv_sel")
        inv = billing.get_invoice(sel, invoices)
        if inv:
            _render_invoice_output(inv, key="hist")
            existing_rcp = rcp_by_inv.get(sel)

            st.divider()
            if existing_rcp:
                st.info(f"ออกใบเสร็จแล้ว: **{existing_rcp.get('receipt_no','')}** "
                        f"(ดู/พิมพ์ได้ที่แท็บ 🧾 ใบเสร็จ)")
            else:
                st.subheader("ออกใบเสร็จจากใบแจ้งหนี้นี้")
                rc1, rc2 = st.columns(2)
                method = rc1.radio("วิธีชำระเงิน", billing.PAYMENT_METHODS,
                                   key="rcp_method")
                r_issue = rc2.date_input("วันที่ออกใบเสร็จ", value=date.today(),
                                         format="DD/MM/YYYY", key="rcp_issue")
                if st.button("🧾 ออกใบเสร็จ", type="primary"):
                    rno = billing.create_receipt(sel, r_issue, method)
                    st.success(f"ออกใบเสร็จ **{rno}** แล้ว — ดู/พิมพ์ได้ที่แท็บ 🧾 ใบเสร็จ")
                    st.rerun()

                with st.expander("🗑️ ลบใบแจ้งหนี้นี้"):
                    if st.button("ลบ", key="del_inv"):
                        billing.delete_invoice(sel)
                        st.success(f"ลบ {sel} แล้ว")
                        st.rerun()


# --- ประวัติใบเสร็จ --------------------------------------------------------
with tab_rcp:
    receipts = sheets.receipts()
    if not receipts:
        st.info("ยังไม่มีใบเสร็จ")
    else:
        bills_rows = sheets.bills()
        items_rows = sheets.bill_items()
        rows = []
        for rcp in receipts:
            _, total = _lines_total(rcp.get("customer_code", ""),
                                    bills.parse_date(rcp.get("period_start")),
                                    bills.parse_date(rcp.get("period_end")),
                                    bills_rows, items_rows)
            rows.append({
                "เลขที่": rcp.get("receipt_no", ""),
                "วันที่": rcp.get("issue_date", ""),
                "ลูกค้า": _fmt_customer(rcp.get("customer_code", "")),
                "อ้างถึงใบแจ้งหนี้": rcp.get("invoice_no", ""),
                "วิธีชำระ": rcp.get("payment_method", ""),
                "ยอดรวม": round(total),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        nos = [rcp.get("receipt_no", "") for rcp in receipts]
        sel = st.selectbox("เลือกใบเสร็จ", nos, key="rcp_sel")
        rcp = billing.get_receipt(sel, receipts)
        if rcp:
            _render_receipt_output(rcp, key="rhist")
            with st.expander("🗑️ ลบใบเสร็จนี้ (ใบแจ้งหนี้จะกลับเป็น ค้างชำระ)"):
                if st.button("ลบ", key="del_rcp"):
                    billing.delete_receipt(sel)
                    st.success(f"ลบ {sel} แล้ว")
                    st.rerun()
