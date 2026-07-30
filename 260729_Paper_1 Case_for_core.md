# Paper 1: The Case for Core

*A short proposal for HMRC policy and digital leadership. Detail is carried in two annexes: Annex A1 (a plain-language account of how the mechanism works) and Annex A2 (the technical specification for digital and data architects).*

---

## The problem

Almost every tax and customs process HMRC operates depends on getting data from the taxpayer, trader, or their agent. Inheritance Tax alone runs to as many as a dozen potential schedules, most built from multiple sections, each with many questions. A Duty Deferment Authorisation application is similarly structured — multiple sections, each with many questions. The exceptions prove the rule: VAT now reports directly from accounting systems under Making Tax Digital, and most PAYE employees never complete a return at all. Everywhere else, HMRC still asks, and still has to build the asking.

Building that asking is slow and expensive. Every question, every page, is currently hand-crafted by specialist developers and designers — for every service, from scratch. Once built, services are just as slow and expensive to amend, even though tax and compliance policy changes far more often than any development team can comfortably keep pace with. The result is a familiar bind: policy teams depend on digital intermediaries for even modest changes, delivery timescales stretch, and citizens experience forms that don't reflect what's actually happened to them.

## What HMRC's Transformation Goals require

Whatever specific services are built next, HMRC needs data-gathering that can be:

- **set up quickly** — a new question set stood up in days, not a development sprint;
- **maintained easily** — amended directly by policy and compliance teams as rules and guidance change, and in response to user feedback;
- **testable by policy and compliance teams themselves** — without needing to stand up a new digital team to trial a new question or a new route through existing ones;
- **ready for AI-assisted support** — for both staff and citizens — without a further rebuild when that capability arrives;
- **consistent with HMRC's own platform principles** — to Adopt rather than Adapt its E-CRM platform, and to reuse capability across the enterprise rather than rebuild it service by service.

Gov.UK Forms, with its form builder used repeatedly to create one simple form per service, doesn't reach this bar. It is built for services that ask one thing at a time, in a fixed sequence, with no meaningful branching or repeated structure. Most of HMRC's own forms are more demanding than that: they mix single-answer questions, repeating record sets, and questions whose follow-ups depend on what's already been said about that specific record. None of that is well served by a tool built for the simpler case.

## The proposal

Rather than a form builder, this paper proposes a single configurable **utility** capable of handling all three patterns HMRC's forms actually contain — plain single-answer questions with conditional routing, simple repeating tables, and conditional tables where a table row's own follow-up questions depend on what's already been answered for that row. Annex A1 sets out how this works in plain terms, with worked examples from an Inheritance Tax return. Annex A2 sets out the underlying technical architecture — the data model, the routing engine, and the design choices behind it — for digital and data architects to assess.

The utility does not replace the service's own front door. Each service keeps **its own home page**, under HMRC's direct control, and calls the utility only for the parts of the journey the utility is well suited to. A service designer can build a first, short set of tailoring questions ("did the deceased own a property? hold pension assets?") to work out which further action buttons an individual case actually needs — and can always drop out of the utility to hand-build a screen directly, for the cases that don't fit its three patterns cleanly. The utility is a genuine accelerant for the great majority of a service's data-gathering needs; it is deliberately not a straitjacket for the rest.

## The scale of the prize

The case above applies to any HMRC process that gathers structured data from a taxpayer, trader, or agent — which is most of them. Inheritance Tax is the proving ground: it exercises every pattern the utility needs to handle, at realistic complexity, with a clear near-term delivery deadline. But the same utility, once built and proven, applies directly to Self Assessment schedules, customs authorisations, and every other HMRC service currently built the hand-crafted way. This is not a proposal to solve Inheritance Tax's data-gathering problem; it is a proposal to solve HMRC's, using Inheritance Tax as the first, well-understood test case.

## The timing

Inheritance Tax has a realistic delivery target of a private beta from around April 2027. That timescale forces a choice now, not later. HMRC can make a small number of "good enough for now" design decisions and build the IHT proof of concept directly on the approach set out here — or it can build every IHT screen the conventional way, and accept the rework later needed to bring IHT onto the utility once it exists, on top of whatever further rework AI-assisted support will itself require.

## The ask

A short session — a day or two — with the relevant HMRC policy and digital colleagues, to test appetite for this approach before either path is committed to. Annexes A1 and A2 are offered as the basis for that conversation.
