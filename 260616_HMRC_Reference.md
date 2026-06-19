# cg_data_exchange — HMRC Reference
Date: June 2026
Status: Living document — add sections as IHT is built out
Verified: Content checked against file_dump.txt by Claude on 16 June 2026

---

## 1. HMRC thin layer

`dept_hmrc` is the HMRC department app. URL prefix `/hmrc/`.
Live on Render at `https://cg-data-exchange-hmrc.onrender.com`.

### Views: `dept_hmrc/views/hmrc_home.py`

**`dept_home`** — HMRC landing page. Lists all HMRC regimes. Sets
`active_dept='HMRC'` in session.

**`regime_home`** — thin dispatcher. Checks `regime_id` and routes to the
correct orchestrator. Currently:
```python
if regime_id == 'HMRC_IHT':
    return iht_orchestrate(request)
# Generic fallback for unconfigured regimes
```
Adding a new tax regime: add a new `elif` here and create a new subfolder
under `views/`.

### URLs

| URL | View | Name |
|-----|------|------|
| `/hmrc/` | `dept_home` | `dept_home` |
| `/hmrc/regime/<regime_id>/` | `regime_home` | `regime_home` |
| `/hmrc/iht/matching/<case_id>/` | `iht_matching_result` | `iht_matching_result` |
| `/hmrc/iht/reckoner/compute/` | `iht_reckoner_compute` | `iht_reckoner_compute` |
| `/hmrc/iht/reckoner/threshold/` | `iht_reckoner_threshold` | `iht_reckoner_threshold` |
| `/hmrc/tools/` | (core admin tools) | — |

---

## 2. IHT regime — overview

The IHT regime (`HMRC_IHT`) uses a progressive home page model. Action
buttons appear on the estate homepage as the executor progresses — not all
at once. This replaces the overwhelming schedule-selector model of the
paper IHT400.

The home page is driven by `iht_orchestrate`, which reads all state fresh
on every visit and dispatches. `iht_screen` renders the UX and never reads
the DB. For a full description of the orchestration logic see
`260615_IHT_Orchestration_Logic.md`.

There is a subtlety in how Cases work in IHT. Since IHT relates to an
estate, it is possible for more than one executor to each attempt to create
a submission: each attempt is allocated its own Case by the core app. But
the initial details of the deceased (last name and date of death) are then
checked against all earlier Cases; only if unique will a `reference` be
issued — the IHT case number. A **verified case** is a Case with
`reference` not null — one that has passed this matching check.

`iht_orchestrate` writes the current actor's `user_id` and `actor_id` to
session on every visit before resolving the acting-for user, ensuring the
correct user's cases are always queried regardless of session state.

### Home page UX (`iht_screen`)

Once a verified case exists, `iht_screen` renders two things:

A **deceased details summary panel** — name, date of birth, date of death,
NI number, and IHT reference, drawn from the verified case.

A **recursive action list** — each row represents one action button. Rows
are built dynamically by `_build_action_list` and passed into the template
as a list of dicts. Each row can carry: a status badge (with colour), an
action link with label, and an optional flash message shown above the row.
The template loops over rows generically — adding a new action button
requires no template changes.

The reckoner row shows a persistent conclusion message derived from the
`IHTReckoner` model (see section 4). Flash messages (`iht_flash` session
key) take priority over the persistent message when both are present.

### File structure

```
dept_hmrc/
  models.py                 — IHTReckoner model
  views/iht/
    orchestrate.py          — iht_orchestrate + _build_action_list
    screen.py               — iht_screen (renderer only, never reads DB)
    matching.py             — iht_matching_result, run_iht_matching,
                              _generate_iht_reference
    reckoner.py             — handle_reckoner, get_reckoner_state,
                              _save_conclusion, iht_reckoner_compute,
                              iht_reckoner_threshold, answer value constants,
                              RECKONER_SECTION dict
    utils.py                — _get_iht_answers shared helper
  templates/dept_hmrc/iht/
    home.html               — IHT estate homepage (pre- and post-matching)
    duplicate.html          — Duplicate case page
```

### IHTReckoner model (`dept_hmrc/models.py`)

