"""
Pytest fixtures for the SQLite-backed data layer.

Every test gets a fresh temp SQLite DB. We repoint ``lib.config.DB_PATH`` (which
``lib.db.connect`` reads at call time) and reset ``lib.db._init_logged`` so the
one-time init log fires per test. No real Streamlit runtime is required:
``sheets.clear_caches()`` soft-imports streamlit and ``st.cache_data.clear()``
no-ops (with a harmless warning) when run headless.
"""
from __future__ import annotations

import pytest

from lib import config, db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Point the data layer at a fresh temp SQLite DB and create the schema.

    Yields a zero-arg helper that (re-)runs ``db.ensure_db()`` against the temp
    path and returns the live connection (caller is responsible for closing it
    if it keeps the handle; the normal ``lib.sheets`` path opens/closes its own).
    Tests then use ``lib.sheets.*`` / ``lib.bills.*`` normally.
    """
    db_file = tmp_path / "app.db"
    monkeypatch.setattr(config, "DB_PATH", db_file)
    # Reset the once-only init log flag so each temp DB logs its own readiness.
    monkeypatch.setattr(db, "_init_logged", False, raising=False)

    def _ensure():
        return db.ensure_db()

    # Create tables + VIEW up front so plain reads work before any write.
    conn = _ensure()
    conn.close()

    yield _ensure
