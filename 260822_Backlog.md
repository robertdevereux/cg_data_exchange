# cg_data_exchange — Backlog
Date: 22 August 2026
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

### ~~D18: Configure and test IHT405 property sections~~ — **Complete (31 July 2026)**
~~HMRC_S8 (Deceased's residence) built and live-tested: SET10 through END, ownership fork, spousal-exemption exit (3a = Yes → END), valuation-trust gateway. See Completed (31 July 2026) below.~~
**Note: the spousal-exemption logic described here was a simplified binary version, since
superseded — see the full rebuild in Completed (15 August 2026) below.**

### New, 5 July 2026: Reconcile duplicate "start a new estate" entry paths
`_entry_start` and `iht_start_new_estate` both start a new IHT estate but
diverge in behaviour (the former shows an interim pre-verified screen, the
latter skips straight into S1). Likely fix: `iht_start_new_estate` becomes
`_entry_start`'s path with a flag, rather than a separate implementation.
See HMRC IHT Reference section 2. **Confirmed as a live duplication by the
coherence audit (Item 2, 7 July 2026)**, not just the original observation.

### ~~New, 4 July 2026: Triage-set completion gating~~ — **Fixed (31 July 2026)**
~~Confirmed as vacuous "Complete" from zero Yes-answers. Fixed: `if not set_items: continue` in `_build_action_list` omits empty-category rows entirely. See Completed (31 July 2026) below.~~

### ~~New, 3 August 2026: Author HMRC_46/HMRC_14 compound-condition routing rows~~ — **Complete (15 August 2026)**
~~The compound-condition routing engine (comparator_1/test_value_1/
alternate_condition_id/comparator_2/test_value_2) is built and live, but
the flagship example that motivated it — HMRC_46's ownership-type fork
needing a second condition on HMRC_14 (marital status) for the
sole-ownership branch — has not itself been authored. HMRC_46's three
existing rows (Sole ownership / Joint names / Tenants in common) each
still carry only a slot-1 condition; the sole-ownership row needs
splitting into two outcomes conditioned on HMRC_14, per the worked
example in 260802_Handoff_core_session_refactor_and_compound_routing.md
§3 and 260802_routing_engine_prototype.py's __main__ block. Needs the
admin UX below, or manual/fixture creation in the interim.~~
Resolved as part of a larger rebuild than originally scoped — the full
HMRC_S8 ownership-fork restructure (sole/joint/TIC together, not just
HMRC_46 alone). See Completed (15 August 2026) below.

### ~~New, 15 August 2026: load_hmrc_s8_routing.py is stale and destructive if re-run~~ — **Resolved (deleted, 15 August 2026)**
~~The management command used to originally build HMRC_S8's routing describes
a 25-row structure with the old node order (HMRC_46 before value) and
HMRC_53 in the TIC branch — both since rebuilt (15 August 2026, see
Completed). The live DB now has 30 rows in the corrected structure. This
command is delete-then-recreate (idempotent by design) — if anyone runs it
without first checking it against the current design, it will silently
overwrite the live, tested, correct routing with the old, buggy version.~~
Deleted rather than fixed — `core/management/commands/load_hmrc_s8_routing.py`
was not called by any test, by `load_test_data.py`, or by anything else in
the codebase; the live DB's routing is already correct and backed up
(`core_routing_backup_20260803_hmrc_s8`), and `260815_Ownership_fork_routing_template.md`
is now the authoritative source for any HMRC_S8 rebuild or reuse against a
new asset class. If HMRC_S8 is later folded into `load_test_data.py` under
D3, it should use that command's existing idempotent `route()` helper
against the compound-condition fields, not a resurrected standalone command.

### New, 31 July 2026: Tailor exit gate
After the three triage pages are submitted and all triage sections are marked complete, check every Yes-answered triage question against `QUESTION_SCHEDULE_MAP` and built-section status — reusing `_get_built_schedule_items`'s existing logic. If any Yes-answered item maps to no built schedule section, redirect to a holding page naming the specific unbuilt items rather than allowing entry to an action list with dead-end `#` URLs. Log which triage questions triggered each block, for beta prioritisation.

Current state (confirmed by live DB query 31 July 2026): only HMRC_S4 (property) questions `HMRC_16` and `HMRC_31` have `QUESTION_SCHEDULE_MAP` entries. HMRC_S5 (pensions, HMRC_24–30) and HMRC_S6 (other assets) have no entries at all. The gate would therefore block all pension and other-asset Yes answers until those schedules are built — which is the correct behaviour at this stage.

---

## SOON

### D1: Build IHT Reckoner Parts 1 and 2
The single route (Part 3: `reckoner_single`, `HMRC_S3`) is built and
correctly gated. Parts 1 (married/civil partnership) and 2 (widowed) still
to build. Both need flow documents equivalent to `IHT_Reckoner_Part3_Flow-2.md`
before building; key points outlined in that doc. The HMRC_14/HMRC_43
(Yes/No) reckoner routing has been verified as correct — no pre-work needed
on that mapping before starting.

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
- When HMRC_S8 (or any other asset-class section) is added to
  `load_test_data.py`, use the existing `route()` helper against the
  compound-condition fields (comparator_1/test_value_1/alternate_condition_id/
  comparator_2/test_value_2) — do not reintroduce a standalone rebuild command.

### D6: Permission grant UI — case selection step
The grant wizard at `/tools/actors/` needs an optional step:
"Do you want to limit this grant to a specific case?"
Shows dropdown of subject user's cases for the selected regime.
Full scope matrix in Core Platform Reference section 6.
Prompt already drafted — ready to fire at CC.

### New, 3 August 2026: Admin UX for two-slot Routing conditions
The Routing admin form still only surfaces the old fields (answer_value,
condition_question_id, comparator, threshold_value). The five new
compound-condition fields exist on the model and are evaluated correctly
by _evaluate_routing, but have no ergonomic admin surface — new compound
routing rows currently require manual DB/fixture creation, as done for
the full HMRC_S8 rebuild (15 August 2026). Not blocking any single item
now, but the manual-SQL route doesn't scale to the other asset classes
that will eventually reuse the same ownership-fork pattern (see the
asset class configuration register, Annex 3B §6) — worth building before
the next asset-class section needs it.

### New, 3 August 2026: Validation-strictness pass on compound Routing rows
No model-level constraint prevents a self-contradictory row — e.g.
comparator_2 set without alternate_condition_id. _evaluate_routing
currently treats such a row as silently never-matching rather than
erroring (_matches receives all_answers.get(None) → None → False). Low
risk today (no live rows in this state), but worth a validation pass —
either a model clean() method or a check in the routing admin tools —
before authoring gets more widespread. See prototype's Outcome.
__post_init__ for the equivalent guard in the reference implementation.

### New, 7 July 2026: Formalise orchestrate.py's direct core-internals access
Per Coherence Audit Item 8: `orchestrate.py` currently reads `Section`,
`Routing`, `QuestionSetMember`, and `Regime` directly from `core.models`,
and imports `resolve_user` from `core.nav_reference` (a non-interfaces path).
Decide which of these reads should become documented `interfaces.py` helpers
versus which are legitimately structural (i.e. the dept layer reading its
own regime structure, not citizen data). Then implement: add helpers to
`interfaces.py` for any reads that belong there; leave direct imports only
for what's genuinely outside the data-access boundary. The correctness rule
(`case.user` vs `request.user`) already documented in Core Platform Reference
section 4a is the model for what a documented boundary looks like.

### New, 21 August 2026: `_build_section_tables`'s `section=None` default fails silently

`_build_section_tables(routing_rows, section=None)` — added 16 August
2026 as part of `SectionQuestionGuidance` — only resolves guidance/hint
overrides when a `section` is actually passed in. When it isn't (the
default), the function doesn't error or warn; it just falls back to each
question's own `guidance`/`hint`, indistinguishable from "there's
genuinely no override for this question." Both current call sites (the
department-facing routing-replay helper, and `load_cache_for_routed_section`)
correctly pass `section` through — but nothing prevents a future call
site from omitting it, and the resulting bug would look exactly like "the
override exists in the DB but isn't showing," which already cost real
diagnostic time once this session (chasing session caching and template
rendering before finding the actual cause was a missing render block —
not this issue, but the same *symptom*, and a missing `section` argument
would present identically).

