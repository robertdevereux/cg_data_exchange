# Annex 3B: The IHT Design — Technical Detail

*Companion to Paper 3: Delivering Inheritance Tax via Core, and to Annex 3A's plain-language account. Written for digital and data architects and for policy analysts configuring the routing itself. Uses the section-type vocabulary and object names established in Annex A2 throughout — this document adds nothing to the platform's own mechanics; it only configures them for Inheritance Tax.*

**Supersession note:** this document consolidates and supersedes the ownership/valuation and routing-mechanics material previously held in `260726_ownership_marital_template-4.md`, and the RNRB, transferred-allowances, and asset-class configuration material previously held in `260628_iht-journey-architecture.md`. Both source documents can be retired once this annex is in place.

**Revision note (this version):** Part 2 replaces an earlier design in which the marital-status branch (formerly "3a") was a single binary question, asked identically regardless of ownership type. Working through the interplay in detail established that the mechanism by which an asset passes to a spouse differs fundamentally by ownership type — a distinction the binary treatment didn't capture, and which produces wrong or unanswerable questions for tenants-in-common and multi-owner joint tenancy cases. Part 2 is rewritten accordingly. Part 7 is new, describing a home-page estate progress summary made possible by data this design already collects. Full, build-level question sequences for all three ownership branches are set out in the companion reference document `IHT_ownership_branch_questions.md`; this annex summarises them at the level needed for routing design.

---

## 1. The generic asset row template

Every asset class with an ownership or valuation dimension — property, bank and savings accounts, listed and unlisted shares, business and partnership interests, and (in reduced form) chattels such as jewellery or vehicles — is captured in a **Table with routing** section (`section_type = 2`, per Annex A2 Part Three). Each row is one asset instance. The row's stored data is sparse, per Annex A2: only the questions actually reached on that row's path are present.

### 1.1 Row shape

| Step | Question | Notes |
|---|---|---|
| 1 | Asset identification (address / description / account details / executor reference) | Wording is asset-specific |
| 2 | **Value**: "What is the open market value of the whole [asset]?" | Always the **whole** asset — see 1.2 |
| 3 | **Ownership type**: "How was this asset owned?" — sole / joint tenants / tenants in common | Neutral wording ("this asset"), reusable across classes as a shared platform Question |
| 3a+ | **Ownership follow-ups and marital-status branch** (first-death cases only, where applicable) | Genuinely different by ownership type, not a single shared step — see Part 2 |
| 5 | **Valuation evidence**: "Is this value supported by a written professional valuation?" | If yes: upload prompt, whole-asset value expected, passive flag if a discount has already been applied by the valuer. If no: asset-specific substitute evidence questions (see 1.4) |

Value is deliberately asked before ownership type, not after — identification, then value, then ownership, is the order most executors find natural to answer in, and it also means the value the ownership-fork arithmetic operates on (Part 2.4) is already on record by the time the fork is reached. The ownership fork (step 3/3a+) and the valuation-evidence fork (step 5) are independent branches on the same row, sequenced so all ownership questions complete as one block before valuation-evidence questions begin — keeping the row's routing tree legible rather than interleaving two unrelated forks.

### 1.2 The full-value principle

The value captured at step 2, and any uploaded valuation, is always the **whole asset's** open market value — never a pre-discounted or share-only figure. This is a reasonable requirement to place on valuers as well as executors: a professional (e.g. RICS Red Book) valuation is normally instructed and reported on a whole-asset, open-market basis; a discount for a partial interest is a specialist adjustment applied *to* that value, not a separate valuation exercise. Executors are never asked to calculate a discounted or proportionate value themselves — the engine applies the ownership share and, where applicable, the tenants-in-common partial-interest discount (typically 10–15% for residential property; the figure may vary by asset class).

A passive, non-routing safeguard is captured at upload: whether the valuation already includes a stated discount for the deceased's share. This doesn't change the question flow, but flags for caseworker review the case where the engine would otherwise reapply its own discount on top of one the valuer has already applied.

### 1.3 Shared Question Set governance

Step 3's ownership-type Question is defined once as a shared platform Question, worded neutrally ("this asset," not "this property"), and reused across every asset class's Table with routing section. Because `AnswerTable` is keyed by `(user, actor, regime, case, section)`, not by question, reusing the same Question definition across asset classes carries no risk of answers conflating between asset classes: each asset class's section has its own `AnswerTable` row, entirely separate from any other's. The three ownership-specific follow-up sequences that step 3 forks into (Part 2.4) are themselves shared across asset classes on the same basis, wherever the asset-class configuration register (Part 6) enables the relevant depth of fork.

