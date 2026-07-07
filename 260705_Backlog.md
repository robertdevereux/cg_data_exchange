# cg_data_exchange — Backlog
Date: 5 July 2026
Status: Live working document — update as items are completed or added

---

## Priority tiers

- **NOW** — active sprint, do next
- **SOON** — important, do after NOW items
- **LATER** — valuable but not urgent
- **DOC** — documentation work
- **TIDY** — housekeeping, low risk, do when convenient

---

## NOW

### D18: Configure and test IHT405 property sections
IHT405 boxes 6 and 7 (deceased's residence; other land and buildings) are
the first real type-2 (Table with routing) sections. **Status update, 5
July 2026: the admin-tooling blockers that were in the way of building
this comfortably have now been resolved** — the section-membership pool
(`SectionMember`), the routing insert/delete overhaul, and admin-controlled
`order_in_section` placement (see Core Platform Reference sections 3 and 8)
were all built and tested this week specifically to make this kind of
build tractable. D18 itself has **not** been started. Once question
definitions are available:
1. Create HMRC questions for core property columns + two gateway Yes/No
   questions (special factors; sale/intent to sell)
2. Create QuestionSets for the core columns and any follow-up groups
   (note: QuestionSet IDs are now `SET{N}`, not `S{N}` — see Core Platform
   Reference section 3)
3. Configure routing for each section (S_core → conditional branches per
   routing table in the conditional table spec) — add each question/set to
   the section's pool first, then wire routing using the simplified
   insert/delete tools
4. Set `display_question_ids` to core columns + gateway questions
5. Set `totals_question_ids` to open market value question
6. Manual smoke test: add/change/delete rows; verify "Other details" link;
   verify sparse rows; verify totals

### New, 5 July 2026: Reconcile duplicate "start a new estate" entry paths
`_entry_start` and `iht_start_new_estate` both start a new IHT estate but
diverge in behaviour (the former shows an interim pre-verified screen, the
latter skips straight into S1). Likely fix: `iht_start_new_estate` becomes
`_entry_start`'s path with a flag, rather than a separate implementation.
See HMRC IHT Reference section 2. Good candidate for the "coherence audit"
session below, or can be picked off on its own.

### New, 4 July 2026, still open: Triage-set completion gating
The three triage-set action-list rows (Common assets / Pensions / Other)
were observed showing "Complete" before "Tailor your submission" had
genuinely been completed for that estate. Not yet established whether this
is a real bug in `_should_show_tailor`/`_triage_set_rollup`, or a vacuous
"complete" from zero Yes-answers. Needs a deliberate before/after test on
a fresh estate (check the three rows *before* touching Tailor at all).
See HMRC IHT Reference sections 7–8.

### New, 5 July 2026: Coherence/architecture audit session
After a long, productive but reactive session (multiple interlocking fixes
to routing tools, identity handling, and session state), worth a dedicated
session — **no new features, only finding and reporting drift** — before
further build work:
- Grep every `request.user` use across `core` and `dept_*` apps; check each
  against whether it should be `case.user`-scoped instead (the exact bug
  class found and fixed twice on 5 July 2026 — see Core Platform Reference
  section 4a). Report findings; do not fix inline.
- Look for other "two paths, one concept" duplications like `_entry_start`
  vs `iht_start_new_estate` across `orchestrate.py`, now that it has grown
  organically across several sessions.
- Diff the HMRC IHT Reference doc's description of ENTRY/EXIT against what
  `orchestrate.py` actually does, line by line — the doc has drifted from
  the code before (the phantom `ScheduleSection` model was one instance)
  and may have again.

---

## SOON

### D1: Build IHT Reckoner Parts 1 and 2
Part 1 (deceased survived by spouse) and Part 2 (widowed).
Both need flow documents equivalent to `IHT_Reckoner_Part3_Flow-2.md`
before building. Key points outlined in that doc. **Also now needs**:
`RECKONER_SECTION`'s HMRC_14 lookup was written for the old three-way
single/married/widowed answer; HMRC_14 is now Yes/No with a separate
HMRC_43 follow-up (see HMRC IHT Reference section 4) — check this mapping
still resolves correctly before relying on it.

### New, 5 July 2026: Derived marital-status helper
Anything needing "is this estate married / widowed / single-or-divorced"
as one concept (reckoner section selection; the Q1 marital gate in the IHT
journey architecture doc informing D18) currently has no single place to
get it — HMRC_14 (Yes/No) and HMRC_43 (Yes/No, conditional) need reading
together. Build a small helper (e.g. `get_marital_status(case)`) rather
than each caller re-deriving it. Low effort, but do it before D1 or D18
need it, not after.

### D2: Estate detail sections — build from triage scaffolding
Triage scaffolding complete (S4/S5/S6). Next: build S4/S5/S6 action
buttons in HMRC orchestrate using `call_core` with schedule lists derived
from Yes-answered triage questions. Entry/exit conditions for each button
follow the two-phase pattern. Start with S4 (common assets). Each asset
type gets one or more schedules defined in the regime; `call_core` routes
to `regime_top_level` or direct to section list as appropriate.

### D3: Encode IHT regime in load_test_data
Once HMRC_S1 through HMRC_S6 stable, encode all regime/section/routing/
question records in `load_test_data` so they survive a database reset.
Pattern: `update_or_create` with `old_ids` cleanup list.
Also fix at D3:
- `call_regime` (and other call helpers) use `get_or_create_case` internally,
  not `create_case` — inconsistent with multiple-case intent. Fix when
  stabilising load_test_data.
- `PlatformRouter` routes on model class, not `is_platform` flag — all
  Question records go to same DB alias regardless. Harmless while both
  aliases point at same Neon DB, but must fix before DB separation is
  provisioned.

### D6: Permission grant UI — case selection step
The grant wizard at `/tools/actors/` needs an optional step:
"Do you want to limit this grant to a specific case?"
Shows dropdown of subject user's cases for the selected regime.
Full scope matrix in Core Platform Reference section 6.
Prompt already drafted — ready to fire at CC.

---

## SOON — Documentation

### DOC G1: Functional Architecture — remaining updates
- Case model: multiple cases per user+regime; create_case/get_cases
- Permission model: case dimension; full 5-row scope matrix
- IHT pattern: lead executor, estate identity, matching flow, estate
  homepage, selective section calling — **now also**: the deceased-identity
  lifecycle (synthetic User, Answer re-keying) built 5 July 2026, and the
  actor/user split as actually implemented (see Core Platform Reference
  section 6a and HMRC IHT Reference section 3a)
- Section 3.1: JSON storage and schema evolution note
- Section 7: confirm three-tier DB separation story
- Replace "Layer 1/2" vocabulary with standard terms:
  orchestration layer / execution engine
- Describe structural separation conceptually for Salesforce architect
- Document two-phase action button pattern (iht_in_core / iht_current_action)
  as canonical dept orchestration pattern → maps to Salesforce master Flow
- Section types: Standard / Table / Table with routing — architecture and
  design rationale

### DOC G2: Vision Paper — minor amendment
One sentence amendment to section 6.1 already drafted:
"A Regime is composed of Sections, optionally grouped into Schedules..."
Apply and save as v0.3.

### DOC G3: Implementation Options — check for staleness
### DOC G4: Salesforce Implementation Plan — significant update likely
Two-tier question bank and Case/Permission changes have implications for the
Salesforce data model. Phase 1 data model section needs revisiting.

---

## LATER

### D5: Cross-department pre-population demo
Once a second live dept app exists alongside HMRC, demonstrate pre-population
on P_1 (name) and/or P_3 (DOB). This is the PoC's centrepiece capability.
Currently deferred — HMRC is the only live dept.

### D7: IHT S1 amend — conflict handling
When an executor amends deceased's details (S1 View/amend) and the new
details conflict with another verified estate:
- `_exit_deceased_details` in orchestrate.py currently calls
  `_render_duplicate_amend` which references `duplicate_amend.html`
  — this template does not yet exist
- Template should explain the conflict, preserve the existing IHT reference
  and all completed work
- Also need to restore original S1 answers. Design the restoration mechanism
  before building.

### D8: Dept FK on Question model
Add nullable dept FK to Question for formal scoping.
One migration, update admin tools filter, update routing dropdowns.

### D9: Question/set deletion with governance
Design the departmental clearance workflow before building.

### New, 1 July 2026: Section-membership deletion governance
Same shape as D9, scoped to `SectionMember` rather than platform-wide
question deletion: currently a pool member can be removed even while still
referenced by `Routing` (the remove action silently no-ops rather than
warning). Low priority per explicit steer — a visible warning UI is the
likely eventual fix.

### D10: Section intro pages
Four fixed intro types: none, simple, checklist, summary.
`intro_type` field on Section model (migration needed).

### D11: GDS compliance audit
Check rendered HTML for each question type against GOV.UK Design System
specs: aria-describedby, error prefix, autocomplete attrs,
fieldset/legend structure.

### D13: IHT triage — jointly owned assets
Jointly owned assets cut across all asset categories and have their own
IHT schedule (IHT404) with distinct tax treatment. Currently excluded from
S4. Need to decide: separate top-level triage question, or two-pass approach?
Design before building.

### D14: IHT triage — nil rate band transfers
IHT400 Q29a–d are a conceptually distinct category. Deferred from the
tailoring flow entirely. Design separately — likely a fourth triage section
or a dedicated action button.

### D16: Regime wizard — membership vs presentation order
The regime wizard currently conflates membership with top-level presentation
order. Needs two explicit steps: (1) membership declaration, (2) ordered
list. Until then, depts using `call_core` must supply ordered items
explicitly in their orchestrate code.

### D17: Degenerate schedule UX
Some asset types (single-section assets) cause a double-click (choose
schedule → choose its only section). Design auto-skip or combined page.

### D19: Table row amendment validation
Type-2 table row set pages (`table_routed_set.html`) currently have no
field-level error display for required fields. Add same validation pattern
as `question_set.html`.

### D20: `radio_inline` in row journey templates
`radio_inline` question type not yet rendered in `table_routed_question.html`
or `table_routed_set.html`. Add when a form requires it.

### DOC G6: README
Government-audience README: what the PoC is, how to run it, architecture
portability, how to add a new department. Draft after D1–D5 complete.

### D12: Note — `post_confirm_redirect` scoping (platform consideration)
Currently unscoped; not causing any conflict today. If a genuine conflict
arises in another regime, consider scoping it by section_id. Not urgent.

---

## TIDY — Housekeeping

- **Extract back-link calculation in `_process_answer`** — duplicated ~5 times.
  Extract to `_get_back_url(pss, section_id, question_id)` helper.

- **Consolidate `_get_or_create_case` in views_layer2** — private copy
  duplicates the one in `interfaces.py`. Remove and import from interfaces at D3.

- **Extract `_get_case` helper** — case resolution is duplicated across several
  table section views. Extract to a single helper.

- **Extract shared question-field rendering** — `table_routed_question.html`,
  `table_routed_set.html`, `question.html`, and `question_set.html` share
  question-field markup. Extract to `_question_field.html` include.

- **Remove `get_or_create_case()`** — deprecated, still used by TEST/demo
  harness only. Remove when harness is updated.


- **Consistency checker for QuestionSet nodes** — one skipped test.
  Complete when QuestionSet usage grows.

- **Routing display verbosity** — unconditional single routes display as
  "All other answers → [NEXT]" even when there is no branching. Cosmetic
  only, not a bug. Fix when convenient.

---

## Completed (5 July 2026 session)

- **Removed `dept_defra` and `dept_dwp` in full (2026-07-07)** — both apps had
  zero models and zero migrations; deleted directories, removed INSTALLED_APPS
  entries and URL includes, stripped DWP/DEFRA user/department/permission
  fixture blocks from `load_test_data.py`, fixed one trivially-unused
  `dwp_alice` reference in `dept_hmrc/tests.py`. HMRC is now the only live
  dept. Pre-removal audit in `260707_DEFRA_DWP_Audit.md`.

- **Removed META mechanism in full (2026-07-05)** — deleted `meta_processors.py`,
  `tools_create.html`, the three `tools_create*` views, and all META regime /
  sections / M_N questions in `load_test_data.py`.

This was a long session covering a housekeeping detour, a large routing-UX
overhaul, and the IHT actor/subject identity split. Full technical detail
in Core Platform Reference and HMRC IHT Reference (both updated same day);
summary here for backlog tracking.

- **QuestionSet ID convention changed `S{N}` → `SET{N}`** — collided
  visually with Section IDs (`{DEPT}_S{N}`). Existing sets renamed via a
  one-off management command (run once, deleted); `_next_set_id()` updated
  to the new pattern going forward.

- **`ScheduleSection` phantom-model bug fixed** — `_get_triage_sets()`
  imported a `ScheduleSection` model that does not exist in code (Section
  has a direct FK to Schedule). Since this ran at module import time, it
  crashed the *entire app*, not just HMRC, whenever `orchestrate.py` was
  loaded. Core Platform Reference corrected to remove the phantom model
  from the documented data model.

- **`SectionMember` model added** — explicit pool of Questions/Sets
  available to a section, decoupled from routing. Section wizard gained a
  new "Add questions and sets to this section" panel (associate existing,
  or define-new-and-associate inline). Routing wizard node pickers now
  only offer pool members, keeping them usable as the question bank grows
  past ~40 questions. Existing sections backfilled via data migration.

- **Routing insert/delete UX fully rebuilt.** Three iterations were needed
  to reach a stable design (see Core Platform Reference section 8 for the
  final shape):
  - Per-condition-row menus and the crowded inline "add condition" form
    removed entirely from the tree display; consolidated into a single
    shared partial (`_routing_tree.html`) used by both the routing page
    and the section-edit page, which had drifted out of sync.
  - "Insert" simplified to two actions ("insert above," first row only;
    "insert below," every other row) that **never rewire any other row** —
    an earlier version that auto-spliced across a branching anchor's
    multiple rows was identified as wrong and reverted.
  - "Delete" simplified to `node_only` mode — removes only the target
    node's own rows, leaves predecessors/downstream untouched (dangling
    references surface via the validation banner instead of being
    silently rewritten). Earlier `delete_all` cascade behaviour caused
    real, unintended data loss during testing (deleting one node
    cascaded into deleting a whole downstream subtree) and was retired
    from the UI.
  - `order_in_section` changed from an integer to a `FloatField`,
    entirely admin-controlled via midpoint insertion on "insert below" —
    no automatic renumbering of any kind. A brief detour through an
    integer-renumbering design (a graph-traversal-based `_renumber_routing`)
    was built, found to conflict with "the admin decides display order,"
    and removed in favour of the simpler float scheme.
  - Bracketed, clickable destination references (e.g. `[HMRC_43]`) added
    for nodes with no routing rows yet, correctly anchored to insert
    adjacent to the reference clicked.

