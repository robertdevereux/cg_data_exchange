# State of Play — Handoff Note (29 July 2026)

*For starting a new chat session. Covers the "core"/IHT project as of the end of a long working session on 29 July 2026.*

---

## 1. The pitch/design papers (the proposed design)

Six documents, in project files, prefixed `260729_`:

| Document | What it does |
|---|---|
| `Paper1_case_for_core.md` | Short (1–2pp) pitch to HMRC policy/digital leadership: the case for a single configurable "utility" (core) to replace hand-built forms, called by each service's own home page. |
| `Annex_A1_core_mechanism_policy.md` | Plain-language companion to Paper 1: the three section types, confirmation screens, pre-population, explained for a policy/ops/senior audience. |
| `Annex_A2_technical_architecture.md` | Technical companion to Paper 1: full spec for digital/data architects — the three section types (Standard/Table/Table-with-routing, `section_type` 0/1/2) as the primary organising structure, each with "In plain English / Configuration as data / Session data / Supporting functions," the permission/delegation model, the complete data model, NFRs. Old multi-department material compressed to an appendix (not part of the current ask). |
| `Paper2_two_problems_iht_data_gathering.md` | Independent policy case (doesn't depend on Paper 1 being accepted): three problems with today's IHT data gathering — the transferable-allowance time bomb, the sole-ownership bias, the reckoner's lack of persistence. |
| `Annex_3A_iht_design_policy.md` | Plain-language companion to Paper 3: action buttons as HMRC's own design (with real entry/exit examples from `orchestrate.py`), the marital-status/ownership interplay explained at a high level, the generic four-part asset row shape, a brief property illustration. |
| `Annex_3B_iht_design_technical.md` | Technical companion to Paper 3: the full generic asset row template, the Qa/Qb marital-status gate and Fork 1/Fork 2 per-row routing design (one deep path, two routes in), RNRB architecture, transferred allowances mechanics, the asset-class configuration register, worked property illustration, and two flagged-open decisions. |

**Paper 3 itself** (`Paper3_delivering_iht_via_core.md`) ties Papers 1 and 2 together into the concrete design, explaining how it answers each of Paper 2's three problems, and states plainly that it changes no tax policy — only the shape and sequence of questions.

**Two source design documents**, still in project files, now fully consolidated into and superseded by Annex 3B (safe to retire once you're comfortable):
- `260628_iht-journey-architecture.md`
- `260726_ownership_marital_template-4.md`

**Two archived documents**, superseded by Paper 1 + A1/A2 (kept locally, removed from project files):
- `260515_Vision_v0_2.docx` (the old cross-government pitch)
- `260607_Functional_Architecture_v03.docx` (the old technical spec, Vision-toned)

**Two open design decisions**, flagged but not resolved anywhere:
1. Per-asset-class valuation-evidence substitute questions (beyond property) — needs policy input, class by class.
2. Second-death journey: should it surface first-death asset detail (Option A) or only the transferred-allowance percentage (Option B)? Option A raises a cross-case consent question that needs settling with HMRC.

## 2. The Build reference docs (as-built, reconciled 29 July)

Three documents, now correctly dated and named:
- `260729_Build_CORE_data_model_and_interfaces.md`
- `260729_Build_CORE_codebase_file_map.md`
- `260729_Build_HMRC_IHT.md`

These were reconciled by Claude Code against a freshly-regenerated `file_dump.txt` and against `260714_Backlog.md`'s 7 July "audit and tidy" session, which had drifted out of the reference docs. Notable fix: Backlog had named a function, `resolve_completion_url`, that doesn't actually exist in code (the logic is inline in `section_done`) — corrected in both the Build docs and, separately, in Backlog itself.

**Current confirmed build state, in brief:**
- Single reckoner route (`reckoner_single`, `HMRC_S3`) built and verified.
- Married and widowed reckoner routes — i.e. the Qa/Qb, Fork 1/Fork 2 marital-status design described in Annex 3B — **not yet built.**
- IHT405 property sections (type-2 Table-with-routing) — **not yet built** (D18). Planning scripts (`agent*.py`, `load_iht405_data.py`) exist untracked in the project root; `load_iht405_data.py` has a known question-ID conflict with existing `HMRC_1`–`5` that must be resolved before it can run.
- `dept_defra`/`dept_dwp` removed entirely; HMRC is the only live department app.
- META mechanism fully removed.

**Important nuance for the new session:** the papers describe the *target* design. The Build docs describe what's *actually running*. These are not yet the same thing — most conspicuously, none of Annex 3B's marital-status/ownership routing design is built yet. Treat the papers as the spec to build toward, not as a description of current behaviour.

## 3. Backlog

`260714_Backlog.md` is the organic, working task list (NOW/SOON/LATER/TIDY tiers plus a completed-session record) — not a systematic reconciliation of papers-vs-build. It happens to contain some of that gap (D18 is the clearest example) but nothing has ever walked through Papers 1–3/Annex 3B item by item and logged each undesigned-vs-unbuilt gap as a tracked Backlog item.

**A good next task, not yet done:** a proper "design vs build" pass — reading Annex 3B against the live code (via Claude Code, since it needs to check against the actual repo, not just the Build docs' prose) and adding the resulting gaps to Backlog as real, prioritised entries. This has been discussed but not started.

## 4. Repo state

As of the end of this session: working tree clean, fully pushed to `origin/main` (commits `9d76840` and `f123b19` both landed). No untracked or stray files remaining unaccounted for.

## 5. Suggested first questions for a new session

- "Let's do the design-vs-build gap analysis and add it to Backlog" — the natural next step per section 3 above.
- "Let's start building D18 (IHT405 property sections)" — resolve the `load_iht405_data.py` ID conflict first.
- "Let's build the married/widowed reckoner routes" — i.e. start implementing Annex 3B's Qa/Qb/Fork design for real.
