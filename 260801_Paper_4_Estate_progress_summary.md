# Paper 4: An Estate Progress Summary on the IHT Home Page

*A short paper recording a single design idea reached in working session, for handoff into further design work. Assumes familiarity with Paper 3 and Annex 3B's asset row template, and with the companion reference document `IHT_ownership_branch_questions.md`, which sets out the full ownership/spousal-exemption question sequences this idea builds on. Nothing in those documents is restated here.*

---

## 1. The idea

A home-page button — **"View estate as so far defined"** — producing a summary table, one row per asset class, with three columns:

- **Gross estate** — the deceased's share value, before exemptions.
- **Taxable estate** — the deceased's share value, after spouse exemption is applied.
- **Probate estate** — the deceased's share value, restricted to assets that actually require a Grant of Probate to administer (excludes joint-tenancy shares, which pass by survivorship).

A "see details" link per asset class expands to the same three columns, one row per individual asset instance within that class.

---

## 2. Why this is a low-cost addition, not new machinery

**It requires no new storage or computation model.** It is the same "exit from the action button" aggregation logic already described for estate-total aggregation in Annex 3B §2.4 — summing rows within and across asset-class sections by outcome, at the home-page level. Core itself needs no awareness of what a gross or taxable estate even is; it is simply reading back rows it already stores.

**It is safe to build as a live view over completed records only, with no special handling for partially-entered assets.** Under the platform's table-section storage model, a row is only ever written when it reaches its own END — whether an early close (wholly exempt) or full completion of a deeper path. An asset the executor has started but not finished has no row yet, and is correctly absent from the summary; there is no intermediate, half-formed state that could leak an inaccurate figure into the total. The feature is honestly and simply **progress so far, based on completed records** — no caveating beyond that is needed.

---

## 3. Two refinements settled in discussion

- **A fourth column — whole-asset (pre-share) market value — was considered and dropped from the summary.** It isn't itself an IHT figure, and summed across an asset class it can look like double-counting against the other three columns. It remains useful context and is better placed on the per-asset details page, alongside the whole-asset value the executor themselves supplied.

- **Asset classes where the ownership/spousal fork is suppressed by configuration (ISAs: always sole-name; pensions: pass by nomination, outside the estate) need no special-case treatment in the summary.** They contribute genuine, meaningful zeros to the gross and taxable estate columns in the same way any other row would — simply because the fork that would otherwise populate those figures never runs for that class. No exclusion or distinct row type is needed.

---

## 4. What this doesn't change

Nothing here proposes any change to what qualifies for spouse exemption, how transferable allowances are calculated, or what constitutes a taxable estate. This is a read-only, home-page-level presentation of data the design already collects — it adds one new view, nothing else.
