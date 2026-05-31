"""
หน้าใบส่งสินค้า — list + create + edit + print bill
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

st.title("📦 ใบส่งสินค้า")

tab_list, tab_new = st.tabs(["📋 รายการใบส่ง", "➕ สร้างใบใหม่"])

with tab_list:
    st.subheader("รายการใบส่งทั้งหมด")
    try:
        bills = sheets.bills()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()
    if not bills:
        st.info("ยังไม่มีใบส่ง")
    else:
        st.dataframe(bills, use_container_width=True, hide_index=True)

with tab_new:
    st.subheader("สร้างใบส่งใหม่ (กริดสินค้าทั้งหมด)")
    st.info(
        "🚧 กำลังพัฒนา\n\n"
        "Flow ที่จะทำ:\n"
        "1. เลือกลูกค้า + วันที่\n"
        "2. แสดงสินค้าทุกตัวที่ใช้งาน พร้อมตัวเลขแนะนำ (AVG 7 วัน − สต็อก)\n"
        "3. ใส่จำนวนเฉพาะตัวที่ส่ง\n"
        "4. กด Save → เขียนลง Sheet → สามารถพิมพ์บิล PDF ได้"
    )

# TODO:
# - Form กริดสินค้าทั้งหมด (st.data_editor)
# - สูตรแนะนำ: AVG bill_items 7 วันล่าสุดของลูกค้านี้ × สินค้านี้ − สต็อกล่าสุด
# - เขียนแถวลง bill + bill_item
# - ปุ่ม "พิมพ์บิล" → lib.pdf.generate_bill_pdf → st.download_button
# - ปุ่ม "แก้ไข" → form prefilled
# - ปุ่ม "ลบ" → confirm dialog
