# Annex 3B: The IHT Design — Technical Detail

*Companion to Paper 3: Delivering Inheritance Tax via Core, and to Annex 3A's plain-language account. Written for digital and data architects and for policy analysts configuring the routing itself. Uses the section-type vocabulary and object names established in Annex A2 throughout — this document adds nothing to the platform's own mechanics; it only configures them for Inheritance Tax.*

**Supersession note:** this document consolidates and supersedes the ownership/valuation and routing-mechanics material previously held in `260726_ownership_marital_template-4.md`, and the RNRB, transferred-allowances, and asset-class configuration material previously held in `260628_iht-journey-architecture.md`. Both source documents can be retired once this annex is in place.

---

## 1. The generic asset row template

Every asset class with an ownership or valuation dimension — property, bank and savings accounts, listed and unlisted shares, business and partnership interests, and (in reduced form) chattels such as jewellery or vehicles — is captured in a **Table with routing** section (`section_type = 2`, per Annex A2 Part Three). Each row is one asset instance. The row's stored data is sparse, per Annex A2: only the questions actually reached on that row's path are present.

### 1.1 Row shape

| Step | Question | Notes |
|---|---|---|
| 1 | Asset identification (address / description / account details / executor reference) | Wording is asset-specific |
| 2 | **Ownership type**: "How was this asset owned?" — sole / joint tenants / tenants in common | Neutral wording ("this asset"), reusable across classes as a shared platform Question |
| 3 | **Value**: "What is the open market value of the whole [asset]?" | Always the **whole** asset — see 1.2 |
| 3a | **Marital-status branch** (first-death cases only): "Does the deceased's share of this asset pass entirely to the surviving spouse?" | See Part 2 |
| 4/6 | **Ownership follow-ups** (joint tenants or tenants in common only): number of holders; relationship; for tenants in common, share % if not equal | Fires as a block once ownership type is known, before valuation-evidence questions |
| 5 | **Valuation evidence**: "Is this value supported by a written professional valuation?" | If yes: upload prompt, whole-asset value expected, passive flag if a discount has already been applied by the valuer. If no: asset-specific substitute evidence questions (see 1.4) |

The ownership fork (step 2/4) and the valuation-evidence fork (step 5) are independent branches on the same row, sequenced so all ownership questions complete as one block before valuation-evidence questions begin — keeping the row's routing tree legible rather than interleaving two unrelated forks.

### 1.2 The full-value principle

The value captured at step 3, and any uploaded valuation, is always the **whole asset's** open market value — never a pre-discounted or share-only figure. This is a reasonable requirement to place on valuers as well as executors: a professional (e.g. RICS Red Book) valuation is normally instructed and reported on a whole-asset, open-market basis; a discount for a partial interest is a specialist adjustment applied *to* that value, not a separate valuation exercise. Executors are never asked to calculate a discounted or proportionate value themselves — the engine applies the ownership share (from step 4) and, where applicable, the tenants-in-common partial-interest discount (typically 10–15% for residential property; the figure may vary by asset class).

A passive, non-routing safeguard is captured at upload: whether the valuation already includes a stated discount for the deceased's share. This doesn't change the question flow, but flags for caseworker review the case where the engine would otherwise reapply its own discount on top of one the valuer has already applied.

### 1.3 Shared Question Set governance

Step 2's ownership-type Question, and its step-4 follow-ups, are defined once as a shared platform Question Set — worded neutrally ("this asset," not "this property") — and reused across every asset class's Table with routing section. Because `AnswerTable` is keyed by `(user, actor, regime, case, section)`, not by question, reusing the same Question definition across asset classes carries no risk of answers conflating between asset classes: each asset class's section has its own `AnswerTable` row, entirely separate from any other's.

