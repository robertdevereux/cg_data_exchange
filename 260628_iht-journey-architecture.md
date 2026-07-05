# IHT Journey Architecture: Key Decisions and Frameworks

## Introduction

This document sets out the architectural decisions reached in designing a user-friendly IHT journey for executors and their agents. It is intended to inform the development of a digital service that guides executors through the information HMRC needs, without requiring them to understand the underlying form structure or legal concepts.

### The core design principle

The journey is conceived as a two-step process:

**Step 1 — Marital status**
A single gate question asked once at the outset establishes the deceased's marital status. This single question does substantial work throughout the remainder of the journey, in two respects:

- It determines, for each asset class, whether the executor needs to declare all assets or only those passing to someone other than a surviving spouse — radically reducing the data-gathering burden for first deaths, where the spouse exemption means the majority of assets are simply irrelevant to the IHT calculation
- It determines whether transferred allowances — transferable NRB and RNRB from a predeceased spouse — are potentially available at all, confining that complexity to journeys where it is actually relevant

**Step 2 — Asset by asset declaration**
The executor works through each asset class in turn, answering a consistent sequence of questions: does the asset exist, list the instances, what is each worth, how was it owned, and if jointly owned, by whom and in what shares. The sequence is identical across asset classes; only the surface wording varies.

### What this achieves

For the common case of a first death in a married couple where most or all assets pass to the surviving spouse, the journey becomes primarily a recording exercise — capturing transferred allowance percentages for use at the second death, with minimal asset-level detail required. The full complexity of ownership, tenure, valuation and relief only surfaces where it genuinely matters: assets passing to non-spouse beneficiaries, and the second death journey where no spouse exemption is available.

For single or divorced deceased, or for the second death of a couple, the full asset declaration sequence applies — but even then the consistent Q2–Q6 template means the executor encounters a predictable, repeating pattern rather than a different set of questions for every asset class.

### A note on transferred allowances

The marital status gate at Step 1 also determines whether the transferred allowances section of the journey fires at all. Transferred NRB and RNRB are only available where the deceased was widowed at some point — whether or not they subsequently remarried. For never-married or divorced deceased, the transferred allowances section is suppressed entirely. Where the deceased was widowed, the journey collects the information needed to calculate the transferable percentage from each predeceased spouse, subject to the overall cap of 100% of one additional allowance.

---

## 1. Top-Level Marital Status Gate (Q1)

The entire journey is framed by a single universal gate question asked once at the outset:

**Q1: "At the date of death, what was the deceased's marital status?"**
- Never married or divorced → single route: all assets in scope; no transferred allowances possible
- Married, and this is the first death of the couple → first death route: spouse exemption applies; focus on assets passing to anyone other than the surviving spouse; transferred allowances not yet relevant but percentages captured for second death
- Widowed (whether or not subsequently remarried) → widowed route: full asset declaration; transferred allowances from predeceased spouse(s) available, subject to 100% cap

Q1 is asked once and silently determines:
- Which variant of Q3 fires throughout the entire asset declaration
- Whether the transferred allowances section fires at all
- If so, how many predeceased spouses need to be accounted for

The executor never sees the routing machinery.

---

## 2. Generic Asset Class Template (Q2–Q6)

All asset classes follow the same six-question template. Only the surface wording varies by asset class; the logical structure is identical throughout.

### Q2 — Asset existence
"Did the deceased own any [asset type]?"
- No → exit this asset section
- Yes → continue

Q2 is purely about existence of the asset in the deceased's estate at date of death. It makes no reference to who the asset passes to — that filter only applies at Q3.

### Q3 — Asset listing (marital status variant)

**Q3A — Single/divorced/widowed**
"Please list each [asset type]"

**Q3B — First death of a couple**
"Please list each [asset type] that passes to someone other than the surviving spouse"

Q3 is the first point where the Q1 marital status gate produces a visible difference to the executor.

### Q4 — Valuation
"What is the open market value of this [asset type] at the date of death?"

Q4 collects the full gross value of the asset before any adjustment for shared ownership. The journey applies ownership adjustments at Q6; executors are not asked to calculate net or proportionate values themselves. Liabilities such as mortgages are collected separately in the liabilities section; the journey calculates net values.

