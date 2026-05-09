"""
dept_demo/views_regime_schedules.py — Home page for DEMO_SCHEDULES regime.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from core.interfaces import bootstrap_section_statuses, get_or_create_case
from core.models import Regime, SectionStatus
from core.nav_reference import _resolve_user, resolve_layer1_entry_url
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session

_REGIME_ID = 'DEMO_SCHEDULES'
_TEMPLATE  = 'dept_demo/regimes/schedules_home.html'


@login_required
def regime_schedules_home(request):
    """
    Home page for DEMO_SCHEDULES (schedule-based, Pattern C).
    Bootstraps Case and SectionStatus, then shows the start/continue button.
    """
    regime = Regime.objects.get(regime_id=_REGIME_ID)
    actor  = request.user
    user   = _resolve_user(get_session(request), actor)

    permitted = get_permitted_sections(actor, user).filter(
        Q(regime_id=_REGIME_ID) | Q(schedule__regime_id=_REGIME_ID)
    )

    case = get_or_create_case(user, regime)
    bootstrap_section_statuses(user, regime, permitted)

    statuses = SectionStatus.objects.filter(
        user=user, regime=regime, section__in=permitted,
    )
    total    = statuses.count()
    complete = statuses.filter(status='complete').count()
    all_complete = total > 0 and complete == total

    # Set the four SESSION_KEYS + return_url
    update_session(request, {
        'user_id':    user.pk,
        'actor_id':   actor.pk,
        'regime_id':  regime.regime_id,
        'case_id':    case.case_id,
        'return_url': request.path,
        'breadcrumbs': [
            {'label': 'HMRC',                 'url': '/demo/'},
            {'label': 'Personal Tax Account', 'url': '/demo/regimes/'},
        ],
    })

    # Resolve entry URL; remap any /regime/... path to /demo/regime/...
    entry_url = resolve_layer1_entry_url(permitted, _REGIME_ID, all_complete)
    if entry_url.startswith('/regime/'):
        entry_url = '/demo' + entry_url

    pss = get_session(request)
    return render(request, _TEMPLATE, {
        'regime':       regime,
        'total':        total,
        'complete':     complete,
        'all_complete': all_complete,
        'entry_url':    entry_url,
        'acting_for':   get_acting_for_name(pss),
        'breadcrumbs': [
            {'label': 'HMRC',                 'url': '/demo/'},
            {'label': 'Personal Tax Account', 'url': '/demo/regimes/'},
            {'label': regime.regime_name,     'url': None},
        ],
    })
