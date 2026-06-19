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

def create_case(user, regime):
    """
    Always create a fresh draft Case for this user/regime.

    Use this (not get_or_create_case) when starting a new submission.

    Args:
        user:   User instance (the subject, not the actor)
        regime: Regime instance
    Returns:
        New Case instance (status=Case.DRAFT)
    """
    return Case.objects.create(
        case_id=str(uuid.uuid4()),
        user=user,
        regime=regime,
        status=Case.DRAFT,
    )


def get_cases(user, regime, status=None):
    """
    Return a queryset of Case objects for this user + regime, most recent first.

    Args:
        user:   User instance (the subject)
        regime: Regime instance
        status: optional — one of Case.DRAFT, Case.SUBMITTED, Case.LAPSED;
                if omitted all statuses are returned
    Returns:
        QuerySet of Case ordered by -started_at
    """
    qs = Case.objects.filter(user=user, regime=regime).order_by('-started_at')
    if status is not None:
        qs = qs.filter(status=status)
    return qs


def get_or_create_case(user, regime):
    """
    Find the most recent draft Case for this user/regime, or create one if
    none exists.

    # DEPRECATED: use create_case() for new cases, get_cases() to find
    # existing ones. Retained for TEST/demo backward compatibility only.

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

    session_case_id = request.session.get('case_id')
    permitted = get_permitted_sections(actor, user, case_id=session_case_id).filter(
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

    session_case_id = request.session.get('case_id')
    permitted = get_permitted_sections(actor, user, case_id=session_case_id).filter(
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


def call_sections(request, regime, actor, user, section_ids, url_prefix='', title=None):
    """
    Section-filtered entry point.

    Like call_regime but only includes sections whose section_id is in
    section_ids. Useful when an intermediary has access to specific sections
    rather than the whole regime or schedule.

    url_prefix: see call_regime.
    title: optional heading for the section list page (multiple sections only).
    """
    from .permissions import get_permitted_sections
    from .session import update_session

    session_case_id = request.session.get('case_id')
    permitted = get_permitted_sections(actor, user, case_id=session_case_id).filter(
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
        'return_url':             request.session.get('regime_home_url', request.path),
        'permitted_schedule_ids': permitted_schedule_ids,
        'permitted_section_ids':  permitted_section_ids,
    })

    ordered = []
    for sid in section_ids:
        s = permitted.filter(section_id=sid).first()
        if s:
            ordered.append(s)

    if not ordered:
        return (
            f'/{url_prefix.strip("/")}/regime/{regime.regime_id}/sections/'
            if url_prefix else
            f'/regime/{regime.regime_id}/sections/'
        )

    if len(ordered) == 1:
        first = ordered[0]
        if first.section_type in (1, 2):
            return f'/section/{first.section_id}/table/'
        return f'/section/{first.section_id}/start/'

    # Multiple sections — store in session and route to filtered section list
    update_session(request, {
        'permitted_section_ids': [s.section_id for s in ordered],
        'section_list_title':    title or regime.regime_name,
    })
    prefix = f'/{url_prefix.strip("/")}' if url_prefix else ''
    return f'{prefix}/regime/{regime.regime_id}/sections/'


# ── Answer utilities ──────────────────────────────────────────────────────────

def get_answers(case, question_ids):
    """
    Return a dict of {question_id: answer} for the given case and question IDs.

    Uses case.user for the user filter — the correct user for all answer
    lookups within a case.

    Returns None for any question_id not found.
    """
    from .models import Answer
    rows = Answer.objects.filter(
        user=case.user,
        case=case,
        question_id__in=question_ids,
    )
    result = {qid: None for qid in question_ids}
    for row in rows:
        result[row.question_id] = row.answer
    return result


def format_date(answer):
    """
    Format a date-type answer dict {day, month, year} as DD/MM/YYYY.
    Returns empty string if answer is None or not a dict.
    """
    if not isinstance(answer, dict):
        return str(answer) if answer else ''
    day   = str(answer.get('day',   '')).zfill(2)
    month = str(answer.get('month', '')).zfill(2)
    year  = answer.get('year', '')
    return f'{day}/{month}/{year}'
