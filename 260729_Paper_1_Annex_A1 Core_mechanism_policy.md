# Annex A1: The Core Mechanism — A Plain-Language Account

*Companion to Paper 1: The Case for Core. Written for policy, operations, and senior colleagues who need to understand how the mechanism works, without the technical detail needed to build it — that detail is in Annex A2.*

---

## Three kinds of question, one engine

Looking closely at HMRC's own forms — Inheritance Tax, Self Assessment, Duty Deferment Authorisations, and others — the same three patterns recur again and again, often on the same form.

**First, single-answer questions.** "Did the deceased leave a will?" Most questions are like this: one question, one answer. Often the next question depends on the answer just given — only someone who answered "yes" is then asked to attach a copy of the will. Different users take different routes through the same underlying set of questions, depending on their circumstances.

**Second, questions with more than one answer — simple tables.** "For each executor named in the will, please give their full name, address, and contact details." Here every column has to be filled in for every row, and there's usually no conditionality within the row — the questions asked are the same whether it's the first executor or the third.

**Third, and less common: conditional tables.** IHT405's property section is a good example. If a property is leased, there are extra questions about the lease. If it's been damaged, there are extra questions about insurance cover. Each row can take a different path depending on what's already been answered on that row. This is genuinely a hybrid of the first two patterns: the multiple-rows structure of a simple table, combined with the branching of a single-answer question, applied independently within each row.

A single engine can be built to handle all three patterns as configuration, not bespoke code — each one becomes a "section type," and a service is built by assembling sections of the right type for each part of the form.

## What drives it: two simple tables

The engine is driven by service data held in two straightforward, tabular objects — one holding the questions, one holding the routing between them. Because both are plain data, not code, they are easy to inspect and easy to amend. A policy analyst can read the routing table and understand exactly which answer sends a citizen down which path. A change to a question's wording, or to a branching condition, is a data edit — not a development ticket.

This matters for HMRC specifically because tax and compliance policy changes far more often than any development team can comfortably rebuild screens for. A question set built this way can be tested, amended, and re-tested by policy and compliance teams directly, without a digital team standing up a new build for every change.

## Confirming answers, not just capturing them

Every logical group of questions ends with a confirmation screen: a single page playing back everything just entered, letting the user amend any answer before moving on. This is standard Government Digital Service practice for one-question-per-page journeys, but it has one important consequence worth spelling out: if a user changes an earlier answer that affects routing, everything downstream of that answer needs to be re-asked, since the route itself may have changed. The system handles this automatically — the user is taken back through whatever new or removed questions the changed answer implies, and the confirmation screen updates to show only what was actually most recently asked.

For simple tables, the pattern differs slightly: rather than a single confirmation screen, the user sees a "landing page" showing how many records have been entered, with the option to view, amend, delete, or add another — and, importantly, the ability to say the table is complete, since only the user knows how many entries are actually needed. Conditional tables use the same landing-page pattern, but with a simplified summary view for each row (for example, just the address and value for a property), with a link through to the full detail where more was asked.

## Re-using data, carefully

It's often suggested that citizens should only need to tell government something once — an address, say — and that a service should then simply reuse it elsewhere. There's real value in this, but it needs handling carefully, and HMRC should be cautious about how far to take it.

The distinction that matters is between **relying** on previously-given information and **offering it back as a suggestion**. Reliance would mean skipping a question entirely because the answer is already known elsewhere — which risks acting on data that may no longer be accurate, and removes the citizen's opportunity to correct it. The approach proposed here is different: where a previous answer to the same question exists, it is offered back as a pre-filled suggestion, but the citizen is always asked to positively confirm that it still reflects their current circumstances before it's recorded. Every answer in the system is, in this sense, freshly given — even when it happens to match what was said before.

This preserves both the convenience of not re-typing everything, and the accuracy that comes from always asking rather than assuming.

## The service home page stays in charge

The engine does not replace the service's own home page — it sits underneath it, called on demand. At its simplest, a home page could have a single "Start" button that hands the whole question set over to the engine and gets the user back at the end. In practice, for a service like Inheritance Tax, it's more useful for the service designer to build a series of action buttons — each calling the engine for just one part of the journey. Answering a first, short set of "tailoring" questions ("did the deceased own a property? hold pension assets?") lets the home page then generate exactly the further action buttons that estate actually needs, rather than presenting every possible question to every user regardless of relevance.

This division of responsibility has one further, important benefit: the service designer is never trapped by the engine. If a particular combination of questions doesn't fit the three section types cleanly, the designer can simply build that one screen directly, as they would today, and drop back into the engine for everything else. The engine is a genuine time-saver for the great majority of a service's data-gathering needs — it is not a straitjacket for the exceptions.
