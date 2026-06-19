# IHT Orchestration Logic — Reference Document
Date: 16 June 2026
Status: Current as of file_dump regenerated 16 June 2026

---

## 1. Key terms

### Platform terms (core app)

**Section** — a linear or branching set of questions managed entirely by
the core execution engine. The executor never knows where one section ends
and another begins. Each section has a `section_id` (e.g. `HMRC_S1`).

**SectionStatus** — a database row (in `core_sectionstatus`) recording
whether a given user has `not_started`, `in_progress`, or `complete` status
for a given section. Written by the core execution engine, never by dept
code.

**`section_done`** — the core view that fires when a section is confirmed
complete. It reads `return_url` from session and redirects there. If
`post_confirm_redirect` is set in session, it redirects there instead
(once only — the key is then cleared from session).

**`call_sections`** — a platform interface function. Sets `return_url` in
session to the caller's path (i.e. the regime home URL), and returns an
entry URL for the first section in the list. The dept uses this to send
the executor into a section and ensure they come back afterwards.

**`post_confirm_redirect`** — a session key. When set, `section_done`
redirects here instead of `return_url`, and clears the key. Used by dept
code to intercept the post-completion redirect for special handling.

**`show_confirmation=False`** — a section flag. When set, there is no
explicit confirmation page on first entry — the section auto-commits on
the last question. On re-entry of a completed section, `section_start`
detects existing answers and redirects to the review screen, from which
the executor can confirm without re-answering every question.

### Dept terms (dept_hmrc)

**`iht_orchestrate`** — a Django view, permanently mapped to
`/hmrc/regime/HMRC_IHT/`. Runs on every visit to that URL — including
after every section completion, because `section_done` reads `return_url`
from session (set to `/hmrc/regime/HMRC_IHT/` by `call_sections`) and
redirects there. `iht_orchestrate` doesn't know a section just completed
— it reads all current state from the DB fresh and decides what to do next.

**`_build_action_list`** — a helper function called by `iht_orchestrate`.
Reads current section statuses, `IHTReckoner` conclusion, and flash
messages, and returns a list of action row dicts — one per button on the
home page. Each row carries: id, label, hint, status, status_label,
status_colour, url, link_label, flash_message.

**`iht_screen`** — a Django view that renders `dept_hmrc/iht/home.html`.
Receives the action list, verified case details, and breadcrumbs as
parameters. Never reads the DB itself.

**`handle_reckoner`** — a helper function (not a view, not mapped to any
URL). Called by `iht_orchestrate` when S2 is complete. Reads HMRC_13/14
answers and S3 status. Returns either a redirect (into S3) or None
(telling `iht_orchestrate` to render the home screen).

**`get_reckoner_state`** — a helper function called directly by
`iht_reckoner_compute`. Reads S3 answers, computes the adjusted threshold
(£325k + RNRB - taper-adjusted gifts), writes it to session, and redirects
to the threshold view. Handles knock-out directly via `_save_conclusion`.

**`_save_conclusion`** — a helper function. Writes a conclusion
(`not_payable`, `may_be_payable`, or `knock_out`) to the `IHTReckoner`
model and redirects to regime home.

**`iht_reckoner_compute`** — a bespoke dept view, mapped to
`/hmrc/iht/reckoner/compute/`. Intercepts `section_done` after S3
completion (via `post_confirm_redirect`). Deletes any stale `IHTReckoner`
row for the verified case, then calls `get_reckoner_state` directly —
bypassing `handle_reckoner` and its `IHTReckoner.exists()` guard.

**`iht_reckoner_threshold`** — a bespoke dept view, mapped to
`/hmrc/iht/reckoner/threshold/`. Renders a single computed radio question:
"Was the total value of the estate less than £X?" On POST, writes the
conclusion, threshold, question text, and answer to `IHTReckoner`, then
redirects to regime home.

**`IHTReckoner`** — a Django model (table `dept_hmrc_ihtreckoner`). One
row per case. Fields: `conclusion` (`not_payable` / `may_be_payable` /
`knock_out`), `question_text`, `threshold`, `answer`, `answered_at`.
The dept's own persistent store for reckoner results, outside
`core_answer`. Written by `_save_conclusion` (knock-out) or
`iht_reckoner_threshold` (non-knock-out). Read by `_build_action_list`
to show a persistent conclusion message on the reckoner row.

---

## 2. The home page visit cycle

Every visit to `/hmrc/regime/HMRC_IHT/` hits `iht_orchestrate`. It reads
all current state from the DB fresh and decides what to do. There is no
memory between visits other than what is stored in the DB or session.

```
Browser GET /hmrc/regime/HMRC_IHT/
    → iht_orchestrate runs
    → reads DB state fresh
    → decision tree (see section 3)
    → either: redirect to a section or bespoke view
           or: _build_action_list → iht_screen → renders home screen
```

---

## 3. `iht_orchestrate` decision tree

