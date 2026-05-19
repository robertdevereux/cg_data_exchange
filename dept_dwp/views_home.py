"""
dept_dwp/views_home.py — DWP department home (flat regime card list).
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from core.nav_reference import _resolve_user
from core.permissions import get_permitted_regimes
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
    Flat regime card list for DWP. Unlike dept_demo, no current/other split —
    all permitted regimes are shown in a single list ordered by display_order.
    """
    request.session['active_dept'] = 'DWP'
    actor = request.user
    pss   = get_session(request)
    if not pss.get('user_id'):
        update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
        pss = get_session(request)
    user     = _resolve_user(pss, actor)
    is_agent = (actor.pk != user.pk)

    permitted_regimes = get_permitted_regimes(actor, user, dept_id='DWP')
    acting_for        = get_acting_for_name(pss)

    if not permitted_regimes.exists():
        return render(request, 'dept_dwp/home.html', {
            'regime_data':  [],
            'no_access':    True,
            'is_agent':     is_agent,
            'subject':      user,
            'acting_for':   acting_for,
            'breadcrumbs': [
                {'label': 'DWP',        'url': '/dwp/'},
                {'label': 'DWP Account', 'url': None},
            ],
        })

    regime_data = [
        _build_regime_item(r)
        for r in permitted_regimes.order_by('display_order')
    ]

    return render(request, 'dept_dwp/home.html', {
        'regime_data':  regime_data,
        'is_agent':     is_agent,
        'subject':      user,
        'acting_for':   acting_for,
        'breadcrumbs': [
            {'label': 'DWP',        'url': '/dwp/'},
            {'label': 'DWP Account', 'url': None},
        ],
    })
