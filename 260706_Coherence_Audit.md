# Coherence Audit — core/dept boundary and identity scoping
**Date:** 2026-07-06  
**Scope:** Read-only audit. No code was changed during this session.

---

## Item 1: `request.user` vs `case.user`/actor scoping

### Background

The platform distinguishes between:
- **`request.user`** — the logged-in executor (actor, e.g. alice)
- **`case.user`** — the subject (e.g. the deceased after IHT promotion)

All Answer, AnswerHistory, AnswerTable, and SectionStatus rows must be keyed to `case.user`. The last session fixed six such sites in `_commit_section_answers`. The table-journey code paths were not in scope for that fix.

### Confirmed intentional exception

`core/views_layer2.py` line 457:
```python
Answer.objects.filter(user=request.user, question_id=question_id)
```
Cross-case pre-population in `section_question`. The actor's prior answers across other cases are scanned to offer a suggestion banner. Actor-scoped by design. Confirmed as the sole intentional `request.user` data-query hit.

### Unfixed bugs — table-journey code paths

All of these key data rows to `request.user` (the executor) instead of `case.user` (the subject). For non-IHT journeys they are harmless (actor == subject). For verified IHT cases they silently write/read against the wrong user and will produce empty reads or duplicate writes.

| Line | Code | Problem |
|------|------|---------|
| 282 | `AnswerTable.objects.get_or_create(user=request.user, case=case, ...)` in `_commit_table_row` | AnswerTable row keyed to executor, not subject |
| 297 | `SectionStatus.objects.update_or_create(user=request.user, ...)` in `_commit_table_row` | Completion status keyed to executor |
| 391 | `SectionStatus.objects.get_or_create(user=request.user, ...)` in `section_start` | "In progress" status keyed to executor |
| 400 | `update_session(request, {'user_id': request.user.pk, ...})` in `section_start` | Overwrites `user_id` in session with actor PK on every section entry, undoing the correct `case.user` PK set by `call_core` |
| 894 | `AnswerHistory.objects.filter(user=request.user, ...)` in `section_review` | History query uses executor; history was written with `case.user`, so review page always appears empty for verified IHT cases |
| 1098–1101 | `_get_or_create_case(request.user, regime)` + `update_session({'user_id': request.user.pk, 'actor_id': request.user.pk, ...})` in `section_table` bootstrap | Fallback bootstrap clobbers session `user_id` to actor |
| 1136 | `AnswerTable.objects.get(user=request.user, case=case, ...)` in `section_table` | Reads table rows for executor; finds nothing for a verified IHT case |
| 1719 | `AnswerTable.objects.get(user=request.user, ...)` in `section_confirm_table` | Reads table rows for executor |
| 1723 | `AnswerTableHistory.objects.create(user=request.user, ...)` in `section_confirm_table` | Writes history against executor |
| 1735 | `SectionStatus.objects.update_or_create(user=request.user, ...)` in `section_confirm_table` | Marks section complete against executor |

### In dept_* apps

Every `request.user` hit in `dept_hmrc/`, `dept_demo/`, `dept_defra/`, `dept_dwp/` is of the form `actor = request.user` — explicit assignment to the `actor` variable at the top of a view, before `user` is resolved separately. None are data-query keys. All are correct.

### Verdict

**High priority.** The non-table path (`_commit_section_answers`) was fixed in the previous session. The table-section path (`_commit_table_row`, `section_table`, `section_confirm_table`, `section_review`) is entirely unfixed. Any IHT section of type 1 or 2 (table sections, e.g. IHT405) will silently write status and history under the executor's identity and fail to read it back under the deceased's. The `section_start` session overwrite at line 400 is particularly treacherous: it fires on every section entry and undoes `call_core`'s correct `user_id` write.

**Recommendation:** Fix all ten lines above in a single table-journey pass, mirroring the pattern used in `_commit_section_answers`. The `section_start` session overwrite (line 400) should be removed or guarded: only write `user_id` when no `case_id` is already in session.

