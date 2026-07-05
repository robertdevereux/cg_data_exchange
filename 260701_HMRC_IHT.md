# HMRC IHT — Technical Reference
Date: 1 July 2026
Status: Current — reflects code as at end of 1 July 2026 session

This document covers the IHT (Inheritance Tax) regime implementation in full.

---

## 1. Overview

The IHT regime allows an executor to submit an Inheritance Tax return online.
The PoC implements the triage and ready reckoner stages — full form completion
is deferred.

**Key concepts:**
- **Estate** — the deceased person's assets and liabilities
- **Executor** — the person completing the submission (the platform user)
- **IHT reference** — a unique reference (IHT-000000001 format) assigned once
  the estate is verified as unique in the system
- **Verified case** — a Case record with a non-null reference; the estate has
  passed duplicate checking

**File structure:**
```
dept_hmrc/views/iht/
  orchestrate.py   — regime controller; all dispatch logic
  screen.py        — rendering only; decorates lean action state
  matching.py      — duplicate checking and reference generation (functions only)
  reckoner.py      — reckoner dispatch and threshold computation
  utils.py         — answer extraction helpers
```

---

## 2. The two-phase action button pattern

Every action button on the IHT home page has two phases, both handled in
`iht_orchestrate`:

**ENTRY** — user has clicked an action button; `iht_orchestrate` sends them
into core sections.

**EXIT** — core has completed and returned to `iht_orchestrate` via
`return_url = regime_home_url`; `iht_orchestrate` does post-processing
then renders home.

Two session flags control dispatch:

| Flag | Purpose |
|------|---------|
| `iht_current_action` | Which action button is active. Set by the thin action button view, cleared by `iht_orchestrate` on exit. |
| `iht_in_core` | True while user is inside core sections. Set by each `_entry_*` function, popped by `iht_orchestrate` on every visit. |

`iht_orchestrate` logic:

```python
returning_from_core = request.session.pop('iht_in_core', False)

if not returning_from_core:   # ENTRY
    dispatch to _entry_[action]()
else:                          # EXIT
    dispatch to _exit_[action]()
```

**No `post_confirm_redirect` is used in HMRC IHT.** All post-processing
happens in `iht_orchestrate` on return from core. `call_core` sets
`return_url = regime_home_url` so core always returns here.

**ENTRY functions always send users into core first.** An `_entry_*`
function must never do routing logic — it calls `_enter_core` then
`call_core` and redirects. All post-section logic belongs in `_exit_*`.
(Historical note: `_entry_reckoner` previously combined entry and routing
logic because S2 was a gate question. This was simplified when S2 was
redesigned — see section 6.)

---

## 3. `iht_orchestrate` — the dispatcher

```
Every visit to /hmrc/regime/HMRC_IHT/
    ↓
_setup() — regime, actor, user, session, crumbs
    ↓
active_items = _get_active_triage_items(verified_case)
pop iht_in_core → returning_from_core
read iht_current_action → current_action
    ↓
Bootstrap: if no verified_case and no current_action
    → set current_action = 'start'
    ↓
if not returning_from_core:          ← ENTRY
    start            → _entry_start()
    deceased_details → _entry_deceased_details()
    reckoner         → _entry_reckoner()
    tailor           → _entry_tailor()
    hmrc_s4/s5/s6   → _entry_triage_assets(section_id)
    None             → _render_home()
    ↓
if returning_from_core:              ← EXIT
    start            → _exit_start()
    deceased_details → _exit_deceased_details()
    reckoner         → _exit_reckoner() [may re-enter core]
    tailor           → (nothing) → fall through
    hmrc_s4/s5/s6   → (nothing) → fall through
    ↓
_clear_current_action()
_render_home()
```

---

## 4. Action button: Start

**Concept:** The very first visit — no verified case exists yet. The executor
provides the deceased's details so the estate can be identified.

### Entry

`_entry_start`:
1. `_get_or_create_draft_case` — ensures a draft Case exists in DB
2. `_enter_core` — sets `iht_in_core = True`
3. `call_core([{'type': 'section', 'id': 'HMRC_S1'}])` — sends user into S1
4. Renders `iht_screen_unverified` — pre-verified home page showing the
   "Create a new draft estate submission" entry button

**S1 questions** (HMRC_S1 — "Create a new draft estate submission"):
| ID | Question |
|----|----------|
| HMRC_1 | Title |
| HMRC_2 | First name |
| HMRC_3 | Last name |
| HMRC_4 | Date of birth |
| HMRC_5 | Date of death |
| HMRC_14 | At the time of their death, was the deceased... (marital status) |