**Options, roughly in order of how much they cost to build:**
1. **Do nothing, keep documenting it** — current state. Cheapest, but the
   sharp edge stays sharp for whoever adds the next call site.
2. **Log a warning when `section` is `None`** — cheap, non-breaking,
   makes the silent case visible in logs without changing any behaviour
   or call site.
3. **Make `section` a required, non-defaulted parameter** — forces every
   call site to make the choice explicitly (including deliberately
   passing `None` if that's ever genuinely intended), catches a missing
   argument at call time via `TypeError` rather than at "why isn't my
   guidance showing" debugging time. Requires touching both existing call
   sites (trivial — they already pass it) but is the most robust option.

**Recommendation:** (3) — the existing call sites already pass `section`
correctly, so this costs nothing for them and closes the gap for good
rather than just making it easier to notice.

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

### New, 7 July 2026: "How to build a new department app" guide
With `dept_defra` and `dept_dwp` gone, HMRC/IHT is the only worked example
of the orchestrator boundary-controller pattern. Before institutional memory
of the pattern lives only in one file, document it explicitly:
- The three mandatory session keys (`regime_home_url`, `return_url`,
  `user_id`/`actor_id`) and who writes/reads each
- ENTRY/EXIT distinction: what the orchestrator must do on each side of a
  `call_core` call
- `call_core`'s contract: what it reads from PSS, what it writes back
- The identity gate (`choose_user_for_regime`) and when to use it
- How to wire the two-phase pattern (`iht_in_core` / `iht_current_action`)
  for action buttons
- URL structure and namespace conventions

Then **prove the guide's completeness by building one small fresh second
dept from it** — a minimal scaffold with one regime, one section, and a
working orchestrator — rather than leaving it as untested documentation.

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

### ~~D20: `radio_inline` in row journey templates~~ — **Complete (30 July 2026)**
Fixed: `table_routed_question.html` branch condition merged to include
`radio_inline`; `govuk-radios--inline` CSS class now applied conditionally.
`table_routed_set.html` was already correct. 1 new test
(`test_radio_inline_question_renders_inline_class_not_text_input`). 188 tests
passing (1 skipped). Prerequisite for D18 (IHT405 property sections), where
ownership-type and the Qa/Qb marital-status branch (step 2/3a in Annex 3B
row template) are both `radio_inline` questions.

### DOC G6: README
Government-audience README: what the PoC is, how to run it, architecture
portability, how to add a new department. Draft after D1–D5 complete.

### D12: Note — `post_confirm_redirect` scoping (platform consideration)
Currently unscoped; not causing any conflict today. If a genuine conflict
arises in another regime, consider scoping it by section_id. Not urgent.

### New, 31 July 2026: S5/S6 schedule allocation — pensions and other assets
HMRC_S5 (pensions and life assurance, questions HMRC_24–30) and HMRC_S6 (other
assets and liabilities, HMRC_32+) have no `QUESTION_SCHEDULE_MAP` entries and no
allocated Schedule records at all — confirmed by live DB query 31 July 2026. Before
building any of these, design the schedule allocation explicitly:

Pension sub-types (state pension / workplace pension / personal pension / life
assurance) are likely different HMRC forms and cannot be assumed to share one schedule
the way S4's property fork works. S6 similarly spans heterogeneous sub-types (jointly
owned assets, business interests, and others). Do not assume 1-category-to-1-schedule
— design the mapping per sub-type, confirm with HMRC which forms are needed, then
add entries to `QUESTION_SCHEDULE_MAP` and create the Schedule records before any
triage journey for S5 or S6 can proceed to an action button.

