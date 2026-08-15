# IHT Asset Row: Ownership Branch Question Reference

*Working reference note. Each ownership type is defined as a self-contained, fully-written-out sequence rather than a single shared numbering scheme with per-branch exceptions — deliberately, because the spousal-destination step is not the same question with conditional presence across branches: for sole and tenants in common it is a directly-asked will/intestacy fact, while for joint tenants it is arithmetic derived from ownership data already collected. Forcing all three into one numbering scheme obscures that difference rather than revealing it.*

*In build, every question below becomes `HMRC_n` with the next available sequential ID — the Sole-/Joint-/TIC- labels here are for this document only, to keep each branch legible on its own terms.*

*Three underlying concepts recur throughout and are tagged where relevant:*
- ***(1) Grant/probate estate** — assets that require a Grant of Probate to be administered.*
- ***(2) Gross IHT-reporting estate** — total value HMRC needs reported, including assets that don't need a grant (e.g. survivorship assets). Feeds RNRB tapering.*
- ***(3) Taxable/chargeable estate** — value remaining after exemptions and reliefs; what tax is actually calculated on.*

---

## Shared opening (all branches)

**Q1 — Identification.** [Asset-specific: address / account details / description], plus the executor's own reference if they're keeping one.

**Q2 — Value.** What is the open market value of the whole [asset]? *Always the whole asset — never a share the executor has worked out themselves.*

**Q3 — Ownership type.** How was this asset owned? Sole ownership / Joint tenants / Tenants in common / Not sure. *("Not sure" routes to a prompt to check the title register, e.g. Land Registry for property, before proceeding.) This is the fork into one of the three branches below.*

**Case-level, asked once per case, not per row: Qa** — Was the deceased married (or in a civil partnership) at the time of death? *Gates the spousal-destination step in every branch below.*

---

## Branch: Sole ownership

**Sole-1 — Deceased's share.** No question needed — deceased's share = 100% of Q2's value. *(Feeds Concept 1: this asset requires a Grant of Probate. Feeds Concept 2 directly.)*

**Sole-2 — Spouse destination** *(only if Qa = Yes)*. Does the deceased's share of this asset pass under the will (or, if there is no will, under the intestacy rules) — **entirely** to the surviving spouse, **partly** to the surviving spouse, or **not at all** to the surviving spouse?

- **Entirely** → row closes. Sole-1 value stands as the recorded figure. No further questions.
- **Not at all** → full Sole-1 value proceeds to Sole-4.
- **Partly** → **Sole-3**.

**Sole-3 — Spouse share value** *(only if Sole-2 = Partly)*. What value (or proportion) of the deceased's share passes to the spouse? *The spouse-bound portion is exempt and excluded from Sole-4; the remainder proceeds to Sole-4 as a taxable share.*

**Sole-4 — Valuation evidence** *(fires on whatever portion, if any, didn't close as fully exempt — i.e. skipped only if Sole-2 = Entirely)*. Is this value supported by a written professional valuation?

- **Yes** → upload prompt; whole-asset value expected; flag if the valuer has already applied a discount.
- **No** → asset-specific substitute questions (e.g. lease length and damage for property; turnover/accounts for a business interest).

*No partial-interest discount applies to any remainder in this branch — a sole-owned share is never a divisible legal interest to discount.*

---

## Branch: Joint tenants

**Joint-1 — Number of joint owners.** How many people owned this asset jointly in total, including the deceased? *(Gives N. Fires regardless of Qa — needed for the share calculation whether or not the deceased was ever married.)*

**Joint-2 — Deceased's share.** No question needed — deceased's share = Q2's value × 1/N. *(This asset passes by survivorship, outside the grant — no contribution to Concept 1. Still contributes to Concept 2 and to RNRB tapering.)*

**Joint-3 — Spouse as joint owner** *(only if Qa = Yes)*. Was the deceased's spouse one of the other joint owners of this asset? (Yes/No)

At this point the system derives the outcome — no further questions needed for the exemption calculation:

- **Exempt value** = Q2's value × [1/N × 1/(N−1)], if Joint-3 = Yes; £0 if Joint-3 = No or Qa = No.
- **Non-exempt remainder** = Joint-2 value − exempt value.

**Row outcome:**

- **Joint-3 = Yes and N = 2** → exempt value = the whole deceased's share (1/2 × 1/1 = 1/2). Row closes. No further questions.
- **Joint-3 = Yes and N ≥ 3** → exempt value covers only part of the deceased's share; non-exempt remainder proceeds to Joint-4.
- **Joint-3 = No** (or Qa = No) → nothing exempt; full deceased's share proceeds to Joint-4.

**Joint-4 — Valuation evidence** *(fires on whatever portion, if any, didn't close as fully exempt)*. Same question and branching as Sole-4.

*No partial-interest discount applies to any remainder in this branch — no divisible legal share exists in law for a joint tenancy.*

---

## Branch: Tenants in common

**TIC-1 — Number of tenants in common.** How many people owned this asset as tenants in common in total, including the deceased? *(Sets the default assumption and denominator for TIC-2.)*

**TIC-2 — Equal shares?** Was the deceased's share equal to the other owners' shares? (Yes/No)

- **Yes** → deceased's share = 1/N of Q2's value, N from TIC-1.
- **No** → **TIC-2a**: What was the deceased's percentage share? *(Free entry; evidence of the actual unequal split may be requested — e.g. the original conveyance or declaration of trust.)*

**Deceased's share value = Q2's value × deceased's share %.** *(This asset requires a Grant of Probate for the deceased's share — contributes to Concept 1 — and to Concept 2.)*

**TIC-3 — Spouse destination** *(only if Qa = Yes)*. Same three-way question as Sole-2: does the deceased's share pass **entirely** / **partly** / **not at all** to the surviving spouse, under the will or intestacy?

- **Entirely** → row closes. Deceased's share value stands as the recorded figure.
- **Not at all** → full deceased's share value proceeds to TIC-5.
- **Partly** → **TIC-4**.

**TIC-4 — Spouse share value** *(only if TIC-3 = Partly)*. Same as Sole-3: what value (or proportion) of the deceased's share passes to the spouse?

**TIC-5 — Valuation evidence** *(fires on whatever portion, if any, didn't close as fully exempt)*. Same question and branching as Sole-4/Joint-4.

*Partial-interest discount (typically 10–15%) is eligible ONLY here, and only on whatever value reaches TIC-5 — i.e. never on a value that closed at TIC-3 (Entirely), since spouse exemption already zeroes the tax regardless of precision. This is the one branch where the discount question arises at all.*

---

## Convergence point

Despite genuinely different questions and mechanisms above, all three branches produce the same two outputs before valuation evidence:

- **Exempt value** (may be £0)
- **Non-exempt remainder** (may be £0, closing the row)

From that point on, the valuation-evidence question (Sole-4 / Joint-4 / TIC-5) is worded identically across all three branches and could be implemented as one shared question object — the only thing carried forward that varies by branch is a single discount-eligibility flag: **on**, but only, for a non-exempt remainder originating in the tenants-in-common branch.
