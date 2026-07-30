# DEFRA / DWP Removal Audit — 7 July 2026

Audit only — no changes made. Grepped the entire codebase (excluding
`__pycache__` and `.claude/worktrees`) for every reference to `dept_defra` and
`dept_dwp`. Each hit is classified:

- **(a)** internal to the app (removable with it)
- **(b)** genuine external reference that would break if the app were removed
- **(c)** incidental — comment, doc string, or documentation-only markdown

---

## 1. Complete grep results with classification

### config/settings.py

| Line | Content | Class |
|------|---------|-------|
| 45 | `'dept_dwp',` in INSTALLED_APPS | **(b)** |
| 47 | `'dept_defra',` in INSTALLED_APPS | **(b)** |

### config/urls.py

| Line | Content | Class |
|------|---------|-------|
| 24 | `from dept_dwp import urls as dept_dwp_urls` | **(b)** |
| 26 | `from dept_defra import urls as dept_defra_urls` | **(b)** |
| 48 | `path('dwp/', include((dept_dwp_urls, 'dept_dwp'))),` | **(b)** |
| 50 | `path('defra/', include((dept_defra_urls, 'dept_defra'))),` | **(b)** |

**6 genuine external references total — 3 per app — all requiring code edits
before the directory can be deleted.**

### core/management/commands/load_test_data.py

| Lines | Content | Class |
|-------|---------|-------|
| 207 | `# ── DWP test users ──` (comment) | (c) |
| 209–211 | `dwp_alice`, `dwp_bob`, `dwp_agent1` user creation | (a) |
| 225 | `# ── DEFRA test users ──` (comment) | (c) |
| 227–231 | `defra_alice` user creation | (a) |
| 242–244 | `dwp_alice = User.objects.get(...)` references (used in permission block below) | (a) |
| 387 | `dept_id='DWP'` Department fixture row | (a) |
| 391 | `dept_id='DEFRA'` Department fixture row | (a) |
| 705 | `# ── DWP user permissions ──` (comment) | (c) |
| 707 | comment explaining blanket-permission grant | (c) |
| 709 | `for u in [dwp_alice, dwp_bob]: Permission.objects.create(...)` | (a) |
| 717 | comment | (c) |
| 719 | `Permission.objects.create(actor=dwp_agent1, user=dwp_alice, ...)` | (a) |
| 863–864 | `self.stdout.write(...)` output lines naming DWP/DEFRA users | (a) |
| 870–872 | `self.stdout.write(...)` output lines summarising permissions | (a) |

All load_test_data.py hits are either comments (c) or internal fixture-setup
code (a). None are referenced from outside this file (confirmed below).

### dept_hmrc/tests.py

| Lines | Content | Class |
|-------|---------|-------|
| 571–574 | Comment and `other_client.login(username='dwp_alice', ...)` | **(b)** |

**This is the only external test reference.** `dwp_alice` is borrowed here
purely as a convenient "user with no IHT verified cases". The actual test
logic (line 577–583) uses `self.carla` and `bob`, not `dwp_alice` — the login
call on line 573 is unused (the comment on line 574 explains this). If
`dwp_alice` no longer exists in the fixture, this test would fail at the
`login()` call with an authentication error, even though `dwp_alice` is never
actually exercised by the assertion.

**Classification: (b) — a real dependency, but a trivially fixable one.**
Changing line 573 to login as `bob` or `carla` and deleting lines 571–574
removes the dependency in full.

### dept_defra/ and dept_dwp/ — internal files

All files inside `dept_defra/` and `dept_dwp/` (apps.py, urls.py, views*.py,
templates/, tests.py, models.py, migrations/__init__.py) are **(a) — internal**
and are removed when the directory is deleted. Not enumerated individually here
as they are trivially internal.

### Documentation markdown files (root)

References in `260614_Initial_Prompt.md`, `260701_Core_Platform_Reference.md`,
`260705_Core_Core_Map.md`, `260706_Coherence_Audit.md`, `260705_Backlog.md`,
etc. are all **(c) incidental** — historical documentation, not runtime code.

---

## 2. Classification summary

| Class | Count | Notes |
|-------|-------|-------|
| **(a) internal** | ~30 | removable with the app directory |
| **(b) external** | 7 | 6 in config/ + 1 in dept_hmrc/tests.py |
| **(c) incidental** | ~10 | comments and docs |

---

## 3. Core test suite dependency check

`core/tests.py` — **zero hits** for `dwp`, `defra`, `DWP`, `DEFRA`. The core
test suite defines all its own fixture data (TEST regimes, `alice`, `bob`,
`carla`) and has no dependency on either app being installed or on any
DWP/DEFRA regime row existing.

The only external test reference is `dept_hmrc/tests.py:573` (classified **(b)**
above) where `dwp_alice` is logged in but immediately abandoned — the actual
assertion uses unrelated users. One-line fix.

---

## 4. Migration check

Neither app defines any Django models:

- `dept_defra/models.py` — empty (comments only)
- `dept_dwp/models.py` — empty (comments only)
- `dept_defra/migrations/` — contains only `__init__.py`; no migration files
- `dept_dwp/migrations/` — contains only `__init__.py`; no migration files

**No `makemigrations` or `migrate` commands are needed.** There are no database
tables to drop. The app directories can be deleted; the empty migrations
packages leave no database artefact.

The DWP/DEFRA `Dept` rows in the database (created by `load_test_data.py`) are
core-model rows, not app-owned. Deleting the apps does not cascade-delete them.
A one-time cleanup of `Dept.objects.filter(dept_id__in=['DWP', 'DEFRA']).delete()`
can be run manually after removal, or those rows can simply remain dormant.

---

## 5. Recommendation

### dept_defra — **safe to remove**

No core dependency. No DB tables. The 3 config/ references are a one-edit
removal. No test outside the app itself depends on DEFRA.

### dept_dwp — **safe to remove, one trivial pre-fix required**

Same as DEFRA for config/ references and DB. The single external dependency
is `dept_hmrc/tests.py:573` — `dwp_alice` is logged in but the assertion does
not use the result. Fix: replace with `bob` or remove the login call entirely,
then delete the now-stale comment block on lines 571–574.

### Required steps before deletion (both apps)

1. **`config/settings.py`** — remove `'dept_dwp'` (line 45) and `'dept_defra'`
   (line 47) from INSTALLED_APPS.

2. **`config/urls.py`** — remove the two import lines (24, 26) and the two
   `path(...)` lines (48, 50).

3. **`dept_hmrc/tests.py`** — remove or fix the `dwp_alice` login on line 573
   (and the surrounding comment block 571–574).

4. **`core/management/commands/load_test_data.py`** — remove the DWP user,
   DEFRA user, Department, and Permission fixture blocks (lines 207–244,
   387/391, 705–722, 863–864, 870–872). Optional but leaves the fixture clean.

5. **Delete directories** — `dept_defra/` and `dept_dwp/`.

6. No migration step needed.
