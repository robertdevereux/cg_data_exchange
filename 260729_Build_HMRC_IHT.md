# HMRC IHT — Technical Reference
Date: 29 July 2026
Status: Current — reflects code as at 29 July 2026

This document covers the IHT (Inheritance Tax) regime implementation in full.

---

## 1. Overview

The IHT regime allows an executor to submit an Inheritance Tax return online.
The PoC implements the triage and ready reckoner stages — full form completion
is deferred.

**Key concepts:**
- **Estate** — the deceased person's assets and liabilities
- **Executor (actor)** — the person completing the submission (logged in)
- **Deceased (user/subject)** — **(new concept, 5 July 2026)** a synthetic,
  login-incapable `User` record created once an estate is verified,
  representing the deceased. `case.user` points at this record, not at the
  executor. See section 3a below for the full lifecycle.
- **IHT reference** — a unique reference (IHT-000000001 format) assigned once
  the estate is verified as unique in the system
- **Verified case** — a Case record with a non-null reference; the estate has
  passed duplicate checking

**File structure:**
```
dept_hmrc/views/iht/
  orchestrate.py   — regime controller; all dispatch logic
  screen.py        — rendering only; decorates lean action state
  matching.py      — duplicate checking, reference generation, and
                     (new) deceased-identity promotion
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

Three session keys drive the two-phase dispatch:

| Key | Who sets it | Who reads it | Purpose |
|-----|------------|--------------|---------|
| `return_url` (PSS) | `call_core` (sets to `regime_home_url`) | core execution engine (`section_done`) | Ensures core always returns to `iht_orchestrate` after a section completes |
| `iht_in_core` | `_enter_core` (sets True before every `call_core` call) | `iht_orchestrate` (pops on every visit) | Distinguishes ENTRY (False/absent) from EXIT (True, then immediately cleared) |
| `iht_current_action` | The thin action button view (e.g. `iht_action_reckoner`) | `iht_orchestrate` (ENTRY branch — selects `_entry_*`; EXIT branch — selects `_exit_*`) then cleared | Identifies which action button pair is active |

**Timing note:** `iht_in_core` is set *just before* calling `call_core`, and popped *on the very next visit* to `iht_orchestrate` (i.e., when core returns). `iht_current_action` persists across the full round-trip and is cleared by `iht_orchestrate` after the exit handler runs. `return_url` is set by `call_core` and immediately overwritten by any Layer 1 list view visited during the journey — but in all HMRC IHT flows the journey ends with `section_done`, which reads the current `return_url` (still `regime_home_url` if no Layer 1 view was visited) and redirects back here.

Two session flags control dispatch (summary):

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

**Known tech debt, not yet resolved (flagged 5 July 2026, confirmed by
coherence audit 7 July 2026):** there are currently **two different code
paths for starting a new estate**: `_entry_start` (the original bootstrap
path — renders an interim "pre-verified" screen via `iht_screen_unverified`
before entering S1) and `iht_start_new_estate` (added for the multi-estate
picker's "Begin a new estate" option — skips the interim screen and enters
S1 directly). These diverge in behaviour and should be reconciled, most
likely by having `iht_start_new_estate` become `_entry_start`'s path with a
flag rather than a separate implementation. Left as a backlog item for a
dedicated review.

---

## 3. `iht_orchestrate` — the dispatcher

```
Every visit to /hmrc/regime/HMRC_IHT/
    ↓
_setup() — regime, actor, pss, crumbs (NOT user — see below)
    ↓
if no user_id in session → _iht_gate() (acting-for / estate picker)
    ↓
current_action = read iht_current_action
returning_from_core = pop iht_in_core
    ↓
Resolve case + user from the DATABASE, not session cache (changed 5 July 2026):
    case_id = session.get('case_id')
    case = Case.objects.filter(case_id=case_id, regime=regime).first()
    if case:
        user = case.user            ← authoritative; correct whether
        verified_case = case if case.reference else None   draft or verified
    elif other verified cases exist for this actor:
        → _iht_gate()  (re-show the picker; case_id was cleared)
    else:
        user = <actor's own default user>
        verified_case = None
    ↓
