# IHT Tailoring Flow — Reference Document
Date: 16 June 2026
Status: Draft — granular questions marked [DRAFT FOR NOW]

---

## 1. Overview

"Tailor your submission" is an action button on the IHT estate homepage, visible
once a verified case exists. It allows the executor to declare which asset and
liability types are relevant to the estate. The output of this step drives which
further action buttons appear on the home page.

The tailoring section is intentionally dumb — it captures Yes/No answers only.
All intelligence lives in the orchestrator, which reads those answers fresh on
every home page visit to determine what to surface.

The executor can return to "Tailor your submission" at any time and change their
answers. Changing a Yes to No removes the corresponding action button. If answers
have already been provided in a removed section, the executor is warned explicitly
before deletion proceeds.

---

## 2. Section: HMRC_S4 — Tailor your submission

**Type:** Standard platform section, three QuestionSet nodes.

**show_confirmation:** False — the section auto-commits on the last page.
Re-entry goes to the review screen.

**Post-section:** `post_confirm_redirect` points to a new bespoke view
`iht_triage_confirm`, which compares new answers against previous answers and
handles the deletion warning flow (see section 5).

**Routing:** Linear. Set 1 → Set 2 → Set 3 → END. No branching within the
section — all questions are Yes/No radio, all appear on their Set page regardless
of other answers.

---

## 3. Granular questions [DRAFT FOR NOW]

Each question is a standalone radio question (Yes/No), `question_type=radio`,
`options='Yes;No'`. Questions are grouped into QuestionSets for page rendering.
Routing operates at Set level (each Set is a single routing node).

Question IDs are indicative — assign actual IDs (HMRC_16 onwards) when building.

### Set A — Common assets and liabilities (Page 1)

| Draft ID | Question text |
|----------|---------------|
| HMRC_T01 | Did the deceased own a home? |
| HMRC_T02 | Did the deceased have any bank or building society accounts? |
| HMRC_T03 | Did the deceased have any Premium Bonds or National Savings? |
| HMRC_T04 | Did the deceased have any household goods or personal possessions? |
| HMRC_T05 | Did the deceased jointly own any assets with another person? |
| HMRC_T06 | Did the deceased make any gifts or other transfers of value in the 7 years before death? |
| HMRC_T07 | Were there any other debts owed by the deceased (excluding any mortgage)? |
| HMRC_T08 | Was any money owed to the deceased by way of personal loans? |

### Set B — Pensions and life assurance (Page 2)

| Draft ID | Question text |
|----------|---------------|
| HMRC_T09 | Did any pension payments continue after the deceased's death? |
| HMRC_T10 | Was a lump sum (death benefit) payable under a pension scheme? |
| HMRC_T11 | Were any pension contributions made in the 2 years before death? |
| HMRC_T12 | Were any sums payable by an insurance company to the estate as a result of the death? |
| HMRC_T13 | Was the deceased covered by a jointly owned life assurance policy that continues after death? |
| HMRC_T14 | Was the deceased entitled to benefit from a policy on someone else's life that continues after death? |
| HMRC_T15 | Did any payments under a purchased life annuity continue after death? |

### Set C — Less common assets (Page 3)

| Draft ID | Question text |
|----------|---------------|
| HMRC_T16 | Did the deceased own any other land, buildings or property (not their principal home)? |
| HMRC_T17 | Did the deceased own any listed stocks, shares or ISAs? |
| HMRC_T18 | Did the deceased own any unlisted stocks, shares or control holdings? |
| HMRC_T19 | Did the deceased have any business or partnership interests? |
| HMRC_T20 | Did the deceased own any agricultural property or farmland? |
| HMRC_T21 | Did the deceased own any assets outside the UK? |
| HMRC_T22 | Did the deceased have any right to benefit from assets held in trust? |
| HMRC_T23 | Was the deceased entitled to receive any legacy from another estate not yet received? |
| HMRC_T24 | Is any asset exempt on grounds of national or scientific heritage? |

**Note on Set groupings:** The three Sets (pages) are a presentation decision,
not a structural one. The granular questions are the fixed point. Sets can be
reorganised — questions moved between Sets, Sets renamed, a fourth Set added —
purely through admin configuration with no code changes. The post-processing
and action button logic operates on granular question answers, not Set membership.

**Note on IHT schedules:** The question texts above are derived from IHT400
Q29–47 and the individual schedule forms (IHT409, IHT410 etc.), reworded into
plain English. They intentionally do not mirror the IHT400 gateway question
wording, which is written for accountants rather than executors.

---

## 4. Two-level navigation model

The tailoring answers drive a two-level navigation structure on the estate
homepage.

### Level 1 — Home page

One action button per Set (currently three: "Common assets and liabilities",
"Pensions and life assurance", "Less common assets"). Each button's status
rolls up from the granular questions in that Set:

- **Not started** — no Yes answers in this Set have been actioned
- **In progress** — at least one Yes answer actioned, at least one not yet
- **Complete** — all Yes answers in this Set have been actioned (or there
  are no Yes answers in this Set)

Clicking a Level 1 button goes to its Level 2 sub-page.

### Level 2 — Sub-page

