# Ownership-fork routing rebuild — reusable template

Source: the live SQL actually run against HMRC_S8 (property) on 15 August 2026.
Kept here as a starting point for any other asset-class section that uses the
same sole/joint/tenants-in-common ownership fork (per Annex 3B §6's asset
class configuration register — "Full" or "Sole/joint only" fork classes:
property, other land, bank/savings accounts, shares/investments, business
interests, chattels, vehicles).

**Confirmed reuse cases (as at 22 August 2026):**

| Section | Asset class | Opening | Tail | Notes |
|---------|-------------|---------|------|-------|
| HMRC_S8 | Residential property | SET10 → HMRC_47 → HMRC_46 | HMRC_60 → HMRC_56–59 (valuation-evidence) | Original; template source |
| HMRC_S7 | Bank and building society accounts | SET11 → HMRC_46 | END (no tail) | 18 August 2026 |
| HMRC_S9 | Listed stocks, shares and ISAs | SET12 → [5×HMRC_63 branches] → SET14/detail → HMRC_46 | END (no tail) | 22 August 2026; first section where the fork is needed at the identification step itself (see note below) |

**HMRC_S9 identification note:** HMRC_S9 is the first section where the
ownership fork needed to be reached via a *branching identification step* rather
than a single fixed opening chain. SET12's routing uses `alternate_condition_id`
to branch on HMRC_63 (type of holding — 5 options), with different detail
paths per branch before all merging at HMRC_46. HMRC_S7 and HMRC_S8 route
unconditionally from their respective identification SETs straight to the
first fork node. Anyone reusing this template for a section with multiple
holding types should follow the S9 pattern: use `alternate_condition_id` on
the SET-level routing row to branch at the identification step itself.

**What's genuinely reusable, unchanged:** the ownership-fork shape itself —
HMRC_46 (ownership type, already a shared platform Question, asset-neutral
wording) branching into sole/joint/TIC, the N=2-vs-N≥3 compound condition
on the joint branch, and HMRC_55 (spousal destination, also asset-neutral
wording, "this asset" not "this property") with its three-way Entirely/
Partly/Not-at-all logic and the HMRC_54→HMRC_61/62 £-or-% follow-up. All of
these questions and this routing shape are designed to be shared across
asset classes (Annex 3B §1.3) — reuse the same `HMRC_46`/`HMRC_48`/`HMRC_50`/
`HMRC_49`/`HMRC_51`/`HMRC_52`/`HMRC_55`/`HMRC_54`/`HMRC_61`/`HMRC_62` IDs
directly; don't create new questions for these.

**What will differ per asset class — check before reusing, don't copy blind:**

1. **The opening.** `SET10`→`HMRC_47`→`HMRC_46` here is property-specific
   (address, reference, property value). Another asset class will have its
   own identification/value questions and its own entry node — only the
   *shape* ("identify → value → ownership type," per Annex 3B §1.1) carries
   over, not the actual node chain.
2. **The value question feeding the arithmetic.** `HMRC_47` here; substitute
   whatever the new class's own value question is.
3. **Whether the fork applies at all.** ISAs and pensions are "Suppressed" —
   skip the fork entirely for those, per the config register.
4. **Whether it's the full three-way fork or a reduced one.** Chattels and
   vehicles are "Sole/joint only" — no tenants-in-common branch, no unequal-
   share sub-branch. Don't include the TIC block for those classes.
5. **The tail after the fork.** `HMRC_60`→`HMRC_56`-`HMRC_59` (professional
   valuation, freehold/let/damage/sold) is property-specific "valuation-
   evidence substitute" content. Per the config register: shares/investments
   and bank accounts typically need *no* substitute tail at all (fork's
   non-exempt output just closes); business interests need turnover/
   accounts/BPR-status questions instead; chattels need an insurance-
   schedule/de-minimis check. Build the right tail per class — don't reuse
   HMRC_56-59 outside property.
6. **`section_id` and the actual `current_node`/`next_node` values** obviously
   change to the new section and its own question IDs throughout.

---

## The script, as run

