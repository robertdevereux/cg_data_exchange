# Annex A2: The Core Platform — Technical Architecture

*Companion to Paper 1: The Case for Core. Written for digital and data architects who need to assess how the platform works technically, in enough detail to plan a build against it. A plain-language account for policy and operational readers is in Annex A1.*

**Scope note:** this document describes the platform as needed to support HMRC's own regimes. It does not depend on, or require agreement to, any cross-department capability. The platform's architecture extends cleanly to multi-department operation should that ever be wanted; that extension is described in outline in a short appendix at the end, but is not part of this proposal.

---

## The core idea

Looking closely at HMRC's own forms, almost everything they ask reduces to three logically different kinds of question set, and every form is some combination of the three:

| # | Name | What it is | Django `section_type` |
|---|---|---|---|
| 1 | **Standard** | One question (or closely related group of questions) per page, with routing between them that can depend on earlier answers | `0` |
| 2 | **Table** | A repeating record with a fixed set of columns, no branching within the record | `1` |
| 3 | **Table with routing** | A repeating record where the follow-up questions for a given record depend on what's already been answered for that same record | `2` |

The platform provides one well-tested engine for each of these three types. A **Section** is the unit that has a type; every question HMRC needs to ask lives inside some Section, and every Section is exactly one of these three types — never a mix.

A logical subject — property, bank accounts, a Duty Deferment Authorisation application — is not itself a section. It's an **ordered list of sections**, each one of a type suited to the part of the subject it covers: a standard section for "did the deceased own any property," a conditional table for the property records themselves, perhaps another standard section for a closing declaration. Breaking a subject into its component sections this way is the first and most basic act of navigation design — before any thought is given to tailoring, action buttons, or how a home page presents things to the citizen.

The platform's job stops there. It does not decide which sections a service calls, in what order, or what happens when they're done — that's the service's own home page. The platform can be called with **any ordered list of any defined sections**, processes them, and returns control once that list is complete. A service can call it once with a whole subject's worth of sections, or call it repeatedly, one action button at a time, inspecting answers between calls to decide what to call next — the mechanics described in this document are identical either way; only the calling pattern differs, and that's the service's choice, not the platform's.

The rest of this document takes each of the three section types in turn, using the same four headings throughout: what it does in plain terms; the data that configures it; the transient session state it needs while a citizen is mid-journey; and the specific functions that implement it.

---

## Part One: Standard sections (`section_type = 0`)

### In plain English

A standard section asks a citizen one question at a time. Some questions depend on earlier answers — only someone who says "yes" to "did the deceased leave a will" is then asked to attach a copy of it. At the end, the citizen sees everything they've just said on one page and can correct anything before confirming. If they do correct an earlier answer that affects the route taken, everything downstream of that answer is re-asked, since the right next question may have changed.

This is the section type behind the great majority of HMRC's questions, and the one every other type builds on.

### Configuration as data

**Question.** Every question asked anywhere on the platform is a single record: its text, its type (radio, checkbox, text, number, date, or a compound type[^1]), hint text, and any validation rules. Questions are defined once and reused across regimes. A small, deliberately bounded set — names, addresses, contact details — is defined at platform level and shared; everything else is owned by the regime or service that defined it, governed by that team without central clearance.

**Question Sets.** Where several independent questions belong together on one page — telephone number, email, preferred contact method — a Question Set groups them without changing how they're stored: each member question still has its own identifier and its own Answer record. A Set appears in the routing table as a single node and is treated exactly like a Question node by the routing engine.

**Routing.** The sequence of questions within a section is not fixed in code — it's a table of records, each one saying: at this node, given this answer, go to this next node. A special end-of-section marker sends the citizen to the confirmation page. Branching is supported for radio/checkbox answers (grouped by option) and for numeric thresholds (`=`, `<`, `<=`, `>`, `>=`); free-text and date answers can't be branched on, since they have no enumerable or comparable values.

**Answer.** Every confirmed answer is a record capturing the Question, the Case, the User (the citizen), the Actor (whoever actually submitted it — the citizen or an intermediary), the value, and the timestamp. Amending an answer never overwrites it: the old record moves to Answer History, and a fresh record is created. Every answer's full provenance — who gave it, on whose behalf, and its complete amendment history — is permanently reconstructable.

### Session data

While a citizen is mid-journey through a section — before anything is confirmed — the platform tracks, in session state, which questions have actually been reached so far on the route taken: an ordered list of node IDs, `asked_ids`. This is what makes backtracking work correctly: if a citizen returns to an earlier question already on this list and changes their answer, the list is truncated back to that point, because everything asked after it belonged to a route that may no longer apply. The "Back" link on any question page is computed directly from this list — the previous entry in `asked_ids`, not simply "the page the browser came from."

