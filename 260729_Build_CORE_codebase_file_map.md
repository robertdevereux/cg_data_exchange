# cg_data_exchange — "Core Core" Map
Date: 15 August 2026 (updated from 29 July 2026)
Scope: `core` app's data model + execution engine + platform interface only.
**Deliberately excludes** `views_admin_tools.py`, `urls_tools.py`, `admin.py`
(admin tooling) and `management/commands/load_test_data.py` — separate
problem, separate session.
Source: live codebase read directly 15 August 2026. Line counts from `wc -l`
against current files; cross-checked against live DB. Reflects compound-condition
routing engine (Phases 1–5, 3 August 2026) and the alternate_condition_id
external-fetch fix (15 August 2026).

---

## 1. The shape of it, in one paragraph

`models.py` defines everything. Dept apps talk to core **only** through
`interfaces.py` — mainly `call_core`. Core's own request/response flow for
answering questions lives in `views_layer2.py` (the execution engine
proper). `views_layer1.py` + `nav_reference.py` sit between `call_core` and
`views_layer2.py`, handling "which of several permitted things is the user
looking at" navigation. `permissions.py` is consulted by nearly everything.
`session.py` is the shared state substrate everything else reads/writes
through. `views_gate.py` is the acting-for identity gate.

---

## 2. Data model — `models.py` (871 lines)

Already well documented in Core Platform Reference §3. Three groups:
- **Configuration:** `Regime`, `Department`, `Schedule`, `Section`,
  `Question`, `QuestionSet`, `QuestionSetMember`, `SectionMember`, `Routing`
- **Runtime:** `Case`, `Answer`, `AnswerHistory`, `AnswerTable`,
  `AnswerTableHistory`, `SectionStatus`, `ScheduleStatus`
- **Access control:** `Permission`, `User`

No functions of note beyond `__str__`/`clean`/`get_regime` — this file is
in good shape; not a concern.

---

## 3. Platform interface — `interfaces.py` (462 lines)
*The documented contract dept apps call. Depts never touch models directly.*

| Function | Role |
|---|---|
| `create_case` / `get_cases` / `get_or_create_case` | Case lifecycle (`get_or_create_case` deprecated) |
| `bootstrap_section_statuses` | Seed `SectionStatus` rows for a set of sections |
| `reset_section_progress` | Delete all `SectionStatus` rows for user+regime (new, July 2026) |
| `promote_case_to_verified` | Atomic re-key of Answer+SectionStatus, update case.user+reference, create Permission (new, July 2026) |
| `call_core` (+ `_build_permitted_lists`) | **The** unified entry point — routes to a single section, a single schedule, or `regime_top_level` for a mixed list; always intersects with `get_permitted_sections` |
| `call_regime` | Thin wrapper around `call_core`; still present and callable |
| `get_answers` / `get_asked_answers_for_section` / `format_answer_for_display` / `format_date` | Answer read/display helpers |

**Note:** `call_schedules` and `call_sections` have been removed. `call_regime` remains as a thin convenience wrapper.

---

## 4. Execution engine — `views_layer2.py` (2,476 lines)
*Three distinct journeys bundled into one file, sharing a few helpers.*

**Shared / routing:**
`_matches`, `_evaluate_routing`, `_build_crumbs`, `_get_or_create_case`

`_resolve_routing_answer` — **DEAD CODE** (Phase 5, 3 August 2026). Still
present in the file (marked `# noqa: dead-code`) pending removal of the four
old Routing model fields it depended on. Not called anywhere in active code.

**Section metadata cache (Phase 1–2, 3 August 2026):**
`_section_cache_get(request, section_id)`,
`_section_cache_set(request, section_id, data)` — helpers for the
`request.session['_section_cache']` namespace (see §4 session keys).

`load_cache_for_fixed_table_section(request, section)` — fetches and caches
column metadata (from `display_question_ids`) for a type-1 section. Returns
a dict including `column_dicts`.

`load_cache_for_routed_section(request, section)` — fetches and caches
routing/question/set metadata (via `_build_section_tables`) for a type-2
section. Returns the full `_build_section_tables` dict plus
`external_condition_qids` (questions from other sections referenced via
`condition_question_id` or `alternate_condition_id` that need fetching
without a section= filter).

`_fetch_external_answers(case, ext_qids)` — fetches `Answer` rows for
`external_condition_qids`; returns `{question_id: answer}` dict.

**Standard section journey (section_type=0):**
`section_start` → `section_question` / `_process_answer` →
`section_review` / `_commit_section_answers` → `section_confirm` →
`section_done`; plus `section_set_page` / `_process_set_answer` for
QuestionSet pages.

**Flat table journey (section_type=1):**
`section_table`, `section_table_add`

**Routed table journey (section_type=2):**
`section_table_routed_add` / `_change` / `_question` / `_row_detail` /
`_delete`, `section_confirm_table`, plus row-session helpers
`_table_row_ns_get/set/clear` and `_commit_table_row`,
`_build_section_tables`