```sql
-- ═══════════════════════════════════════════════════════════════
-- 0. Backup (always do this first, name it per-section and per-date)
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS core_routing_backup_20260803_hmrc_s8;
CREATE TABLE core_routing_backup_20260803_hmrc_s8 AS
SELECT * FROM core_routing WHERE section_id = 'HMRC_S8';

SELECT COUNT(*) FROM core_routing_backup_20260803_hmrc_s8;  -- sanity check

-- ═══════════════════════════════════════════════════════════════
BEGIN;

-- 1. Delete existing routing for the section
DELETE FROM core_routing WHERE section_id = 'HMRC_S8';

-- 2. Rebuild
INSERT INTO core_routing
    (section_id, current_node, next_node, order_in_section,
     comparator_1, test_value_1, alternate_condition_id, comparator_2, test_value_2)
VALUES
    -- ── Shared opening — PROPERTY-SPECIFIC, replace for other classes ──
    ('HMRC_S8', 'SET10',    'HMRC_47', 10,  NULL, NULL, NULL,       NULL, NULL),
    ('HMRC_S8', 'HMRC_47',  'HMRC_46', 20,  NULL, NULL, NULL,       NULL, NULL),

    -- ── Ownership fork — REUSABLE SHAPE, same HMRC_46 question ──
    ('HMRC_S8', 'HMRC_46', 'HMRC_55', 30, '=', 'Sole ownership of the deceased', 'HMRC_14', '=', 'Yes'),
    ('HMRC_S8', 'HMRC_46', 'HMRC_60', 40, '=', 'Sole ownership of the deceased', NULL,      NULL, NULL),
    ('HMRC_S8', 'HMRC_46', 'HMRC_48', 50, '=', 'Joint names',                    NULL,      NULL, NULL),
    ('HMRC_S8', 'HMRC_46', 'HMRC_49', 60, '=', 'Tenants in common',              NULL,      NULL, NULL),

    -- ── Joint tenants branch — REUSABLE SHAPE (omit if class is Sole/joint-only with no unequal-share nuance, or Suppressed) ──
    ('HMRC_S8', 'HMRC_48', 'HMRC_50', 70, NULL, NULL, 'HMRC_14', '=', 'Yes'),
    ('HMRC_S8', 'HMRC_48', 'HMRC_60', 80, NULL, NULL, NULL,      NULL, NULL),
    ('HMRC_S8', 'HMRC_50', NULL,      90, '=', 'Yes', 'HMRC_48', '=', '2'),
    ('HMRC_S8', 'HMRC_50', 'HMRC_60', 100, '=', 'Yes', NULL,     NULL, NULL),
    ('HMRC_S8', 'HMRC_50', 'HMRC_60', 110, '=', 'No',  NULL,     NULL, NULL),

    -- ── Tenants in common branch — REUSABLE SHAPE (omit entirely for "Sole/joint only" classes — chattels, vehicles) ──
    ('HMRC_S8', 'HMRC_49', 'HMRC_51', 120, NULL, NULL, NULL,      NULL, NULL),
    ('HMRC_S8', 'HMRC_51', 'HMRC_55', 130, '=', 'Yes', 'HMRC_14', '=', 'Yes'),
    ('HMRC_S8', 'HMRC_51', 'HMRC_60', 140, '=', 'Yes', NULL,      NULL, NULL),
    ('HMRC_S8', 'HMRC_51', 'HMRC_52', 150, '=', 'No',  NULL,      NULL, NULL),
    ('HMRC_S8', 'HMRC_52', 'HMRC_55', 160, NULL, NULL, 'HMRC_14', '=', 'Yes'),
    ('HMRC_S8', 'HMRC_52', 'HMRC_60', 170, NULL, NULL, NULL,      NULL, NULL),

    -- ── Shared spouse-destination question — REUSABLE, same HMRC_55 ──
    ('HMRC_S8', 'HMRC_55', NULL,      180, '=', 'All of it',  NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_55', 'HMRC_54', 190, '=', 'Some of it', NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_55', 'HMRC_60', 200, '=', 'None of it', NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_54', 'HMRC_61', 210, '=', 'A value (£)', NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_54', 'HMRC_62', 220, '=', 'A share (%)', NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_61', 'HMRC_60', 230, NULL, NULL, NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_62', 'HMRC_60', 240, NULL, NULL, NULL, NULL, NULL),

    -- ── Tail — PROPERTY-SPECIFIC, replace with the right valuation-
    --    evidence substitute for the target asset class (see note 5 above) ──
    ('HMRC_S8', 'HMRC_60', NULL,      250, '=', 'Yes', NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_60', 'HMRC_56', 260, '=', 'No',  NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_56', 'HMRC_57', 270, NULL, NULL, NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_57', 'HMRC_58', 280, NULL, NULL, NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_58', 'HMRC_59', 290, NULL, NULL, NULL, NULL, NULL),
    ('HMRC_S8', 'HMRC_59', NULL,      300, NULL, NULL, NULL, NULL, NULL);

-- 3. Verify before committing
SELECT COUNT(*) FROM core_routing WHERE section_id = 'HMRC_S8';

SELECT current_node, next_node, order_in_section,
       comparator_1, test_value_1, alternate_condition_id, comparator_2, test_value_2
FROM core_routing
WHERE section_id = 'HMRC_S8'
ORDER BY order_in_section;

-- 4. Only after checking the above looks right:
-- COMMIT;
-- (or ROLLBACK; if anything looks wrong)
```

---

---

## `condition_question_id` vs `alternate_condition_id` — use the right one

**(Discovered 22 August 2026 during HMRC_S9 build.)**

The `Routing` model has two fields that look like they both redirect a routing
test to another question's answer:

- **`condition_question_id`** — has its own `help_text` describing this
  behaviour. However: it is **never actually read by `_evaluate_routing`**.
  It is a dead field from an earlier migration, superseded by the Phase 3
  compound-condition overhaul (3 August 2026). The dead-fields note in Core
  Platform Reference §3 confirms this. Any routing row that sets only
  `condition_question_id` will have its condition silently ignored at
  evaluation time — `_evaluate_routing` only reads the five compound-condition
  fields.

- **`alternate_condition_id`** — slot-2 of the two-slot AND model. This is
  the field that actually routes evaluation to a different question's answer.
  Set in combination with `comparator_2` and `test_value_2`. Slot 1
  (`comparator_1`/`test_value_1`) may be null (i.e. slot-2-only rows are
  valid — `alternate_condition_id` with slot 1 left unconditional is how the
  joint-tenants marital-status branch works at `HMRC_48` in the template
  script above).

**Rule:** anyone routing off a SET member's answer — or off any other
external question's answer — must use `alternate_condition_id` (with slot 1
set to null or to a real test value, as appropriate). Setting only
`condition_question_id` will appear to work in the admin UI (the field
exists and saves) but the condition will silently never fire.

---

## Ordering rule, worth restating for whoever picks this up next

Where two rows share the same `Q_condition` (`test_value_1`), the row **with**
an `Alt_condition` (`alternate_condition_id`/`comparator_2`/`test_value_2`)
must have a lower `order_in_section` than the plain fallback row with the same
`test_value_1` — the engine stops at the first full match, so the narrower
compound row has to be checked first (see rows 30/40, 90/100, 130/140 above).
Rows with **both** `comparator_1` and `comparator_2` null are a separate,
always-checked-last fallback bucket — ordering doesn't matter for those (e.g.
row 80).
