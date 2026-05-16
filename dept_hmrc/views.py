"""
dept_hmrc/views.py — HMRC department views.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from core.interfaces import call_regime
from core.models import Regime, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_regimes, get_permitted_sections
from core.session import get_acting_for_name, get_session


@login_required
def dept_home(request):
    """HMRC department landing page — lists permitted HMRC regimes."""
    actor = request.user
    pss   = get_session(request)
    user  = _resolve_user(pss, actor)

    regimes = (
        get_permitted_regimes(actor, user)
        .filter(dept_id='HMRC')
        .order_by('display_order', 'regime_name')
    )

    return render(request, 'dept_hmrc/dept_home.html', {
        'regimes':     regimes,
        'acting_for':  get_acting_for_name(pss),
        'breadcrumbs': [
            {'label': 'HMRC', 'url': None},
        ],
    })


@login_required
def regime_list(request):
    """Redirect to dept_home — the landing page is the regime list for HMRC."""
    return redirect('dept_hmrc:dept_home')


@login_required
def regime_home(request, regime_id):
    """HMRC regime landing page — start/continue button and completion status."""
    regime = get_object_or_404(
        Regime.objects.filter(dept_id='HMRC'),
        regime_id=regime_id,
    )
    actor = request.user
    pss   = get_session(request)
    user  = _resolve_user(pss, actor)

    entry_url = call_regime(request, regime, actor, user)

    # Remap /regime/... to /hmrc/regime/...
    if entry_url.startswith('/regime/'):
        entry_url = '/hmrc' + entry_url

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

    # Re-read session after call_regime has written to it
    pss = get_session(request)

    return render(request, 'dept_hmrc/regime_home.html', {
        'regime':      regime,
        'total':       total,
        'complete':    complete,
        'all_complete': all_complete,
        'entry_url':   entry_url,
        'acting_for':  get_acting_for_name(pss),
        'breadcrumbs': [
            {'label': 'HMRC',             'url': '/hmrc/'},
            {'label': regime.regime_name, 'url': None},
        ],
    })
