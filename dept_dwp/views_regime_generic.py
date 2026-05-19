"""
dept_dwp/views_regime_generic.py — Generic home page for any DWP regime.

Handles all DWP regime IDs. Uses call_regime() to set session and resolve
the entry URL, remaps /regime/... to /dwp/regime/..., then renders the
generic template.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from core.interfaces import call_regime
from core.models import Regime, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session


@login_required
def regime_generic_home(request, regime_id):
    """
    Generic regime home page for any DWP regime.
    Calls call_regime() which sets all session keys and returns the entry URL.
    """
    request.session['active_dept'] = 'DWP'
    regime = get_object_or_404(
        Regime.objects.exclude(dept_id='PLATFORM'),
        regime_id=regime_id,
    )
    actor = request.user
    pss   = get_session(request)
    user  = _resolve_user(pss, actor)

    entry_url = call_regime(request, regime, actor, user)

    # Remap Pattern B section-list URLs to /dwp/ prefix.
    # Pattern C schedule-list URLs (/regime/.../schedules/) are served by core
    # at the root path and must NOT be remapped.
    if entry_url.startswith('/regime/') and entry_url.endswith('/sections/'):
        entry_url = '/dwp' + entry_url

    # Set breadcrumbs and regime_home_url in session for core Pattern C views.
    # call_regime() does not set these, so we add them here.
    regime_home_url = request.path
    update_session(request, {
        'regime_home_url': regime_home_url,
        'breadcrumbs': [
            {'label': 'DWP',              'url': '/dwp/'},
            {'label': 'DWP Account',      'url': '/dwp/regimes/'},
            {'label': regime.regime_name, 'url': regime_home_url},
        ],
    })

    # Count completion for button label and status paragraph
    permitted = get_permitted_sections(actor, user).filter(
        Q(regime=regime) | Q(schedule__regime=regime)
    )
    statuses = SectionStatus.objects.filter(
        user=user, regime=regime, section__in=permitted,
    )
    total        = statuses.count()
    complete     = statuses.filter(status='complete').count()
    all_complete = total > 0 and complete == total

    # Re-read session after call_regime has written to it
    pss = get_session(request)

    templates = [
        f'dept_dwp/{regime_id}_home.html',
        'dept_dwp/regimes/generic_home.html',
    ]
    return render(request, templates, {
        'regime':       regime,
        'total':        total,
        'complete':     complete,
        'all_complete': all_complete,
        'entry_url':    entry_url,
        'acting_for':   get_acting_for_name(pss),
        'breadcrumbs': [
            {'label': 'DWP',              'url': '/dwp/'},
            {'label': 'DWP Account',      'url': '/dwp/regimes/'},
            {'label': regime.regime_name, 'url': None},
        ],
    })