`asked_ids` is a session-level concept here, discarded once the section is confirmed and its answers committed. Part Three reuses the same idea in a more permanent form — kept alongside the stored data itself, not just in-session — for a different purpose: pruning a conditional table row, not just supporting backtracking within one journey.

### Supporting functions

`section_start` → `section_question` / `_process_answer` → `section_review` / `_commit_section_answers` → `section_confirm` → `section_done` — with `section_set_page` / `_process_set_answer` handling Question Set pages within that same flow. Two routing helpers, `_resolve_routing_answer` and `_evaluate_routing`, do the actual next-node computation and are shared by every section type that involves routing (see Part Three).

`section_start` also detects, on re-entry, whether the citizen already has confirmed answers for this section and sends them to the review page rather than the first question — the same underlying "replay the route against known answers" logic that `asked_ids` supports live, in-session.

---

## Part Two: Table sections (`section_type = 1`)

### In plain English

A table section asks for the same fixed set of fields, once per record — every executor's name and contact details, say. There's no branching within a record: every field is asked for every row, in the same order, every time. The citizen sees a landing page listing how many records exist so far, with the ability to add, view, amend, or delete one, and to say when the table is complete — since only the citizen knows how many records are actually needed.

Because there's no branching within a record, a table section needs neither a Routing object nor a check-your-answers confirmation page. Everything is captured in a single form per record. This is a deliberately simpler mechanism than Part One's, not a variant of it.

### Configuration as data

**AnswerTable.** Where a standard section stores one Answer per question, a table section stores one `AnswerTable` record per section per case, holding a JSON list — one dict per row the citizen has added, each dict keyed by the question IDs that make up a row.

**`display_question_ids`.** A section-level field listing, in order, which questions make up each row. For a table section, this is the complete definition of the add-form: every question in the list appears, in that order, on a single page, and the same list defines the landing page's column headings.

**`totals_question_ids`.** An optional section-level field naming numeric questions to be totalled at the foot of the table — applies to both table types.

There is no Routing object involved anywhere in a type-1 section — there is nothing for it to branch on within a row.

### Session data

None beyond the ordinary form-submission state of a single page. Because a row is captured in one page with no branching, there is no in-progress journey to track between questions, and so no equivalent of Part One's `asked_ids`.

### Supporting functions

`section_table` (landing page) → `section_table_add` (single-page form covering every column) → `section_table_delete` (remove a row by index) → `section_confirm_table` (snapshot to `AnswerTableHistory`, mark complete) → `section_done` (shared with standard sections — the same function closes out every section type). `section_table_delete`, `section_confirm_table` and `section_done` are not reimplemented for this type; they are the same functions Part Three's conditional tables use.

---

## Part Three: Conditional table sections (`section_type = 2`)

### In plain English

A conditional table looks like a table section from the landing page — records can be added, viewed, amended, deleted — but each record's own follow-up questions depend on what's already been said about that same record. IHT405's property section is the clearest example: record a lease and you're asked lease length; record damage and you're asked about insurance cover. Two properties on the same table can end up answering entirely different follow-up questions, because each one's route depends only on its own earlier answers.

The right way to think about this is: **a conditional table's row is a standard section's routing journey, run once per row.** Nothing new needs to be invented for the branching itself — Part One's Question and Routing objects are reused exactly as they are. What's new is only what's needed to run that journey once per row rather than once per section, and to handle the fact that different rows may take different routes.

### Configuration as data

The row journey uses the same Question and Routing configuration as Part One — nothing new is defined for it. The one addition is how `display_question_ids` is interpreted: unlike a flat table, it does *not* define the full row journey here — routing does that. It instead declares which of the routed questions appear as summary columns on the landing page. Anything a row answered that isn't in this list is still stored and still retrievable, just not shown on the summary — reached instead through a per-row "other details" link.

Rows are stored in the same `AnswerTable` object Part Two uses, but sparsely: because different rows can take different routes, a row's stored dict contains only the questions actually reached on the path that row took. A row that never triggered the lease-length branch simply has no key for it — not a null, not a blank, no key at all. The landing page's summary table shows `—` for any column absent from a given row.

### Session data

As in Part One, a live `asked_ids` list tracks which nodes have been reached on the current row's journey — but here it persists as part of the row's own working data, not just as ordinary journey-navigation state, because it has a second job: pruning. When a citizen amends a row and, partway through, gives a different answer that sends them down a different branch than before, any answers already recorded for the *old* branch must not survive into the amended row. At commit time, the row is pruned to only the node IDs actually present in `asked_ids` for the path just taken; anything left over from a previous, now-abandoned branch is discarded. This is the one piece of logic that has no equivalent in either of the other two section types, because it's the only place where the same record can legitimately take a different route on a second pass.