Note: HMRC_14 (marital status) was moved into S1 from S2 so it is collected
as part of deceased's details, where it conceptually belongs. It is
architecturally significant — it determines which reckoner journey fires.

### Exit

`_exit_start` — called when user returns from S1 for the first time:
1. Finds the draft case (reference still null)
2. Calls `run_iht_matching(draft_case)` — compares last name + date of death
   against all other verified cases
3. **If duplicate** → renders `duplicate.html` — dead end, user told estate
   already exists
4. **If unique** → calls `_generate_iht_reference()`, assigns reference to
   case, flashes confirmation message, redirects to regime home

Reference format: `IHT-000000001` (sequential, zero-padded to 9 digits).

**Matching logic** (`run_iht_matching`):
- Compares `last_name` and `dod_raw` from `_get_iht_answers`
- Excludes the current case from comparison
- Returns `('unique', None)` or `('duplicate', matching_case)`

---

## 5. Action button: Deceased's details

**Concept:** The executor returns to amend the deceased's details after the
estate has been verified. The IHT reference must be preserved regardless.

### Action button view

`iht_action_deceased` — thin wrapper:
```python
_set_current_action(request, 'deceased_details')
redirect → regime_home → iht_orchestrate (ENTRY)
```

### Entry

`_entry_deceased_details`:
1. `_enter_core` — sets `iht_in_core = True`
2. `call_core([{'type': 'section', 'id': 'HMRC_S1'}])` — sends user into S1 (re-entry, shows review)

### Exit

`_exit_deceased_details`:
1. Calls `run_iht_matching(verified_case)` against amended answers
2. **If now duplicate** → renders `duplicate_amend.html` (see D7 in backlog
   — template not yet built; this is a dead end telling the executor their
   changes conflict with an existing estate and HMRC will be in touch)
3. **If still unique** → flashes "Deceased's details have been updated",
   redirects to regime home. IHT reference unchanged.

---

## 6. Action button: Estate ready reckoner

**Concept:** Two questions determine whether the executor wants reckoner help
and what type of estate it is. The answers then route to the appropriate
reckoner journey or directly to the asset selector.

### IHT home page display

The IHT home page displays deceased's details including marital status:
- Name, Date of birth, Date of death, National Insurance number
- Marital status (HMRC_14 — now collected in S1)
- IHT reference

### Section structure

| Section | Name | Questions |
|---------|------|-----------|
| HMRC_S1 | Create a new draft estate submission | HMRC_1–5 + HMRC_14 |
| HMRC_S2 | Ready Reckoner Access | HMRC_13 only |
| HMRC_S3 | Ready reckoner 1A | Reckoner questions (single/never married) |

**HMRC_S2 routing:** HMRC_13 → END (unconditional single route, no branching).

### Key questions

| ID | Question | Role |
|----|----------|------|
| HMRC_13 | Would you like help working out if IHT is payable? | Reckoner gateway |
| HMRC_14 | At the time of their death, was the deceased... | Marital status; selects reckoner section; collected in S1 |

### Action button view

`iht_action_reckoner` — thin wrapper:
```python
_set_current_action(request, 'reckoner')
redirect → regime_home → iht_orchestrate (ENTRY)
```

### Entry

`_entry_reckoner`:
1. `_enter_core` — sets `iht_in_core = True`
2. `call_core([{'type': 'section', 'id': 'HMRC_S2'}])` — always sends user
   into S2 (the single-question reckoner preference section)

