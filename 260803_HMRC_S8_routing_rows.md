# HMRC_S8 (Property) — Routing rows, one line per outcome

Format per row: `Q_condition=[...], Alt_condition=[...] => Next_Q=[...]`
`(none)` = that field is NULL in the real row.

**Ordering rule:** within a node, where two rows share the same `Q_condition`,
the row WITH an `Alt_condition` must be listed (and given a lower
`order_in_section`) before the row without one. The engine stops at the first
full match — if the broader fallback were checked first it would wrongly
match before the narrower compound row got a chance.

## Glossary

| ID | About |
|---|---|
| HMRC_44 | property address |
| HMRC_45 | your reference |
| HMRC_47 | whole property value |
| HMRC_46 | ownership type: sole / joint names / tenants in common |
| HMRC_14 | married/civil partner? (case-level) |
| HMRC_48 | number of joint owners, N |
| HMRC_50 | was spouse one of the other joint owners? |
| HMRC_49 | number of tenants in common, N |
| HMRC_51 | equal share with other tenants in common? |
| HMRC_52 | deceased's % share (if unequal) |
| HMRC_55 | how much passes to spouse: All/Some/None of it |
| HMRC_54 | value specified as £ or %? ⚠ options unconfirmed |
| HMRC_61 | £ value to spouse |
| HMRC_62 | % to spouse |
| HMRC_60 | professional valuation? |
| HMRC_56 | freehold or leasehold? |
| HMRC_57 | was property let? |
| HMRC_58 | special factors (damage)? |
| HMRC_59 | sold/intend to sell within 12 months? |

---

## HMRC_44 — "What is the address of the property?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_45`

## HMRC_45 — "What is your reference for the property?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_47`

## HMRC_47 — "What is the open market value of the whole asset, in £?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_46`

## HMRC_46 — "How was this asset owned?"
```
Q_condition="Sole ownership of the deceased", Alt_condition=HMRC_14="Yes" => Next_Q=HMRC_55
Q_condition="Sole ownership of the deceased", Alt_condition=(none)        => Next_Q=HMRC_60
Q_condition="Joint names",                     Alt_condition=(none)        => Next_Q=HMRC_48
Q_condition="Tenants in common",               Alt_condition=(none)        => Next_Q=HMRC_49
```

## HMRC_48 — "How many joint tenants owned this property in total, including the deceased?"
```
Q_condition=(none), Alt_condition=HMRC_14="Yes" => Next_Q=HMRC_50
Q_condition=(none), Alt_condition=(none)        => Next_Q=HMRC_60
```
*(both slots null on row 2 → engine's true "unconditional" fallback bucket — order vs row 1 doesn't matter here, unlike the same-Q_condition cases below.)*

## HMRC_50 — "Is the deceased's spouse/civil partner one of the other owners?"
```
Q_condition="Yes", Alt_condition=HMRC_48="2" => Next_Q=END
Q_condition="Yes", Alt_condition=(none)      => Next_Q=HMRC_60
Q_condition="No",  Alt_condition=(none)      => Next_Q=HMRC_60
```
⚠ `HMRC_48="2"` assumes the answer is stored as the plain string `"2"` —
confirm before writing SQL.

## HMRC_49 — "How many tenants in common owned this asset, including the deceased?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_51`

## HMRC_51 — "Did the deceased own an equal share with other tenants in common?"
```
Q_condition="Yes", Alt_condition=HMRC_14="Yes" => Next_Q=HMRC_55
Q_condition="Yes", Alt_condition=(none)        => Next_Q=HMRC_60
Q_condition="No",  Alt_condition=(none)        => Next_Q=HMRC_52
```

## HMRC_52 — "What was the deceased's share of this asset (%)?"
```
Q_condition=(none), Alt_condition=HMRC_14="Yes" => Next_Q=HMRC_55
Q_condition=(none), Alt_condition=(none)        => Next_Q=HMRC_60
```

## HMRC_55 — "How much of the deceased's share of this asset passes to the surviving spouse or civil partner?"
```
Q_condition="All of it",  Alt_condition=(none) => Next_Q=END
Q_condition="Some of it", Alt_condition=(none) => Next_Q=HMRC_54
Q_condition="None of it", Alt_condition=(none) => Next_Q=HMRC_60
```
*(already live — matches the SQL fix made earlier this session.)*

## HMRC_54 — "Was the portion of the deceased's share passing to the spouse specified as a value (£) or a share (%)?" ⚠ option text unconfirmed
```
Q_condition="[£ option — confirm exact text]", Alt_condition=(none) => Next_Q=HMRC_61
Q_condition="[% option — confirm exact text]", Alt_condition=(none) => Next_Q=HMRC_62
```

## HMRC_61 — "What value, in £, passes to the spouse?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_60`

## HMRC_62 — "What percentage of the deceased's share passes to the spouse?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_60`

## HMRC_60 — "Is the overall property value supported by a written professional valuation?"
```
Q_condition="Yes", Alt_condition=(none) => Next_Q=END
Q_condition="No",  Alt_condition=(none) => Next_Q=HMRC_56
```

## HMRC_56 — "Was the property owned Freehold or Leasehold?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_57`

## HMRC_57 — "Was the property let?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_58`

## HMRC_58 — "Was the property value ubject to any special factors, such as major damage or development potential?" ⚠ typo in live text ("ubject" → "subject")
`Q_condition=(none), Alt_condition=(none) => Next_Q=HMRC_59`

## HMRC_59 — "Has the property been sold, or do you intend to sell it, within 12 months of the date of death?"
`Q_condition=(none), Alt_condition=(none) => Next_Q=END`
