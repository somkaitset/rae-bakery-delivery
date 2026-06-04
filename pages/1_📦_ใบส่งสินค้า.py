"""
หน้าใบส่งสินค้า — list (คลิกแถวเพื่อเปิด) + detail + edit (ร่าง) + พิมพ์/คลัง PDF + delete
+ create (grid form)
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
import streamlit.components.v1 as components

from lib import bills, pdf, pdf_archive, sheets
from lib.auth import require_auth

require_auth()

st.title("📦 ใบส่งสินค้า")


# =====================================================
# Shared product-quantity grid (ใช้ทั้งแท็บสร้างใหม่ + ฟอร์มแก้ไข)
# =====================================================
def _bill_grid(active_products, price_set, prices, preset_qty=None, key=None):
    """แสดงกริดสินค้าทั้งหมด (เรียงตามกลุ่มราคา→รหัส) ให้กรอกจำนวน.

    preset_qty: { product_code: qty } เพื่อ preload (None = เริ่มที่ 0).
    คืน (items_qty dict {code: qty>0}, ยอดรวมเงิน).
    """
    preset_qty = preset_qty or {}
    products_sorted = sorted(active_products, key=bills.price_group_sort_key)

    grid_rows = []
    for p in products_sorted:
        code = str(p.get("code", ""))
        pg = str(p.get("price_group", ""))
        unit = bills.unit_price(price_set, pg, prices)
        grid_rows.append({
            "รหัส": code,
            "ชื่อสินค้า": str(p.get("name", "")),
            "กลุ่ม": pg,
            "หน่วยละ": unit,
            "จำนวน": int(preset_qty.get(code, 0)),
        })
    grid_df = pd.DataFrame(grid_rows)

    st.markdown("### กรอกจำนวนเฉพาะที่ส่ง (เว้น 0 = ไม่ส่ง)")
    edited = st.data_editor(
        grid_df,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "รหัส": st.column_config.TextColumn(disabled=True),
            "ชื่อสินค้า": st.column_config.TextColumn(disabled=True),
            "กลุ่ม": st.column_config.TextColumn(disabled=True, width="small"),
            "หน่วยละ": st.column_config.NumberColumn(disabled=True, format="%.2f", width="small"),
            "จำนวน": st.column_config.NumberColumn(min_value=0, max_value=999, step=1, format="%d"),
        },
        key=key,
    )

    edited["จำนวนเงิน"] = edited["จำนวน"] * edited["หน่วยละ"]
    qty_sum = int(edited["จำนวน"].sum())
    amt_sum = float(edited["จำนวนเงิน"].sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("จำนวนชนิด (ที่ส่ง)", int((edited["จำนวน"] > 0).sum()))
    col2.metric("จำนวนชิ้น", qty_sum)
    col3.metric("รวมเป็นเงิน", f"{amt_sum:,.2f}")

    items_qty = {
        row["รหัส"]: int(row["จำนวน"])
        for _, row in edited.iterrows()
        if int(row["จำนวน"]) > 0
    }
    return items_qty, amt_sum


tab_list, tab_new = st.tabs(["📋 รายการใบส่ง", "➕ สร้างใบใหม่"])


# =====================================================
# Tab: รายการใบส่ง
# =====================================================
with tab_list:
    try:
        bills_data = sheets.bills()
        items_data = sheets.bill_items()
        customers_list = sheets.customers()
        products_list = sheets.products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()

    customers_map = {c.get("code"): c.get("name") for c in customers_list}
    product_name_map = {p.get("code"): p.get("name") for p in products_list}

    if not bills_data:
        st.info("ยังไม่มีใบส่ง — ไปที่แท็บ \"สร้างใบใหม่\"")
    else:
        # ตาราง: รหัส / วันที่ / ลูกค้า / รวมเป็นเงิน / สถานะ (เรียงวันที่ใหม่→เก่า)
        rows = []
        for b in bills_data:
            bid = str(b.get("bill_id", ""))
            rows.append({
                "รหัส": bid,
                "วันที่": b.get("date", ""),
                "ลูกค้า": customers_map.get(str(b.get("customer_code", "")), b.get("customer_code", "")),
                "รวมเป็นเงิน": bills.bill_total(bid, items_data),
                "สถานะ": b.get("status", ""),
            })
        df = pd.DataFrame(rows)
        df["_sort"] = df["วันที่"].apply(lambda s: bills.parse_date(s) or date(1900, 1, 1))
        df = df.sort_values("_sort", ascending=False).drop(columns=["_sort"]).reset_index(drop=True)

        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "รวมเป็นเงิน": st.column_config.NumberColumn(format="%.2f"),
            },
            key="bill_list_df",
        )

        # อ่านแถวที่คลิก → ตั้ง bill ที่กำลังเปิดไว้ใน session_state
        selected_rows = event.selection.rows if event and event.selection else []
        if selected_rows:
            st.session_state["sel_bill_id"] = str(df.iloc[selected_rows[0]]["รหัส"])

        sel_bill_id = st.session_state.get("sel_bill_id")
        # ใบที่เลือกอาจถูกลบไปแล้ว — เคลียร์ถ้าไม่เจอ
        if sel_bill_id and not any(str(b.get("bill_id")) == sel_bill_id for b in bills_data):
            sel_bill_id = None
            st.session_state.pop("sel_bill_id", None)

        if sel_bill_id:
            bill = next(b for b in bills_data if str(b.get("bill_id")) == sel_bill_id)
            cust = next(
                (c for c in customers_list if str(c.get("code")) == str(bill.get("customer_code"))),
                {},
            )
            status = str(bill.get("status", ""))
            cust_name = customers_map.get(str(bill.get("customer_code", "")), bill.get("customer_code", ""))

            st.divider()
            st.subheader(f"ใบ {sel_bill_id} — {cust_name}")
            st.caption(f"วันที่ {bill.get('date', '')} · สถานะ: **{status}**")

            # --- รายการสินค้า (ตามชนิดสินค้า) ---
            bill_items = [
                it for it in items_data
                if str(it.get("bill_id", "")) == sel_bill_id
                and bills._to_float(it.get("qty", 0)) > 0
            ]
            detail_rows = [
                {
                    "สินค้า": product_name_map.get(str(it.get("product_code", "")), it.get("product_code", "")),
                    "จำนวน": int(bills._to_float(it.get("qty", 0))),
                    "หน่วยละ": bills._to_float(it.get("unit_price", 0)),
                    "จำนวนเงิน": bills._to_float(it.get("amount", 0)),
                }
                for it in bill_items
            ]
            if detail_rows:
                st.dataframe(
                    pd.DataFrame(detail_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "หน่วยละ": st.column_config.NumberColumn(format="%.2f"),
                        "จำนวนเงิน": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
            else:
                st.info("ใบนี้ยังไม่มีรายการสินค้า")

            total = bills.bill_total(sel_bill_id, items_data)
            st.metric("รวมเป็นเงิน", f"{total:,.2f}")

            # --- พิมพ์บิล (key off STATUS) ---
            lines = bills.lines_for_bill(sel_bill_id)
            if st.button("🖨️ พิมพ์บิล", type="primary", key="print_btn"):
                if not lines:
                    st.warning("ใบนี้ยังไม่มีรายการ — ยังพิมพ์ไม่ได้")
                else:
                    try:
                        if status == "ร่าง":
                            pdf_bytes = pdf.generate_bill_pdf(bill, cust, lines, total)
                            pdf_archive.save_pdf(sel_bill_id, pdf_bytes)
                            bills.finalize(sel_bill_id)  # ร่าง → ส่งแล้ว (ล็อก)
                        elif pdf_archive.read_pdf(sel_bill_id) is None:
                            # ส่งแล้ว แต่ยังไม่มีไฟล์ในคลัง → self-heal (สถานะคงเดิม)
                            pdf_bytes = pdf.generate_bill_pdf(bill, cust, lines, total)
                            pdf_archive.save_pdf(sel_bill_id, pdf_bytes)
                        else:
                            pdf_bytes = pdf_archive.read_pdf(sel_bill_id)  # ใช้ไฟล์เดิม

                        st.session_state["print_html"] = pdf.render_bill_html(bill, cust, lines, total)
                        st.session_state["print_bill_id"] = sel_bill_id
                        st.rerun()
                    except Exception as e:
                        st.error(f"พิมพ์/สร้าง PDF ไม่ได้: {e}")

            # auto-pop print dialog (หลัง rerun) สำหรับใบที่เพิ่งกดพิมพ์
            if st.session_state.get("print_bill_id") == sel_bill_id and st.session_state.get("print_html"):
                components.html(st.session_state["print_html"], height=0)
                st.caption("แตะ 'Print' เพื่อยืนยัน — บนมือถือบาง browser อาจต้องเปิดเอง")

            # ดาวน์โหลด PDF ตัวจริงจากคลัง (artifact ตัวจริง / พิมพ์ซ้ำ)
            archived = pdf_archive.read_pdf(sel_bill_id)
            if archived:
                st.download_button(
                    label="⬇️ ดาวน์โหลด PDF",
                    data=archived,
                    file_name=f"bill-{sel_bill_id}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dl_pdf",
                )

            st.divider()

            # --- แก้ไข (เฉพาะ 'ร่าง') / ล็อก (ส่งแล้ว) ---
            if status == "ร่าง":
                with st.expander("✏️ แก้ไขใบนี้", expanded=False):
                    active_customers = sheets.active_customers()
                    active_products = sheets.active_products()
                    if not active_customers or not active_products:
                        st.warning("ไม่มีลูกค้า/สินค้าที่ใช้งาน")
                    else:
                        cust_opts = {f"{c['name']} ({c['code']})": c for c in active_customers}
                        labels = list(cust_opts.keys())
                        cur_code = str(bill.get("customer_code", ""))
                        cur_idx = next(
                            (i for i, lab in enumerate(labels) if cust_opts[lab]["code"] == cur_code),
                            0,
                        )
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            edit_label = st.selectbox(
                                "ลูกค้า", options=labels, index=cur_idx, key="edit_cust"
                            )
                            edit_cust = cust_opts[edit_label]
                        with ec2:
                            cur_date = bills.parse_date(bill.get("date")) or date.today()
                            edit_date = st.date_input(
                                "วันที่", value=cur_date, format="DD/MM/YYYY", key="edit_date"
                            )

                        edit_price_set = edit_cust.get("price_set", "มาตรฐาน")
                        st.caption(f"ชุดราคา: **{edit_price_set}**")
                        edit_prices = bills.price_map()

                        preset = {
                            str(it.get("product_code", "")): int(bills._to_float(it.get("qty", 0)))
                            for it in items_data
                            if str(it.get("bill_id", "")) == sel_bill_id
                        }
                        edit_items_qty, _ = _bill_grid(
                            active_products, edit_price_set, edit_prices,
                            preset_qty=preset, key="edit_grid",
                        )
                        edit_note = st.text_input(
                            "หมายเหตุ (ทางเลือก)", value=str(bill.get("note", "")), key="edit_note"
                        )

                        if st.button("💾 บันทึกการแก้ไข", type="primary", key="save_edit"):
                            if not edit_items_qty:
                                st.warning("ยังไม่ได้ใส่จำนวนสินค้าใดเลย")
                            else:
                                try:
                                    with st.spinner("กำลังบันทึก..."):
                                        bills.update_bill(
                                            sel_bill_id,
                                            edit_cust["code"],
                                            edit_date,
                                            edit_items_qty,
                                            note=edit_note,
                                        )
                                    st.success("บันทึกการแก้ไขเรียบร้อย")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"บันทึกไม่ได้: {e}")
            else:
                st.info("🔒 ใบนี้ส่งแล้ว — ล็อกการแก้ไข กด \"ปลดล็อกเป็นร่าง\" เพื่อแก้")
                if st.button("🔓 ปลดล็อกเป็นร่าง", key="unlock_btn"):
                    try:
                        bills.revert_to_draft(sel_bill_id)
                        pdf_archive.delete_pdf(sel_bill_id)  # ให้พิมพ์ครั้งหน้า regenerate
                        st.session_state.pop("print_html", None)
                        st.session_state.pop("print_bill_id", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"ปลดล็อกไม่ได้: {e}")

            # --- ลบใบส่ง ---
            with st.expander("⚠️ ลบใบส่ง (ลบ items ทั้งหมดด้วย)"):
                confirm = st.checkbox(f"ยืนยันลบ `{sel_bill_id}`", key=f"confirm_del_{sel_bill_id}")
                if st.button("🗑️ ลบ", type="secondary", disabled=not confirm, key="del_btn"):
                    with st.spinner("กำลังลบ..."):
                        n = bills.delete_bill(sel_bill_id)
                    st.session_state.pop("sel_bill_id", None)
                    st.success(f"ลบใบ {sel_bill_id} เรียบร้อย (ลบ {n} แถว)")
                    st.rerun()
        else:
            st.info("คลิกแถวในตารางเพื่อเปิดดู/แก้ไข/พิมพ์ใบส่ง")


# =====================================================
# Tab: สร้างใบใหม่ (กริดสินค้าทั้งหมด)
# =====================================================
with tab_new:
    try:
        active_customers = sheets.active_customers()
        active_products = sheets.active_products()
    except Exception as e:
        st.error(f"อ่านข้อมูลไม่ได้: {e}")
        st.stop()

    if not active_customers or not active_products:
        st.warning("ไม่มีลูกค้า/สินค้าที่ใช้งาน")
        st.stop()

    cust_options = {f"{c['name']} ({c['code']})": c for c in active_customers}

    col1, col2 = st.columns(2)
    with col1:
        cust_label = st.selectbox("ลูกค้า", options=list(cust_options.keys()), key="new_cust")
        selected_cust = cust_options[cust_label]
    with col2:
        bill_date = st.date_input("วันที่", value=date.today(), format="DD/MM/YYYY", key="new_date")

    price_set = selected_cust.get("price_set", "มาตรฐาน")
    st.caption(f"ชุดราคา: **{price_set}**")

    prices = bills.price_map()

    items_qty, amt_sum = _bill_grid(active_products, price_set, prices, key="new_grid")

    note = st.text_input("หมายเหตุ (ทางเลือก)", key="new_note")

    col_save, col_save_send = st.columns(2)
    save_draft = col_save.button("💾 บันทึก (สถานะ: ร่าง)", use_container_width=True)
    save_send = col_save_send.button(
        "✅ บันทึก + ส่งแล้ว",
        type="primary",
        use_container_width=True,
    )

    if save_draft or save_send:
        if not items_qty:
            st.warning("ยังไม่ได้ใส่จำนวนสินค้าใดเลย")
        else:
            try:
                with st.spinner("กำลังบันทึก..."):
                    new_id = bills.create_bill(
                        customer_code=selected_cust["code"],
                        bill_date=bill_date,
                        items_qty=items_qty,
                        note=note,
                        status="ส่งแล้ว" if save_send else "ร่าง",
                    )
                st.success(f"🎉 สร้างใบ `{new_id}` เรียบร้อย ({len(items_qty)} ชนิด, รวม {amt_sum:,.2f} บาท)")
                st.balloons()
                st.info("ไปแท็บ \"รายการใบส่ง\" → คลิกแถวใบที่เพิ่งสร้าง → กด \"พิมพ์บิล\"")
            except Exception as e:
                st.error(f"บันทึกไม่ได้: {e}")