This in-progress row state — the answers gathered so far, plus its `asked_ids` list — lives in its own session namespace (`_table_row[section_id]`), isolated from the section-level session state a standard section uses. This is what allows a citizen to be partway through adding one row without disturbing any other section's progress.

### Supporting functions

`section_table_routed_add` (start a new row journey) / `section_table_routed_change` (start an amend-row journey, pre-populated from the saved row — reconstructing its `asked_ids` by replaying routing against the saved answers) → `section_table_routed_question` (the per-node workhorse, handling both Question and Question Set nodes via the same `_resolve_routing_answer` / `_evaluate_routing` helpers Part One uses) → `_commit_table_row` (write the pruned row to `AnswerTable`, appending for a new row or replacing at index for an amendment) → `section_table_row_detail` (read-only view of any answers not shown as summary columns). `section_table_delete` and `section_confirm_table` are the same functions Part Two uses.

---

## Permissions and Delegation

These apply identically across all three section types — permission is enforced at the point of navigating to a Section, before processing of any type begins, so the mechanism described here doesn't vary by what kind of section is being protected.

### The citizen as access controller

A citizen who wants a solicitor to complete a probate section on their behalf grants access directly, at section level, to the named individual. The platform records the grant, enforces it in the navigation layer, and maintains the full audit trail.

### The permission model

The model separates the User (the citizen whose data is at stake) from the Actor (whoever is actually completing the interaction — the User themselves, or a consented intermediary). A Permission record grants a named Actor access to one or more named Sections, on behalf of a named User. Grants are explicit; there are no implicit or inherited permissions. The Answer object records both User and Actor for every confirmed answer, so the audit trail always shows who actually submitted it, not just whose data it concerns.

### The Section as permission boundary

Permission is granted at Section level, not regime level — a land agent can be given access to the land holdings section without seeing the bank account or investment sections. This works because the permission check happens in navigation, before any questions are shown: an Actor without access to a Section never sees its questions, and its Answer records are never in scope for them.

### Delegation

A Permission record may include delegation rights, letting the Actor pass their grant — or a subset of it — to another named individual. An Actor can only delegate Sections they themselves hold, and only if their own grant includes delegation rights; they can choose whether to pass delegation rights on or withhold them, but can never grant rights they don't hold themselves. Every delegation creates its own Permission record, so the full chain from the citizen's original grant to the most junior delegate is recorded and auditable, and can be revoked and re-granted without breaking that chain.

The model as specified is for named individuals as both grantors and grantees; organisational grants (a citizen granting access to a firm, which then manages internal allocation) are a natural extension, deferred to a later phase.

---

## The Complete Data Model

| **Object** | **Purpose** | **Key fields** | **Used by** |
|---|---|---|---|
| Regime | Configuration record for a single HMRC service | Name, identifier | Container for a service's Schedules/Sections |
| Schedule | Optional named grouping of Sections within a Regime | Name, display order | Used only where a regime's size warrants intermediate grouping |
| Section | The unit with a type — Standard, Table, or Table with routing | Name, `section_type` (0/1/2), display order, `display_question_ids`, `totals_question_ids`, `show_confirmation` | All three parts above |
| Question | A single question, defined once, reusable across regimes | Text, type, hint, options, validation | Parts One and Three (routing); Part Two (flat form) |
| Question Set | A named grouping of Questions on one page | Set identifier, title | Parts One and Three |
| Question Set Member | Membership/order of a Question within a Set | Set, Question, order, required | — |
| Routing | Conditional logic: node, condition, next node | Section, current node, answer condition, next node | Parts One and Three only — **not used by Part Two** |
| Answer | A citizen's confirmed single response, with provenance | Question, Case, User, Actor, value, timestamp | Part One |
| AnswerTable | A section's full set of rows, one JSON list per case | Section, Case, list of row dicts | Parts Two and Three |
| Permission | A grant of Section access from User to Actor | User, Actor, Sections, delegation rights, granted-by | All three parts, via navigation |
| Case | A citizen's instance of a regime | Case identifier, User, Regime, status | All three parts |

### Regime configuration tooling

