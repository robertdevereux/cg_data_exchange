# IHT Reckoner — Decision Flow
## Parts 1, 2 and 3: Entry, Marital Status Routing, and Part 3 Detail

Date: June 2026
Status: Working draft

---

## Overview

The IHT Ready Reckoner is a guided assessment that helps an executor determine
whether Inheritance Tax is payable on an estate, and whether a full IHT return
is required. It is reached via the Estate Ready Reckoner button on the IHT
estate homepage.

The reckoner is designed to deliver one of two conclusions:

- "Based on what you have told us, IHT is not payable on the estate of [name]."
- "IHT may be payable. We will help you work out if it is." → main flow

For most estates the first conclusion is correct. The reckoner is designed to
reach it quickly and confidently, with questions that are both comprehensible
to a non-expert executor and comprehensive enough to give HMRC the basis for
the reassurance.

---

## Entry: Do you need help?

The reckoner is entered via HMRC_S2, a two-question navigation section
(show_confirmation=False) that sits on the IHT estate homepage.

**HMRC_13: Do you need help working out whether a full Inheritance Tax return
is required for this estate?**

- Yes, I'd like help working that out → HMRC_14
- No, I know a full return is required and want to get started → END
  [Home page shows Estate elements row — main flow entry point]

---

## Marital status routing

**HMRC_14: At the time of their death, was the deceased...**

Guidance: The rules used to calculate whether Inheritance Tax is payable differ
depending on the marital status of the deceased at the time of their death. In
particular, married couples and civil partners can pass unused tax-free allowances
to each other, which may significantly increase the threshold above which tax
becomes payable. If the deceased was divorced, they are treated as single for
this purpose. If the deceased was widowed and subsequently remarried, select the
first option.

- Married, with their spouse surviving them → Part 1 (stub — not yet built)
- Themselves a widow or widower, their spouse having died before them and not
  subsequently remarried → Part 2 (stub — not yet built)
- Neither of the above — for example single, divorced, or living with a partner
  but not married → Part 3 (below)

For Part 1 and Part 2, the home page currently shows:
"This part of the reckoner is not yet available. Please return later."

---

## Why Part 3 first?

Part 3 (single/divorced/partnered) has the simplest allowance structure —
a single nil-rate band of £325,000, plus potentially the Residence Nil-Rate
Band (£175,000) where a home is left to direct descendants. There is no
transferable nil-rate band complexity.

Parts 1 and 2 involve the transferable nil-rate band from a deceased spouse,
and potentially the transferable Residence Nil-Rate Band also. These are more
complex and will be built once Part 3 is complete and tested.

The decision tree for Parts 1 and 2 has been discussed and outlined but not
yet formally documented. Key points:

Part 1 (survived by spouse):
  - Assets to surviving spouse → IHT exempt
  - If all assets to spouse → not payable immediately
  - If some assets to others (A) → compare A against £325k threshold
  - Then gifts section as per Part 3

Part 2 (widow/widower, spouse predeceased):
  - Potentially inheriting unused nil-rate band from first spouse
  - Did first spouse leave any assets to others? → unused NRB calculation
  - Carried-over allowance C = (£325k - B) where B = first spouse's
    non-exempt gifts
  - Effective threshold = £325k + C (up to £650k)
  - RNRB potentially transferable too (up to further £175k)
  - Home left to descendants? → Q3/Q4 as Part 3
  - Then gifts section as per Part 3

Both parts need a flow document equivalent to this one before building.

---

## Part 3: Single, divorced, or partnered but not married

Part 3 applies where the deceased was, at the time of their death:
- single
- divorced (even if previously married)
- living with a partner but not married or in a civil partnership

Note: someone who was divorced is treated as single for IHT purposes,
even if they have children from the marriage. They may still benefit
from the Residence Nil-Rate Band if they leave a home to direct
descendants.

The reckoner for Part 3 operates across four sections (HMRC_RECK1-4),
each returning to the estate homepage between them. The homepage view
reads completed answers, performs any necessary calculations, and
determines which section to call next.

---

## Section 1: Assets

Handled within HMRC_RECK1 (show_confirmation=False).

**Q1: Were the total assets of the deceased worth more than £325,000 at the
time of their death?**