Bootstrap: if no verified_case and no current_action
    → set current_action = 'start'
    ↓
if not returning_from_core:          ← ENTRY
    start            → _entry_start()       [renders, does not redirect — shows
                                             pre-verified home with entry button]
    deceased_details → _entry_deceased_details()
    reckoner         → _entry_reckoner()
    tailor           → _entry_tailor()
    hmrc_s4/s5/s6   → _entry_triage_assets(section_id)
                                            [returns None if no built schedules
                                             for this triage section; caller
                                             falls through to _render_home()]
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

Note: iht_start_new_estate is NOT dispatched by this table. It is reached
directly via the acting-for gate's "Begin a new estate" option and bypasses
iht_orchestrate's ENTRY logic entirely — it creates a draft case then enters
S1 directly, without rendering the pre-verified home screen.
```

**Why case/user resolution changed (5 July 2026):** the previous version
cached `user_id` in session (set once by the acting-for gate) and separately
tried to match `session['case_id']` against a list of verified cases. This
broke the moment a draft case was promoted to verified mid-session — the
newly-promoted case's owner (`case.user`) is the deceased, not the cached
actor id, so the match failed, `user` silently fell back to the actor, and
the just-completed section showed as "Not started" (the actor genuinely has
no `SectionStatus` rows for a case they no longer own). The fix removes the
cache: `user` is now derived fresh from `case.user`, read straight from the
database, on every request. See Core Platform Reference section 5 for the
general principle this illustrates.

---

## 3a. Deceased identity lifecycle (new, 5 July 2026)

Every IHT case needs a distinct **subject** identity (the deceased),
separate from the **actor** (the executor), for two reasons: (1) it is the
architecturally honest model — the answers are about the deceased, not the
executor — and (2) without it, the platform's cross-case pre-population
feature (`section_question`'s "suggested from a prior case" banner, which
is deliberately actor-scoped platform-wide) would silently offer up one
deceased person's name/DOB/NINO as a suggested answer when the same
executor starts a *second* estate. This was a real, observed bug before
the fix landed.

**Sequence, tied to matching (`_exit_start` in `orchestrate.py`,
`_promote_case_to_verified` in `matching.py`):**

1. Executor answers S1. Answers are captured **provisionally under the
   actor** (`user=actor`) — at this point we don't yet know if this is a
   new person (matching hasn't run), so there's no identity to create yet.
2. `run_iht_matching(draft_case)` runs.
3. **Duplicate found** → the draft's `Answer` rows (owned by the actor) are
   deleted, the draft `Case` itself is deleted, `case_id` is cleared from
   session, and the dead-end page is shown. Nothing is left behind that
   could later surface as a pre-population suggestion on the actor's own
   future estates.
4. **Unique** → `matching._promote_case_to_verified(case, actor, deceased_name)`,
   a thin coordinator in `matching.py` that:
   - Creates a new, **inactive** `User` (`username='ihtsubject_<case pk>'`,
     `set_unusable_password()`, no email needed) representing the deceased,
     using the name captured in HMRC_1.
   - Generates the IHT reference string.
   - Then delegates to `interfaces.promote_case_to_verified(case, actor,
     deceased, reference)`, which atomically (`@transaction.atomic`):
     - Re-keys the case's already-written `Answer` and `SectionStatus` rows
       from the actor to the new `User`. **`AnswerHistory` rows are NOT
       re-keyed** — they remain owned by the actor; this is an accepted
       limitation, not a bug.
     - Sets `case.user` to the deceased identity and `case.reference` to the
       generated reference.
     - Grants the actor a case-scoped `Permission`
       (`actor=<executor>, user=<deceased>, regime=HMRC_IHT, case=<case>,
       section=None` — the "all sections of that specific case" shape
       already supported by the Permission model, no schema change needed).
5. From this point on, every read/write of this case's answers uses
   `case.user` (the deceased), never the actor — see the correctness rule
   in Core Platform Reference section 4a.

**Amending an already-verified estate** (`_exit_deceased_details`) does
not repeat identity creation — the case already has its deceased identity;
matching simply re-runs against the amended answers to catch a newly-
created conflict.

**Cleanup script convention:** any one-off data-fix script touching IHT
cases should be written as a Django management command, run once, then
**deleted** — this was the pattern used twice on 5 July 2026 (QuestionSet
ID rename; stale pre-fix-estate cleanup) and should be followed for any
future one-off fix rather than left as permanent, unused code.

---

## 3b. Acting-for gate and the estate picker

**(Replaces the earlier `iht_case_picker`/`iht_select_case` design from
1 July 2026, itself replaced on 5 July 2026 — see below.)**

IHT uses the platform's shared, regime-scoped acting-for gate
(`core.views_gate.choose_user_for_regime` — see Core Platform Reference
section 6a) via a thin wrapper:

```python
def _iht_gate(request, regime):
    new_url  = reverse('dept_hmrc:iht_start_new_estate')
    self_url = f"{reverse('core:select_self')}?{urlencode({'next': new_url})}"
    return choose_user_for_regime(
        request, regime=regime,
        leading_option={'label': 'Begin a new estate', 'action_url': self_url},
        next_url=reverse('dept_hmrc:regime_home', kwargs={'regime_id': regime.regime_id}),
    )
