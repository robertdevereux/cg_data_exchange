# HMRC_S7 (Bank & building society accounts) — Routing rows, one line per outcome

Built from `260803_HMRC_S8_routing_rows.md` (property), reusing the shared
ownership-fork questions (HMRC_46/48/49/50/51/52/55/54/61/62) unchanged, per
`260815_Ownership_fork_routing_template.md`. Differences from S8, both
deliberate, per your instructions:

1. **Opening.** S8 chains three individual questions (HMRC_44 → HMRC_45 →
   HMRC_47) before reaching HMRC_46. For S7, the three opening facts (bank
   name HMRC_40, account number HMRC_41, balance HMRC_42) are grouped as
   one page, `SET11`, going straight to HMRC_46 — one row instead of three.

2. **Every S8 destination of `HMRC_60`** (the "professional valuation?"
   gateway into the property-specific tail) becomes **`END`** for S7.

3. **The entire tail — HMRC_60, HMRC_56, HMRC_57, HMRC_58, HMRC_59 — is
   dropped.** No substitute-evidence questions for bank accounts.

Format per row: `Q_condition=[...], Alt_condition=[...] => Next_Q=[...]`
`(none)` = that field is NULL in the real row. **Bold** marks every row
whose `Next_Q` differs from the equivalent S8 row (i.e. was `HMRC_60`,
now `END`).

**Ordering rule (unchanged from S8):** within a node, where two rows share
the same `Q_condition`, the row WITH an `Alt_condition` must be listed
(and given a lower `order_in_section`) before the row without one.

## Glossary

| ID | About |
|---      |---|
| HMRC_40 | bank/building society name |
| HMRC_41 | account number |
| HMRC_42 | account balance at date of death, £ |
| SET11   | the above three, shown together on one page |
| HMRC_46 | ownership type: sole / joint names / tenants in common |
| HMRC_14 | married/civil partner? (case-level) |
| HMRC_48 | number of joint owners, N |
| HMRC_50 | was spouse one of the other joint owners? |
| HMRC_49 | number of tenants in common, N |
| HMRC_51 | equal share with other tenants in common? |
| HMRC_52 | deceased's % share (if unequal) |
| HMRC_55 | how much passes to spouse: All/Some/None of it |
| HMRC_54 | value specified as £ or %? ⚠ options unconfirmed (same as S8) |
| HMRC_61 | £ value to spouse |
| HMRC_62 | % to spouse |

---

## SET11 — "Bank/building society name", "Account number", "Account balance at date of death"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_46`

## HMRC_46 — "How was this asset owned?"
```
Q_condition="Sole ownership of the deceased", Alt_condition=HMRC_14="Yes" => Next_Q=HMRC_55
Q_condition="Sole ownership of the deceased", Alt_condition=(none)        => Next_Q=END        **
Q_condition="Joint names",                    Alt_condition=(none)        => Next_Q=HMRC_48
Q_condition="Tenants in common",              Alt_condition=(none)        => Next_Q=HMRC_49
```

## HMRC_48 — "How many joint tenants owned this account in total, including the deceased?"
```
Q_condition=(none), Alt_condition=HMRC_14="Yes" => Next_Q=HMRC_50
Q_condition=(none), Alt_condition=(none)        => Next_Q=END        **
```
*(both slots null on row 2 → true "unconditional" fallback bucket — order vs row 1 doesn't matter.)*

## HMRC_50 — "Is the deceased's spouse/civil partner one of the other owners?"
```
Q_condition="Yes", Alt_condition=HMRC_48="2" => Next_Q=END
Q_condition="Yes", Alt_condition=(none)      => Next_Q=END        **
Q_condition="No",  Alt_condition=(none)      => Next_Q=END        **
```
⚠ `HMRC_48="2"` assumes the answer is stored as the plain string `"2"` —
same unresolved flag as in the S8 doc; confirm before writing SQL.
Row 1 was already `END` in S8 — unaffected by the HMRC_60→END change, but
worth double-checking it's still correctly ordered *before* row 2 (same
`Q_condition="Yes"`), since both now point to `END` and it would be easy to
assume the ordering rule no longer matters once the destinations match. It
still matters: without the compound row appearing first, the engine would
never get the chance to evaluate the `HMRC_48="2"` condition at all — row 2
would already have matched. The two rows are only reachable independently
because of this ordering, not because their identical destination makes
distinguishing them unnecessary.

## HMRC_49 — "How many tenants in common owned this account, including the deceased?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_51`

## HMRC_51 — "Did the deceased own an equal share with other tenants in common?"
```
Q_condition="Yes", Alt_condition=HMRC_14="Yes" => Next_Q=HMRC_55
Q_condition="Yes", Alt_condition=(none)        => Next_Q=END        **
Q_condition="No",  Alt_condition=(none)        => Next_Q=HMRC_52
```

## HMRC_52 — "What was the deceased's share of this asset (%)?"
```
Q_condition=(none), Alt_condition=HMRC_14="Yes" => Next_Q=HMRC_55
Q_condition=(none), Alt_condition=(none)        => Next_Q=END        **
```

## HMRC_55 — "How much of the deceased's share of this asset passes to the surviving spouse or civil partner?"
```
Q_condition="All of it",  Alt_condition=(none) => Next_Q=END
Q_condition="Some of it", Alt_condition=(none) => Next_Q=HMRC_54
Q_condition="None of it", Alt_condition=(none) => Next_Q=END        **
```

## HMRC_54 — "Was the portion of the deceased's share passing to the spouse specified as a value (£) or a share (%)?" ⚠ option text unconfirmed
```
Q_condition="[£ option — confirm exact text]", Alt_condition=(none) => Next_Q=HMRC_61
Q_condition="[% option — confirm exact text]", Alt_condition=(none) => Next_Q=HMRC_62
```

## HMRC_61 — "What value, in £, passes to the spouse?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=END        **`

## HMRC_62 — "What percentage of the deceased's share passes to the spouse?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=END        **`

---

## Row count

10 nodes, 23 routing rows total (vs S8's 15 nodes / 24 rows up to and
including HMRC_62 — S7 saves 2 rows on the opening by using SET11 instead
of three chained questions, and shares the same fork/spouse-destination row
count as S8). No HMRC_60 or tail (HMRC_56–59) — 6 fewer rows than S8's
full 30.

## Open items carried over from the S8 doc, unresolved for S7 too

- ⚠ `HMRC_48="2"` string-format assumption (HMRC_50, row 1) — same flag as S8.
- ⚠ HMRC_54's exact option text (£ / % wording) — same flag as S8; whatever
  gets confirmed for S8 applies here unchanged, since HMRC_54 is reused.