Guidance: Include everything owned — money in bank accounts, savings,
investments, personal possessions, vehicles, and any property or land.
Do not deduct any debts or mortgages at this stage.

- No → Gifts section (within HMRC_RECK1)
- Yes → Q2
- Don't know yet → Save and return
  [To answer this question you will need a rough picture of everything the
  deceased owned. You do not need precise valuations at this stage — a
  reasonable estimate is fine. Link: how to estimate an estate's value.]

---

**Q2: Did the deceased own a home, or a share of a home, at the time of
their death?**

Guidance: This includes a home they may have moved out of — for example if
they were living in a care home or hospital at the time of death.

- No → END [Home page routes to main flow]
  [IHT may be payable. We will help you work out if it is.]
- Yes → Q3

(No "Don't know" option here — home ownership should be clear.)

---

**Q3: Was any part of that home left to a direct descendant — for example a
child, grandchild, or stepchild?**

Guidance: Link — full list of who counts as a direct descendant for this
purpose.

- No → END [Home page routes to main flow]
  [IHT may be payable. We will help you work out if it is.]
- Yes → Gifts section (within HMRC_RECK1)
- Don't know yet → Save and return
  [The answer to this question will be in the deceased's will. If you do not
  yet have a copy, link: how to obtain a copy of a will.]

Note: where Q3=Yes, the home value (F) has not yet been captured. The home
page view will call HMRC_RECK2 to capture F and compute the threshold before
proceeding.

---

## Section 2: Gifts

Handled within HMRC_RECK1 (show_confirmation=False), reached after assets
questions.

### Page 1: Gifts made during the deceased's lifetime

**Guidance — IHT and gifts made during the deceased's lifetime**

IHT may be charged on assets which the deceased gave away in the last seven
years of their life. In law there are two types of such gift:

- Gifts with a Reservation of Benefit — where the deceased transferred
  ownership of an asset but continued to benefit from it (for example,
  passing ownership of a home to a child while continuing to live in it
  without paying a market rent)
- Potentially Exempt Transfers — where the deceased made a gift and kept
  no further benefit from it (for example, making a cash gift to a
  grandchild, or giving away a car and no longer using it)

Link: Full definitions and further examples

---

**Within the last seven years of their life, did the deceased make any gifts?**

Tick whichever of the following options applies:

[ ] The deceased made no gifts in the last seven years of their life
[ ] The deceased made Gifts with a Reservation of Benefit
[ ] The deceased made Potentially Exempt Transfers

Routing:
- GWR ticked (with or without PET) → END [Home page routes to main flow]
  [Gifts with a Reservation of Benefit can be complex. We will help you
  declare them properly as part of the full estate details, but we cannot
  confirm at this stage whether IHT is payable.]
- No gifts ticked → Page 2: Other additions
- PET only ticked → Page 2: Other additions (noting PET for later)

---

### Page 2: Other assets that may count as part of the estate

**Guidance — Other assets that may count as part of the estate**

In some circumstances, assets which the deceased no longer owned at the time
of their death may still need to be included in the IHT calculation. These
situations are less common than straightforward gifts, but it is important
to consider them:

- Transfers into trust — where the deceased transferred assets into a trust
  during their lifetime. These may affect the nil-rate band available to
  the estate
- Assets sold at undervalue — where the deceased sold an asset to a family
  member or close friend for significantly less than its market value. The
  difference between the sale price and the market value may count as a
  transfer of value
- Unused pension funds — from April 2027, unused pension pots will be
  brought into the estate for IHT purposes. If the deceased had unused
  pension funds at the time of their death, these may need to be declared

Link: Full definitions and further examples

---

**Did any of these situations apply to the deceased?**

○ No → END [Home page decides: not payable conclusion or HMRC_RECK3]
○ Yes → END [Home page routes to main flow]
  [Some aspects of this estate mean we cannot confirm at this stage whether
  IHT is payable. We will help you declare everything properly.]
○ I'm not sure → END [Home page routes to main flow]
  [That is fine. We will help you work through the details.]

---

## HMRC_RECK2: Home value

Single question section. Reached only when Q3=Yes and home value not yet
captured.

**Q4: What was the value of the share of the home left to direct descendants?**

Guidance: If the whole home was left to direct descendants, use the full
value of the home. If only a share was left, use that share's value. An
estate agent's estimate is fine at this stage — a formal probate valuation
is not needed yet. Link: how to get a property valuation for probate.

[Numeric input] → F

Home page calculation on return:
  Threshold = £325,000 + min(F, £175,000)
  If A ≤ Threshold → proceed to gifts/PET assessment
  If A > Threshold → main flow

- Don't know yet → Save and return
  [A formal valuation of the home will be needed for probate in any case.
  An estate agent's estimate is fine for now. Link: how to get a property
  valuation for probate.]

---

## HMRC_RECK3: PET total

Single question section. Reached only if PET ticked on gifts page and
no other additions, and A ≤ threshold.

**QP1: What was the total value of Potentially Exempt Transfers made by the
deceased in the seven years before their death?** → D1

Home page calculation on return:
  If A + D1 ≤ Threshold → CONCLUSION: Not payable
  If A + D1 > Threshold → call HMRC_RECK4

---

## HMRC_RECK4: PET 7-year breakdown

Single compound question section. Reached only if A + D1 > threshold.

**QP2: What was the value of gifts made in each of the seven years before
death?**

[Compound question — 7 components, all number type]:
  Year 1 — most recent year (year of death)
  Year 2
  Year 3
  Year 4
  Year 5
  Year 6
  Year 7 — earliest year

Home page calculation on return:
  Taper relief rates:
    Years 1-3: 100% of value counts
    Year 4:     80%
    Year 5:     60%
    Year 6:     40%
    Year 7:     20%

  D2 = sum of (year value × taper rate) for years 1-7

  If A + D2 ≤ Threshold → CONCLUSION: Not payable
  If A + D2 > Threshold → main flow

---

## Conclusions

**Not payable:**
"Based on what you have told us, IHT is not payable on the estate of [name]."

Note: This conclusion is based on the information you have provided. If
circumstances change or further assets come to light, please return to this
service.

**Main flow:**
"IHT may be payable on this estate. We will help you work through the full
details."
[Estate elements row appears on home page]

---

## Home page orchestration summary

The estate homepage view (dept_hmrc/views.py) orchestrates between sections
by reading completed answers and determining next action. The get_reckoner_state()
helper function implements this logic. Key decision points on return from each
section:

After HMRC_S2:
  HMRC_13=No → show Estate elements row (main flow)
  HMRC_13=Yes, HMRC_14=part1 or part2 → show stub message
  HMRC_13=Yes, HMRC_14=part3 → call HMRC_RECK1

After HMRC_RECK1:
  Read gifts checkbox and other additions answers:
  GWR ticked → main flow
  Other additions Yes/not sure → main flow
  No gifts, No other additions → not payable conclusion
  PET only, No other additions, Q3=Yes, no home value yet → call HMRC_RECK2
  PET only, No other additions, threshold known → call HMRC_RECK3

After HMRC_RECK2:
  Compute threshold = £325k + min(F, £175k)
  A > threshold → main flow
  A ≤ threshold → call HMRC_RECK3

After HMRC_RECK3:
  A + D1 ≤ threshold → not payable conclusion
  A + D1 > threshold → call HMRC_RECK4

After HMRC_RECK4:
  Compute D2 (tapered)
  A + D2 ≤ threshold → not payable conclusion
  A + D2 > threshold → main flow

---

## Notes and open questions

1. Save and return capability: referenced at several points — needs to be
   built or noted as a design intention for the PoC.

2. Taper relief percentages: confirmed as current (2026) but should be
   verified against HMRC published rates before production use.

3. Debts: Q1 says do not deduct debts at this stage. Debts do reduce the
   taxable estate but are deducted in the main flow, not the reckoner.
   This should be made clear to the executor before they exit via
   "not payable".

4. Charity exemption: assets passed to charity are IHT-exempt. Not
   currently handled in the reckoner — a charitable gift could reduce A.
   To consider for a future iteration.

5. Parts 1 and 2 (surviving spouse; widow/widower) still to be designed
   and documented in detail before building.

6. April 2027 pension change: included in guidance on Page 2 but not yet
   in scope for full calculation. Flag for future iteration.

7. Question IDs: this document uses design labels (Q1, Q2, Q3, Q4, QP1,
   QP2) and section IDs (HMRC_RECK1-4). Actual auto-generated question
   IDs must be confirmed from admin tools before CC work on D0.