---

## Item 2: Duplicate-concept scan — orchestrate.py / matching.py / reckoner.py

### Known pair (documented tech debt)

**`_entry_start` (orchestrate.py ~295–310) vs `iht_start_new_estate` (~248–288)**  
Both create a draft case and call `call_core` with S1. `_entry_start` first renders `iht_screen_unverified` (the pre-verified home with an explicit "Create" button); `iht_start_new_estate` enters S1 directly. Documented in `260705_HMRC_IHT.md` §2 as known tech debt.

### New finding: `_get_verified_case` is dead code

`orchestrate.py` lines 774–779:
```python
def _get_verified_case(user, regime):
    return get_cases(user, regime).filter(reference__isnull=False).first()
```
This function is **never called**. The live code (lines 139–143) resolves the verified case inline via `Case.objects.filter(case_id=case_id, regime=regime).first()` and checks `case.reference`. `_get_verified_case` is a stale helper from an earlier design, now dead code.

### New finding: `_enter_core` helper bypassed in reckoner.py

`orchestrate.py` defines a canonical helper at lines 806–809:
```python
def _enter_core(request):
    request.session['iht_in_core'] = True
    request.session.modified = True
```
`reckoner.py` line 233 sets the flag directly:
```python
request.session['iht_in_core'] = True
```
`reckoner.py` does not import `_enter_core`. If the mechanism changes (e.g. an additional flag), `reckoner.py` would silently be missed. Genuine duplication.

### Structural duplication: actor/user bootstrap

`orchestrate.py` `_setup()` (lines 744–764) canonically handles:
```python
actor = request.user
update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
pss  = get_session(request)
user = _resolve_user(pss, actor)
```
`reckoner.py` `iht_reckoner_compute` (lines 166–173) repeats this inline rather than calling `_setup`. `_setup` also resolves `regime` and `crumbs`, so they are not identical, but the actor/user resolution pattern is repeated. Low-severity structural duplication.

### Summary

| Pair | Files / Lines | Verdict |
|------|--------------|---------|
| `_entry_start` / `iht_start_new_estate` | orchestrate.py 295–310 / 248–288 | Known tech debt, documented |
| `_get_verified_case` / inline case lookup | orchestrate.py 774–779 / 139–143 | Dead code — `_get_verified_case` never called |
| `_enter_core` / raw `iht_in_core` set | orchestrate.py 806–809 / reckoner.py 233 | Real duplication; reckoner bypasses the helper |
| Actor/user bootstrap in `_setup` / `iht_reckoner_compute` | orchestrate.py 744–764 / reckoner.py 166–173 | Structural duplication; low severity |

**Recommendation:** Remove `_get_verified_case` (dead code). Have `reckoner.py` import and call `_enter_core`. Consider extracting the actor/user bootstrap into a minimal shared helper if `reckoner.py` continues to grow.

---

## Item 3: Doc-vs-code reconciliation — HMRC IHT ENTRY/EXIT table

### Overall verdict

The ENTRY/EXIT dispatch table in `260705_HMRC_IHT.md` §3 matches `iht_orchestrate` exactly. Every branch listed in the doc is present in the code; no code branch is missing from the doc.

### Minor doc omissions

1. **`_entry_start` renders, not just redirects.** The ENTRY/EXIT table says `start → _entry_start()`. It does not note that `_entry_start` renders `iht_screen_unverified` rather than immediately redirecting. A reader of the table alone would assume ENTRY always transitions to core. Covered in §4 but not flagged inline in the table.

2. **`_entry_triage_assets` early-exit not in table.** If `_get_built_schedule_items` returns empty, `_entry_triage_assets` returns `None` and the caller falls through to `_render_home`. The ENTRY/EXIT table shows `hmrc_s4/s5/s6 → _entry_triage_assets(section_id)` with no note about this fallback path. Covered loosely in §8a.

