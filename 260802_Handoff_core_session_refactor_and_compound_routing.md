# Track (ii) Build Note: Session-Caching Refactor and Compound-Condition Routing

*Assumes Paper 5 (Towards a 1 April Private Beta) has been read first. This note is the "how do we build Track (ii)" document Paper 5 §6 points to — it operates entirely within the ground rules Paper 5 sets out (§3: the homepage/Core boundary, entry/exit criteria, the three section types, the answer format, the estate progress summary) and doesn't restate them. Written for a fresh chat picking up this thread; assumes access to `file_dump.txt` (the current Core codebase) and the technical architecture papers (Annex A2, Build_CORE docs). Two pieces of work are described here — related, but genuinely separable, and this note is explicit throughout about which is which.*

---

## 1. Where this came from

Working through the IHT ownership/spousal-exemption design in detail surfaced a real gap in Core's routing capability: some routing decisions need to test **more than one already-answered question at once** (e.g. "ownership type = Sole ownership" AND "was the deceased married = Yes"), and the current `Routing` model only supports testing a single question's answer per node. That's Piece 2 below, and a prototype already exists for it.

While designing that prototype, a second, independent issue came to light: it assumed a "load once at journey start, then work entirely from an in-memory/session copy, write once at the end" architecture, modelled on the eventual Salesforce Platform Cache target (§5). Checking this against the actual Core codebase found that **this pattern already exists correctly for ordinary sections (type=0), but is not applied consistently for table sections (type=1/2)** — routing/question data is re-fetched from the database on every single step, when it should be fetched once per section visit and reused. That's Piece 1.

The two pieces are independent — Piece 1 can be fixed without Piece 2, and Piece 2 doesn't need Piece 1 to be usable — but they share a boundary (§4) worth designing deliberately so the two don't end up coupled by accident.

---

## 2. Piece 1: two "read into cache" functions, split by how each derives its question set

Two versions of the section-level cache-loading step, not one, because type=0/2 and type=1 derive *which questions matter* in fundamentally different ways — routing-derived vs. section-defined. Both currently over-fetch; the fix for each is the same shape, applied to different source data.

### 2.1 `load_cache_for_routed_section()` — shared by type=0 and type=2

Type=0 and type=2 should use **one shared function**, because both derive their question set the same way: walking every `current_node` referenced in the section's `Routing` rows and fetching the `Question`/`QuestionSet` objects those nodes resolve to. This is exactly what `_build_section_tables()` already does, and it's already called identically by `section_start` (type=0) and by all three type=2 entry points (`section_table_routed_add`, `_change`, `_question`) — what's missing is only that type=2's callers don't cache and reuse its output the way type=0's caller does.

**The problem, with evidence (type=2 — type=0 already does this correctly):** `section_start`'s docstring states its job plainly: *"Load routing/questions into session and redirect to the first question."* It queries `Routing` **once**, builds via `_build_section_tables()`, and writes into session. Every subsequent step (`section_question`) reads back from session.

Type=2 doesn't follow this. `section_table_routed_add` and `section_table_routed_change` (row-journey init) each call `_build_section_tables()` once but discard the result rather than storing it; `section_table_routed_question` (the per-step workhorse) repeats the identical query and rebuild on every single GET/POST. For a row with six steps, the routing table is rebuilt seven times — and none of it carries over to a second row in the same section visit either, since `section_table_routed_add` re-queries from scratch every time a new row starts, even though routing and question definitions can't have changed between rows.

**The fix:** fetch once, on first entry to the section for this visit (not first entry to each row); store in a section-level session namespace; every view that currently re-queries reads from there instead, populating only if not already present for this visit.

**A genuine gap this exposed, not yet handled even in the existing type=0 code:** `section_start` builds its answer-fetch list as `question_node_ids + list(question_to_set.keys())` — both derived purely from `current_node` values in *this section's own* routing. The existing `condition_question_id` test coverage only ever exercises a condition question that's *also* a `current_node` in the same section, so it gets fetched correctly almost incidentally. **Our case is different in kind:** HMRC_14 is never a `current_node` within S8's own routing — it's a case-level answer from a different section entirely. Built this way, its answer never gets fetched, and `_resolve_routing_answer` would silently return an empty string rather than its real value — a silent wrong-route bug, not a loud failure, and one Piece 2's `alternate_condition_id` slot (§3) makes more likely to occur, not less, since every outcome row can now name a second question to fetch, not just the odd row that happens to reuse `condition_question_id` today.

So `load_cache_for_routed_section()` needs its answer-fetch list built from **three** sources, not two: `question_node_ids`, `question_to_set.keys()`, and **every distinct `alternate_condition_id` referenced anywhere in this section's routing** (per §3's field naming) — walked explicitly, not relied on to incidentally overlap.

### 2.2 `load_cache_for_fixed_table_section()` — type=1 only, genuinely separate

Type=1 has no routing at all — one page, all fields at once, no branching — so there's no node-walk to perform. Its question set comes straight from `section.display_question_ids`, a fixed field on `Section` itself. This is why it needs its own function: the *source of truth* is different in kind, not just smaller in scope.

