"""
Billing documents (ใบวางบิล) — invoices (ใบแจ้งหนี้) + receipts (ใบเสร็จรับเงิน).

A billing document aggregates ONE customer's delivery bills over a date range
into per-day totals (one table row per delivery day). Amounts are NOT snapshotted:
``day_lines`` recomputes from ``bill``/``bill_item`` every time, so a reprint
reflects the current bills. The invoice/receipt tables therefore store only the
document record (number, customer, period, status) — see lib/schema.py.

A receipt is always issued FROM an existing invoice: it copies the invoice's
customer + period, references its number, and flips the invoice to "ชำระแล้ว".
"""
from __future__ import annotations

from datetime import date

from lib import bills, sheets


# Bill statuses that count as billable (delivered). Drafts ("ร่าง") are excluded:
# a draft has not been delivered yet, so it must not appear on an invoice.
BILLABLE_STATUSES: tuple[str, ...] = ("ส่งแล้ว",)

PAYMENT_METHODS: tuple[str, ...] = ("เงินสด", "โอนเข้าบัญชีธนาคาร")

INVOICE_STATUS_UNPAID = "ค้างชำระ"
INVOICE_STATUS_PAID = "ชำระแล้ว"


# --- Aggregation -----------------------------------------------------------

def day_lines(
    customer_code: str,
    start: date,
    end: date,
    bills_rows: list[dict] | None = None,
    items_rows: list[dict] | None = None,
    statuses: tuple[str, ...] = BILLABLE_STATUSES,
) -> list[dict]:
    """Per-day billable totals for one customer over [start, end] (inclusive).

    Returns a list (sorted by date) of {"date", "date_str", "amount"}, one entry
    per day that has at least one billable bill summing to > 0. Pass statuses=()
    to count every status regardless of สถานะ.
    """
    bills_rows = bills_rows if bills_rows is not None else sheets.bills()
    items_rows = items_rows if items_rows is not None else sheets.bill_items()

    allowed = set(statuses) if statuses else None
    totals: dict[date, float] = {}
    for b in bills_rows:
        if str(b.get("customer_code", "")) != customer_code:
            continue
        if allowed is not None and str(b.get("status", "")) not in allowed:
            continue
        d = bills.parse_date(b.get("date"))
        if d is None or d < start or d > end:
            continue
        amt = bills.bill_total(str(b.get("bill_id", "")), items_rows)
        if amt:
            totals[d] = totals.get(d, 0.0) + amt

    return [
        {"date": d, "date_str": bills.fmt_date(d), "amount": totals[d]}
        for d in sorted(totals)
        if totals[d] > 0
    ]


def grand_total(lines: list[dict]) -> float:
    return sum(ln["amount"] for ln in lines)


# --- Number generators (reset per calendar year) ---------------------------

def _max_seq_for_prefix(rows: list[dict], key_field: str, prefix: str) -> int:
    """Highest trailing sequence among IDs shaped '{prefix}{seq:04d}'. 0 if none."""
    n = 0
    for r in rows:
        rid = str(r.get(key_field, ""))
        if rid.startswith(prefix):
            try:
                n = max(n, int(rid[len(prefix):]))
            except ValueError:
                pass
    return n


def next_invoice_no(issue_date: date, existing: list[dict] | None = None) -> str:
    """INV-<year>-#### — sequence resets each calendar year."""
    rows = existing if existing is not None else sheets.invoices()
    prefix = f"INV-{issue_date.year}-"
    return f"{prefix}{_max_seq_for_prefix(rows, 'invoice_no', prefix) + 1:04d}"


def next_receipt_no(issue_date: date, existing: list[dict] | None = None) -> str:
    """RCP-<year>-#### — sequence resets each calendar year."""
    rows = existing if existing is not None else sheets.receipts()
    prefix = f"RCP-{issue_date.year}-"
    return f"{prefix}{_max_seq_for_prefix(rows, 'receipt_no', prefix) + 1:04d}"


# --- Queries ---------------------------------------------------------------

def get_invoice(invoice_no: str, invoices_rows: list[dict] | None = None) -> dict | None:
    rows = invoices_rows if invoices_rows is not None else sheets.invoices()
    return next((r for r in rows if str(r.get("invoice_no", "")) == invoice_no), None)


