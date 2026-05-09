"""
dept_demo/views_home.py — Department landing page (regime card list).

Shown when the actor/user pair has multiple regimes available.
Reached via select_regime → redirect when count > 1.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from core.nav_reference import _resolve_user
from core.permissions import get_permitted_regimes
from core.session import get_acting_for_name, get_session

# Regime classification — determines which section of the home page each appears in
_CURRENT_REGIME_IDS = ['DEMO_SIMPLE', 'DEMO_SECTIONS']
_OTHER_REGIME_IDS   = ['DEMO_SCHEDULES']


def _build_regime_item(regime):
    return {
        'regime': regime,
        'url':    reverse('dept_demo:regime_home',
                          kwargs={'regime_id': regime.regime_id}),
    }


@login_required
def dept_home(request):
    """
    Regime card list for the actor/user pair established by choose_user.
    Reads the session user so intermediaries see the subject's regimes.
    Regimes are split into 'current' and 'other' groups for the HMRC-style layout.
    """
    actor    = request.user
    pss      = get_session(request)
    user     = _resolve_user(pss, actor)
    is_agent = (actor.pk != user.pk)

    permitted_regimes = get_permitted_regimes(actor, user)

    acting_for = get_acting_for_name(pss)

    if not permitted_regimes.exists():
        return render(request, 'dept_demo/home.html', {
            'current_regime_data': [],
            'other_regime_data':   [],
            'no_access':           True,
            'is_agent':            is_agent,
            'subject':             user,
            'acting_for':          acting_for,
            'breadcrumbs': [
                {'label': 'HMRC',                 'url': '/demo/'},
                {'label': 'Personal Tax Account', 'url': None},
            ],
        })

    current_regime_data = [
        _build_regime_item(r)
        for r in permitted_regimes.filter(regime_id__in=_CURRENT_REGIME_IDS)
        .order_by('display_order')
    ]
    other_regime_data = [
        _build_regime_item(r)
        for r in permitted_regimes.filter(regime_id__in=_OTHER_REGIME_IDS)
        .order_by('display_order')
    ]

    return render(request, 'dept_demo/home.html', {
        'current_regime_data': current_regime_data,
        'other_regime_data':   other_regime_data,
        'is_agent':            is_agent,
        'subject':             user,
        'acting_for':          acting_for,
        'breadcrumbs': [
            {'label': 'HMRC',                 'url': '/demo/'},
            {'label': 'Personal Tax Account', 'url': None},
        ],
    })
