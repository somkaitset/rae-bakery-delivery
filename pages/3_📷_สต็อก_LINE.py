"""
หน้าบันทึกสต็อกคงเหลือจากรูปลูกค้าส่งทาง LINE
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from lib.auth import require_auth

require_auth()

st.title("📷 สต็อกคงเหลือ (จากรูป LINE)")

tab_list, tab_new = st.tabs(["📋 สต็อกล่าสุด", "➕ บันทึกใหม่"])

with tab_list:
    st.subheader("สต็อกที่บันทึกไว้")
    st.info("🚧 กำลังพัฒนา — แสดงเป็น gallery (รูป + ลูกค้า + สินค้า + จำนวน)")

with tab_new:
    st.subheader("บันทึกสต็อกใหม่")
    st.info(
        "🚧 กำลังพัฒนา\n\n"
        "Flow:\n"
        "1. ลูกค้าส่งรูปสินค้าเหลือทาง LINE\n"
        "2. กด `Browse files` หรือใช้กล้องอัปโหลด\n"
        "3. เลือกลูกค้า, สินค้า, จำนวนคงเหลือ, วันที่\n"
        "4. กด Save → อัปโหลดรูปไป Drive → บันทึกลง Sheet"
    )
    # uploaded = st.camera_input("ถ่ายรูป") หรือ st.file_uploader("อัปโหลดรูป")

# TODO:
# - st.file_uploader / st.camera_input
# - selectbox: ลูกค้า, สินค้า
# - number_input: จำนวนคงเหลือ
# - date_input: วันที่ (default = today)
# - upload via lib.drive.upload_bytes → save URL ลง stock tab
