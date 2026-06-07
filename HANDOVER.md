# HANDOVER — rae-bakery-delivery

Snapshot for picking up work in a fresh Claude Code session. Last updated **2026-06-04**.

- **Path:** `/home/raebakery/claude_code/project/rae-bakery-delivery`
- **Repo:** https://github.com/somkaitset/rae-bakery-delivery (private, SSH)
- **Stack:** Streamlit (Python 3.13) + **SQLite** (source of truth) + local disk for images & bill PDFs
- **Deploy target:** Proxmox LXC (Debian 12) + Tailscale — **not yet deployed**
- **Local dev:** `192.168.1.170:8501`

> Project memory: `~/.claude/projects/-home-raebakery-claude-code-project-rae-bakery-delivery/memory/` (`MEMORY.md` indexes it).
> Plans/specs: `.omc/plans/` (`delivery-bill-improvements.md`, `sqlite-migration-phase1.md`, `open-questions.md`) and `.omc/specs/`.

---

## Decisions

### D1 — Drop AppSheet, use Streamlit
AppSheet linter false positives, Group-aggregate Preview failures, and Action Parameter behind a paid tier. Cost vs control vs debuggability favored Streamlit.

### D2 — ~~Google Sheet stays as DB~~ → **SQLite is the single source of truth** *(superseded)*
The data store was migrated Google Sheets → **SQLite** (Phase 1, commit `e1749a7`). `lib/db.py` + `lib/schema.py` own the schema; `lib/sheets.py` keeps its public surface but is now backed by SQLite. The live Google Sheet is **retired/frozen** as a read-only backup; the one-time import is `scripts/migrate_sheets_to_sqlite.py`. `gspread`/`google-auth` are imported **only** by that migration script — not at runtime. `DB_PATH` env points at the `.db` (WAL needs local fs — no NFS/CIFS).

### D2b — English keys internally (Phase 2, commit `d62d896`)
`sheets.*` returns rows keyed by **English** column names (`row.get("customer_code")`). Thai survives only as UI display labels (`lib/labels.py::thai_columns`). `lib/schema.py` `COLUMNS` is the single source mapping english ⇄ thai header. Key lookups are still `dict.get` → a wrong key silently returns empty, but keys are now stable English.

### D2c — `bill_lines` is a SQL VIEW (not a Sheet ARRAYFORMULA)
`bills.create_bill()` writes `bill` + `bill_item` rows only. `bill_lines` is a `CREATE VIEW` in `lib/schema.py` grouping `bill_item` by `(bill_id, price_group)`. The PDF reads it via `bills.lines_for_bill`. **Do not write `bill_lines` rows from Python — it's read-only.** The ~5s Sheet eventual-consistency lag is gone.

### D3 — Local disk for images, NOT Google Drive
Service Account on personal Gmail has no Drive quota (`403 storageQuotaExceeded`). `lib/storage.py` writes to `IMAGES_DIR` (env); Sheet/DB stores **basename only**. `lib/drive.py` is **dead code** (kept, not deleted). On Proxmox point `IMAGES_DIR` at a backed-up volume.

### D4 — Images auto-processed on save
`lib/storage.py` EXIF-rotates → flattens RGB → thumbnails to `IMAGE_MAX_SIDE` (1600) → JPEG `IMAGE_JPEG_QUALITY` (85). Mobile 3–5 MB → 100–300 KB.

### D6 — Auth via `streamlit-authenticator` + session_state
`Authenticate` instance stashed in `st.session_state` (NOT `@st.cache_resource` — triggers CachedWidgetWarning + duplicate CookieManager). `app.py` calls `login_or_stop()`; every page calls `require_auth()` first.

### D7 — HTTPS via self-signed cert for LAN
Mobile `getUserMedia` (`st.camera_input`) needs a secure context. `.streamlit/config.toml` enables `sslCertFile`/`sslKeyFile`. `certs/` + `*.pem` gitignored.

### D9 — Click-to-edit pattern (session_state router)
Pages use `session_state` as a router (e.g. `prod_edit_code`, `sel_bill_id`) + `st.rerun()` for click-to-edit, because `st.tabs` can't be switched programmatically.

### D10 — Bill PDF matches the Google Sheet print template *(feature/bill-signature-layout)*
The authoritative layout is the Sheet's own print HTML (`~/Documents/sheet ส่งโรงเรียน/พิมพ์บิล พป..html`) and `ส่งโรงเรียน2022.xlsx` `พิมพ์บิล <customer>` sheets. `lib/pdf.py` matches it: shop name **Charmonman**, headings **Chakra Petch**, body **Sarabun** (role-based `_register_fonts` with graceful fallback to Sarabun→Helvetica); grey `#cccccc` header + total rows; "รวมเป็นเงิน" right-aligned in the รายการ column; **signature drawn at a fixed page-bottom Y via page callback** so it sits in the same place regardless of row count. PDF + HTML renderers share `assemble_lines`/`fmt_int_cell`. Brand spelling is **`เรเบเกอรี่`** — the Sheet's `เรเบอเกอรี่` is a typo, **not** propagated. Decorative fonts live in `secrets/` (gitignored, optional).

### D11 — One PDF file per bill on local disk + status model
`lib/pdf_archive.py` writes `{bill_id}.pdf` under `BILLS_PDF_DIR` (deterministic name, no DB flag). Print flow: draft → generate → archive → `bills.finalize()` (ร่าง→ส่งแล้ว, locks edit); sent w/o file → self-heal; else reuse. `bills.revert_to_draft()` (ส่งแล้ว→ร่าง) deletes the archived PDF so it regenerates. `bills.update_bill` edits drafts only, replacing all items in one transaction (`db.replace_bill_items`).

---

## Done

