"""English column key -> Thai display label (UI boundary). Phase 2."""
from __future__ import annotations

from lib import schema


def thai_columns(tab_key: str) -> dict[str, str]:
    """{english_col: thai_label} for renaming display DataFrames back to Thai."""
    return {eng: thai for eng, thai in schema.COLUMNS[tab_key]}
