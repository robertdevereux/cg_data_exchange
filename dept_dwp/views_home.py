"""
dept_dwp/views_home.py — DWP department home (flat regime card list).
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from core.models import Regime
from core.nav_reference import resolve_user
from core.session import get_acting_for_name, get_session, update_session


def _build_regime_item(regime):
    return {
        'regime': regime,
        'url':    reverse('dept_dwp:regime_home',
                          kwargs={'regime_id': regime.regime_id}),
    }


@login_required
def dept_home(request):
    """
    Flat regime card list for DWP. Shows all DWP regimes — permission
    enforcement happens at the section level, not here.
    """
    request.session['active_dept'] = 'DWP'
    actor = request.user
    pss   = get_session(request)
    update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
    pss = get_session(request)
    user     = resolve_user(pss, actor)
    is_agent = (actor.pk != user.pk)

    all_regimes = Regime.objects.filter(dept_id='DWP').order_by('display_order', 'regime_id')
    regime_data = [_build_regime_item(r) for r in all_regimes]

    return render(request, 'dept_dwp/home.html', {
        'regime_data':  regime_data,
        'is_agent':     is_agent,
        'subject':      user,
        'acting_for':   get_acting_for_name(pss),
        'breadcrumbs': [
            {'label': 'DWP',        'url': '/dwp/'},
            {'label': 'DWP Account', 'url': None},
        ],
    })
