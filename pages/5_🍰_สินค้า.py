"""
หน้าจัดการสินค้า — แกลเลอรี่ (คลิกแก้ไข) + ตาราง + เพิ่ม + แก้ไข/ลบ

โครงสร้าง: ใช้ session_state เป็น router แทน st.tabs เพราะ tabs สลับเองไม่ได้
- ปกติ: เลือกมุมมองด้วย radio (แกลเลอรี่ / ตาราง / เพิ่ม)
- คลิก "แก้ไข" ใต้รูปในแกลเลอรี่ → เข้าโหมดแก้ไขสินค้านั้น
- บันทึก/ลบ/ยกเลิก → กลับมาที่แกลเลอรี่ (อ่านข้อมูลใหม่ → รูปอัปเดตทันที)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from lib import bills, sheets, storage
from lib.auth import require_auth

require_auth()

st.title("🍰 สินค้า")

PRICE_GROUPS = ["10", "12", "15", "20", "25", "30", "35"]

st.session_state.setdefault("prod_edit_code", None)
st.session_state.setdefault("prod_table_nonce", 0)


# --- helpers ---

def _normalize_active(v):
    return bool(v) if isinstance(v, bool) else str(v).upper() in ("TRUE", "1")


def _sort_key(p):
    """เรียงตามกลุ่มราคา (ตัวเลข) แล้วตามด้วยรหัสสินค้า."""
    return (int(bills._to_float(p.get("price_group", 0))), str(p.get("code", "")))


def _go_edit(code: str) -> None:
    st.session_state.prod_edit_code = code


def _go_gallery() -> None:
    st.session_state.prod_edit_code = None
    st.session_state.prod_nav = "🖼️ แกลเลอรี่"


# ============ Views ============

def render_gallery() -> None:
    flash = st.session_state.pop("prod_flash", None)
    if flash:
        st.success(flash)

    try:
        ps = sheets.products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        return

    if not ps:
        st.info("ยังไม่มีสินค้า — ไปที่ ➕ เพิ่มสินค้า")
        return

    active_only = st.toggle("แสดงเฉพาะที่ใช้งาน", value=True, key="gal_active")
    ps = [p for p in ps if (not active_only) or _normalize_active(p.get("active"))]
    ps.sort(key=_sort_key)
    st.caption("เรียงตามกลุ่มราคา → รหัสสินค้า • คลิก **✏️ แก้ไข** ใต้รูปเพื่อแก้สินค้านั้น")

    cols_per_row = 4
    for i in range(0, len(ps), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, p in enumerate(ps[i:i + cols_per_row]):
            code = str(p.get("code", ""))
            with cols[j]:
                img = storage.image_src(p.get("image"))
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
                st.button(
                    "✏️ แก้ไข",
                    key=f"edit_btn_{code}",
                    use_container_width=True,
                    on_click=_go_edit,
                    args=(code,),
                )
                st.markdown(
                    f"**{p.get('name', '')}**  \n"
                    f"`{code}` • กลุ่ม {p.get('price_group', '')}"
                )


def render_table() -> None:
    flash = st.session_state.pop("prod_table_flash", None)
    if flash:
        st.success(flash)

    try:
        ps = sheets.products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        return
    if not ps:
        st.info("ยังไม่มีสินค้า")
        return

    ps_sorted = sorted(ps, key=_sort_key)
    # One normalized source for BOTH the editor frame and the diff snapshot, so
    # like-typed comparisons don't false-positive every row as "changed"
    # (active→bool, display_order→int, price_group→str). image is kept for the
    # write pass-through but is omitted from the editor.
    normalized = [
        {
            "code": str(p.get("code", "")),
            "name": str(p.get("name", "") or ""),
            "price_group": str(p.get("price_group", "")),
            "display_order": int(bills._to_float(p.get("display_order", 0))),
            "active": _normalize_active(p.get("active")),
            "image": str(p.get("image", "") or ""),
        }
        for p in ps_sorted
    ]
    snapshot = {row["code"]: row for row in normalized}

    df_editable = pd.DataFrame(
        [{k: r[k] for k in ("code", "name", "price_group", "display_order", "active")}
         for r in normalized]
    )

    edited = st.data_editor(
        df_editable,
        key=f"prod_table_{st.session_state.prod_table_nonce}",
        num_rows="fixed",
        use_container_width=True,
        hide_index=True,
        column_config={
            "code": st.column_config.TextColumn("รหัสสินค้า", disabled=True),
            "name": st.column_config.TextColumn("ชื่อสินค้า", required=True),
            "price_group": st.column_config.SelectboxColumn("กลุ่มราคา", options=PRICE_GROUPS),
            "display_order": st.column_config.NumberColumn(
                "ลำดับแสดง", min_value=0, max_value=999, step=1
            ),
            "active": st.column_config.CheckboxColumn("ใช้งาน"),
        },
    )

    if st.button("💾 บันทึก", type="primary", use_container_width=True):
        edited_rows = edited.to_dict("records")
        written = 0
        empty_name_codes: list[str] = []
        missing_row_codes: list[str] = []
        for row in edited_rows:
            code = str(row.get("code", ""))
            orig = snapshot.get(code)
            if orig is None:
                continue
            name = str(row.get("name", "") or "").strip()
            price_group = str(row.get("price_group", ""))
            display_order = int(bills._to_float(row.get("display_order", 0)))
            active = bool(row.get("active"))
            changed = (
                name != orig["name"].strip()
                or price_group != orig["price_group"]
                or display_order != orig["display_order"]
                or active != orig["active"]
            )
            if not changed:
                continue
            if not name:
                empty_name_codes.append(code)
                continue
            row_number = sheets.find_row_by_key("product", code)
            if not row_number:
                missing_row_codes.append(code)
                continue
            bills.update_product(
                row_number, code, name, price_group,
                orig["image"], display_order, active,
            )
            written += 1

        if written:
            st.session_state.prod_table_flash = f"บันทึก {written} รายการเรียบร้อย"
            st.session_state.prod_table_nonce += 1
        if empty_name_codes:
            st.error("ชื่อสินค้าห้ามว่าง: " + ", ".join(empty_name_codes))
        if missing_row_codes:
            st.error("หาแถวใน Sheet ไม่เจอ ข้าม: " + ", ".join(missing_row_codes))
        if written:
            st.rerun()
        elif not empty_name_codes and not missing_row_codes:
            st.info("ไม่มีการเปลี่ยนแปลง")

    active_n = sum(_normalize_active(p.get("active")) for p in ps)
    st.caption(f"รวม **{len(ps)}** รายการ ({active_n} ใช้งาน)")


def render_add() -> None:
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

        uploaded = st.file_uploader(
            "รูปสินค้า (บนมือถือเลือก \"ถ่ายรูป\" หรือ \"เลือกจากเครื่อง\" ได้)",
            type=["jpg", "jpeg", "png", "webp"],
        )

        submitted = st.form_submit_button("💾 บันทึก", type="primary", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("กรอกชื่อสินค้า")
                return
            image_url = ""
            if uploaded:
                try:
                    with st.spinner("กำลังบันทึกรูป..."):
                        image_url = storage.save_image(
                            name=f"product_{name.strip()}_{next_code}.jpg",
                            content=uploaded.getvalue(),
                            mime_type=uploaded.type or "image/jpeg",
                        )
                except Exception as e:
                    st.warning(f"บันทึกรูปไม่ได้: {e} — บันทึกข้อมูลโดยไม่มีรูป")
            try:
                code = bills.create_product(
                    name=name.strip(),
                    price_group=pg_pick,
                    image_url=image_url,
                    display_order=int(display_order),
                    active=active,
                )
                st.success(f"เพิ่ม `{code}` ({name}) เรียบร้อย")
                preview = storage.image_src(image_url)
                if preview:
                    st.image(preview, width=150)
            except Exception as e:
                st.error(f"บันทึกไม่ได้: {e}")


def render_edit(code: str) -> None:
    st.button("⬅️ กลับแกลเลอรี่", on_click=_go_gallery)

    try:
        ps = sheets.products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        return

    target = next((p for p in ps if str(p.get("code", "")) == code), None)
    if target is None:
        st.error(f"ไม่พบสินค้า `{code}` (อาจถูกลบไปแล้ว) — กดกลับแกลเลอรี่")
        return

    row_number = sheets.find_row_by_key("product", code)
    if not row_number:
        st.error(f"หาแถวของ `{code}` ใน Sheet ไม่เจอ")
        return

    st.subheader(f"แก้ไขสินค้า `{code}`")

    current_img = str(target.get("image", "") or "")
    current_src = storage.image_src(current_img)
    if current_src:
        st.image(current_src, width=150, caption="รูปปัจจุบัน")

    with st.form("edit_product_form"):
        st.text_input("รหัส", value=code, disabled=True)
        name = st.text_input("ชื่อสินค้า *", value=str(target.get("name", "")))
        current_pg = str(target.get("price_group", "10"))
        price_group = st.selectbox(
            "กลุ่มราคา *",
            options=PRICE_GROUPS,
            index=PRICE_GROUPS.index(current_pg) if current_pg in PRICE_GROUPS else 0,
        )
        display_order = st.number_input(
            "ลำดับแสดง", min_value=0, max_value=999,
            value=int(bills._to_float(target.get("display_order", 0))),
        )
        active = st.checkbox("ใช้งาน", value=_normalize_active(target.get("active")))

        uploaded = st.file_uploader(
            "เปลี่ยนรูป (เว้นว่าง = ใช้รูปเดิม)",
            type=["jpg", "jpeg", "png", "webp"],
        )

        submitted = st.form_submit_button("💾 บันทึก", type="primary", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("กรอกชื่อสินค้า")
                return
            new_img = current_img
            if uploaded:
                try:
                    with st.spinner("กำลังบันทึกรูปใหม่..."):
                        new_img = storage.save_image(
                            name=f"product_{name.strip()}_{code}.jpg",
                            content=uploaded.getvalue(),
                            mime_type=uploaded.type or "image/jpeg",
                        )
                except Exception as e:
                    st.warning(f"บันทึกรูปไม่ได้: {e}")
            try:
                bills.update_product(
                    row_number, code, name.strip(), price_group,
                    new_img, int(display_order), active,
                )
                st.session_state.prod_flash = f"อัปเดต `{code}` เรียบร้อย"
                _go_gallery()
                st.rerun()
            except Exception as e:
                st.error(f"อัปเดตไม่ได้: {e}")

    with st.expander("🗑️ ลบสินค้านี้"):
        st.warning("การลบไม่สามารถย้อนกลับได้ (รูปในเครื่องจะถูกลบด้วย)")
        if st.button(f"ยืนยันลบ `{code}`", type="primary", key="del_prod"):
            try:
                bills.delete_product(row_number)
                storage.delete_image(current_img)
                st.session_state.prod_flash = f"ลบ `{code}` แล้ว"
                _go_gallery()
                st.rerun()
            except Exception as e:
                st.error(f"ลบไม่ได้: {e}")


# ============ Router ============

if st.session_state.prod_edit_code:
    render_edit(st.session_state.prod_edit_code)
else:
    view = st.radio(
        "เมนู",
        ["🖼️ แกลเลอรี่", "📋 ตาราง", "➕ เพิ่มสินค้า"],
        horizontal=True,
        key="prod_nav",
        label_visibility="collapsed",
    )
    if view == "🖼️ แกลเลอรี่":
        render_gallery()
    elif view == "📋 ตาราง":
        render_table()
    else:
        render_add()