One row per case. Stores the reckoner conclusion and the computed threshold
question details. Written by `_save_conclusion` (knock-out path) or
`iht_reckoner_threshold` POST (threshold path). Read by `_build_action_list`
to show a persistent conclusion message on the reckoner row.

| Field | Type | Notes |
|-------|------|-------|
| `case` | OneToOneField → core.Case | |
| `conclusion` | CharField | `not_payable` / `may_be_payable` / `knock_out` |
| `question_text` | TextField | The computed question shown to executor |
| `threshold` | IntegerField (nullable) | Computed £ threshold |
| `answer` | CharField | `Yes` / `No` / blank (knock-out) |
| `answered_at` | DateTimeField | auto_now_add |

DB table: `dept_hmrc_ihtreckoner`. Migration: `0001_initial.py`.

---

## 3. Action button: Deceased's details

### Summary

**Enables:** The executor enters the name, dates, and NI number of the
deceased. On completion the system checks whether an IHT case for this
estate already exists. If not, it creates one and assigns an IHT reference
number. The deceased details summary panel then appears on the home page
for all subsequent visits.

**Sections called:** HMRC_S1

---

### HMRC_S1 — About the deceased

**Enables:** Captures the core identity details of the deceased needed to
identify the estate and run the duplicate check.

| Question | ID | Type |
|----------|----|------|
| Full name | HMRC_1 | personal_name |
| Date of death | HMRC_2 | date |
| Date of birth | HMRC_3 | date |
| National Insurance number | HMRC_4 | text |
| Did the deceased leave a will? | HMRC_5 | radio |

Routing: linear (no branching). `show_confirmation=True`.

**Post-section: matching flow**

`section_done` redirects to `iht_matching_result` rather than back to the
home page directly. This is achieved via `post_confirm_redirect` written
to session by `iht_orchestrate` before the section is entered. When
HMRC_S1 is entered, `section_start` clears any existing
`post_confirm_redirect` to prevent misfires from the reckoner path.

`run_iht_matching(case)` compares last name + date of death against all
verified cases (those with a non-null `reference`).

- **Unique:** assigns reference in `IHT-000000001` format (sequential,
  derived from `MAX(reference)` across all IHT cases), writes `iht_flash`
  to session, redirects to regime home.
- **Duplicate:** renders `iht/duplicate.html`.

**Status:** Complete.

---

## 4. Action button: Estate ready reckoner

### Summary

**Enables:** Guides the executor through a series of questions to determine
whether IHT is payable on the estate. Designed to reach a "not payable"
conclusion quickly for most estates without requiring precise asset values.
Three possible outcomes: knock-out (must use full return), not payable
(reckoner complete), or may be payable (estate details button appears).

**Sections and views called:**
- HMRC_S2 — entry: need help? + marital status (always called by button)
- HMRC_S3 — reckoner questions, Part 3: single/divorced/partnered
- `iht_reckoner_compute` — intercepts S3 completion, clears stale conclusion,
  calls `get_reckoner_state` (bespoke dept view, not a platform section)
- `iht_reckoner_threshold` — renders computed threshold question, stores
  conclusion (bespoke dept view, not a platform section)

Parts 1 (married) and 2 (widowed) are not yet built. When selected,
`handle_reckoner` returns None and the home page renders without a
reckoner conclusion.

**View / amend:** the reckoner row link points to `/section/HMRC_S3/review/`
once S3 is complete, so the executor sees their substantive reckoner answers.
On confirm (with or without changes), `section_done` fires
`post_confirm_redirect` → `iht_reckoner_compute` → updated conclusion.

---

### HMRC_S2 — Do you need help?

**Enables:** Establishes whether the executor wants guided help (reckoner
path) or already knows a full return is required (direct to estate details).
Captures marital status to determine which reckoner part applies.

| Question | ID | Type | Options |
|----------|----|------|---------|
| Do you need help? | HMRC_13 | radio | Yes / No |
| Marital status at time of death | HMRC_14 | radio | Single / Married / Widowed |

Routing: HMRC_13=Yes → HMRC_14 → END; HMRC_13=No → END.
`show_confirmation=False`.

