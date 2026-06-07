"""
Loader for billing_config.yaml — static shop + per-customer data for the
billing documents (ใบแจ้งหนี้ / ใบเสร็จรับเงิน).

This file is git-ignored (like auth_config.yaml) because it holds tax ids, a bank
account number and personal names. Copy billing_config.example.yaml to
billing_config.yaml and fill in the real values.

Shape:
    shop:
      name, address, tax_id, signatory
      bank: {account_name, bank_name, account_no}
    customers:
      <customer_code>:
        company_name, tax_id, branch, billing_address

No streamlit/gspread import -> headless-safe + testable. Missing file returns
empty dicts so the app can show a friendly "fill in billing_config.yaml" notice
instead of crashing.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from lib import config

# Cache the parsed YAML keyed by (path, mtime) so edits are picked up without a
# restart but we don't re-read on every Streamlit rerun.
_cache: dict | None = None
_cache_key: tuple[str, float] | None = None


def _load() -> dict:
    global _cache, _cache_key
    path = Path(config.BILLING_CONFIG_PATH)
    if not path.exists():
        return {}
    key = (str(path), path.stat().st_mtime)
    if key != _cache_key:
        with open(path, encoding="utf-8") as f:
            _cache = yaml.safe_load(f) or {}
        _cache_key = key
    return _cache or {}


def config_exists() -> bool:
    return Path(config.BILLING_CONFIG_PATH).exists()


def shop() -> dict:
    """Shop-side block (name/address/tax_id/bank/signatory). {} if unset."""
    return _load().get("shop") or {}


def customer_billing(code: str) -> dict:
    """Per-customer billing block for a customer code. {} if not configured."""
    return (_load().get("customers") or {}).get(code) or {}


def billing_customer_codes() -> list[str]:
    """Customer codes that have a billing entry — drives the page's selector."""
    return list((_load().get("customers") or {}).keys())