3. **`iht_start_new_estate` not in the ENTRY/EXIT table.** It is reached via the gate's "Begin a new estate" URL, not via the dispatcher. Documented separately in §4 but absent from the table, which a reader could take as the complete map of IHT entry points.

### Live bug: reckoner.py HMRC_14 constants are stale

`reckoner.py` lines 42–44 define:
```python
RECKONER_SECTION = {
    "Married, with their spouse surviving them": ...,
    "Themselves a widow or widower...":          ...,
    "Neither of the above...":                   ...,
}
```
HMRC_14 was restructured from a three-way choice to a `Yes`/`No` field. `handle_reckoner` reads `ans['HMRC_14']` and looks it up in `RECKONER_SECTION`. The current field returns `'Yes'` or `'No'`, which matches nothing, so `section_id` is always `None` and the reckoner journey falls through unconditionally regardless of the marital status answer. **The reckoner is non-functional.** `260705_HMRC_IHT.md` §6 notes this under Caution ("not verified") but the code is objectively broken. This is not a doc discrepancy — it is a live bug that the doc has already flagged.

**Recommendation:** Fix `reckoner.py` constants to match the current Yes/No field shape. The doc caution note in §6 should be updated once fixed.

---

## Item 4: `call_regime` / `call_schedules` / `call_sections` back-compat wrappers

**Defined in:** `core/interfaces.py` lines ~234–290.

### Caller audit

| Wrapper | Callers found |
|---------|--------------|
| `call_regime` | `dept_dwp/views_regime_generic.py` line 35; `dept_defra/views.py` line 59; `dept_hmrc/views/hmrc_home.py` line 75 |
| `call_schedules` | **None** |
| `call_sections` | **None** |

`call_regime` has three active callers and is a live public interface. `call_schedules` and `call_sections` have zero callers anywhere in the codebase. The IHT orchestrator uses `call_core` directly with inline `items` lists.

**Verdict:** `call_regime` — keep. `call_schedules` and `call_sections` — dead code, safe to remove.

---

## Item 5: `select_schedule` / `select_section` (nav_reference.py) vs `regime_schedules` / `regime_sections` (views_layer1.py)

**Not genuine duplication.** These are two distinct things that share surface-level names.

### What each pair actually does

| Dimension | `select_schedule` / `select_section` (nav_reference.py) | `regime_schedules` / `regime_sections` (views_layer1.py) |
|-----------|----------------------------------------------------------|-----------------------------------------------------------|
| Purpose | Reference implementation; pre-dates Layer 1 | Live platform views, URL-routed |
| Session writes | None | Write `return_url`, `schedule_list_url`, `regime_home_url`, `breadcrumbs` |
| `back_url` | Hardcoded string (`/select-regime/`) | Read from session (`regime_home_url`) |
| Schedule URL | Hardcoded f-string | `reverse('core:regime_schedule_sections', ...)` |
| Breadcrumbs | Not passed | Passed + written back to session |
| `acting_for` | Not passed | Passed |
| `title` source | `regime.regime_name` only | `pss.get('section_list_title') or regime.regime_name` |
| Callers | None (unreachable as live views) | Reached via `call_core` → `/regime/<id>/schedules/` or `/regime/<id>/sections/` |

### Real finding

`select_schedule` and `select_section` in `nav_reference.py` are **unreachable as live views** in the current URL configuration. No URL pattern routes to them. `call_schedules` and `call_sections` (the wrappers that would have routed to them) have zero callers (see Item 4). The `nav_reference.py` module docstring describes these as "reference implementations for departments to copy/adapt" — but they are broken as copies too (hardcoded back URLs, no session writes mean `section_done` has no `return_url` to read).

**Verdict:** Not duplication, but `select_schedule` and `select_section` are dead reference code. They should either be clearly marked as documentation-only (moved to a non-importable doc file) or removed. Currently they create a false impression of an alternative navigation path.

---

## Item 6: `call_core`'s implicit session preconditions

### Complete list of implicit preconditions

