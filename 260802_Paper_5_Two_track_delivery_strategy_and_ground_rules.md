# Paper 5: Towards a 1 April Private Beta — A Two-Track Delivery Strategy for IHT

*Companion to Paper 3 (Delivering IHT via Core) and its annexes, and to the separate handoff note on the cache-based Core refactor and compound-condition routing. This paper sits above both: it frames the delivery strategy and the contract that must hold regardless of which track builds any given piece, so that the cache-refactor work can proceed as an implementation of one option under this contract, not as the only option this paper assumes.*

---

## 1. Purpose: towards 1 April

HMRC wants a private beta of the IHT service by 1 April, open to named, willing, experienced IHT solicitors. Building that on the cache-based Core utility described elsewhere in this project — the architecture we believe is the right long-term answer — is achievable, but only if work starts now and the scope is disciplined; starting later, or with a broader scope, puts 1 April at real risk.

Rather than gamble the date on one architecture being ready in time, this paper sets out a **two-track strategy**: a quick, deliberately narrow build for 1 April, running alongside continued work on the systemic long-term answer, with an explicit, disciplined contract that lets both tracks sit behind the same homepage without the homepage — or the citizen, or the solicitor — needing to know which one is doing the work at any given moment.

---

## 2. The two tracks, and why we're likely riding both

**Track (i): quick and dirty.** Hand-crafted screens — most likely Salesforce Flow — built fast, for a deliberately narrow slice of asset types, with the same minimum security and data-protection rigour any live service handling real personal data requires, but without depending on the cache-based routing/compound-condition work being ready. Fast to build, well-trodden technically, but not the right long-term architecture — every asset class built this way is expected to need rebuilding, not extending, when Track (ii) is ready for it.

**Track (ii): systemic.** The cache-based Core utility — `load_cache_for_routed_section()`/`load_cache_for_fixed_table_section()`, compound-condition routing, everything set out in the separate handoff note. The right long-term answer: scalable, extensible, avoids the asset-class-by-asset-class rebuild Track (i) implies. Slower to reach a working state, because it depends on genuinely new engineering (a boolean-expression parser in Apex, a Platform Cache-based data-loading layer, testing and deployment through Salesforce's proper lifecycle) rather than translation of anything that already exists.

**Why both, rather than picking one:** Track (ii) alone risks missing 1 April if it isn't ready in time, for reasons genuinely outside engineering skill (a security/data-protection review process that doesn't compress just by adding developers, in particular). Track (i) alone locks in a rebuild for every asset class ever built on it: it still has to arrive at the *same correct outcomes* the ownership, spousal-exemption, and compound-routing design work established — §3.4 requires that, since the progress summary depends on it — but it does so by hand-enumerating each branch directly in Flow rather than through a generic, reusable mechanism, which is exactly the engineering effort the compound-condition design was meant to spare every future asset class from repeating. Running both in parallel costs a second team, paid for starting now, with the explicit expectation that Track (i)'s internal work is very unlikely to be reusable — but it protects the date without abandoning the destination.

This is a genuine trade-off, not a free lunch, and should be presented to HMRC as one: lower delivery risk to 1 April, in exchange for paying for two teams and accepting that Track (i)'s internal work is very unlikely to be reusable.

---

## 3. The ground rules: what has to hold regardless of which track builds what

This is the part that makes riding two horses survivable. If both tracks respect the same contract at the same set of boundaries, the choice of what sits *behind* any given button becomes a genuinely local decision — swappable later, invisible to everything around it. If they don't, "two tracks" quietly becomes "two incompatible services wearing the same homepage," and the promised low-risk cutover from Track (i) to Track (ii) stops being true.

### 3.1 The homepage/Core distinction (Layer 1)

The regime homepage — IHT's own — calls into whatever handles a given section or schedule and gets control back. This boundary must stay genuinely indifferent to what's on the other side of it. The homepage should never need to know, or care, whether a given button's action ran as a cache-driven Core section or a hand-crafted Flow screen.

### 3.2 Entry and exit criteria for every action button

Every "Call to get X" button (property, bank accounts, whichever asset classes are in scope) must honour the same entry contract (what the button hands off — case, actor, regime context) and the same exit contract (what control returns — completion status, enough for `SectionStatus`/`ScheduleStatus` to update correctly) regardless of which track built the thing behind the button. A concrete example: the "Call to get property" button hands off exactly the same way whether what runs next is Track (i)'s Flow or Track (ii)'s cache-driven property section — and hands *back* exactly the same way too.