Asset-specific guidance that would be misleading shown generically (for example, the bank-account-specific note that someone named on an account "for convenience" doesn't automatically acquire a beneficial interest) is attached only where relevant — as a departmental guidance override or a separate class-specific hint — rather than folded into the shared Question itself.

### 1.4 What varies by asset class

Two things are configured per asset class, not assumed generic:

- **Valuation-evidence substitutes (step 5, no-valuation branch).** Asset-specific by nature: lease length, damage, and special factors for property; turnover, accounts, or BPR-claim status for business interests; an insurance-schedule value or de minimis threshold for chattels; a trade-guide lookup for vehicles. Some classes may not need this fork at all (vehicles, low-value chattels) — a legitimate configuration choice, not an oversight.
- **Depth of the ownership fork.** Tenants-in-common with an evidenced unequal share is realistic for property, shares, and business interests; rarely worth modelling for vehicles or personal chattels, where sole/joint is normally sufficient.

---

## 2. Marital status and the single-section, per-row branching design

### 2.1 Qa and Qb

Two yes/no questions, asked once per case (not per asset, not per row), establish marital status and are stored at case level in the basic `Answer` model — never written into any asset row:

- **Qa**: was the deceased married at the time of death? "Yes" signals a possible first death.
- **Qb**: had the deceased previously been married, where that marriage ended in the death of the spouse? "Yes" signals second death, and gates the transferred-allowances section (Part 4).

### 2.2 One section, two forks, one deep path

Every asset class keeps its existing action button and its existing Table with routing section — first death does not add a second section, a second action button, or a second pass through the asset list. Instead, two single-condition routing forks apply within each row:

| Step | Fires | Tests |
|---|---|---|
| Fork 1 (at Q3, once value is answered) | Every row | Qa. If Yes → next question is 3a. If No → skip 3a; next is step 5 (valuation evidence) |
| 3a | Only reached when Qa = Yes | "Does the deceased's share of this asset pass entirely to the surviving spouse?" |
| Fork 2 (once 3a is answered) | Only reached when Fork 1 sent the row here | 3a. If Yes → **END**, row closes. If No → step 5 (valuation evidence) |

There is only **one** definition of the valuation-evidence step onward (step 5+), reached by two separate routes: directly from Fork 1 whenever Qa = No, and via Fork 2 whenever Qa = Yes but 3a = No. Neither fork tests more than one condition; Qa is never re-tested or re-derived once Fork 1 has run. This is why no compound routing condition is needed anywhere in the design.

Where a row closes at END (Qa = Yes and 3a = Yes — the shallow path), the deceased's share value from step 3 is recorded, undiscounted, as the estate-relevant figure; no valuation-evidence questions and no discount ever fire on that row. Where a row continues to step 5 (the deep path), it receives exactly the same treatment described in Part 1, regardless of whether it got there via Fork 1 or Fork 2.

An executor with three properties — two passing wholly to the spouse, one passing partly to a child — adds all three as rows in the same Property section. The first two close at END via Fork 2. The third takes Fork 2's "No" branch into the same deep path a divorced or single deceased's rows reach directly via Fork 1.

### 2.3 Share identification vs discounting

Two distinct things determine the value recorded on any row, and must not be conflated:

1. **Whose share is in the estate at all** — always the deceased's own share, established at step 2, regardless of who the co-owner is and regardless of who eventually inherits it. A joint tenants or tenants-in-common asset is never entered at its whole value unless the deceased owned the whole. This step fires on every row regardless of eventual destination.
2. **Whether a discount applies** — only relevant on the deep path, and only for tenants-in-common shares. The shallow path never needs it, because spousal exemption already zeroes the tax regardless of the figure's precision; joint tenants never attracts it on either path, since no divisible legal share exists in law.

### 2.4 Estate-total aggregation

The estate total (shallow-path share values plus deep-path net share values, summed across every asset class) is derived by summing rows within and across sections based on each row's outcome (END vs continued), rather than by any special section of its own. This is downstream, home-page-level aggregation — the kind of "exit from the action button" logic Annex 3A's Idea 1 describes — not part of the row-level question design in this annex.

### 2.5 Single, divorced, or second-death journeys

Where Qa = No (never married, divorced, or widowed), Fork 1 sends every row straight to step 5; 3a is never asked and never appears in the row's stored data. The deep path is, in other words, the entire single/divorced/second-death journey. First death differs only in that Fork 1 tests Qa = Yes and inserts one extra branch question (3a) before some rows are allowed to reach the same deep path. One row template, one deep-path definition, serves all four marital-status cases.

---

## 3. RNRB architecture

The residence nil-rate band regime has three routes, all anchored to one foundational test: **property the deceased owned and lived in at any point while they owned it.**

**Route 1: Conventional RNRB.** Property still in the estate at death, passing to a direct descendant.

**Route 2: Downsizing addition.** Property sold after 8 July 2015, with assets of equivalent value passing to a direct descendant. Doesn't require a current owned residence in the estate — can be the sole RNRB claim.

**Route 3: Qualifying trust.** Property passing into a qualifying trust (IPDI, bereaved minor, age 18-to-25, or disabled person's trust) in which a direct descendant has an immediate defined interest.

**The universal filter** is applied at the point the executor lists properties, not as a later filter: "Did the deceased own any property — house, flat, or other dwelling — in which they had lived at any point while they owned it?" (asked once, separately from "did the deceased own any other land, buildings or rights over land," which has no RNRB relevance).

**Question flow.** Does the estate include a qualifying-residence property? If yes, conventional route continues. If no, was any such property sold after 8 July 2015 → downsizing route if yes, no RNRB if no. Does the property (or a share) pass to a direct descendant, directly or via a qualifying trust? If more than one qualifying property, which is nominated? What value passes to direct descendants (capped at property value, checked against the property row's own recorded value)?

**Taper.** RNRB is tapered at £1 for every £2 by which the net estate exceeds £2 million, and withdrawn entirely above £2.35 million. The taper is calculated automatically from the total estate value (Part 2.4); executors are never asked to calculate it.

---

## 4. Transferred allowances

**Availability.** Transferred NRB and RNRB are available only where the deceased was widowed at some point (Qb = Yes), whether or not subsequently remarried. Never-married or divorced deceased never see this section.

**The cap.** A surviving spouse may inherit transferred allowance from more than one predeceased spouse, but total transferred NRB cannot exceed 100% of one NRB (£325,000), and total transferred RNRB cannot exceed 100% of one RNRB (£175,000), regardless of how many predeceased spouses contributed unused allowance.

**At first death**, the percentage transferred is calculated from whatever passed to non-spouse beneficiaries — i.e. from the deep-path rows only (Part 2.2). Rows that closed at END (wholly spouse-bound) don't affect the percentage; their value is only relevant to total estate value (Part 2.4) and RNRB tapering, not to the transferred-allowance calculation itself. If every asset closes at END, 100% of both allowances transfer; otherwise the percentage is calculated proportionately from the deep-path total.

**At second death**, the transferred-allowances section surfaces this stored percentage and applies it directly.

### 4.1 Second-death access to first-death detail

Because every row that closes at END at first death produces an itemised, valued record of the deceased's share passing to the surviving spouse — not just an aggregate percentage — the second-death journey has the option of surfacing that record to help populate the survivor's own estate inventory. This detail is identifiable at query time (rows across all asset-class sections, for the first-death case, where 3a = Yes) without any separate stored object.

**This remains an open design decision, not yet resolved:**
- **Option A (data carry-forward):** the system pre-fills known assets and rough values from the first-death record into the second-death journey; the second executor confirms, updates, or removes each item.
- **Option B (allowance-only):** only the numeric transferred-allowance percentage carries forward; no asset-level detail is surfaced.

Option A raises a genuine consent/governance question — surfacing one case's stored data into a different, later case — analogous to the session-scoped consent pattern for cross-department pre-population described in Annex A2 Appendix 2, but for cross-*case* rather than cross-department reuse. Whether that pattern is adequate here, or needs its own governance sign-off, should be settled explicitly with HMRC before Option A is built.

---

## 5. Worked illustration: property

Property exercises every element of Parts 1–3, plus RNRB entanglement, and illustrates the general template rather than defining a separate pattern.

**Step 1 — identification:** full address (or description and plan reference for land without one).

**Step 2 — ownership type:** sole / joint tenants / tenants in common. "Not sure" routes to a prompt to check the Land Registry title register before proceeding.

**Step 3 — value:** open market value of the whole property at date of death.

**Step 3a (first death only):** does the deceased's share pass entirely to the spouse?

**Step 4 — ownership follow-ups** (joint tenants or tenants in common only): number of joint owners; relationship to deceased; for tenants in common, share percentage (default: equal split, rebuttable with evidence of an actual unequal share).

**Step 5 — valuation evidence:** professional valuation? If yes: upload, whole-property value expected, passive discount flag. If no: lease length (if leasehold), whether the property has suffered damage affecting value, any other special factors.

**Downstream, invisible to the executor:** the engine applies the tenants-in-common share percentage to the whole-property value, then applies the typical 10–15% partial-interest discount where applicable (deep-path rows only — see Part 2.3), to produce the net figure feeding IHT405/435. RNRB triage (Part 3) runs alongside this template and is not restated here.

---

## 6. Asset class configuration register

HMRC maintains a configuration register specifying, for each asset class, which parts of the row template (Part 1) fire, and how deep the ownership fork goes. This makes the design modular — no bespoke journey is needed per asset class.

| Asset class | Ownership fork | Unequal-share sub-branch | Valuation-evidence substitutes | Notes |
|---|---|---|---|---|
| Property (lived in while owned) | Full | Yes | Lease, damage, special factors | RNRB-relevant; Land Registry verification prompt |
| Other land and buildings | Full | Yes | Lease, damage, special factors | No RNRB relevance |
| Bank and savings accounts | Full | Rarely used | None typically needed | "Named for convenience" guidance at step 2 |
| Share portfolios and investments | Full | Yes | None typically needed | Nominee arrangements may need flagging |
| Business and partnership interests | Full | Yes | Turnover, accounts, BPR-claim status | Partnership agreement terms may be requested |
| Chattels (jewellery, etc.) | Sole/joint only | No | Insurance-schedule value or de minimis threshold | Unequal-share branch disproportionate at this value |
| Vehicles | Sole/joint only | No | None — trade-guide lookup instead | Valuation-evidence fork may be omitted entirely |
| ISAs | Suppressed | — | — | Always sole-name; no ownership fork at all |
| Pensions | Suppressed | — | — | Passes by nomination outside the estate; modified treatment throughout |

This register is illustrative; HMRC determines the correct configuration for each asset class, and can add or reconfigure classes without any change to the underlying row template or routing mechanism in Parts 1–2.

---

## 7. What remains open

- **Per-asset-class valuation-evidence substitutes** (Part 1.4, Part 6) — need working through class by class with policy input, not assumed generic.
- **Second-death data carry-forward** (Part 4.1) — Option A vs Option B, and if Option A, the consent/governance model required.
