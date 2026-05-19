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
- Use call_regime(), call_schedules(), or call_sections() as a single-call
  shortcut that sets all session keys and returns the entry URL
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


# ── Call helpers ──────────────────────────────────────────────────────────────

def _build_permitted_lists(permitted):
    """
    Derive permitted_schedule_ids and permitted_section_ids from a permitted
    sections queryset.

    schedule_ids: distinct, ordered by schedule display_order then schedule_id.
    section_ids:  list of section_id strings.
    """
    permitted_schedule_ids = list(dict.fromkeys(
        permitted
        .filter(schedule__isnull=False)
        .order_by('schedule__display_order', 'schedule__schedule_id')
        .values_list('schedule__schedule_id', flat=True)
    ))
    permitted_section_ids = list(
        permitted.values_list('section_id', flat=True)
    )
    return permitted_schedule_ids, permitted_section_ids


def call_regime(request, regime, actor, user, url_prefix=''):
    """
    Full-regime entry point.

    Finds/creates a case, bootstraps section statuses, writes all SESSION_KEYS
    plus permitted_schedule_ids, permitted_section_ids, and return_url to
    session, then returns the Layer 1 entry URL.

    url_prefix: optional dept prefix (e.g. 'hmrc') — when provided, any
    /regime/... entry URL is rewritten to /<prefix>/regime/... so the calling
    view does not need a separate remap block.
    """
    from django.db.models import Q
    from .permissions import get_permitted_sections
    from .nav_reference import resolve_layer1_entry_url
    from .session import update_session

    permitted = get_permitted_sections(actor, user).filter(
        Q(regime=regime) | Q(schedule__regime=regime)
    )

    case = get_or_create_case(user, regime)
    bootstrap_section_statuses(user, regime, permitted)

    permitted_schedule_ids, permitted_section_ids = _build_permitted_lists(permitted)

    update_session(request, {
        'user_id':                user.pk,
        'actor_id':               actor.pk,
        'regime_id':              regime.regime_id,
        'case_id':                case.case_id,
        'return_url':             request.path,
        'permitted_schedule_ids': permitted_schedule_ids,
        'permitted_section_ids':  permitted_section_ids,
    })

    entry_url = resolve_layer1_entry_url(permitted, regime.regime_id)
    if url_prefix and entry_url.startswith('/regime/'):
        entry_url = '/' + url_prefix.strip('/') + entry_url
    return entry_url


def call_schedules(request, regime, actor, user, schedule_ids, url_prefix=''):
    """
    Schedule-filtered entry point.

    Like call_regime but only includes sections whose schedule is in
    schedule_ids. Useful when an intermediary has access to specific schedules
    rather than the whole regime.

    url_prefix: see call_regime.
    """
    from .permissions import get_permitted_sections
    from .nav_reference import resolve_layer1_entry_url
    from .session import update_session

    permitted = get_permitted_sections(actor, user).filter(
        schedule__schedule_id__in=schedule_ids
    )

    case = get_or_create_case(user, regime)
    bootstrap_section_statuses(user, regime, permitted)

    permitted_schedule_ids, permitted_section_ids = _build_permitted_lists(permitted)

    update_session(request, {
        'user_id':                user.pk,
        'actor_id':               actor.pk,
        'regime_id':              regime.regime_id,
        'case_id':                case.case_id,
        'return_url':             request.path,
        'permitted_schedule_ids': permitted_schedule_ids,
        'permitted_section_ids':  permitted_section_ids,
    })

    entry_url = resolve_layer1_entry_url(permitted, regime.regime_id)
    if url_prefix and entry_url.startswith('/regime/'):
        entry_url = '/' + url_prefix.strip('/') + entry_url
    return entry_url


def call_sections(request, regime, actor, user, section_ids, url_prefix=''):
    """
    Section-filtered entry point.

    Like call_regime but only includes sections whose section_id is in
    section_ids. Useful when an intermediary has access to specific sections
    rather than the whole regime or schedule.

    url_prefix: see call_regime.
    """
    from .permissions import get_permitted_sections
    from .nav_reference import resolve_layer1_entry_url
    from .session import update_session

    permitted = get_permitted_sections(actor, user).filter(
        section_id__in=section_ids
    )

    case = get_or_create_case(user, regime)
    bootstrap_section_statuses(user, regime, permitted)

    permitted_schedule_ids, permitted_section_ids = _build_permitted_lists(permitted)

    update_session(request, {
        'user_id':                user.pk,
        'actor_id':               actor.pk,
        'regime_id':              regime.regime_id,
        'case_id':                case.case_id,
        'return_url':             request.path,
        'permitted_schedule_ids': permitted_schedule_ids,
        'permitted_section_ids':  permitted_section_ids,
    })

    entry_url = resolve_layer1_entry_url(permitted, regime.regime_id)
    if url_prefix and entry_url.startswith('/regime/'):
        entry_url = '/' + url_prefix.strip('/') + entry_url
    return entry_url
