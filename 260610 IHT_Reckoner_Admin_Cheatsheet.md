# IHT Reckoner — Admin Configuration Cheat Sheet
## Questions, Sections and Routing to enter via /hmrc/tools/

Date: June 2026 (updated 10 June 2026)
Status: Working draft

---

## Overview

Four sections, all under regime HMRC_IHT.
No schedule wrapper — sections called directly from the estate homepage.
All routing ends in END (NULL next_node). The home page view reads answers
on return and decides what to show or call next.

IMPORTANT: HMRC_S2 (Estate Ready Reckoner entry) is already built and wired.
It contains HMRC_13 (need help?) and HMRC_14 (marital status). Do not recreate.
The sections below (HMRC_RECK1-4) are the reckoner detail sections for Part 3.

Section IDs:
  HMRC_RECK1  — Assets + Gifts navigation (show_confirmation=False)
  HMRC_RECK2  — Home value
  HMRC_RECK3  — Total PET value
  HMRC_RECK4  — PET 7-year breakdown (compound question)

---

## What is already built

HMRC_S2 — complete and wired to home page:
  HMRC_13: Do you need help? (radio: yes/no)
  HMRC_14: Marital status (radio: part1/part2/part3)
  Routing: HMRC_13=yes → HMRC_14 → END; HMRC_13=no → END

Tier 1 scalar routing: comparator and threshold_value fields now on
Routing model. Admin tools routing UI shows comparator+scalar inputs
for number/compound questions automatically.

show_confirmation flag: now on Section model. Uncheck for navigation
sections. HMRC_RECK1 should have show_confirmation=False.

Compound question type: now available. Use for HMRC_RECK4.

---

## Questions to create for HMRC_RECK1

All HMRC dept questions (is_platform=False). Note auto-generated IDs.
Placeholder IDs below (HMRC_Rx) — replace with actual IDs when entered.

---

**HMRC_R1: Were the total assets of the deceased worth more than £325,000
at the time of their death?**
  Type: radio
  Options:
    no         — No
    yes        — Yes
    dont_know  — I don't know yet
  Guidance: Include everything owned — money in bank accounts, savings,
  investments, personal possessions, vehicles, and any property or land.
  Do not deduct any debts or mortgages at this stage.

---

**HMRC_R2: Did the deceased own a home, or a share of a home, at the time
of their death?**
  Type: radio
  Options:
    no   — No
    yes  — Yes
  Guidance: This includes a home they may have moved out of — for example
  if they were living in a care home or hospital at the time of death.

---

**HMRC_R3: Was any part of that home left to a direct descendant — for
example a child, grandchild, or stepchild?**
  Type: radio
  Options:
    no         — No
    yes        — Yes
    dont_know  — I don't know yet
  Guidance: [Link: full list of who counts as a direct descendant]

---

**HMRC_R4: Within the last seven years of their life, did the deceased
make any gifts?**
  Type: checkbox
  Options:
    none  — The deceased made no gifts in the last seven years of their life
    gwr   — The deceased made Gifts with a Reservation of Benefit
    pet   — The deceased made Potentially Exempt Transfers
  Guidance title: IHT and gifts made during the deceased's lifetime
  Guidance: IHT may be charged on assets which the deceased gave away in
  the last seven years of their life. In law there are two types of such gift:
  - Gifts with a Reservation of Benefit — where the deceased transferred
    ownership of an asset but continued to benefit from it (for example,
    passing ownership of a home to a child while continuing to live in it
    without paying a market rent)
  - Potentially Exempt Transfers — where the deceased made a gift and kept
    no further benefit from it (for example, making a cash gift to a
    grandchild, or giving away a car and no longer using it)
  [Link: Full definitions and further examples]

---

**HMRC_R5: Did any of these situations apply to the deceased?**
  Type: radio
  Options:
    no        — No
    yes       — Yes
    not_sure  — I'm not sure
  Guidance title: Other assets that may count as part of the estate
  Guidance: In some circumstances, assets which the deceased no longer owned
  at the time of their death may still need to be included in the IHT
  calculation. These situations are less common than straightforward gifts,
  but it is important to consider them:
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
  [Link: Full definitions and further examples]

---

## Questions to create for HMRC_RECK2

**HMRC_R6: What was the value of the share of the home left to direct
descendants?**
  Type: number
  Guidance: If the whole home was left to direct descendants, use the full
  value of the home. If only a share was left, use that share's value.
  An estate agent's estimate is fine at this stage — a formal probate
  valuation is not needed yet.
  [Link: how to get a property valuation for probate]
  Hint: Enter the value in pounds. For example, 250000 for £250,000.

---

## Questions to create for HMRC_RECK3

**HMRC_R7: What was the total value of Potentially Exempt Transfers made
by the deceased in the seven years before their death?**
  Type: number
  Guidance: Include the total value of all outright gifts — cash payments,
  assets transferred, and any other gifts where the deceased kept no further
  benefit. Do not include Gifts with a Reservation of Benefit.
  Hint: Enter the value in pounds. If you are not sure of the exact total,
  use your best estimate.

---

