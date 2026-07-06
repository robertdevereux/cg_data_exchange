"""
core/nav_reference.py — Reference navigation patterns.

These are worked examples of the three Layer 1 navigation patterns described
in the Functional Architecture document. They are not part of the platform —
departments are free to use, adapt, or ignore them entirely.

Pattern A: single section — navigate directly to section
Pattern B: section menu  — present list of sections
Pattern C: schedule menu — present schedules, then sections

Each pattern function takes a request and the permitted sections QuerySet and
returns an HttpResponse or redirect. Department views call these functions
after setting the four SESSION_KEYS.
"""

from .models import User


# ── Shared helper ─────────────────────────────────────────────────────────────

def _resolve_user(pss, actor):
    """Return the User the actor is acting for, defaulting to actor themselves."""
    user_id = pss.get('user_id')
    if user_id:
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            pass
    return actor


# ── Pattern A/B/C routing helper ─────────────────────────────────────────────

# Reference implementation — departments may adapt

def resolve_layer1_entry_url(permitted, regime_id, all_complete=False):
    """
    Determine the correct Layer 1 entry-point URL given the set of permitted
    sections and their completion state.

    Pattern A — single section:          go directly to the section
    Pattern B — multiple, no schedules:  section task list
    Pattern C — sections under schedules: schedule menu

    Args:
        permitted:    QuerySet of permitted Section instances for this regime
        regime_id:    str — the regime_id
        all_complete: bool — True when every section is complete (Pattern A
                      only: routes to review instead of start)
    Returns:
        str — the URL to use as the entry point button href
    """
    section_count = permitted.count()

    if section_count == 0:
        # No accessible sections — fall through to an empty section list
        return f'/regime/{regime_id}/sections/'

    if section_count == 1:
        # Pattern A: go directly to the one permitted section.
        # Always route via section_start — it detects existing answers and
        # redirects to review automatically, so /review/ is never needed here.
        section = permitted.first()
        if section.section_type in (1, 2):
            return f'/section/{section.section_id}/table/'
        return f'/section/{section.section_id}/start/'

    if permitted.filter(schedule__isnull=False).exists():
        # Pattern C: sections under schedules — show schedule menu first
        return f'/regime/{regime_id}/schedules/'

    # Pattern B: multiple sections, no schedules — show section task list
    return f'/regime/{regime_id}/sections/'


