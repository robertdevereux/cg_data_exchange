# cg_data_exchange — Backlog
Date: 14 June 2026
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

### D2: Estate elements — stub to full build
Estate details action row currently `href="#"`.
Full build: sections for property, financial assets, jointly owned assets,
liabilities. Grouped into Schedule HMRC_SCH1.

### D3: Encode IHT regime in load_test_data
Once HMRC_S1 through HMRC_S5 stable, encode all regime/section/routing/
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
- Document iht_orchestrate/iht_screen/handle_reckoner as canonical
  dept orchestration pattern → maps to Salesforce master Flow + Screen

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
- Do NOT show the generic duplicate.html template (designed for first-time
  matching, no reference issued yet)
- Show a new `duplicate_amend.html` template explaining the conflict,
  preserving the existing IHT reference and all completed work
- Message: "We're unable to update the deceased's details as they now match
  another estate. Your existing submission (ref IHT-XXXXXXXXX) remains
  unchanged. HMRC will be in touch if needed."
- Single action: "Return to your submission"
- Restore original S1 answers (the amended answers should be discarded —
  need to store pre-amend answers before S1 entry, or re-fetch from DB
  snapshot). Design the restoration mechanism before building.

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

### DOC G6: README
Government-audience README: what the PoC is, how to run it, architecture
portability, how to add a new department. Draft after D1–D5 complete.

### D12: Scope `post_confirm_redirect` by section_id (platform change)
Currently `post_confirm_redirect` fires on any `section_done` while the
session key is set — including table sections. Dept code manages misfire
risk manually (e.g. clearing the key in `section_start` for S1). A cleaner
platform solution: store a `section_id` alongside the URL and have
`section_done` only consume the key if the completing section matches:
```python
request.session['post_confirm_redirect'] = {
    'url': reverse('dept_hmrc:iht_reckoner_compute'),
    'section_id': 'HMRC_S3',
}
```
This is a core change. Defer until a concrete misfire risk arises in
practice — the current manual approach is safe for existing IHT sections.

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

---

*Update by telling Claude what's done or what's new.*