The user always sees S2 on entry — whether starting fresh, amending HMRC_13,
or correcting marital status (HMRC_14, now in S1 via Deceased's details).

### Exit

`_exit_reckoner` — delegates to `handle_reckoner`:

`handle_reckoner` reads HMRC_13 (from S2) and HMRC_14 (from S1):
- **HMRC_13 = No** → deletes any stale `IHTReckoner` row → returns None
  → tailor button appears (if `_should_show_tailor` is satisfied)
- **HMRC_13 = Yes + HMRC_14 maps to a built section** → calls that section
- **HMRC_13 = Yes + HMRC_14 maps to unbuilt section** → returns None

**Stale IHTReckoner cleanup:** When a user changes HMRC_13 from Yes to No,
`handle_reckoner` deletes any existing `IHTReckoner` row so the reckoner
conclusion does not persist on the home page.

**`iht_reckoner_threshold`** — a bespoke dept view (not a core section):
- Renders a single computed radio question: "Was the total value of the
  estate less than £X?" where X is the applicable threshold
- On POST: saves conclusion to `IHTReckoner`, redirects to regime home
- Conclusion values: `not_payable` | `may_be_payable` | `knock_out`

**`IHTReckoner` model:**
| Field | Purpose |
|-------|---------|
| case | FK to Case |
| conclusion | `not_payable` / `may_be_payable` / `knock_out` |
| threshold | The threshold value used in the computation |

**Reckoner sections** (`RECKONER_SECTION` dict in `reckoner.py` maps HMRC_14
answers to section IDs):
- Single/never married → HMRC_S3 (built)
- Married/widowed → not yet built (D1)

### Show tailor condition

`_should_show_tailor` returns True when:
- S2 is complete, AND
- `reckoner_conclusion == 'may_be_payable'` OR `HMRC_13 answer contains 'No'`

---

## 7. Action button: Tailor your submission

**Concept:** The executor declares which asset and liability types are present
in the estate. This drives which further action buttons appear on the home page.

### Action button view

`iht_action_tailor` — thin wrapper:
```python
_set_current_action(request, 'tailor')
redirect → regime_home → iht_orchestrate (ENTRY)
```

### Entry

`_entry_tailor`:
1. `_enter_core` — sets `iht_in_core = True`
2. `call_core([{'type': 'schedule', 'id': 'HMRC_SCH1'}], title='Tailor your submission')` —
   routes to the schedule's section list (S4, S5, S6)

`HMRC_SCH1` is the source of truth for triage sections. Adding or reordering
sections in the schedule automatically updates the tailor journey — no code
changes needed.

### The three triage sections

| Section | Name | Questions |
|---------|------|-----------|
| HMRC_S4 | Common assets and liabilities | HMRC_16, 31, 17–19, 21–23 |
| HMRC_S5 | Pensions and life assurance | HMRC_24–30 |
| HMRC_S6 | Other assets and liabilities | HMRC_32–39 |

Each section contains one QuestionSet. All questions are `radio_inline`
type (Yes/No on one line). The user works through each section in any order.
On completing all three, they are returned to the IHT home page.

**Triage questions — HMRC_S4 (Common assets and liabilities):**
| ID | Question |
|----|----------|
| HMRC_16 | Did the deceased own any property in which they had lived at any point while they owned it? |
| HMRC_31 | Did the deceased own any other land, buildings or rights over land? |
| HMRC_17 | Did the deceased have any bank or building society accounts? |
| HMRC_18 | Did the deceased have any Premium Bonds or National Savings? |
| HMRC_19 | Did the deceased have any household goods or personal possessions? |
| HMRC_21 | Did the deceased make any gifts or other transfers of value in the 7 years before death? |
| HMRC_22 | Were there any other debts owed by the deceased (excluding any mortgage)? |
| HMRC_23 | Was any money owed to the deceased by way of personal loans? |

Note: HMRC_20 (jointly owned assets) excluded pending design — see D13.

**Triage questions — HMRC_S5 (Pensions and life assurance):**
| ID | Question |
|----|----------|
| HMRC_24 | Did any pension payments continue after the deceased's death? |
| HMRC_25 | Was a lump sum (death benefit) payable under a pension scheme? |
| HMRC_26 | Were any pension contributions made in the 2 years before death? |
| HMRC_27 | Were any sums payable by an insurance company to the estate as a result of the death? |
| HMRC_28 | Was the deceased covered by a jointly owned life assurance policy that continues after death? |
| HMRC_29 | Was the deceased entitled to benefit from a policy on someone else's life that continues after death? |
| HMRC_30 | Did any payments under a purchased life annuity continue after death? |

**Triage questions — HMRC_S6 (Other assets and liabilities):**
| ID | Question |
|----|----------|
| HMRC_32 | Did the deceased own any listed stocks, shares or ISAs? |
| HMRC_33 | Did the deceased own any unlisted stocks, shares or control holdings? |
| HMRC_34 | Did the deceased have any business or partnership interests? |
| HMRC_35 | Did the deceased own any agricultural property or farmland? |
| HMRC_36 | Did the deceased own any assets outside the UK? |
| HMRC_37 | Did the deceased have any right to benefit from assets held in trust? |
| HMRC_38 | Was the deceased entitled to receive any legacy from another estate not yet received? |
| HMRC_39 | Is any asset exempt on grounds of national or scientific heritage? |

### Exit

`_exit_tailor` — nothing to do. Falls through to `_render_home`.

The home page then shows triage set rows (see section 8 below).

### Dynamic question lookup

`_get_triage_question_ids(section_id)` reads question IDs dynamically from
`QuestionSetMember` via the section's routing — no hardcoded question lists.
This means adding a question in the admin tools automatically includes it in
the active items computation.

### Active items dict

`_get_active_triage_items(verified_case)` returns:
```python
{
    'HMRC_S4': [
        {'question_id': 'HMRC_16', 'detail_section': None},
        {'question_id': 'HMRC_17', 'detail_section': None},
    ],
    'HMRC_S5': [],   # no Yes answers
    'HMRC_S6': [...],
}
```

Only Yes-answered questions appear. `detail_section` is None — this field
is retained for backward compatibility but the asset detail navigation is
now driven by `QUESTION_SCHEDULE_MAP` and `_get_built_schedule_items`
(see section 8a below).

---

## 8. Home page

### Action list build

`_build_action_list` returns a list of lean dicts (logical state only):
```python
{
    'id':            str,   # unique row identifier
    'status':        str,   # not_started | in_progress | complete | ...
    'url':           str,   # action link href (or None)
    'flash_message': str,   # one-time message (or None)
    'hint':          str,   # sub-label hint (or None)
    'extra':         dict,  # additional data for screen layer
}
```

No labels, colours, or link text in this layer — that's screen.py's job.

Flash messages appear **below** the action row that generated them.

### Screen decoration

`screen.py / _decorate_actions` adds presentation fields:
- `label` — from `ACTION_LABELS` dict, or `Section.section_name` for triage rows
- `status_label` / `status_colour` — from `STATUS_DISPLAY` dict
- `link_label` — Start / View & amend / None
- `flash_message` — reckoner row gets persistent conclusion message as fallback

Section names for triage rows are read from the DB in a single query —
rename a section in the admin tools and the button label updates automatically.

### Triage set rows (Level 1)

Shown on home page once all three triage sections are complete. One row per
entry in `TRIAGE_SETS`. Status rolls up from `_triage_set_rollup`:

| Condition | Status |
|-----------|--------|
| No Yes answers + section complete | complete |
| No Yes answers + not complete | not_started |
| Any Yes with `detail_section = None` | in_progress |
| All Yes with complete detail sections | complete |
| Otherwise | in_progress |

Each row's URL is computed dynamically by `_get_built_schedule_items`:
- If at least one schedule for that set has a section built → real action URL
- If no schedules built yet → `#` (no Start link shown)

This gives progressive results — asset buttons appear and become clickable
as detail sections are built, without any code changes.

### Reckoner conclusion message

The reckoner row's `flash_message` shows a persistent conclusion message
(not a one-time flash) derived from `IHTReckoner.conclusion`:
- `not_payable` → "Based on your answers, no Inheritance Tax is payable..."
- `may_be_payable` → "Based on your answers, Inheritance Tax may be payable..."
- `knock_out` → "Based on your answers, you will need to complete a full IHT return."

---

## 8a. Action buttons: Triage asset sets (Common assets, Pensions, Other)

**Concept:** Once tailor is complete, one action button per triage set appears.
Clicking it enters a schedule list showing only the Yes-answered assets for
that set that have sections built. The list grows progressively as sections
are built.

### Key constants in `orchestrate.py`

**`TRIAGE_SETS`** — derived dynamically from `HMRC_SCH1` at startup:

```python
def _get_triage_sets():
    from core.models import ScheduleSection
    from django.db.models import F
    return list(
        ScheduleSection.objects
        .filter(schedule_id='HMRC_SCH1')
        .select_related('section')
        .order_by('display_order')
        .values('section_id', name=F('section__section_name'))
    )

TRIAGE_SETS = _get_triage_sets()
TRIAGE_SECTION_IDS = [t['section_id'] for t in TRIAGE_SETS]
```

`HMRC_SCH1` is the single source of truth. Adding a section to the schedule
in the admin tools automatically adds it to `TRIAGE_SETS` — no code changes
needed. `TRIAGE_SECTION_IDS` is derived from `TRIAGE_SETS` for status lookups.

**`QUESTION_SCHEDULE_MAP`** — maps triage question IDs to asset schedule IDs:

```python
QUESTION_SCHEDULE_MAP = {
    'HMRC_16': 'HMRC_SCH2',   # Residential property
    'HMRC_31': 'HMRC_SCH3',   # Other land, buildings and rights over land
    'HMRC_17': 'HMRC_SCH4',   # Bank and building society accounts
    'HMRC_18': 'HMRC_SCH5',   # Premium Bonds and National Savings
    'HMRC_19': 'HMRC_SCH6',   # Household goods and personal possessions
    'HMRC_21': 'HMRC_SCH7',   # Gifts and transfers of value
    'HMRC_22': 'HMRC_SCH8',   # Other debts
    'HMRC_23': 'HMRC_SCH9',   # Personal loans owed to the deceased
}
```

### Action button views and URLs

Action button views are named using section IDs as slugs — consistent with
core URL conventions. No human-readable slugs:

```python
# urls.py
path('iht/action/hmrc_s4/', views.iht_action_hmrc_s4, name='iht_action_hmrc_s4'),
path('iht/action/hmrc_s5/', views.iht_action_hmrc_s5, name='iht_action_hmrc_s5'),
path('iht/action/hmrc_s6/', views.iht_action_hmrc_s6, name='iht_action_hmrc_s6'),
```

The URL for each triage set row is built dynamically:
```python
action_url = reverse(f'dept_hmrc:iht_action_{triage_set["section_id"].lower()}')
```

Adding a fourth triage set: add section to HMRC_SCH1 in admin, add one
view and one URL entry in urls.py. Everything else follows automatically.

### Helper: `_get_built_schedule_items`

```python
_get_built_schedule_items(active_items, section_id, QUESTION_SCHEDULE_MAP)
```

1. Reads Yes-answered question IDs from `active_items[section_id]`
2. Maps each to a schedule ID via `QUESTION_SCHEDULE_MAP`
3. Filters to schedules that have at least one section in DB
4. Returns ordered list of `{'type': 'schedule', 'id': schedule_id}` dicts

Returns `[]` if nothing built yet → button stays at `#`, no Start shown.

### Entry

`_entry_triage_assets(request, regime, actor, user, verified_case, section_id)`:
1. Calls `_get_built_schedule_items` for the given `section_id`
2. If empty → returns None → falls through to home (no navigation)
3. `_enter_core` — sets `iht_in_core = True`
4. `call_core(items, title=triage_set['name'], url_prefix='hmrc')`
5. Redirects to entry URL (schedule list or direct to single schedule's sections)

The function is shared across all three triage sets — `section_id` and `title`
are passed dynamically.

### Exit

Nothing to do. Falls through to `_render_home`.

---

## 9. `radio_inline` question type

A question type for triage questions. Renders Yes/No options on the same
line as the question text (GDS `govuk-radios--inline`).

- Model: `question_type = 'radio_inline'`
- Template: `core/templates/core/question_radio_inline.html`
- Set template: handled in `question_set.html` via
  `{% if field.question_type == 'radio_inline' %}` adding
  `govuk-radios--inline` class
- Dispatch: `views_layer2.py` template map includes
  `'radio_inline': 'core/question_radio_inline.html'`

All 24 triage questions (HMRC_16–HMRC_39) use `radio_inline`.

Note: `radio_inline` not yet supported in type-2 row journey templates
(`table_routed_question.html`, `table_routed_set.html`) — see D20.

---

## 10. `call_core` — the unified core entry point

`call_core` in `core/interfaces.py` is the single entry point for all dept
navigation into core. It replaces `call_regime`, `call_schedules`, and
`call_sections` (which remain as thin wrappers for backward compatibility).

`call_core(request, regime, actor, user, items, title=None, url_prefix='')`

`items` is an ordered list of `{'type': 'schedule'|'section', 'id': str}` dicts.

**Routing logic:**
- Empty after permission filter → empty section list fallback
- Single section → direct to `section_start`
- Single schedule → direct to `regime_schedule_sections`
- Multiple items → `regime_top_level` (mixed ordered list page)

**Permission intersection:** always intersects `items` with
`get_permitted_sections` for the current user. Dept-specified items narrow
the permission-derived list; they never expand it.

**`return_url`** is always set to `regime_home_url` from session — core
always returns to the dept orchestrator.

See Core Platform Reference section 5 for full detail.

---

## 11. What is deferred

| Item | Backlog ref |
|------|-------------|
| Reckoner parts 1 and 2 (married, widowed) | D1 |
| S1 amend conflict — `duplicate_amend.html` template and answer restoration | D7 |
| Jointly owned assets triage design | D13 |
| Nil rate band transfers | D14 |
| IHT405 property sections (type-2 table sections) | D18 — NOW |
