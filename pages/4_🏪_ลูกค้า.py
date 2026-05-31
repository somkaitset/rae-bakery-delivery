"""
หน้าจัดการลูกค้า — list + CRUD
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from lib.auth import require_auth
from lib import sheets

require_auth()

st.title("🏪 ลูกค้า")

tab_list, tab_new = st.tabs(["📋 รายชื่อ", "➕ เพิ่มลูกค้า"])

with tab_list:
    try:
        customers = sheets.customers()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()
    if not customers:
        st.info("ยังไม่มีลูกค้า")
    else:
        st.dataframe(customers, use_container_width=True, hide_index=True)

with tab_new:
    st.subheader("เพิ่มลูกค้าใหม่")
    st.info("🚧 กำลังพัฒนา — st.form กรอกข้อมูล + auto-gen รหัสลูกค้า")

# TODO:
# - st.form กรอก: ชื่อลูกค้า, ชุดราคา (มาตรฐาน/ศว.), ที่อยู่, เบอร์โทร
# - auto-gen รหัสลูกค้า (C001, C002, ...) จาก max existing + 1
# - sheets.append("customer", [code, name, price_set, address, phone, True])
# - แก้: edit form แสดงข้อมูลเดิม → update_row
# - ปิด/เปิด: toggle ใช้งาน
