"""
core/interfaces.py — Platform interface for department apps.

This module defines the contract between the core platform and any department
app built on top of it.

Department apps must:
1. Set the four SESSION_KEYS in the session before redirecting to any Layer 2
   URL.
2. Obtain case_id exclusively via get_or_create_case() — never construct or
   guess a case_id independently.
3. Call bootstrap_section_statuses() when a citizen enters a regime, so Layer 1
   navigation has status records to display.

Department apps may:
- Import and call get_permitted_sections() and get_permitted_regimes() from
  core.permissions
- Query any core model directly (Answer, SectionStatus, Regime, Schedule,
  Section etc.) for read purposes
- Build any Layer 1 navigation pattern they choose, provided it sets the four
  SESSION_KEYS correctly
"""

import uuid

from .models import Case, SectionStatus


# ── Session contract ──────────────────────────────────────────────────────────

SESSION_KEYS = {
    'user_id':  'int — Django User pk of the subject '
                '(whose data is being recorded)',
    'actor_id': 'int — Django User pk of the actor '
                '(who is logged in; equals user_id when self-filing)',
    'regime_id': 'str — the regime_id of the regime being completed',
    'case_id':  'str — UUID of the draft Case for this user/regime; '
                'obtain via get_or_create_case()',
}


# ── Case bootstrap ────────────────────────────────────────────────────────────

def get_or_create_case(user, regime):
    """
    Find the most recent draft Case for this user/regime, or create one if
    none exists.

    This is the only correct way for a department app to obtain a case_id
    before entering Layer 2.

    Args:
        user:   User instance (the subject, not the actor)
        regime: Regime instance
    Returns:
        Case instance (status=Case.DRAFT)
    """
    case = (
        Case.objects
        .filter(user=user, regime=regime, status=Case.DRAFT)
        .order_by('-started_at')
        .first()
    )
    if not case:
        case = Case.objects.create(
            case_id=str(uuid.uuid4()),
            user=user,
            regime=regime,
            status=Case.DRAFT,
        )
    return case


# ── Section status bootstrap ──────────────────────────────────────────────────

def bootstrap_section_statuses(user, regime, sections):
    """
    Ensure a SectionStatus record exists for every permitted section in this
    regime for this user.

    Called by department Layer 1 when a citizen enters a regime. Safe to call
    multiple times (idempotent).

    Args:
        user:     User instance
        regime:   Regime instance
        sections: QuerySet of permitted Section instances
    """
    for section in sections:
        SectionStatus.objects.get_or_create(
            user=user,
            regime=regime,
            section=section,
            defaults={'status': 'not_started'},
        )