Every session key a dept must pre-set before calling a shared core function, where the core function reads it implicitly rather than receiving it as a parameter:

| Session key | Must be written by | Read by | Notes |
|-------------|-------------------|---------|-------|
| `regime_home_url` | Dept regime home view (or `_setup` in IHT) | `call_core`, `regime_sections`, `regime_schedules`, `regime_top_level`, `regime_schedule_sections`, `resolve_completion_url` | Falls back to `request.path` in `call_core` if absent; silently wrong elsewhere |
| `user_id` | `call_core` (writes it); dept home must ensure PSS is initialised first | `_resolve_user` (called throughout core and dept views), `iht_orchestrate` | `call_core` writes `user_id = user.pk`; this is the correct write site, but if a dept calls any core view without going through `call_core` first, `user_id` is absent |
| `actor_id` | `call_core` | Used in `_commit_section_answers` to set `Answer.actor` | Same dependency as `user_id` |
| `case_id` | `call_core` (writes on case creation/lookup) | `iht_orchestrate` reads it to resolve `case`; `_commit_section_answers` reads it | IHT relies on this being set correctly; re-entry without `case_id` falls back to gate |
| `top_level_items` | `call_core` (via session) | `regime_top_level` | If `call_core` is not the entry point, `top_level_items` is empty and the page renders nothing |
| `breadcrumbs` | Dept regime home view | All Layer 1 views, section views | Must be seeded correctly at the regime home; Layer 1 views pass it through |
| `return_url` | Layer 1 list views (regime_sections, regime_schedule_sections, regime_top_level) | `resolve_completion_url` | Section done redirects to this; if dept bypasses Layer 1, section_done has no return target |
| `iht_current_action` | IHT: `_entry_*` functions set before calling `call_core`; `iht_start_new_estate` sets directly | `iht_orchestrate` — EXIT dispatch | IHT-specific; not required by core |
| `iht_in_core` | `_enter_core()` in orchestrate; also raw in reckoner.py (Item 2 finding) | `iht_orchestrate` — `returning_from_core` check | IHT-specific |
| `post_confirm_redirect` | Dept views may set (one-shot override) | `resolve_completion_url` (popped on first use) | Optional dept override; not required |
| `section_list_title` | `call_core` or dept | `regime_sections`, `regime_top_level` | Optional; falls back to `regime.regime_name` |
| `permitted_section_ids` | `call_core` (writes from `items`) | `regime_sections`, `regime_top_level` | If absent, falls back to full `get_permitted_sections` query |

### The `regime_home_url` dual-write finding

In `dept_hmrc/views/iht/orchestrate.py`, `iht_start_new_estate` contains:
```python
request.session['regime_home_url'] = reverse('dept_hmrc:iht_home')
```
This is a raw `request.session[...]` write rather than via `update_session()`. Every other dept writes `regime_home_url` via `update_session()`. This is the **only** raw session write for this key in the entire codebase. The practical difference: `update_session` may apply additional logic (e.g. logging, key validation); the raw write bypasses it. Currently no such extra logic exists in `update_session`, so the effect is identical — but the inconsistency is a trap for future `update_session` enhancements.

**Verdict:** The implicit precondition pattern is a structural issue. `regime_home_url` is the most important: it flows through the entire completion routing chain and its absence causes silent wrong redirects, not an error. It is a candidate for an explicit `call_core(..., regime_home_url=...)` parameter, which would make the dependency visible and catch missing callsites at invocation time rather than at runtime. The raw session write in `iht_start_new_estate` is a low-risk inconsistency but should be normalised to `update_session`.

---

## Item 7: Breadcrumb gap in Layer 1 views

### Current state

| View | Appends own label to breadcrumb trail? |
|------|---------------------------------------|
| `regime_sections` (views_layer1.py ~47–112) | **No** — reads `pss.get('breadcrumbs', [])`, passes through unchanged |
| `regime_schedules` (~118–187) | **No** — same; passes through unchanged |
| `regime_schedule_sections` (~193–265) | **Yes** — builds extended crumbs by truncating to the regime home crumb, then appending `{'label': schedule.schedule_name, 'url': section_list_url}` |
| `regime_top_level` (~271–365) | **No** — reads and passes through unchanged |

