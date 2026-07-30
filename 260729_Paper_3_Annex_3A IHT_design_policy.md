# Annex 3A: The IHT Design — A Plain-Language Account

*Companion to Paper 3: Delivering Inheritance Tax via Core. Written for policy, operations, and senior colleagues who need to understand how the design works, without the technical routing detail needed to build it — that detail is in Annex 3B.*

---

## Idea 1: Action buttons are HMRC's design, not core's

Paper 1 made the point that core is called by a service's own home page, with the service deciding what to call, when, and in what order. Inheritance Tax is where that idea is actually put to work, and it's worth bringing to life before anything asset-specific is discussed, because it's the thing that stops this whole design from becoming one long, undifferentiated form.

The IHT home page doesn't send every executor through every possible question. It starts with a short set of tailoring questions — did the deceased own any property? Hold any pension assets? Have any business interests? — and uses the answers to build a bespoke list of action buttons, specific to that estate. An executor whose entire estate is a house and a couple of bank accounts sees two or three buttons. An executor handling a business owner's estate sees more. Nobody sees a button for an asset class that plainly doesn't apply to them.

Each action button, when clicked, calls core with exactly the ordered list of sections relevant to that one task — but the home page can, and often does, do real work of its own both before and after that call. Before calling core, the "tailor your submission" button doesn't send every executor into the same fixed set of asset questions — it first looks at what the executor has already said in answer to the earlier tailoring questions, and builds the specific list of asset schedules that actually apply to this estate. If nothing yet qualifies, it doesn't call core at all — the executor is simply returned to the home page. After core returns, the ready-reckoner button doesn't just mark itself complete — it reads the answers just given and decides what should happen next: sometimes that means sending the executor straight back into core for a further reckoner question, and sometimes it means concluding the reckoner altogether and returning to the home page with a result. Both the "what to ask" decision on the way in, and the "what happens now" decision on the way out, belong entirely to the home page. Core itself never needs to know why a particular list of sections was chosen, or what the home page plans to do once they're answered.

This entry-and-exit pattern is what makes the "not a straitjacket" argument concrete rather than theoretical. The home page stays entirely in HMRC's control — it decides the tailoring questions, the button labels, the order they appear in, and what happens between calls to core. Core's job is narrow and well-defined: process whatever list of sections it's given, and return. Nothing about IHT's design requires core to understand marital status, asset classes, or tailoring logic at all — all of that lives in the home page, exactly where the service, not the platform, should own it.

## Idea 2: Marital status and ownership work together, not in sequence

The second idea sits underneath every asset class's action button, and it's worth explaining once, here, rather than repeating it for each asset in turn.

**Where the deceased was married, and this is the first death of the couple**, assets that pass entirely to the surviving spouse attract no Inheritance Tax regardless of their value — spouse exemption applies. For these assets, the executor needs only a light pass: enough to establish what was owned and its value, so probate is accurate and HMRC has a reliable total estate figure, but nothing more. There's no need for detailed ownership follow-up, no need for valuation evidence, because no tax turns on getting that value exactly right.

**Every other asset — everything that doesn't pass entirely to the spouse, and everything in an estate where there is no surviving spouse at all (single, divorced, or the second death of a widowed person) — needs the fuller pass.** This is where ownership detail, valuation evidence, and (where relevant) substitute questions in the absence of a professional valuation all come into play, because these are exactly the assets where the value recorded actually determines the tax due.

The technical detail of how a single, shared question design achieves both of these — without asking the executor the same question twice, and without building two separate journeys through the same asset class — is set out in Annex 3B. At the policy level, the important point is simply this: **every asset gets asked about once**, and the depth of what follows depends only on where it's going. An estate passing entirely to a spouse involves almost no further questions at all. An estate with even one asset going to someone else gets the full treatment for that asset, and only that asset.

## The common shape of the fuller pass, for any asset class

Whatever the asset — a house, a bank account, a shareholding, a business interest — the fuller pass always follows the same four-part shape:

**(a) Identify the asset.** An address for property, an account number for a bank account, a company name and shareholding for a business interest — whatever identifies this specific instance, together with the executor's own reference for it if they're keeping one.

**(b) The value of the whole asset.** Always the whole thing — never a share the executor has worked out for themselves. If the asset was jointly owned, the system calculates the deceased's share and any adjustment; the executor is never asked to do that arithmetic.

**(c) How it was owned.** Sole ownership, joint ownership with automatic survivorship, or ownership in defined shares (tenants in common) — with a short follow-up only where it wasn't sole: how many others held a share, their relationship to the deceased, and what share each held.

**(d) Evidence of the value.** If a professional valuation exists, it can simply be uploaded, and nothing further is needed. If it doesn't, HMRC needs a small number of substitute questions to satisfy itself the value given is reasonable — these substitute questions are specific to the asset class (a property's lease length or any damage affecting value; a business's turnover or accounts, say), but the underlying "was there a valuation" branch is the same question, asked the same way, for every asset class.

This four-part shape is what every conditional table on the IHT service is built from. It doesn't change asset to asset; only the fine detail within part (d) does.

## A brief illustration: property

Property is the asset class that exercises every part of this shape, plus one extra: whether the deceased owned and lived in the property at any point, which determines whether it's relevant to the residence nil-rate band. In outline: the executor gives the address, says whether the whole property or a share was owned, gives the whole property's value, and either uploads a valuation or answers a short set of questions about lease terms and any damage. Everything downstream — the deceased's proportionate share, any discount for a shared interest, and the residence nil-rate band calculation — is worked out by the system, not the executor.

This is one illustration, not an exhaustive tour of every asset class HMRC needs to cover. The full, asset-by-asset technical detail — including exactly how the marital-status and ownership questions combine into a single routing design without duplication — is in Annex 3B.
