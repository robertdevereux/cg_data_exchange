# The IHT Home Page and Tailor Journey: Salesforce Build Specification for 1 April Private Beta

*Assumes Paper 5 (Towards a 1 April Private Beta) has been read first. This paper covers Layer 1 only — the permanent home-page choreography, built once in Salesforce regardless of which track (Flow or cache utility) sits behind any given action button. It does not cover asset-level logic: that is the job of a separate Lucid chart per asset/liability type, produced in parallel, each of which must terminate in the shared exit contract this paper fixes (§4). Source of truth throughout is the existing Python implementation (`orchestrate.py`/`screen.py`), described here as functional build requirements, not as code to translate literally.*

---

## 1. Private beta scope, as decided

- All three tailor question sets — S4 (Common assets and liabilities), S5 (Pensions and life assurance), S6 (Other assets and liabilities) — are asked in full, always. This is a positive completeness check: the executor confirms what the estate *does* contain, not just what private beta happens to cover.
- **Any Yes answer anywhere in S5 or S6 takes the estate out of scope.** The journey ends with an apology, naming private beta's current coverage. This is the explicit, checkable eligibility rule Paper 5 §5 called for.
- An estate with **only** S4 Yes-answers proceeds: the home page shows a single "Common assets and liabilities" row, scoped to *only* the specific S4 items this estate answered Yes to.
- Every S4 item this row can lead to must have a built Flow behind it before 1 April — no dead ends are permitted for anything a real estate could tick.
- The **Estate ready reckoner** is dropped from private beta entirely — it addresses a lay-executor need this beta doesn't need to serve, and two of its three routes (married, widowed) are unbuilt in any case.

---

## 2. The home page action rows, adjusted for private beta

| Row | Status for private beta |
|---|---|
| Deceased's details | Unchanged — build as in the existing Python implementation |
| ~~Estate ready reckoner~~ | Removed. Do not build for 1 April. |
| Tailor your submission | Built, with a **new entry gate** (§3) replacing the reckoner-dependent one |
| Common assets and liabilities (Level 1, dynamic) | Built, scoped to only the Yes-answered S4 items for this estate |
| Pensions and life assurance / Other assets and liabilities (Level 1, dynamic) | **Do not build.** Any estate that would surface these rows has already been knocked out at Tailor's exit (§3). |

---

## 3. Entry and exit, per button

### Deceased's details

Unchanged. Entry sends the executor into deceased-details capture (or amendment, on re-entry). Exit runs duplicate-matching against every other verified estate; a genuine duplicate is a dead end telling the executor HMRC will be in touch; a unique match promotes the case to verified status and assigns an IHT reference.

### Tailor your submission

**New entry gate, replacing the previous reckoner-conditioned one:** Tailor becomes available when, and only when, **deceased's details is complete AND the case has been verified** — meaning matching has confirmed this is a new, unique estate and an IHT reference has been assigned. This is simpler than the previous gate and has no dependency on the (now-removed) reckoner.

**Entry:** calls all three tailor sections (S4, S5, S6) in any order the executor chooses, exactly as today.

**Exit — new logic:** once all three sections are complete, check every answer given:

- **If any S5 or S6 question was answered Yes** → do not return to the ordinary home page. Show the apology/knock-out screen instead, naming private beta's scope and confirming no further action is available for this estate in this service at this time.
- **Otherwise** → return to the home page as normal. The Common assets and liabilities row (§2) becomes available, scoped to the specific S4 items answered Yes.

### Common assets and liabilities

**Entry:** calls whichever S4 item Flows apply to this estate — only the Yes-answered ones, each its own "Call to get X" action per Paper 5 §3.2. No estate should ever be offered an item it didn't confirm having.

**Exit:** nothing estate-specific to decide; falls through to the home page, which reflects updated status and (per Paper 4/5 §3.5) the estate progress summary.

---

## 4. The AnswerTable exit contract — shared across every S4 item

