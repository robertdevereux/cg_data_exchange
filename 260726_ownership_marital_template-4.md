# IHT Journey: Generic Asset Template, Ownership, and Marital Status Architecture

## Status

This document consolidates decisions reached in design discussion on 26 July 2026. It builds on and should be read alongside `260628_iht-journey-architecture.md` (core Q1/Q2–Q6 template, RNRB, transferred allowances) and `260607_Functional_Architecture_v03.docx` (section types, routing, Question Sets, AnswerTable storage). Where this document refines or supersedes detail in the earlier architecture note, that is flagged explicitly.

---

## 1. The core problem this resolves

The existing Q2–Q6 generic asset template (Section 2 of the 28 June architecture note) already handles asset existence, listing, valuation and ownership type in outline. Two things were not yet resolved:

1. **How ownership type is captured without forcing every asset class into a bespoke conditional_table design** — the risk being that "ownership" tacked onto a flat table as an extra column immediately requires per-row conditional logic (joint tenants and tenants-in-common each need different follow-up questions), which a `table` (section_type=1) section cannot support.
2. **How the existence of a professional valuation should short-circuit the asset-specific evidence questions** (lease length, damage, special factors for property; equivalent substitutes for other asset classes) that HMRC otherwise needs in its absence.
3. **How spousal exemption at first death should be reflected** — not as a separate section or action button, but as a per-row branch within the same asset-class sections used for every other case, in a way that still produces a usable total estate value (for RNRB tapering) and a foundation of data that helps the second-death journey.

This document sets out the resolved design for all three.

---

## 2. Section type: conditional_table

Every asset class with an ownership dimension is implemented as a **conditional_table** (section_type=2), not a flat `table`. This is because ownership type creates genuine per-row branching: the questions asked after "how was this owned?" differ depending on the answer, and that branching must be evaluated per row, per asset instance — exactly the conditional_table use case described in the Functional Architecture.

Each row is one asset instance (one property, one shareholding, one bank account). The row's JSON dict is **sparse**: only the questions actually reached on that row's routing path are present, analogous to `asked_ids` in a standard section. A sole-ownership row will simply have no `share_percentage` key at all, rather than a null or blank one.

Because `AnswerTable` is keyed by `(user, actor, regime, case, section)` — not by question — and each asset class has its own `Section` record, answers from one asset class's ownership questions can never conflate with another's, even where the underlying Question definitions are shared verbatim across asset classes (see Section 3 below). The scoping is structural, not a matter of careful question naming.

---

## 3. The generic asset row template

The template below applies, with only surface wording varying, to every asset class with an ownership or valuation-evidence dimension: property, bank and savings accounts, listed and unlisted shares, business and partnership interests, and (in reduced form) chattels such as jewellery or vehicles.

### 3.1 Page order within a row

| Step | Question | Notes |
|---|---|---|
| 1 | Asset identification (address / description / account details / executor reference) | Wording is asset-specific |
| 2 | **Ownership type**: "How was this asset owned?" — sole / joint tenants / tenants in common | Neutral wording ("this asset"), reusable across classes |
| 3 | **Value**: "What is the open market value of the whole [asset]?" | Always the **whole** asset, never a pre-discounted share — see 3.2 |
| 6 | **Ownership follow-ups** (only for joint tenants or tenants in common): number of holders; relationship; for tenants in common, share % if not equal | Fires immediately after value, before valuation-evidence questions, so that all "who owns what" data is gathered as one coherent block |
| 4 | **Valuation evidence**: "Is this value supported by a written professional valuation?" | See Section 4 |
| 4a | If yes: upload prompt, with instruction that the valuation should be of the **whole** asset at open market value, and a passive flag if a discount for a partial interest has already been applied by the valuer | See Section 4 |
| 5 | If no: asset-specific substitute evidence questions (lease length, damage, special factors for property; class-specific equivalents elsewhere) | Only fires in the absence of a professional valuation |

The two forks — ownership type (step 2/6) and valuation evidence (step 4/5) — are independent branches on the same row. They are sequenced so that all ownership questions complete as one block before all valuation-evidence questions begin, rather than interleaving, so the row's routing tree stays legible at a glance (per the Functional Architecture's own design discipline for routing tables).

### 3.2 Full-value principle

The value captured at step 3, and the value any uploaded professional valuation must be of, is **always the whole asset's open market value** — never a pre-discounted or share-only figure. This mirrors the existing rule for Q4 in the 28 June architecture (Q4 collects full property value; the journey calculates the deceased's proportionate share at Q6B) and is now stated as a general principle for all asset classes, not only property.