**Post-section: `handle_reckoner`**

Called by `iht_orchestrate` when S2 is complete:
- HMRC_13=No → return None (estate details button appears)
- HMRC_13=Yes, HMRC_14=Single → call HMRC_S3 (if not complete) or return
  None (if complete — home page renders with stored conclusion)
- HMRC_13=Yes, HMRC_14=Married or Widowed → return None (not yet built)

When dispatching into S3, `iht_orchestrate` sets `post_confirm_redirect`
to `iht_reckoner_compute` in session on every home page visit where
HMRC_13=Yes and HMRC_14=Single.

**Status:** Complete.

---

### HMRC_S3 — Reckoner questions (Part 3: single/divorced/partnered)

**Enables:** Establishes whether any disqualifying circumstances apply
(knock-out), the value of any home left to direct descendants (RNRB), and
the total taper-adjusted value of gifts made in the last 7 years. These
values feed into the threshold computation in `get_reckoner_state`.

Question order as routed:

| # | ID | Question | Type | Options / Notes |
|---|-----|----------|------|-----------------|
| 1 | HMRC_11 | Knock-out: did any of the following apply? | checkbox | See below |
| 2 | HMRC_10 | Did the deceased make any gifts in the 7 years before death? | radio | Yes / No |
| 3 | HMRC_15 | Gift values by year | compound | 7 components (if HMRC_10=Yes) |
| 4 | HMRC_7 | Did the deceased own a home? | radio | Yes / No |
| 5 | HMRC_8 | Was any part left to a direct descendant? | radio | Yes / No |
| 6 | HMRC_9 | Value of share left to descendants | number | |

HMRC_11 knock-out options (exact stored strings):
- `Transfers into trust`
- `Assets sold at undervalue`
- `Unused pension funds`
- `Gifts with reservation`
- `None of the above` (continues to HMRC_10)

HMRC_15 component labels (exact stored strings, used as dict keys):
- `Year 1 — gifts made in the year before death`
- `Year 2 — gifts made 2 years before death`
- `Year 3 — gifts made 3 years before death`
- `Year 4 — gifts made 4 years before death`
- `Year 5 — gifts made 5 years before death`
- `Year 6 — gifts made 6 years before death`
- `Year 7 — gifts made 7 years before death`

Routing (as stored in admin tools):
```
HMRC_11: knock-out options → END
         None of the above → HMRC_10
HMRC_10: Yes → HMRC_15,  No → HMRC_7      (default → HMRC_7)
HMRC_15: All other answers → HMRC_7
HMRC_7:  Yes → HMRC_8,   No → END         (default → END)
HMRC_8:  Yes → HMRC_9,   No → END         (default → END)
HMRC_9:  All other answers → END
```
`show_confirmation=False`.

**Post-section: `iht_reckoner_compute` → `get_reckoner_state`**

`section_done` redirects to `iht_reckoner_compute` (via
`post_confirm_redirect`). That view deletes any stale `IHTReckoner` row
and calls `get_reckoner_state` directly.

`get_reckoner_state` reads S3 answers and:

1. **Knock-out check** — if any knock-out option in HMRC_11 → calls
   `_save_conclusion(request, case, 'knock_out')` → `IHTReckoner` written,
   redirect to regime home.

2. **Threshold computation** (non-knock-out paths):
   ```
   rnrb         = min(HMRC_9, £175,000)  if HMRC_9 answered, else 0
   taper_gifts  = sum of (year value × taper_rate) from HMRC_15
   threshold    = £325,000 + rnrb - taper_gifts
   ```
   Taper rates: Years 1–3 = 100%, Year 4 = 80%, Year 5 = 60%,
   Year 6 = 40%, Year 7 = 20%.

3. Writes `threshold` and `case_id` to session, redirects to
   `iht_reckoner_threshold`.

**Status:** Complete.

---

### Bespoke view: `iht_reckoner_threshold`

**Enables:** Asks the single computed question that closes the reckoner —
"Was the total value of the estate less than £X?" where X is the computed
threshold. The executor is unaware this is rendered by dept code rather
than the platform — it uses the core `question_radio.html` template.