### 3.3 The three section types

Whatever built a given section — Flow or Core — the data it produces must still be recognisable as one of the three section types this whole design is built around (single-answer section, fixed-field table, routed table), because everything above this level (Layer 2's status tracking, the estate progress summary, eventual reporting) is written against that typology, not against "however Track (i) happened to structure this."

### 3.4 The answer format for property (and every asset class)

This is the one most worth stating as a hard, non-negotiable requirement on Track (i), not a nice-to-have: whatever Track (i)'s Flow does internally, its output must land in `AnswerTable` in the same row shape Track (ii) would have produced — including the exempt/non-exempt split established in Annex 3B, not just a bare total value. If Track (i) skips this because it seems unnecessary for a fast build, two things break quietly: the estate progress summary (§3.5) either fails or needs Track (i)-specific special-casing, and any later reporting or reconciliation across estates started on either track becomes unreliable. The *internal* mechanism — how the Flow gets to an answer — is Track (i)'s to build however's fastest. The *exit* data shape is shared infrastructure and is not Track (i)'s to redefine.

### 3.5 The estate progress summary (the in-flight three-way values table)

Paper 4's "View estate as so far defined" feature — gross/taxable/probate columns, built by reading completed rows — must work identically regardless of which track produced those rows. This falls out automatically from §3.4 being honoured properly: if every row, from either track, is written in the same shape, the progress summary needs no awareness of which track wrote it. This is also a good acceptance test for §3.4: if the progress summary can't be built without asking which track a row came from, §3.4 hasn't actually been respected.

---

## 4. Given §3, the calls behind any button can be (i) Flow or (ii) the cache utility

Provided every button honours §3.1–§3.5, which asset classes are built on Track (i) versus Track (ii) becomes a scoping decision, not an architectural one. Property might launch on Track (i) for 1 April and move to Track (ii) three months later; bank accounts might go straight to Track (ii) if it's ready in time; some future asset class might never touch Track (i) at all. None of that requires touching the homepage, the button contract, or the progress summary — only the one section behind the button that's changing.

---

## 5. Case lifecycle across paper, Track (i), and Track (ii)

This is genuinely a three-way, shifting triage, not a single handoff, and it changes shape over time:

- **Estates already in progress on paper when Track (i) launches** are not migrated into either digital track. They stay on paper to completion. This mirrors HMRC's existing, well-understood paper tail — a precedent worth citing directly, since it's proof HMRC already knows how to resource a shrinking legacy channel.
- **Track (i) accepts only estates within its own deliberately narrow scope**, and — because that scope excludes multiple properties, business or trust interests, cross-border elements, and disputes, by design — every estate Track (i) accepts is one it can also finish. Track (i) starts and finishes whole estates; there is no migration of an in-flight Track (i) case into Track (ii). This needs two supporting pieces, not yet built: an explicit, checkable eligibility rule (so solicitors and HMRC can determine correctly, up front, whether a given estate qualifies for Track (i)), and an explicit escape hatch for a Track (i) case that turns out, mid-journey, not to be eligible after all (e.g. a second property surfaces) — the honest answer being "drop out of Track (i), finish on paper," planned for rather than discovered live.
- **Track (ii) is expected to open with broader scope than Track (i), but not full scope from day one.** The genuinely complex cases — those Track (i) never touches — remain on paper until Track (ii)'s own coverage grows to include them. This means Track (ii) reaching "open to new estates" is not the same milestone as "paper is no longer needed for new estates" — there is a second, later date, when Track (ii)'s scope finally matches paper's full scope, and that is the real retirement point for paper. Worth naming both dates explicitly in any plan, even if the second is well beyond the horizon currently being scoped, so they don't get quietly conflated.
- **Eventually, all new estates — however complex — start and finish on Track (ii)**, and both paper and Track (i) exist only as long as their own last open estate takes to close.

---

## 6. What this paper deliberately doesn't cover

The engineering detail of Track (ii) itself — the cache-load functions, compound-condition routing engine, the known `boolean.py` symbol-naming trap, the Apex-vs-Expression-Set question, schema and admin-tooling decisions still open — is covered in the separate handoff note (currently titled around session-caching refactor and compound-condition routing). That note should now be read as answering "how do we build Track (ii)," operating *within* the contract this paper establishes, not as the only path to 1 April. Track (i)'s own build (Flow structure, screen design, asset-class eligibility rules) has not yet been scoped at all, and is a natural next piece of work once this paper's ground rules are agreed.