### Q5 — Ownership type
"How was this [asset type] owned?"
- Solely owned → no further ownership questions; proceed to next asset
- Joint tenants with another person → Q6A
- Tenants in common with another person → Q6B
- Not sure → asset-specific verification prompt (e.g. check Land Registry for property)

The three tenure options are mutually exclusive and exhaustive. Radio buttons are appropriate. Brief plain-English descriptions of each option should accompany the question.

### Q6A — Joint tenants follow-up
- How many people were named on the [asset] including the deceased?
  → journey calculates default equal share automatically
- Who are the other named owners, and what is their relationship to the deceased?
  → flags family members for HMRC attention
- Confirms survivorship treatment → routes to IHT404

### Q6B — Tenants in common follow-up
- How many people own a share including the deceased?
  → journey calculates default equal share automatically
- Was the deceased's share different from an equal split?
  - No → use calculated default
  - Yes → specify actual share + prompt for supporting evidence
- Who owns the remaining shares, and what is their relationship to the deceased?
  → flags family members
  → routes deceased's proportionate share to IHT405 at partial interest valuation

---

## 3. Asset Class Configuration Register

HMRC maintains a configuration register specifying, for each asset class, which questions in the Q2–Q6 template fire. This makes the journey modular — bespoke journey design is not needed for every asset class.

The key principle is:

- **Potentially shared ownership** → full Q2–Q6 template
- **Always solely owned** → Q5 and Q6 suppressed
- **Passes outside estate by nomination** → modified Q3; Q5 and Q6 suppressed; separate nomination/beneficiary section

| Asset class | Q2 | Q3A/B | Q4 | Q5 | Q6A/B | Notes |
|---|---|---|---|---|---|---|
| Property (lived in while owned) | ✅ | ✅ | ✅ | ✅ | ✅ | Full template; Land Registry verification prompt for unclear tenure |
| Other land and buildings | ✅ | ✅ | ✅ | ✅ | ✅ | Full template; no RNRB relevance |
| Bank and savings accounts | ✅ | ✅ | ✅ | ✅ | ✅ | Beneficial interest vs signatory guidance needed at Q5 |
| Share portfolios and investments | ✅ | ✅ | ✅ | ✅ | ✅ | Nominee arrangements may need flagging |
| ISAs | ✅ | ✅ | ✅ | ❌ | ❌ | Always sole-name; Q5 and Q6 drop out |
| Pensions | ✅ | ❌ | ❌ | ❌ | ❌ | Passes by nomination outside estate; modified treatment throughout |
| Business interests | ✅ | ✅ | ✅ | ✅ | ✅ | Partnership agreements; BPR implications |

This register is illustrative. HMRC determines the correct configuration for each asset class.

---

## 4. Property-Specific Architecture

### IHT405 simplification

The current IHT405 splits property into:
- Section 6: Deceased's residence
- Section 7: Other land, buildings and rights over land

This split reflects legacy form structure and valuation administration convenience, not a principled taxonomy. A redesigned journey replaces it with:

**Category (a): Property the deceased owned and lived in at any point while they owned it**
→ RNRB-relevant; feeds IHT435

**Category (b): All other land, buildings and rights over land**
→ Asset inventory only; no RNRB relevance

The "owned and lived in simultaneously" test is the single universal filter for the entire RNRB regime. It is applied at Q2/Q3 when the executor lists properties, not as a subsequent filter.

### Property triage questions

**Q2-property (all routes)**
"Did the deceased own any property — house, flat or other dwelling — in which they had lived at any point while they owned it?"

**Q2-other-property (all routes)**
"Did the deceased own any other land, buildings or rights over land?"
*Hint: for example, rental or investment property, commercial premises, farmland, fishing or mineral rights*

**Q3A-property (single/divorced/widowed)**
"Please give the address of each such property"

**Q3B-property (first death of couple)**
"Please give the address of each such property that passes to someone other than the surviving spouse"

### Tenure three-way split (Q5-property)
Radio button, one selection per property:
- Owned outright → straight to next question
- Joint tenants with another person → Q6A-property
- Tenants in common with another person → Q6B-property
- Not sure → prompt to check Land Registry title register before proceeding