**The problem, with evidence:** `section_table_add` handles both the row-entry GET and the POST, and on **every single call** — for every row added — runs `Question.objects.filter(question_id__in=col_qids)` fresh and rebuilds `ordered_columns`/`column_dicts` from scratch.

**The fix:** fetch once, on first entry to the section's table view for this visit; store in the section-level namespace; both GET and POST paths, for every row added during the visit, read from there instead.

Type=1 has no `condition_question_id` concept, so no equivalent of 2.1's answer-fetch gap — but it should still fetch already-confirmed answers for pre-filling a change journey, if that's wanted for type=1 (not yet reviewed against existing behaviour).

### Common ground, and scope

Both store in a section-level (not row-level) session namespace, separate from the existing row-level `_table_row` namespace that holds per-row answers and `_asked_ids`. Neither requires any change to `_resolve_routing_answer`, `_evaluate_routing`, or the routing-evaluation logic itself (2.1 only — 2.2 has no routing) — they already take `routing_table` as a plain argument, agnostic to where it came from.

Two functions, replacing a handful of call sites that currently duplicate their own fetch logic, mirroring a pattern that already exists correctly for type=0. Not a redesign of Core's session architecture.

**One caveat worth carrying forward:** Django's default session backend is itself database-backed unless a cache-based session engine (e.g. Redis) is configured. "Moved into session" reduces several queries per step to one session-table read per step — real, but not literally zero DB access on the current stack. Worth deciding explicitly whether a cache-based session backend is in scope.

---

## 3. Piece 2: compound-condition routing (two-slot AND)

### The problem

The current `Routing` model supports exactly one condition per row: the current node's own answer, or one other already-answered question's answer (`condition_question_id`) — never both.

This surfaced concretely in the sole-ownership branch of the IHT property design: routing "Sole ownership" onward correctly requires testing **both** "ownership type = Sole ownership" **and** "was the deceased married = Yes/No" together. Not a one-off — every asset class using this shared row template hits the identical problem in its sole-ownership branch, since sole ownership is the one branch with no natural intervening "count" question to serve as a single-condition checkpoint.

### The design — deliberately minimal, not a general boolean engine

An earlier version of this design used a free-text logic string (`"C1 AND C2"`, etc.), parsed and evaluated with the third-party `boolean.py` library, supporting arbitrary AND/OR/NOT/parentheses combinations of any number of numbered conditions. **This has been superseded** by a much smaller design, arrived at by checking what every real case in this project has actually needed:

- **OR is already free.** A `current_node` can have multiple outcome rows, evaluated in order, first match wins — exactly how `Routing` already worked before any of this compound-condition work started. "Go to X if (A and B), else go to Y if (C and D)" is just two ordinary rows, not a within-row OR.
- **NOT is already free.** `"HMRC_46 = Sole AND HMRC_14 <> Yes"` says exactly what a `NOT` operator would say, using only the `<>` comparator already agreed as a needed addition.
- The only genuinely missing primitive, checked against every case this project has produced, is: **test two conditions on one row, both must hold.** Never three, never a within-row OR.

So the fix is two parallel condition "slots" on one `Routing` row, ANDed when both are present — no logic string, no parser, no third-party dependency, no free-text authoring trap for a policy analyst to get wrong. If a real case is ever found needing a third simultaneous condition, that's the trigger to generalise further (e.g. a `RoutingCondition` child table) — not before.

**Final field list** (agreed field names — `_1`/`_2` suffixes throughout for symmetry):

| Field | Role |
|---|---|
| `section` | Which section this rule belongs to |
| `current_node` | The row this rule fires *from* — also, implicitly, slot 1's question |
| `next_node` | Where to go if this rule matches |
| `order_in_section` | Evaluation order among rules sharing a `current_node`; first match wins |
| `comparator_1` | Slot 1's test. `=`/`<>` for a categorical answer, `=`,`<>`,`<`,`<=`,`>`,`>=` for numeric. Null → slot 1 not tested. |
| `test_value_1` | Slot 1's target — literal text or numeric threshold, per `comparator_1`. |
| `alternate_condition_id` | Names slot 2's question — an already-answered question other than `current_node`. Null → slot 2 not tested. |
| `comparator_2` | Slot 2's test, same operator set as `comparator_1`. |
| `test_value_2` | Slot 2's target, same dual role as `test_value_1`. |

`answer_value`/`threshold_value` as two separate fields per slot are retired: a question is either categorical or numeric, never both, so `comparator` alone disambiguates which interpretation `test_value` carries — no need to hold both a literal and a numeric field per slot.

**Evaluation rule**, subsuming every existing routing pattern as a special case rather than needing separate handling:

