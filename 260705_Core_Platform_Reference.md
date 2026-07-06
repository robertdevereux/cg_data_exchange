# cg_data_exchange — Core Platform Reference
Date: 5 July 2026
Status: Stable reference — update only when the core app itself changes
Verified: Content checked against file_dump.txt and live session by Claude on 5 July 2026

---

## 1. What the core app provides

`core` is the platform app. It owns the data model, the execution engine
(question rendering, answer capture, routing, confirmation), and the shared
interfaces that department apps call. It does not know about individual tax
regimes or departments.

Department apps (dept_hmrc, dept_defra, etc.) own their own orchestration
logic, question content, and home page UX. They call into core via the
documented interface in `core/interfaces.py`. They never query core models
directly.

---

## 2. Folder structure

```
core/
  models.py               — full data model (all models, incl. SectionMember)
  interfaces.py           — documented platform interface for dept apps
  views_layer1.py         — shared orchestration views (regime_top_level,
                            regime_schedules, regime_schedule_sections,
                            regime_sections)
  views_layer2.py         — execution engine (section_start, question rendering,
                            section_confirm, section_done, table section views etc.)
  views_gate.py           — choose_user_for_regime (shared acting-for gate)
  views_admin_tools.py    — admin wizards (questions, sets, sections, routing)
  nav_reference.py        — navigation helpers (resolve_layer1_entry_url etc.)
  permissions.py          — get_permitted_sections
  session.py              — session read/write helpers
  templatetags/
    markdown_extras.py    — markdown rendering for guidance fields
  config/
    test_runner.py        — custom test runner (loads test data once per suite)
    routers.py            — PlatformRouter (routes platform questions to
                            'platform' DB alias)
```

---

## 3. Data model

Models defined in `core/models.py`:

**Configuration models** (define the regime structure):
- `Regime` — a tax or service regime (e.g. HMRC_IHT). Has `dept_id`, `regime_id`, `name`.
- `Schedule` — optional grouping of sections within a regime.
- `Section` — a set of questions, linear or branching or table-based.
  Has a **direct FK to `Schedule`** (`section.schedule`, nullable), with
  `display_order` living on `Section` itself. There is no separate
  `ScheduleSection` join model — an earlier design used one, but the actual
  implementation uses this simpler direct FK. (Correction as of 5 July 2026;
  earlier documentation incorrectly described a `ScheduleSection` model that
  does not exist in code.) Key fields:
  - `section_type` — integer, three values:
    - `0` Standard: routing-driven, one question (or set) per page
    - `1` Table: flat columns, all questions on one add-form page, no per-row routing
    - `2` Table with routing: repeating rows, each row is a mini routing journey
  - `section_name` — human-readable name; used directly as action button label
    for triage rows (rename in admin tools to update automatically)
  - `display_question_ids` (TextField, nullable) — semicolon-delimited question IDs.
    For type 1: defines add-form columns and display order.
    For type 2: declares which routed questions appear as summary columns
    (routing defines the full row journey; this is the display projection only).
  - `totals_question_ids` (TextField, nullable) — semicolon-delimited IDs of
    numeric questions to total at the foot of the table. Applies to both table types.
  - `section_guidance` (TextField, nullable) — shown at the top of table sections.
  - `show_confirmation` (BooleanField, default=True) — if False, auto-commits
    on last question and redirects to section_done without a confirmation page.
- `Question` — a single question. Key fields:
  - `question_id` — auto-generated (see naming convention below)
  - `question_type` — radio, radio_inline, checkbox, text, number, date,
    personal_name, address, compound
  - `is_platform` (BooleanField) — True for P_, O_, M_ questions
  - `options` — TextField. Semicolon-delimited for radio/checkbox; JSON
    array string for compound type (component definitions).
- `QuestionSet` — a grouped set of questions rendered as a single page.
  ID convention is **`SET1`, `SET2`, `SET3`...** (changed 1 July 2026 from
  a bare `S1, S2...` convention, which collided visually with Section IDs
  `{DEPT}_S{N}`). `_next_set_id()` in `views_admin_tools.py` enforces this.
- `QuestionSetMember` — membership/ordering within a QuestionSet.
- `SectionMember` — **(new, 1 July 2026)** explicit pool of Questions/Sets
  available to a Section, independent of and prior to routing. A node must
  be a `SectionMember` before it can appear in the section's routing wizard
  pickers. Fields: `section` (FK), `node_id`, `node_type` (`'Q'` or `'S'`),
  `added_order`. Scoped to type-0 and type-2 sections only (type-1 flat
  tables use `display_question_ids` and have no routing step). Existing
  sections were backfilled by scanning their `Routing` rows for every
  distinct `current_node`/`next_node` at migration time.
