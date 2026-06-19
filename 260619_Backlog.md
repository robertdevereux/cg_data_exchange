# cg_data_exchange — Backlog
Date: 19 June 2026
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

Nothing currently active — see SOON for next priorities.

---

## SOON

### D1: Build IHT Reckoner Parts 1 and 2
Part 1 (deceased survived by spouse) and Part 2 (widowed).
Both need flow documents equivalent to `IHT_Reckoner_Part3_Flow-2.md`
before building. Key points outlined in that doc.

### D2: Estate detail sections — build from triage scaffolding
The triage scaffolding is complete (S4/S5/S6, active items dict, triage
set rows on home page). Next step: build actual detail sections for each
Yes-answered triage question. Pattern:
- Each triage set row (Common assets, Pensions, Other) gets a Level 2
  sub-page listing its Yes-answered items with status and Start/Continue
- Each item links to a detail section with the actual IHT schedule questions
- Wire up `detail_section` in `TRIAGE_DETAIL_MAP` (currently all None)
- Start with one asset type (e.g. bank accounts) as the pattern

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

### DOC G2: Vision Paper — minor amendment
One sentence amendment to section 6.1 already drafted:
"A Regime is composed of Sections, optionally grouped into Schedules..."
Apply and save as v0.3.

### DOC G3: Implementation Options — check for staleness
### DOC G4: Salesforce Implementation Plan — significant update likely
Two-tier question bank and Case/Permission changes have implications for
the Salesforce data model. Phase 1 data model section needs revisiting.

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
- Message: "We're unable to update the deceased's details as they now match
  another estate. Your existing submission (ref IHT-XXXXXXXXX) remains
  unchanged. HMRC will be in touch if needed."
- Single action: "Return to your submission"
- Also need to restore original S1 answers (the amended answers are already
  saved to DB by the time we detect the conflict). Design the restoration
  mechanism before building — options: store pre-amend snapshot before
  entering S1, or re-fetch from a DB backup point.

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
Jointly owned assets cut across all asset categories (home, bank accounts,
investments etc.) and have their own IHT schedule (IHT404) with distinct
tax treatment. Currently excluded from S4 (HMRC_20 not in Set S7).
Need to decide: separate top-level triage question, or two-pass approach
(common assets first, then jointly owned variants of same assets)?
Design before building.

### D14: IHT triage — nil rate band transfers
IHT400 Q29a–d (residence nil rate band, transfer of unused NRB etc.) are
a conceptually distinct category from asset/liability triage. Deferred
from the tailoring flow entirely. Design separately — likely a fourth
triage section or a dedicated action button.

### D15: Improve call_schedules to match call_sections behaviour
`call_schedules` currently always goes to the full schedule list page.
Should mirror the new `call_sections` pattern:
- `call_schedules` with one schedule_id → go direct to that schedule's
  section list (same filtered section list page, populated from the
  schedule's members), bypassing the schedule menu entirely
- `call_schedules` with multiple schedule_ids → filtered schedule list
  showing only the specified schedules, with a `title` parameter
This is a pure `core/interfaces.py` change plus a session-filter in
`regime_schedules` view, following the same pattern as the `call_sections`
fix already done.

### DOC G6: README
Government-audience README: what the PoC is, how to run it, architecture
portability, how to add a new department. Draft after D1–D5 complete.

### D12: Note — `post_confirm_redirect` scoping (platform consideration)
`post_confirm_redirect` is no longer used in HMRC IHT — all post-processing
happens in `iht_orchestrate` via the `iht_in_core` / `iht_current_action`
pattern. This is the preferred pattern for dept orchestration.
However `post_confirm_redirect` remains available in core for simpler
dept patterns that don't need full two-phase orchestration. If a misfire
risk arises in another regime, consider scoping it by section_id:
```python
request.session['post_confirm_redirect'] = {
    'url': reverse('...'),
    'section_id': 'HMRC_S3',
}
```
Not urgent — note for future reference only.

---

## TIDY — Housekeeping

- **Extract back-link calculation in `_process_answer`** — the back-link
  URL block is duplicated ~5 times across type-specific validation branches.
  Extract to `_get_back_url(pss, section_id, question_id)` helper.

- **Extract answer display formatting in `section_review`** — month-name
  expansion and dict-type detection logic duplicated verbatim for set-member
  and standalone question branches. Extract to
  `_format_answer_for_display(answer, question_type)` helper.

- **Consolidate `_get_or_create_case` in views_layer2** — private copy
  duplicates the one in `interfaces.py`. Remove and import from interfaces
  at D3.

- **Extract routing tree to shared Django include** — `tools_section_routing.html`
  and `tools_regime_edit_composite.html` both render the routing tree.
  Extract to `core/templates/core/_routing_tree.html`.

- **Hide or remove old META wizard at `/tools/create/`** — superseded by
  current admin tools. Retained for now.

- **Remove `get_or_create_case()`** — deprecated, still used by TEST/demo
  harness only. Remove when harness is updated.

- **Rationalise DWP app structure** — has legacy nav/ and regime/ subfolders,
  not yet aligned to canonical flat structure.

- **Consistency checker for QuestionSet nodes** — one skipped test.
  Complete when QuestionSet usage grows.

- **Refactor routing tree UI to shared `{% include %}` partial** — the
  routing tree HTML/CSS/JS exists independently in both
  `tools_section_routing.html` and `tools_section_edit.html`. Any UI
  change must currently be made in both. Extract to
  `core/templates/core/_routing_tree.html` and include from both.

---

## Completed this sprint (19 June 2026)

- **D2 (partial)** — IHT triage scaffolding built: S4/S5/S6 sections,
  24 `radio_inline` triage questions (HMRC_16–39), `call_sections` multiple-
  section behaviour, filtered section list with title, triage set rows on
  home page, active items dict built dynamically from DB
- **Two-phase orchestrate pattern** — `iht_in_core` / `iht_current_action`
  session flags, clean ENTRY/EXIT separation, no `post_confirm_redirect`
  in HMRC IHT, `call_sections` returns to `regime_home_url`
- **`radio_inline` question type** — model choice, template, set template
  support, dispatch in `views_layer2.py`
- **Core `call_sections` improvements** — single section goes direct,
  multiple sections show filtered titled section list, `return_url` set
  to `regime_home_url` not `request.path`
- **Matching refactor** — `iht_matching_result` and `iht_matching_amend`
  removed as URL-routed views; matching logic moved into `_exit_start` and
  `_exit_deceased_details` in orchestrate.py
- **Core cleanup** — HMRC_S1 guard removed from `section_start`
- **Documentation** — `260619_HMRC_IHT.md` created as single authoritative
  IHT reference, replacing three previous docs
- **115 tests passing, 0 failures**

---

## Known limitations (fix when they bite)

- `call_sections` / `call_schedules`: `regime_home_url` not set in session
  (only by `call_regime`). May cause redirect issues when all sections
  complete. Fix when it causes a problem in practice.
- Pre-population on set pages: works on amendment but not on first visit
  from a previous regime for compound types.
- Table section answer pre-population not yet implemented.
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

---

*Update by telling Claude what's done or what's new.*
