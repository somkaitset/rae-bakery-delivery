"""
Bill operations + ID generators + price lookup + date helpers
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from lib import sheets


# --- Date helpers ---

def fmt_date(d: date) -> str:
    """date → 'd/m/yyyy' (เหมือนใน Sheet — ไม่มี leading zero)"""
    return f"{d.day}/{d.month}/{d.year}"


def parse_date(s: str | Any) -> date | None:
    """'21/5/2026' → date(2026, 5, 21). คืน None ถ้า parse ไม่ได้."""
    if not s:
        return None
    s = str(s).strip()
    # ลอง d/m/yyyy
    for sep in ("/", "-"):
        if sep in s:
            try:
                parts = s.split(sep)
                if len(parts) == 3:
                    d, m, y = parts
                    if int(y) < 100:
                        y = int(y) + 2000
                    return date(int(y), int(m), int(d))
            except (ValueError, IndexError):
                pass
    # ลอง iso
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


# --- ID generators ---

def _max_seq(rows: list[dict], key_field: str, prefix: str) -> int:
    """หาเลข sequence สูงสุดของ ID ที่ขึ้นต้นด้วย prefix."""
    nums = []
    for row in rows:
        rid = str(row.get(key_field, ""))
        if rid.startswith(prefix):
            try:
                nums.append(int(rid[len(prefix):]))
            except ValueError:
                pass
    return max(nums) if nums else 0


def next_bill_id(existing_bills: list[dict] | None = None) -> str:
    bs = existing_bills if existing_bills is not None else sheets.bills()
    return f"D{_max_seq(bs, 'รหัสใบส่ง', 'D') + 1:04d}"


def next_item_seq(existing_items: list[dict] | None = None) -> int:
    """คืนเลข seq ถัดไป (ใช้ format ภายหลัง: f'I{seq:04d}')"""
    items = existing_items if existing_items is not None else sheets.bill_items()
    return _max_seq(items, 'รหัสรายการ', 'I') + 1


def next_customer_code(existing_customers: list[dict] | None = None) -> str:
    cs = existing_customers if existing_customers is not None else sheets.customers()
    return f"C{_max_seq(cs, 'รหัสลูกค้า', 'C') + 1:03d}"


def next_product_code(price_group: str, existing_products: list[dict] | None = None) -> str:
    """
    P{group_digit}{seq:02d} เช่น P104 (กลุ่ม 10 ตัวที่ 4), P314 (กลุ่ม 15 ตัวที่ 14)
    """
    ps = existing_products if existing_products is not None else sheets.products()
    prefix_map = {
        "10": "P1", "12": "P2", "15": "P3", "20": "P4",
        "25": "P5", "30": "P6", "35": "P7",
    }
    prefix = prefix_map.get(str(price_group), "P9")
    nums = []
    for p in ps:
        pc = str(p.get("รหัสสินค้า", ""))
        if pc.startswith(prefix) and len(pc) >= 4:
            try:
                nums.append(int(pc[2:]))
            except ValueError:
                pass
    next_num = (max(nums) if nums else 0) + 1
    return f"{prefix}{next_num:02d}"


def next_stock_id(existing_stocks: list[dict] | None = None) -> str:
    ss = existing_stocks if existing_stocks is not None else sheets.stocks()
    return f"S{_max_seq(ss, 'รหัสสต็อก', 'S') + 1:04d}"


# --- Price lookup ---

def price_map(wholesale_rows: list[dict] | None = None) -> dict[str, float]:
    """
    คืน dict { 'มาตรฐาน-15': 12.0, 'ศว.-20': 15.0, ... }
    cache ได้: ส่ง wholesale_rows เข้ามา ถ้ามีโหลดไว้แล้ว
    """
    rows = wholesale_rows if wholesale_rows is not None else sheets.wholesale_prices()
    return {
        str(r.get("รหัสราคา", "")): _to_float(r.get("ราคาส่ง", 0))
        for r in rows
    }


def unit_price(price_set: str, price_group: str, prices: dict[str, float] | None = None) -> float:
    if prices is None:
        prices = price_map()
    return prices.get(f"{price_set}-{price_group}", 0.0)


# --- Bill totals / queries ---

def bill_total(bill_id: str, items: list[dict] | None = None) -> float:
    items = items if items is not None else sheets.bill_items()
    return sum(
        _to_float(it.get("จำนวนเงิน", 0))
        for it in items
        if str(it.get("รหัสใบส่ง", "")) == bill_id
        and _to_float(it.get("จำนวน", 0)) > 0
    )


def bill_qty_total(bill_id: str, items: list[dict] | None = None) -> int:
    items = items if items is not None else sheets.bill_items()
    return sum(
        int(_to_float(it.get("จำนวน", 0)))
        for it in items
        if str(it.get("รหัสใบส่ง", "")) == bill_id
    )


def lines_for_bill(bill_id: str, bill_lines_rows: list[dict] | None = None) -> list[dict]:
    """คืน BillLines (สรุปตามกลุ่มราคา) สำหรับใบนี้"""
    rows = bill_lines_rows if bill_lines_rows is not None else sheets.bill_lines()
    return [r for r in rows if str(r.get("รหัสใบส่ง", "")) == bill_id]


# --- Mutations ---

def create_bill(
    customer_code: str,
    bill_date: date,
    items_qty: dict[str, int],  # { product_code: qty }
    note: str = "",
    status: str = "ร่าง",
) -> str:
    """
    เขียน 1 แถวใน 'ใบส่งสินค้า' + แถวใน 'รายการสินค้า' (เฉพาะ qty > 0)
    คืน รหัสใบส่ง ที่สร้าง
    """
    # โหลดข้อมูลที่จำเป็นครั้งเดียว
    existing_bills = sheets.bills()
    existing_items = sheets.bill_items()
    customers = {c.get("รหัสลูกค้า"): c for c in sheets.customers()}
    products = {p.get("รหัสสินค้า"): p for p in sheets.products()}
    prices = price_map()

    bill_id = next_bill_id(existing_bills)
    price_set = customers.get(customer_code, {}).get("ชุดราคา", "มาตรฐาน")

    # bill row
    sheets.append("bill", [
        bill_id,
        fmt_date(bill_date),
        customer_code,
        note,
        status,
    ])

    # item rows (batch)
    next_seq = next_item_seq(existing_items)
    new_item_rows = []
    for product_code, qty in items_qty.items():
        if qty <= 0:
            continue
        prod = products.get(product_code, {})
        price_group = str(prod.get("กลุ่มราคา", ""))
        unit = unit_price(price_set, price_group, prices)
        amount = qty * unit
        new_item_rows.append([
            f"I{next_seq:04d}",
            bill_id,
            product_code,
            qty,
            price_group,
            unit,
            amount,
        ])
        next_seq += 1

    if new_item_rows:
        sheets.append_many("bill_item", new_item_rows)

    sheets.clear_caches()
    return bill_id


def delete_bill(bill_id: str) -> int:
    """
    ลบ bill + items ทั้งหมดของ bill_id นี้
    คืนจำนวนแถวที่ลบ
    """
    deleted = 0

    # delete items (reverse order to preserve row numbers)
    items = sheets.bill_items()
    item_rows = [
        i + 2  # row 1 = header, +2 because enumerate starts 0
        for i, it in enumerate(items)
        if str(it.get("รหัสใบส่ง", "")) == bill_id
    ]
    for row_num in sorted(item_rows, reverse=True):
        sheets.delete_row("bill_item", row_num)
        deleted += 1

    # delete bill
    bills_data = sheets.bills()
    for i, b in enumerate(bills_data):
        if str(b.get("รหัสใบส่ง", "")) == bill_id:
            sheets.delete_row("bill", i + 2)
            deleted += 1
            break

    sheets.clear_caches()
    return deleted


# --- Customer / Product / Stock mutations ---

def create_customer(name: str, price_set: str, address: str = "", phone: str = "") -> str:
    code = next_customer_code()
    sheets.append("customer", [code, name, price_set, address, phone, True])
    sheets.clear_caches()
    return code


def update_customer(row_number: int, code: str, name: str, price_set: str,
                    address: str, phone: str, active: bool) -> None:
    sheets.update_row("customer", row_number,
                      [code, name, price_set, address, phone, active])
    sheets.clear_caches()


def create_product(name: str, price_group: str, image_url: str = "",
                   display_order: int = 0, active: bool = True) -> str:
    code = next_product_code(price_group)
    if display_order == 0:
        existing = sheets.products()
        display_order = max(
            (int(_to_float(p.get("ลำดับแสดง", 0))) for p in existing),
            default=0,
        ) + 1
    sheets.append("product",
                  [code, name, price_group, image_url, display_order, active])
    sheets.clear_caches()
    return code


def update_product(row_number: int, code: str, name: str, price_group: str,
                   image_url: str, display_order: int, active: bool) -> None:
    sheets.update_row("product", row_number,
                      [code, name, price_group, image_url, display_order, active])
    sheets.clear_caches()


def delete_product(row_number: int) -> None:
    """ลบสินค้า 1 แถวออกจากชีต (row_number = 1-indexed sheet row)."""
    sheets.delete_row("product", row_number)
    sheets.clear_caches()


def create_stock(stock_date: date, customer_code: str, product_code: str,
                 remaining: int, image_url: str = "", note: str = "") -> str:
    sid = next_stock_id()
    sheets.append("stock", [
        sid,
        fmt_date(stock_date),
        customer_code,
        product_code,
        remaining,
        image_url,
        note,
    ])
    sheets.clear_caches()
    return sid


# --- Suggest qty (avg over last N days minus latest stock) ---

def suggest_qty(
    customer_code: str,
    product_code: str,
    days: int = 7,
    stock_max_age_days: int = 2,
    items: list[dict] | None = None,
    bills: list[dict] | None = None,
    stocks: list[dict] | None = None,
) -> int:
    """
    ตัวเลขแนะนำ:
      max(0, round(avg(qty 7 วันล่าสุดของลูกค้านี้×สินค้านี้)) - สต็อกล่าสุด)
    """
    items = items if items is not None else sheets.bill_items()
    bills = bills if bills is not None else sheets.bills()
    stocks = stocks if stocks is not None else sheets.stocks()

    today = date.today()
    cutoff_sales = today.toordinal() - days
    cutoff_stock = today.toordinal() - stock_max_age_days

    bill_to_cust = {}
    bill_to_date = {}
    for b in bills:
        bid = str(b.get("รหัสใบส่ง", ""))
        bill_to_cust[bid] = str(b.get("รหัสลูกค้า", ""))
        d = parse_date(b.get("วันที่"))
        if d:
            bill_to_date[bid] = d.toordinal()

    qtys = []
    for it in items:
        bid = str(it.get("รหัสใบส่ง", ""))
        if bill_to_cust.get(bid) != customer_code:
            continue
        if str(it.get("รหัสสินค้า", "")) != product_code:
            continue
        if bill_to_date.get(bid, 0) < cutoff_sales:
            continue
        q = int(_to_float(it.get("จำนวน", 0)))
        if q > 0:
            qtys.append(q)

    avg_qty = round(sum(qtys) / len(qtys)) if qtys else 0

    latest_stock = 0
    latest_date = -1
    for s in stocks:
        if str(s.get("รหัสลูกค้า", "")) != customer_code:
            continue
        if str(s.get("รหัสสินค้า", "")) != product_code:
            continue
        d = parse_date(s.get("วันที่"))
        if not d:
            continue
        if d.toordinal() < cutoff_stock:
            continue
        if d.toordinal() > latest_date:
            latest_date = d.toordinal()
            latest_stock = int(_to_float(s.get("จำนวนคงเหลือ", 0)))

    return max(0, avg_qty - latest_stock)


# --- Internal ---

def _to_float(x: Any) -> float:
    if x in (None, "", "TRUE", "FALSE", True, False):
        return float(bool(x))
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0
