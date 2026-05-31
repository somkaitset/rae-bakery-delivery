"""
หน้าจัดการสินค้า — list (gallery) + CRUD + อัปโหลดรูป
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

st.title("🍰 สินค้า")

tab_list, tab_new = st.tabs(["📋 รายการสินค้า", "➕ เพิ่มสินค้า"])

with tab_list:
    try:
        products = sheets.products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()
    if not products:
        st.info("ยังไม่มีสินค้า")
    else:
        st.dataframe(products, use_container_width=True, hide_index=True)
        # TODO: แทน dataframe ด้วย gallery (st.columns + st.image)

with tab_new:
    st.subheader("เพิ่มสินค้าใหม่")
    st.info("🚧 กำลังพัฒนา — st.form + st.camera_input/st.file_uploader สำหรับรูป")

# TODO:
# - st.form: ชื่อสินค้า, กลุ่มราคา (selectbox จาก กลุ่มราคา), ลำดับแสดง
# - st.camera_input / st.file_uploader → lib.drive.upload_bytes → URL ลง สินค้า.รูปสินค้า
# - auto-gen รหัสสินค้า (P{group}{seq}) จาก max existing + 1 ในกลุ่มนั้น
# - Gallery view: columns 3 ต่อแถว, st.image(url) + caption
