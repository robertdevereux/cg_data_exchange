"""
dept_hmrc/views/hmrc_home.py — HMRC department and regime dispatch views.
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from core.interfaces import call_regime
from core.models import Regime, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session


@login_required
def dept_home(request):
    """HMRC department landing page — lists all HMRC regimes."""
    request.session['active_dept'] = 'HMRC'
    actor = request.user
    pss   = get_session(request)
    update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
    pss  = get_session(request)
    user = _resolve_user(pss, actor)

    regimes = Regime.objects.filter(dept_id='HMRC').order_by(
        'display_order', 'regime_name')

    return render(request, 'dept_hmrc/dept_home.html', {
        'regimes':     regimes,
        'acting_for':  get_acting_for_name(pss),
        'breadcrumbs': [{'label': 'HMRC', 'url': None}],
    })


@login_required
def regime_list(request):
    """Redirect to dept_home."""
    return redirect('dept_hmrc:dept_home')


@login_required
def regime_home(request, regime_id):
    """
    HMRC regime dispatcher. Routes to the correct regime orchestrator.
    Add new regimes here as they are built.
    """
    if regime_id == 'HMRC_IHT':
        from dept_hmrc.views.iht.orchestrate import iht_orchestrate
        return iht_orchestrate(request)

    # Generic fallback for unconfigured regimes
    regime = get_object_or_404(
        Regime.objects.filter(dept_id='HMRC'), regime_id=regime_id)
    actor = request.user
    pss   = get_session(request)
    user  = _resolve_user(pss, actor)

    entry_url = call_regime(request, regime, actor, user, url_prefix='hmrc')
    permitted = get_permitted_sections(actor, user).filter(
        Q(regime=regime) | Q(schedule__regime=regime))
    statuses     = SectionStatus.objects.filter(
        user=user, regime=regime, section__in=permitted)
    total        = statuses.count()
    complete     = statuses.filter(status='complete').count()
    all_complete = total > 0 and complete == total

    crumbs = [
        {'label': 'HMRC',             'url': '/hmrc/'},
        {'label': regime.regime_name, 'url': None},
    ]
    update_session(request, {
        'breadcrumbs':     crumbs,
        'regime_home_url': request.path,
        'active_dept':     'HMRC',
        'regime_id':       regime.regime_id,
    })
    pss = get_session(request)

    return render(request, 'dept_hmrc/regime_home.html', {
        'regime':        regime,
        'total':         total,
        'complete':      complete,
        'all_complete':  all_complete,
        'entry_url':     entry_url,
        'acting_for':    get_acting_for_name(pss),
        'breadcrumbs':   crumbs,
    })
