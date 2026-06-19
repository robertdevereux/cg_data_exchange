"""
core/views_layer1.py — Shared Layer 1 navigation views.

Generic (department-neutral) views served at /regime/... for all departments.
Implements Pattern B (direct section list) and Pattern C (schedule → section
list) navigation.

Departments register their own regime home pages and link here for navigation.
Breadcrumbs and regime_home_url are read from session, where they are expected
to have been set by the regime home page.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from core.models import Regime, Schedule, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session

_STATUS_LABEL = {
    'not_started': 'Not started',
    'in_progress': 'In progress',
    'complete':    'Complete',
}


# ── Pattern B — direct section list (no schedule) ────────────────────────────

@login_required
def regime_sections(request, regime_id):
    """
    Pattern B: list direct sections for a regime (no schedule).
    Reads breadcrumbs and regime_home_url from session (set by regime home page).
    Sets return_url in session so section_done redirects back here.
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    session_section_ids = pss.get('permitted_section_ids')
    if session_section_ids:
        # Dept-specified section list — filter to those IDs only.
        # get_permitted_sections still enforces permissions; schedule filter
        # is intentionally dropped since dept may specify schedule-assigned sections.
        permitted = get_permitted_sections(actor, user).filter(
            section_id__in=session_section_ids,
        )
    else:
        permitted = get_permitted_sections(actor, user).filter(
            regime_id=regime_id,
            schedule__isnull=True,
        )
    title = pss.get('section_list_title') or regime.regime_name

    section_statuses = {
        ss.section_id: ss.status
        for ss in SectionStatus.objects.filter(
            user=user, regime=regime, section__in=permitted,
        )
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
            'status_display': _STATUS_LABEL.get(status, 'Not started'),
            'action_url':     action_url,
        })

    regime_home_url  = pss.get('regime_home_url', '/')
    breadcrumbs      = pss.get('breadcrumbs', [])
    section_list_url = reverse('core:regime_sections', kwargs={'regime_id': regime_id})

    update_session(request, {
        'return_url':      section_list_url,
        'schedule_id':     None,
        'regime_home_url': regime_home_url,
        'breadcrumbs':     breadcrumbs,
    })

    return render(request, 'core/regime_sections.html', {
        'regime':      regime,
        'sections':    section_data,
        'back_url':    regime_home_url,
        'breadcrumbs': breadcrumbs,
        'acting_for':  get_acting_for_name(pss),
        'title':       title,
    })


# ── Pattern C level 1 — schedule list ────────────────────────────────────────

@login_required
def regime_schedules(request, regime_id):
    """
    Pattern C level 1: list schedules for a regime.
    Reads breadcrumbs and regime_home_url from session (set by regime home page).
    Links each schedule to the core regime_schedule_sections view.
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    permitted = get_permitted_sections(actor, user).filter(
        schedule__regime_id=regime_id
    ).select_related('schedule')

    schedule_ids = list(permitted.values_list('schedule_id', flat=True).distinct())
    schedules = (
        Schedule.objects
        .filter(schedule_id__in=schedule_ids)
        .order_by('display_order')
    )

    section_statuses = {
        ss.section_id: ss.status
        for ss in SectionStatus.objects.filter(
            user=user, regime=regime, section__in=permitted,
        )
    }

    schedule_data = []
    for sched in schedules:
        sched_sections = permitted.filter(schedule=sched)
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
            'section_count':  sched_sections.count(),
            'status':         sched_status,
            'status_display': _STATUS_LABEL[sched_status],
            'url': reverse(
                'core:regime_schedule_sections',
                kwargs={'regime_id': regime_id, 'schedule_id': sched.schedule_id},
            ),
        })

    regime_home_url   = pss.get('regime_home_url', '/')
    breadcrumbs       = pss.get('breadcrumbs', [])
    schedule_list_url = reverse('core:regime_schedules', kwargs={'regime_id': regime_id})

    update_session(request, {
        'regime_home_url':   regime_home_url,
        'schedule_list_url': schedule_list_url,
    })

    return render(request, 'core/select_schedule.html', {
        'regime':      regime,
        'schedules':   schedule_data,
        'back_url':    regime_home_url,
        'breadcrumbs': breadcrumbs,
        'acting_for':  get_acting_for_name(pss),
    })


# ── Pattern C level 2 — section list within a schedule ───────────────────────

@login_required
def regime_schedule_sections(request, regime_id, schedule_id):
    """
    Pattern C level 2: list sections within a schedule.
    Sets return_url in session so section_done redirects back here.
    Extends session breadcrumbs with the schedule name for use by Layer 2 pages.
    """
    actor    = request.user
    pss      = get_session(request)
    user     = _resolve_user(pss, actor)
    regime   = get_object_or_404(Regime, regime_id=regime_id)
    schedule = get_object_or_404(Schedule, schedule_id=schedule_id)

    permitted = get_permitted_sections(actor, user).filter(
        Q(regime_id=regime_id) | Q(schedule__regime_id=regime_id)
    ).filter(schedule_id=schedule_id)

    section_statuses = {
        ss.section_id: ss.status
        for ss in SectionStatus.objects.filter(
            user=user, regime=regime, section__in=permitted,
        )
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
            'status_display': _STATUS_LABEL.get(status, 'Not started'),
            'action_url':     action_url,
        })

    regime_home_url   = pss.get('regime_home_url', '/')
    schedule_list_url = reverse('core:regime_schedules', kwargs={'regime_id': regime_id})
    section_list_url  = reverse(
        'core:regime_schedule_sections',
        kwargs={'regime_id': regime_id, 'schedule_id': schedule_id},
    )

    # Build breadcrumbs: truncate session crumbs to the regime level (to avoid
    # stacking on repeated visits), then append the schedule name.
    base_crumbs = pss.get('breadcrumbs', [])
    truncated = base_crumbs
    for i, crumb in enumerate(base_crumbs):
        if crumb.get('url') == regime_home_url:
            truncated = base_crumbs[:i + 1]
            break
    crumbs = truncated + [
        {'label': schedule.schedule_name, 'url': section_list_url},
    ]

    update_session(request, {
        'return_url':        section_list_url,
        'schedule_id':       schedule_id,
        'breadcrumbs':       crumbs,
        'regime_home_url':   regime_home_url,
        'schedule_list_url': schedule_list_url,
    })

    return render(request, 'core/select_section.html', {
        'regime':      regime,
        'schedule':    schedule,
        'sections':    section_data,
        'back_url':    schedule_list_url,
        'breadcrumbs': crumbs,
        'acting_for':  get_acting_for_name(pss),
        'title':       schedule.schedule_name,
    })