`regime_schedule_sections` is the only Layer 1 view that adds its own page to the trail. The other three rely entirely on the dept regime home page having pre-seeded breadcrumbs correctly.

### Impact

The gap is presentational only. Citizens navigating through `regime_sections`, `regime_schedules`, or `regime_top_level` do not see a breadcrumb for the page they are currently on — the breadcrumb trail terminates at the regime home. This is a UX inconsistency, not a functional bug (unlike the `return_url` gap that was already fixed).

### Relationship to the `return_url` fix

The `return_url` bug in `regime_top_level` was a functional navigation bug (section_done had nowhere to return). The breadcrumb gap is a presentation issue. They are **separate concerns** despite touching the same views. The breadcrumb fix would be natural to bundle with any future Layer 1 pass, but it is not urgent and not broken in the functional sense.

**Verdict:** Low priority. Confirm breadcrumb gap exists as documented; worth fixing in the same batch as any future Layer 1 improvements, but should not be bundled with the urgent `request.user` fix (Item 1) or reckoner fix (Item 3).

---

## Item 8: `orchestrate.py` direct core-internals access

### All core imports in `orchestrate.py` (lines 39–50)

```python
from core.interfaces import (
    call_core, create_case, format_answer_for_display,
    get_answers, get_asked_answers_for_section, get_cases,
)
from core.models import Case, Permission, Regime, Routing, Section, SectionStatus
from core.models import QuestionSetMember
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session
from core.views_gate import choose_user_for_regime
```

### Classification

| Symbol | Usage | Classification |
|--------|-------|---------------|
| `call_core`, `create_case`, `format_answer_for_display`, `get_answers`, `get_asked_answers_for_section`, `get_cases` | All via `core.interfaces` | **(a) Reading content / platform API — fine** |
| `Case` (read) | `iht_orchestrate` lines 139–143: fetch case by session `case_id` | **(a) Reading content — fine** |
| `Case` (delete draft) | `_exit_start`: deletes draft case if matching fails | **(c) Mutating core state** — see below |
| `Regime` | `_setup` line 752: `get_object_or_404(Regime, ...)` | **(a) Reading content — fine** |
| `Routing` | `_get_triage_question_ids` lines 641–659: reads Routing rows to build triage question list | **(b) Reading core config — freelance but benign** |
| `Section` | `_get_triage_sets`, `_render_home`, `_build_action_list` | **(b) Reading core config — freelance but benign** |
| `SectionStatus` (read) | `_get_statuses`: queries section completion for home screen | **(b) Reading core config — benign** |
| `SectionStatus` (delete) | `iht_start_new_estate`: `SectionStatus.objects.filter(user=user, regime=regime).delete()` | **(c) Mutating core state — high priority** |
| `Permission` (read) | `_get_verified_cases`: queries case-scoped permissions | **(b) Reading core config — benign** |
| `QuestionSetMember` | `_get_triage_question_ids`: reads question set membership | **(b) Reading core config — benign** |
| `_resolve_user` (private) | `_setup` line 762 | **(b) Private import — should be a public API** |
| `get_permitted_sections` | `_get_statuses`, `_build_action_list` | **(b) Reading core config — benign** |

### High-priority finding: `SectionStatus.objects.filter(...).delete()` in `iht_start_new_estate`

`orchestrate.py` lines 258–260:
```python
SectionStatus.objects.filter(user=user, regime=regime).delete()
new_case = create_case(user, regime)
```
A dept view directly deletes rows from core's `SectionStatus` table. This bypasses any platform-level logic (e.g. audit trail, cascade handling, future validation). Classification: **(c) mutating core's own runtime state — high priority.** This should be a platform function: `interfaces.reset_section_progress(user, regime)` or similar.