### Valuation (Q4-property, all routes)
"What is the open market value of the deceased's interest in this property at the date of death?"
"Do you have a professional valuation?"
- Yes → note that HMRC may request a copy
- No → value stands; HMRC may request further information

Mortgages are collected separately in the liabilities section. The journey calculates net values; executors are not asked to net off liabilities at asset level.

Tenancy details (whether the property is let, lease terms etc.) are not collected upfront. Where a property is tenanted, HMRC may request supporting information on a case-by-case basis.

---

## 5. RNRB Architecture

The RNRB regime has three routes, all anchored to the same foundational definition: property the deceased owned and lived in at any point while they owned it.

### Route 1: Conventional RNRB
Property still in estate at date of death, passing to a direct descendant.

### Route 2: Downsizing addition
Property sold after 8 July 2015; assets of equivalent value passing to a direct descendant. Does not require a current owned residence in the estate — can be the sole RNRB claim.

### Route 3: Qualifying trust
Property passing into a qualifying trust (IPDI, bereaved minor, age 18-to-25, or disabled person's trust) in which a direct descendant has an immediate defined interest.

### RNRB question flow
1. Does the estate include property the deceased owned and lived in while they owned it? (Q2-property above)
   - Yes → conventional RNRB route; continue
   - No → was any such property sold after 8 July 2015? → downsizing route if yes; no RNRB if no
2. Does the property, or a share of it, pass to a direct descendant?
   - Directly → conventional or downsizing RNRB
   - Via a qualifying trust → qualifying trust check
   - No → no RNRB on this property
3. If more than one qualifying property: which do you nominate?
4. What value passes to direct descendants? (capped at property value; checked against IHT405 figure)

### Taper
RNRB is tapered at £1 for every £2 by which the net estate exceeds £2 million, and withdrawn entirely above £2.35 million. The journey calculates taper automatically from the total estate value; executors are not asked to calculate it.

---

## 6. Transferred Allowances

### Availability
Transferred NRB and RNRB are only available where the deceased was widowed at some point. The transferred allowances section of the journey fires only where Q1 identifies the deceased as widowed (whether or not subsequently remarried). For never-married or divorced deceased it is suppressed entirely.

### Multiple predeceased spouses
A surviving spouse may inherit transferred allowances from more than one predeceased spouse. However the total transferred NRB cannot exceed 100% of one NRB (£325,000), and the total transferred RNRB cannot exceed 100% of one RNRB (£175,000), regardless of how many predeceased spouses contributed unused allowance.

### First death of a couple
For the first death of a married couple:
- Assets passing to the surviving spouse → spouse exemption applies; zero IHT regardless of value
- Unused NRB and RNRB transfer to the surviving spouse as a percentage of the allowance unused
- Total estate value is not relevant to the transfer calculation; only what passed to non-exempt beneficiaries matters
- If the entire estate passes to the spouse → 100% of both allowances transfer
- If some assets passed to others → percentage transfer calculated proportionately by the journey

The journey focuses on assets passing to non-spouse beneficiaries for IHT calculation purposes, while capturing transferred allowance percentages for use in the second death journey.

---

## 7. Joint Ownership Guidance Notes

### Property
- Tenure formally recorded at Land Registry; executors should verify if unclear
- Partial interest discount typically 10–15% for tenants in common share in residential property; professional valuation should reflect this
- Q4 collects full property value; journey calculates deceased's proportionate share at Q6B

### Bank and savings accounts
- Joint accounts default to joint tenancy with survivorship
- A person named on an account solely for convenience (e.g. to operate it on behalf of an elderly parent) does not automatically acquire a beneficial interest
- Guidance at Q5: "If another person was named on the account solely to help manage it — for example, an adult child added to pay bills — this does not automatically make them a joint owner with a beneficial interest. If that person had no claim to the money as their own, the account should be treated as solely owned by the deceased."
- Default share: equal split by number of account holders; asymmetric ownership requires evidence
- Joint account held with surviving spouse: flag immediately as spouse-exempt
- Where a joint account existed, HMRC's default assumption is an equal split of the balance unless there is evidence to the contrary

---

*Document status: draft summary of architectural decisions reached in IHT journey design discussion. To be read alongside IHT forms IHT400, IHT404, IHT405, IHT435 and associated guidance.*