### New, 31 July 2026: Deferred property detail sub-questions (D18 follow-ups)
The following were explicitly parked during D18 build — not yet started:
- Lease length and rent details (leasehold property, no-valuation branch step 5)
- Damage description (property affected by damage — no-valuation branch step 5)
- Insurance cover questions (HMRC_58/59 sub-detail)
- Professional-valuation upload subsystem — requires real file-storage
  infrastructure; a simple text field is not sufficient. Not started.

All four live inside the "no professional valuation" branch. The gateway question
(HMRC_60: "Is the overall property value supported by a written professional
valuation?") is live; the Yes path (upload prompt) and the sub-detail No-path
questions are placeholders only. [Corrected 15 August 2026 — this entry previously
misnamed the gateway question as HMRC_62, which is actually the "% passes to
spouse" question, unrelated to valuation.]

---

## TIDY — Housekeeping

- **New, 16 August 2026: `Section.section_guidance` appears orphaned — check and likely remove** —
  `section_guidance` (TextField, nullable) is settable via the admin section create/edit forms,
  is carried over when a section is duplicated via "copy section," and its inline doc comment
  describes it as "shown at the top of table sections." But it is not rendered anywhere
  citizen-facing: none of the six citizen-facing table templates (`table_add.html`,
  `table_landing.html`, `table_routed_add.html`, `table_routed_question.html`,
  `table_routed_set.html`, `table_row_detail.html`) reference it, and no view passes it into
  a citizen-facing context. It looks like a field built for an early version of table sections,
  before `QuestionSet.set_hint` existed — `set_hint` now does the job `section_guidance` was
  presumably meant to do, and unlike `section_guidance`, it is live: rendered via
  `{% if set_hint %}<div class="govuk-hint">{{ set_hint }}</div>{% endif %}` in both
  `question_set.html` and `table_routed_set.html`.
  Action: confirm via git history whether `section_guidance` was ever wired up and later
  stripped out, or never wired up at all. If confirmed dead: remove the field, its admin form
  inputs (`tools_section_create.html`, `tools_section_edit.html`), and its handling in
  `views_admin_tools.py` and section-copy logic. Same shape of tidy-up as the HMRC_53 orphan —
  a leftover from an earlier design iteration that should be removed rather than left to confuse
  the next person who reads the model and assumes it does something.

- **New, 16 August 2026: Policy question — should a branching question ever be embedded inside a QuestionSet?**
  Raised while scoping `SectionQuestionGuidance` (guidance/hint override
  model, see Completed 16 August 2026). A SET is a single atomic routing
  node — `question_to_set` maps the whole set to one `current_node`; all
  members are answered together on one page, and the outer routing
  evaluates that node once to pick a single `next_node`. There's no
  mechanism for routing to branch off one member's answer while the set
  page is still being shown.

  For genuine fork-defining questions — HMRC_46, HMRC_49, HMRC_51, HMRC_52,
  HMRC_55 (the ownership-fork block; each one's own answer is what routing
  evaluates to select the next node) — burying one inside a multi-question
  SET screen doesn't fit this model well and is of doubtful UX value besides
  (citizen submits a whole page, then branches on just one sub-answer within
  it). Current view: probably shouldn't be allowed, but not yet a settled
  policy.

  **Consequence for now:** `SectionQuestionGuidance` deliberately only
  resolves against `question_table` — i.e. questions reached directly as
  their own routing node. It does **not** look up overrides for
  `set_table` members. If a branching question is ever embedded in a SET,
  its guidance/hint override (if any) would silently be ignored in that
  context.

  **Action:** settle the underlying policy question (should branching
  questions be allowed inside SETs at all?) before this gap matters. If the
  answer ends up "no, never," this item can simply be closed with no build
  work needed. If "yes, sometimes," extend the guidance-override lookup to
  also check `set_table` members at that point — the SET-facing code paths
  in `_build_section_tables` (`views_layer2.py`) are the place to do it,
  mirroring the `question_table` handling already built.

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

- **New, 15 August 2026: HMRC_53 (Question) — orphaned, no routing row references it** —
  Previously used (incorrectly, per Annex 3B) by HMRC_S8's tenants-in-common branch;
  superseded by HMRC_55 reuse in the 15 August 2026 HMRC_S8 rebuild. The Question record
  itself is untouched and still live, just no longer routed to from anywhere. Distinct
  from the four dead Routing fields tracked below — this is a dead Question, not a dead
  field. Retire, repurpose, or leave; no urgency.

- **New, 15 August 2026: HMRC_58 question_text typo** — "Was the property value ubject to
  any special factors..." should read "subject". Cosmetic, noted during the 15 August
  HMRC_S8 rebuild but not fixed at the time.

- **New, 3 August 2026: Remove dead Routing fields and _resolve_routing_answer** —
  condition_question_id, answer_value, comparator, threshold_value (model
  fields) and _resolve_routing_answer (views_layer2.py) are dead — no
  longer read by any evaluation path as of Phase 5 (3 August 2026).
  Deliberately kept in place pending the admin UX update above and a final
  grep confirming no remaining references. Requires a further migration to
  drop the columns once removed.

- **New, 7 July 2026: Split `views_admin_tools.py`** — flagged early in the
  audit/tidy session; at 3,300+ lines it is the largest file in the codebase
  and blends question, section, routing, regime, schedule, and permission
  wizard logic in one module. Natural split: one file per wizard domain.
  Low risk (internal to admin; no public interface), but deferred as
  non-urgent housekeeping.

---

## Completed (7 July 2026 — audit and tidy session)

- **Completion routing unified** — single precedence chain
  (post_confirm_redirect → all-complete → schedule-complete → return_url →
  fallback) documented and enforced, inline in `section_done` (there is no
  separately named `resolve_completion_url` function — that name was used in
  this entry as a concept label only). `regime_top_level` gaps fixed:
  `return_url` now written correctly and breadcrumb appended on every visit.

- **META mechanism fully removed** — code (meta_processors.py,
  tools_create views, templates) and live data (META regime, sections,
  M_N questions in load_test_data.py).

- **Table-journey `request.user` → `case.user` fix** — 16 instances across
  `views_layer2.py` corrected to use `case.user` for Answer/SectionStatus
  reads and writes, per the correctness rule in Core Platform Reference
  section 4a.

- **Reckoner routing corrected to HMRC_14/HMRC_43 (Yes/No shape)** — the
  single-estate route (`reckoner_single`, `HMRC_S3`) built and verified.
  Married (Part 1) and widowed (Part 2) correctly gated as not-yet-built;
  `RECKONER_SECTION` mapping re-verified against new Yes/No + HMRC_43 shape.

- **`interfaces.reset_section_progress` and `interfaces.promote_case_to_verified`
  added** — replacing raw ORM mutations previously scattered across
  `orchestrate.py` and `matching.py`. Dept code now calls documented
  interface functions for these operations rather than writing to core
  models directly.

- **Dead code removed** — `_get_verified_case` (orchestrate.py),
  `call_schedules` and `call_sections` (interfaces.py),
  `select_schedule` and `select_section` (nav_reference.py).

- **`call_core` fixed to read `regime_home_url` from PSS** — previously read
  from raw `request.session`; now reads from `get_session(request)` (PSS
  namespace). Pre-write ordering fixed in DWP, DEFRA, and HMRC generic views
  so the URL is in PSS before `call_regime` is called. Verified across all
  three dept flows.

- **`dept_defra` and `dept_dwp` removed entirely** — pre-removal audit in
  `260707_DEFRA_DWP_Audit.md`; no models, no migrations, no DB table drops
  required. 18 DWP tests removed; 187 tests passing post-removal.

- **Coherence/architecture audit run** (`260706_Coherence_Audit.md`) — 8
  findings. Resolved in this session: Items 1–7 (request.user bugs, dead
  code, session-key inconsistency, reckoner routing, interface boundary
  violations, duplicate-path documentation). Carried forward: Item 8
  (formalise orchestrate.py's direct core-internals access — see SOON above).

- **Standing rules added to `260701_Initial_Prompt.md`:**
  - Commit at end of every verified session before any worktree is created.
  - Never run concurrent `manage.py test` invocations against the Neon test
    DB — several test classes use fixed-ID fixtures in `setUpTestData` and
    will produce spurious unique-constraint errors under concurrent execution.

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
  it (`dept_defra` and `dept_dwp` were removed before migration).

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

## Completed (31 July 2026)

- **D18 — IHT405 property section (HMRC_S8) built and live-tested** (routing in `58e480d`) —
  SET10 (identification + ownership type) through END: ownership fork (sole / joint tenants /
  tenants in common), spousal-exemption exit (3a = Yes → END), valuation-trust gateway. 25
  routing rows, rebuilt via delete-then-recreate management command. All branches live-tested.
  **(Superseded 15 August 2026 — see above: shared opening reordered, spousal-exemption
  question rebuilt from binary to three-way, TIC branch restructured, HMRC_53 retired.)**

- **D20 — `radio_inline` in type-2 row journey templates** (`ae9353e`) — already marked
  complete 30 July 2026; confirmed still present in Completed (30 July 2026) below.

- **Silent-END routing bug fix** (`86b713a`) — `section_table_routed_question` discarded the
  `found` flag from `_evaluate_routing`; a missing routing row was indistinguishable from a
  legitimate END and the partial row was silently committed. Now captures `found` at both call
  sites (Q-node and S-node paths); on `False`, row not committed, mismatch logged server-side,
  page re-renders with a `routing_error` banner.

- **Set-member answer pruning fix** (`f0075d1`) — `asked_ids` pruning at commit time dropped
  all set-member answers: sets were tracked by set node ID (`SET10`) but member answers stored
  under individual question IDs. Fixed: `asked_ids` expanded to `allowed_keys` (set IDs +
  member question IDs) before the prune.

- **`dept_id` schedule-fallback regression test** (`68845c9`) — existing fallback logic
  (`section.regime → section.schedule.regime`) in `tools_section_edit` confirmed correct by
  inspection; regression test added to lock it. No code change required — root cause was a
  missing `schedule_id` link on the section (data fix, not code).

- **D22 — check-your-answers / view-amend for type-2 rows** (`f5eea14`) — `section_table_row_review`
  and `section_table_routed_amend` added; `review.html` reused for row-level check/amend,
  replacing separate "Change" + "Other details" action columns with a single "View/amend" link.
  Stale-tail truncation on amend: `asked_ids` cut at the amendment node so downstream stale
  answers are absent at commit.

- **Numeric column formatting** (`e5d0447`) — type-2 table landing: numeric columns
  right-aligned and comma-formatted (`f'{val:,.2f}'`); `values` and `totals_row` now
  `{text, align}` dicts; GDS `govuk-table__header--numeric` / `govuk-table__cell--numeric`
  classes applied per column.

- **Address rendering in type-2 row set pages** (`90f3f45`) — `table_routed_set.html` had no
  address branch; `question_type='address'` members fell through to a single plain text input
  storing nothing (actual sub-fields named `address_line1_{qid}` etc.). Fixed: address branch
  added to template; POST handler assembles sub-fields into a structured dict; GET handler
  populates `address_parts` for pre-fill. Four stale HMRC_S8 rows with flat-string addresses
  deleted.

- **Action-list empty-category fix** (`df0f1b2`) — triage categories with zero Yes-answered
  triage questions (e.g. HMRC_S5, HMRC_S6 on a property-only estate) no longer appear as
  "Complete" on the IHT home page; `if not set_items: continue` in `_build_action_list` omits
  them entirely.

- **Build reference doc updates** (`debb7c3`) — all three build docs updated to reflect 31 July
  session changes: D18–D22 and triage fix in HMRC IHT doc; pruning bug/fix, D22 landing table,
  D20 radio_inline, numeric formatting, and address rendering in Core data model doc; line count
  and urgency update in Core file map doc. Doc impact: none (doc-only commit).

## Completed (22 August 2026)

### HMRC_S9 — Stocks and shares section built end-to-end

Built HMRC_S9 (Stocks and shares, type-2 routed table) as a third direct-dispatch
section alongside HMRC_S7/HMRC_S8, sharing the same ownership-fork block
(HMRC_46–62) unchanged by ID. Key differences from S7/S8:

- **Opening:** SET12 (identification — name of holding, HMRC_63 broker/platform,
  HMRC_64 description) and an initial identification-type branch question
  (HMRC_63) with five branches — the first section where the fork applies to the
  identification step itself rather than only downstream of a single fixed opening.
  SET14 handles the value/unit capture for the path that needs it. Unlike S7 and
  S8, the identification fork required using `alternate_condition_id` (not
  `condition_question_id`) at SET12 itself — the first live use of the
  `alternate_condition_id` field on a SET-level routing row.
- **Questions:** HMRC_63–75. 30 routing rows total.
- **Tail:** no equivalent of HMRC_S8's valuation-evidence tail (HMRC_60/56–59).
  Like S7, every fork branch terminates at the ownership fork or the spousal
  destination — no substitute evidence questions needed.
- **`QUESTION_SCHEDULE_MAP` entry:** `'HMRC_32': ('section', 'HMRC_S9')` —
  triage Yes-answer on HMRC_32 dispatches directly to HMRC_S9 rather than
  through a schedule listing, identical pattern to HMRC_16→S8 and HMRC_17→S7.
- **SectionMember associations:** all routing nodes added as `SectionMember`
  rows for HMRC_S9.

**Test coverage:** Manually exercised via live UI through all five HMRC_63
branches, both ownership-fork paths (Sole/Joint/TIC-equal/TIC-unequal),
and both spousal-destination outcomes (All of it / Some of it). All routes
confirmed against live `AnswerTable` data. Automated test:
`test_hmrc_32_yes_dispatches_directly_to_s9` (new, in `TestTriageDirectSectionDispatch`).

Doc impact: HMRC IHT Reference (new §13 — HMRC_S9); Ownership-fork routing
template (third confirmed reuse case); Backlog §8a (QUESTION_SCHEDULE_MAP entry).

---

### `set_guidance` added to `QuestionSet`

New optional `TextField` (`set_guidance`, blank=True, null=True) on `QuestionSet`.
Migration `0021_add_set_guidance_to_questionset`. Rendered above the existing
`set_hint` line as `govuk-inset-text` using the `render_markdown` filter.

Touchpoints: model + migration; `_build_section_tables` (builder); four view
context dicts (`section_set_page`, `_process_set_answer`, `section_table_routed_question`
×2); `question_set.html` and `table_routed_set.html` templates (both gain
`{% load markdown_extras %}` and the guidance block); admin add/edit form
templates (`tools_set_add.html`, `tools_set_edit.html`); admin display views
(`tools_sets_list.html`, `tools_sets_edit_picker.html`, `tools_viewer.html`);
`tools_set_add` and `tools_set_edit` POST handlers in `views_admin_tools.py`.

General platform capability — not HMRC_S9-specific. Any QuestionSet can now
carry freeform markdown guidance shown as an inset-text block above the hint.

Doc impact: Core Platform Reference §3 (`QuestionSet` field docs).

---

### PlatformRouter migration-bookkeeping bug found and fixed

`PlatformRouter.allow_migrate` correctly refuses migrations on the `default`
alias for `Question`, `QuestionSet`, and `QuestionSetMember` — but `django_migrations`
records them as applied anyway (because `default` and `platform` share one
physical DB and one migrations table). The result: `python manage.py migrate`
silently reports success while leaving the schema change absent from the alias
that actually matters.

Confirmed incident: `0021_add_set_guidance_to_questionset` was marked applied
on `default` without the `set_guidance` column ever being added, until caught
and re-run explicitly against `platform`.

**Fix:** `core/management/commands/migrate_all.py` — iterates `settings.DATABASES`
and calls Django's built-in `migrate` against every alias in sequence. Use
`python manage.py migrate_all` (not bare `migrate`) for any migration touching
the three PlatformRouter-routed models. Rule documented in Core Platform
Reference §7 and in `CLAUDE.md`.

Doc impact: Core Platform Reference §7 (already updated in this session).

---

### Triage dispatch fix — QUESTION_SCHEDULE_MAP values changed to (type, id) tuples

`QUESTION_SCHEDULE_MAP` in `orchestrate.py` previously mapped triage question IDs
to bare schedule ID strings. Changed to `(type, id)` tuples, where `type` is
`'section'` or `'schedule'`. `_get_built_schedule_items` updated to branch on
type: section-type entries check `CoreSection.objects.filter(section_id__in=...)`
and emit `{'type': 'section', 'id': ...}` items; schedule-type entries continue
as before.

Effect: a triage "Yes" answer can now resolve directly to a bare `Section` on
the regime (bypassing any schedule-listing intermediate page), or to a schedule
as before. `call_core` already handles both `type: 'section'` and `type: 'schedule'`
items — no core change needed.

**Re-parenting:** HMRC_S7 and HMRC_S8 were re-parented from their schedules
(HMRC_SCH4 and HMRC_SCH2 respectively) to bare sections directly on `HMRC_IHT`
(schedule_id → null, regime_id set). `HMRC_16`, `HMRC_17`, `HMRC_32` map
updated to `('section', 'HMRC_S8')`, `('section', 'HMRC_S7')`, `('section', 'HMRC_S9')`.
`HMRC_SCH3` (other land, HMRC_31) left as a schedule entry — empty schedule,
pre-existing gap, untouched deliberately.

7 new tests (`TestTriageDirectSectionDispatch`): unit tests for section-type
and schedule-type resolution and order preservation; dispatch integration tests
for HMRC_16→S8, HMRC_17→S7, HMRC_32→S9; regression guard for HMRC_18→SCH5.
235 tests total (all pass).

Doc impact: HMRC IHT Reference §8a (QUESTION_SCHEDULE_MAP and
`_get_built_schedule_items` description); §12 (HMRC_S7 schedule assignment
corrected).

---

### Row-review Confirm button — `back_label`/`back_primary` context keys

`core/templates/core/review.html` and `section_table_row_review` in
`views_layer2.py` now support two optional context keys:

- `back_label` — overrides the default "Back to list" link text
- `back_primary` — if True, renders the button without `govuk-button--secondary`
  (i.e., green primary button instead of grey secondary)

`section_table_row_review` sets both (`back_label='Confirm'`, `back_primary=True`)
so the row-review page's link appears as a green "Confirm" button. Cosmetic only
— the row commit still happens on the last routing answer node, not on this click.
All other callers of `review.html` that don't set `back_url` are entirely
unaffected (confirmed by grep: only two callers, `section_review` and
`section_table_row_review`; `section_review` does not set `back_url`).

Doc impact: Core Platform Reference §4d (type-2 row review).

---

### GOV.UK error-handling standard — seven question templates

Applied the full GOV.UK error pattern to all seven simple question templates
that were previously missing field-level errors or correct summary linking:

**Group A** (`question_text`, `question_radio`, `question_radio_inline`,
`question_checkbox`): added `govuk-form-group--error` wrapper class;
`govuk-error-message` paragraph with `id="{field}-error"` and `<span
class="govuk-visually-hidden">Error:</span>`; `aria-describedby` on inputs/
fieldsets chaining hint id and error id; `govuk-input--error` /
`govuk-textarea--error` on inputs; error summary updated from bare `<p>` to
`<ul><li><a href="#answer">`.

**Group B** (`question_date`, `question_personal_name`, `question_address`):
added `id` to `<fieldset>` (`date`/`name`/`address`) so summary `href`
resolves; error summary updated to `<ul><li><a href="#{id}">`.
Removed the duplicate `id="date"` from `govuk-date-input` inner div (moved
to fieldset instead).

21 new tests in `TestQuestionErrorHandling` asserting (a) field-level error
message id, (b) `govuk-form-group--error` class, (c) summary href per template.
256 tests pass.

- `7a91f65` — GOV.UK error-handling standard applied to all seven simple question
  templates + 21 new tests. Doc impact: none (pattern change only, no doc section covers this).

---

### Question-level validation fields (required, max_length, min/max, min_date/max_date, no_future_date, regex)

**Phase 1 — Schema.** Eight new fields on `Question` (migration `0022_question_validation_fields`):
`required` (BooleanField, default=True), `max_length` (nullable IntegerField), `min`/`max`
(nullable DecimalField, max_digits=12, decimal_places=4), `min_date`/`max_date` (nullable
DateField), `no_future_date` (BooleanField, default=False), `regex` (nullable CharField,
max_length=255). All nullable/Boolean-defaulted so no backfill needed; default=True on
`required` preserves every existing row's current behaviour exactly.

Migration applied to the physical table via fake-unapply-on-default workaround (identical
root cause to 0021 incident: PlatformRouter skips `Question` ops on `default` alias but
marks the migration as applied in the shared `django_migrations` table, so `platform` alias
then finds nothing to do). Confirmed correct: all 8 columns now exist in `core_question`.

**Phase 2 — Validation.** `_process_answer` in `views_layer2.py` refactored for plain-answer
types (text, textarea, number, radio, radio_inline, checkbox):
- Replaced unconditional non-empty check with `required`-gated check. `required=False` lets
  a blank answer advance. `required=True` (default) errors with derived message
  `'Enter ' + question_text.lower().rstrip('?').rstrip('.')` — matching `_process_set_answer`
  pattern, replacing the old generic 'Please answer this question before continuing.'.
- Additional checks (each only when the field is set): `max_length` → character count;
  `min`/`max` → float comparison; `min_date`/`max_date` → parse answer as ISO date and
  compare; `no_future_date` → compare parsed date to today; `regex` → `re.match`.
  All messages derived from `question_text`. Non-date answers silently skip date checks.
- Decimal→float and date→ISO-string conversions in `_build_section_tables` so `question_table`
  remains JSON-serialisable when stored in the session.
- Existing date/personal_name/address/compound validation blocks untouched.

**Phase 3 — Admin.** `tools_question_add` and `tools_question_edit` views updated to
read/save all 8 new fields. Both templates gain a collapsed `<details>` section for the
new fields (auto-open on edit if any constraint is set). `required` and `no_future_date`
render as inline radios; numeric/date/regex fields as text inputs.

20 new tests in `TestQuestionValidationFields`; 276 pass (was 256).

- `2bf5927` — Question validation fields (schema + logic + admin). Doc impact:
  Core Platform Reference §3 (Question field docs — new fields not yet documented).

### Date-question constraint validation + migrate_all ordering fix

**Instruction 1 — date constraints.** Extended the date-type validation block in
`_process_answer` (`views_layer2.py`) to check `min_date`, `max_date`, and
`no_future_date` after individual day/month/year checks pass. Guard: if day/month/year
individually fail, constraint checks are skipped (no date construction attempted).
Error messages derived from `question_text`. `try/except ValueError` catches invalid
combinations (e.g. Feb 31) that pass individual checks.

13 new tests in `TestDateQuestionConstraints`: baseline behaviour (no constraints),
`no_future_date` (past/today advance, future errors, invalid components skip constraint),
`min_date`/`max_date` (inside/on-boundary advance, outside range errors, invalid
components skip constraint). 288 tests pass (1 skip).

**Instruction 2 — migrate_all ordering.** Fixed `migrate_all.py` to sort `platform`
before `default`. Root cause of migration 0022 incident: both aliases share one physical
DB / one `django_migrations` table; whichever alias runs first marks the migration as
applied. Running `default` first caused PlatformRouter-routed `AddField` operations to
be silently skipped. Fix: `sorted(settings.DATABASES, key=lambda a: (0 if a == 'platform' else 1, a))`.

- `b99880f` — Date constraint validation + migrate_all ordering fix. Doc impact:
  Core Platform Reference §5 (migrate_all — ordering requirement not previously documented).
- `c3a5779` — Extend validation constraints to Set-member questions. Doc impact: none
  (build docs don't document the constraint fields in detail yet).
- `02a8e9c` — Extract `_extract_answer`/`_validate_answer` helpers; wire all three POST
  paths (`_process_answer`, `_process_set_answer`, `section_table_routed_question`).
  Fixes missing date/personal_name extraction in table-routed views; adds validation
  to `section_table_routed_question` (previously had none). Doc impact: none.
- `c5db7b6` — Fix `_triage_set_rollup` two bugs: (1) `_get_active_triage_items` now
  populates `detail_type`/`detail_id` from `QUESTION_SCHEDULE_MAP` instead of hardcoding
  `None`; (2) rollup returns all three states. New `_item_rollup_status` helper handles
  schedule-type items. 9 new tests. Doc impact: none.
- `6153397` — GDS error display for `table_routed_question.html` and `table_routed_set.html`:
  proper `<ul><li><a>` error summary, `govuk-form-group--error`, `govuk-error-message`,
  `govuk-input--error`, `aria-describedby`. `routing_error` reserved for config-error case
  only. 13 new tests. Doc impact: none.
  items by rolling up all child sections. 9 new `TestTriageSetRollup` tests. Doc impact: none.

---

## Completed (19 August 2026)

- `49cf5cf` — Fix table_routed_question.html not rendering question.guidance: added
  {% load markdown_extras %} and govuk-inset-text block (matching standard question templates).
  Also added integration test asserting override text reaches rendered HTML (not just context dict).
  228 tests, 1 pre-existing failure (test_solicitor1_reaches_sched_s3_table, confirmed broken
  before this commit), 1 skipped. Doc impact: none.

---

## Completed (18 August 2026)

### HMRC_S7 — bank and building society accounts section built and routing-tested

Built the ownership-fork routing for HMRC_S7 (type-2 routed table),
reusing the shared block (HMRC_46/48/49/50/51/52/55/54/61/62) unchanged
from HMRC_S8 per `260815_Ownership_fork_routing_template.md`. Two
deliberate differences from property:

- **Opening:** `SET11` (bank name HMRC_40, account number HMRC_41,
  balance HMRC_42, one page) routes straight to HMRC_46 — no separate
  chained identify/value questions as in S8.
- **Every S8 destination of `HMRC_60`** (the property valuation-evidence
  gateway) becomes `END` for S7, and the entire property-specific tail
  (HMRC_60, HMRC_56–59) is absent — bank accounts need no substitute
  chargeable-value evidence.

23 routing rows total, inserted via direct SQL (`core_routing`,
`section_id='HMRC_S7'`), 18 August 2026. `core_section` row confirmed
correct: `section_type=2`, `schedule_id='HMRC_SCH4'` (pre-existing
`QUESTION_SCHEDULE_MAP` entry `HMRC_17 → HMRC_SCH4` means reachability
from S4 triage required no new build).

**Test coverage:** manually exercised via two test cases (a married
subject and an unmarried subject) covering every reachable branch —
all 12 non-END transitions in the routing table individually confirmed
against live `AnswerTable` data:

| Transition | Confirmed by |
|---|---|
| Sole, spouse → HMRC_55 | ✓ |
| Sole, no spouse → END | ✓ |
| Joint → HMRC_48 | ✓ |
| TIC → HMRC_49 | ✓ |
| HMRC_48 → HMRC_50 (married) | ✓ |
| HMRC_48 → END (unmarried, spouse check skipped) | ✓ |
| HMRC_50 → END, N=2 compound condition | ✓ |
| HMRC_50 → END, plain Yes (N≠2) | ✓ |
| HMRC_50 → END, No | ✓ |
| HMRC_49 → HMRC_51 | ✓ |
| HMRC_51 → HMRC_55 (equal share, spouse) | ✓ |
| HMRC_51 → HMRC_52 (unequal share) | ✓ |
| HMRC_52 → HMRC_55 (spouse) | ✓ |
| HMRC_52 → END (no spouse) | ✓ |
| HMRC_55 → HMRC_54 (some of it) | ✓ |
| HMRC_54 → HMRC_61 (£ value) | ✓ |
| HMRC_54 → HMRC_62 (% share) | ✓ |

**Bug found and fixed during testing:** `HMRC_48`'s question text still
read "...owned this **property**..." — a leftover from when the question
was first authored for HMRC_S8, never generalised the way its TIC sibling
HMRC_49 ("...this asset...") was. Fixed globally via direct SQL (see
entry below) — improves HMRC_S8's wording too, no routing impact.

### HMRC_48 question text corrected — leftover "property" wording

`HMRC_48` ("How many joint tenants owned this [asset/property] in total,
including the deceased?") still read "property" — a leftover from being
first authored for HMRC_S8, never generalised the way its TIC sibling
HMRC_49 was when the ownership-fork block was designed for reuse.
Surfaced during HMRC_S7 test-data review (a citizen would have seen a
bank account described with property wording). Fixed globally, live data:

```sql
UPDATE core_question
SET question_text = 'How many joint tenants owned this asset in total, including the deceased?'
WHERE question_id = 'HMRC_48';
```

No routing impact — text-only change, applies retroactively to HMRC_S8
as well as HMRC_S7.

---

## Completed (16 August 2026)

- `9d5a91e` — Add SectionQuestionGuidance per-section guidance/hint override model, migration,
  admin registration, views_layer2 wiring (_build_section_tables now accepts section arg and
  applies overrides per question), interfaces.py caller updated. 3 new tests; 227 tests pass
  (1 skipped). Doc impact: build doc §3 (data model — new model), build doc §4 (question table
  assembly in _build_section_tables).

---

## Completed (15 August 2026)

- **HMRC_S8 property routing — full rebuild (live data against Neon, no code commit)** —
  Restructured HMRC_S8's routing to close several gaps between the live build and the
  design (Annex 3B §1.1, §2.3, and 260801_IHT_ownership_branch_questions.md):
  - Shared opening reordered: value (HMRC_47) now asked before ownership type (HMRC_46),
    per Annex 3B §1.1 ("identification, then value, then ownership"). SET10 now routes to
    HMRC_47, not directly to HMRC_46.
  - HMRC_55 (spousal-destination question) reworded from a binary Yes/No to the three-way
    form the design specifies ("All of it" / "Some of it" / "None of it"), and its routing
    rebuilt to add the previously entirely-missing "Partly" path (→ HMRC_54 → HMRC_61/62).
    The old binary routing was also found to be silently unroutable — its rows tested
    against 'Yes'/'No', which matched none of HMRC_55's actual live option values.
  - Tenants-in-common branch restructured to reuse HMRC_55 (the same asked, three-way fact
    as sole ownership) instead of HMRC_53's joint-tenancy-style derived-fact pattern, which
    the design explicitly says TIC should not use (TIC shares pass by will/intestacy, not
    survivorship).
  - HMRC_53 retired: no longer referenced by any routing row (see TIDY, below).
  - New two-slot compound row for the joint-tenants N=2 vs N≥3 split (HMRC_50 AND HMRC_48)
    — the first live use of the Phase 3–5 compound-condition mechanism outside the Phase 4
    migration itself.
  30 routing rows total (was 26; pre-rebuild state backed up to
  `core_routing_backup_20260803_hmrc_s8`). Live-tested end to end across all three
  ownership branches, married and not-married, and both £/% spousal-value sub-paths, via
  real UI walkthroughs against production data — not just the test suite. This testing is
  what surfaced the `b7cb8e5` bug below, without which the married branches routed
  incorrectly regardless of actual marital status. Doc impact: HMRC IHT Reference (HMRC_S8
  section — supersedes the 31 July description below), build doc §5.

- `b7cb8e5` — Fix: load_cache_for_routed_section was scanning only condition_question_id
  when building external_condition_qids; alternate_condition_id (Phase 3 compound-condition
  slot-2 field) was never scanned. Any compound routing row referencing an external question
  via alternate_condition_id (e.g. HMRC_S8's married-branch rows referencing HMRC_14) always
  saw None for slot 2, silently failed, and fell through. Fix: scan both fields, deduplicated.
  2 new tests in TestRoutedSectionCache (EXT_ALT_S1 fixture); 224 tests pass (1 skipped).
  Doc impact: build doc §5 (type-2 routed table execution — external_condition_qids note).

---

## Completed (3 August 2026)

- `3ac331c` — Phase 1: load_cache_for_fixed_table_section() caching refactor, views_layer2.py.
  Doc impact: build doc §4 (type-1 table section execution).
- `48fa723` — Phase 2: load_cache_for_routed_section(), _fetch_external_answers(), external-condition
  answer fix across all five type-2 entry points, views_layer2.py + tests. Doc impact: build doc §5
  (type-2 routed table execution).
- `b9427b4` — Phase 3: add comparator_1/test_value_1/alternate_condition_id/comparator_2/test_value_2
  to Routing model; migration 0018. Doc impact: Core data model doc (Routing table schema).
- `3540712` — Phase 4: RunPython migration 0019 backfilling compound-condition fields on all 89 live
  Routing rows; TestRoutingEquivalence pre-flight test. Applied to live Neon DB 2026-08-03.
  Doc impact: Core data model doc (Routing field semantics).
- `8c8d59f` — Backlog: log Phase 4 entry. Doc impact: none.
- `c5707fe` — Phase 5: _evaluate_routing ported to two-slot compound-condition logic; 12 new
  tests (TestCompoundConditionRouting); old Routing fields marked dead; 220 tests pass.
  Doc impact: build doc §routing-engine (evaluation logic), §dead-fields note.
- `1a5b851` — Fix: stray _resolve_routing_answer call in interfaces.py
  get_asked_answers_for_section; 2 regression tests; 222 tests pass. Doc impact: none.

---

## Completed (30 July 2026)

- **Platform fix — silent-END on routing data errors (type-2 row journeys)** —
  `section_table_routed_question` discarded the `found` flag returned by
  `_evaluate_routing`, so a routing configuration error (no matching row for a
  given answer) was indistinguishable from a legitimate END — the partial row
  was silently committed and the user redirected to the section list with no
  error shown. Surfaced via HMRC_S8/property testing: HMRC_46's
  `Question.options` wording had drifted from its `Routing.answer_value`
  entries (`'Sole ownership'` → `'Sole ownership of the deceased'`;
  `'Joint tenants'` → `'Joint names'`). Fixed: `found` is now captured at
  both call sites (S-node and Q-node paths); on `False`, the row is not
  committed, the mismatch is logged server-side (section, node, routing answer),
  and the page re-renders with a `routing_error` banner instead. Commit
  `86b713a`. 1 test added confirming the error path; 189 tests passing (1
  skipped). **General implication:** any type-2 section is exposed to this
  failure mode if a question's options text and its routing table's
  `answer_value` entries ever drift apart. A pre-build check (question options
  vs routing values, exact string match) for future sections (D2 and beyond)
  would catch this class of error early — this fix surfaces it at runtime
  rather than preventing it.

- **D20 — `radio_inline` in type-2 row journey templates** — Fixed:
  `table_routed_question.html` branch condition updated to
  `question.question_type == "radio" or question.question_type == "radio_inline"`;
  `govuk-radios--inline` CSS class added conditionally. `table_routed_set.html`
  was already correct (used as reference). 1 new test in
  `TestConditionalTableSection`. 188 tests passing (1 skipped). Prerequisite
  for D18 (IHT405 property sections): ownership-type and the Qa/Qb
  marital-status branch (step 2/3a in Annex 3B row template) are both
  `radio_inline` questions.

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
- ~~`radio_inline` not yet supported in type-2 row journey templates~~ — fixed D20 (30 July 2026).
- Consistency checker: mixed `condition_question_id` values per node warns
  but does not block; only the first `condition_question_id` found is used
  by `_resolve_routing_answer` (sufficient for current patterns).

---

*Update by telling Claude what's done or what's new.*