## Questions to create for HMRC_RECK4

**HMRC_R8: What was the value of gifts made in each of the seven years
before the deceased's death?**
  Type: compound
  Components (use compound builder wizard):
    Year 1 — most recent year (year of death)   type: number
    Year 2                                       type: number
    Year 3                                       type: number
    Year 4                                       type: number
    Year 5                                       type: number
    Year 6                                       type: number
    Year 7 — earliest year                       type: number
  Guidance: Enter 0 for any year in which no gifts were made. Taper relief
  will be applied automatically — you do not need to calculate it.
  Hint: Enter values in pounds.

  Note: Taper relief rates applied by home page view:
    Years 1-3: 100% of value counts
    Year 4:     80%
    Year 5:     60%
    Year 6:     40%
    Year 7:     20%

---

## Sections to create

### HMRC_RECK1
  Section name: IHT Reckoner — Assets and gifts
  Regime:       HMRC_IHT
  Schedule:     none
  show_confirmation: False (uncheck the box)
  First node:   HMRC_R1 (actual ID — confirm from admin tools)

### HMRC_RECK2
  Section name: IHT Reckoner — Home value
  Regime:       HMRC_IHT
  Schedule:     none
  show_confirmation: True (default)
  First node:   HMRC_R6 (actual ID — confirm from admin tools)

### HMRC_RECK3
  Section name: IHT Reckoner — Total PET value
  Regime:       HMRC_IHT
  Schedule:     none
  show_confirmation: True (default)
  First node:   HMRC_R7 (actual ID — confirm from admin tools)

### HMRC_RECK4
  Section name: IHT Reckoner — PET 7-year breakdown
  Regime:       HMRC_IHT
  Schedule:     none
  show_confirmation: True (default)
  First node:   HMRC_R8 (actual ID — confirm from admin tools)

---

## Routing to enter for HMRC_RECK1

Enter after all questions created and IDs confirmed.
All MAIN_FLOW exits → END (NULL next_node). Home page view reads
answers on return and determines whether to show main flow or continue.

Using actual question IDs (replace HMRC_Rx with real IDs):

  HMRC_R1 = no         → END   (assets ≤ £325k → gifts section)
  HMRC_R1 = yes        → HMRC_R2
  HMRC_R1 = dont_know  → END   (save and return)

  HMRC_R2 = no         → END   (no home, assets > £325k → home page → main flow)
  HMRC_R2 = yes        → HMRC_R3

  HMRC_R3 = no         → END   (home not left to descendants → home page → main flow)
  HMRC_R3 = yes        → HMRC_R4
  HMRC_R3 = dont_know  → END   (save and return)

  HMRC_R4 contains gwr → END   (GWR → home page → main flow immediately)
  HMRC_R4 = none       → HMRC_R5
  HMRC_R4 contains pet → HMRC_R5

  Note: GWR routing (contains gwr) must take priority over none/pet routing.
  Enter GWR condition first so it is evaluated first.

  HMRC_R5 = no         → END   (no other additions → home page decides)
  HMRC_R5 = yes        → END   (other additions → home page → main flow)
  HMRC_R5 = not_sure   → END   (not sure → home page → main flow)

---

## Routing for HMRC_RECK2, RECK3, RECK4

Single question sections — no branching routing needed.
Each question simply → END (NULL next_node).
The section engine captures the answer and returns to home page.

---

## Home page view logic (for CC reference)

After HMRC_RECK1 completes, home page view reads:
  HMRC_R1 answer (assets bracket: no/yes/dont_know)
  HMRC_R2 answer (has home: no/yes)
  HMRC_R3 answer (home to descendants: no/yes/dont_know)
  HMRC_R4 answer (gifts checkbox: none/gwr/pet — may be multiple)
  HMRC_R5 answer (other additions: no/yes/not_sure)

And determines:
  GWR in R4, or R5=yes/not_sure → main flow
  R2=no → main flow (assets > £325k, no home)
  R3=no → main flow (home not to descendants)
  R1=no and no gifts → not payable conclusion
  R1=no and pet only and R5=no → call HMRC_RECK3
  R3=yes and home value not yet captured → call HMRC_RECK2
  After RECK2: compute threshold, compare A, route accordingly
  After RECK3: A + D1 vs threshold → not payable or call RECK4
  After RECK4: compute D2 (tapered), A + D2 vs threshold → conclusion

Full specification in IHT_Reckoner_Part3_Flow.md.

---

## Notes

1. Confirm all actual question IDs from admin tools before entering routing.
   Placeholder IDs (HMRC_R1-R8) in this document are for reference only.

2. HMRC_RECK1 must be assigned to HMRC_IHT regime or it will not appear
   in get_permitted_sections. Check regime assignment immediately after
   creating each section.

3. Parts 1 and 2 (married/widowed) not yet built. HMRC_S2 currently routes
   part1 and part2 to a stub message on the home page.

4. Save and return: referenced in Q1 and Q3 guidance. Not yet implemented
   as a formal feature — treat as a design intention for now.

5. Taper relief is computed by the home page view, not by routing.
   The executor does not see taper calculations — only the conclusion.