This is a reasonable requirement to place on valuers, not merely a convenient assumption: professional (e.g. RICS Red Book) valuations are normally instructed and reported on an open-market, whole-asset basis; a valuation of a bare fractional interest, standalone, is the unusual instruction rather than the norm. Applying a discount for a partial interest is itself a specialist adjustment made **to** the open market value, not a separate valuation exercise.

Executors are never asked to calculate a discounted or proportionate value themselves, at any point. The engine, not the executor, applies:
- the ownership share percentage (from step 6), and
- the tenants-in-common partial-interest discount (typically 10–15% for residential property; percentage may vary by asset class), where applicable.

### 3.3 Passive safeguard against double-discounting

Because a valuer or solicitor might in practice upload a valuation that already reflects a discounted share (contrary to the instruction at 4a), a lightweight passive flag is captured at upload: "Does this valuation include a stated discount for the deceased's share?" This is not a routing branch — it does not change the question flow — but sits as a field for caseworker review, to catch the case where the engine would otherwise reapply its own discount on top of one the valuer has already applied.

### 3.4 Reuse and governance of shared Question Sets

The ownership-type Question Set (step 2 and step 6) is defined once, worded neutrally ("this asset," not "this property" or "this shareholding"), and reused as a Question Set across every asset class's conditional_table. This is consistent with the platform's existing distinction between platform questions (single canonical definition, changes propagate everywhere, cross-departmental governance) and departmental questions.

Asset-specific guidance text that would be actively misleading if shown generically (for example, the bank-account-specific note that a person named on an account "for convenience" does not automatically acquire a beneficial interest) is **not** folded into the shared Question Set. It is attached only where relevant, either as a departmental guidance override on the shared platform question, or as a separate, class-specific hint question layered alongside it. The underlying data question stays identical and reusable; only the contextual guidance varies by asset class.

### 3.5 What varies by asset class

Two things do **not** generalise, and should be configured per asset class rather than assumed generic:

- **Valuation-evidence substitutes (step 5).** These are asset-specific by nature: lease length, damage and special factors for property; accounts, turnover, or BPR-claim status for business interests; insurance-schedule value or a de minimis per-item threshold for chattels; a trade-guide lookup for vehicles. Some asset classes may not need this fork at all (vehicles, low-value chattels) — that is a legitimate configuration decision, not an oversight.
- **Depth of the ownership fork.** Tenants-in-common with an evidenced unequal share is a realistic scenario for property, shares, and business interests, but rarely worth modelling in full for vehicles or personal chattels, where sole/joint is normally sufficient and an unequal-share sub-branch can reasonably be omitted.

---

## 4. Worked illustration: property

Property is the asset class where every element of the generic template is exercised, plus RNRB entanglement. It illustrates the general template rather than defining a separate pattern.

**Step 1 — identification**: full address (or description and plan reference, for land without an address).

**Step 2 — ownership type**: sole / joint tenants / tenants in common. "Not sure" routes to a prompt to check the Land Registry title register before proceeding.

**Step 3 — value**: open market value of the **whole** property at date of death.

**Step 6 — ownership follow-ups** (joint tenants or tenants in common only): number of joint owners; relationship to deceased; for tenants in common, share percentage (default assumption: equal split, rebuttable with evidence of an actual unequal share).

**Step 4 — valuation evidence**: "Is this value supported by a written professional valuation?"
- Yes → upload prompt: valuation must be of the whole property at open market value; passive flag if a discount has already been applied by the valuer.
- No → value stands as entered; HMRC may request further information.

**Step 5 — substitute questions (no valuation only)**: lease length (if leasehold), whether the property has suffered damage affecting value, and any other special factors affecting value.

**Downstream, invisible to the executor**: the engine applies the tenants-in-common share percentage to the whole-property value, then applies the typical 10–15% partial-interest discount where applicable, to produce the net figure feeding IHT405/435.

**RNRB**: property triage (has the deceased owned and lived in a qualifying residence) and the RNRB three-route logic (conventional / downsizing / qualifying trust) sit alongside this template as already specified in the 28 June architecture note (Section 5) and are not restated here.

---

## 5. Marital status gate and the single-section, per-row branching design for first death

### 5.1 Qa and Qb (unchanged in substance, named precisely here)

Two yes/no questions, asked once per case (not per asset, not per row), establish marital status:
- **Qa**: was the deceased married (at the time of death)? A "Yes" signals a possible first death.
- **Qb**: had the deceased previously been married, where that marriage ended in the death of the spouse? A "Yes" signals second death, and gates the transferred-allowances section.

