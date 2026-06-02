"""
SQLite data layer (no Streamlit / no gspread).

Phase 1 backend behind lib/sheets.py. Reads return rows as ``list[dict]`` keyed
by the live Thai headers (NULL -> "" to match gspread's ``get_all_records``).
Writes/edits/deletes preserve the old Google-Sheets *positional* contract:

  - rows are ordered by an autoincrement ``_id`` (monotonic, never reused,
    VACUUM-stable — so "insertion order" is durable)
  - ``row_number`` from the callers is a 1-indexed *sheet* row (header = 1,
    first data row = 2); we translate it to the ``_id`` at offset ``row_number-2``.

Connections are opened per-operation (WAL + busy_timeout). We deliberately do
NOT cache a connection (e.g. via st.cache_resource): Streamlit reruns hop
threads and sqlite3 defaults to check_same_thread=True.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

from lib import config, schema

log = logging.getLogger(__name__)
_init_logged = False


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open a fresh connection with WAL + a busy timeout (per-operation use)."""
    # Read config.DB_PATH at call time so tests can repoint it per-temp-dir.
    path = str(db_path) if db_path is not None else str(config.DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all base tables + the bill_lines VIEW if absent (idempotent)."""
    global _init_logged
    for tab_key in schema.BASE_TABS:
        conn.execute(schema.create_table_sql(tab_key))
    conn.execute(schema.CREATE_BILL_LINES_VIEW)
    conn.commit()
    if not _init_logged:
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        log.info("SQLite ready at %s (journal_mode=%s)", config.DB_PATH, mode)
        _init_logged = True


def ensure_db(db_path: str | None = None) -> sqlite3.Connection:
    """connect() + init_db() in one call."""
    conn = connect(db_path)
    init_db(conn)
    return conn


def _cell(value: Any) -> Any:
    """Match gspread: a blank cell reads back as "" (never None)."""
    return "" if value is None else value


# --- Reads -----------------------------------------------------------------

def all_rows(conn: sqlite3.Connection, tab_key: str) -> list[dict[str, Any]]:
    """Return every row as a dict keyed by the English column name, ordered by _id."""
    pairs = (
        schema.BILL_LINES_COLUMNS
        if tab_key == "bill_lines"
        else schema.COLUMNS[tab_key]
    )
    eng_cols = ", ".join(f'"{eng}"' for eng, _ in pairs)
    order = "" if tab_key == "bill_lines" else " ORDER BY _id"
    rows = conn.execute(f'SELECT {eng_cols} FROM "{tab_key}"{order}').fetchall()
    return [
        {eng: _cell(row[eng]) for eng, _ in pairs}
        for row in rows
    ]


def ordered_ids(conn: sqlite3.Connection, tab_key: str) -> list[int]:
    """The _id values in insertion order — the addressing index for row_number."""
    rows = conn.execute(f'SELECT _id FROM "{tab_key}" ORDER BY _id').fetchall()
    return [r["_id"] for r in rows]


def _id_for_row_number(conn: sqlite3.Connection, tab_key: str, row_number: int) -> int | None:
    """row_number (1-indexed sheet row) -> the _id at data offset row_number-2."""
    offset = row_number - 2
    if offset < 0:
        return None
    ids = ordered_ids(conn, tab_key)
    if offset >= len(ids):
        return None
    return ids[offset]


# --- Writes ----------------------------------------------------------------

def _fit_row(tab_key: str, row: list[Any]) -> list[Any]:
    """Map a positional write list to the tab's data columns.

    Pad-short with "" and reject-overlong (defensive: a longer list means the
    caller and schema disagree, which would silently write into the wrong place).
    """
    n = len(schema.COLUMNS[tab_key])
    if len(row) > n:
        raise ValueError(
            f"{tab_key}: got {len(row)} values for {n} columns (overlong row)"
        )
    fitted = list(row) + [""] * (n - len(row))
    # bool -> stored as TEXT "1"/"0" via affinity (sqlite3 maps bool->int first);
    # leave other types to TEXT affinity.
    return fitted


def append(conn: sqlite3.Connection, tab_key: str, row: list[Any]) -> None:
    cols = ", ".join(f'"{eng}"' for eng in schema.english_columns(tab_key))
    qs = ", ".join("?" for _ in schema.COLUMNS[tab_key])
    conn.execute(
        f'INSERT INTO "{tab_key}" ({cols}) VALUES ({qs})', _fit_row(tab_key, row)
    )
    conn.commit()


def append_many(conn: sqlite3.Connection, tab_key: str, rows: list[list[Any]]) -> None:
    if not rows:
        return
    cols = ", ".join(f'"{eng}"' for eng in schema.english_columns(tab_key))
    qs = ", ".join("?" for _ in schema.COLUMNS[tab_key])
    conn.executemany(
        f'INSERT INTO "{tab_key}" ({cols}) VALUES ({qs})',
        [_fit_row(tab_key, r) for r in rows],
    )
    conn.commit()


def update_row(conn: sqlite3.Connection, tab_key: str, row_number: int, row: list[Any]) -> None:
    target = _id_for_row_number(conn, tab_key, row_number)
    if target is None:
        raise IndexError(f"{tab_key}: no row at row_number={row_number}")
    sets = ", ".join(f'"{eng}"=?' for eng in schema.english_columns(tab_key))
    conn.execute(
        f'UPDATE "{tab_key}" SET {sets} WHERE _id=?',
        [*_fit_row(tab_key, row), target],
    )
    conn.commit()


def delete_row(conn: sqlite3.Connection, tab_key: str, row_number: int) -> None:
    target = _id_for_row_number(conn, tab_key, row_number)
    if target is None:
        raise IndexError(f"{tab_key}: no row at row_number={row_number}")
    conn.execute(f'DELETE FROM "{tab_key}" WHERE _id=?', [target])
    conn.commit()


def find_row_number(
    conn: sqlite3.Connection, tab_key: str, key_value: str, key_col: int = 1
) -> int | None:
    """First match's row_number (offset+2), scanning the 1-indexed key_col.

    Mirrors gspread's ``worksheet.find(key_value, in_column=key_col)``: exact
    string match against the column at position ``key_col-1``, first hit wins.
    """
    pairs = schema.COLUMNS[tab_key]
    if not (1 <= key_col <= len(pairs)):
        return None
    eng = pairs[key_col - 1][0]
    rows = conn.execute(f'SELECT "{eng}" FROM "{tab_key}" ORDER BY _id').fetchall()
    for i, r in enumerate(rows):
        if str(_cell(r[eng])) == str(key_value):
            return i + 2
    return None
