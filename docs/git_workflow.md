# Git Workflow

## Branching strategy
- `main` — production-ready code; ห้าม commit ตรง (release merges + hotfix เท่านั้น)
- `develop` — integration branch; all `feature/*` branches merge here first, then `develop` is promoted to `main` for a release
- `feature/<short-name>` — งานใหม่ทุกอย่าง (เพิ่ม feature, fix bug, refactor); branch from `develop`, merge back into `develop`
- `hotfix/<short-name>` — แก้ด่วน production (branch from `main`, merge เข้าทั้ง `main` และ `develop`; แล้วผมจะ tag)

## ขั้นตอนทำ feature ใหม่

```bash
# 1. update develop ก่อน
git checkout develop
git pull origin develop

# 2. สร้าง branch ใหม่ (แตกจาก develop)
git checkout -b feature/bill-grid-form

# 3. เขียน code → commit ทีละหน่วยที่ทำงานได้
git add pages/1_📦_ใบส่งสินค้า.py
git commit -m "feat: add bill grid form with all products"

# 4. push ขึ้น remote
git push -u origin feature/bill-grid-form

# 5. (ถ้ามี remote เป็น GitHub/GitLab) เปิด Pull Request เข้า develop → review → merge
# (ถ้าใช้ local อย่างเดียว) merge เข้า develop:
git checkout develop
git merge --no-ff feature/bill-grid-form
git push origin develop
git branch -d feature/bill-grid-form
```

## Releasing (develop → main)

`main` moves only through a `develop` promotion (a release) or a `hotfix/*` merge — never a direct commit. When `develop` is stable and ready to ship:

```bash
git checkout main
git pull origin main
git merge --no-ff develop              # bring the release into main
git tag -a vX.Y.Z -m "release: <summary>"
git push origin main --follow-tags

git checkout develop                   # sync develop back with main
git merge --no-ff main
git push origin develop
```

## Commit message convention

ใช้ **Conventional Commits** — ช่วยให้อ่าน history ง่าย + gen changelog ได้

```
<type>: <subject>

<body, optional>
```

### Type ที่ใช้บ่อย

| type | ใช้เมื่อ |
|---|---|
| `feat` | เพิ่ม feature ใหม่ |
| `fix` | แก้ bug |
| `refactor` | ปรับโครงสร้างโดยไม่เปลี่ยน behavior |
| `docs` | แก้เอกสาร |
| `style` | format, linting (ไม่กระทบ logic) |
| `test` | เพิ่ม/แก้ test |
| `chore` | งานเบื้องหลัง (deps, config) |
| `perf` | ปรับ performance |

### ตัวอย่างที่ดี
```
feat: add bill grid form with auto-suggest quantity
fix: handle missing stock rows (return 0 instead of error)
refactor: split sheets.py — move bill logic to bills.py
docs: add proxmox deploy guide
chore: bump streamlit 1.37 → 1.38
```

### ที่ไม่ควรเขียน
```
update                      # ← ไม่บอกว่า update อะไร
fix bug                     # ← bug อะไร?
WIP                         # ← work-in-progress commit ไม่ควรเข้า main
```

## ดู history สวยๆ

```bash
git log --oneline --graph --decorate --all
```

ตั้ง alias:
```bash
git config alias.lg "log --oneline --graph --decorate --all"
git lg
```

## undo ที่ใช้บ่อย

| สถานการณ์ | คำสั่ง |
|---|---|
| แก้ไฟล์แต่ยังไม่ stage | `git restore <file>` |
| `git add` ไปแล้วแต่ยังไม่ commit | `git restore --staged <file>` |
| commit ผิด (ยังไม่ push) แก้ message | `git commit --amend` |
| ลบ commit ล่าสุด (เก็บ changes) | `git reset HEAD^` |
| ลบ commit ล่าสุด ทิ้ง changes | `git reset --hard HEAD^` ⚠️ |

## ไฟล์ที่ห้ามขึ้น git

ตรวจที่ `.gitignore`:
- `secrets/*.json` (service account key)
- `.env` (env vars จริง)
- `auth_config.yaml` (user passwords)
- `.venv/` (dependencies)
- `__pycache__/`, `*.pyc`

ก่อน commit ครั้งแรก:
```bash
git status                  # ดูว่ามีไฟล์ secret โผล่มาไหม
git ls-files | grep -i 'secret\|env\|json'  # double check
```