def get_receipt(receipt_no: str, receipts_rows: list[dict] | None = None) -> dict | None:
    rows = receipts_rows if receipts_rows is not None else sheets.receipts()
    return next((r for r in rows if str(r.get("receipt_no", "")) == receipt_no), None)


def receipt_for_invoice(invoice_no: str, receipts_rows: list[dict] | None = None) -> dict | None:
    """The receipt issued from this invoice, if any (one receipt per invoice)."""
    rows = receipts_rows if receipts_rows is not None else sheets.receipts()
    return next((r for r in rows if str(r.get("invoice_no", "")) == invoice_no), None)


# --- Mutations -------------------------------------------------------------

def create_invoice(
    customer_code: str,
    issue_date: date,
    period_start: date,
    period_end: date,
    note: str = "",
) -> str:
    """Record a new invoice (unpaid). Lines/total are recomputed at render time."""
    existing = sheets.invoices()
    invoice_no = next_invoice_no(issue_date, existing)
    sheets.append("invoice", [
        invoice_no,
        bills.fmt_date(issue_date),
        customer_code,
        bills.fmt_date(period_start),
        bills.fmt_date(period_end),
        INVOICE_STATUS_UNPAID,
        note,
    ])
    sheets.clear_caches()
    return invoice_no


def set_invoice_status(invoice_no: str, status: str) -> None:
    """Rewrite the whole invoice row, changing only its status.

    Builds the full row from the loaded dict (a short list would let _fit_row pad
    the rest to "" and silently drop customer/period — same trap as bills.set_status).
    """
    inv = get_invoice(invoice_no)
    if inv is None:
        raise ValueError(f"invoice not found: {invoice_no}")
    row_number = sheets.find_row_by_key("invoice", invoice_no, key_col=1)
    sheets.update_row("invoice", row_number, [
        inv.get("invoice_no", ""),
        inv.get("issue_date", ""),
        inv.get("customer_code", ""),
        inv.get("period_start", ""),
        inv.get("period_end", ""),
        status,
        inv.get("note", ""),
    ])
    sheets.clear_caches()


def create_receipt(
    invoice_no: str,
    issue_date: date,
    payment_method: str,
    note: str = "",
) -> str:
    """Issue a receipt from an existing invoice: copy its customer + period,
    reference its number, and mark the invoice paid. Returns the receipt_no."""
    inv = get_invoice(invoice_no)
    if inv is None:
        raise ValueError(f"invoice not found: {invoice_no}")
    existing = sheets.receipts()
    receipt_no = next_receipt_no(issue_date, existing)
    sheets.append("receipt", [
        receipt_no,
        invoice_no,
        bills.fmt_date(issue_date),
        str(inv.get("customer_code", "")),
        str(inv.get("period_start", "")),
        str(inv.get("period_end", "")),
        payment_method,
        note,
    ])
    set_invoice_status(invoice_no, INVOICE_STATUS_PAID)
    sheets.clear_caches()
    return receipt_no


def delete_invoice(invoice_no: str) -> None:
    """Delete an invoice. Refuses if a receipt references it (delete that receipt
    first) so a receipt's อ้างถึงใบแจ้งหนี้ is never orphaned."""
    if receipt_for_invoice(invoice_no) is not None:
        raise ValueError("cannot delete an invoice that already has a receipt")
    row_number = sheets.find_row_by_key("invoice", invoice_no, key_col=1)
    if row_number is None:
        return
    sheets.delete_row("invoice", row_number)
    sheets.clear_caches()


def delete_receipt(receipt_no: str) -> None:
    """Delete a receipt and revert its invoice back to unpaid."""
    rcp = get_receipt(receipt_no)
    row_number = sheets.find_row_by_key("receipt", receipt_no, key_col=1)
    if row_number is None:
        return
    sheets.delete_row("receipt", row_number)
    if rcp is not None:
        inv_no = str(rcp.get("invoice_no", ""))
        if inv_no and get_invoice(inv_no) is not None:
            set_invoice_status(inv_no, INVOICE_STATUS_UNPAID)
    sheets.clear_caches()
