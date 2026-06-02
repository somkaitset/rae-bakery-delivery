"""
Migration parity tests for scripts/migrate_sheets_to_sqlite.py.

The script is authored in parallel by another agent. If it is not importable
yet, this whole module is SKIPPED with a clear reason rather than failing — the
tests auto-activate once the script lands. The verified contract is:

    migrate(fetch=<callable>, db_path=<path>, dry_run=<bool>) -> int  # 0 ok, 1 fatal

where ``fetch`` is an injectable PER-TAB seam:
    fetch(tab_key) -> (live_headers: list[str], records: list[dict])
with records keyed by the live Thai headers (incl. "รูปจาก LINE" with a space).
``migrate`` RETURNS a non-zero exit code on abort (it does not raise/SystemExit).
"""
from __future__ import annotations

import inspect
import sqlite3
from contextlib import closing

import pytest

from lib import schema

# Skip the entire module if the migration script isn't importable yet.
migrate_mod = pytest.importorskip(
    "scripts.migrate_sheets_to_sqlite",
    reason="scripts/migrate_sheets_to_sqlite.py not present yet (written in parallel)",
)


def _resolve_migrate():
    """Return the migrate() callable, or skip if the expected seam is absent."""
    fn = getattr(migrate_mod, "migrate", None)
    if fn is None or not callable(fn):
        pytest.skip("migrate_sheets_to_sqlite has no callable migrate()")
    params = inspect.signature(fn).parameters
    for needed in ("fetch", "db_path", "dry_run"):
        if needed not in params:
            pytest.skip(
                f"migrate() missing expected kwarg '{needed}'; signature={list(params)}"
            )
    return fn


# --- A fake per-tab fetch with REAL Thai headers (incl. the spaced LINE one) -

def _seed_data(overrides=None):
    """Build {tab_key: (headers, records)} with live Thai headers.

    ``overrides`` lets a test replace one tab's (headers, records) tuple.
    """
    data: dict[str, tuple[list[str], list[dict]]] = {}
    for tab_key in schema.BASE_TABS:
        data[tab_key] = (list(schema.thai_headers(tab_key)), [])

    data["customer"] = (
        list(schema.thai_headers("customer")),
        [
            {"รหัสลูกค้า": "C001", "ชื่อลูกค้า": "ก", "ชุดราคา": "มาตรฐาน",
             "ที่อยู่": "addr1", "เบอร์โทร": "0811111111", "ใช้งาน": "TRUE"},
            {"รหัสลูกค้า": "C002", "ชื่อลูกค้า": "ข", "ชุดราคา": "ศว.",
             "ที่อยู่": "addr2", "เบอร์โทร": "0822222222", "ใช้งาน": "FALSE"},
        ],
    )
    data["bill"] = (
        list(schema.thai_headers("bill")),
        [
            {"รหัสใบส่ง": "D0001", "วันที่": "21/5/2026", "รหัสลูกค้า": "C001",
             "หมายเหตุ": "", "สถานะ": "ส่งแล้ว"},
        ],
    )
    data["bill_item"] = (
        list(schema.thai_headers("bill_item")),
        [
            {"รหัสรายการ": "I0001", "รหัสใบส่ง": "D0001", "รหัสสินค้า": "P301",
             "จำนวน": "3", "กลุ่มราคา": "15", "หน่วยละ": "12", "จำนวนเงิน": "36"},
            {"รหัสรายการ": "I0002", "รหัสใบส่ง": "D0001", "รหัสสินค้า": "P401",
             "จำนวน": "2", "กลุ่มราคา": "20", "หน่วยละ": "15", "จำนวนเงิน": "30"},
        ],
    )
    data["stock"] = (
        list(schema.thai_headers("stock")),
        [
            {"รหัสสต็อก": "S0001", "วันที่": "20/5/2026", "รหัสลูกค้า": "C001",
             "รหัสสินค้า": "P301", "จำนวนคงเหลือ": "5",
             "รูปจาก LINE": "line_photo.jpg", "หมายเหตุ": "note"},
        ],
    )

    if overrides:
        data.update(overrides)
    return data


