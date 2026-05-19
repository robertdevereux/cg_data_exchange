"""
dept_defra/views.py — DEFRA department views.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.interfaces import call_regime
from core.views_layer1 import regime_schedule_sections, regime_schedules  # noqa: F401 — re-exported for urls.py
from core.models import Regime, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session


@login_required
def dept_home(request):
    """DEFRA department landing page — lists all DEFRA regimes.
    Permission enforcement happens at the section level, not here.
    """
    request.session['active_dept'] = 'DEFRA'
    actor = request.user
    pss   = get_session(request)
    if not pss.get('user_id'):
        update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
        pss = get_session(request)
    user  = _resolve_user(pss, actor)

    regimes = Regime.objects.filter(dept_id='DEFRA').order_by('display_order', 'regime_name')

    return render(request, 'dept_defra/dept_home.html', {
        'regimes':     regimes,
        'acting_for':  get_acting_for_name(pss),
        'breadcrumbs': [
            {'label': 'DEFRA', 'url': None},
        ],
    })


@login_required
def regime_list(request):
    """Redirect to dept_home — the landing page is the regime list for DEFRA."""
    return redirect('dept_defra:dept_home')


@login_required
def regime_home(request, regime_id):
    """DEFRA regime landing page — start/continue button and completion status."""
    request.session['active_dept'] = 'DEFRA'
    regime = get_object_or_404(
        Regime.objects.filter(dept_id='DEFRA'),
        regime_id=regime_id,
    )
    actor = request.user
    pss   = get_session(request)
    user  = _resolve_user(pss, actor)

    entry_url = call_regime(request, regime, actor, user)

    # Map core /regime/... entry URLs to DEFRA-namespaced equivalents.
    # Pattern C (schedules): /regime/<id>/schedules/ → dept_defra:regime_schedules
    # Pattern B (sections):  /regime/<id>/sections/ → dept_defra:select_section
    if entry_url.startswith('/regime/') and entry_url.endswith('/schedules/'):
        entry_url = reverse(
            'dept_defra:regime_schedules',
            kwargs={'regime_id': regime.regime_id},
        )
    elif entry_url.startswith('/regime/') and entry_url.endswith('/sections/'):
        entry_url = reverse(
            'dept_defra:select_section',
            kwargs={'regime_id': regime.regime_id},
        )

    # Completion status
    permitted = get_permitted_sections(actor, user).filter(
        Q(regime=regime) | Q(schedule__regime=regime)
    )
    statuses = SectionStatus.objects.filter(
        user=user, regime=regime, section__in=permitted,
    )
    total        = statuses.count()
    complete     = statuses.filter(status='complete').count()
    all_complete = total > 0 and complete == total

    # Re-read session after call_regime has written to it, then write fresh
    # breadcrumbs so downstream views (schedule list, section list) inherit them.
    pss = get_session(request)
    crumbs = [
        {'label': 'DEFRA',            'url': '/defra/'},
        {'label': regime.regime_name, 'url': request.path},
    ]
    update_session(request, {
        'breadcrumbs':     crumbs,
        'regime_home_url': request.path,
        'active_dept':     'DEFRA',
        'regime_id':       regime.regime_id,
    })

    templates = [
        f'dept_defra/{regime_id}_home.html',
        'dept_defra/regime_home.html',
    ]
    return render(request, templates, {
        'regime':       regime,
        'total':        total,
        'complete':     complete,
        'all_complete': all_complete,
        'entry_url':    entry_url,
        'acting_for':   get_acting_for_name(pss),
        'breadcrumbs': [
            {'label': 'DEFRA',            'url': '/defra/'},
            {'label': regime.regime_name, 'url': None},
        ],
    })


@login_required
def select_section(request, regime_id):
    """
    Pattern B task-list: all permitted sections in this DEFRA regime (no schedule).
    Sets return_url so section_done redirects back here.
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime.objects.filter(dept_id='DEFRA'), regime_id=regime_id)

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
        reverse('dept_defra:regime_home', kwargs={'regime_id': regime_id}),
    )
    back_url   = reverse('dept_defra:dept_home')
    return_url = reverse('dept_defra:select_section', kwargs={'regime_id': regime_id})
    crumbs = pss.get('breadcrumbs') or [
        {'label': 'DEFRA',            'url': '/defra/'},
        {'label': regime.regime_name, 'url': regime_home_url},
    ]

    update_session(request, {
        'return_url':        return_url,
        'schedule_id':       None,
        'breadcrumbs':       crumbs,
        'regime_home_url':   regime_home_url,
        'schedule_list_url': None,
    })

    return render(request, 'core/select_section.html', {
        'regime':      regime,
        'schedule':    None,
        'sections':    section_data,
        'back_url':    back_url,
        'breadcrumbs': crumbs,
        'acting_for':  get_acting_for_name(pss),
    })
