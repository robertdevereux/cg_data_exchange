"""
routing_engine_prototype.py
============================

A prototype conditional-routing engine supporting a compound (two-slot AND)
condition per routing row — the capability the original single-condition
Routing model lacked.

Revision note: this replaces an earlier version built around a free-text
boolean logic string (parsed with the boolean.py library) supporting
arbitrary AND/OR/NOT/parentheses combinations of numbered conditions.
Working through every real case this design has actually needed established
that OR is already free (multiple ordered outcome rows per current_node,
first match wins — exactly how the model already worked) and NOT is already
free (the '<>' comparator). The only genuinely missing primitive was
"test two conditions, both must hold, on one row." This version provides
exactly that, and nothing more — no parser, no grammar, no third-party
dependency, no logic-string authoring trap to guard against. If a real case
is ever found needing a third simultaneous condition, that is the trigger
to generalise further — not before.

Structured to mirror an eventual Salesforce Platform Cache load-once/
evaluate-in-memory approach — see the module-level docstring in the
superseded version, and Track (ii) Build Note §5, for that framing. Only
load_section_cache touches the database; everything else is a pure
function over an assembled SectionCache and an in-memory answers dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────
# Data shapes
# ─────────────────────────────────────────────────────────────────────────

# Valid comparators, shared by both slots.
COMPARATORS = {'=', '<>', '<', '<=', '>', '>='}


def _matches(comparator: str, actual: Any, target: Any) -> bool:
    """
    Evaluate one slot's test: does `actual` satisfy `comparator` against
    `target`? Shared logic for slot 1 and slot 2 — both use the same rules.
    """
    if actual is None:
        return False

    if comparator == '=':
        return str(actual) == str(target)
    if comparator == '<>':
        return str(actual) != str(target)

    # Remaining comparators are numeric.
    try:
        actual_num = float(actual)
        target_num = float(target)
    except (TypeError, ValueError):
        return False

    if comparator == '<':
        return actual_num < target_num
    if comparator == '<=':
        return actual_num <= target_num
    if comparator == '>':
        return actual_num > target_num
    if comparator == '>=':
        return actual_num >= target_num

    raise ValueError(f'Unhandled comparator {comparator!r}')  # unreachable


@dataclass(frozen=True)
class Outcome:
    """
    One routing outcome, matching the Routing model's field names directly:

      current_node          — the node this rule fires from (also, where
                               comparator_1 is set, slot 1's own question)
      next_node              — where to go if this outcome matches; None = END
      comparator_1           — slot 1's test, or None if slot 1 isn't tested
      test_value_1            — slot 1's target (literal or numeric)
      alternate_condition_id — slot 2's question, or None if slot 2 isn't tested
      comparator_2           — slot 2's test, or None
      test_value_2            — slot 2's target
      order                   — evaluation order among outcomes sharing a
                                current_node; first match wins

    Evaluation rule:
      - neither comparator set  -> unconditional match (today's catch-all)
      - only comparator_1 set   -> today's own-answer routing
      - only comparator_2 set   -> today's condition_question_id-only routing
      - both set                -> AND both (the new case)
    """
    current_node: str
    next_node: str | None
    comparator_1: str | None
    test_value_1: Any
    alternate_condition_id: str | None
    comparator_2: str | None
    test_value_2: Any
    order: int

    def __post_init__(self):
        for comparator in (self.comparator_1, self.comparator_2):
            if comparator is not None and comparator not in COMPARATORS:
                raise ValueError(f'Unknown comparator {comparator!r}')
        if self.comparator_2 is not None and self.alternate_condition_id is None:
            raise ValueError(
                'comparator_2 is set but alternate_condition_id is not — '
                'slot 2 needs a question to test.'
            )


@dataclass
class SectionCache:
    """
    Everything needed to evaluate routing for one section, held in memory.
    This is the object that would be populated into Platform Cache.
    """
    section_id: str
    outcomes_by_node: dict[str, list[Outcome]] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
# Loading — the ONLY place this module touches the database
# ─────────────────────────────────────────────────────────────────────────

def load_section_cache(section_id: str) -> SectionCache:
    """
    Single DB read, assembling the full routing table for a section into
    memory. Stands in for load_cache_for_routed_section() — see the Track
    (ii) Build Note §2.1 for where this logic is expected to actually live
    once Piece 1 (the Core session-caching refactor) is done; this function
    is a placeholder for that, not a second, competing loader.

    Expects one Django model (sketched, not defined here):
      RoutingOutcome(section_id, current_node, next_node, order,
                     comparator_1, test_value_1,
                     alternate_condition_id, comparator_2, test_value_2)
    """
    from myapp.models import RoutingOutcome  # placeholder

    outcomes_by_node: dict[str, list[Outcome]] = {}

    for row in RoutingOutcome.objects.filter(section_id=section_id).order_by(
        'current_node', 'order'
    ):
        outcome = Outcome(
            current_node=row.current_node,
            next_node=row.next_node,
            comparator_1=row.comparator_1,
            test_value_1=row.test_value_1,
            alternate_condition_id=row.alternate_condition_id,
            comparator_2=row.comparator_2,
            test_value_2=row.test_value_2,
            order=row.order,
        )
        outcomes_by_node.setdefault(row.current_node, []).append(outcome)

    return SectionCache(section_id=section_id, outcomes_by_node=outcomes_by_node)


# ─────────────────────────────────────────────────────────────────────────
# Evaluation — pure, in-memory, no database access
# ─────────────────────────────────────────────────────────────────────────

def evaluate_outcome(outcome: Outcome, answers: dict[str, Any]) -> bool:
    """
    Does this outcome match, given the in-memory answers dict?
    answers: {question_id: value}, already loaded for this journey.

    Slot 1 tests answers[outcome.current_node] — the current node's own
    answer. Slot 2, if present, tests answers[outcome.alternate_condition_id]
    — a different, already-answered question.
    """
    if outcome.comparator_1 is None and outcome.comparator_2 is None:
        return True  # unconditional — the catch-all row

    slot_1_ok = True
    if outcome.comparator_1 is not None:
        actual = answers.get(outcome.current_node)
        slot_1_ok = _matches(outcome.comparator_1, actual, outcome.test_value_1)

    slot_2_ok = True
    if outcome.comparator_2 is not None:
        actual = answers.get(outcome.alternate_condition_id)
        slot_2_ok = _matches(outcome.comparator_2, actual, outcome.test_value_2)

    return slot_1_ok and slot_2_ok


def resolve_next_node(
    cache: SectionCache,
    current_node: str,
    answers: dict[str, Any],
) -> str | None:
    """
    The single routing decision point. Returns the next node ID, or None
    for END. Raises if no outcome matches — every current_node's outcome
    list should end with an unconditional catch-all row, so this should
    only fire on a genuine data-authoring error.
    """
    outcomes = cache.outcomes_by_node.get(current_node, [])
    for outcome in outcomes:
        if evaluate_outcome(outcome, answers):
            return outcome.next_node

    raise RuntimeError(
        f'No matching routing outcome for node {current_node!r} '
        f'given answers {answers!r} — missing a catch-all row?'
    )


# ─────────────────────────────────────────────────────────────────────────
# Worked example — the sole-ownership branch's checkpoint decision
# ─────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Two outcomes for current_node = HMRC_46, both requiring the answer
    # 'Sole ownership of the deceased' AND a second condition on HMRC_14 —
    # exactly the compound condition the original single-condition Routing
    # model couldn't express, now expressed with no logic string at all.
    outcomes = [
        Outcome(
            current_node='HMRC_46',
            next_node='HMRC_55',
            comparator_1='=', test_value_1='Sole ownership of the deceased',
            alternate_condition_id='HMRC_14',
            comparator_2='=', test_value_2='Yes',
            order=10,
        ),
        Outcome(
            current_node='HMRC_46',
            next_node='HMRC_60',
            comparator_1='=', test_value_1='Sole ownership of the deceased',
            alternate_condition_id='HMRC_14',
            comparator_2='<>', test_value_2='Yes',
            order=20,
        ),
        Outcome(
            current_node='HMRC_46',
            next_node='HMRC_48',
            comparator_1='=', test_value_1='Joint names',
            alternate_condition_id=None, comparator_2=None, test_value_2=None,
            order=30,
        ),
        Outcome(
            current_node='HMRC_46',
            next_node='HMRC_49',
            comparator_1='=', test_value_1='Tenants in common',
            alternate_condition_id=None, comparator_2=None, test_value_2=None,
            order=40,
        ),
    ]

    cache = SectionCache(
        section_id='HMRC_S8',
        outcomes_by_node={'HMRC_46': outcomes},
    )

    # Case A: sole ownership, married -> HMRC_55
    answers_a = {'HMRC_46': 'Sole ownership of the deceased', 'HMRC_14': 'Yes'}
    print('Case A (sole, married):', resolve_next_node(cache, 'HMRC_46', answers_a))

    # Case B: sole ownership, not married -> HMRC_60
    answers_b = {'HMRC_46': 'Sole ownership of the deceased', 'HMRC_14': 'No'}
    print('Case B (sole, not married):', resolve_next_node(cache, 'HMRC_46', answers_b))

    # Case C: joint names -> HMRC_48, regardless of marital status
    answers_c = {'HMRC_46': 'Joint names', 'HMRC_14': 'Yes'}
    print('Case C (joint):', resolve_next_node(cache, 'HMRC_46', answers_c))

    # Numeric example: a second condition of the form Q14 < 2000
    numeric_outcome = Outcome(
        current_node='HMRC_3', next_node='HMRC_9',
        comparator_1='=', test_value_1='Wales',
        alternate_condition_id='HMRC_14',
        comparator_2='<', test_value_2=2000,
        order=10,
    )
    numeric_cache = SectionCache(
        section_id='DEMO', outcomes_by_node={'HMRC_3': [numeric_outcome]}
    )
    answers_d = {'HMRC_3': 'Wales', 'HMRC_14': 1500}
    print('Case D (Wales, <2000):', resolve_next_node(numeric_cache, 'HMRC_3', answers_d))