Regimes, Schedules, Sections, Questions, Sets and Routing rows are all data, not code — so building or amending a regime is, in principle, a data operation. The platform provides a staff-only configuration suite making this true in practice, not just in principle: dedicated management screens for Questions, Sets, Sections (including a visual, point-and-click routing editor — the section's complete question flow shown as a colour-coded tree, directly editable), Schedules, and Regimes. Questions and Sets are shared assets: editing one propagates everywhere it's used, and deletion of an in-use question or set is blocked; a further governed-deletion clearance step for shared assets is identified as needed for production but deferred to a later phase. In the current implementation, questions and sets can be freely created and edited; deletion is not yet available through the tooling.

---

## Non-Functional Requirements

**Scale.** The platform must support large volumes of concurrent users across multiple regimes simultaneously, without degradation in response time or data integrity.

**Data isolation.** Answers belonging to one regime must be inaccessible to another regime except where the citizen has explicitly consented to cross-regime sharing, enforced architecturally rather than by convention.

**Audit.** Every answer, amendment, permission grant and delegation must be permanently and tamper-evidently recorded, reconstructable at any point in time: who provided it, on whose behalf, in which regime, and its full amendment history.

**Accessibility.** Every citizen-facing interaction must meet WCAG 2.1 AA as a minimum, as a structural property of the presentation layer, not an add-on.

**Performance.** The transition between questions must feel immediate — the routing logic determining the next question must be available to the presentation layer without a round-trip to a remote data store on every question transition.

---

## Appendix 1: The service navigation contract

*Detail for anyone actually wiring a service's home page to the platform. Not required reading for assessing the case in Paper 1.*

The platform does not dictate how a service's home page is built, what it calls when, or in what order — that is the service's own design decision, and the action-button pattern set out for Inheritance Tax in Paper 3 is one example of it. What the platform requires in return is a well-defined, minimal contract:

- **Session values.** Before calling into any section, the service must have written four values into the session: the User, the Actor, the Regime, and the Case identifier (obtained only through the platform's own case-management interface, never constructed independently).
- **The call interface.** A single entry point accepts an ordered list of sections (and/or schedules), establishes the session contract, bootstraps section-status records, and returns the correct entry URL for wherever the citizen currently is in that list — starting fresh, resuming, or amending. The service redirects to that URL; the platform takes over from there and returns control once the list is exhausted.
- **Breadcrumbs.** The platform's pages need navigational context (titles, back links, breadcrumb trails) that it cannot construct itself, since it doesn't know the service's URL structure. The service writes an ordered label/URL breadcrumb trail into the session before handing off; the platform appends its own labels as the citizen progresses.

A service can call the platform once, with everything a subject needs, and get the citizen back at the end — or call it repeatedly, section by section or list by list, inspecting answers between calls to decide what to call next. Both are the same contract, used differently; the platform does not need to know or care which pattern a given service has chosen.

Reference navigation patterns — working, adaptable starting points for the common cases (direct-to-section, section task list, schedule-then-section menu) — are provided as illustrative code that services own and modify freely; they are not part of the platform package itself.

Where a service needs an interaction the platform's three section types genuinely can't support, it remains free to build that interaction entirely in its own code and call it from its home page alongside conventional sections — at the cost that anything not written back to the platform's own Answer/AnswerTable objects using the correct User/Actor/Regime/Case keys falls outside the audit trail and pre-population vocabulary described above.

## Appendix 2: Future extension — multi-department operation

*Not part of this proposal. Included for completeness, since the architecture above was designed to support this extension without rework, should HMRC wish to pursue it later with other departments.*

The same Question and Routing objects, the same Section/navigation separation, and the same Permission model extend to a multi-department setting through a three-tier implementation: a central service holding only the shared Question/QuestionSet vocabulary and a department registry (no citizen data); a managed software package containing the routing engine and permission model, installed identically by each department; and each department's own installation, holding its own Regimes, Sections, Cases and Answers in full isolation, with citizen data leaving an installation only in direct response to a citizen-consented, peer-to-peer request from another department.

Under this extension, pre-population could operate across departments as well as within HMRC's own regimes, with an explicit, session-scoped consent step before any answer from another department is offered as a suggestion. A new department would join by registering with the central service, installing the managed package, and configuring its own regimes and Layer 1 — none of which requires changes to the platform package or to any existing department's installation. This extension is technically available should it ever be wanted; it is not assumed, requested, or required by anything else in this document.

---

[^1]: A small further category — **compound questions** — covers answers that are intrinsically a single unit and can't be meaningfully split into separate questions: the value of gifts made in each of the last seven years, or a vehicle's make, weight and axle count. Rather than separate Question and Answer records per component, a compound question stores its whole answer as one JSON record against a single identifier, with its components defined once (via an admin wizard) and rendered by a single generic template. Two component structures — name and address — are stable and widely reused enough to be defined once at platform level as named compound types, available for any regime to instantiate.
