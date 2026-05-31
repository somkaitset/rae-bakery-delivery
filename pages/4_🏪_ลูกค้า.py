"""
หน้าจัดการลูกค้า — list + add + edit
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from lib import bills, sheets
from lib.auth import require_auth

require_auth()

st.title("🏪 ลูกค้า")

tab_list, tab_new, tab_edit = st.tabs(["📋 รายชื่อ", "➕ เพิ่มลูกค้า", "✏️ แก้ไข"])

PRICE_SETS = ["มาตรฐาน", "ศว."]


# --- List ---
with tab_list:
    try:
        cs = sheets.customers()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()

    if not cs:
        st.info("ยังไม่มีลูกค้า")
    else:
        df = pd.DataFrame(cs)
        # normalize ใช้งาน column to bool
        if "ใช้งาน" in df.columns:
            df["ใช้งาน"] = df["ใช้งาน"].apply(
                lambda v: bool(v) if isinstance(v, bool) else str(v).upper() in ("TRUE", "1")
            )
        df = df.sort_values(["ใช้งาน", "ชื่อลูกค้า"], ascending=[False, True]).reset_index(drop=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"รวม **{len(cs)}** ราย ({int(df['ใช้งาน'].sum())} ใช้งาน)")


# --- Add ---
with tab_new:
    st.subheader("เพิ่มลูกค้าใหม่")
    next_code = bills.next_customer_code()
    st.caption(f"รหัสที่จะใช้: `{next_code}`")
    with st.form("new_customer_form", clear_on_submit=True):
        name = st.text_input("ชื่อลูกค้า *", placeholder="เช่น โรงเรียนเทศบาล 1")
        price_set = st.selectbox("ชุดราคา *", options=PRICE_SETS, index=0)
        address = st.text_area("ที่อยู่", height=80)
        phone = st.text_input("เบอร์โทร")
        submitted = st.form_submit_button("💾 บันทึก", type="primary", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("กรอกชื่อลูกค้า")
            else:
                try:
                    code = bills.create_customer(name.strip(), price_set, address.strip(), phone.strip())
                    st.success(f"เพิ่ม `{code}` ({name}) เรียบร้อย")
                except Exception as e:
                    st.error(f"บันทึกไม่ได้: {e}")


# --- Edit ---
with tab_edit:
    st.subheader("แก้ไขลูกค้า")
    try:
        cs = sheets.customers()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()

    if not cs:
        st.info("ยังไม่มีลูกค้า")
    else:
        labels = {f"{c['รหัสลูกค้า']} — {c['ชื่อลูกค้า']}": (i, c) for i, c in enumerate(cs)}
        choice = st.selectbox("เลือกลูกค้า", options=list(labels.keys()), key="edit_cust")
        idx, target = labels[choice]
        row_number = idx + 2  # row 1 = header

        with st.form("edit_customer_form"):
            code = st.text_input("รหัส", value=target.get("รหัสลูกค้า", ""), disabled=True)
            name = st.text_input("ชื่อลูกค้า *", value=str(target.get("ชื่อลูกค้า", "")))
            current_ps = str(target.get("ชุดราคา", "มาตรฐาน"))
            price_set = st.selectbox(
                "ชุดราคา *",
                options=PRICE_SETS,
                index=PRICE_SETS.index(current_ps) if current_ps in PRICE_SETS else 0,
            )
            address = st.text_area("ที่อยู่", value=str(target.get("ที่อยู่", "")), height=80)
            phone = st.text_input("เบอร์โทร", value=str(target.get("เบอร์โทร", "")))
            current_active = str(target.get("ใช้งาน", "TRUE")).upper() in ("TRUE", "1")
            active = st.checkbox("ใช้งาน", value=current_active)
            submitted = st.form_submit_button("💾 บันทึก", type="primary", use_container_width=True)
            if submitted:
                if not name.strip():
                    st.error("กรอกชื่อลูกค้า")
                else:
                    try:
                        bills.update_customer(
                            row_number, code, name.strip(), price_set,
                            address.strip(), phone.strip(), active,
                        )
                        st.success(f"อัปเดต `{code}` เรียบร้อย")
                        st.rerun()
                    except Exception as e:
                        st.error(f"อัปเดตไม่ได้: {e}")
