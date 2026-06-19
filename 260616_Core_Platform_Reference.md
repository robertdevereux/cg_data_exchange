# cg_data_exchange — Core Platform Reference
Date: June 2026
Status: Stable reference — update only when the core app itself changes
Verified: Content checked against file_dump.txt by Claude on 14 June 2026

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
  models.py               — full data model (all 16+ models)
  interfaces.py           — documented platform interface for dept apps
  meta_processors.py      — meta processor system
  views_layer1.py         — shared orchestration views (regime_schedules,
                            regime_schedule_sections, regime_sections)
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
- `Section` — a linear or branching set of questions. Key fields:
  - `show_confirmation` (BooleanField, default=True) — if False, auto-commits
    on last question and redirects to section_done without a confirmation page.
    On re-entry of a completed show_confirmation=False section, section_start
    detects existing answers and redirects to review screen.
- `Question` — a single question. Key fields:
  - `question_id` — auto-generated (see naming convention below)
  - `question_type` — radio, checkbox, text, number, date, personal_name,
    address, compound
  - `is_platform` (BooleanField) — True for P_, O_, M_ questions
  - `options` — TextField. Semicolon-delimited for radio/checkbox; JSON
    array string for compound type (component definitions).
- `QuestionSet` — a grouped set of questions rendered as a single page.
- `QuestionSetMember` — membership/ordering within a QuestionSet.
- `Routing` — routing rules between questions within a section. Key fields:
  - `answer_value` — the trigger value; NULL means unconditional (default route)
  - `next_node` — destination question (NULL = end of section)
  - `comparator` and `threshold_value` — for Tier 1 scalar routing (e.g. >, >=)

**Runtime models** (created as users move through regimes):
- `Case` — one case per user+regime entry. Key fields:
  - `reference` (CharField, nullable) — assigned after matching check
    (e.g. IHT-000000001). Null = not yet verified.
- `Answer` — one row per question per case. `answer` is a JSONField.
- `AnswerHistory` — full history of answer changes.
- `AnswerTable` / `AnswerTableHistory` — table-type answer storage.
- `SectionStatus` — completion status of a section for a case.
- `ScheduleStatus` — completion status of a schedule for a case.

**Access control models**:
- `Permission` — grants a user access to a regime/case/section combination.
  Five scope combinations (see section 6 below).
- `User` — custom user model. Table name: `core_user` (not auth_user).
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
| `radio` | Single choice |
| `checkbox` | Multi-select; answer stored as list |
| `text` | Free text |
| `number` | Numeric input |
| `date` | Stored as `{day, month, year}` dict |
| `personal_name` | Stored as `{title, first_name, last_name}` dict |
| `address` | Stored as multi-field dict |
| `compound` | User-defined multi-field; components in `options` as JSON array |

All answers stored as JSONField. Schema evolution: adding a sub-field returns
`''` for old records (graceful). Removing a sub-field leaves it in old records.

---

## 4. Execution engine (Layer 2)

The execution engine lives in `core` and handles everything within a section:

- `section_start` — entry point; detects prior completion for show_confirmation=False sections
- Question rendering — all question types via shared templates
- Answer capture and validation
- `section_confirm` — shows delta (changed answers) and commits on POST
- `section_done` — completion; redirects to `post_confirm_redirect` if set,
  otherwise to `return_url`
- Routing engine — evaluates Routing rules to determine next question
- Pre-population — fills answers from prior sections/regimes on P_ questions

