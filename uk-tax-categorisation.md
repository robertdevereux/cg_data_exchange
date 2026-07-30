# UK Tax & Duty Categorisation — Registration and Declaration Mechanisms

A broad-brush taxonomy of how individuals and organisations register (if at all) and declare information for UK taxes/duties, categorised by *mechanism* rather than by tax head. Excludes nothing this time — VAT and Corporation Tax are explicitly placed.

---

## A — Income-related taxes on individuals
**PAYE/NIC, self-assessment, CGT, and MTD ITSA** — treated as one family: withheld in real time (PAYE/NIC), declared annually after the fact (self-assessment), or increasingly reported quarterly (MTD ITSA, from April 2026 for qualifying sole traders/landlords), depending on the type of income involved.

**Carve-out:** CGT on UK residential property doesn't follow this family's rhythm — it's a 60-day, event-triggered return filed shortly after completion, and belongs mechanically with B1 instead.

---

## B — Mandatory non-tax "gateway" forces discovery of the obligation
The common feature: nobody has to separately notice a filing duty exists, because the tax obligation is welded onto a process you're already going through for non-tax reasons (conveyancing, probate, customs clearance, trade settlement, vehicle/property registration).

### B1 — Gateway forces discovery; taxpayer/agent still computes the liability
SDLT, Stamp Duty/SDRT, IHT on death, Customs Duty (via CDS), residential property CGT.
*Someone still has to work out the figure — reliefs, valuations, tariff classification, gains — but the obligation to engage is unavoidable because it rides on the underlying transaction (buying a property, a death and probate, importing goods, settling a trade).*

### B2 — Gateway forces discovery; the state also computes the liability
VED, Council Tax, Business Rates.
*The state (DVLA, VOA/local authority) holds the relevant facts and sets the liability itself; the taxpayer's only obligation is to notify a change of status. Nothing to compute, nothing to declare in the usual sense.*

---

## C — No forcing gateway: register on starting an activity or crossing a threshold, then self-assess periodically
No unavoidable third-party process surfaces the obligation — the taxpayer has to notice it's in scope, register, and then periodically report the facts that determine liability, entirely on its own initiative.

### C1 — VAT
Same registration/periodic-return shape as C2, but singled out because it's the one member that's actually been digitised: MTD started here in 2019 and it's the only fully mandatory, fully bedded-in case.

### C2 — Everything else on the "notice, register, self-assess periodically" model
Corporation Tax, Insurance Premium Tax, Air Passenger Duty, Landfill Tax, Aggregates Levy, Climate Change Levy, Plastic Packaging Tax, Soft Drinks Industry Levy, Bank Levy, Digital Services Tax, Economic Crime Levy, ATED, the excise duties (alcohol/tobacco/hydrocarbon oils, with EMCS layered on top for movement tracking), and the gambling duties.

*No consistent digitisation story, and — per HMRC's July 2025 decision to scrap MTD for Corporation Tax — no near-term prospect of one. Part of the reason: most of these taxes' underlying data (tonnage, litres, passenger-miles, premiums, energy units) isn't ledger-shaped the way VAT's and CT's is, so an MTD-style bridge from ordinary accounting software wouldn't naturally capture it even if HMRC did extend the programme.*

---

## Notes for future refinement
- The line between families is drawn **per-charge, not per-tax-head** — CGT and IHT each split across two families depending on the specific transaction (general CGT vs. residential property CGT; IHT on death vs. IHT on lifetime trusts, which is genuinely C-shaped via the Trust Registration Service and 10-year charges).
- B1 vs B2 isn't about "thinking vs not thinking" — it's about whether the state, having forced discovery, also does the arithmetic.
- C2 is the largest and most heterogeneous category by tax head, but the most uniform by mechanism.