- Neither `comparator_1` nor `comparator_2` set → unconditional match (today's catch-all/"All other answers" row).
- Only `comparator_1` set → today's ordinary own-answer routing.
- Only `comparator_2` set → today's `condition_question_id`-only routing, current node's own answer ignored.
- Both set → AND both — the new case, and the only one that's actually new.

Every existing routing row, unmodified in behaviour, is representable in this schema (slot 2 simply stays empty) — nothing needs migrating in logic, only in field layout. **One migration step still needed:** every existing row today has `answer_value` populated implicitly as an equality test with no explicit comparator; moving to this schema means setting `comparator_1 = '='` explicitly and moving the value into `test_value_1` — a one-off data migration, not a logic change.

A working prototype exists: **`routing_engine_prototype.py`** (revised to this design — the `boolean.py`-based version and its `C1`/`C2` symbol-naming trap no longer apply and have been removed entirely). `evaluate_outcome` and `resolve_next_node` are pure functions over an assembled `SectionCache` and an answers dict — nothing else. Only `load_section_cache` in the prototype touches the database, and per §4, its job is expected to be absorbed into `load_cache_for_routed_section()` rather than existing as a second loader.

### What's not yet decided

- Whether a categorical question's `comparator_1`/`comparator_2` should be restricted to `=`/`<>` only at the data-entry/validation layer, or left open to the full operator set with numeric comparators simply never matching (returning `False`) against non-numeric answers — a validation-strictness question, not a logic question.
- Admin-tool UX for authoring a two-slot condition safely — likely just two straightforward dropdown-and-value pairs per outcome row, given there's no logic string to construct; simpler than the design this replaces.

---

## 4. How the two pieces meet: one boundary, deliberately kept narrow

The prototype's `load_section_cache` was always a stand-in for `load_cache_for_routed_section()` (§2.1). Once Piece 1 is done, the compound-condition routing code needs no rework — it already only consumes an assembled structure and an answers dict. The only change is that `load_section_cache` is deleted, its job absorbed into `load_cache_for_routed_section()`, including the corrected three-source answer-fetch logic.

**Design discipline worth stating explicitly:** keep a sharp, named boundary between (a) the function(s) that populate the in-memory/session structure at journey-start and read it back per step, and (b) the routing-evaluation logic that consumes it. Only (a) should know whether it's talking to a Django session, Redis, or eventually Salesforce Platform Cache. (b) — `_resolve_routing_answer`, `_evaluate_routing`, and the compound-condition equivalents — stays entirely ignorant of the storage backend. This is what makes the eventual Salesforce port "rewrite the boundary functions," not "rewrite the routing logic."

---

## 5. Why Salesforce is the reference point

Flow won't hold up at HMRC's scale and concurrency, per Salesforce-architect advice — it executes as part of the transactional record-save lifecycle with per-transaction governor-limit overhead. The alternative is **Salesforce Platform Cache** — a genuine memory-based caching layer, distinct from the database, with Session Cache (per-journey, private) and Org Cache (shared, static) partitions. This is why the prototype and Piece 1 are both designed around "load once, evaluate in memory, write once" now, even on Django: it's meant as a faithful analogue of the target, not just a Django optimisation.

On whether the routing logic itself belongs in hand-written Apex or in Salesforce's declarative rules tooling (Business Rules Engine/Expression Sets): current working assumption, pending the Salesforce architect's confirmation, is that a few lines of Apex operating purely on cached data is the right call. This is reinforced by the two-slot design in §3 landing on something simpler than originally expected — two comparator/value pairs, ANDed, is a trivial translation into Apex (a couple of `if` statements), with no parser, no grammar, and no library gap to work around at all. There's correspondingly less reason to reach for a separate rules-engine service call than there was under the earlier logic-string design.

---

## 6. Suggested next steps, in order

1. Scope and implement Piece 1 (§2) — `load_cache_for_routed_section()` (§2.1, including the corrected cross-section answer-fetch logic) and `load_cache_for_fixed_table_section()` (§2.2). More mechanical, unblocks nothing else, worth doing first.
2. Extend the `Routing` model with the fields in §3 (`comparator_1`/`test_value_1`/`alternate_condition_id`/`comparator_2`/`test_value_2`), and settle the validation-strictness question noted in §3.
3. **Migrate every existing `Routing` row into the new field layout** before the new fields go live: for each row, set `comparator_1 = '='` explicitly and move its current `answer_value` into `test_value_1`; leave `alternate_condition_id`/`comparator_2`/`test_value_2` null except where a row currently uses `condition_question_id`, which should map onto `alternate_condition_id`/`comparator_2`/`test_value_2` in the same way. This is a data migration against a live table underpinning every existing section's routing, not just a schema change — worth its own test pass (confirm every migrated row routes identically before and after) rather than assumed safe because the logic is "equivalent."
4. Confirm with the Salesforce architect whether plain Apex (§5) is the right call — the two-slot design makes this close to a formality rather than an open question, but worth confirming before treating it as settled.
5. Keep the boundary from §4 explicit in whatever code is written, so both pieces remain independently portable to Salesforce.
6. Ensure whatever this produces still satisfies Paper 5 §3's contract — in particular, the answer-format requirement (§3.4) — before it's treated as ready to sit behind any homepage button.
