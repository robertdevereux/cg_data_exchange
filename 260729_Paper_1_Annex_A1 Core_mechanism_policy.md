# Annex A1: The Core Mechanism — A Plain-Language Account

*Companion to Paper 1: The Case for Core. Written for policy, operations, and senior colleagues who need to understand how the mechanism works, without the technical detail needed to build it — that detail is in Annex A2.*

---

## Three kinds of questions on HMRC forms

Looking closely at HMRC's own forms — Inheritance Tax, Self Assessment, Duty Deferment Authorisations, and others — the same three patterns recur again and again, often on the same form.

First, **Single Answer questions**. "Did the deceased leave a will?" Many questions are like this: one question, one answer. Often the next question depends on the answer just given: only someone who answered "yes" to a will is then asked to upload a copy of the will. Different users take different routes through the same underlying set of questions, depending on their circumstances.

Second, **Simple Tables: questions with more than one answer.** "For each executor named in the will, please give their full name, address, and contact details." Here the same set of questions (each a column) has to be answered for each executor (each a row). There's no conditionality within the row — the questions asked are the same whether it's the first executor or the third.

Third, **Conditional Tables: questions with more than one answer, but with conditional routing through those questions.** IHT405's property section is a good example. If a property is leased, there are extra questions about the lease. If it's been damaged, there are extra questions about insurance cover. Each row can take a different path depending on what's already been answered on that row. This is genuinely a hybrid of the first two patterns: the multiple-rows structure of a simple table, combined with the branching of a single-answer question, applied independently within each row.

A typical HMRC paper form includes two, and sometimes all three, of these types of questions. A digital journey collecting the same data can be comprised of different Sections, each of a single question type. For example, using IHT,
- an initial section with Single Answer questions (eg details of the deceased)
- a Simple Table (eg contact details for each Executor)
- a Conditional Table (eg for Property details)
- a Conditional Table (eg for another asset)
- and so on.

## Confirming answers, when routing is conditional on answers provided

As the end of each logical group of Single Answer questions, the standard Government Digital Service practice is to generate a confirmation screen: a single page playing back everything just entered, allowing the user either to confirm their entries, or to make amendments. 

But Single Answer sections allow the routing to be conditional on the answers provided. So changing one answer could trigger a different route from that question onwards. The engine handles this automatically. When a user chooses to amend, say, the third answer on ther confirmation screen, they are taken to the question page for that question. Once that answer is amended, the user is then taken through  each subsequent question which the routing now defines (given the new answer to the third questions). Where a question has already been answered, the answer is pre-populated with the previous answer to save time. At the end of the new route, the confirmation screen is shown again, only for the questions asked on the new route.

The engine operates in the same way for each row of a Conditional Table.

For simple tables, confirmation screens are not used. For any one row, the set of questions appears on one page by design. The user effectivly confirms their entry when they choose to add a new row. Adding a confirmation screen for each row is unecessary, and likely to irritate users. 

## Digital forms organised by question type 

Many HMRC paper forms combine two or more of these three types of questions. 

The sames can be achieved for digital forms, combining various Sections, each Section focused  
- either on a logical group of less than (say) 15 Single Answer questions;
- or a Simple Table; 
- or a Conditional Table


 can separate out, as separate Sections, questions all of which have the same type. For example, an existing paper form might The utility works differentlyA single engine can handle all three patterns as configuration, not bespoke code.  — each one becomes a "section type," and a service is built by assembling "sections" of the right type for each part of the form.

## What drives the engine: two simple data objects

The engine is driven by data held in two tabular data objects — one holding the questions, one holding the routing between them. Because both are plain data, not code, they are easy to inspect and easy to amend. A policy analyst can read the routing table and understand exactly which answer sends a citizen down which path. A change to a question's wording, or to a branching condition, is a data edit — not a development ticket.

## The service home page stays in charge

The engine does not replace the service's own home page — it sits underneath it, called on demand. At its simplest, a home page could have a single "Start" button that hands the whole question set over to the engine and gets the user back at the end. 

In practice, for a service like Inheritance Tax, it's more useful for the service designer to build a series of action buttons — each calling the engine for just one part of the journey. Answering a first, short set of "tailoring" questions ("did the deceased own a property? hold pension assets?") lets the home page then generate exactly the further action buttons that estate actually needs, rather than presenting every possible question to every user regardless of relevance.

This division of responsibility has one further, important benefit: the service designer is never trapped by the engine. If a particular combination of questions doesn't fit the three section types cleanly, the designer can simply build that one screen directly, as they would today, and drop back into the engine for everything else. The engine is a genuine time-saver for the great majority of a service's data-gathering needs — it is not a straitjacket for the exceptions.


## Re-using data, carefully

It's often suggested that citizens should only need to tell government something once — an address, say — and that a service should then simply reuse it elsewhere. There's real value in this, but it needs handling carefully, and HMRC should be cautious about how far to take it.

The distinction that matters is between **relying** on previously-given information and **offering it back as a suggestion**. Reliance would mean skipping a question entirely because the answer is already known elsewhere — which risks acting on data that may no longer be accurate, and removes the citizen's opportunity to correct it. The approach proposed here is different: where a previous answer to the same question exists, it is offered back as a pre-filled suggestion, but the citizen is always asked to positively confirm that it still reflects their current circumstances before it's recorded. Every answer in the system is, in this sense, freshly given — even when it happens to match what was said before.

This preserves both the convenience of not re-typing everything, and the accuracy that comes from always asking rather than assuming.


## Two types of landing page

Sections comprised of Single-answer questions start with the first question, on its own page, followed by successive pages reflecting the conditionality defined.

Simple and conditional tables need a different treatment. Here a section starts by showing the user the records already defined (if any), and allows the user to add a new record, or to view/amend or delete an existing record.

For conditional tables, 