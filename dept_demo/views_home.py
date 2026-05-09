"""
dept_demo/views_home.py — Department landing page (regime card list).

Shown when the actor/user pair has multiple regimes available.
Reached via select_regime → redirect when count > 1.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse

from core.models import SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_regimes, get_permitted_sections
from core.session import get_session


@login_required
def dept_home(request):
    """
    Regime card list for the actor/user pair established by choose_user.
    Reads the session user so intermediaries see the subject's regimes.
    """
    actor = request.user
    user  = _resolve_user(get_session(request), actor)

    permitted_regimes = get_permitted_regimes(actor, user)

    if not permitted_regimes.exists():
        return render(request, 'dept_demo/home.html', {
            'regime_data': [],
            'no_access':   True,
        })

    regime_data = []
    for regime in permitted_regimes:
        permitted = get_permitted_sections(actor, user).filter(
            Q(regime_id=regime.regime_id) | Q(schedule__regime_id=regime.regime_id)
        )
        total    = permitted.count()
        complete = SectionStatus.objects.filter(
            user=user, regime=regime, section__in=permitted, status='complete',
        ).count()

        if total == 0 or complete == 0:
            status_text = 'Not started'
        elif complete == total:
            status_text = 'Complete'
        else:
            status_text = f'In progress ({complete} of {total} complete)'

        regime_data.append({
            'regime':      regime,
            'status_text': status_text,
            'url': reverse('dept_demo:regime_home',
                           kwargs={'regime_id': regime.regime_id}),
        })

    return render(request, 'dept_demo/home.html', {'regime_data': regime_data})
