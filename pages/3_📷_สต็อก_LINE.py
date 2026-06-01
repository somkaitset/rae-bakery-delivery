"""
หน้าบันทึกสต็อกคงเหลือจากรูปลูกค้าส่งทาง LINE
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

from lib import bills, sheets, storage
from lib.auth import require_auth

require_auth()

st.title("📷 สต็อกคงเหลือ (จากรูป LINE)")

tab_list, tab_new = st.tabs(["📋 สต็อกล่าสุด", "➕ บันทึกใหม่"])


# --- List (gallery) ---
with tab_list:
    try:
        ss = sheets.stocks()
        customers_map = {c.get("รหัสลูกค้า"): c.get("ชื่อลูกค้า") for c in sheets.customers()}
        products_map = {p.get("รหัสสินค้า"): p.get("ชื่อสินค้า") for p in sheets.products()}
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()

    if not ss:
        st.info("ยังไม่มีบันทึกสต็อก — ไปที่แท็บ \"บันทึกใหม่\"")
    else:
        # sort: วันที่ desc
        ss_sorted = sorted(
            ss,
            key=lambda r: (bills.parse_date(r.get("วันที่")) or date(1900, 1, 1)),
            reverse=True,
        )

        cols_per_row = 3
        for i in range(0, len(ss_sorted), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, row in enumerate(ss_sorted[i:i + cols_per_row]):
                with cols[j]:
                    img = storage.image_src(row.get("รูปจาก LINE"))
                    if img:
                        try:
                            st.image(img, use_container_width=True)
                        except Exception:
                            st.caption("(โหลดรูปไม่ได้)")
                    cust_name = customers_map.get(str(row.get("รหัสลูกค้า", "")), row.get("รหัสลูกค้า", ""))
                    prod_name = products_map.get(str(row.get("รหัสสินค้า", "")), row.get("รหัสสินค้า", ""))
                    st.markdown(
                        f"**{prod_name}** เหลือ **{row.get('จำนวนคงเหลือ', '')}** ชิ้น  \n"
                        f"📅 {row.get('วันที่', '')} • 🏪 {cust_name}"
                    )
                    if row.get("หมายเหตุ"):
                        st.caption(str(row.get("หมายเหตุ", "")))


# --- Add ---
with tab_new:
    st.subheader("บันทึกสต็อกใหม่")
    try:
        active_customers = sheets.active_customers()
        active_products = sheets.active_products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()

    if not active_customers or not active_products:
        st.warning("ไม่มีลูกค้า/สินค้าที่ใช้งาน")
        st.stop()

    next_id = bills.next_stock_id()
    st.caption(f"รหัสที่จะใช้: `{next_id}`")

    uploaded = st.file_uploader(
        "รูปจาก LINE (บนมือถือเลือก \"ถ่ายรูป\" หรือ \"เลือกจากเครื่อง\" ได้)",
        type=["jpg", "jpeg", "png", "webp"],
    )

    with st.form("new_stock_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            stock_date = st.date_input("วันที่", value=date.today(), format="DD/MM/YYYY")
        with c2:
            cust_options = {f"{c['ชื่อลูกค้า']} ({c['รหัสลูกค้า']})": c for c in active_customers}
            cust_label = st.selectbox("ลูกค้า *", options=list(cust_options.keys()))
            selected_cust = cust_options[cust_label]

        # filter สินค้าตามลำดับแสดง
        active_products_sorted = sorted(
            active_products,
            key=lambda p: int(bills._to_float(p.get("ลำดับแสดง", 0))),
        )
        prod_options = {
            f"{p['ชื่อสินค้า']} ({p['รหัสสินค้า']}) — กลุ่ม {p.get('กลุ่มราคา', '')}": p
            for p in active_products_sorted
        }
        prod_label = st.selectbox("สินค้า *", options=list(prod_options.keys()))
        selected_prod = prod_options[prod_label]

        c3, c4 = st.columns([1, 2])
        with c3:
            remaining = st.number_input("จำนวนคงเหลือ *", min_value=0, max_value=999, value=0)
        with c4:
            note = st.text_input("หมายเหตุ (ทางเลือก)")

        submitted = st.form_submit_button("💾 บันทึก", type="primary", use_container_width=True)
        if submitted:
            image_url = ""
            img_file = uploaded
            if img_file:
                try:
                    with st.spinner("กำลังบันทึกรูป..."):
                        image_url = storage.save_image(
                            name=f"stock_{selected_cust['รหัสลูกค้า']}_{selected_prod['รหัสสินค้า']}_{stock_date.isoformat()}.jpg",
                            content=img_file.getvalue(),
                            mime_type=img_file.type or "image/jpeg",
                        )
                except Exception as e:
                    st.warning(f"บันทึกรูปไม่ได้: {e} — บันทึกโดยไม่มีรูป")
            try:
                sid = bills.create_stock(
                    stock_date=stock_date,
                    customer_code=selected_cust["รหัสลูกค้า"],
                    product_code=selected_prod["รหัสสินค้า"],
                    remaining=int(remaining),
                    image_url=image_url,
                    note=note.strip(),
                )
                st.success(
                    f"บันทึก `{sid}` — {selected_prod['ชื่อสินค้า']} เหลือ {remaining} "
                    f"ที่ {selected_cust['ชื่อลูกค้า']}"
                )
            except Exception as e:
                st.error(f"บันทึกไม่ได้: {e}")
