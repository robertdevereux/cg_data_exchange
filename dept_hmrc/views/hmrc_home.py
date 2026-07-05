"""
dept_hmrc/views/hmrc_home.py — HMRC department and regime dispatch views.
"""
from urllib.parse import urlencode as _urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.interfaces import call_regime
from core.models import Regime, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session


def _hmrc_gate(request):
    """
    Return a redirect to the IHT regime choose_identity page if user_id/actor_id
    are not yet established this session.  Returns None when the session is ready.
    """
    pss = get_session(request)
    if not pss.get('user_id'):
        return redirect(reverse('dept_hmrc:regime_choose_identity',
                                kwargs={'regime_id': 'HMRC_IHT'}))
    return None


@login_required
def dept_home(request):
    """HMRC department landing page — lists all HMRC regimes."""
    request.session['active_dept'] = 'HMRC'
    actor = request.user
    pss   = get_session(request)
    user  = _resolve_user(pss, actor)

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
    gate = _hmrc_gate(request)
    if gate:
        return gate

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


@login_required
def regime_choose_identity(request, regime_id):
    """
    Per-regime identity picker for HMRC.
    For IHT: leading option is 'Begin a new estate' (chains through select_self
    to iht_start_new_estate). Other candidates are promoted estates (Permission
    rows with case_id set, created by _promote_case_to_verified).
    """
    from core.models import Regime as _Regime
    from core.views_gate import choose_user_for_regime

    regime   = get_object_or_404(_Regime.objects.filter(dept_id='HMRC'), regime_id=regime_id)
    next_url = reverse('dept_hmrc:regime_home', kwargs={'regime_id': regime_id})

    if regime_id == 'HMRC_IHT':
        # "Begin a new estate" → select_self → iht_start_new_estate
        new_url  = reverse('dept_hmrc:iht_start_new_estate')
        self_url = reverse('core:select_self') + '?' + _urlencode({'next': new_url})
        leading_option = {'label': 'Begin a new estate', 'action_url': self_url}
    else:
        self_url = reverse('core:select_self') + '?' + _urlencode({'next': next_url})
        leading_option = {'label': 'Myself', 'action_url': self_url}

    return choose_user_for_regime(request, regime, leading_option, next_url)
