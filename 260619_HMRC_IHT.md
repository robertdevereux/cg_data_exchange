# HMRC IHT — Technical Reference
Date: 19 June 2026
Status: Current — reflects code as at end of sprint 3

This document covers the IHT (Inheritance Tax) regime implementation in full.
It replaces and supersedes:
- 260616_IHT_Orchestration_Logic.md
- 260616_IHT_Tailoring_Flow.md
- The IHT sections of 260616_HMRC_Reference.md

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
happens in `iht_orchestrate` on return from core. `call_sections` sets
`return_url = regime_home_url` so core always returns here.

---

## 3. `iht_orchestrate` — the dispatcher

```
Every visit to /hmrc/regime/HMRC_IHT/
    ↓
_setup() — regime, actor, user, session, crumbs
    ↓
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
    None             → _render_home()
    ↓
if returning_from_core:              ← EXIT
    start            → _exit_start()
    deceased_details → _exit_deceased_details()
    reckoner         → _exit_reckoner() [may re-enter core]
    tailor           → (nothing) → fall through
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
3. `call_sections(['HMRC_S1'])` — sends user into S1
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
2. `call_sections(['HMRC_S1'])` — sends user into S1 (re-entry, shows review)

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

**Concept:** A series of questions to determine whether IHT is likely payable,
and if so whether the executor needs to complete a full return.

### Action button view

`iht_action_reckoner` — thin wrapper:
```python
_set_current_action(request, 'reckoner')
redirect → regime_home → iht_orchestrate (ENTRY)
```

### Entry

`_entry_reckoner` — delegates to `handle_reckoner`:

`handle_reckoner` reads HMRC_13 and HMRC_14 then decides:
- HMRC_13 = No (executor doesn't want help) → returns None → render home
- HMRC_13 = Yes + HMRC_14 maps to a built section → calls that section
- HMRC_13 = Yes + HMRC_14 maps to unbuilt section → returns None

**Key questions:**
| ID | Question | Role |
|----|----------|------|
| HMRC_6 | Is the deceased domiciled in the UK? | S2 gateway |
| HMRC_7 | Did the deceased have a surviving spouse/civil partner? | S2 routing |
| HMRC_13 | Would you like help working out if IHT is payable? | Reckoner gateway |
| HMRC_14 | What was the deceased's marital status at death? | Selects reckoner section |

**Reckoner sections** (HMRC_S3 currently built — single/never married):

`RECKONER_SECTION` dict in `reckoner.py` maps HMRC_14 answers to section IDs.

### Exit

`_exit_reckoner` — delegates to `handle_reckoner` again:
- If S3 not complete → `handle_reckoner` sets `iht_in_core = True` and
  enters S3. `_exit_reckoner` re-sets `iht_in_core = True`.
- If S3 complete and `IHTReckoner` exists → returns None → render home
- If S3 complete but no `IHTReckoner` → calls `get_reckoner_state` →
  redirects to `iht_reckoner_threshold`

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
2. `call_sections(TRIAGE_SECTION_IDS, title='Tailor your submission')` —
   shows a filtered section list page with S4, S5, S6

Because `call_sections` receives multiple section IDs, it writes
`permitted_section_ids` and `section_list_title` to session and routes to
`regime_sections` (the core section list view). The user sees a titled page
listing the three sections with status badges and Start/Continue links.

### The three triage sections

| Section | Name | Questions |
|---------|------|-----------|
| HMRC_S4 | Common assets and liabilities | HMRC_16–23 |
| HMRC_S5 | Pensions and life assurance | HMRC_24–30 |
| HMRC_S6 | Other assets and liabilities | HMRC_31–39 |

Each section contains one QuestionSet. All questions are `radio_inline`
type (Yes/No on one line). The user works through each section in any order.

**Triage questions — HMRC_S4 (Common assets and liabilities):**
| ID | Question |
|----|----------|
| HMRC_16 | Did the deceased own a home? |
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
| HMRC_31 | Did the deceased own any other land, buildings or property (not their principal home)? |
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

Only Yes-answered questions appear. `detail_section` is None until detail
sections are built — this is the extension point for D2 (estate detail
sections).

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

Each row currently points at `#` — Level 2 sub-pages are deferred (D2).

### Reckoner conclusion message

The reckoner row's `flash_message` shows a persistent conclusion message
(not a one-time flash) derived from `IHTReckoner.conclusion`:
- `not_payable` → "Based on your answers, no Inheritance Tax is payable..."
- `may_be_payable` → "Based on your answers, Inheritance Tax may be payable..."
- `knock_out` → "Based on your answers, you will need to complete a full IHT return."

---

## 9. `radio_inline` question type

A new question type added for triage questions. Renders Yes/No options
on the same line as the question text (GDS `govuk-radios--inline`).

- Model: `question_type = 'radio_inline'`
- Template: `core/templates/core/question_radio_inline.html`
- Set template: handled in `question_set.html` via
  `{% if field.question_type == 'radio_inline' %}` adding
  `govuk-radios--inline` class
- Dispatch: `views_layer2.py` template map includes
  `'radio_inline': 'core/question_radio_inline.html'`

All 24 triage questions (HMRC_16–HMRC_39) use `radio_inline`.

---

## 10. `call_sections` — multiple section behaviour

`call_sections` in `core/interfaces.py` now handles both single and
multiple section IDs:

**Single section ID:**
Goes directly to that section's start URL. Existing behaviour.

**Multiple section IDs:**
Writes `permitted_section_ids` and `section_list_title` to session, then
routes to `regime_sections` (the core section list view). `regime_sections`
filters its queryset to `permitted_section_ids` — overriding the normal
`schedule__isnull=True` filter — and uses `section_list_title` as the
page heading.

`call_sections` always sets `return_url = regime_home_url` (from session),
not `request.path`. This ensures core always returns to the dept orchestrator.

---

## 11. What is deferred

| Item | Backlog ref |
|------|-------------|
| S1 amend conflict — `duplicate_amend.html` template and answer restoration | D7 |
| Level 2 sub-pages for triage rows (detail sections per asset type) | D2 |
| Jointly owned assets triage design | D13 |
| Nil rate band transfers | D14 |
| Reckoner parts 1 and 2 (married, widowed) | D1 |
| `call_schedules` single-schedule behaviour | D15 |