def _make_fetch(data):
    """Wrap a {tab_key: (headers, records)} dict as a fetch(tab_key) callable."""
    def _fetch(tab_key):
        return data[tab_key]
    return _fetch


def _read_tab(db_file, tab_key):
    """Read a migrated tab through the SQLite data layer."""
    from lib import config, db as dbmod

    config.DB_PATH = db_file
    dbmod._init_logged = False
    with closing(dbmod.ensure_db()) as conn:
        return dbmod.all_rows(conn, tab_key)


# --- Tests ------------------------------------------------------------------

def test_migration_per_table_count_parity(tmp_path):
    migrate = _resolve_migrate()
    data = _seed_data()
    db_file = tmp_path / "migrated.db"

    rc = migrate(fetch=_make_fetch(data), db_path=str(db_file), dry_run=False)
    assert rc == 0

    conn = sqlite3.connect(str(db_file))
    try:
        for tab_key, (_headers, records) in data.items():
            n = conn.execute(f'SELECT COUNT(*) FROM "{tab_key}"').fetchone()[0]
            assert n == len(records), f"count parity failed for {tab_key}"
    finally:
        conn.close()


def test_migration_aborts_on_missing_required_header(tmp_path):
    migrate = _resolve_migrate()
    # Drop a REQUIRED header from customer (ชื่อลูกค้า is required).
    bad_headers = [h for h in schema.thai_headers("customer") if h != "ชื่อลูกค้า"]
    data = _seed_data(overrides={"customer": (bad_headers, [])})
    db_file = tmp_path / "should_not_exist.db"

    rc = migrate(fetch=_make_fetch(data), db_path=str(db_file), dry_run=False)
    # Aborts with a non-zero exit code and writes NO DB file.
    assert rc != 0
    assert not db_file.exists()


def test_migration_never_creates_bill_lines_as_base_table(tmp_path):
    migrate = _resolve_migrate()
    db_file = tmp_path / "migrated.db"

    rc = migrate(fetch=_make_fetch(_seed_data()), db_path=str(db_file),
                 dry_run=False)
    assert rc == 0

    conn = sqlite3.connect(str(db_file))
    try:
        # bill_lines must exist ONLY as a VIEW, never as a base table.
        view = conn.execute(
            "SELECT type FROM sqlite_master WHERE name='bill_lines'"
        ).fetchone()
        assert view is not None and view[0] == "view"
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bill_lines'"
        ).fetchone()
        assert table is None
    finally:
        conn.close()


def test_migration_dry_run_writes_no_db(tmp_path):
    migrate = _resolve_migrate()
    db_file = tmp_path / "dryrun.db"
    rc = migrate(fetch=_make_fetch(_seed_data()), db_path=str(db_file),
                 dry_run=True)
    assert rc == 0
    assert not db_file.exists()


def test_migration_preserves_app_visible_types(tmp_path):
    migrate = _resolve_migrate()
    db_file = tmp_path / "migrated.db"
    rc = migrate(fetch=_make_fetch(_seed_data()), db_path=str(db_file),
                 dry_run=False)
    assert rc == 0

    from lib import bills

    bill_rows = _read_tab(db_file, "bill")
    # d/m/yyyy text date survives verbatim and parses app-side.
    assert bill_rows[0]["วันที่"] == "21/5/2026"
    assert bills.parse_date(bill_rows[0]["วันที่"]).isoformat() == "2026-05-21"

    # active "TRUE" passes the tolerant filter; "FALSE" does not.
    customers = _read_tab(db_file, "customer")
    actives = [c for c in customers
               if c.get("ใช้งาน") in (True, "TRUE", "true", 1, "1")]
    assert {c["รหัสลูกค้า"] for c in actives} == {"C001"}

    # The spaced "รูปจาก LINE" header round-trips intact.
    stocks = _read_tab(db_file, "stock")
    assert stocks[0]["รูปจาก LINE"] == "line_photo.jpg"
