"""
dept_demo/views_nav.py — Layer 1 navigation views for dept_demo.

Implements all three navigation patterns using the platform interfaces and
reference implementations from core.nav_reference, adapted for dept_demo's
URL structure (/demo/ prefix) and templates.

These are the department's chosen implementations — departments are free to
adapt the core reference patterns as needed.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import Regime, Schedule, SectionStatus, User
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_regimes, get_permitted_sections
from core.session import get_session, update_session


# ── Regime slug map (regime_id → URL-friendly slug) ──────────────────────────

_REGIME_URL_NAMES = {
    'DEMO_SIMPLE':    'dept_demo:regime_demo_simple',
    'DEMO_SECTIONS':  'dept_demo:regime_demo_sections',
    'DEMO_SCHEDULES': 'dept_demo:regime_demo_schedules',
}


# ─────────────────────────────────────────────────────────────────────────────
# CHOOSE USER — self-filing only for now
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def choose_user(request):
    """
    For dept_demo, self-filing only for now.
    Sets user_id = actor_id = logged-in user and skips straight to
    select_regime.  Full intermediary UI is deferred to a later iteration.
    """
    update_session(request, {
        'user_id':  request.user.pk,
        'actor_id': request.user.pk,
    })
    return redirect('dept_demo:select_regime')


# ─────────────────────────────────────────────────────────────────────────────
# SELECT REGIME
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_regime(request):
    """
    Show available regimes and redirect to the appropriate regime home page.
    Auto-skips when only one regime is available.
    """
    pss   = get_session(request)
    actor = request.user
    user  = _resolve_user(pss, actor)

    if not pss.get('user_id'):
        update_session(request, {'user_id': user.pk, 'actor_id': actor.pk})

    regimes = get_permitted_regimes(actor, user)

    if not regimes.exists():
        return render(request, 'dept_demo/nav/select_regime.html', {
            'regimes': [],
            'no_access': True,
        })

    if regimes.count() == 1:
        return redirect(
            reverse('dept_demo:regime_home',
                    kwargs={'regime_id': regimes.first().regime_id})
        )

    if request.method == 'POST':
        regime_id = request.POST.get('regime_id', '')
        permitted_ids = list(regimes.values_list('regime_id', flat=True))
        if regime_id in permitted_ids:
            return redirect(
                reverse('dept_demo:regime_home', kwargs={'regime_id': regime_id})
            )

    return render(request, 'dept_demo/nav/select_regime.html', {'regimes': regimes})


# ─────────────────────────────────────────────────────────────────────────────
# REGIME HOME ROUTER
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def regime_home(request, regime_id):
    """
    Router: sends the citizen to the correct regime-specific home page based
    on regime_id.  Unknown regime_ids fall back to the department home.
    """
    url_name = _REGIME_URL_NAMES.get(regime_id)
    if url_name:
        return redirect(reverse(url_name))
    return redirect(reverse('dept_demo:home'))


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
                'dept_demo:select_section_in_schedule',
                kwargs={'regime_id': regime_id,
                        'schedule_id': sched.schedule_id},
            ),
        })

    return render(request, 'dept_demo/nav/select_schedule.html', {
        'regime':    regime,
        'schedules': schedule_data,
        'back_url':  '/demo/',
    })


# ─────────────────────────────────────────────────────────────────────────────
# SELECT SECTION — Pattern B task list; Pattern C second level
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_section(request, regime_id, schedule_id=None):
    """
    Task-list view: all permitted sections for this regime (filtered by
    schedule_id when coming from the schedule menu).

    Also sets return_url and schedule_id in the session so section_done
    knows where to redirect after a section is completed.
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

        if status == 'complete':
            action_url = f'/section/{section.section_id}/review/'
        elif section.section_type in (1, 2):
            action_url = f'/section/{section.section_id}/table/'
        else:
            action_url = f'/section/{section.section_id}/start/'

        section_data.append({
            'section':        section,
            'status':         status,
            'status_display': _status_label.get(status, 'Not started'),
            'action_url':     action_url,
        })

    # Set return_url so section_done redirects back to the right level
    if schedule_id:
        back_url   = reverse('dept_demo:select_schedule',
                             kwargs={'regime_id': regime_id})
        return_url = reverse('dept_demo:select_section_in_schedule',
                             kwargs={'regime_id': regime_id,
                                     'schedule_id': schedule_id})
    else:
        back_url   = '/demo/'
        return_url = reverse('dept_demo:select_section',
                             kwargs={'regime_id': regime_id})

    update_session(request, {
        'return_url':  return_url,
        'schedule_id': schedule_id,
    })

    return render(request, 'dept_demo/nav/select_section.html', {
        'regime':   regime,
        'schedule': schedule,
        'sections': section_data,
        'back_url': back_url,
    })
