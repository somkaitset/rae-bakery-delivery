# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Streamlit app for a Thai bakery ("เรเบเกอรี่") that records and prints delivery bills for products sent to schools. The UI and page titles are in **Thai** — preserve those strings exactly. As of Phase 2, data is keyed internally by **English** column names (`row.get("customer_code")`, not `row.get("รหัสลูกค้า")`); Thai survives only as UI display labels. Key lookups are still `dict.get`, so a wrong key silently returns empty — but the keys are now stable English (see `lib/schema.py` `COLUMNS`).

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

There is a `pytest` suite under `tests/` — run it with `.venv/bin/pytest -q`. No linter or CI is configured. `.pytest_cache/`/`.ruff_cache/`/`.mypy_cache/` appear in `.gitignore` as conventions, but only `pytest` is wired up. Pages are smoke-tested manually (their `require_auth()` + `sys.path` side effects make full import-smoke in pytest brittle).

## Architecture

**SQLite is the single source of truth.** `lib/db.py` + `lib/schema.py` define the schema; `lib/sheets.py` is backed by SQLite (gspread removed from it). The Google Sheet is retired/frozen as a read-only backup; the one-time import is done via `scripts/migrate_sheets_to_sqlite.py`. `lib/schema.py` `COLUMNS` is the single source of truth, mapping each tab's English column ⇄ its Thai header.

**Phase 2 (English keys) is done.** `sheets.*` returns rows as `list[dict]` keyed by **English** column names; `lib/bills.py`, `lib/pdf.py`, and all 5 pages read English keys. **Thai survives only as UI display labels** — widget text inline, and `st.dataframe`/`st.data_editor` headers renamed back to Thai via `lib/labels.py::thai_columns(tab)` (derived from `schema.COLUMNS`). Key lookups are still `dict.get`, so a wrong key returns empty — but the keys are now stable English. Unchanged from Phase 1: positional writes (`append([...])` in schema column order), `update_row`/`delete_row` 1-indexed `row_number`, and `find_row_by_key`. The live Google Sheet (read only by the migration) still has Thai headers — `schema.COLUMNS` maps them.

Layered design:
- **`lib/config.py`** — single source of env/config (loads `.env`), the `TABS` mapping, and tunables (`IMAGES_DIR`, `IMAGE_MAX_SIDE`, `DB_PATH`). Import config from here, never re-read env elsewhere.
- **`lib/schema.py`** — `COLUMNS` dict (per-tab ordered `[(english, thai_header)]` pairs) and `REQUIRED_KEYS` per tab. Column definitions are driven by live Sheet headers, not `models.py` English names. Also holds `CREATE TABLE` DDL and the `bill_lines` `CREATE VIEW`.
- **`lib/db.py`** — `connect()` (WAL + `busy_timeout=5000`, per-operation), `init_db()` (idempotent), `_ordered_ids()`. No `streamlit` or `gspread` imports.
- **`lib/sheets.py`** — same public surface (`customers()`, `products()`, `bills()`, `bill_items()`, `bill_lines()`, `stocks()`, `wholesale_prices()`, `active_customers()`, `active_products()`, `append()`, `update_row()`, `delete_row()`, `find_row_by_key()`), now backed by SQLite via `lib/db.py`. `_invalidate()` and `clear_caches()` call `st.cache_data.clear()` globally (also clears page-level caches). No gspread import.
- **`lib/bills.py`** — domain logic on top of `sheets`: ID generators (`next_bill_id` → `D0001`, `next_product_code` maps price-group→`P1xx/P2xx/...`), Thai date parse/format (`d/m/yyyy`, no leading zero), price lookups, totals, `suggest_qty` (7-day sales avg minus latest stock), and the create/update/delete operations. **Pages should call `bills.*` for anything beyond a plain read.** Read-once-pass-down: functions accept optional pre-loaded row lists to avoid re-fetching inside loops.
- **`lib/storage.py`**, **`lib/pdf.py`**, **`lib/auth.py`** — image storage, PDF rendering, authentication (below).
- **`lib/models.py`** — dataclasses documenting each tab's shape. They are *reference only*; the live code passes raw `dict`s keyed by **English** column names (per Phase 2), not these instances.
- **`pages/N_emoji_name.py`** — Streamlit auto-multipage. Each page re-inserts repo root on `sys.path` (the `ROOT = Path(...).parent.parent; sys.path.insert` block) so `from lib import ...` works, then calls `require_auth()` first thing.

### Things that will bite you

- **`lib/drive.py` is dead code.** Image storage moved to **local disk** (`lib/storage.py`) because the Service Account has no Drive quota (`403 storageQuotaExceeded`) and a personal Gmail can't use a Shared Drive. The Sheet stores only the **bare filename**; `storage.image_src()` resolves it under `IMAGES_DIR` at render time, so moving machines only needs a new `IMAGES_DIR` env. `storage.image_src()` still passes through old `http(s)://` Drive URLs for backward compatibility.
- **`gspread`/`google-auth` are now used ONLY by the one-time migration script** (`scripts/migrate_sheets_to_sqlite.py`). They are not imported anywhere in `lib/` at runtime. `lib/drive.py` remains dead code.
- **`bill_lines` is a SQL VIEW, not a Sheet formula.** `bills.create_bill()` writes `bill` + `bill_item` rows only. `bill_lines` is computed by a `CREATE VIEW` in SQLite (`lib/schema.py`) grouping `bill_item` by `(รหัสใบส่ง, กลุ่มราคา)`. The PDF (`lib/pdf.py` via `bills.lines_for_bill`) reads from it. The ~5s eventual-consistency lag that the old Sheet ARRAYFORMULA caused is gone. Don't try to write `bill_lines` rows from Python — it is a read-only VIEW.
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

## Language policy (Thai / English)

How Claude *communicates* in this repo is user-toggleable; how it *builds* is not. **Default is English.** Thai is opt-in via a flag in `CLAUDE.local.md` (gitignored, personal). **At the start of every session, read `CLAUDE.local.md`:** if it contains `lang: th`, follow the Thai rules below; otherwise (any other value, or the file/flag absent) use English.

**Toggle (trigger phrases).** When the user types one of these, update the `lang:` line in `CLAUDE.local.md` accordingly (create the file with a single `lang:` line if missing) and apply it for the rest of the session:
- Enable Thai → `ไทย`, `พูดไทย`, `ภาษาไทย`, `thai on`
- Back to English → `อังกฤษ`, `พูดอังกฤษ`, `english`, `thai off`

**When `lang: th`, write these in Thai:**
- Chat explanations, summaries, and status updates.
- Clarifying questions, plans/proposals, and interview prompts — any Q&A with the user.
- Bug reports that need the user's action or decision.

**Always English, regardless of the flag** (this is the "code & docs in English" rule):
- Source code, identifiers, comments, and docstrings.
- Documentation files (`README.md`, `CLAUDE.md`, `docs/**`, this file).
- Git commit messages and PR titles/bodies.

**Inside Thai prose, keep verbatim in English:** file paths, code identifiers, shell commands, error messages, and log lines (e.g. `lib/bills.py`, `pytest -q`, `KeyError: 'qty'`). Translate the explanation around them, never the tokens themselves.

**Sub-agents** work and report internally in English (keeps their reasoning sharp and their artifacts English); Claude synthesizes and delivers the user-facing summary in Thai when `lang: th`.

## Coding guidelines

Behavioral guidelines to reduce common LLM coding mistakes (from [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md)). These bias toward caution over speed — for trivial tasks, use judgment.

### 1. Think before coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity first

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

### 4. Goal-driven execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