Qa and Qb are stored once, at case level, in the basic `Answer` model (keyed by question and case) — **not** in any asset class's `AnswerTable`. They are never written into, or re-derived from, any asset row. Their only role in everything that follows is to control routing at two specific, separate points, described below.

### 5.2 One action button, one section, per-row branching, and one deep path reached two ways

Earlier drafts of this document modelled first death as two sequential passes ("Canter 1" and "Canter 2"), each a candidate for its own Section and its own action button on the regime home page. That is now superseded. The action-button-per-asset-class design already on the home page ("Did the deceased own property?", "Did the deceased hold bank accounts?" and so on) stays exactly as is — one button per asset class, not two. The spouse/non-spouse split is handled **within** the single conditional_table section behind that button, as a per-row branch, not as a second section or a second pass through the asset list.

Each row of each asset class's conditional_table runs the following steps. Two separate routing forks are involved — each testing exactly one condition — and it is important to keep them distinct:

| Step | Question | Notes |
|---|---|---|
| 1 | Identification | Fires for every row |
| 2 | Ownership type / share (sole, joint tenants, tenants in common + share) | Fires for every row — needed regardless of eventual destination, since it establishes whose share is even in the estate (see 5.3) |
| 3 | Value of the **whole** asset (engine computes the deceased's share) | Fires for every row |
| — | **Fork 1, evaluated once Q3 is answered — tests Qa only:** | |
| | *Qa = Yes* → next question is **3a** | |
| | *Qa = No* → skip 3a entirely; next question is **4b** | |
| 3a | "Does the deceased's share of this asset pass entirely to the surviving spouse?" | Only ever reached when Qa = Yes. Never asked, and never present in the row's stored data at all (not even as a default), when Qa = No |
| — | **Fork 2, evaluated once 3a is answered — tests 3a only:** | |
| | *3a = Yes* → **END** (row closes) | |
| | *3a = No* → **4b** | |
| 4b | Valuation-evidence fork: professional valuation? upload / substitute questions — then the tenants-in-common discount (where applicable) is applied server-side | The single, unique definition of the deep path |

**The key point requested here**: there is only **one** definition of the deep path (4b onward), and it has two separate incoming routes into it — directly from Q3 via Fork 1 (whenever Qa = No), and via 3a's Fork 2 (whenever Qa = Yes but 3a = No). Neither fork tests more than one condition. Nothing about Qa is retested, restored, or looked up again once Fork 1 has run; by the time Fork 2 (or the direct Fork-1 route) is evaluated, all the routing engine ever inspects is the single answer immediately in front of it (Qa at Fork 1; 3a at Fork 2). This is why no two-part or compound condition is needed anywhere in this design, and why the existing single-condition routing mechanism is sufficient without extension.

Where a row closes at END (the shallow path — Qa = Yes and 3a = Yes), the deceased's share value from step 3 is recorded, undiscounted, as the estate-relevant figure; no valuation-evidence questions and no discount are ever asked or applied on that row.

An executor with, say, three properties — two passing wholly to the spouse, one passing partly to a child — adds all three as rows in the **same** Property section. The first two rows close at END via Fork 2. The third takes Fork 2's "No" branch into 4b, the same 4b that a divorced or single deceased's rows reach directly via Fork 1. No duplicate menu entries, no separate `SectionStatus` per phase, and mixed-destination assets (a property held as tenants in common, part to spouse, part to a child) sit as a single row throughout.

### 5.3 General rule: share identification vs discounting (unchanged from the corrected design)

Two distinct things determine the value recorded on any row, and they must not be conflated:

1. **Whose share is in the estate at all** — always just the deceased's own share, established at step 2, regardless of who the co-owner is (spouse or third party) and regardless of who eventually inherits it. A joint tenants or tenants-in-common asset is never entered at its whole value unless the deceased owned the whole.
2. **Whether a discount applies** — only relevant on the deep path (4b), and only for tenants-in-common shares. The shallow path (END via Fork 2) never needs it, because spousal exemption already zeroes the tax regardless of the figure's precision; joint tenants never attracts it on either path, because no divisible legal share exists in law.

Step 2 (ownership/share identification) therefore fires on every row regardless of eventual destination. What differs between the shallow and deep paths is only whether the discount and valuation-evidence questions are also asked afterward.

### 5.4 Estate-total aggregation is a downstream calculation, not a core design concern

Because both paths live in the same section, the estate total (shallow-path share values + deep-path net share values, summed across all asset classes) is derived by summing rows within and across sections based on each row's outcome (whether it closed at END or continued through 4b), rather than by summing two separately-badged sections. This is exactly the kind of exit/aggregation logic the platform design already treats as belonging outside the core action-button journey (an "exit from the action button on the regime home page" concern) rather than as part of the row-level question design documented here, and is not elaborated further in this document.

### 5.5 Single, divorced, or second-death journeys

Where Qa = No (never married, divorced, or widowed — i.e. any case other than first death of a still-married couple), Fork 1 sends every row straight to 4b; 3a is never asked and never appears in the row's stored data. In other words, the **deep path (4b) is the single/divorced/second-death journey**; first death differs only in that Fork 1 tests Qa = Yes and inserts one extra branch question (3a) into the same, otherwise-identical row template before some rows are allowed to reach the same 4b. No second section, no second action button, and no bespoke journey was invented for first death — one row template and one deep-path definition serve all four marital-status cases.

---

## 6. Second death: transferred allowances and access to first-death data

### 6.1 Availability (unchanged)

Transferred NRB and RNRB are only available where the deceased was widowed at some point, whether or not subsequently remarried. The transferred-allowances section fires only on that route, subject to the existing rule that combined transfers from any number of predeceased spouses cannot exceed 100% of one NRB (£325,000) or one RNRB (£175,000).

### 6.2 What the first-death row design now makes possible

Because every row that closes at END (Qa = Yes and 3a = Yes) at first death produces an itemised, valued record of the deceased's share passing to the surviving spouse — not just an aggregate percentage — the second-death journey has the option of surfacing that record to help populate the survivor's own estate inventory, rather than starting the executor from a blank asset list. This detail can be identified straightforwardly at query time (rows across all asset-class sections, for the first-death case, where 3a = Yes), without needing a separate section or table to have stored it distinctly.

**This is flagged as an open design decision, not yet resolved:**
- **Option A (data carry-forward)**: the system pre-fills known assets and rough values from the first-death Canter 1 record into the second-death journey; the second executor confirms, updates or removes each item as circumstances have changed in the intervening years.
- **Option B (allowance-only)**: only the numeric transferred-allowance percentage is carried forward, as in the original design; no asset-level detail is surfaced.

Option A is a materially bigger step than option B: it involves surfacing one case's stored data into a different, later case, which — even though both cases ultimately concern the same underlying individual (as spouse, then as deceased) — raises the same kind of consent question already addressed for cross-department pre-population in the Functional Architecture (session-scoped consent, asked once, clearly, before any prior answers are offered as suggestions). Whether that consent pattern is adequate for cross-case (rather than cross-department) reuse, or needs its own governance sign-off, should be settled explicitly with HMRC before Option A is built, rather than assumed to follow automatically from the data now being available.

Note also that, since the shallow/deep split is now a per-row branch rather than a separately-badged section, "the first-death record" for this purpose means a filtered query across the ordinary asset-class sections (rows where step 3a = yes), not a distinct stored object — nothing extra needs to be built to make this data identifiable later.

---

## 7. Summary of what is now settled vs still open

**Settled:**
- Ownership and valuation-evidence questions are captured via conditional_table, using a shared, asset-neutral Question Set for ownership, reused across asset classes.
- Full open-market whole-asset value is always the anchor figure; the deceased's share is calculated from it; all discounting happens server-side.
- First death is handled by **one action button, one section per asset class** — the same as every other marital-status case. Two single-condition routing forks apply: Fork 1 (tests Qa) sends a row either to the spouse-destination question 3a (Qa = Yes) or straight to the deep path 4b (Qa = No); Fork 2 (tests 3a, only reached when Fork 1 sent you there) sends the row either to END (3a = Yes) or into the same 4b (3a = No). There is only one definition of 4b, reached by two different routes; no compound or two-part routing condition is needed anywhere, and no separate section, action button, or "canter" pass exists for spouse-bound assets.
- Every co-owned asset, on either path, requires the ownership/share-identification step; only the discount and valuation-evidence questions are conditional on the path taken.
- The deep path is identical to the single/divorced/second-death journey.

**Open, flagged for decision:**
- Per-asset-class configuration of the valuation-evidence substitute questions (Section 3.5) — needs to be worked through asset class by asset class, not assumed generic.
- Whether second-death transferred-allowance calculation surfaces first-death asset detail (Option A) or remains percentage-only (Option B), and if the former, what consent/governance model applies (Section 6.2).

---

*Document status: consolidated design note from discussion of 26 July 2026, revised same day to replace an earlier two-section ("Canter 1 / Canter 2") sketch with the single-section, per-row branching design in Section 5, once it was clarified that the regime home page presents one action button per asset class, not one per marital-status pass. To be read alongside `260628_iht-journey-architecture.md` and the Functional Architecture document (section types, routing, AnswerTable storage). Does not alter RNRB or core Q1 gate mechanics already documented on 28 June.*