URL: `/hmrc/iht/reckoner/threshold/`

**GET:** Reads threshold from session. Renders `core/question_radio.html`
with computed question text, Yes/No options, and hint text. Pre-populates
from existing `IHTReckoner` if present (re-entry).

**POST:** Validates answer. Writes `IHTReckoner` row:
- `conclusion`: `not_payable` (Yes) or `may_be_payable` (No)
- `question_text`: the formatted string shown to executor
- `threshold`: computed integer
- `answer`: Yes or No

Clears threshold from session. Redirects to regime home.

On the next home page visit, `_build_action_list` reads `IHTReckoner`
and shows the persistent conclusion message on the reckoner row. If
`may_be_payable`, the Estate details button appears.

**Status:** Complete.

---

### Bespoke view: `iht_reckoner_compute`

**Enables:** Intercepts `section_done` after S3 completion (via
`post_confirm_redirect`). Deletes any stale `IHTReckoner` row for the
verified case, then calls `get_reckoner_state` directly. Ensures the
threshold view is always reached after S3 confirms — whether on first
entry or after View / amend.

URL: `/hmrc/iht/reckoner/compute/`

**Status:** Complete.

---

## 5. Action button: Estate details

### Summary

**Enables:** The executor declares the full details of the estate —
property, financial assets, jointly owned assets, and liabilities.
This button appears only when the reckoner concludes IHT may be payable,
or when the executor already knows a full return is required (HMRC_13=No).

**Sections called:** To be grouped into Schedule HMRC_SCH1. Sections for
property, financial assets, jointly owned assets, and liabilities.

**Status:** Not yet built. Button currently shows `href="#"`. See D2 in Backlog.

---

## 6. Orphaned questions

These questions exist in the database but are not assigned to any section.
Leave in place until D3 (load_test_data) is updated.

| ID | Formerly used for |
|----|-------------------|
| HMRC_6 | Assets > £325k radio (retired from S3) |
| HMRC_12 | PET total number (retired with S4) |

HMRC_S4 and HMRC_S5 (formerly PET total and 7-year breakdown sections)
are also orphaned — retired when gifts-by-year was folded into S3.

---

## 7. Database content (as of 15 June 2026)

| Type | Content |
|------|---------|
| Questions | HMRC_1–HMRC_15 (HMRC_6, HMRC_12 orphaned) |
| Sections | HMRC_S1, HMRC_S2, HMRC_S3 (complete); HMRC_S4, HMRC_S5 (orphaned) |
| Regime | HMRC_IHT (active) |
| Cases in production | IHT-000000001 through IHT-000000003 |

**Test users** (password: `testpass123`):
`alice`, `bob`, `carla`, `solicitor1`

**Admin users:**
`admin` (is_staff=True, pw: `password123`),
`super_admin` (is_superuser=True, pw: `password123`)

---

## 8. Tests

`dept_hmrc/tests.py` — 11 tests (115 total across core + dept_hmrc),
run separately (not in INSTALLED_APPS):
```
/Users/robert/anaconda3/envs/env_python_django_psql/bin/python manage.py test dept_hmrc --keepdb
```

---

## 9. Admin tools — IHT-specific notes

The core admin tools at `/hmrc/tools/` are used to manage all IHT
questions, sections, and routing. Key behaviours as of 16 June 2026:

**Question edit** — the edit wizard shows and allows editing of `options`
for radio and checkbox questions (semicolon-delimited in a textarea).
Compound questions show the component builder. Other question types show
neither.

**Routing display** — question header rows show the full question text
(wrapping, no truncation). The three-dots menu on question rows offers:
Insert question above, Delete this question and conditions, and a
per-option condition panel showing each option's current destination
pre-populated. Changing a destination and clicking Add updates the
existing routing rule. Condition rows have no three-dots menu.

**Shared routing tree** — the routing tree UI exists in two templates:
`tools_section_routing.html` and `tools_section_edit.html`. Changes to
the routing tree UI must be made in both. A refactor to a shared
`{% include %}` partial is in the TIDY backlog.