Asset-specific guidance that would be misleading shown generically (for example, the bank-account-specific note that someone named on an account "for convenience" doesn't automatically acquire a beneficial interest) is attached only where relevant — as a departmental guidance override or a separate class-specific hint — rather than folded into the shared Question itself.

### 1.4 What varies by asset class

Two things are configured per asset class, not assumed generic:

- **Valuation-evidence substitutes (step 5, no-valuation branch).** Asset-specific by nature: lease length, damage, and special factors for property; turnover, accounts, or BPR-claim status for business interests; an insurance-schedule value or de minimis threshold for chattels; a trade-guide lookup for vehicles. Some classes may not need this fork at all (vehicles, low-value chattels) — a legitimate configuration choice, not an oversight.
- **Depth of the ownership fork.** Tenants-in-common with an evidenced unequal share is realistic for property, shares, and business interests; rarely worth modelling for vehicles or personal chattels, where sole/joint is normally sufficient.

---

## 2. Marital status and ownership: three branch-specific treatments

### 2.1 Qa and Qb

Two yes/no questions, asked once per case (not per asset, not per row), establish marital status and are stored at case level in the basic `Answer` model — never written into any asset row:

- **Qa**: was the deceased married at the time of death? "Yes" signals a possible first death.
- **Qb**: had the deceased previously been married, where that marriage ended in the death of the spouse? "Yes" signals second death, and gates the transferred-allowances section (Part 4).

### 2.2 Three estate concepts, per asset

Any given asset's value can be described in three distinct ways, and the row template must keep them distinct rather than conflating them:

1. **The grant/probate estate** — assets that require a Grant of Probate to be administered. Sole-owned and tenants-in-common shares require a grant. Joint-tenancy shares do not — they pass by survivorship, outside the grant entirely, even though HMRC still needs their value reported.
2. **The gross estate for IHT reporting** — the total value HMRC needs reported, including everything the deceased had any share in, regardless of exemption and regardless of whether a grant was needed. This is the figure that feeds RNRB tapering (Part 3).
3. **The taxable (chargeable) estate** — the value remaining after exemptions and reliefs, on which tax is actually calculated. Spouse exemption removes spouse-bound value from this figure entirely, with no cap and no threshold.

A single asset can contribute differently to all three — a jointly-owned house held by the deceased and their spouse alone contributes a divided share to the gross estate, £0 to the taxable estate, and nothing to the probate estate in the narrow administrative sense, even though HMRC still needs the share reported. These three figures are what the row template (and, downstream, the estate progress summary in Part 7) must each be able to produce per row, per asset class, and in aggregate.

### 2.3 Ownership determines the mechanism of passing, not the destination

Ownership type does not, by itself, tell you who inherits an asset. It tells you **how** the destination is determined, and the two mechanisms are different enough that they cannot share a question:

- **Sole ownership** and **tenants in common**: the deceased's share falls into the estate and passes under the **will**, or under the **intestacy rules** if there is no will. The destination is a fact the executor must report, independent of ownership type.
- **Joint tenants**: the deceased's share passes automatically by the **right of survivorship** to the other joint owner(s), overriding the will for that asset. The destination is not a separate fact to ask about — it follows directly from who the other joint owner(s) were.

This is the reason the previous single, binary marital-status question ("does the deceased's share pass entirely to the spouse?") is replaced below by two structurally different treatments: an asked, three-way fact for sole and tenants-in-common rows, and a derived fact for joint-tenancy rows.

### 2.4 The three branches

Full question-by-question sequences are in the companion reference document. In routing-design summary:

**Sole ownership.** Deceased's share = 100% of the whole-asset value (Q2); contributes to the grant/probate estate. Where Qa = Yes, a direct three-way question is asked: does the share pass **entirely**, **partly**, or **not at all** to the spouse, under the will or intestacy?

- Entirely → row closes at END. No valuation-evidence step.
- Not at all → full share value proceeds to step 5.
- Partly → a follow-up captures the value or proportion passing to the spouse; the spouse-bound portion is exempt and excluded from step 5; the remainder proceeds to step 5.

No partial-interest discount ever applies — a sole share is not a divisible legal interest.

**Joint tenants.** Ownership follow-up captures N (total joint owners, including the deceased); deceased's share = whole-asset value × 1/N. This asset does not require a grant. Where Qa = Yes, only one further fact is needed: was the spouse one of the other joint owners (yes/no). No relationship detail on non-spouse co-owners is required. The three-way outcome is then **derived**, not asked:

- **Exempt value** = whole-asset value × [1/N × 1/(N−1)], if the spouse was a joint owner; £0 otherwise.
- **Non-exempt remainder** = deceased's share − exempt value.

This formula holds generally, including the boundary case N = 2, where it collapses to the deceased's entire share (1/2 × 1/1 = 1/2) — consistent with a departing joint tenant's share being redistributed equally among *all* surviving joint owners, not assigned wholesale to a single named survivor. Where N ≥ 3 and the spouse is one of several surviving joint owners, only part of the deceased's share is exempt, and the row does not close — the non-exempt remainder proceeds to step 5. No partial-interest discount ever applies — no divisible legal share exists in law for a joint tenancy.

**Tenants in common.** Ownership follow-up captures N and whether shares are equal (default) or unequal (stated percentage, evidenced); deceased's share = whole-asset value × deceased's share %. This asset requires a grant. Where Qa = Yes, the spousal-destination question is worded identically to the sole-ownership question above — a direct, independently-asked will/intestacy fact — because TIC shares, like sole shares, pass by will or intestacy, not survivorship. The same entirely/partly/not-at-all handling applies. The typical 10–15% partial-interest discount is eligible here, and only here, applied only to whatever value reaches step 5 (never to a value that closed as wholly exempt, since spouse exemption already zeroes the tax regardless of precision).

### 2.5 The convergence point

Despite asking or deriving the outcome differently, all three branches produce the same two outputs before valuation evidence: an **exempt value** (possibly £0) and a **non-exempt remainder** (possibly £0, in which case the row closes at END with no step-5 questions). From that point on:

- Step 5 (valuation evidence) is worded identically across all three branches and is implemented as a single shared question object.
- The only thing that varies by branch downstream is a single **discount-eligibility flag**, on only for a non-exempt remainder originating from a tenants-in-common row (Part 2.6).

Each branch is defined as a complete, self-contained sequence in the companion reference document rather than as one shared step-numbering scheme with per-branch exceptions. This is deliberate: the spousal-destination step is not the same question suppressed in one branch, but two structurally different mechanisms (asked-fact vs. derived-fact) that happen to produce outputs of the same shape. A single numbering scheme with conditional exceptions obscures that difference; three full sequences keep each branch legible on its own terms, at no cost to the executor, who only ever sees the branch they are actually in.

### 2.6 Share identification vs discounting

Two distinct things determine the value recorded on any row, and must not be conflated:

1. **Whose share is in the estate at all** — always the deceased's own share, established at step 2/3, regardless of who the co-owner is and regardless of who eventually inherits it. A joint tenants or tenants-in-common asset is never entered at its whole value unless the deceased owned the whole. This step fires on every row regardless of eventual destination.
2. **Whether a discount applies** — only relevant to a non-exempt remainder, and only for tenants-in-common shares (Part 2.4). It never applies to a value that closed at END wholly exempt, because spousal exemption already zeroes the tax regardless of the figure's precision; it never applies to joint tenants on either path, since no divisible legal share exists in law; and, where a tenants-in-common row is only *partly* exempt, the discount applies solely to the non-exempt remainder proceeding to step 5, not to the row's full share value.

### 2.7 Estate-total aggregation

The estate total (summed exempt values plus summed non-exempt remainders, across every row and every asset class) is derived by summing rows within and across sections based on each row's stored outcome, rather than by any special section of its own. This is downstream, home-page-level aggregation — the kind of "exit from the action button" logic Annex 3A's Idea 1 describes — not part of the row-level question design in this annex. Part 7 describes a home-page feature built directly on this aggregation.

### 2.8 Single, divorced, or second-death journeys

Where Qa = No (never married, divorced, or widowed), every row proceeds straight to step 5 in whichever branch its ownership type puts it in; no spousal-destination question or derivation ever fires, and nothing spouse-related appears in the row's stored data. This is, in other words, the entire single/divorced/second-death journey for that row. First death differs only in that Qa = Yes activates the branch-specific spousal-destination treatment described in Part 2.4 before some rows are allowed to reach step 5. One row template per ownership type, one step-5 definition shared by all three, serves all four marital-status cases.

---

## 3. RNRB architecture

The residence nil-rate band regime has three routes, all anchored to one foundational test: **property the deceased owned and lived in at any point while they owned it.**

**Route 1: Conventional RNRB.** Property still in the estate at death, passing to a direct descendant.

**Route 2: Downsizing addition.** Property sold after 8 July 2015, with assets of equivalent value passing to a direct descendant. Doesn't require a current owned residence in the estate — can be the sole RNRB claim.

**Route 3: Qualifying trust.** Property passing into a qualifying trust (IPDI, bereaved minor, age 18-to-25, or disabled person's trust) in which a direct descendant has an immediate defined interest.

**The universal filter** is applied at the point the executor lists properties, not as a later filter: "Did the deceased own any property — house, flat, or other dwelling — in which they had lived at any point while they owned it?" (asked once, separately from "did the deceased own any other land, buildings or rights over land," which has no RNRB relevance).

**Question flow.** Does the estate include a qualifying-residence property? If yes, conventional route continues. If no, was any such property sold after 8 July 2015 → downsizing route if yes, no RNRB if no. Does the property (or a share) pass to a direct descendant, directly or via a qualifying trust? If more than one qualifying property, which is nominated? What value passes to direct descendants (capped at property value, checked against the property row's own recorded value)?

**Taper.** RNRB is tapered at £1 for every £2 by which the net estate exceeds £2 million, and withdrawn entirely above £2.35 million. The taper is calculated automatically from the total estate value (Part 2.7); executors are never asked to calculate it.

---

## 4. Transferred allowances

**Availability.** Transferred NRB and RNRB are available only where the deceased was widowed at some point (Qb = Yes), whether or not subsequently remarried. Never-married or divorced deceased never see this section.

**The cap.** A surviving spouse may inherit transferred allowance from more than one predeceased spouse, but total transferred NRB cannot exceed 100% of one NRB (£325,000), and total transferred RNRB cannot exceed 100% of one RNRB (£175,000), regardless of how many predeceased spouses contributed unused allowance.

**At first death**, the percentage transferred is calculated from whatever passed to non-spouse beneficiaries — i.e. from the summed non-exempt remainders across all rows (Part 2.6–2.7). Rows or portions of rows that closed as exempt don't affect the percentage; their value is only relevant to total estate value (Part 2.7) and RNRB tapering, not to the transferred-allowance calculation itself. If every row closes wholly exempt, 100% of both allowances transfer; otherwise the percentage is calculated proportionately from the non-exempt total.

**At second death**, the transferred-allowances section surfaces this stored percentage and applies it directly.

### 4.1 Second-death access to first-death detail

Because every row (or exempt portion of a row) that closes wholly or partly exempt at first death produces an itemised, valued record of the deceased's share passing to the surviving spouse — not just an aggregate percentage — the second-death journey has the option of surfacing that record to help populate the survivor's own estate inventory. This detail is identifiable at query time (rows across all asset-class sections, for the first-death case, wherever an exempt value was recorded) without any separate stored object.

**This remains an open design decision, not yet resolved:**
- **Option A (data carry-forward):** the system pre-fills known assets and rough values from the first-death record into the second-death journey; the second executor confirms, updates, or removes each item.
- **Option B (allowance-only):** only the numeric transferred-allowance percentage carries forward; no asset-level detail is surfaced.

Option A raises a genuine consent/governance question — surfacing one case's stored data into a different, later case — analogous to the session-scoped consent pattern for cross-department pre-population described in Annex A2 Appendix 2, but for cross-*case* rather than cross-department reuse. Whether that pattern is adequate here, or needs its own governance sign-off, should be settled explicitly with HMRC before Option A is built.

---

## 5. Worked illustration: property

Property exercises every element of Parts 1–3, plus RNRB entanglement, and illustrates the general template rather than defining a separate pattern. The ownership-type fork determines which of the three branches (Part 2.4) the remainder of the row follows.

**Step 1 — identification:** full address (or description and plan reference for land without one).

**Step 2 — value:** open market value of the whole property at date of death.

**Step 3 — ownership type:** sole / joint tenants / tenants in common. "Not sure" routes to a prompt to check the Land Registry title register before proceeding.

**From here, branch-specific (Qa = Yes only; see Part 2.4 for full detail):**

- *Sole or tenants in common:* ownership follow-ups (for TIC: number of owners, equal/unequal share), then the direct three-way spousal-destination question (entirely / partly / not at all).
- *Joint tenants:* number of joint owners (N), then the single binary "was the spouse one of the other joint owners" question — the three-way outcome is derived from N and this answer, not asked.

**Step 5 — valuation evidence** (fires on any non-exempt remainder): professional valuation? If yes: upload, whole-property value expected, passive discount flag. If no: lease length (if leasehold), whether the property has suffered damage affecting value, any other special factors.

**Downstream, invisible to the executor:** the engine applies the ownership share, the exempt/non-exempt split, and — for tenants-in-common remainders only — the typical 10–15% partial-interest discount, to produce the net figure feeding IHT405/435. RNRB triage (Part 3) runs alongside this template and is not restated here.

---

## 6. Asset class configuration register

HMRC maintains a configuration register specifying, for each asset class, which parts of the row template (Part 1) fire, and how deep the ownership fork goes. This makes the design modular — no bespoke journey is needed per asset class.

| Asset class | Ownership fork | Unequal-share sub-branch | Valuation-evidence substitutes | Notes |
|---|---|---|---|---|
| Property (lived in while owned) | Full | Yes | Lease, damage, special factors | RNRB-relevant; Land Registry verification prompt |
| Other land and buildings | Full | Yes | Lease, damage, special factors | No RNRB relevance |
| Bank and savings accounts | Full | Rarely used | None typically needed | "Named for convenience" guidance at step 3 |
| Share portfolios and investments | Full | Yes | None typically needed | Nominee arrangements may need flagging |
| Business and partnership interests | Full | Yes | Turnover, accounts, BPR-claim status | Partnership agreement terms may be requested |
| Chattels (jewellery, etc.) | Sole/joint only | No | Insurance-schedule value or de minimis threshold | Unequal-share branch disproportionate at this value |
| Vehicles | Sole/joint only | No | None — trade-guide lookup instead | Valuation-evidence fork may be omitted entirely |
| ISAs | Suppressed | — | — | Always sole-name; no ownership fork at all |
| Pensions | Suppressed | — | — | Passes by nomination outside the estate; modified treatment throughout |

This register is illustrative; HMRC determines the correct configuration for each asset class, and can add or reconfigure classes without any change to the underlying row template or routing mechanism in Parts 1–2.

---

## 7. Estate progress summary

A home-page button — "View estate as so far defined" — produces a summary table, one row per asset class, with three columns: **gross estate**, **taxable estate**, and **probate estate** (the deceased's share values, per the definitions in Part 2.2). A "see details" link per asset class expands to the same three columns, one row per individual asset instance within that class.

This requires no new storage or computation model. It is the same aggregation described in Part 2.7 — summing rows within and across asset-class sections by stored outcome, at the home-page level, with core itself needing no awareness of what a gross or taxable estate even is.

It is also safe to build as a live view over completed records only, with no special handling for partially-entered assets. Under the platform's table-section storage model, a row is only ever written to `AnswerTable` when it reaches its own END — whether an early close (wholly exempt) or full completion of the deep path (per Annex A2's row-journey mechanics). An asset the executor has started but not finished has no row yet, and is correctly absent from the summary; there is no intermediate, half-formed state that could leak an inaccurate figure into the total. The feature is, honestly and simply, **progress so far, based on completed records** — no further caveating is needed.

Two configuration points:

- **Whole-asset (pre-share) market value is deliberately not a summary column.** It isn't itself an IHT figure, and summed across an asset class it can look like double-counting against the other three columns. It remains useful context and belongs on the per-asset details page, alongside the whole-asset value the executor themselves supplied.
- **Asset classes where the ownership/spousal fork is suppressed by configuration** (ISAs, pensions — Part 6) need no special-case treatment in the summary. They contribute genuine, meaningful zeros to the gross and taxable estate columns in the same way any other row would, simply because the fork that would otherwise populate those figures never runs for that class.

---

## 8. What remains open

- **Per-asset-class valuation-evidence substitutes** (Part 1.4, Part 6) — need working through class by class with policy input, not assumed generic.
- **Second-death data carry-forward** (Part 4.1) — Option A vs Option B, and if Option A, the consent/governance model required.