Every asset or liability's underlying questions are expected to differ — property has an ownership fork (Annex 3B); a debt does not. What must **not** differ is what each row hands back once complete. Every Flow, for every S4 item, must produce a row containing:

| Field | Notes |
|---|---|
| `description` | Reference/identification for this row |
| `category` | `asset` or `liability` |
| `whole_value` | For assets, the whole-asset value. For liabilities, the amount owed, stored as a **negative** figure — `category` distinguishes asset from liability; `whole_value`'s sign is then consistent for both. |
| `gross_estate_contribution` | £, per Annex 3B's gross-estate concept |
| `taxable_estate_contribution` | £, after any exemption |
| `probate_estate_contribution` | £, per Annex 3B's probate/grant concept |
| `evidence_provided` | Flag |

**Private-beta simplification for liabilities, stated explicitly rather than left implicit:** a liability's `whole_value` is a negative figure, and that value shows up in only one of the three contribution fields — `taxable_estate_contribution` — reducing the taxable estate. `gross_estate_contribution` and `probate_estate_contribution` are left at zero for liability rows: a debt doesn't inflate the gross estate or require a grant to administer. This is a private-beta simplification, not asserted as universally correct; worth revisiting if a more complex liability type is added later.

This contract, not the internal question flow, is what makes the estate progress summary (Paper 4/5 §3.5) work identically regardless of which S4 item, or which Flow, produced a given row. Each per-asset Lucid chart defines *how* its Flow arrives at these six values; this paper fixes *what* it must hand back.

---

## 5. The S4 build list for 1 April

| Question | Item | Design status |
|---|---|---|
| HMRC_16 | Property lived in by the deceased | **Complete** — Annex 3B, full ownership/spousal-exemption design |
| HMRC_31 | Other land, buildings, or rights over land | Not yet designed |
| HMRC_17 | Bank or building society accounts | Not yet designed |
| HMRC_18 | Premium Bonds / National Savings | Not yet designed |
| HMRC_19 | Household goods and personal possessions | Not yet designed |
| HMRC_21 | Gifts or transfers of value in the 7 years before death | Not yet designed |
| HMRC_22 | Other debts owed by the deceased (excl. mortgage) | Not yet designed — liability |
| HMRC_23 | Money owed to the deceased (personal loans) | Not yet designed — liability |

Property is the only item with design work equivalent to Annex 3B done. The remaining seven need their own design pass — expected over the next two weeks — before a Lucid chart can be produced for each. Not all seven will need the same depth: HMRC_22/23 are liabilities/receivables, not owned assets, and likely need a materially simpler question shape than an ownership fork; HMRC_21 (gifts) is a different shape again (dates and values, not ownership). Worth sizing each individually rather than assuming property's depth is the template for all eight.

**One known, deliberately deferred gap:** `HMRC_20` (jointly owned assets, as its own triage question) is excluded from the current triage set pending design (backlog item D13). This doesn't block any individual asset's own ownership question, which stands independently — but it's a live, unresolved item sitting inside the S4 list this paper commits to building out in full.

---

## 6. Known items to resolve before or during the build, not by this paper

- **The seven remaining S4 asset/liability designs** (§5) — separate work, over the next two weeks, each producing its own Lucid chart against the §4 contract.
- **Triage-set completion status:** an unconfirmed bug (flagged 4 July, still open) where triage-row completion could show "Complete" before Tailor has genuinely been finished on a fresh estate. Needs a deliberate before/after test before the Salesforce build relies on equivalent logic.
- **`HMRC_20` (jointly owned assets)** — deferred design item (D13), noted above.

---

## 7. What this paper deliberately doesn't cover

The internal logic of any individual S4 item's Flow — that's the Lucid charts, produced in parallel, one per item, each free to be built however team (i) finds easiest, provided it terminates in the §4 contract (per Paper 5 §4's general principle: implementation is free, the contract is not).
