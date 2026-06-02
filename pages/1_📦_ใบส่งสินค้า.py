"""
หน้าใบส่งสินค้า — list + create (grid form) + print PDF + delete
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from lib import bills, sheets
from lib.auth import require_auth
from lib.pdf import generate_bill_pdf

require_auth()

st.title("📦 ใบส่งสินค้า")

tab_list, tab_new = st.tabs(["📋 รายการใบส่ง", "➕ สร้างใบใหม่"])


# =====================================================
# Tab: รายการใบส่ง
# =====================================================
with tab_list:
    try:
        bills_data = sheets.bills()
        items_data = sheets.bill_items()
        customers_map = {c.get("code"): c.get("name") for c in sheets.customers()}
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()

    if not bills_data:
        st.info("ยังไม่มีใบส่ง — ไปที่แท็บ \"สร้างใบใหม่\"")
    else:
        # สร้างตาราง pretty
        rows = []
        for b in bills_data:
            bid = str(b.get("bill_id", ""))
            rows.append({
                "รหัส": bid,
                "วันที่": b.get("date", ""),
                "ลูกค้า": customers_map.get(str(b.get("customer_code", "")), b.get("customer_code", "")),
                "จำนวนชิ้น": bills.bill_qty_total(bid, items_data),
                "รวมเป็นเงิน": bills.bill_total(bid, items_data),
                "สถานะ": b.get("status", ""),
            })
        df = pd.DataFrame(rows)
        # sort: วันที่ desc
        df["_sort"] = df["วันที่"].apply(lambda s: bills.parse_date(s) or date(1900, 1, 1))
        df = df.sort_values("_sort", ascending=False).drop(columns=["_sort"]).reset_index(drop=True)

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "รวมเป็นเงิน": st.column_config.NumberColumn(format="%.2f"),
                "จำนวนชิ้น": st.column_config.NumberColumn(format="%d"),
            },
        )

        st.divider()
        st.subheader("จัดการใบ")
        bill_ids = [str(b.get("bill_id", "")) for b in bills_data]
        col1, col2 = st.columns([2, 1])
        with col1:
            selected = st.selectbox("เลือกใบส่ง", options=bill_ids, key="manage_bill_select")
        with col2:
            st.write("")
            st.write("")
            print_clicked = st.button("📄 พิมพ์บิล (PDF)", type="primary", use_container_width=True)

        if print_clicked and selected:
            bill = next((b for b in bills_data if str(b.get("bill_id")) == selected), {})
            cust = next(
                (c for c in sheets.customers() if str(c.get("code")) == str(bill.get("customer_code"))),
                {},
            )
            lines = bills.lines_for_bill(selected)
            if not lines:
                st.warning("ใบนี้ยังไม่มีรายการ หรือ BillLines ยังไม่อัปเดต (รอ ~5 วินาที แล้วลองใหม่)")
            else:
                total = bills.bill_total(selected, items_data)
                try:
                    pdf_bytes = generate_bill_pdf(bill, cust, lines, total)
                    st.download_button(
                        label=f"⬇️ ดาวน์โหลด บิล-{cust.get('name', '')}-{bill.get('date', '').replace('/', '')}.pdf",
                        data=pdf_bytes,
                        file_name=f"bill-{selected}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"สร้าง PDF ไม่ได้: {e}")

        with st.expander("⚠️ ลบใบส่ง (ลบ items ทั้งหมดด้วย)"):
            confirm = st.checkbox(f"ยืนยันลบ `{selected}`", key=f"confirm_del_{selected}")
            if st.button("🗑️ ลบ", type="secondary", disabled=not confirm):
                with st.spinner("กำลังลบ..."):
                    n = bills.delete_bill(selected)
                st.success(f"ลบใบ {selected} เรียบร้อย (ลบ {n} แถว)")
                st.rerun()


# =====================================================
# Tab: สร้างใบใหม่ (กริดสินค้าทั้งหมด)
# =====================================================
with tab_new:
    try:
        active_customers = sheets.active_customers()
        active_products = sheets.active_products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()

    if not active_customers or not active_products:
        st.warning("ไม่มีลูกค้า/สินค้าที่ใช้งาน")
        st.stop()

    cust_options = {f"{c['name']} ({c['code']})": c for c in active_customers}

    col1, col2 = st.columns(2)
    with col1:
        cust_label = st.selectbox("ลูกค้า", options=list(cust_options.keys()), key="new_cust")
        selected_cust = cust_options[cust_label]
    with col2:
        bill_date = st.date_input("วันที่", value=date.today(), format="DD/MM/YYYY", key="new_date")

    price_set = selected_cust.get("price_set", "มาตรฐาน")
    st.caption(f"ชุดราคา: **{price_set}**")

    # โหลด price map ครั้งเดียว
    prices = bills.price_map()

    # สร้าง DataFrame ของสินค้าทั้งหมด + คำนวณ หน่วยละ + เริ่มต้น qty 0
    products_sorted = sorted(
        active_products,
        key=lambda p: int(bills._to_float(p.get("display_order", 0))),
    )

    grid_rows = []
    for p in products_sorted:
        pg = str(p.get("price_group", ""))
        unit = bills.unit_price(price_set, pg, prices)
        grid_rows.append({
            "รหัส": str(p.get("code", "")),
            "ชื่อสินค้า": str(p.get("name", "")),
            "กลุ่ม": pg,
            "หน่วยละ": unit,
            "จำนวน": 0,
        })
    grid_df = pd.DataFrame(grid_rows)

    st.markdown("### กรอกจำนวนเฉพาะที่ส่ง (เว้น 0 = ไม่ส่ง)")
    edited = st.data_editor(
        grid_df,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "รหัส": st.column_config.TextColumn(disabled=True),
            "ชื่อสินค้า": st.column_config.TextColumn(disabled=True),
            "กลุ่ม": st.column_config.TextColumn(disabled=True, width="small"),
            "หน่วยละ": st.column_config.NumberColumn(disabled=True, format="%.2f", width="small"),
            "จำนวน": st.column_config.NumberColumn(min_value=0, max_value=999, step=1, format="%d"),
        },
        key="new_grid",
    )

    # คำนวณ summary
    edited["จำนวนเงิน"] = edited["จำนวน"] * edited["หน่วยละ"]
    qty_sum = int(edited["จำนวน"].sum())
    amt_sum = float(edited["จำนวนเงิน"].sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("จำนวนชนิด (ที่ส่ง)", int((edited["จำนวน"] > 0).sum()))
    col2.metric("จำนวนชิ้น", qty_sum)
    col3.metric("รวมเป็นเงิน", f"{amt_sum:,.2f}")

    note = st.text_input("หมายเหตุ (ทางเลือก)", key="new_note")

    col_save, col_save_send = st.columns(2)
    save_draft = col_save.button("💾 บันทึก (สถานะ: ร่าง)", use_container_width=True)
    save_send = col_save_send.button(
        "✅ บันทึก + ส่งแล้ว",
        type="primary",
        use_container_width=True,
    )

    if save_draft or save_send:
        items_qty = {
            row["รหัส"]: int(row["จำนวน"])
            for _, row in edited.iterrows()
            if int(row["จำนวน"]) > 0
        }
        if not items_qty:
            st.warning("ยังไม่ได้ใส่จำนวนสินค้าใดเลย")
        else:
            try:
                with st.spinner("กำลังบันทึก..."):
                    new_id = bills.create_bill(
                        customer_code=selected_cust["code"],
                        bill_date=bill_date,
                        items_qty=items_qty,
                        note=note,
                        status="ส่งแล้ว" if save_send else "ร่าง",
                    )
                st.success(f"🎉 สร้างใบ `{new_id}` เรียบร้อย ({len(items_qty)} ชนิด, รวม {amt_sum:,.2f} บาท)")
                st.balloons()
                st.info("ไปแท็บ \"รายการใบส่ง\" → เลือก ใบที่เพิ่งสร้าง → กด \"พิมพ์บิล (PDF)\"")
            except Exception as e:
                st.error(f"บันทึกไม่ได้: {e}")
