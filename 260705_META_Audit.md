# META Mechanism Audit — 2026-07-05

## What is META?

META is a self-hosting wizard — a Django admin tool that lets a platform operator *create a new regime by answering questions inside the platform itself*. It uses a special regime (`regime_id='META'`) with 7 sections and 27 `M_N`-prefixed questions. On completion, `meta_processors.py` reads those answers and writes new `Regime`, `Schedule`, `Section`, `Question`, `QuestionSet`, `QuestionSetMember`, and `Routing` rows into the database.

META has been superseded by the admin tools UI (`tools_section_create`, `tools_routing_insert`, etc.) and is no longer used.

---

## Audit questions

1. Is META genuinely dead — no active usage, no tests?
2. What are all the files/lines that reference META?
3. For each reference: is it (a) part of META itself, (b) an external reference that would break if META were removed, or (c) incidental?
4. Is it safe to remove?

---

## Complete inventory

### Core mechanism files

| Component | File | Lines | Category | Notes |
|-----------|------|-------|----------|-------|
| META processor library | `core/meta_processors.py` | entire file | **(a) META** | `dispatch_meta_processor` + 7 `process_meta_*` functions. Writes to Regime/Schedule/Section/Question/QuestionSet/QuestionSetMember/Routing on section completion. |
| `dispatch_meta_processor` hook — post-confirm | `core/views_layer2.py` | ~1073–1076 | **(a) META** | `if section.section_id.startswith('META_'):` guard, calls `dispatch_meta_processor`. Executes during section confirm. |
| `dispatch_meta_processor` hook — post-routing | `core/views_layer2.py` | ~1744–1747 | **(a) META** | Same guard, called in routing path. |
| `tools_create` view | `core/views_admin_tools.py` | ~3126–3257 | **(a) META** | Regime creation wizard entry point. Requires META regime to exist; reads `M_21` for target regime ID. |
| `tools_create_save` view | `core/views_admin_tools.py` | ~3261–3296 | **(a) META** | POST only. Marks META case SUBMITTED; deletes Answer/AnswerTable/SectionStatus. |
| `tools_create_abandon` view | `core/views_admin_tools.py` | ~3300–3329 | **(a) META** | Lapses META cases; deletes answers; redirects to `/tools/create/`. |
| 3 URL patterns | `core/urls_tools.py` | ~215–225 | **(a) META** | `tools/create/`, `tools/create/save/`, `tools/create/abandon/`. |
| `tools_create.html` template | `core/templates/core/tools_create.html` | entire file | **(a) META** | GDS task-list rendering of META sections. Only outbound link is to `/tools/create/abandon/` (self-referential). No other template links to this one. |

### Test data

| Component | File | Lines | Category | Notes |
|-----------|------|-------|----------|-------|
| META regime creation | `core/management/commands/load_test_data.py` | ~605–612 | **(a) META** | Creates `regime_id='META'`. |
| 27 `M_N` question creation | `core/management/commands/load_test_data.py` | ~413–508 | **(a) META** | `M_1`–`M_27`, all with `is_platform=True`. Safe to remove — no test depends on them. |
| 7 META section creation | `core/management/commands/load_test_data.py` | ~675–753 | **(a) META** | `META_ADD_REGIME`, `META_ADD_SCHEDULES`, `META_ADD_SECTIONS`, `META_ADD_QUESTIONS`, `META_ADD_SETS`, `META_ADD_SETMEMBERS`, `META_ADD_ROUTING`. |
| META routing | `core/management/commands/load_test_data.py` | ~838–846 | **(a) META** | Routing for `META_ADD_REGIME` section. |

### Things that look like META references but are NOT

| Item | File | Category | Notes |
|------|------|----------|-------|
| `is_platform` field definition | `core/models.py` | **(b) NOT META — keep** | Active field used by `PlatformRouter` to route `P_N`/`O_N` questions to the `'platform'` DB alias. M_N questions happen to use it too, but the field exists for the platform question routing feature. Removing this field would break `PlatformRouter`. |
| `is_platform` schema migration | `core/migrations/0006_*` | **(b) NOT META — keep** | Normal schema migration for the above field. |

### Incidental references (docs/backlog)

| Item | File | Category | Notes |
|------|------|----------|-------|
| `M_1`–`M_27` in question ID table | `260705_Core_Platform_Reference.md` | **(c) incidental** | Documentation only. Remove the M_N rows from the table when META is removed. |
| META flagged for removal | `260705_Backlog.md` (and 3 older date-stamped versions) | **(c) incidental** | Backlog items — these *expect* META to be removed. No action needed beyond deleting META. |

---

## Is META genuinely dead?

Yes.

- **No tests** exercise `tools_create`, `tools_create_save`, `tools_create_abandon`, or `dispatch_meta_processor`. The test suite (193 tests) has zero coverage of these paths.
- **No navigation** reaches `/tools/create/` from anywhere in the templates. The only internal link to the abandon URL is inside `tools_create.html` itself.
- **No dept code** calls `dispatch_meta_processor` or imports from `meta_processors.py` outside `views_layer2.py`.
- The backlog (`260705_Backlog.md`) explicitly lists META removal as a pending task.

---

## Recommendation

**Safe to remove in full**, with one named exception.

### Remove (all category (a)):
1. `core/meta_processors.py` — delete entire file
2. `core/views_layer2.py` — delete the two `dispatch_meta_processor` hook blocks (~1073–1076 and ~1744–1747) and the `from core.meta_processors import dispatch_meta_processor` import
3. `core/views_admin_tools.py` — delete `tools_create`, `tools_create_save`, `tools_create_abandon` views (~3126–3329)
4. `core/urls_tools.py` — delete the 3 `tools/create/` URL patterns (~215–225)
5. `core/templates/core/tools_create.html` — delete file
6. `core/management/commands/load_test_data.py` — delete META regime, 27 M_N questions, 7 META sections, and META routing blocks

### Do NOT remove (category (b)):
- `is_platform` field on `Question` and its migration — this is an active feature used by `PlatformRouter`.

### Tidy up after removal (category (c)):
- Remove the `M_1`–`M_27` rows from the question ID reference table in `260705_Core_Platform_Reference.md`.
- The backlog items referencing META removal can be marked done.

### Risk: none identified
No external code imports from `meta_processors.py`. No tests will break. No nav template links to the removed URLs. The only removal risk would be if `is_platform=True` were used as a proxy for "is a META question" somewhere — it is not; `PlatformRouter` uses it for all `P_N`/`O_N` questions independently of META.
