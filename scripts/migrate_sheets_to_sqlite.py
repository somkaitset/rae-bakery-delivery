"""
One-time migration: Google Sheets → SQLite

Reads every base tab via gspread (BASE_TABS only — bill_lines is a VIEW,
never migrated), inserts rows into a fresh SQLite file in a single transaction,
and gates the commit behind:

  (a) header-presence  — every REQUIRED_KEYS[tab] must be in live headers
  (b) count parity     — SELECT COUNT(*) == len(records) after INSERT
  (c) duplicate-ID     — warn (do not auto-dedupe)
  (d) price-per-group  — bill_item: warn on multi-หน่วยละ per (bill, group)
  (e) empty-tab        — create table + 0 rows, not fatal

Usage:
    .venv/bin/python scripts/migrate_sheets_to_sqlite.py [--dry-run] [--db-path PATH]

On any FATAL error: exit code 1, DB file not written (or rolled back).
On success:         exit code 0, DB file written.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

# Ensure repo root on sys.path so ``from lib import ...`` works when the script
# is run from any cwd (mirrors the pattern used in pages/).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config, db, schema  # noqa: E402  (after sys.path fixup)


# ---------------------------------------------------------------------------
# Type alias for the injectable fetch callable
# ---------------------------------------------------------------------------
FetchCallable = Callable[[str], tuple[list[str], list[dict]]]


# ---------------------------------------------------------------------------
# Default gspread reader (production path)
# ---------------------------------------------------------------------------

def gspread_fetch(tab_key: str) -> tuple[list[str], list[dict]]:
    """Read one tab from the live Google Sheet.

    Returns:
        (live_headers, records)
        live_headers — row 1 of the worksheet ([] if the sheet is empty)
        records      — worksheet.get_all_records()
    """
    import gspread  # noqa: PLC0415 — migration-only import
    from google.oauth2.service_account import Credentials  # noqa: PLC0415

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_PATH, scopes=scopes
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(config.SHEET_ID)
    thai_tab_name = config.TABS[tab_key]
    ws = sheet.worksheet(thai_tab_name)

    all_values = ws.get_all_values()
    live_headers: list[str] = all_values[0] if all_values else []
    records: list[dict] = ws.get_all_records()
    return live_headers, records


# ---------------------------------------------------------------------------
# Per-tab gate checks (pure — operate on already-fetched data)
# ---------------------------------------------------------------------------

def _check_required_headers(
    tab_key: str, live_headers: list[str]
) -> list[str]:
    """Return list of REQUIRED_KEYS missing from live_headers (empty = OK)."""
    required = schema.REQUIRED_KEYS.get(tab_key, [])
    return [h for h in required if h not in live_headers]


def _check_duplicate_ids(
    tab_key: str, records: list[dict]
) -> list[str]:
    """Return list of duplicate id-column values (first column of COLUMNS[tab])."""
    if not records:
        return []
    id_thai = schema.COLUMNS[tab_key][0][1]  # Thai header of the id column
    seen: set[str] = set()
    dups: list[str] = []
    for rec in records:
        val = str(rec.get(id_thai, ""))
        if val in seen:
            if val not in dups:
                dups.append(val)
        else:
            seen.add(val)
    return dups


def _check_price_consistency(records: list[dict]) -> list[tuple[str, str, int]]:
    """For bill_item: return (bill_id, price_group, distinct_price_count) where count > 1.

    R4 — the VIEW uses MAX so the app won't crash, but real pricing
    inconsistencies must be surfaced here.
    """
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for rec in records:
        bill_id = str(rec.get("รหัสใบส่ง", ""))
        group = str(rec.get("กลุ่มราคา", ""))
        price = str(rec.get("หน่วยละ", ""))
        groups[(bill_id, group)].add(price)
    return [
        (bill_id, grp, len(prices))
        for (bill_id, grp), prices in groups.items()
        if len(prices) > 1
    ]


# ---------------------------------------------------------------------------
# Build insert rows from records (maps by Thai header name, not position)
# ---------------------------------------------------------------------------

def _build_insert_rows(tab_key: str, records: list[dict]) -> list[list[str]]:
    """Map each record to a positional value list matching COLUMNS[tab_key].

    Looks up each column by Thai header name from the record dict, so live
    column reordering in the Sheet does not corrupt the SQLite insert.
    Falls back to "" for any header not present in the record.
    """
    col_thais = [thai for _, thai in schema.COLUMNS[tab_key]]
    return [
        [str(rec.get(thai, "")) for thai in col_thais]
        for rec in records
    ]


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _fmt_row(
    tab_key: str,
    live_header_count: int,
    required_ok: bool,
    missing_keys: list[str],
    record_count: int,
    dup_ids: list[str],
    price_issues: list[tuple[str, str, int]],
    status: str,
) -> str:
    missing_str = (", ".join(missing_keys) if missing_keys else "—")
    dup_str = (", ".join(dup_ids[:5]) + ("..." if len(dup_ids) > 5 else "")) if dup_ids else "—"
    price_str = str(len(price_issues)) if price_issues else "—"
    req_str = "OK" if required_ok else f"MISSING: {missing_str}"
    return (
        f"  {tab_key:<12} | headers={live_header_count:>3} | required={req_str:<40} "
        f"| rows={record_count:>5} | dup_ids={dup_str:<30} | price_issues={price_str} | {status}"
    )


def _print_report(rows: list[str]) -> None:
    print()
    print("=" * 120)
    print("  Migration report")
    print("=" * 120)
    for row in rows:
        print(row)
    print("=" * 120)


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------

def migrate(
    fetch: FetchCallable = gspread_fetch,
    db_path: str | Path | None = None,
    dry_run: bool = False,
) -> int:
    """Migrate all BASE_TABS from the Sheet into a fresh SQLite file.

    Args:
        fetch:    Callable (tab_key) -> (live_headers, records). Inject a fake
                  for tests; defaults to gspread_fetch for production.
        db_path:  Path to the SQLite file. Defaults to config.DB_PATH.
        dry_run:  If True, print the full report but do NOT write the DB.

    Returns:
        0 on success, 1 on any FATAL error.
    """
    resolved_path = Path(db_path) if db_path is not None else config.DB_PATH

    print(f"[migrate] db_path  = {resolved_path}")
    print(f"[migrate] dry_run  = {dry_run}")
    print(f"[migrate] tabs     = {schema.BASE_TABS}")

    # ------------------------------------------------------------------
    # Phase 1: fetch all tabs + run gates (no DB writes yet)
    # ------------------------------------------------------------------
    tab_data: dict[str, tuple[list[str], list[dict], list[list[str]]]] = {}
    report_rows: list[str] = []
    has_fatal = False

    for tab_key in schema.BASE_TABS:
        print(f"[migrate] fetching {tab_key!r} ...")
        try:
            live_headers, records = fetch(tab_key)
        except Exception as exc:
            print(f"[FATAL] {tab_key}: fetch failed — {exc}")
            has_fatal = True
            report_rows.append(
                _fmt_row(tab_key, 0, False, [], 0, [], [], "FATAL (fetch error)")
            )
            continue

        # Gate (a): required headers
        missing_keys = _check_required_headers(tab_key, live_headers)
        required_ok = len(missing_keys) == 0
        if missing_keys:
            has_fatal = True

        # Gate (c): duplicate IDs (warn only)
        dup_ids = _check_duplicate_ids(tab_key, records)

        # Gate (d): price consistency on bill_item (warn only)
        price_issues: list[tuple[str, str, int]] = []
        if tab_key == "bill_item":
            price_issues = _check_price_consistency(records)

        # Build insert rows (mapped by Thai header name)
        insert_rows = _build_insert_rows(tab_key, records)
        tab_data[tab_key] = (live_headers, records, insert_rows)

        status = "FATAL (missing required headers)" if missing_keys else (
            "WARN (duplicates)" if dup_ids else (
                "WARN (price inconsistency)" if price_issues else (
                    "empty (ok)" if not records else "OK"
                )
            )
        )

        report_rows.append(
            _fmt_row(
                tab_key,
                len(live_headers),
                required_ok,
                missing_keys,
                len(records),
                dup_ids,
                price_issues,
                status,
            )
        )

        # Verbose warnings (always printed, not just in dry-run)
        if dup_ids:
            print(f"  [WARN] {tab_key}: duplicate id-column values: {dup_ids}")
        if price_issues:
            for bill_id, grp, cnt in price_issues:
                print(
                    f"  [WARN] bill_item: bill={bill_id!r} group={grp!r} "
                    f"has {cnt} distinct หน่วยละ values (VIEW uses MAX)"
                )

    _print_report(report_rows)

    if has_fatal:
        print("\n[FAIL] FATAL errors found — DB will NOT be written.")
        return 1

    if dry_run:
        print("\n[dry-run] No DB written. All gates passed.")
        return 0

    # ------------------------------------------------------------------
    # Phase 2: write DB (only if no FATAL and not dry-run)
    # ------------------------------------------------------------------

    # Idempotency: remove any existing file, then build fresh.
    if resolved_path.exists():
        print(f"[migrate] removing existing DB: {resolved_path}")
        resolved_path.unlink()

    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    conn = db.connect(str(resolved_path))
    db.init_db(conn)

    # All inserts in a single transaction; rollback on count-parity failure.
    parity_ok = True
    try:
        conn.execute("BEGIN")
        for tab_key in schema.BASE_TABS:
            if tab_key not in tab_data:
                # fetch failed for this tab — already recorded as FATAL above
                continue
            _, records, insert_rows = tab_data[tab_key]

            if insert_rows:
                cols = ", ".join(
                    f'"{eng}"' for eng in schema.english_columns(tab_key)
                )
                qs = ", ".join("?" for _ in schema.COLUMNS[tab_key])
                conn.executemany(
                    f'INSERT INTO "{tab_key}" ({cols}) VALUES ({qs})',
                    insert_rows,
                )

            # Gate (b): count parity
            count = conn.execute(
                f'SELECT COUNT(*) FROM "{tab_key}"'
            ).fetchone()[0]
            if count != len(records):
                print(
                    f"[FATAL] {tab_key}: count parity FAIL — "
                    f"expected {len(records)}, got {count}"
                )
                parity_ok = False

        if not parity_ok:
            conn.execute("ROLLBACK")
            conn.close()
            print("\n[FAIL] Count parity error — DB rolled back and NOT written.")
            return 1

        conn.execute("COMMIT")
        conn.close()

    except Exception as exc:
        try:
            conn.execute("ROLLBACK")
            conn.close()
        except Exception:
            pass
        print(f"\n[FATAL] Unexpected error during insert: {exc}")
        print("[FAIL] DB rolled back and NOT written.")
        return 1

    print(f"\n[OK] Migration complete — {resolved_path}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Migrate Google Sheets → SQLite (one-time, idempotent). "
            "Re-running recreates the DB from the live Sheet."
        )
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the parity/guard report without writing the DB.",
    )
    p.add_argument(
        "--db-path",
        metavar="PATH",
        default=None,
        help=f"SQLite file path (default: {config.DB_PATH})",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return migrate(
        fetch=gspread_fetch,
        db_path=args.db_path,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
