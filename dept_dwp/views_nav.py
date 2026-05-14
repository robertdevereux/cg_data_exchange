"""
dept_dwp/views_nav.py — Layer 1 navigation views for dept_dwp.

All DWP regimes use the generic regime home view — there is no slug map.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import Regime, Schedule, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_regimes, get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session


# ─────────────────────────────────────────────────────────────────────────────
# SELECT REGIME
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_regime(request):
    """
    Show available regimes for the actor/user pair.
    Auto-skips when only one regime is available; redirects to dept_home
    when multiple regimes exist.
    """
    pss   = get_session(request)
    actor = request.user
    user  = _resolve_user(pss, actor)

    if not pss.get('user_id'):
        update_session(request, {'user_id': user.pk, 'actor_id': actor.pk})

    regimes = get_permitted_regimes(actor, user)

    if not regimes.exists():
        return render(request, 'dept_dwp/nav/select_regime.html', {
            'regimes':   [],
            'no_access': True,
        })

    if regimes.count() == 1:
        return redirect(
            reverse('dept_dwp:regime_home',
                    kwargs={'regime_id': regimes.first().regime_id})
        )

    return redirect(reverse('dept_dwp:dept_home'))


# ─────────────────────────────────────────────────────────────────────────────
# SELECT SCHEDULE — Pattern C first level
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_schedule(request, regime_id):
    """Show schedules containing at least one permitted section."""
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

    _status_label = {
        'not_started': 'Not started',
        'in_progress': 'In progress',
        'complete':    'Complete',
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
            'status_display': _status_label[sched_status],
            'url': reverse(
                'dept_dwp:select_section_in_schedule',
                kwargs={'regime_id': regime_id, 'schedule_id': sched.schedule_id},
            ),
        })

    regime_home_url = reverse('dept_dwp:regime_home', kwargs={'regime_id': regime_id})
    crumbs = [
        {'label': 'DWP',              'url': '/dwp/'},
        {'label': 'DWP Account',      'url': '/dwp/regimes/'},
        {'label': regime.regime_name, 'url': regime_home_url},
    ]
    update_session(request, {
        'breadcrumbs':     crumbs,
        'regime_home_url': regime_home_url,
    })
    return render(request, 'dept_dwp/nav/select_schedule.html', {
        'regime':      regime,
        'schedules':   schedule_data,
        'back_url':    reverse('dept_dwp:dept_home'),
        'breadcrumbs': crumbs,
        'acting_for':  get_acting_for_name(pss),
    })


# ─────────────────────────────────────────────────────────────────────────────
# SELECT SECTION — Pattern B task list; Pattern C second level
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_section(request, regime_id, schedule_id=None):
    """
    Task-list view for all permitted sections in this regime.
    Filtered by schedule_id when coming from the schedule menu.
    Sets return_url so section_done redirects back here.
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

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

    regime_home_url = reverse('dept_dwp:regime_home', kwargs={'regime_id': regime_id})

    if schedule_id:
        back_url         = reverse('dept_dwp:select_schedule',
                                   kwargs={'regime_id': regime_id})
        return_url       = reverse('dept_dwp:select_section_in_schedule',
                                   kwargs={'regime_id': regime_id,
                                           'schedule_id': schedule_id})
        section_list_url = return_url
        crumbs = [
            {'label': 'DWP',                  'url': '/dwp/'},
            {'label': 'DWP Account',          'url': '/dwp/regimes/'},
            {'label': regime.regime_name,     'url': regime_home_url},
            {'label': schedule.schedule_name, 'url': section_list_url},
        ]
    else:
        back_url   = reverse('dept_dwp:dept_home')
        return_url = reverse('dept_dwp:select_section',
                             kwargs={'regime_id': regime_id})
        crumbs = [
            {'label': 'DWP',              'url': '/dwp/'},
            {'label': 'DWP Account',      'url': '/dwp/regimes/'},
            {'label': regime.regime_name, 'url': regime_home_url},
        ]

    schedule_list_url = (
        reverse('dept_dwp:select_schedule', kwargs={'regime_id': regime_id})
        if schedule_id else None
    )

    update_session(request, {
        'return_url':        return_url,
        'schedule_id':       schedule_id,
        'breadcrumbs':       crumbs,
        'regime_home_url':   regime_home_url,
        'schedule_list_url': schedule_list_url,
    })

    return render(request, 'dept_dwp/nav/select_section.html', {
        'regime':      regime,
        'schedule':    schedule,
        'sections':    section_data,
        'back_url':    back_url,
        'breadcrumbs': crumbs,
        'acting_for':  get_acting_for_name(pss),
    })