- `Routing` — routing rules between questions/sets within a section. Key fields:
  - `current_node` — the Q or S node this rule applies from
  - `condition_question_id` (CharField, nullable) — if set, routing evaluates
    the answer to *this* question rather than the current node's own answer.
    Useful for set nodes where branching depends on a specific member question's
    answer. Leave null for standard behaviour (condition on current node's answer).
  - `answer_value` — the trigger value; NULL means unconditional (default route)
  - `next_node` — destination question/set (NULL = end of section)
  - `comparator` and `threshold_value` — for scalar routing (e.g. >, >=)
  - `order_in_section` — **(changed 3 July 2026) a `FloatField`, not an
    integer.** Its only *functional* (runtime) role is determining
    `first_node` — the citizen-facing engine simply starts at whichever row
    has the lowest `order_in_section`. Beyond that first row, it is purely
    a *display-order* hint for the admin tree — the engine otherwise follows
    `current_node` → evaluate condition → `next_node` regardless of physical
    row order. **It is entirely admin-controlled and is never recomputed
    or renumbered by any background process.** See section 8 for how the
    admin tools set it on insert.

**Runtime models** (created as users move through regimes):
- `Case` — one case per user+regime entry. Key fields:
  - `user` — the citizen the case's answers belong to. For most regimes this
    is the same as the actor. For HMRC IHT it is a distinct synthetic
    identity representing the deceased — see HMRC IHT Reference and section
    6a below. **`case.user` is the single authoritative source for "who
    owns this case's data" — never cache it in session; always resolve or
    look it up fresh when needed** (see the correctness rule in section 4a).
  - `reference` (CharField, nullable) — assigned after matching check
    (e.g. IHT-000000001). Null = not yet verified.
- `Answer` — one row per question per case. `answer` is a JSONField.
- `AnswerHistory` — full history of answer changes.
- `AnswerTable` / `AnswerTableHistory` — table-type answer storage.
  `AnswerTable.answer` is a JSONField storing a list of row dicts.
  Each row dict is keyed by question_id; type-2 rows are sparse
  (only questions actually reached on the routing path are present).
- `SectionStatus` — completion status of a section for a user+regime.
  Note: keyed on `user`, not `case`. Fields: `user`, `regime`, `section_id`, `status`.
- `ScheduleStatus` — completion status of a schedule for a case.

**Access control models**:
- `Permission` — grants a user access to a regime/case/section combination.
  Five scope combinations (see section 6 below).
- `User` — custom user model (extends Django's `AbstractUser`). Table name:
  `core_user` (not auth_user). A `post_save` signal (`_auto_grant_regimes`)
  automatically grants every new `User` a self-permission
  (`actor=instance, user=instance, regime=X`) for every non-platform regime.
  This fires even for synthetic, login-incapable users (see section 6a) —
  harmless, since such users never authenticate to use it.
- `Department` — dept registry.

### Question ID naming convention

All IDs use underscore separator and are auto-generated — never typed by admin.

| Prefix | Scope | Example |
|--------|-------|---------|
| `P_N` | Platform person questions | P_1, P_6 |
| `O_N` | Platform organisation questions | (none yet) |
| `M_N` | Platform META/wizard questions | M_1–M_27 |
| `{DEPT}_N` | Department questions | HMRC_1, DEFRA_1 |
| `{DEPT}_S{N}` | Section IDs | HMRC_S1, HMRC_S3 |
| `{DEPT}_SCH{N}` | Schedule IDs | HMRC_SCH1 |
| `SET{N}` | QuestionSet IDs (changed 1 July 2026, was `S{N}`) | SET1, SET7 |
| `{DEPT}_{CODE}` | Regime IDs | HMRC_IHT |

### Platform questions (P series, is_platform=True)

| ID | Question | Type |
|----|----------|------|
| P_1 | What is your name? | personal_name |
| P_2 | What is your address? | address |
| P_3 | What is your date of birth? | date |
| P_4 | What is your email address? | text |
| P_5 | What is your mobile telephone number? | text |
| P_6 | What is your landline telephone number? | text |

### Question types

| Type | Notes |
|------|-------|
| `radio` | Single choice; options on separate lines |
| `radio_inline` | Single choice; Yes/No on same line as question (GDS inline). Used for survey-style Yes/No questions in sets. |
| `checkbox` | Multi-select; answer stored as list |
| `text` | Free text |
| `number` | Numeric input |
| `date` | Stored as `{day, month, year}` dict |
| `personal_name` | Stored as `{title, first_name, last_name}` dict |
| `address` | Stored as multi-field dict |
| `compound` | User-defined multi-field; components in `options` as JSON array |

All answers stored as JSONField. Schema evolution: adding a sub-field returns
`''` for old records (graceful). Removing a sub-field leaves it in old records.

**`radio_inline` rendering:** Template `core/question_radio_inline.html`.
In QuestionSet pages, handled via `question_set.html` which adds
`govuk-radios--inline` class when `field.question_type == 'radio_inline'`.
Template dispatch in `views_layer2.py` maps `'radio_inline'` to
`'core/question_radio_inline.html'`.

---

## 4. Execution engine (views_layer2.py)

The execution engine lives in `core` and handles everything within a section.
It is invariant — department apps do not modify it.

### 4a. Standard sections (section_type=0)

- `section_start` — entry point; builds routing/question/set metadata via
  `_build_section_tables(routing_rows)`; loads into session; detects prior
  answers and redirects to review if section already started
- Question rendering — all question types via shared templates
- Answer capture and validation via `_process_answer` / `_process_set_answer`
- `section_review` — shows all answers; citizen can amend
- `section_confirm` — shows delta (changed answers) and commits on POST
- `section_done` — completion; delegates to `resolve_completion_url` (see §5)
- Routing engine — `_evaluate_routing` evaluates Routing rules;
  `_resolve_routing_answer` determines which answer to test (current node's
  own answer, or a named `condition_question_id`)

**`show_confirmation=False` behaviour:** The last question routes directly to
`section_done` without showing the review page. On re-entry (existing answers
found by `section_start`), the user is shown the review page and can amend.

**CRITICAL correctness rule (added 5 July 2026): use `case.user`, never
`request.user`, for any read or write of a case's own `Answer`,
`AnswerHistory`, or `SectionStatus` rows.** `request.user` is the *actor* —
the person currently logged in and providing answers. `case.user` is the
*subject* — the citizen the answers are about. For most regimes these are
identical, which let this distinction go unenforced for a long time. HMRC
IHT (see HMRC IHT Reference) is the first regime where they genuinely
differ — the actor is the executor, the subject is a synthetic identity
representing the deceased — and two real bugs were found and fixed on 5
July 2026 where `views_layer2.py` used `request.user` where `case.user` was
required (`section_start`'s existing-answer lookup, and five sites inside
`_commit_section_answers`). The one deliberate, correct exception is
cross-case pre-population in `section_question` (the "suggested from a
prior case" banner), which is intentionally actor-scoped — it is asking
"what has this *actor* answered elsewhere," not "what does this case's
subject know." Any new code touching `Answer`/`AnswerHistory`/
`SectionStatus` should default to `case.user` unless it is specifically
doing actor-scoped pre-population.

### 4b. Routing engine

Two private helpers used by all section types:

**`_resolve_routing_answer(routing_table, current_node, all_answers)`**
Determines which answer to test when evaluating routing from `current_node`.
If any routing row for `current_node` has `condition_question_id` set,
returns `all_answers[condition_question_id]`. Otherwise returns
`all_answers[current_node]` (standard: condition on current node's own answer).
`all_answers` must contain all answers accumulated so far in the journey
(for set nodes: `{**basic_answers, **field_values}`).

**`_evaluate_routing(routing_table, current_node, answer)`**
Evaluates routing rows for `current_node` against `answer`. Returns
`(next_node, found)`. `next_node=None` means END. Supports equality
matching on `answer_value` and scalar comparators via `comparator`/
`threshold_value`. Unconditional rows (`answer_value=None`) act as defaults.

### 4c. Flat table sections (section_type=1)

- `section_table` — landing page; displays all rows as a table using
  `display_question_ids` as column definitions; "Add a record" goes to
  `section_table_add`
- `section_table_add` — renders all columns as a single form page (analogous
  to a question set); single POST saves the row
- `section_table_delete` — removes a row by index
- `section_confirm_table` — snapshots to `AnswerTableHistory`, marks complete
- `section_done` — shared with standard sections

### 4d. Routed table sections (section_type=2)

Each row is a mini routing journey — conceptually, the section's routing
is run repeatedly, each run producing one row stored in `AnswerTable`.

**Row journey flow:**
1. `section_table_routed_add` — init: builds routing/question/set metadata,
   seeds `request.session['_table_row'][section_id]` with empty `row_answers`
   and `row_index=None`, redirects to first node
2. `section_table_routed_change` — init for existing row: same as above but
   pre-populates `row_answers` from the saved row, sets `row_index=<int>`
3. `section_table_routed_question` — workhorse GET/POST for each node in the
   row journey; supports both Q-nodes and S-nodes (QuestionSet); uses
   `_resolve_routing_answer` + `_evaluate_routing`; on END calls
   `_commit_table_row` and clears row session
4. `_commit_table_row` — writes `row_answers` to `AnswerTable`: appends if
   `row_index=None` (new row), replaces at index if `row_index=<int>` (change)
5. `section_table_row_detail` — read-only view of "extra" answers (keys in the
   row not in `display_question_ids`) for a specific row

**Path divergence / pruning:**
At commit time, `row_to_save` is pruned to `asked_ids` — the list of nodes
actually visited on the current path through the routing tree. This ensures
that when a user amends a row and takes a different branch, stale answers
from the original path are not saved. The `not asked_ids` guard preserves
legacy/type-1 behaviour where `_asked_ids` was never populated.

```python
asked_ids = row_data.get('_asked_ids', [])
row_to_save = {k: v for k, v in row_data.items()
               if not k.startswith('_') and (not asked_ids or k in asked_ids)}
```

**Table landing for type 2:**
- "Add a record" links to `section_table_routed_add`
- Each row has: "Change" → `section_table_routed_change`; "Delete" →
  `section_table_delete`; "Other details" → `section_table_row_detail`
  (only shown when the row has keys not in `display_question_ids`)

**Row session namespace:** `request.session['_table_row'][section_id]`
Contains: `routing_table`, `question_table`, `set_table`, `question_to_set`,
`asked_ids`, `row_answers`, `row_index`. Isolated from the main `pss` dict.

**Sparse rows:** Type-2 rows are dicts containing only questions actually
reached on the routing path taken. Questions on unvisited branches are absent.
The summary table shows `—` for absent keys.

### 4e. Shared table helpers

**`_build_section_tables(routing_rows)`** — extracts the routing/question/set
table build logic shared between `section_start`, `section_table_routed_add`,
and `section_table_routed_change`. Returns
`(routing_table, question_table, set_table, question_to_set)`.

---

## 5. Platform interface (core/interfaces.py)

Department apps call these functions. Never query core models directly.

```python
create_case(user, regime)
```
Always creates a fresh Case. Use for all new regime entries.

```python
get_cases(user, regime, status=None)
```
Returns queryset of Cases for user+regime, newest first.

```python
get_answers(case, question_ids)
```
Returns `{question_id: answer}` dict. Uses `case.user` internally.
Returns `None` for missing/unanswered questions.
**Always use this for answer reads in dept code — never query Answer directly.**

```python
get_asked_answers_for_section(case, section)
```
**(New, 5 July 2026.)** Walks a section's routing against the case's
confirmed answers, replaying the same path the citizen actually took.
Returns an ordered list of `{'question_id', 'question_text', 'answer'}`
dicts — one entry per question actually reached and answered, in the order
asked. Set nodes are expanded to their member questions in member order.
Stops at the first unanswered/unreached node. Extracted from logic
previously duplicated inline in `section_start`'s re-entry path and
`section_table_routed_change`. Use this instead of hand-picking a fixed
list of question IDs when building a dept home-page summary — a fixed list
cannot reflect branching (e.g. a conditional follow-up question that only
applies to some cases).

```python
format_answer_for_display(question_type, answer)
```
**(New, 5 July 2026.)** Formats a raw `Answer.answer` JSON value into a
display string, per question type (handles `date`, `personal_name`,
`address`, `compound`, and plain types). Extracted from logic previously
duplicated in `section_review`; both `section_review` and any dept code
building a display summary should use this single implementation.

```python
get_section_status(user, regime, section)
get_schedule_status(user, regime, schedule)
```
Returns status string: `'not_started'`, `'in_progress'`, `'complete'`.

```python
get_permitted_sections(user, regime, case=None)
```
Returns queryset of Sections the user may access.

```python
call_core(request, items, title=None)
```
Unified entry point for core execution engine. `items` is an ordered list
of section IDs and/or schedule IDs. Handles single-item (direct) and
multi-item (top-level page) patterns. Sets `return_url` to `regime_home_url`
as the initial value; this is immediately overwritten when the citizen visits
a Layer 1 list view (see completion routing below).

### Completion routing — `resolve_completion_url`

`section_done` delegates entirely to `resolve_completion_url(request, pss, section)`
in `views_layer2.py`. This is a single function with a single precedence chain —
one concept, one place:

| Priority | Condition | Destination |
|----------|-----------|-------------|
| 1 | `post_confirm_redirect` in session (popped; one-shot) | that URL |
| 2 | All `SectionStatus` rows for user+regime are `complete` | `regime_home_url` |
| 3 | All `SectionStatus` rows for user+schedule are `complete` | `schedule_list_url` |
| 4 | `return_url` set in session | `return_url` |
| 5 | (none of the above) | `/` + warning log |

**`post_confirm_redirect`** is a dept-set one-shot override. Set
`request.session['post_confirm_redirect'] = '/path/'` before entering the
section journey; it fires exactly once and bypasses all rollup logic. Not
used in HMRC IHT (which uses the two-phase `iht_in_core` /
`iht_current_action` pattern — see HMRC IHT Reference section 2).

**`return_url`** is written by all three Layer 1 list views on every visit —
each sets it to its own URL so `section_done` can navigate back to the list
that sent the citizen into the section:

| Layer 1 view | Written by | Sets `return_url` to |
|---|---|---|
| `regime_sections` | `update_session` | `/regime/<id>/sections/` |
| `regime_schedule_sections` | `update_session` | `/regime/<id>/schedule/<id>/sections/` |
| `regime_top_level` | `update_session` | `/regime/<id>/top/` |

`call_core` also writes `return_url = regime_home_url` as an initial value,
but this is overwritten the moment the citizen visits a list view.

**Three terms for three layers:**
- **Section-list navigation** — the citizen browsing Layer 1 list views
  (`regime_sections`, `regime_schedule_sections`, `regime_top_level`).
  Each view owns `return_url` while the citizen is working through its items.
- **Completion routing** — `resolve_completion_url` deciding where to go
  after a section completes. Uses rollup state and `return_url`.
- **Regime orchestration** — dept-level logic in e.g. `orchestrate.py`,
  operating above completion routing. Uses `post_confirm_redirect` or the
  two-phase `iht_in_core`/`iht_current_action` pattern.

### Session keys written by core / read by dept

| Key | Written by | Read by | Purpose |
|-----|-----------|---------|---------|
| `return_url` | Layer 1 list views (all three); `call_core` (initial value) | `resolve_completion_url` | Where to go after section completes (priority 4) |
| `regime_home_url` | dept orchestrator (`_setup`) | `call_core`; `resolve_completion_url` (priority 2) | Used as `return_url` initial value; regime-complete destination |
| `schedule_list_url` | `regime_schedule_sections` | `resolve_completion_url` (priority 3) | Schedule-complete destination |
| `permitted_section_ids` | `call_core` | `regime_sections` | Filter section list |
| `permitted_schedule_ids` | `call_core` | `regime_schedule_sections` | Filter schedule list |
| `top_level_items` | `call_core` (multiple) | `regime_top_level` | Ordered mixed list |
| `top_level_title` | `call_core` (multiple) | `regime_top_level` | Page heading |
| `post_confirm_redirect` | dept code (optional) | `resolve_completion_url` (priority 1) | One-shot override; highest priority |
| `_table_row` | `section_table_routed_add/change` | `section_table_routed_question` | Per-row journey state (type-2 sections only) |

**Caution on caching identity in session (added 5 July 2026):** avoid caching
`user_id` (or any derived-from-`case.user` value) in session across a
transition that changes `case.user` — e.g. an IHT case moving from draft to
verified. A same-session bug was found and fixed on 5 July 2026 where a
cached session `user_id` continued pointing at the actor after promotion,
causing the freshly-verified case's own action button to show "Not started"
despite the section being complete. The fix removed the cache entirely:
`iht_orchestrate` now resolves `user` fresh from `case.user` on every
request rather than trusting a session value. Prefer this pattern —
resolve identity from the authoritative DB row, don't cache it — over
remembering to update a cached value at every transition point.

### Deprecated

`get_or_create_case()` — deprecated. TEST/demo harness only. Do not use.

---

## 6. Permission model

`Permission` grants a user access with five scope combinations:

| regime | case | section | Meaning |
|--------|------|---------|---------|
| null | null | null | All regimes, all cases, all sections (power of attorney) |
| set | null | null | All cases and sections within that regime |
| set | set | null | All sections of that specific case |
| set | null | set | That section across all cases in the regime |
| set | set | set | That specific section of that specific case |

Unique constraint includes all five fields. The grant wizard at `/<dept>/tools/actors/`
manages permissions. A case selection step (D6) is not yet built.

### 6a. Actor / User separation and the acting-for gate

The platform distinguishes **actor** (the person currently logged in,
providing answers) from **user** (the citizen the data is about). For most
regimes these are the same person. Where they can differ — an intermediary
acting for someone else, or (uniquely) HMRC IHT where the subject is a
deceased person who can never log in — the platform resolves which
identity applies via a shared, regime-scoped gate:

```python
choose_user_for_regime(request, regime, leading_option, next_url)
```
**(Promoted to `core/views_gate.py` on 5 July 2026; was previously a
department-specific `choose_user` under `dept_demo`.)** Runs *after* regime
selection (not before), so its candidate list can be correctly scoped to
`Permission` rows for that specific regime rather than showing every
acting-for relationship a user has across every department. Builds a
candidate list from `leading_option` (always shown first — typically
`{'label': 'Myself', ...}` for self-filing regimes) plus every
`Permission.objects.filter(actor=request.user, regime=regime)` row
excluding self. **Auto-skips silently (no screen shown) when there is
exactly one candidate** — this is why solo users never see an extra step.

HMRC IHT is the one regime with a genuinely different leading option —
`{'label': 'Begin a new estate', ...}` instead of `'Myself'`, since IHT's
actor is structurally never the subject. See HMRC IHT Reference for the
full estate-identity lifecycle (synthetic deceased `User` creation,
`Answer` re-keying, case-scoped `Permission` grant).

**Known gap (backlog item):** `dept_dwp` has its own older, non-regime-
scoped `choose_user` implementation that predates this shared routine and
has not been migrated to it.

---

## 7. Database structure

Single Neon database (name: `hmrc_demo` — legacy name, ignore it).
Two DB aliases in `settings.py`:

| Alias | Content | Notes |
|-------|---------|-------|
| `default` | Dept data (regimes, sections, answers, etc.) | |
| `platform` | Platform data (P_, M_, O_ questions) | Currently same Neon DB |

`PlatformRouter` in `config/routers.py` routes `Question`, `QuestionSet`,
and `QuestionSetMember` with `is_platform=True` to the `platform` alias.

Target architecture: separate Neon project per dept + one platform DB.
Separation is configuration-only — no code changes needed when provisioned.

**Test isolation note (found 5 July 2026):** because `'default'` and
`'platform'` are separate DB connections to the same physical database,
under `READ COMMITTED` isolation a test fixture written via `.using('default')`
inside a transaction is not visible to platform-routed reads on the
`'platform'` connection until committed. Tests exercising both need
`@override_settings(DATABASE_ROUTERS=[])` to fall back to `'default'` for
the duration of that test class.

Key table names for psql:

| Table | Contents |
|-------|---------|
| `core_user` | Users (NOT auth_user) |
| `core_answer` | Answers |
| `core_case` | Cases |
| `core_sectionstatus` | Section completion (keyed on user, not case) |
| `core_routing` | Routing rules |
| `core_sectionmember` | Section membership pool (new 1 July 2026) |
| `core_answertable` | Table section answers (JSON list of row dicts) |

---

## 8. Admin tools

Available at `/<dept>/tools/`. Admin and super_admin users only.

**Access tiers:**
- `super_admin` — platform questions (P_, O_, M_), full tools
- `admin` — dept questions and configuration, scoped to active dept

**Key tools:**
- Question creation (dept questions and platform questions). Can also be
  reached inline from a section's pool panel ("Define a new question") —
  on save, the new question is automatically added to that section's pool
  and the admin is returned there, rather than to the general question list.
- **Section pool panel ("Add questions and sets to this section")** — sits
  between the section title/type panel and the routing panel, for type-0
  and type-2 sections. Lists current `SectionMember` rows (grouped
  Questions/Sets) with a remove action per row (blocked, silently, if the
  node is still referenced by any `Routing` row — a visible warning on
  removal-in-use is backlogged, not yet built). Below the list: a grouped
  picker to associate an existing dept question/set not yet in the pool,
  and a "Define a new question" link (see above). **The routing wizard's
  node pickers only ever offer nodes already in this pool** — this is what
  keeps the picker lists manageable as the question bank grows.
- **Routing tree display** — one panel per Section, showing each question
  node with its conditions/destinations indented beneath. As of 3 July 2026
  this was substantially simplified:
  - Each question row has a three-dot menu: the **first row only** shows
    "Insert above" + "Insert below" + "Delete"; every other row shows
    "Insert below" + "Delete" (no branching/linear distinction any more).
  - **"Insert" never rewires any other row.** It only ever creates new
    `Routing` row(s) from whatever `current_node`/condition/`next_node`
    values are chosen on the insert-wizard page. Placement in the display
    is purely a matter of the new row's `order_in_section` value (see
    below) — nothing else is touched.
  - **"Delete" (`delete_mode='node_only'`, the only mode wired to the UI)**
    removes only the target node's own `Routing` rows. It does **not**
    touch predecessors or downstream nodes. A predecessor left pointing at
    the now-deleted node becomes a dangling reference, caught by the
    validation banner rather than silently rewritten — this is deliberate,
    not a gap: earlier `delete_all`/`promote` modes existed and cascaded
    further, which caused real data loss during development and were
    retired from the UI (the underlying code paths remain, unused, in case
    of future need).
  - **Condition/branch rows have no menu at all** — plain text. To edit a
    branching node's conditions, delete the node and reinsert it via
    "insert below" on its predecessor, redefining all conditions at once
    on the wizard page.
  - **Bracketed, clickable destinations** (e.g. `[HMRC_43]`) appear only
    for a destination that has **no routing rows of its own yet** — click
    to jump straight to the insert wizard with that node pre-filled as
    `current_node`, correctly anchored so the new row displays adjacent to
    the reference you clicked (not at the top of the list). A destination
    that already has its own row renders as plain text at the reference
    point instead.
  - **`order_in_section` placement on insert:** "insert below row X" sets
    the new row's value to the midpoint between X and whatever currently
    follows it (or `X + 10` if X is currently last). "Insert above" (first
    row only) sets it to half the current first row's value. Values are
    plain floats — repeated insertions into the same gap simply keep
    halving it (e.g. 20/30 → 25 → 27.5 → 28.75), which in practice never
    runs out of room. **There is no renumbering step of any kind** — a
    row's `order_in_section` never changes except at the moment it is
    created.
  - **Validation banner** (unreachable nodes, dangling destination
    references) is computed separately via a genuine graph-reachability
    walk from the entry point — this is unrelated to display ordering and
    was deliberately kept when the renumbering machinery was removed.
- Section edit and routing tree are now rendered from a single shared
  partial (`core/_routing_tree.html`), included by both the dedicated
  routing page and the section-edit page — previously these were two
  independently hand-written copies that had drifted out of sync.
- Regime management (create, edit, reorder, assign sections)
- Schedule management (create, edit, assign sections to schedule)
- Permission grant wizard (`/tools/actors/`)

**Important:** A section must be assigned to a regime (or to a schedule
within a regime) to be visible via `get_permitted_sections`. A section with
no regime/schedule assignment will not appear in any section list.

**`regime_top_level`** — when `call_core` is called with multiple items,
renders an ordered mixed list of schedules and bare sections in dept-specified
order, with rollup status for each row.

---

## 9. Navigation and URL structure

Root landing page at `/` (no login required). Lists all departments except
PLATFORM and TEST. Clicking a regime requires login (`?next=` mechanism).
`LOGOUT_REDIRECT_URL = '/'`.

| URL pattern | View | Notes |
|-------------|------|-------|
| `/<dept>/` | dept_home | |
| `/<dept>/regime/<regime_id>/` | regime_home | Dept dispatcher |
| `/choose-user/` | `core:choose_user` (via `choose_user_for_regime`) | Regime-scoped acting-for gate |
| `/select-self/` | `core:select_self` | Proceeds as self, sets session, redirects to `?next=` |
| `/select-identity/<perm_id>/` | `core:select_identity` | Proceeds as a named acting-for candidate |
| `/regime/<id>/top/` | regime_top_level | Mixed ordered top-level list |
| `/section/<section_id>/start/` | section_start | Standard section entry |
| `/section/<section_id>/review/` | section_review | |
| `/section/<section_id>/done/` | section_done | Shared by all section types |
| `/section/<section_id>/table/` | section_table | Table landing (types 1 and 2) |
| `/section/<section_id>/table/add/` | section_table_add | Flat add form (type 1) |
| `/section/<section_id>/table/add-routed/` | section_table_routed_add | Row journey init (type 2) |
| `/section/<section_id>/table/add-routed/<q_or_s_id>/` | section_table_routed_question | Row journey question (type 2) |
| `/section/<section_id>/table/change/<row_index>/` | section_table_routed_change | Row change init (type 2) |
| `/section/<section_id>/table/row-detail/<row_index>/` | section_table_row_detail | Extra details view (type 2) |
| `/section/<section_id>/table/delete/<row_index>/` | section_table_delete | Delete row (types 1 and 2) |
| `/section/<section_id>/table/confirm/` | section_confirm_table | Confirm table section |
| `/<dept>/tools/` | Admin tools | |

Core URLs are always ID-based — `/section/HMRC_S4/start/` not
`/section/common-assets/start/`. No human-readable slugs in core URLs.
Dept action button URLs (e.g. `/hmrc/iht/action/hmrc_s4/`) are dept-specific
and also use section IDs as slugs — see HMRC IHT Reference section 8a.

---

## 10. Test infrastructure

- Custom test runner: `config/test_runner.py` — loads test data once per suite
- Test command: `/Users/robert/anaconda3/envs/env_python_django_psql/bin/python manage.py test --keepdb`
  — **always use the full conda path.** A bare `python manage.py test` can
  silently hit a different Python/Django install (observed 2 July 2026,
  producing a misleadingly low test count with no error).
- Test dept: `dept_demo`, internal `dept_id='TEST'`, URL prefix `/demo/`
- All core tests run against TEST data
- Current count: 193 tests passing, 0 failures, 1 skip (pre-existing)
- `dept_hmrc` tests included in total

---

## 11. Design decisions (platform-level)

**Sections are independent of regimes at creation time.** Created without
regime assignment, assigned later via Schedule edit or Regime edit.

**Navigation pattern inferred from structure.** Pattern A/B/C not stored —
inferred at runtime from regime composition.

**Two-tier question bank.** Platform tier (P_, O_): ~20-30 questions,
governed centrally by super_admin. Department tier (DEPT_N): each dept's
own questions independently. Cross-dept pre-population works on platform
questions only.

**One Login as identity anchor.** GOV.UK One Login credential is the
identity anchor for cross-government pre-population lookups.

**Multiple cases per user+regime.** Platform allows multiple Cases per
user+regime with no restriction. `create_case()` always creates fresh.
`get_cases()` returns all. Dept regime home decides what to surface.

**JSON storage and schema evolution.** All answers stored as JSONField.
Adding a sub-field: old records return `''` for new key (graceful).

**Dept-specific models.** Dept apps may define their own Django models for
data outside `core_answer`. `dept_hmrc` has `IHTReckoner` as the first
example. Dept models live in `dept_hmrc/models.py` and are outside core.

**Orchestration layer / execution engine split.** The execution engine
(core) is invariant. The orchestration layer (dept) reads state, dispatches
to sections, renders the home UX. Formally distinct even though both are
Django view layers in the PoC.

**Two-phase dept orchestration pattern.** The preferred pattern for dept
orchestration (exemplified in HMRC IHT) uses two session flags:
- `iht_in_core` — set on entry to core, popped on every regime home visit
- `iht_current_action` — identifies which action button sent the user to core

This gives the dept orchestrator a clean ENTRY/EXIT distinction for each
action button. `post_confirm_redirect` is not needed under this pattern.
See HMRC IHT Reference section 2.

**Known tech debt (flagged 5 July 2026, not yet resolved):** within HMRC
IHT's own orchestrator, two different code paths currently exist for
starting a new estate — `_entry_start` (the original bootstrap path,
which renders an interim "pre-verified" screen) and `iht_start_new_estate`
(added later for the multi-estate picker, which skips straight into S1).
These diverge in behaviour and should be reconciled — likely by having
`iht_start_new_estate` become `_entry_start`'s "start" path with a flag,
rather than remaining a second, subtly different implementation. Flagged
for a dedicated review session rather than fixed reactively.

**Table sections are repeating basic sections (type 2).** A type-2 table
section is conceptually a basic section whose routing journey can be run
N times, each run producing one row. The routing engine is identical;
only the storage (row dict in `AnswerTable`) and display (summary table)
differ. This means all routing capabilities — conditional branching,
`condition_question_id`, set nodes — are available within a row journey.

**Type-2 row pruning.** At commit time, row answers are pruned to `asked_ids`
(the nodes actually visited on this path). Stale answers from a prior path
through the same row are discarded. This is the correct behaviour for sparse
rows and path divergence on amendment.

**Triage section URLs use section IDs, not slugs.** Action button views for
triage asset sets are named `iht_action_hmrc_s4`, `iht_action_hmrc_s5` etc.,
matching the section ID. This avoids a naming problem and keeps the pattern
consistent with core URLs. Adding a new triage section requires: add section
to HMRC_SCH1 in admin, add a view and one URL entry in urls.py.

**Resolve identity from source, don't cache across a state transition.**
See section 5's caution note. Where a value (like a `Case`'s owning `User`)
can genuinely change during a session, prefer resolving it fresh from the
database on each request over caching it in session and remembering to
update the cache at every transition point — the latter is exactly the
pattern that produced two real bugs on 5 July 2026.
