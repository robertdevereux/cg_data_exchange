# Parked thoughts: question labelling, routing display, and routing validation

3 August 2026. Captured as a standalone note, not added to the Backlog — these
are half-formed ideas worth returning to, not committed work items.

---

## 1. Question ID labelling scheme

Raised: as the platform grows toward thousands of questions (HMRC alone), the
flat `HMRC_n` numbering gives no way to tell, from the ID alone, whether a
question is shared platform-wide, shared within a regime, or specific to one
section.

Proposed direction (not adopted — you went off the idea mid-conversation):
a hierarchical scheme, e.g. `HMRC_Q_n` for dept-wide cross-regime questions
(identity/case facts — name, DOB, NINO), `HMRC_IHT_OWN_n` for questions shared
across sections within IHT (the ownership fork, spouse-destination question —
using a short mnemonic like `OWN` rather than a single letter, since a single
letter like `P` reads ambiguously — could mean "Property" when the group
isn't property-specific).

Also flagged, unresolved: whether `S8`'s numbering is arbitrary/internal or
mirrors HMRC's actual IHT400 form Schedule numbering. If the latter, that's a
stable external anchor worth preserving deliberately rather than treating as
an internal detail.

Scale of the migration if ever done: touches every `Question.question_id`,
all four string-matched `Routing` fields (`current_node`, `next_node`,
`condition_question_id`, `alternate_condition_id` — plain `CharField`s, not
FK-enforced, so a missed rename fails silently rather than erroring),
`AnswerTable` rows, any hardcoded ID literals in Python, and every design doc.
Bigger and more failure-prone than the Phase 4 migration if picked up later —
worth doing early if done at all, and worth its own dedicated session with the
same backup/audit/equivalence-test discipline as Phase 4.

**Status: parked. Not decided either way.**

---

## 2. Auto-generating the routing display doc from live data

The "clean doc" format used earlier this session (flat list, one heading per
node, `##`-per-node, downstream convergence nodes referenced by ID rather than
reprinted) was produced by hand. Question raised: could this be generated
automatically from the live `Routing` table, and would an automated version
still look like what we've got?

Depth-first traversal of a graph is not unique in general — it depends on (a)
starting node, (b) the order in which a node's outgoing edges are tried, (c)
how repeat-visited nodes are handled. Our format already resolves (a) via
`first_node` and (c) via "show once, reference by ID thereafter, no
reprinting." (b) was being resolved by `order_in_section` — see §3 below for
why that may not need to survive.

Three things a generator needs to handle explicitly, not inherit for free:

- **Orphaned nodes** — an edit that removes the only path into a node leaves
  its routing rows live but unreachable, silently. Needs an explicit
  "unreachable from first_node" warning, not silent omission from the doc.
- **Cycles** — an edit that accidentally routes a later node back to an
  earlier one needs a hard-fail check independent of the doc generator itself
  (this is an engine correctness issue, not a documentation nicety — a live
  cycle is an infinite-loop risk).
- **Discovery-order churn** — because heading order depends on which branch
  reaches a shared node first, an unrelated edit elsewhere can reshuffle
  heading order in the regenerated doc even when that node's own content
  hasn't changed. For a wizard-style review tool, this means the useful
  output is a **diff** (rows added/changed/removed) rather than two full
  regenerations side by side — the reshuffling would otherwise bury real
  changes in noise.

**Status: the format itself is trustworthy; a naive "just re-run DFS"
implementation is not, without the three guards above.**

---

## 3. Dropping `order_in_section` in favour of automatic ordering

Raised: rather than requiring a human-assigned `order_in_section` on every
row (as today, and as used throughout this session's HMRC_S8 rebuild), could
the two things it currently does be derived automatically?

- **Evaluation order** (which row the engine tries first) — proposed:
  derive from *specificity* (rows testing both slots evaluated before rows
  testing one slot, before rows testing none), rather than a manually
  authored number. This is a natural extension of a rule the engine already
  half-implements (the true-unconditional bucket — both slots null — is
  already always deferred to last, regardless of position).
- **Display order** (which node's heading appears first in the flat doc) —
  proposed: any stable deterministic tiebreak (row `id`, or alphabetical by
  `test_value_1`) — purely cosmetic, doesn't need manual authoring either.

**Consequence this surfaces, not removes:** once there's no manually-assigned
number to (accidentally or deliberately) break ties, two rows at the *same*
specificity tier whose conditions could both match one real answer become a
genuine, undetected ambiguity rather than something a human happened to
order correctly. This folds into §4 below — it becomes a validation
requirement rather than an ordering convention.

**Status: a real, worthwhile change to `_evaluate_routing` and the `Routing`
model (drop `order_in_section`, add specificity-based sort, add the tie
validation from §4) — not adopted, needs its own dedicated, carefully-tested
session, same discipline as Phase 4.**

---

## 4. Exclusivity/completeness checker for routing conditions

Core idea: for any node's set of outgoing routing rows, check that every
possible answer to the current question routes *somewhere* (completeness) and
routes to *exactly one* place, not zero and not more than one (exclusivity/
mutual exclusion) — a partition check on the space of possible answers.

**This would have caught, immediately, the bug found by hand earlier this
session:** `HMRC_55`'s routing tested against `'Yes'`/`'No'` while its real
options were `'All of it'`/`'Some of it'`/`'None of it'` — a pure
completeness failure (every real answer matched zero rows). A checker like
this is worth treating as a general audit tool to run against every
currently-live section, not just a safeguard for future edits.

The check differs by field type — not one algorithm:

- **Radio (finite options):** trivial — enumerate every option, confirm each
  matches exactly one row.
- **Numeric (comparator-based):** domain is an (effectively unbounded)
  range — check via interval coverage (no gaps, no overlaps), not
  enumeration. A distinct piece of logic from the radio case.
- **Compound rows (both slots set):** radio×radio is a finite Cartesian
  product, brute-forceable. Radio×numeric (the `HMRC_50`+`HMRC_48` case
  built this session) decomposes into one interval check per radio value.
  Numeric×numeric would need true 2D interval overlap — doesn't exist
  anywhere in the live design yet, flag for manual review if it ever arises
  rather than pre-building the general case.
- **Checklist/checkbox:** see §5 — not a simple extension of the radio case.

**Requires joining `Routing` against `Question.question_type`/`options`**,
not just introspecting the routing table alone — the domain being checked
lives on the Question record, for both the current node and (for compound
rows) whatever `alternate_condition_id` points to.

**Stated assumption worth keeping explicit:** slot 2's domain assumes the
alt-condition question has always already been answered by the time the
current node is evaluated (true for `HMRC_14` — asked case-level, before any
section that references it). If that assumption were ever violated,
"unanswered" becomes a real member of the domain needing its own covering
rule, not an edge case to wave away.

**Status: strong candidate for a real audit tool, not adopted or built.**

---

## 5. Checkbox conditions — partition rule vs multi-select semantics

Checklist/checkbox questions don't extend the radio case cleanly, because
`_matches`'s existing semantics are set-*intersection*: an answer selecting
several options can legitimately satisfy more than one row's condition at
once. Combined with "first match wins," this reintroduces exactly the
row-order-dependent non-determinism the completeness/exclusivity checker is
meant to eliminate.

Proposed refinement (your suggestion, in place of excluding checkbox
entirely): require the *options themselves* to be partitioned into disjoint
groups when used as a routing condition (e.g. "1,2,3 → route A; 4 → route B;
5–10 → route C"), making the check structurally identical to the radio case.

**This resolves the completeness/exclusivity check, but doesn't by itself
resolve cross-group answers** — someone can still validly select an option
from group A *and* group C in one answer, and the row-order problem returns
at that point. Two genuinely different scenarios were identified, needing
different fixes:

1. **Genuinely independent multi-select** (e.g. `HMRC_11` — "did the deceased
   do any of the following?" — several unrelated things can all be true at
   once, each with its own downstream consequence). Here, single-route
   first-match dispatch is the wrong model regardless of partitioning — this
   points back toward excluding checkbox from single-route conditions
   entirely, just for a more specific reason than originally raised.
2. **Checkbox-as-grouped-radio** — the UI widget is checkbox, but the
   question is only ever meant to have one group selected. If this is the
   real intent, the fix is a validation rule on the *question* itself
   (reject cross-group selections at answer time) — which then makes the
   downstream routing check trivial and exactly analogous to radio.

**Status: unresolved which of these two shapes matches any real intended
checkbox-as-routing-condition case — no live example currently uses checkbox
as a routing condition, so this is speculative until/unless one is proposed.**
