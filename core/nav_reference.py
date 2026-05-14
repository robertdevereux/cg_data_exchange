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

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Regime, Schedule, Section, SectionStatus, User
from .permissions import get_permitted_sections
from .session import get_session


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


# ── Pattern C: Schedule menu ──────────────────────────────────────────────────

# Reference implementation — departments may adapt

@login_required
def select_schedule(request, regime_id):
    """Show schedules that contain at least one permitted section."""
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    session_schedule_ids = pss.get('permitted_schedule_ids')
    session_section_ids  = pss.get('permitted_section_ids')

    if session_schedule_ids is not None and session_section_ids is not None:
        # Use session-cached permission lists (set by call_regime / call_schedules)
        permitted = Section.objects.filter(
            section_id__in=session_section_ids,
            schedule__isnull=False,
        ).select_related('schedule')
        schedules = (
            Schedule.objects
            .filter(schedule_id__in=session_schedule_ids)
            .order_by('display_order')
        )
    else:
        # Fallback: derive from DB (used in tests and direct URL access)
        permitted = get_permitted_sections(actor, user).filter(
            schedule__regime_id=regime_id
        ).select_related('schedule')
        schedule_ids = list(
            permitted.values_list('schedule_id', flat=True).distinct()
        )
        schedules = (
            Schedule.objects
            .filter(schedule_id__in=schedule_ids)
            .order_by('display_order')
        )

    # Section statuses for the user, keyed by section_id
    section_statuses = {
        ss.section_id: ss.status
        for ss in SectionStatus.objects.filter(
            user=user, regime=regime, section__in=permitted,
        )
    }

    _status_label = {
        'not_started': 'Not started',
        'in_progress': 'In progress',
        'complete':    'Complete',
    }

    schedule_data = []
    for sched in schedules:
        sched_sections = permitted.filter(schedule=sched)
        section_count  = sched_sections.count()

        statuses = [
            section_statuses.get(s.section_id, 'not_started')
            for s in sched_sections
        ]
        if all(s == 'complete' for s in statuses):
            sched_status = 'complete'
        elif any(s in ('in_progress', 'complete') for s in statuses):
            sched_status = 'in_progress'
        else:
            sched_status = 'not_started'

        schedule_data.append({
            'schedule':       sched,
            'section_count':  section_count,
            'status':         sched_status,
            'status_display': _status_label[sched_status],
            'url':            f'/regime/{regime_id}/schedule/{sched.schedule_id}/sections/',
        })

    return render(request, 'core/select_schedule.html', {
        'regime':    regime,
        'schedules': schedule_data,
        'back_url':  '/select-regime/',
    })


# ── Pattern B: Section task list ──────────────────────────────────────────────

# Reference implementation — departments may adapt

@login_required
def select_section(request, regime_id, schedule_id=None):
    """
    Task-list view: all permitted sections for this regime (filtered by
    schedule_id when coming from the schedule menu).

    Each section shows its status and an action link:
      complete     → /section/<id>/review/  (allow amendment)
      not started  → /section/<id>/start/ or /section/<id>/table/
      in progress  → /section/<id>/start/ or /section/<id>/table/
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    session_section_ids = pss.get('permitted_section_ids')

    if session_section_ids is not None:
        # Use session-cached permission list (set by call_regime / call_sections)
        permitted = Section.objects.filter(section_id__in=session_section_ids)
    else:
        # Fallback: derive from DB (used in tests and direct URL access)
        permitted = get_permitted_sections(actor, user).filter(
            Q(regime_id=regime_id) | Q(schedule__regime_id=regime_id)
        )

    if schedule_id:
        schedule = get_object_or_404(Schedule, schedule_id=schedule_id)
        permitted = permitted.filter(schedule_id=schedule_id)
    else:
        schedule = None

    section_statuses = {
        ss.section_id: ss.status
        for ss in SectionStatus.objects.filter(
            user=user, regime=regime, section__in=permitted,
        )
    }

    _status_label = {
        'not_started': 'Not started',
        'in_progress': 'In progress',
        'complete':    'Complete',
    }

    section_data = []
    for section in permitted.order_by('display_order', 'section_name'):
        status = section_statuses.get(section.section_id, 'not_started')

        if section.section_type in (1, 2):
            action_url = f'/section/{section.section_id}/table/'
        else:
            action_url = f'/section/{section.section_id}/start/'

        section_data.append({
            'section':        section,
            'status':         status,
            'status_display': _status_label.get(status, 'Not started'),
            'action_url':     action_url,
        })

    if schedule_id:
        back_url = f'/regime/{regime_id}/schedules/'
    else:
        back_url = '/select-regime/'

    return render(request, 'core/select_section.html', {
        'regime':   regime,
        'schedule': schedule,
        'sections': section_data,
        'back_url': back_url,
    })