```
Visit to /hmrc/regime/HMRC_IHT/
│
├── No verified case
│     → renders home.html inline (pre-matching UX, single Start button)
│       post_confirm_redirect set to iht_matching_result
│       [executor clicks Start → enters S1 → section_done →
│        iht_matching_result → assigns IHT reference → regime home]
│
└── Verified case exists
      │
      ├── S2 not complete
      │     → _build_action_list → iht_screen → home screen
      │       [reckoner row shows Start or In progress]
      │
      └── S2 complete
            │
            ├── HMRC_13=Yes and HMRC_14=Single (reckoner path active)
            │     → writes post_confirm_redirect = /hmrc/iht/reckoner/compute/
            │       to session on every visit (covers both fresh entry
            │       and View / amend)
            │
            └── call handle_reckoner
                  │
                  ├── returns redirect → follow it (enter S3)
                  │
                  └── returns None
                        → _build_action_list → iht_screen → home screen
                          [reckoner row shows conclusion message;
                           estate details button appears if applicable]
```

---

## 4. `handle_reckoner` decision tree

Called by `iht_orchestrate` when S2 is complete.

```
handle_reckoner
│
├── HMRC_13 = No
│     → return None  [home screen; estate details button appears]
│
├── HMRC_13 = Yes, HMRC_14 = Married or Widowed
│     → return None  [Parts 1/2 not yet built]
│
└── HMRC_13 = Yes, HMRC_14 = Single
      │
      ├── S3 not complete
      │     → call_sections(['HMRC_S3']) → return redirect into S3
      │
      └── S3 complete
            │
            ├── IHTReckoner row exists
            │     → return None  [home screen with stored conclusion]
            │
            └── No IHTReckoner row
                  → return None  [iht_reckoner_compute handles this path
                                  via post_confirm_redirect — handle_reckoner
                                  is not the entry point for post-S3 logic]
```

Note: when S3 is complete and no `IHTReckoner` exists, `handle_reckoner`
returns None and the home screen renders. This state is transient —
`post_confirm_redirect` is set on the same home page visit, so as soon as
the executor enters S3 via View / amend and confirms, `section_done`
redirects to `iht_reckoner_compute` which creates the `IHTReckoner` row.

---

## 5. Post-S3 completion cycle

This cycle fires whenever the executor completes or re-confirms S3
— whether on first entry or via View / amend.

```
section_done after S3
    → reads post_confirm_redirect = /hmrc/iht/reckoner/compute/
    → clears post_confirm_redirect from session
    → redirects to /hmrc/iht/reckoner/compute/

iht_reckoner_compute
    → resolves verified case for current user
    → deletes any existing IHTReckoner row
    → calls get_reckoner_state(request, regime, actor, user, case)

get_reckoner_state
    → reads S3 answers (HMRC_10, HMRC_11, HMRC_15, HMRC_7, HMRC_8, HMRC_9)
    → checks knock-out options in HMRC_11:
        if any knock-out selected
            → _save_conclusion('knock_out')
            → IHTReckoner written, redirect to regime home
            → home screen shows "full return required" message
    → computes RNRB: min(HMRC_9, £175,000) if HMRC_9 answered, else 0
    → computes taper-adjusted gifts from HMRC_15 (7 year components,
      taper rates: yrs 1-3=100%, yr4=80%, yr5=60%, yr6=40%, yr7=20%)
    → threshold = £325,000 + rnrb - taper_gifts
    → writes threshold and case_id to session
    → redirects to /hmrc/iht/reckoner/threshold/

iht_reckoner_threshold (GET)
    → reads threshold from session
    → renders question_radio.html:
      "Was the total value of the estate less than £X?"
    → pre-populates from existing IHTReckoner if present (re-entry)

iht_reckoner_threshold (POST)
    → validates answer selected
    → conclusion = 'not_payable' if Yes, 'may_be_payable' if No
    → writes IHTReckoner (conclusion, threshold, question_text, answer)
    → clears threshold from session
    → redirects to /hmrc/regime/HMRC_IHT/

iht_orchestrate runs
    → handle_reckoner: S3 complete, IHTReckoner exists → return None
    → _build_action_list reads IHTReckoner.conclusion
    → home screen renders with persistent conclusion message
    → estate details button appears if conclusion = 'may_be_payable'
```

---

## 6. `_build_action_list` — action row rules

Rows are built in order. Each row appears unconditionally unless noted.

**Row 1 — Deceased's details**
- Always shown
- URL: `/section/HMRC_S1/start/`
- Link label: Start / View / amend
- Flash: `iht_flash` session key if row='deceased_details'

**Row 2 — Estate ready reckoner**
- Always shown
- URL: `/section/HMRC_S2/review/` (if S2 in progress or complete and S3
  not yet started); `/section/HMRC_S3/review/` (if S3 in progress or
  complete); entry URL (if S2 not started)
- Link label: Start / View / amend
- Status: rolls up S3 status — shows In progress if S3 not complete after
  S2 complete
- Flash/conclusion: session flash OR persistent `IHTReckoner` conclusion
  message (whichever is present; session flash takes priority)

**Row 3 — Estate details**
- Shown only when S2 complete AND (HMRC_13=No OR
  `IHTReckoner.conclusion` = 'may_be_payable')
- URL: `#` (not yet built)
- Status: Not started

---

## 7. `post_confirm_redirect` usage in IHT

| Set by | Value | Purpose |
|--------|-------|---------|
| `iht_orchestrate` (pre-matching branch) | `iht_matching_result` | After S1, run duplicate check |
| `iht_orchestrate` (S2 complete branch) | `iht_reckoner_compute` | After S3, run threshold computation |

The S1 entry in `section_start` (core) clears `post_confirm_redirect`
when HMRC_S1 is entered, preventing the reckoner compute URL from
misfiring if the executor amends deceased's details after completing
the reckoner.