Lists only the granular questions from that Set where the answer was Yes.
Each row shows:
- The asset/liability label
- Status badge (Not started / In progress / Complete)
- Action link (Start / Continue / View and amend)

The action link points to the detail section for that granular question
(see mapping dict below).

Both levels use the same action-row pattern already established by
`_build_action_list` and `iht_screen`. The Level 2 sub-page is rendered
by a new parallel view (`iht_estate_screen` or similar) using the same
action-row template.

### The two loops

Neither loop hardcodes any question or section:

**Loop 1** (home page): iterate over Sets → for each Set compute rollup
status from its granular questions → render one Level 1 row per Set.

**Loop 2** (sub-page): for a given Set, iterate over its granular questions
→ filter to Yes answers only → look up detail section in mapping dict →
read SectionStatus → render one Level 2 row per Yes answer.

Adding a new granular question: create the question, add to a Set, add one
entry to the mapping dict. Both loops adapt automatically.

### Mapping dict

A dict in `orchestrate.py` (parallel to `RECKONER_SECTION`) maps each
granular question ID to its detail section ID:

```python
TRIAGE_SECTION_MAP = {
    'HMRC_T01': 'HMRC_S_HOME',        # Owned home detail
    'HMRC_T02': 'HMRC_S_BANK',        # Bank accounts detail
    'HMRC_T09': 'HMRC_S_PENSION_PAY', # Continuing pension payments
    'HMRC_T10': 'HMRC_S_PENSION_DB',  # Death benefit
    # ... etc
}
```

Questions not yet wired to a built section can map to None — the Level 2
row renders as "Coming soon" or similar without a link.

---

## 5. Post-processing: `iht_triage_confirm`

A bespoke dept view mapped to `/hmrc/iht/triage/confirm/`. Triggered via
`post_confirm_redirect` after S4 completes (including on re-entry via
View and amend).

### Flow

```
section_done after S4
    → reads post_confirm_redirect = /hmrc/iht/triage/confirm/
    → clears post_confirm_redirect from session
    → redirects to iht_triage_confirm

iht_triage_confirm
    → resolves verified case for current user
    → reads previous S4 answers (before this submission)
    → reads new S4 answers (just submitted)
    → compares: identifies any Yes → No changes
    → for each Yes → No change:
        → looks up detail section in TRIAGE_SECTION_MAP
        → checks SectionStatus for that section
        → if status is in_progress or complete: flag for warning
    → if no flagged sections:
        → redirect to regime home (no warning needed)
    → if flagged sections exist:
        → render warning page (see below)
```

### Warning page

Renders a list of sections that will be removed, with their current status.
Plain English: "If you continue, the following will be removed and any
answers you have already provided will be deleted."

Two options:
- **Confirm** — deletes answers for flagged sections, resets SectionStatus
  to not_started, redirects to regime home
- **Go back** — returns to S4 review screen so the executor can reinstate
  the Yes answers

### Important behaviours

- The warning fires only when a removal affects a section with existing
  answers. Changing a Yes to No on a not_started section silently removes
  the action button with no warning.
- The comparison is against the previous S4 submission, not the original.
  Each re-entry of S4 compares against the state at the start of that visit.
- Previous S4 answers must be read before S4 is entered, and stored in
  session by `iht_orchestrate` so `iht_triage_confirm` can access them.

---

## 6. Action button on home page

**Label:** "Tailor your submission"

**Visibility:** Shown once a verified case exists (alongside the reckoner
button). Shown regardless of whether S4 has been started.

**Status:** Not started / In progress / Complete — driven by S4 SectionStatus.

**URL:** `/section/HMRC_S4/start/` (pre-completion) or
`/section/HMRC_S4/review/` (post-completion).

**Relationship to Level 1 estate buttons:** The Level 1 estate buttons
(Common assets, Pensions and life assurance, Less common) appear below
"Tailor your submission" once S4 is complete. They are not shown until
S4 is complete — there is nothing to display until the executor has
declared what is relevant.

---

## 7. Status rollup rules

### Level 2 row status (per granular question)
Derived from SectionStatus of the mapped detail section:
- `not_started` → Not started
- `in_progress` → In progress
- `complete` → Complete

### Level 1 row status (per Set)
Derived from the Level 2 rows for that Set (Yes answers only):
- All not_started (or no Yes answers) → Not started
- All complete → Complete
- Otherwise → In progress

### Home page "Tailor your submission" status
Derived from S4 SectionStatus directly (platform-managed).

---

## 8. What is deferred

- The actual detail sections (HMRC_S_HOME, HMRC_S_BANK, HMRC_S_PENSION_PAY
  etc.) — these are D2 proper. The tailoring flow is the scaffolding that
  will surface them.
- The nil rate band transfer questions (IHT400 Q29a–d) — a different
  concept, deferred to a later build.
- The alternative five-headline grouping (Deceased's residence, Household
  and personal goods, Pensions, Life assurance and annuities, Other UK
  financial assets, Other) — the granular questions are grouping-neutral;
  the Set structure can be reorganised to this model without code changes
  if preferred.
- Co-executor visibility of tailoring answers — design deferred.