```

**IHT never offers "Myself"** as the leading option, unlike every other
regime — structurally, the executor is never the subject. The leading
option is always "Begin a new estate," present even when the executor has
no other estates yet (this is how the very first estate gets started).
Named candidates beyond the leading option are the executor's other
verified estates, sourced from their case-scoped `Permission` rows, each
labelled with the deceased's name (read from the synthetic `User`'s
`first_name`/`last_name`, set at promotion — see 3a). Selecting one writes
that Permission's `case_id` into session and proceeds straight to that
estate's home page — no second, IHT-specific picker page in between.

**Auto-skip rule (inherited from the shared gate):** with zero prior
estates, "Begin a new estate" is the only candidate, so the screen is
skipped entirely and the executor goes straight into starting one. With
one or more prior estates, the screen always shows (never auto-skips),
since "begin a new estate" vs "continue an existing one" is a genuine
choice — this was a deliberate correction after an earlier version
special-cased the "exactly one prior estate" case to auto-skip it, which
incorrectly removed the only way to start a *second* estate.

**Retired, 5 July 2026:** the earlier `iht_case_picker`/`iht_select_case`
views, built on 1 July as IHT-specific multi-case disambiguation before
the deceased-identity split existed. Once every estate has its own
synthetic subject, that disambiguation problem is already solved one level
up by the shared gate — the IHT-specific picker was doing the same job
worse (e.g. a picker offering only "James Bond" as a redundant confirmation
after already selecting "James Bond" at the gate).

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

`iht_start_new_estate` (reached via the acting-for gate's "Begin a new
estate" option) does the equivalent job for the multi-estate case, but
currently skips step 4 and enters S1 directly — see the tech-debt note in
section 2 above. It also calls `reset_section_progress(user, regime)` before
creating the new Case, to clear any stale `SectionStatus` rows left by a
previous incomplete draft on the same actor account.

**S1 questions (HMRC_S1), current structure as of 5 July 2026:**

| ID | Question | Type | Notes |
|----|----------|------|-------|
| HMRC_1 | Deceased's name | personal_name | Used by matching (last name) |
| HMRC_2 | Deceased's date of death | date | Used by matching (dod_raw) |
| HMRC_3 | Deceased's date of birth | date | |
| HMRC_4 | Deceased's National Insurance number | text | |
| HMRC_14 | At the time of their death, was the deceased married, or in a civil partnership? | radio (Yes/No) | Branching |
| HMRC_43 | Had the deceased previously been married or in a civil partnership that ended on the death of their spouse or civil partner? | radio (Yes/No) | Only asked if HMRC_14 = No |
| HMRC_5 | Did the deceased leave a will? | radio | |

Routing: HMRC_1 → HMRC_2 → HMRC_3 → HMRC_4 → HMRC_14 → **[Yes]** HMRC_5 /
**[No]** HMRC_43 → HMRC_5 → END.

**This replaces an earlier, inaccurate version of this table** that showed
separate Title/First name/Last name questions and a different HMRC_2–5
mapping — that had drifted from reality independently of tonight's work.
HMRC_14 was restructured on 5 July 2026 from a three-way
single/married/widowed choice into two sequential Yes/No questions
(HMRC_14 + HMRC_43), built using the newly-fixed section-routing admin
tools (see Core Platform Reference section 8). **Downstream impact not yet
addressed:** anything needing "is this estate married / widowed / single-
or-divorced" as one concept (e.g. the reckoner section-selection logic in
section 6, and the Q1 marital gate described in the IHT journey
architecture doc informing D18) will need a small derived helper reading
both HMRC_14 and HMRC_43 together, rather than one raw answer. Not built
yet — flagged for whenever that logic is next touched.

### Exit

`_exit_start` — called when user returns from S1 for the first time:
1. Finds the draft case (reference still null)
2. Calls `run_iht_matching(draft_case)` — compares last name + date of death
   against all other verified cases
3. **If duplicate** → deletes the draft's `Answer` rows and the draft `Case`
   itself, clears `case_id` from session, renders `duplicate.html` — dead
   end, user told estate already exists (see section 3a)
4. **If unique** → `_promote_case_to_verified` creates the deceased
   identity, re-keys answers, assigns reference (see section 3a), flashes
   confirmation message, redirects to regime home

Reference format: `IHT-000000001` (sequential, zero-padded to 9 digits).

**Matching logic** (`run_iht_matching`):
- Compares `last_name` and `dod_raw`, read via direct `get_answers(case,
  ['HMRC_1', 'HMRC_2'])` — **deliberately left using this direct extraction
  rather than the new `get_asked_answers_for_section` helper** (see section
  8 below), since this is structural data extraction for an algorithm, not
  display formatting.
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

**Depends on the `case.user` fix (5 July 2026):** `section_start`'s
existing-answers check previously read `Answer.objects.filter(user=
request.user, ...)` — since `request.user` is the actor, not `case.user`,
this always found nothing for a verified case (whose answers belong to the
deceased), sending the executor to a blank HMRC_1 instead of the review
page. Fixed in `core/views_layer2.py`; see Core Platform Reference section
4a for the full correctness rule.

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

### Section structure

| Section | Name | Questions |
|---------|------|-----------|
| HMRC_S1 | Create a new draft estate submission | HMRC_1–4, HMRC_14, HMRC_43, HMRC_5 — see section 4 |
| HMRC_S2 | Ready Reckoner Access | HMRC_13 only |
| HMRC_S3 | Ready reckoner 1A | Reckoner questions (single/never married) |

**HMRC_S2 routing:** HMRC_13 → END (unconditional single route, no branching).

### Key questions

| ID | Question | Role |
|----|----------|------|
| HMRC_13 | Would you like help working out if IHT is payable? | Reckoner gateway |
| HMRC_14 | At the time of their death, was the deceased married, or in a civil partnership? | Now Yes/No; selects reckoner section; collected in S1 — see section 4 |

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

### Exit

`_exit_reckoner` — delegates to `handle_reckoner`:

`handle_reckoner` reads HMRC_13 (from S2), HMRC_14, and HMRC_43 (both from S1):
- **HMRC_13 = No** → deletes any stale `IHTReckoner` row → returns None
  → tailor button appears (if `_should_show_tailor` is satisfied)
- **HMRC_13 = Yes, HMRC_14 = No, HMRC_43 = No** → single route → HMRC_S3 (built)
- **HMRC_13 = Yes, HMRC_14 = Yes** → married route → None (not yet built)
- **HMRC_13 = Yes, HMRC_14 = No, HMRC_43 = Yes** → widowed route → None (not yet built)
- **answers absent or unexpected** → None

The stale `RECKONER_SECTION` dict and `HMRC14_*` string constants have been
removed. Routing now uses explicit field-based branching on HMRC_14 + HMRC_43
(verified 5 July 2026). The single route (HMRC_14=No, HMRC_43=No) is built
and correctly gated; married (HMRC_14=Yes) and widowed (HMRC_14=No, HMRC_43=Yes)
routes are not yet built and return None.

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

**Reckoner sections** (explicit branching in `reckoner.py` on HMRC_14 + HMRC_43):
- HMRC_14=No, HMRC_43=No (single/never married) → HMRC_S3 (built)
- HMRC_14=Yes (married) → not yet built (D1)
- HMRC_14=No, HMRC_43=Yes (widowed) → not yet built (D1)

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

Each section contains one QuestionSet (ID convention `SET{N}` — see Core
Platform Reference section 3). All questions are `radio_inline` type
(Yes/No on one line). The user works through each section in any order.
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

**Resolved (31 July 2026, `df0f1b2`):** the vacuous-"Complete" issue was
confirmed as zero-Yes-answer categories appearing as "Complete" rather than
being suppressed. See §8a below for the fix and the replacement behaviour.

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

### Deceased-details display — now routing-driven (changed 5 July 2026)

The "This estate relates to" summary previously hand-mapped a fixed list
of five question IDs (`HMRC_1–4, HMRC_14`) to named template fields —
which could not reflect HMRC_14's new Yes/No shape, could not show the new
HMRC_43 follow-up at all, and displayed a hardcoded "Marital status" label
regardless of the question actually asked. `_render_home` now builds this
list generically:

```python
hmrc_s1 = Section.objects.get(section_id='HMRC_S1')
deceased_rows = [
    {'label': row['question_text'],
     'value': format_answer_for_display(row['question_type'], row['answer'])}
    for row in get_asked_answers_for_section(verified_case, hmrc_s1)
]
```

using the two new shared `core.interfaces` functions (see Core Platform
Reference section 5). This walks HMRC_S1's actual routing against the
case's confirmed answers, so the displayed rows always match the path
genuinely taken — HMRC_43 appears only when HMRC_14 was answered "No."
The IHT reference number remains a separate, hardcoded template field
(case metadata, not a question answer) — matching's own raw extraction of
`last_name`/`dod_raw` is likewise untouched (see section 4).

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
entry in `TRIAGE_SETS` **where the category has at least one Yes-answered
triage question**. Categories with zero Yes answers are omitted entirely —
see §8a. Status rolls up from `_triage_set_rollup` for non-empty categories:

| Condition | Status |
|-----------|--------|
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
    """
    Section has a direct FK to Schedule (with display_order on Section
    itself) — there is no separate ScheduleSection join model. (Corrected
    2 July 2026 — an earlier version of this function imported a
    ScheduleSection model that does not exist, which crashed the entire
    app at startup, not just this function, since TRIAGE_SETS is built at
    module import time.)
    """
    from django.db.models import F
    return list(
        Section.objects
        .filter(schedule_id='HMRC_SCH1')
        .order_by('display_order')
        .values('section_id', name=F('section_name'))
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

### Action-list empty-category fix (31 July 2026, `df0f1b2`)

Prior to this fix, triage categories with zero Yes-answered questions appeared
on the home page as "Complete" — because `_triage_set_rollup` returned
`'complete'` for the empty-set case when the triage section itself was marked
complete. This was misleading: "Complete" implied there was nothing to do
because the executor had finished their asset entries, but in fact there were
simply no Yes answers.

**Fix:** `_build_action_list` now checks `if not set_items: continue`
immediately after `set_items = active_items.get(sid, [])`, before passing
to `_triage_set_rollup`. A category with no Yes answers is omitted from
the `actions` list entirely — it produces no home-page row at all.

**`_triage_set_rollup`'s empty-set branch** (`if not set_items: return 'complete'
if section complete else 'not_started'`) is now only reached during the
`_triage_set_rollup` path for tailor's own status computation (which checks
whether *all* triage sections are complete, regardless of content) — not for
the per-category row display.

### Planned: Tailor exit gate (NOW backlog, not yet built)

Once all three triage sections are submitted, `_build_action_list` will add
triage-set rows for Yes-answered categories. The current code has no check
at this point for whether those Yes answers have corresponding built sections
— if `QUESTION_SCHEDULE_MAP` maps a Yes-answered question to a schedule that
has no Sections in the DB yet, the action URL is `#` and the button is a
dead end.

