# Paper 2: What's Wrong With IHT Data Gathering Today

*A short policy paper for HMRC's Inheritance Tax policy and operations teams. This paper makes a case that stands on its own tax-administration merits, independent of any proposal about how HMRC builds its digital services — see Paper 1 for that separate argument, and Paper 3 for how the two combine in a concrete design.*

---

## The problem

Inheritance Tax touches almost every estate in the country, but very few of them ever pay it. The current approach to data gathering — on paper and in HMRC's existing digital forms alike — was built around the estates that do pay: substantial, often complex, frequently disputed. That estate is real, but it is not the typical one. The typical estate is smaller, usually leaves everything to a surviving spouse, and owes nothing. The forms don't distinguish well between these two cases, and three specific consequences follow from that.

## Problem 1: the transferable-allowance time bomb

When one member of a married couple dies leaving everything, or most things, to the survivor, spouse exemption means no Inheritance Tax is due — regardless of the estate's value. What *does* matter, often decades later, is what percentage of the deceased's nil-rate band and residence nil-rate band went unused at that first death, because that percentage transfers to the survivor's own estate and can materially affect whether tax is due at the second death.

Capturing that percentage accurately requires knowing, at the first death, what passed to the spouse and what didn't. But because the first death itself usually attracts no tax, there is limited institutional pressure to gather that information carefully — and no natural point in the current process where a lightweight, low-friction capture of exactly this fact happens. The result is a gap: either the percentage isn't captured at all, and the second-death executor — sometimes acting decades later, often without access to the first executor's papers, sometimes not even aware the first estate was ever formally recorded — has no reliable starting point; or capturing it properly requires running the low-value first estate through the same heavyweight process built for the estates that do pay tax, which is disproportionate to what that estate actually needs.

Either way, the citizen and HMRC both lose. The citizen faces uncertainty or unnecessary paperwork decades after a bereavement they've long since moved past. HMRC risks either incorrect transferable-allowance calculations at the second death, or handling second-death claims with no first-death record to check them against.

## Problem 2: the sole-ownership bias

HMRC's existing forms — IHT404 for joint assets, IHT405 for property, and their equivalents — are built outward from sole ownership as the default case, with detailed provision for valuation, lease terms, damage, special factors, and so on. Joint ownership and survivorship are treated as a variant, with a comparatively thin set of questions layered on top of the sole-ownership base.

In practice, for the ordinary estate, this is close to backwards. The family home held jointly with a spouse, passing by survivorship; a joint bank account; jointly-held investments — these are the common pattern, not the exception, for the estates that don't owe tax and where full valuation rigour serves no purpose. Meanwhile, the estates where sole ownership genuinely predominates — where full valuation detail, lease terms and special factors actually matter — are disproportionately the larger, more complex estates that were always going to need careful handling regardless of how the form is structured.

The consequence is a form that asks its most detailed, effortful questions of executors who least need to answer them in full, while treating the executor's actual, common situation — joint ownership, survivorship, spouse exemption — as an afterthought bolted onto a sole-ownership base. This isn't just an efficiency loss for executors; it also means HMRC's own attention, embedded in the form's structure, is weighted toward the estates least likely to need it and least well-suited to the estates that do.

## Problem 3: the reckoner captures nothing

Before an executor commits to a full IHT return, HMRC offers a ready reckoner — a shorter set of questions intended to indicate whether a full return, and any tax, is likely to be needed at all. As currently built, this journey is unauthenticated: an executor can work through it, reach a conclusion, and none of it persists. If they leave and come back, they start again. If the reckoner's answer later needs to inform the full return, there's no record connecting the two — the executor re-enters, from scratch, information they've already given once.

This is a smaller problem than the first two in scale, but it's diagnostically the same problem: effort the executor has already spent is discarded rather than carried forward, at exactly the point — the very first thing most executors do — where a foundation for everything that follows would have the most value.

## The common thread

All three problems share one root cause: **the current design throws away information the executor has already given, at exactly the points where continuity would matter most** — across the two-death gap in Problem 1, across the ownership/valuation weighting within a single estate in Problem 2, and across a single session boundary in Problem 3. None of these are digital-delivery problems in the first instance; they are problems with what HMRC has decided to ask, and when, independent of the channel used to ask it. A paper form with the same structure would have the same three flaws.

## What this implies for the executor journey

Fixing this doesn't require abandoning any of HMRC's existing data requirements — everything HMRC currently needs to know in order to assess IHT correctly is still needed. What changes is the *shape* of the journey:

- A first death within a marriage should have a genuinely lightweight path for assets passing entirely to the surviving spouse — itemised well enough to support probate and a correct total estate value, but without the full valuation-evidence machinery that only matters where tax is actually at stake — with the resulting transferable-allowance detail captured and held in a form the second-death journey can actually use.
- Ownership type should be established once, early, for every asset — not bolted on as an afterthought — with the executor's answer determining how much further detail is genuinely needed, rather than assuming sole ownership and full detail as the default.
- Whatever an executor tells the reckoner should be the same, persisted answers that carry forward into the full return, not a disposable side-journey that has to be repeated.

Paper 3 sets out a concrete design that achieves all three, using HMRC's existing tax rules exactly as they stand — nothing here proposes any change to what qualifies for spouse exemption, how transferable allowances are calculated, or what constitutes a taxable estate. It is worth noting, separately, that a platform capable of persistent, structured, branching data capture — such as the one proposed in Paper 1 — would make this restructuring straightforward to build and maintain. But the case above does not depend on it: the same restructuring could, in principle, be built the conventional way, at greater cost and with less flexibility to amend as policy evolves. The problems are real regardless of how HMRC chooses to fix them.
