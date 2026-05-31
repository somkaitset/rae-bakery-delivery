"""
rae-bakery-delivery — Streamlit entry point.

หน้าหลัก: login + dashboard
หน้าอื่น: ดูใน pages/ (Streamlit auto-detects multipage)

รัน: streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# ให้ pages/*.py import lib/* ได้
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from lib.config import APP_TITLE
from lib.auth import login_or_stop, current_user, logout_button


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🍞",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Login (block until success) ---
login_or_stop()

# --- Sidebar: user info + logout ---
user = current_user()
with st.sidebar:
    st.markdown(f"👤 **{user['name']}**")
    st.caption(f"role: `{user.get('role', '-')}`")
    logout_button()

# --- Main: dashboard ---
st.title("🍞 เรเบเกอรี่ — ระบบส่งสินค้า")
st.markdown(
    """
    เลือกเมนูทางซ้ายเพื่อเริ่มใช้งาน

    | เมนู | คำอธิบาย |
    |---|---|
    | 📦 **ใบส่งสินค้า** | สร้าง/แก้บิลส่ง + ฟอร์มกริดสินค้าทั้งหมด + พิมพ์ PDF |
    | 📊 **สรุปยอด** | รายวัน/รายสัปดาห์ ทั้งหมด + รายลูกค้า |
    | 📷 **สต็อก LINE** | บันทึกสต็อกคงเหลือจากรูปลูกค้าส่งทาง LINE |
    | 🏪 **ลูกค้า** | เพิ่ม/แก้ข้อมูลลูกค้า |
    | 🍰 **สินค้า** | เพิ่ม/แก้สินค้า + อัปโหลดรูป |
    """
)

st.divider()
st.caption("v0.1 — skeleton (pages ยังเป็น placeholder)")