**Planned gate** (see Backlog, NOW): after triage completion, check every
Yes-answered question against `QUESTION_SCHEDULE_MAP` and built-section
status (reusing `_get_built_schedule_items`'s logic). If any Yes-answered item
has no built section, redirect to a holding page naming the specific unbuilt
items rather than rendering a dead-end action list. Log which triage questions
triggered each block for beta prioritisation.

**Current confirmed gap (live DB query, 31 July 2026):** only HMRC_S4
(property) has `QUESTION_SCHEDULE_MAP` entries — `HMRC_16` → `HMRC_SCH2`
(residential property) and `HMRC_31` → `HMRC_SCH3` (other land/buildings).
HMRC_S5 (pensions and life assurance, questions HMRC_24–30) and HMRC_S6
(other assets, HMRC_32+) have **no** `QUESTION_SCHEDULE_MAP` entries and
no allocated Schedule records at all. Any Yes answer in those categories
currently produces a `#` URL. Until the gate is built, users with pensions
or other-asset Yes answers will see a dead-end button for those categories
on the home page.

**Note for S5/S6 design:** pension sub-types (state pension / workplace
pension / personal pension / life assurance) are likely different HMRC forms
and almost certainly cannot share one schedule the way S4's property fork
does. Do not assume 1-category-to-1-schedule — see Backlog LATER item.

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

`radio_inline` is now fully supported in type-2 row journey templates
(D20 complete, `ae9353e`, 30 July 2026). `table_routed_set.html` already
handled it correctly (used as reference). `table_routed_question.html` was
fixed by extending the branch condition to
`question.question_type == "radio" or question.question_type == "radio_inline"`,
with `govuk-radios--inline` applied conditionally. Both templates are correct.

---

## 10. `call_core` — the unified core entry point

`call_core` in `core/interfaces.py` is the single entry point for all dept
navigation into core. It replaced `call_regime`, `call_schedules`, and
`call_sections`. `call_schedules` and `call_sections` have been removed.
`call_regime` remains as a thin convenience wrapper.

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

## 11. HMRC_S8 — IHT405 property section (type-2 routed table)

*Routing read directly from live DB (15 August 2026). 30 rows.*

HMRC_S8 is the "Deceased's residence / property" section. Each property is
one row in a repeating type-2 table. The row journey uses compound-condition
routing (`alternate_condition_id='HMRC_14'`) at multiple branch points to
branch on marital status (answered in S1) without re-asking it.

`display_question_ids = 'HMRC_45;HMRC_46;HMRC_47'` — the summary table
columns are the property address/reference (HMRC_45, inside SET10), the
ownership type (HMRC_46), and the open market value (HMRC_47).
`show_confirmation = True`.

### 11a. Questions

| ID | Type | Question (abbreviated) |
|----|------|------------------------|
| SET10 | QuestionSet | Property description and reference (includes HMRC_45) |
| HMRC_47 | number | Open market value of the whole asset (£) |
| HMRC_46 | radio | How was this asset owned? |
| HMRC_48 | number | How many joint tenants owned this property in total? |
| HMRC_49 | number | How many tenants in common owned this asset? |
| HMRC_50 | radio | Is the deceased's spouse/civil partner one of the other owners? |
| HMRC_51 | radio | Did the deceased own an equal share with other tenants in common? |
| HMRC_52 | number | What was the deceased's share of this asset (%)? |
| HMRC_55 | radio | How much of the deceased's share passes to the surviving spouse/civil partner? |
| HMRC_54 | radio | Was the portion passing to the spouse specified as a value or a share? |
| HMRC_61 | number | What value (£) passes to the spouse? |
| HMRC_62 | number | What percentage of the deceased's share passes to the spouse? |
| HMRC_60 | radio | Is the property value supported by a written professional valuation? |
| HMRC_56 | radio | Was the property owned Freehold or Leasehold? |
| HMRC_57 | radio | Was the property let? |
| HMRC_58 | radio | Was the property value subject to any special factors? |
| HMRC_59 | radio | Has the property been sold within 12 months of death? |

HMRC_14 (marital status, answered in HMRC_S1) is referenced by routing rows
via `alternate_condition_id` but is never asked again inside HMRC_S8.
HMRC_48 (number of joint tenants) is similarly referenced as slot-2 source
by the HMRC_50 routing row.

### 11b. Row journey — top-level flow

**Value-before-ownership ordering:** The journey collects the open market
value (HMRC_47) *before* asking ownership type (HMRC_46). This is the live
routing order; the display column order in `display_question_ids` differs.

```
SET10 → HMRC_47 → HMRC_46 → [ownership fork]
```

**HMRC_46 ownership fork (three-way + compound condition on HMRC_14):**

| HMRC_46 answer | HMRC_14 (slot 2) | → next |
|---|---|---|
| Sole ownership of the deceased | Yes (married) | HMRC_55 (spousal destination) |
| Sole ownership of the deceased | not Yes | HMRC_60 (valuation gate) |
| Joint names | — | HMRC_48 (number of joint tenants) |
| Tenants in common | — | HMRC_49 (number of TIC owners) |

The first two rows are a compound condition: slot-1 tests HMRC_46='Sole
ownership of the deceased', slot-2 tests `alternate_condition_id='HMRC_14'`
= 'Yes'. Second row has slot-1 only (sole ownership, no marital test).

### 11c. Joint names branch

```
HMRC_48 (how many joint tenants?)
  HMRC_14='Yes' (slot-2 only) → HMRC_50 (is spouse one of the owners?)
  unconditional              → HMRC_60

HMRC_50 (spouse is one of owners?)
  'Yes' AND HMRC_48='2' (compound: both slots) → END
        ↳ Only 2 JTs and spouse is one: deceased's 50% share passes wholly to spouse
  'Yes' (slot-1 only, HMRC_48≠2)              → HMRC_60
        ↳ 3+ JTs including spouse: partial share, needs valuation
  'No' (slot-1 only)                           → HMRC_60
```

The HMRC_50 compound row (`slot-1='Yes'`, `alternate_condition_id='HMRC_48'`,
`slot-2='2'`) is the only row in HMRC_S8 that uses a non-HMRC_14 external
reference for slot 2. HMRC_48 is itself a node within HMRC_S8 (asked earlier
in the joint-names path), so it is NOT in `external_condition_qids` — it
will be in `row_data` from the row journey session.

If not married (HMRC_14≠'Yes'): HMRC_48 → HMRC_60 directly (no spousal
question, full 1/N share is in the estate, straight to valuation gate).

### 11d. Tenants in common branch

```
HMRC_49 (how many TIC owners?) → HMRC_51 (unconditional)

HMRC_51 (equal share with other TIC owners?)
  'Yes' AND HMRC_14='Yes' (compound) → HMRC_55 (spousal destination)
  'Yes' (slot-1 only, not married)   → HMRC_60
  'No' (slot-1 only)                 → HMRC_52 (deceased's % share)

HMRC_52 (deceased's percentage share — when unequal)
  HMRC_14='Yes' (slot-2 only) → HMRC_55 (spousal destination)
  unconditional               → HMRC_60
```

HMRC_55 is the shared spousal-destination question reached by three distinct
paths: sole ownership + married; TIC + equal share + married; TIC + unequal
share + married. Joint names does NOT route to HMRC_55.

### 11e. Spousal destination sub-journey (HMRC_55)

```
HMRC_55 (how much of deceased's share passes to spouse?)
  'All of it'  → END  (100% spousal exemption — row committed)
  'Some of it' → HMRC_54 (how is the portion specified?)
  'None of it' → HMRC_60 (valuation gate)

HMRC_54 (value or percentage?)
  'A value (£)'  → HMRC_61 (value in £) → HMRC_60
  'A share (%)'  → HMRC_62 (% share)    → HMRC_60
```

### 11f. Valuation gate and tail (HMRC_60 onwards)

```
HMRC_60 (professional valuation?)
  'Yes' → END  (valuation exists — row committed; no further questions)
  'No'  → HMRC_56 (tenure)

HMRC_56 (Freehold / Leasehold?) → HMRC_57 (let?) → HMRC_58 (special factors?)
  → HMRC_59 (sold within 12 months?) → END
```

The tail (HMRC_56–HMRC_59) is only reached when there is no professional
valuation. All four are unconditional chains.

### 11g. External questions and `external_condition_qids`

HMRC_14 appears as `alternate_condition_id` on five routing rows (orders
30, 70, 130, 160, and the slot-2-only row at 70). It is answered in HMRC_S1,
not in HMRC_S8, so it is NOT in HMRC_S8's node set. `load_cache_for_routed_section`
collects it into `external_condition_qids`, and `_fetch_external_answers`
retrieves it from the DB once per section visit, independently of any row
being added.

HMRC_48 is referenced as `alternate_condition_id` at row order=90 (the
HMRC_50 compound condition). Since HMRC_48 IS a node in HMRC_S8 (order=70
has it as `current_node`), it IS covered by `question_node_ids` and is NOT
added to `external_condition_qids`. Its answer is available in `row_data`
from the row journey session.

### 11h. What is still to build in HMRC_S8

The current routing is fully live. Sub-questions deferred to a later session:
- Lease length (Leasehold path)
- Damage/special factor detail
- Insurance cover confirmation
- Valuation upload

These were excluded from the initial build and are tracked as LATER in the Backlog.

---

## 12. What is deferred

| Item | Backlog ref |
|------|-------------|
| Reckoner parts 1 and 2 (married, widowed) | D1 |
| S1 amend conflict — `duplicate_amend.html` template and answer restoration | D7 |
| Jointly owned assets triage design | D13 |
| Nil rate band transfers | D14 |
| Reconcile `_entry_start` vs `iht_start_new_estate` duplication | confirmed by coherence audit 7 July 2026 |
| Tailor exit gate — holding page when Yes-answered items have no built sections | NOW — not yet built; see §8a |
| S5/S6 `QUESTION_SCHEDULE_MAP` entries and schedule allocation | LATER — see §8a and Backlog |
| Derived married/widowed/single helper reading HMRC_14+HMRC_43 together | new, 5 July 2026 |
| HMRC_S8 sub-questions: lease length, damage detail, insurance cover, valuation upload | LATER — see §11h and Backlog |
| HMRC_46/HMRC_14 compound routing rows not yet authored via admin UX | NOW — compound engine built, rows need authoring; see §11b and Backlog |
| Admin UX for compound routing (two-slot fields not yet surfaced in routing form) | SOON — blocks authoring above; see Backlog |
