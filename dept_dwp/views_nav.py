"""
dept_dwp/views_nav.py — Layer 1 navigation views for dept_dwp.

All DWP regimes use the generic regime home view — there is no slug map.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import Regime, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_regimes, get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session
from core.views_layer1 import regime_schedule_sections, regime_schedules  # noqa: F401 — re-exported for urls.py


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
# SELECT SECTION — Pattern B task list
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_section(request, regime_id):
    """
    Pattern B task-list: all permitted sections in this regime (no schedule).
    Sets return_url so section_done redirects back here.
    Pattern C (schedule-based) section lists are served by core.views_layer1.
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    permitted = get_permitted_sections(actor, user).filter(
        Q(regime_id=regime_id) | Q(schedule__regime_id=regime_id)
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

    regime_home_url = pss.get(
        'regime_home_url',
        reverse('dept_dwp:regime_home', kwargs={'regime_id': regime_id}),
    )
    back_url   = reverse('dept_dwp:dept_home')
    return_url = reverse('dept_dwp:select_section', kwargs={'regime_id': regime_id})
    crumbs = pss.get('breadcrumbs') or [
        {'label': 'DWP',              'url': '/dwp/'},
        {'label': 'DWP Account',      'url': '/dwp/regimes/'},
        {'label': regime.regime_name, 'url': regime_home_url},
    ]

    update_session(request, {
        'return_url':        return_url,
        'schedule_id':       None,
        'breadcrumbs':       crumbs,
        'regime_home_url':   regime_home_url,
        'schedule_list_url': None,
    })

    return render(request, 'dept_dwp/nav/select_section.html', {
        'regime':      regime,
        'schedule':    None,
        'sections':    section_data,
        'back_url':    back_url,
        'breadcrumbs': crumbs,
        'acting_for':  get_acting_for_name(pss),
    })
