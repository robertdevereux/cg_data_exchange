# Paper 3: Delivering Inheritance Tax via Core

*A short paper for HMRC's Inheritance Tax policy, operations, and digital leadership. Detail is carried in two annexes: Annex 3A (a plain-language account of the design, with a worked example) and Annex 3B (the technical specification for digital and data architects and policy analysts configuring the routing).*

---

## The premise

Paper 1 makes the case for a single configurable utility, called by a service's own home page, capable of handling the three logically different question patterns that make up almost any HMRC form. Paper 2 sets out three specific ways HMRC's current approach to Inheritance Tax data gathering falls short — a transferable-allowance time bomb spanning two deaths, a form structure biased toward sole ownership when joint ownership and survivorship are the common case, and a ready reckoner that captures nothing an executor can build on.

This paper shows that the two combine directly: the utility described in Paper 1 is capable of implementing the restructured IHT journey that Paper 2's diagnosis calls for, without any change to the underlying tax rules, and without inventing anything beyond what Paper 1 already proposed. Nothing here depends on Paper 1 being approved in principle before Paper 2's problems can be discussed — but if it is, Inheritance Tax is where that approval pays off first.

## The design, in outline

Two ideas do almost all the work, and both are explained fully, with worked examples, in Annex 3A.

**The home page stays in charge.** The IHT home page starts with a short set of tailoring questions and builds a bespoke list of action buttons specific to each estate — no executor sees a question that plainly doesn't apply to them. Each button calls the utility with exactly the sections that task needs, and gets control back once they're answered, free to decide what to show next. Some of this decision-making happens *before* the utility is called — working out which asset schedules actually apply to this estate, say — and some happens *after* — deciding whether a reckoner answer needs a further question or is enough to conclude. Both are demonstrated in the system as it stands today, not proposed as future work.

**Marital status and ownership work together, once, per asset.** Every asset an executor records is asked about exactly once, through a single shared design. Where the deceased was married and this is the first death, an extra branch determines whether the recorded value needs anything further: if the asset passes entirely to the surviving spouse, the executor's work on it ends there — no ownership follow-up, no valuation evidence, since no tax turns on getting the figure precisely right. Everything else — including every asset in an estate with no surviving spouse — gets the fuller treatment: how it was owned, its value, and evidence for that value, using a shape that's identical across property, bank accounts, shares, and business interests, varying only in the fine detail of what counts as evidence for each.

## How this answers Paper 2's three problems

**The transferable-allowance time bomb.** Because every spouse-bound asset is still individually recorded — just without the follow-up questions that only matter where tax is at stake — the first death produces a genuine, itemised record of what passed to the spouse, not merely a percentage. That record is available, in principle, to make the second-death executor's task easier decades later, rather than leaving them to start from nothing (Annex 3B, §4).

**The sole-ownership bias.** Ownership type is established for every asset, early, as a matter of course — not bolted on as an afterthought to a sole-ownership base. An executor whose estate is entirely joint accounts and a jointly-owned home answers the ownership question once per asset and, in the common first-death case, is often done there. An executor with a more complex, sole-ownership estate gets exactly the fuller treatment that estate actually needs. Neither case is structurally privileged over the other by the design of the form (Annex 3B, §§1–2).

**The reckoner captures nothing.** Every question asked through the utility, from the very first tailoring question onward, is a confirmed, persisted answer — there is no separate "reckoner mode" whose results are disposable by design. An executor who starts with the reckoner and later needs the full return is continuing the same record, not starting a second one.

## What this doesn't change

Nothing in this design alters what qualifies for spouse exemption, how transferable allowances are calculated, what constitutes a taxable estate, or any other point of tax policy. It changes only the shape and sequence of the questions HMRC asks in order to establish the facts it already needs — which is precisely the scope Paper 2 argued for.

## What's still open

Two things are flagged, not resolved, in Annex 3B: exactly which valuation-evidence questions apply to each asset class beyond property (a policy configuration exercise, not a design question), and whether the second-death journey should actively surface the first death's itemised record to the executor, or only its resulting percentage — the former is more helpful but raises a cross-case data consent question worth settling with HMRC explicitly before it's built.

## The ask

The same short session proposed in Paper 1 can cover this ground alongside it: Inheritance Tax as the proving case for both the utility itself and the specific data-gathering restructuring Paper 2 argues HMRC should make regardless. Annexes 3A and 3B are offered as the basis for that part of the conversation.
