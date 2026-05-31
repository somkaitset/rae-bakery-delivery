"""
หน้าจัดการสินค้า — gallery + add (with image) + edit
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from lib import bills, drive, sheets
from lib.auth import require_auth

require_auth()

st.title("🍰 สินค้า")

PRICE_GROUPS = ["10", "12", "15", "20", "25", "30", "35"]

tab_gal, tab_table, tab_new, tab_edit = st.tabs(
    ["🖼️ Gallery", "📋 ตาราง", "➕ เพิ่มสินค้า", "✏️ แก้ไข"]
)


def _normalize_active(v):
    return bool(v) if isinstance(v, bool) else str(v).upper() in ("TRUE", "1")


# --- Gallery ---
with tab_gal:
    try:
        ps = sheets.products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()

    if not ps:
        st.info("ยังไม่มีสินค้า")
    else:
        # filter active + sort by ลำดับแสดง
        active_only = st.toggle("แสดงเฉพาะที่ใช้งาน", value=True, key="gal_active")
        ps_filtered = [p for p in ps if (not active_only) or _normalize_active(p.get("ใช้งาน"))]
        ps_filtered.sort(key=lambda p: int(bills._to_float(p.get("ลำดับแสดง", 0))))

        cols_per_row = 4
        for i in range(0, len(ps_filtered), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, p in enumerate(ps_filtered[i:i + cols_per_row]):
                with cols[j]:
                    img = str(p.get("รูปสินค้า", "") or "")
                    if img:
                        try:
                            st.image(img, use_container_width=True)
                        except Exception:
                            st.caption("(โหลดรูปไม่ได้)")
                    else:
                        st.markdown(
                            "<div style='height:120px;background:#eee;border-radius:8px;"
                            "display:flex;align-items:center;justify-content:center;color:#999'>"
                            "ไม่มีรูป</div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        f"**{p.get('ชื่อสินค้า', '')}**  \n"
                        f"`{p.get('รหัสสินค้า', '')}` • กลุ่ม {p.get('กลุ่มราคา', '')}"
                    )


# --- Table ---
with tab_table:
    try:
        ps = sheets.products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()
    if not ps:
        st.info("ยังไม่มีสินค้า")
    else:
        df = pd.DataFrame(ps)
        if "ใช้งาน" in df.columns:
            df["ใช้งาน"] = df["ใช้งาน"].apply(_normalize_active)
        df = df.sort_values(["ใช้งาน", "ลำดับแสดง"], ascending=[False, True]).reset_index(drop=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"รวม **{len(ps)}** รายการ ({int(df['ใช้งาน'].sum())} ใช้งาน)")


# --- Add ---
with tab_new:
    st.subheader("เพิ่มสินค้าใหม่")
    pg_pick = st.selectbox("กลุ่มราคา *", options=PRICE_GROUPS, key="new_pg")
    next_code = bills.next_product_code(pg_pick)
    st.caption(f"รหัสที่จะใช้: `{next_code}`")

    with st.form("new_product_form", clear_on_submit=True):
        name = st.text_input("ชื่อสินค้า *", placeholder="เช่น โดนัทช็อกโกแลต")
        c1, c2 = st.columns(2)
        with c1:
            display_order = st.number_input("ลำดับแสดง", min_value=0, max_value=999, value=0)
        with c2:
            active = st.checkbox("ใช้งาน", value=True)

        st.markdown("**รูปสินค้า**")
        col_cam, col_file = st.columns(2)
        with col_cam:
            cam_pic = st.camera_input("📸 ถ่ายรูป")
        with col_file:
            uploaded = st.file_uploader(
                "หรืออัปโหลดจากไฟล์", type=["jpg", "jpeg", "png", "webp"]
            )

        submitted = st.form_submit_button("💾 บันทึก", type="primary", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("กรอกชื่อสินค้า")
            else:
                image_url = ""
                img_file = cam_pic or uploaded
                if img_file:
                    try:
                        with st.spinner("กำลังอัปโหลดรูป..."):
                            res = drive.upload_bytes(
                                name=f"product_{name.strip()}_{next_code}.jpg",
                                content=img_file.getvalue(),
                                mime_type=img_file.type or "image/jpeg",
                            )
                            image_url = res.get("thumbnail_url") or res.get("webViewLink", "")
                    except Exception as e:
                        st.warning(f"อัปโหลดรูปไม่ได้: {e} — บันทึกข้อมูลโดยไม่มีรูป")
                try:
                    code = bills.create_product(
                        name=name.strip(),
                        price_group=pg_pick,
                        image_url=image_url,
                        display_order=int(display_order),
                        active=active,
                    )
                    st.success(f"เพิ่ม `{code}` ({name}) เรียบร้อย")
                    if image_url:
                        st.image(image_url, width=150)
                except Exception as e:
                    st.error(f"บันทึกไม่ได้: {e}")


# --- Edit ---
with tab_edit:
    st.subheader("แก้ไขสินค้า")
    try:
        ps = sheets.products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()
    if not ps:
        st.info("ยังไม่มีสินค้า")
    else:
        labels = {
            f"{p['รหัสสินค้า']} — {p['ชื่อสินค้า']} (กลุ่ม {p.get('กลุ่มราคา', '')})": (i, p)
            for i, p in enumerate(ps)
        }
        choice = st.selectbox("เลือกสินค้า", options=list(labels.keys()), key="edit_prod")
        idx, target = labels[choice]
        row_number = idx + 2

        current_img = str(target.get("รูปสินค้า", "") or "")
        if current_img:
            st.image(current_img, width=150, caption="รูปปัจจุบัน")

        with st.form("edit_product_form"):
            code = st.text_input("รหัส", value=target.get("รหัสสินค้า", ""), disabled=True)
            name = st.text_input("ชื่อสินค้า *", value=str(target.get("ชื่อสินค้า", "")))
            current_pg = str(target.get("กลุ่มราคา", "10"))
            price_group = st.selectbox(
                "กลุ่มราคา *",
                options=PRICE_GROUPS,
                index=PRICE_GROUPS.index(current_pg) if current_pg in PRICE_GROUPS else 0,
            )
            display_order = st.number_input(
                "ลำดับแสดง",
                min_value=0, max_value=999,
                value=int(bills._to_float(target.get("ลำดับแสดง", 0))),
            )
            active = st.checkbox("ใช้งาน", value=_normalize_active(target.get("ใช้งาน")))

            st.markdown("**เปลี่ยนรูป (ทางเลือก)**")
            col_cam, col_file = st.columns(2)
            with col_cam:
                cam_pic = st.camera_input("📸 ถ่ายรูปใหม่", key="edit_cam")
            with col_file:
                uploaded = st.file_uploader(
                    "หรืออัปโหลดไฟล์ใหม่",
                    type=["jpg", "jpeg", "png", "webp"],
                    key="edit_file",
                )
            keep_current = st.checkbox("เก็บรูปเดิม", value=True)

            submitted = st.form_submit_button("💾 บันทึก", type="primary", use_container_width=True)
            if submitted:
                if not name.strip():
                    st.error("กรอกชื่อสินค้า")
                else:
                    new_img_url = current_img if keep_current else ""
                    img_file = cam_pic or uploaded
                    if img_file:
                        try:
                            with st.spinner("กำลังอัปโหลดรูปใหม่..."):
                                res = drive.upload_bytes(
                                    name=f"product_{name.strip()}_{code}.jpg",
                                    content=img_file.getvalue(),
                                    mime_type=img_file.type or "image/jpeg",
                                )
                                new_img_url = res.get("thumbnail_url") or res.get("webViewLink", "")
                        except Exception as e:
                            st.warning(f"อัปโหลดไม่ได้: {e}")
                    try:
                        bills.update_product(
                            row_number, code, name.strip(), price_group,
                            new_img_url, int(display_order), active,
                        )
                        st.success(f"อัปเดต `{code}` เรียบร้อย")
                        st.rerun()
                    except Exception as e:
                        st.error(f"อัปเดตไม่ได้: {e}")
