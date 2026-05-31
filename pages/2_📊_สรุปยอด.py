"""
หน้าสรุปยอด — รายวัน / รายสัปดาห์ / รายลูกค้า / รายเดือน
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

st.title("📊 สรุปยอดส่งสินค้า")

tabs = st.tabs(["📅 รายวัน", "🗓️ รายสัปดาห์", "📆 รายเดือน", "👥 รายลูกค้า"])

with tabs[0]:
    st.subheader("รายวัน — ทุกลูกค้า")
    st.info("🚧 กำลังพัฒนา — pandas pivot + bar chart")

with tabs[1]:
    st.subheader("รายสัปดาห์ — ทุกลูกค้า")
    st.info("🚧 กำลังพัฒนา")

with tabs[2]:
    st.subheader("รายเดือน — ทุกลูกค้า")
    st.info("🚧 กำลังพัฒนา")

with tabs[3]:
    st.subheader("รายลูกค้า")
    st.info("🚧 กำลังพัฒนา — เลือกลูกค้า → สรุปยอดของลูกค้านั้น")

# TODO:
# - อ่าน bills, bill_items, bill_lines via lib.sheets
# - pandas pivot: date × customer × sum(amount)
# - st.bar_chart / st.altair_chart
# - filter ช่วงวันที่ (st.date_input range)
# - export CSV