- **Test-suite discipline notes:** confirmed the canonical test command
  must use the full conda path — a bare `python manage.py test` silently
  hit a different Python install and under-reported the test count with
  no error. Also found and fixed a genuine test-isolation gap where
  `'default'`- and `'platform'`-routed connections to the same physical DB
  don't see each other's uncommitted fixture data under `READ COMMITTED`
  (fixed via scoped `@override_settings(DATABASE_ROUTERS=[])`).

- **`choose_user` promoted from `dept_demo` to `core/views_gate.py`** as
  `choose_user_for_regime` — now regime-scoped (fires *after* regime
  selection, not before) rather than showing every acting-for relationship
  a user has platform-wide. `dept_demo` and `dept_hmrc` both migrated to
  it; `dept_defra` and `dept_dwp` not yet (see SOON, above).

- **HMRC IHT deceased-identity split built.** Each verified estate now
  gets its own synthetic, login-incapable `User` (the deceased) distinct
  from the actor (the executor) — fixing a real, observed bug where
  starting a second estate offered the *first* deceased's name/DOB/NINO as
  a pre-population suggestion. `_promote_case_to_verified` creates the
  identity, re-keys `Answer` rows, assigns the reference, and grants a
  case-scoped `Permission`. The old `iht_case_picker`/`iht_select_case`
  (built earlier in the same session, before the identity split existed)
  were retired in favour of candidates on the shared acting-for gate,
  since the identity split already solves the disambiguation problem one
  level up.

