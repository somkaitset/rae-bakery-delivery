"""
หน้าสรุปยอด — รายวัน / รายสัปดาห์ / รายเดือน / รายลูกค้า
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from lib import bills, sheets
from lib.auth import require_auth

require_auth()

st.title("📊 สรุปยอดส่งสินค้า")


# --- Load data once ---
@st.cache_data(ttl=30)
def _load() -> tuple[pd.DataFrame, dict, dict]:
    bs = sheets.bills()
    its = sheets.bill_items()
    customers_map = {c.get("code"): c.get("name") for c in sheets.customers()}
    products_map = {p.get("code"): p.get("name") for p in sheets.products()}

    # build bills dataframe
    rows = []
    for b in bs:
        bid = str(b.get("bill_id", ""))
        d = bills.parse_date(b.get("date")) or date(1900, 1, 1)
        cust_code = str(b.get("customer_code", ""))
        rows.append({
            "รหัสใบส่ง": bid,
            "วันที่": d,
            "รหัสลูกค้า": cust_code,
            "ลูกค้า": customers_map.get(cust_code, cust_code),
            "จำนวนชิ้น": bills.bill_qty_total(bid, its),
            "รวมเป็นเงิน": bills.bill_total(bid, its),
            "สถานะ": str(b.get("status", "")),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["วันที่"] = pd.to_datetime(df["วันที่"])
        df["สัปดาห์"] = df["วันที่"].dt.to_period("W-SUN").astype(str)
        df["เดือน"] = df["วันที่"].dt.to_period("M").astype(str)

    return df, customers_map, products_map


try:
    df_all, customers_map, products_map = _load()
except Exception as e:
    st.error(f"อ่านข้อมูลไม่ได้: {e}")
    st.stop()

if df_all.empty:
    st.info("ยังไม่มีใบส่ง")
    st.stop()


# --- Date range filter ---
col1, col2, col3 = st.columns([1, 1, 1])
default_start = df_all["วันที่"].min().date()
default_end = df_all["วันที่"].max().date()
with col1:
    start = st.date_input("ตั้งแต่วันที่", value=default_start, format="DD/MM/YYYY")
with col2:
    end = st.date_input("ถึงวันที่", value=default_end, format="DD/MM/YYYY")
with col3:
    st.write("")
    st.write("")
    if st.button("🔄 รีเฟรช cache", use_container_width=True):
        _load.clear()
        st.rerun()

start_dt = pd.Timestamp(start)
end_dt = pd.Timestamp(end) + pd.Timedelta(days=1)
df = df_all[(df_all["วันที่"] >= start_dt) & (df_all["วันที่"] < end_dt)].copy()

if df.empty:
    st.warning("ไม่มีข้อมูลในช่วงที่เลือก")
    st.stop()

# --- KPI ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("ใบส่งทั้งหมด", len(df))
k2.metric("ลูกค้าที่ส่ง", df["รหัสลูกค้า"].nunique())
k3.metric("จำนวนชิ้นรวม", int(df["จำนวนชิ้น"].sum()))
k4.metric("ยอดเงินรวม", f"{df['รวมเป็นเงิน'].sum():,.2f}")

st.divider()

# --- Tabs ---
tab_d, tab_w, tab_m, tab_c = st.tabs(
    ["📅 รายวัน", "🗓️ รายสัปดาห์", "📆 รายเดือน", "👥 รายลูกค้า"]
)


def _pivot_by(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    pivot = df.groupby(group_col).agg(
        ใบส่ง=("รหัสใบส่ง", "count"),
        จำนวนชิ้น=("จำนวนชิ้น", "sum"),
        ยอดเงิน=("รวมเป็นเงิน", "sum"),
    ).reset_index()
    return pivot.sort_values(group_col, ascending=False).reset_index(drop=True)


with tab_d:
    df_show = df.copy()
    df_show["วันที่"] = df_show["วันที่"].dt.strftime("%-d/%-m/%Y")
    pivot = _pivot_by(df_show, "วันที่")
    st.bar_chart(
        pivot.set_index("วันที่")["ยอดเงิน"],
        height=300,
        use_container_width=True,
    )
    st.dataframe(
        pivot,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ยอดเงิน": st.column_config.NumberColumn(format="%.2f"),
            "จำนวนชิ้น": st.column_config.NumberColumn(format="%d"),
        },
    )

with tab_w:
    pivot = _pivot_by(df, "สัปดาห์")
    st.bar_chart(
        pivot.set_index("สัปดาห์")["ยอดเงิน"],
        height=300,
        use_container_width=True,
    )
    st.dataframe(
        pivot,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ยอดเงิน": st.column_config.NumberColumn(format="%.2f"),
            "จำนวนชิ้น": st.column_config.NumberColumn(format="%d"),
        },
    )

with tab_m:
    pivot = _pivot_by(df, "เดือน")
    st.bar_chart(
        pivot.set_index("เดือน")["ยอดเงิน"],
        height=300,
        use_container_width=True,
    )
    st.dataframe(
        pivot,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ยอดเงิน": st.column_config.NumberColumn(format="%.2f"),
            "จำนวนชิ้น": st.column_config.NumberColumn(format="%d"),
        },
    )

with tab_c:
    # group by customer
    by_cust = df.groupby(["รหัสลูกค้า", "ลูกค้า"]).agg(
        ใบส่ง=("รหัสใบส่ง", "count"),
        จำนวนชิ้น=("จำนวนชิ้น", "sum"),
        ยอดเงิน=("รวมเป็นเงิน", "sum"),
    ).reset_index().sort_values("ยอดเงิน", ascending=False)

    st.bar_chart(
        by_cust.set_index("ลูกค้า")["ยอดเงิน"],
        height=300,
        use_container_width=True,
    )
    st.dataframe(
        by_cust.drop(columns=["รหัสลูกค้า"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "ยอดเงิน": st.column_config.NumberColumn(format="%.2f"),
            "จำนวนชิ้น": st.column_config.NumberColumn(format="%d"),
        },
    )

    st.divider()
    st.subheader("รายละเอียดของลูกค้า")
    cust_pick = st.selectbox(
        "เลือกลูกค้า",
        options=by_cust["รหัสลูกค้า"].tolist(),
        format_func=lambda code: customers_map.get(code, code),
    )
    if cust_pick:
        df_cust = df[df["รหัสลูกค้า"] == cust_pick].sort_values("วันที่", ascending=False)
        df_cust_show = df_cust.copy()
        df_cust_show["วันที่"] = df_cust_show["วันที่"].dt.strftime("%-d/%-m/%Y")
        st.dataframe(
            df_cust_show[["วันที่", "รหัสใบส่ง", "จำนวนชิ้น", "รวมเป็นเงิน", "สถานะ"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "รวมเป็นเงิน": st.column_config.NumberColumn(format="%.2f"),
                "จำนวนชิ้น": st.column_config.NumberColumn(format="%d"),
            },
        )