The execution engine is invariant — department apps do not modify it.

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
format_date(answer)
```
Formats `{day, month, year}` dict as DD/MM/YYYY string.

```python
bootstrap_section_statuses(user, regime, sections)
```
Ensures a SectionStatus record exists for every permitted section for this
user. Called when a citizen enters a regime. Safe to call multiple times
(idempotent).

```python
call_regime(request, regime, actor, user, url_prefix='')
```
Finds or creates a case (via `get_or_create_case` internally), bootstraps
section statuses, writes all session keys, and returns the Layer 1 entry URL
(sections menu). For direct section entry bypassing the menu, use
`call_sections` instead.

```python
call_sections(request, regime, actor, user, section_ids, url_prefix)
```
Sets `return_url=request.path` in session. Use for selective section entry
from a bespoke regime home page. Note: does not set `regime_home_url` in
session — known gap, fix when it bites.

```python
call_schedules(request, regime, actor, user, schedule_ids, url_prefix)
```
As call_sections but for schedules.

### Session keys used by the platform

| Key | Set by | Consumed by | Purpose |
|-----|--------|-------------|---------|
| `post_confirm_redirect` | dept code | `section_done` | Override return_url after section completion (see below) |
| `return_url` | `call_sections` | `section_done` | Where to go after section |

**`post_confirm_redirect` — the dept interception mechanism**

When a section completes, `section_done` checks for `post_confirm_redirect`
in session. If present, it redirects there and clears the key (one-shot).
If absent, it redirects to `return_url` (normally regime home).

This is the mechanism by which dept code intercepts `section_done` to run
processing between section completion and the return to regime home. It is
needed when the dept must do something the core cannot — for example,
running a duplicate check after S1, or computing a threshold after S3.
Without it, `section_done` always returns to `return_url` and the dept
has no interception point.

`post_confirm_redirect` fires on any `section_done` while the key is set
— including table sections (which go through `section_done` via
`section_confirm_table`). Dept code is responsible for ensuring the key is
only live when the intended section is active. In IHT, the S3 key is
cleared in `section_start` when HMRC_S1 is entered, preventing misfire if
the executor amends deceased's details after completing the reckoner.

**LATER:** Add `section_id` scoping to `post_confirm_redirect` so the
platform itself prevents misfires:
```python
request.session['post_confirm_redirect'] = {
    'url': reverse('dept_hmrc:iht_reckoner_compute'),
    'section_id': 'HMRC_S3',
}
```
`section_done` would then only consume the key if the completing section
matches. This is a core change — defer until a concrete misfire risk arises.

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

Key table names for psql:

| Table | Contents |
|-------|---------|
| `core_user` | Users (NOT auth_user) |
| `core_answer` | Answers |
| `core_case` | Cases |
| `core_sectionstatus` | Section completion |
| `core_routing` | Routing rules |

---

## 8. Admin tools

Available at `/<dept>/tools/`. Admin and super_admin users only.

**Access tiers:**
- `super_admin` — platform questions (P_, O_, M_), full tools
- `admin` — dept questions and configuration, scoped to active dept

**Key tools:**
- Question creation (dept questions and platform questions)
- Section builder with routing insert wizard
- Routing display (flat directed-graph format — each question node at left
  margin, conditions indented, convergence nodes in [brackets])
- Regime management (create, edit, reorder, assign sections)
- Permission grant wizard (`/tools/actors/`)

**Important:** A section must be assigned to a regime to be visible via
`get_permitted_sections`. A section with no regime assignment will not
appear in any section list. Always check regime assignment when debugging
invisible sections.

---

## 9. Navigation and URL structure

Root landing page at `/` (no login required). Lists all departments except
PLATFORM and TEST. Clicking a regime requires login (`?next=` mechanism).
`LOGOUT_REDIRECT_URL = '/'`.

| URL pattern | View | Notes |
|-------------|------|-------|
| `/<dept>/` | dept_home | |
| `/<dept>/regime/<regime_id>/` | regime_home | Dept dispatcher |
| `/section/<section_id>/start/` | section_start | Core execution engine |
| `/section/<section_id>/review/` | section_review | |
| `/section/<section_id>/done/` | section_done | |
| `/<dept>/tools/` | Admin tools | |

---

## 10. Test infrastructure

- Custom test runner: `config/test_runner.py` — loads test data once per suite
- Test command: `/Users/robert/anaconda3/envs/env_python_django_psql/bin/python manage.py test --keepdb`
- Test dept: `dept_demo`, internal `dept_id='TEST'`, URL prefix `/demo/`
- All core tests run against TEST data
- Current count: 104 core tests passing (1 skipped — pre-existing)
- `dept_hmrc` tests run separately (not in INSTALLED_APPS): 11 passing
- Total across both: 115

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
data that falls outside `core_answer` — for example, computed values or
conclusions that the platform's question model cannot represent. `dept_hmrc`
has `IHTReckoner` as the first example. Dept models live in
`dept_hmrc/models.py` and migrate normally via Django migrations in the
dept app. They are outside core and never queried by core code.

**Orchestration layer / execution engine split.** The execution engine
(core) is invariant — handles all question rendering, answer capture,
confirmation, routing within sections. The orchestration layer (dept)
reads state, dispatches to sections, renders the home UX. These are
formally distinct even though both are implemented as Django view layers
in the PoC.