- **Two real `request.user`-vs-`case.user` bugs found and fixed** — one in
  `section_start` (re-entry showed a blank first question instead of
  existing answers on a verified case), one across five sites in
  `_commit_section_answers` (confirmed answers were being saved under the
  actor rather than the case's actual subject). Both are instances of the
  same root cause: code written before the actor/user split existed
  anywhere on the platform. See Core Platform Reference section 4a for the
  now-documented correctness rule.

- **Session-caching-of-identity bug found and fixed** — `iht_orchestrate`
  previously cached `user_id` in session at the acting-for gate and never
  updated it when a case was promoted mid-session, causing a freshly
  verified estate's own action button to show "Not started." Fixed by
  removing the cache: `user` is now resolved fresh from `case.user` on
  every request. Generalised into a documented platform principle (Core
  Platform Reference section 5).

- **`iht_start_new_estate` redirect-loop bug found and fixed** — `_setup`
  captures `regime_home_url` from `request.path`, which was wrong when
  called from `iht_start_new_estate`'s own URL rather than from
  `iht_orchestrate`; every completed S1 silently created another new draft
  case and looped. Fixed with an explicit session override immediately
  after `_setup`.

- **Extracted `get_asked_answers_for_section(case, section)` and
  `format_answer_for_display(question_type, answer)`** into
  `core/interfaces.py` — replacing a hardcoded five-question list on the
  IHT home page (which could not reflect the new HMRC_14/HMRC_43 branching
  at all) with a generic, routing-driven display. Also de-duplicated
  answer-formatting logic previously only in `section_review`.

- **HMRC_14 restructured** from a three-way single/married/widowed
  question into two sequential Yes/No questions — HMRC_14 ("married or in
  a civil partnership?") and, on "No," a new HMRC_43 ("previously married,
  ended by the spouse's death?") — using the newly-fixed routing tools.
  Downstream consumers of the old three-way shape (reckoner section
  selection) not yet re-checked against this — see SOON.

---

## Completed (1 July 2026 session)

- **S2 redesign** — HMRC_S2 simplified to a single question (HMRC_13: "Do
  you want help working out if IHT is payable?"). HMRC_14 (marital status)
  moved into HMRC_S1 (Deceased's details) where it belongs conceptually and
  architecturally. Both answers to HMRC_13 now lead unconditionally to END;
  orchestrate routes to the appropriate reckoner or asset selector based on
  answers already collected.

- **`_entry_reckoner` fixed** — previously combined entry and routing logic
  (legacy of old S2 design). Simplified to always send user into S2. Routing
  logic remains in `_exit_reckoner` / `handle_reckoner` where it belongs.
  139 tests passing.

- **Stale `IHTReckoner` cleanup** — `handle_reckoner` now deletes any
  existing `IHTReckoner` row when HMRC_13 = No, preventing stale reckoner
  conclusions from persisting on the home page after a user changes their
  mind. 139 tests passing.

- **Marital status on IHT home page** — HMRC_14 answer now displayed in
  the deceased's details panel (between NINO and IHT reference). `_get_iht_answers`
  updated to include HMRC_14; `iht_screen` passes `deceased_marital` to
  template. **(Superseded 5 July 2026 — see above; this hardcoded approach
  was replaced by the routing-driven display.)**

- **Tailor now uses HMRC_SCH1** — `_entry_tailor` previously passed a
  hardcoded list of three section IDs to `call_core`. Now passes
  `{'type': 'schedule', 'id': 'HMRC_SCH1'}`. Adding or reordering triage
  sections in the schedule admin automatically updates the tailor journey.

- **`TRIAGE_SETS` made dynamic** — previously a hardcoded constant with
  `action` slugs (`common`, `pensions`, `other`). Now derived from
  `HMRC_SCH1` via `_get_triage_sets()` at startup. `TRIAGE_SECTION_IDS`
  derived from `TRIAGE_SETS`. Triage asset action button views renamed from
  `iht_action_common/pensions/other` to `iht_action_hmrc_s4/s5/s6` to
  match section IDs — consistent with core URL convention. URLs updated.
  Triage row action URLs built dynamically from `section_id`. 139 tests passing.

- **`_entry_triage_assets` refactored** — previously `_entry_common_assets`
  with hardcoded section ID and title. Now shared function
  `_entry_triage_assets(request, regime, actor, user, verified_case, section_id)`
  with dynamic title from `triage_set['name']`. Entry/exit dispatch updated
  to use set-membership check against `{t['section_id'].lower() for t in TRIAGE_SETS}`.

- **Flash messages repositioned** — flash messages now appear below the
  action row that generated them (previously above).

- **Type-2 row pruning fixed** — `_commit_table_row` / `section_table_routed_question`:
  `row_to_save` is now pruned to `asked_ids` before commit, ensuring stale
  answers from a diverged path are not saved. Guard `not asked_ids` preserves
  legacy behaviour for rows where `_asked_ids` was never set. 139 tests passing.

---

## Completed (28 June 2026 sprint)

- **Routing `condition_question_id`** — new nullable field on `Routing` model
  (migration 0014). When set, routing evaluates the answer to that question
  rather than the current node's own answer. Enables set nodes to branch on
  a specific member question. `_resolve_routing_answer` helper added.
  `_process_set_answer` "first member" hack removed. Admin routing editor
  updated. 5 new tests. 127 tests passing (1 skipped).

- **`display_question_ids` rename** — `column_question_ids` renamed to
  `display_question_ids` on `Section` model (migration 0013). Semantics
  extended: for type-1 flat tables, same as before (add-form columns + display
  order); for type-2 routed tables, declares summary display columns only
  (routing defines the full row journey). All view and template references
  updated.

- **Type-2 Table with routing (section_type=2)** — full implementation:
  - `_build_section_tables` helper extracted from `section_start` (shared)
  - `_commit_table_row` helper for writing row to `AnswerTable`
  - `section_table_routed_add` — row journey init (new row)
  - `section_table_routed_change` — row journey init (change existing row,
    pre-populated)
  - `section_table_routed_question` — workhorse GET/POST for each node;
    supports Q-nodes and S-nodes; back-navigation; path-divergence handling
  - `section_table_row_detail` — read-only extra details view
  - `section_table` updated: `change_url`, `detail_url`, `add_url` branched
    on section type
  - New templates: `table_routed_question.html`, `table_routed_set.html`,
    `table_row_detail.html`
  - `table_landing.html` updated: Change / Delete / Other details action column
  - `tools_section_edit.html`: type-2 shows routing editor; type-1 shows
    inset message
  - 11 new tests (TestConditionalTableSection). 82 tests passing (1 skipped).

---

## Completed (19 June 2026 sprint)

- **D2 (partial)** — IHT triage scaffolding: S4/S5/S6, 24 `radio_inline`
  triage questions (HMRC_16–39), `call_sections` multiple-section behaviour,
  filtered section list with title, active items dict from DB
- **Two-phase orchestrate pattern** — `iht_in_core` / `iht_current_action`
- **`radio_inline` question type** — model, template, set template, dispatch
- **Core `call_sections` improvements**
- **Matching refactor** — logic moved into `_exit_start` and
  `_exit_deceased_details` in orchestrate.py
- **Core cleanup** — HMRC_S1 guard removed from `section_start`
- **D15 — `call_core`** — unified entry point replacing `call_schedules`,
  `call_sections`, `call_regime`. `regime_top_level` view added.
- **115 tests passing, 0 failures**

---

## Known limitations (fix when they bite)

- Pre-population on set pages: works on amendment but not on first visit
  from a previous regime for compound types.
- Table section answer pre-population: not yet implemented for type-1 or type-2.
- Optional standalone questions (required flag on Routing): not yet built.
- Actor/agent consent for cross-dept question editing not enforced.
- Schedule-level permissions: gap — only regime, case, and section level exist.
- Phone/email validation (regex): deferred for P_4, P_5, P_6.
- IHT co-executor confirmation workflow: design deferred.
- Multiple Neon DBs: architecture in place, not yet provisioned.
- personal_name and address migration to compound type: deferred.
- Registration-gated regimes (e.g. Gambling Tax): design needed before build.
- `duplicate_amend.html` template missing — referenced in orchestrate.py
  `_render_duplicate_amend` but not yet built (see D7).
- Type-2 table row set pages: no field-level validation errors (see D19).
- `radio_inline` not yet supported in type-2 row journey templates (see D20).
- Consistency checker: mixed `condition_question_id` values per node warns
  but does not block; only the first `condition_question_id` found is used
  by `_resolve_routing_answer` (sufficient for current patterns).
- Reckoner's `RECKONER_SECTION` HMRC_14 mapping not yet re-verified against
  the new Yes/No + HMRC_43 shape (see D1).

---

*Update by telling Claude what's done or what's new.*
