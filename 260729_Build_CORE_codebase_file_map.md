# cg_data_exchange — "Core Core" Map
Date: 29 July 2026
Scope: `core` app's data model + execution engine + platform interface only.
**Deliberately excludes** `views_admin_tools.py`, `urls_tools.py`, `admin.py`
(admin tooling) and `management/commands/load_test_data.py` — separate
problem, separate session.
Source: `file_dump.txt` regenerated 29 July 2026, cross-checked against
Core Platform Reference and HMRC IHT Reference. All "possible dead code"
flags from the previous version have been resolved (see §11).

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

## 2. Data model — `models.py` (823 lines)

Already well documented in Core Platform Reference §3. Three groups:
- **Configuration:** `Regime`, `Department`, `Schedule`, `Section`,
  `Question`, `QuestionSet`, `QuestionSetMember`, `SectionMember`, `Routing`
- **Runtime:** `Case`, `Answer`, `AnswerHistory`, `AnswerTable`,
  `AnswerTableHistory`, `SectionStatus`, `ScheduleStatus`
- **Access control:** `Permission`, `User`

No functions of note beyond `__str__`/`clean`/`get_regime` — this file is
in good shape; not a concern.

---

## 3. Platform interface — `interfaces.py` (453 lines)
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

## 4. Execution engine — `views_layer2.py` (2,077 lines)
*Three distinct journeys bundled into one file, sharing a few helpers.*

**Shared / routing:**
`_resolve_routing_answer`, `_evaluate_routing`, `_build_crumbs`,
`_get_or_create_case`

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
routed table) living in one file, now **2,366 lines** (up from 2,077 after
D18–D20 landed on 31 July 2026). D18 (row view/amend), D19 (numeric
formatting), and D20 (radio_inline in routed table) all extended the
routed-table journey. The split into e.g. `views_layer2_standard.py` /
`views_layer2_table.py` is now more urgent than when first noted — worth
scheduling as a dedicated TIDY session rather than a backlog line.

---

## 5. Navigation views — `views_layer1.py` (367) + `nav_reference.py` (249)

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

## 10. App bootstrap / misc

- `apps.py` — `_auto_grant_regimes` signal: auto-grants every new `User`
  self-permission on all non-PLATFORM regimes on creation.
- `views.py` — `root_landing` only.
- `urls.py` — routing table, no functions.
- `templatetags/markdown_extras.py` — `render_markdown` only.

All small and single-purpose. No concerns.

---

## 11. Audit findings — status

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
