# cg_data_exchange — Backlog
Date: 1 July 2026
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
the first real type-2 (Table with routing) sections. Questions are being
prepared in a parallel workstream (marital status, forms of ownership,
succession). Once question definitions are available:
1. Create HMRC questions for core property columns + two gateway Yes/No
   questions (special factors; sale/intent to sell)
2. Create QuestionSets for the core columns and any follow-up groups
3. Configure routing for each section (S_core → conditional branches per
   routing table in the conditional table spec)
4. Set `display_question_ids` to core columns + gateway questions
5. Set `totals_question_ids` to open market value question
6. Manual smoke test: add/change/delete rows; verify "Other details" link;
   verify sparse rows; verify totals

---

## SOON

### D1: Build IHT Reckoner Parts 1 and 2
Part 1 (deceased survived by spouse) and Part 2 (widowed).
Both need flow documents equivalent to `IHT_Reckoner_Part3_Flow-2.md`
before building. Key points outlined in that doc.

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
  homepage, selective section calling
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

### D4: Build DEFRA Rural Payments regime
DEFRA has a stub RP regime. Build at least one section with routing to
demonstrate DEFRA as a second working dept.

### D5: Cross-department pre-population demo
Once HMRC IHT and DEFRA RP both have sections using P_1 (name) and/or
P_3 (DOB), demonstrate pre-population. This is the PoC's centrepiece
capability.

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
`post_confirm_redirect` is no longer used in HMRC IHT. If a misfire risk
arises in another regime, consider scoping it by section_id. Not urgent.

---

## TIDY — Housekeeping

- **Extract back-link calculation in `_process_answer`** — duplicated ~5 times.
  Extract to `_get_back_url(pss, section_id, question_id)` helper.

- **Extract answer display formatting in `section_review`** — duplicated logic.
  Extract to `_format_answer_for_display(answer, question_type)` helper.

- **Consolidate `_get_or_create_case` in views_layer2** — private copy
  duplicates the one in `interfaces.py`. Remove and import from interfaces at D3.

- **Extract `_get_case` helper** — case resolution is duplicated across several
  table section views. Extract to a single helper.

- **Extract routing tree to shared Django include** — `tools_section_routing.html`
  and `tools_regime_edit_composite.html` both render the routing tree.
  Extract to `core/templates/core/_routing_tree.html`.

- **Extract shared question-field rendering** — `table_routed_question.html`,
  `table_routed_set.html`, `question.html`, and `question_set.html` share
  question-field markup. Extract to `_question_field.html` include.

- **Hide or remove old META wizard at `/tools/create/`** — superseded.

- **Remove `get_or_create_case()`** — deprecated, still used by TEST/demo
  harness only. Remove when harness is updated.

- **Rationalise DWP app structure** — has legacy nav/ and regime/ subfolders,
  not yet aligned to canonical flat structure.

- **Consistency checker for QuestionSet nodes** — one skipped test.
  Complete when QuestionSet usage grows.

- **Routing display verbosity** — unconditional single routes display as
  "All other answers → [NEXT]" even when there is no branching. Cosmetic
  only, not a bug. Fix when convenient.

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
  template.

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

---

*Update by telling Claude what's done or what's new.*