### High-priority finding: all four mutations in `_promote_case_to_verified` (matching.py)

```python
Answer.objects.filter(case=case, user=actor).update(user=deceased)         # re-key answers
SectionStatus.objects.filter(user=actor, regime=case.regime).update(user=deceased)  # re-key statuses
case.user = deceased; case.reference = ...; case.save()                     # mutate Case
Permission.objects.create(user=actor, case=case, ...)                       # create Permission
```
Every mutation in `_promote_case_to_verified` directly manipulates core models. These are correct by intent (the deceased-identity promotion is a well-understood business operation), but the entire function is a hotspot that a future refactoring should wrap as `interfaces.promote_case_to_verified(case, actor, deceased, reference)`. This would:
- Make the operation atomic from the dept's perspective
- Give core a single place to add audit logging, constraints, or cascade rules
- Allow `matching.py` to import only from `core.interfaces`

Classification: **(c) mutating core state — high priority.**

### `screen.py` and `utils.py`

`screen.py`: imports only `core.models.Section` (local import inside `iht_screen`) for a read query. Classification **(a)**. No mutations. Clean.

`utils.py`: imports only `get_answers` and `format_date` from `core.interfaces`. Classification **(a)**. No model imports. No mutations. Clean.

### `_resolve_user` private import

Both `orchestrate.py` (line 45) and `reckoner.py` (inside `iht_reckoner_compute`) import `core.nav_reference._resolve_user` — a private (underscore-prefixed) 6-line helper. This should be promoted to a public function in `core.interfaces` or `core.session`. Classification **(b) — freelance but benign; candidate for promotion.**

### Summary

| Finding | Priority |
|---------|----------|
| `SectionStatus.objects.filter(...).delete()` in `iht_start_new_estate` | **High — should be `interfaces.reset_section_progress`** |
| All four mutations in `_promote_case_to_verified` (matching.py) | **High — should be `interfaces.promote_case_to_verified`** |
| `Case` deletion in `_exit_start` | Medium — dept deleting a core model directly |
| `_resolve_user` private import | Low — should be a public API |
| All other usages | Benign reads; no action required |

---

## Cross-cutting summary

| Item | Severity | Type | Recommendation |
|------|----------|------|---------------|
| **1. Table-journey `request.user` bugs** | **High** | Silent data bug (live for IHT type-2 sections) | Fix all 10 lines in a single table-journey pass |
| **3. Reckoner HMRC_14 constants stale** | **High** | Live bug — reckoner always falls through | Fix RECKONER_SECTION constants to match Yes/No field |
| **8. `SectionStatus.delete` in `iht_start_new_estate`** | **High** | Boundary violation — direct core mutation | Wrap in `interfaces.reset_section_progress` |
| **8. All mutations in `matching.py`** | **High** | Boundary violation — direct core mutations | Wrap in `interfaces.promote_case_to_verified` |
| **2. `_get_verified_case` dead code** | Medium | Dead code | Remove |
| **2. `_enter_core` bypassed in reckoner.py** | Medium | Duplication | Import and call `_enter_core` from reckoner |
| **4. `call_schedules` / `call_sections` dead wrappers** | Medium | Dead code | Remove |
| **5. `select_schedule` / `select_section` unreachable** | Medium | Dead reference code | Remove or mark as non-callable documentation |
| **6. Raw `request.session` write in `iht_start_new_estate`** | Low | Inconsistency | Normalise to `update_session` |
| **6. `regime_home_url` implicit precondition** | Low | Structural | Candidate for explicit `call_core` parameter |
| **7. Breadcrumb gap in regime_sections / regime_top_level** | Low | Presentation only | Bundle with future Layer 1 improvements |
| **8. `_resolve_user` private import** | Low | Boundary minor | Promote to public API |
| **3. Minor doc omissions in ENTRY/EXIT table** | Low | Doc | Update inline notes in §3 |
