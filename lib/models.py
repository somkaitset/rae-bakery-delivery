"""
Data models (dataclasses) — สะท้อนโครงสร้างของแต่ละแท็บใน Google Sheet
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class PriceGroup:
    price_group: str  # "10", "12", "15", ...
    retail_price: float = 0.0
    order: int = 0


@dataclass
class Wholesale:
    price_id: str  # "มาตรฐาน-15"
    price_set: str  # "มาตรฐาน" or "ศว."
    price_group: str
    wholesale_price: float = 0.0


@dataclass
class Customer:
    code: str
    name: str
    price_set: str = "มาตรฐาน"  # "มาตรฐาน" or "ศว."
    address: str = ""
    phone: str = ""
    active: bool = True


@dataclass
class Product:
    code: str
    name: str
    price_group: str
    image_url: str = ""
    display_order: int = 0
    active: bool = True


@dataclass
class Bill:
    bill_id: str
    bill_date: date
    customer_code: str
    note: str = ""
    status: str = "ร่าง"  # "ร่าง" or "ส่งแล้ว"


@dataclass
class BillItem:
    item_id: str
    bill_id: str
    product_code: str
    qty: int = 0
    price_group: str = ""
    unit_price: float = 0.0
    amount: float = 0.0


@dataclass
class BillLine:
    line_id: str  # "{bill_id}-{price_group}"
    bill_id: str
    price_group: str
    qty: int
    unit_price: float
    amount: float


@dataclass
class Stock:
    stock_id: str
    stock_date: date
    customer_code: str
    product_code: str
    remaining: int = 0
    image_url: str = ""
    note: str = ""
