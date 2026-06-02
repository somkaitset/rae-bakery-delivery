# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Streamlit app for a Thai bakery ("เรเบเกอรี่") that records and prints delivery bills for products sent to schools. The UI, page titles, and all data column names are in **Thai** — preserve Thai strings exactly (column-name keys like `"รหัสลูกค้า"` are dictionary lookups against the Google Sheet headers; a typo silently returns empty).

## Commands

```bash
# Run (dev) — http://localhost:8501
.venv/bin/streamlit run app.py

# Generate a bcrypt hash to paste into auth_config.yaml (one positional arg)
.venv/bin/python scripts/gen_password.py "the-password"

# Deploy on Proxmox LXC
deploy/install.sh     # first-time provision (apt, venv, Tailscale, systemd)
deploy/update.sh      # git pull --ff-only + pip upgrade + systemctl restart rae-bakery
```

There is **no test suite or linter configured** — `tests/` is an empty package and there is no CI. `.pytest_cache/`/`.ruff_cache/`/`.mypy_cache/` appear in `.gitignore` as conventions, but none are wired up. Don't claim tests pass; there are none to run.

## Architecture

**The Google Sheet IS the database.** There is no SQL/ORM. `lib/sheets.py` wraps `gspread` and every "table" is a worksheet tab, mapped from an English key to its Thai name in `lib.config.TABS` (e.g. `"customer"` → `"ลูกค้า"`). Always go through `_ws(tab_key)` / the convenience wrappers (`sheets.customers()`, `sheets.products()`, etc.) rather than hard-coding tab names.

Layered design:
- **`lib/config.py`** — single source of env/config (loads `.env`), the `TABS` mapping, and tunables (`IMAGES_DIR`, `IMAGE_MAX_SIDE`, `SHEETS_CACHE_TTL`). Import config from here, never re-read env elsewhere.
- **`lib/sheets.py`** — raw CRUD on tabs + reads. Reads are cached with `@st.cache_data(ttl=SHEETS_CACHE_TTL)`; **every write calls `_invalidate()`** so the next read is fresh. `bills.py` mutations additionally call `sheets.clear_caches()`.
- **`lib/bills.py`** — domain logic on top of `sheets`: ID generators (`next_bill_id` → `D0001`, `next_product_code` maps price-group→`P1xx/P2xx/...`), Thai date parse/format (`d/m/yyyy`, no leading zero), price lookups, totals, `suggest_qty` (7-day sales avg minus latest stock), and the create/update/delete operations. **Pages should call `bills.*` for anything beyond a plain read.** Read-once-pass-down: functions accept optional pre-loaded row lists to avoid re-fetching inside loops.
- **`lib/storage.py`**, **`lib/pdf.py`**, **`lib/auth.py`** — image storage, PDF rendering, authentication (below).
- **`lib/models.py`** — dataclasses documenting each tab's shape. They are *reference only*; the live code passes raw `dict`s keyed by Thai headers, not these instances.
- **`pages/N_emoji_name.py`** — Streamlit auto-multipage. Each page re-inserts repo root on `sys.path` (the `ROOT = Path(...).parent.parent; sys.path.insert` block) so `from lib import ...` works, then calls `require_auth()` first thing.

### Things that will bite you

- **`lib/drive.py` is dead code.** Image storage moved to **local disk** (`lib/storage.py`) because the Service Account has no Drive quota (`403 storageQuotaExceeded`) and a personal Gmail can't use a Shared Drive. The Sheet stores only the **bare filename**; `storage.image_src()` resolves it under `IMAGES_DIR` at render time, so moving machines only needs a new `IMAGES_DIR` env. `storage.image_src()` still passes through old `http(s)://` Drive URLs for backward compatibility. **The README still says "File storage: Google Drive" — that is outdated.**
- **`BillLines` is a derived tab, not written by the app.** `bills.create_bill()` writes `bill` + `bill_item` rows only. The `BillLines` tab (aggregated by price group) is computed by a **formula inside the Google Sheet** and the PDF (`lib/pdf.py` via `bills.lines_for_bill`) reads from it. Hence the eventual-consistency lag the UI warns about ("รอ ~5 วินาที"). Don't try to populate `BillLines` from Python.
- **Boolean columns are strings.** Sheet "checkbox" values come back as `"TRUE"`/`"FALSE"`/`True`/`1`. Use the existing tolerant checks (`active_customers()` filter, `_normalize_active()`, `bills._to_float()`) instead of truthiness.
- **`save_image()` re-encodes to JPEG** (EXIF-rotate, downscale to `IMAGE_MAX_SIDE`, quality `IMAGE_JPEG_QUALITY`) and returns the final filename — the extension you pass in is not authoritative.
- **Image processing in caves.** Mobile uploads can be 3–5 MB; the downscale keeps the Sheet/disk light. If you change image limits, do it via env in `config.py`.
- Page 5 (สินค้า) uses **`session_state` as a router** (`prod_edit_code`) instead of `st.tabs`, because tabs can't be switched programmatically. Follow that pattern (`_go_edit`/`_go_gallery` + `st.rerun()`) for click-to-edit flows.

### Auth

`streamlit-authenticator` (bcrypt) loaded from `auth_config.yaml`. The `Authenticate` instance lives in `st.session_state` (NOT `@st.cache_resource` — that triggers `CachedWidgetWarning` and duplicate `CookieManager` keys). `app.py` calls `login_or_stop()`; **every page calls `require_auth()`** (or `require_role("admin", ...)`) as its first statement.

## Config & secrets (all git-ignored)

`.env` (see `.env.example`), `auth_config.yaml` (see `.example`), `secrets/service_account.json`, and the Thai PDF fonts `secrets/Sarabun-Regular.ttf` + `Sarabun-Bold.ttf` (without them, PDF Thai text renders as boxes — `lib/pdf.py` falls back to Helvetica). `data/` (local images) and `certs/` (self-signed TLS) are also ignored.

## Deployment notes

Runs as the `rae-bakery` systemd service on a Proxmox LXC, reached over Tailscale. `.streamlit/config.toml` disables XSRF/CORS and binds `0.0.0.0:8501` for LAN/mobile access; TLS is terminated upstream (Nginx Proxy Manager) — the camera/`getUserMedia` secure-context requirement is why HTTPS matters. Persistent image volume should be set via `IMAGES_DIR` to a path covered by Proxmox backups.

## Git workflow

`main` is production — never commit to it directly. Branch as `feature/<name>` (or `hotfix/<name>`), use Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `perf:`), PR → merge. Full convention in `docs/git_workflow.md`.