| Area | Status |
|---|---|
| Path 1–2: 5 pages, image pipeline, auth, deploy artefacts | ✅ (earlier sessions) |
| **SQLite migration** Phase 1 (store) + Phase 2 (English keys) | ✅ `e1749a7`, `d62d896` |
| `develop` integration branch + Thai/English language policy | ✅ |
| **Bill PDF/HTML matches Sheet template + fonts** | ✅ `feature/bill-signature-layout` |
| **Local PDF archive** (1 file/bill) + status model (ร่าง↔ส่งแล้ว) | ✅ same branch |
| **Edit draft bills** + page-1 click-to-edit detail/print/edit | ✅ same branch (closes old R6) |
| Tests: `test_bills_logic`, `test_sheets_sqlite`, `test_migration`, `test_bill_edit`, `test_pdf_bill` | ✅ run `.venv/bin/pytest -q` |

`feature/bill-signature-layout` is 4 commits ahead of `develop` (not yet pushed/PR'd as of this snapshot).

---

## Remaining

### R1 — LAN browser access (carry-over, status unverified this session)
Off-localhost camera needs HTTPS + `ufw allow 8501` (see memory `lan-https-camera-access`). Was being pivoted to self-signed cert (D7). Re-verify on an actual device before declaring done.

### R4 — Deploy to Proxmox LXC
Follow `docs/proxmox_setup.md`: create LXC, Tailscale, clone + venv, copy `.env`/`auth_config.yaml`/`secrets/` (incl. fonts) + certs, set `DB_PATH` + `IMAGES_DIR` + `BILLS_PDF_DIR` to backed-up volumes, install `deploy/streamlit.service`, configure `vzdump`.

### R5 — Suggest-qty prefill in the create grid (NOT done)
`bills.suggest_qty()` exists but page-1 **create** grid (`_bill_grid(..., key="new_grid")`) still starts every row at 0. Wire it: build a per-customer suggestion map once → pass as `preset_qty`. (The edit grid already uses `preset_qty` for current qtys.)

### R7 — Test gaps
Have unit + bill/pdf tests. Missing: `lib/storage.py` round-trip (save/EXIF/URL passthrough) and a page-import smoke (pages have `require_auth()`+`sys.path` side effects → brittle in pytest; smoke them carefully or skip).

### R8 — Code-quality polish
- `lib/drive.py` is dead code — delete or feature-flag (revisit D3 first; the quota issue is structural, don't just restore Drive).
- Replace deprecated `use_container_width=True` with `width="stretch"`.
- `strftime %-d/%-m/%Y` is Linux-only — use an explicit formatter for cross-platform.

---

## Known traps for next agent

1. **Don't `pkill -f streamlit`** — the command string contains "streamlit" and kills the agent's own shell. Use `fuser -k 8501/tcp`.
2. **Auto-reload doesn't re-import `lib/`** — editing `lib/*.py` needs a fresh Streamlit restart (`fuser -k` + rerun).
3. **`bill_lines` is a read-only VIEW** — never INSERT/UPDATE it from Python (D2c).
4. **Boolean columns are strings** (`"TRUE"`/`"FALSE"`/`1`) — use the tolerant checks (`_normalize_active`, `bills._to_float`), not truthiness.
5. **`secrets/` is fully gitignored** (SA JSON + all fonts) — `git status` showing it untracked is intentional; don't `git add secrets/`.
6. **Decorative fonts are optional** — `lib/pdf.py::_register_fonts` falls back to Sarabun if Charmonman/Chakra Petch are absent; a deploy without them still renders (no script look).
7. **Reference binaries are gitignored** — `ส่งโรงเรียน2022.xlsx` (real sales data) + `bill_example.jpg` (real signed bill) stay local.
8. **Customer short code is in `customer.name`** (e.g. "พป."), not `customer.code` (=C001/C002) — the bill prints `.name` (memory `customer-name-holds-short-code`).

---

## Quick reference

```bash
cd /home/raebakery/claude_code/project/rae-bakery-delivery

# dev server (uses .streamlit/config.toml)
.venv/bin/streamlit run app.py
# kill old server (never pkill -f streamlit)
fuser -k 8501/tcp

# tests
.venv/bin/pytest -q

# visually verify the bill PDF against the Sheet template (write your own throwaway
# script calling pdf.generate_bill_pdf with sample lines, then):
#   pdftoppm -png -r 150 sample.pdf out        # PDF → PNG (poppler-utils installed)
#   google-chrome --headless=new --no-sandbox --screenshot=h.png --window-size=620,900 sample.html  # HTML
# reference: ~/Documents/sheet ส่งโรงเรียน/พิมพ์บิล พป..html (the Sheet's own print output)

# new auth user password hash
.venv/bin/python scripts/gen_password.py "their-password"

# git: feature branch → PR → merge into develop (never commit to main)
git checkout -b feature/<name>
```

---

## Hot files (read first)

1. `lib/schema.py` — `COLUMNS` (english⇄thai), DDL, `bill_lines` VIEW
2. `lib/db.py` — `connect()` (WAL), `init_db()`, `replace_bill_items()`
3. `lib/sheets.py` — SQLite-backed public surface + `_invalidate`/`clear_caches`
4. `lib/bills.py` — domain logic: ID gens, dates, totals, `update_bill`, status setters, `suggest_qty`
5. `lib/pdf.py` — PDF + HTML bill renderers (Sheet template, fonts, fixed-Y signature)
6. `lib/pdf_archive.py` — per-bill PDF on disk
7. `pages/1_📦_ใบส่งสินค้า.py` — click-to-edit bill list (detail/print/archive/edit/status)
8. `docs/proxmox_setup.md` — deploy steps
9. `.omc/specs/deep-interview-delivery-bill-improvements.md` — bill-feature spec
