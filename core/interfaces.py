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
- Use call_regime() or call_core() as a single-call shortcut that sets all
  session keys and returns the entry URL
"""

import uuid

from django.db import transaction

from .models import Answer, Case, Permission, SectionStatus


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


def call_core(request, regime, actor, user, items, title=None, url_prefix=''):
    """
    Unified core entry point.

    items: ordered list of dicts, each {'type': 'schedule'|'section', 'id': str}
    title: optional heading for the top-level list page
    url_prefix: dept namespace prefix e.g. 'hmrc'
    """
    from django.db.models import Q
    from .permissions import get_permitted_sections
    from .session import get_session, update_session

    session_case_id = request.session.get('case_id')
    base_qs = get_permitted_sections(actor, user, case_id=session_case_id).filter(
        Q(regime=regime) | Q(schedule__regime=regime)
    )

    schedule_ids_in = [i['id'] for i in items if i['type'] == 'schedule']
    section_ids_in  = [i['id'] for i in items if i['type'] == 'section']

    permitted = base_qs.filter(
        Q(schedule__schedule_id__in=schedule_ids_in) |
        Q(section_id__in=section_ids_in)
    ) if (schedule_ids_in or section_ids_in) else base_qs.none()

    case = get_or_create_case(user, regime)
    bootstrap_section_statuses(user, regime, permitted)

    permitted_schedule_ids, permitted_section_ids = _build_permitted_lists(permitted)

    # Build ordered top-level items, filtered to what user can actually see
    permitted_schedule_set = set(permitted_schedule_ids)
    permitted_section_set  = set(permitted_section_ids)

    ordered_items = []
    for item in items:
        if item['type'] == 'schedule' and item['id'] in permitted_schedule_set:
            ordered_items.append(item)
        elif item['type'] == 'section' and item['id'] in permitted_section_set:
            ordered_items.append(item)

    pss = get_session(request)
    regime_home_url = pss.get('regime_home_url', request.path)

    update_session(request, {
        'user_id':                user.pk,
        'actor_id':               actor.pk,
        'regime_id':              regime.regime_id,
        'case_id':                case.case_id,
        'return_url':             regime_home_url,
        'permitted_schedule_ids': permitted_schedule_ids,
        'permitted_section_ids':  permitted_section_ids,
        'top_level_items':        ordered_items,
        'top_level_title':        title or regime.regime_name,
    })

    # Route
    def _prefix(url):
        if url_prefix and url.startswith('/regime/'):
            return '/' + url_prefix.strip('/') + url
        return url

    if not ordered_items:
        return _prefix(f'/regime/{regime.regime_id}/sections/')

    if len(ordered_items) == 1:
        item = ordered_items[0]
        if item['type'] == 'section':
            return f'/section/{item["id"]}/start/'
        else:
            return _prefix(f'/regime/{regime.regime_id}/schedule/{item["id"]}/sections/')

    return _prefix(f'/regime/{regime.regime_id}/top/')


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
    from .models import Schedule, Section
    schedule_ids = list(
        Schedule.objects.filter(regime=regime)
        .order_by('display_order', 'schedule_id')
        .values_list('schedule_id', flat=True)
    )
    bare_section_ids = list(
        Section.objects.filter(regime=regime, schedule__isnull=True)
        .order_by('display_order', 'section_id')
        .values_list('section_id', flat=True)
    )
    items = (
        [{'type': 'schedule', 'id': sid} for sid in schedule_ids] +
        [{'type': 'section',  'id': sid} for sid in bare_section_ids]
    )
    return call_core(request, regime, actor, user, items, url_prefix=url_prefix)


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


def get_asked_answers_for_section(case, section):
    """
    Replay this section's routing against the case's confirmed answers and
    return the questions actually reached, in the order asked.

    Returns an ordered list of dicts::

        [{'question_id': str, 'question_text': str, 'answer': any}, ...]

    Set nodes are expanded to their member questions in display order.
    Stops at the first unanswered/unreached node, mirroring the re-entry
    reconstruction in section_start.

    Designed to be called by department apps that need to summarise or
    validate what a citizen answered in a completed section.
    """
    # Local imports — keeps layer2 helpers private; avoids future circular risk.
    from .models import Answer, Routing
    from .views_layer2 import (
        _build_section_tables,
        _evaluate_routing,
    )

    routing_rows = Routing.objects.filter(section=section).order_by('order_in_section')
    tables = _build_section_tables(routing_rows)
    if not tables['first_node']:
        return []

    # Collect all question IDs reachable in this section (direct nodes + set members)
    all_question_ids = tables['question_node_ids'] + list(tables['question_to_set'].keys())
    answers = {
        a.question_id: a.answer
        for a in Answer.objects.filter(
            user=case.user, case=case, question_id__in=all_question_ids,
        )
    }

    results = []
    node = tables['first_node']
    while node is not None:
        if node in tables['set_table']:
            # Set node — expand members in display order
            for member in tables['set_table'][node]['members']:
                qid = member['question_id']
                if qid not in answers:
                    return results          # stop at first unanswered member
                results.append({
                    'question_id':   qid,
                    'question_text': member['question_text'],
                    'question_type': member.get('question_type', ''),
                    'answer':        answers[qid],
                })
        else:
            # Direct question node
            if node not in answers:
                return results              # stop at first unanswered question
            q = tables['question_table'][node]
            results.append({
                'question_id':   node,
                'question_text': q['question_text'],
                'question_type': q.get('question_type', ''),
                'answer':        answers[node],
            })

        next_node, found = _evaluate_routing(tables['routing_table'], node, answers)
        if not found:
            break
        node = next_node

    return results


def format_answer_for_display(question_type, answer):
    """
    Turn a raw Answer.answer value into a human-readable display string.

    question_type: the Question.question_type string (e.g. 'text', 'date',
                   'personal_name', 'address', 'compound', 'checkbox', …)
    answer:        the stored value — may be a plain string, list, or dict
                   depending on question_type.

    Returns a non-empty string; uses '—' as the empty sentinel.
    """
    _months = ['January', 'February', 'March', 'April', 'May', 'June',
               'July', 'August', 'September', 'October', 'November', 'December']

    if question_type == 'compound' and isinstance(answer, dict):
        return '\n'.join(f'{k}: {v}' for k, v in answer.items() if v) or '—'

    if isinstance(answer, dict) and all(k in answer for k in ('day', 'month', 'year')):
        try:
            mon = int(answer['month'])
            return f"{answer['day']} {_months[mon - 1]} {answer['year']}"
        except (ValueError, IndexError):
            return (
                f"{answer.get('day', '')} {answer.get('month', '')} {answer.get('year', '')}"
            )

    if isinstance(answer, dict) and 'first_name' in answer:
        return ' '.join(filter(None, [
            answer.get('title', ''),
            answer.get('first_name', ''),
            answer.get('middle_name', ''),
            answer.get('last_name', ''),
        ])) or '—'

    if isinstance(answer, dict) and 'line1' in answer:
        return '\n'.join(filter(None, [
            answer.get('line1', ''),
            answer.get('line2', ''),
            answer.get('city', ''),
            answer.get('county', ''),
            answer.get('postcode', ''),
        ])) or '—'

    if isinstance(answer, list):
        return ', '.join(answer)

    return answer or '—'


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


def reset_section_progress(user, regime):
    """
    Clear all SectionStatus rows for this user/regime — used when starting
    a fresh case where any stale in-progress/complete status from a prior
    case must not carry over.

    Core-owned operation: if SectionStatus ever gains related state (e.g. an
    audit trail), this is the one place that needs to know about it.
    """
    SectionStatus.objects.filter(user=user, regime=regime).delete()


@transaction.atomic
def promote_case_to_verified(case, actor, deceased, reference):
    """
    Promote a draft case from the executor's identity to the deceased's,
    once matching has confirmed which existing (or new) deceased record
    this case belongs to.

    Re-keys all Answer and SectionStatus rows from actor to deceased, updates
    the case itself, and grants the actor permission to continue working the
    case under the deceased's identity.

    Core-owned: this touches four models in one operation and must stay
    atomic and consistent if any of those models change shape.
    """
    Answer.objects.filter(case=case, user=actor).update(user=deceased)
    SectionStatus.objects.filter(user=actor, regime=case.regime).update(user=deceased)
    case.user = deceased
    case.reference = reference
    case.save()
    Permission.objects.create(
        actor=actor,
        user=deceased,
        regime=case.regime,
        case=case,
        section=None,
        can_delegate=False,
    )