**Observation:** this is really three sub-systems (standard / flat table /
routed table) living in one file, now **2,476 lines** (up from 2,366 after
the compound-condition routing engine landed 3 August 2026 — Phases 1–5 plus
the 15 August external-fetch fix added the cache helpers, _matches,
_evaluate_routing rewrite, and the new test suite rows). The split into e.g.
`views_layer2_standard.py` / `views_layer2_table.py` is now more urgent than
when first noted — worth scheduling as a dedicated TIDY session rather than a
backlog line.

---

## 5. Navigation views — `views_layer1.py` (~367) + `nav_reference.py` (76)

| File | Functions |
|---|---|
| `views_layer1.py` | `regime_sections`, `regime_schedules`, `regime_schedule_sections`, `regime_top_level`, `_rollup_status` |
| `nav_reference.py` | `resolve_layer1_entry_url`, `resolve_user` |

**Resolved (July 2026):** `select_schedule` and `select_section` were removed from `nav_reference.py` as duplicate dead code (their logic is covered by `views_layer1.py`). `_resolve_user` was renamed `resolve_user` (now a public API).

---

## 6. Access control — `permissions.py` (132 lines)

`get_permitted_sections`, `get_actor_accessible_regimes`,
`get_permitted_regimes`. Consulted by `call_core`'s permission
intersection and elsewhere. Small, focused, no concerns.

---

## 7. Identity / acting-for gate — `views_gate.py` (126 lines)

`choose_user_for_regime`, `select_identity`, `select_self`,
`_build_select_identity_url`. The shared gate is used by all active dept
apps. (`dept_dwp` had its own older picker, but `dept_dwp` has been
removed — July 2026.)

---

## 8. Session — `session.py` (82 lines)

`get_session` / `update_session` (the PSS namespace), `get_acting_for_name`,
`clear_working_session`, `clear_section_session`. Small, focused, no
concerns — but everything above reads/writes through this, so it's worth
keeping deliberately small as the system grows.

---

## 9. ~~Meta processors — `meta_processors.py`~~

**Removed (July 2026).** `meta_processors.py` was a self-configuration
side-channel that allowed the platform to configure itself (create Regimes,
Sections, Questions, etc.) by answering specially-named `META_` sections
through the ordinary execution engine. It was superseded by the admin
wizards in `views_admin_tools.py` and has been deleted. The `META_*`
dispatch hook in `section_confirm`/`section_confirm_table` has been removed
with it.

---

## 10. Tests — `tests.py` (3,834 lines)

A single file containing all core and HMRC IHT tests. Key classes relevant
to the routing engine:
- `TestRoutedSectionCache` — type-2 cache query-count test (Phase 1
  analogue), external `condition_question_id` fix (EXT_TEST_S1 fixture),
  and external `alternate_condition_id` fix (EXT_ALT_S1 fixture, 15 August
  2026)
- `TestCompoundConditionRouting` — 12 unit tests for the Phase 5 two-slot
  `_evaluate_routing` logic; no HTTP client, no session

Current count: **224 tests** (1 skipped — QuestionSet consistency checker,
deferred pending QuestionSet usage growth). 

---

## 11. App bootstrap / misc

- `apps.py` — `_auto_grant_regimes` signal: auto-grants every new `User`
  self-permission on all non-PLATFORM regimes on creation.
- `views.py` — `root_landing` only.
- `urls.py` — routing table, no functions.
- `templatetags/markdown_extras.py` — `render_markdown` only.

All small and single-purpose. No concerns.

---

## 12. Audit findings — status

1. ~~**`call_regime`/`call_schedules`/`call_sections`** — confirm live
   callers exist; if none, delete.~~ **Resolved (July 2026):** `call_schedules`
   and `call_sections` deleted. `call_regime` retained as a thin convenience
   wrapper that is still used.
2. **`views_layer2.py`** — one file, three journeys; split candidate
   (TIDY, not urgent). Still open — see Backlog.
3. ~~**`select_schedule`/`select_section` vs `regime_schedules`/
   `regime_sections`** — possible duplicate-concept pair.~~ **Resolved (July
   2026):** `select_schedule` and `select_section` were the duplicates;
   both removed. `regime_schedules`/`regime_sections` are the correct Layer 1
   views and remain.
4. ~~**`meta_processors.py`** — confirm live/dead status.~~ **Resolved (July
   2026):** confirmed dead — superseded by admin wizards; file deleted.
5. **Dead Routing model fields and `_resolve_routing_answer`** — Open.
   `condition_question_id`, `answer_value`, `comparator`, `threshold_value`
   on `Routing`, and `_resolve_routing_answer` in `views_layer2.py`, are
   dead as of Phase 5 (3 August 2026). Deliberately kept pending admin UX
   update (new compound-condition field surfaces) and a final grep confirming
   no remaining references. Requires a further migration to drop the columns.
   See Backlog TIDY.
6. **`_section_cache` session key** — raw `request.session`, not PSS. Added
   by Phase 1/2 (3 August 2026). Cleared between section visits via
   `_section_cache = {}` (in tests) or a new request session. Not yet listed
   in Core Platform Reference §5's session-key table — update pending.
