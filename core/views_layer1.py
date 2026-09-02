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
from core.nav_reference import resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, set_crumb, update_session

_STATUS_LABEL = {
    'not_started': 'Not started',
    'in_progress': 'In progress',
    'complete':    'Complete',
}


def _rollup_status(statuses):
    """
    Roll up a list of section/schedule status strings into a single status.
    all complete → complete; any in_progress or complete → in_progress; else not_started.
    """
    if not statuses:
        return 'not_started'
    if all(s == 'complete' for s in statuses):
        return 'complete'
    if any(s in ('in_progress', 'complete') for s in statuses):
        return 'in_progress'
    return 'not_started'


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
    user   = resolve_user(pss, actor)
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
    user   = resolve_user(pss, actor)
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
    user     = resolve_user(pss, actor)
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

    crumbs = set_crumb(pss, schedule.schedule_name, section_list_url)

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


# ── Top-level mixed items (schedules + bare sections) ────────────────────────

@login_required
def regime_top_level(request, regime_id):
    """
    Render a mixed list of schedules and bare sections drawn from
    top_level_items (written by call_core).  Each schedule entry rolls up
    the statuses of its child sections; each bare-section entry shows its
    own status directly.
    """
    actor  = request.user
    pss    = get_session(request)
    user   = resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    top_level_items = pss.get('top_level_items', [])
    title           = pss.get('top_level_title') or regime.regime_name

    schedule_ids_needed = [i['id'] for i in top_level_items if i['type'] == 'schedule']
    section_ids_needed  = [i['id'] for i in top_level_items if i['type'] == 'section']

    # Permitted sections (for both schedules and bare sections)
    permitted = get_permitted_sections(actor, user).filter(
        Q(schedule__schedule_id__in=schedule_ids_needed) |
        Q(section_id__in=section_ids_needed)
    ).select_related('schedule')

    section_statuses = {
        ss.section_id: ss.status
        for ss in SectionStatus.objects.filter(
            user=user, regime=regime, section__in=permitted,
        )
    }

    # Pre-build schedule objects keyed by schedule_id
    schedules_by_id = {
        s.schedule_id: s
        for s in Schedule.objects.filter(schedule_id__in=schedule_ids_needed)
    }

    items_data = []
    for item in top_level_items:
        if item['type'] == 'schedule':
            sched = schedules_by_id.get(item['id'])
            if not sched:
                continue
            sched_sections = permitted.filter(schedule_id=item['id'])
            statuses = [section_statuses.get(s.section_id, 'not_started') for s in sched_sections]
            status   = _rollup_status(statuses)
            section_count = sched_sections.count()
            url = reverse(
                'core:regime_schedule_sections',
                kwargs={'regime_id': regime_id, 'schedule_id': item['id']},
            )
            items_data.append({
                'type':           'schedule',
                'label':          sched.schedule_name,
                'section_count':  section_count,
                'status':         status,
                'status_display': _STATUS_LABEL[status],
                'url':            url,
            })
        else:
            sect_qs = permitted.filter(section_id=item['id'])
            if not sect_qs.exists():
                continue
            sect   = sect_qs.first()
            status = section_statuses.get(sect.section_id, 'not_started')
            if sect.section_type in (1, 2):
                url = f'/section/{sect.section_id}/table/'
            else:
                url = f'/section/{sect.section_id}/start/'
            items_data.append({
                'type':           'section',
                'label':          sect.section_name,
                'status':         status,
                'status_display': _STATUS_LABEL.get(status, 'Not started'),
                'url':            url,
            })

    regime_home_url = pss.get('regime_home_url', '/')
    top_level_url   = reverse('core:regime_top_level', kwargs={'regime_id': regime_id})

    crumbs = set_crumb(pss, title or regime.regime_name, top_level_url)

    update_session(request, {
        'return_url':      top_level_url,   # so section_done returns here
        'regime_home_url': regime_home_url,
        'breadcrumbs':     crumbs,
    })

    return render(request, 'core/regime_top_level.html', {
        'regime':      regime,
        'items':       items_data,
        'title':       title,
        'back_url':    regime_home_url,
        'breadcrumbs': crumbs,
        'acting_for':  get_acting_for_name(pss),
    })
