"""
dept_demo/views_nav.py — Layer 1 navigation views for dept_demo.

Flow (new):
  /demo/ → select_regime (unscoped) → choose_identity/<regime_id>/
         → regime_home router → specific regime home → (Layer 2 section journey)
         → section_done → return_url (set by this layer)
"""

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import Regime, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_actor_accessible_regimes, get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session
from core.views_gate import choose_user_for_regime


# ── Regime slug map (regime_id → named URL) ───────────────────────────────────

_REGIME_URL_NAMES = {
    'TEST_SIMPLE':    'dept_demo:regime_demo_simple',
    'TEST_SECTIONS':  'dept_demo:regime_demo_sections',
    'TEST_SCHEDULES': 'dept_demo:regime_demo_schedules',
}


# ─────────────────────────────────────────────────────────────────────────────
# SELECT REGIME — unscoped, runs before identity is chosen
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_regime(request):
    """
    Show available regimes for the actor — unscoped (no user/identity chosen yet).
    Uses get_actor_accessible_regimes so agents see regimes they can access for
    any client, not just themselves.
    Auto-skips to choose_identity when exactly one regime is accessible.
    Multiple regimes → redirect to the dept home (regime card list).
    """
    if request.user.is_staff:
        return redirect('/tools/')

    actor   = request.user
    regimes = get_actor_accessible_regimes(actor, dept_id='TEST')

    if not regimes.exists():
        return render(request, 'dept_demo/nav/select_regime.html', {
            'regimes':   [],
            'no_access': True,
        })

    if regimes.count() == 1:
        regime = regimes.first()
        return redirect(
            reverse('dept_demo:choose_identity',
                    kwargs={'regime_id': regime.regime_id})
        )

    return redirect(reverse('dept_demo:dept_home'))


# ─────────────────────────────────────────────────────────────────────────────
# CHOOSE IDENTITY — regime-scoped identity picker
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def choose_identity(request, regime_id):
    """
    Regime-scoped identity picker for dept_demo.
    Wraps core.views_gate.choose_user_for_regime with 'Myself' as the leading
    option.  Agents also see the clients they can file for in this regime.
    On selection, sets session (user_id/actor_id) via select_self or
    select_identity, then redirects to the regime home.
    """
    regime   = get_object_or_404(Regime, regime_id=regime_id)
    next_url = reverse('dept_demo:regime_home', kwargs={'regime_id': regime_id})

    # "Myself" — select_self sets user_id = actor.pk then goes to next_url
    self_url       = reverse('core:select_self') + '?' + urlencode({'next': next_url})
    leading_option = {'label': 'Myself', 'action_url': self_url}

    return choose_user_for_regime(request, regime, leading_option, next_url)


# ─────────────────────────────────────────────────────────────────────────────
# REGIME HOME ROUTER
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def regime_home(request, regime_id):
    """
    Router: sends the citizen to the correct regime-specific home page.
    Unknown regime_ids fall back to select_regime.
    """
    request.session['active_dept'] = 'TEST'
    url_name = _REGIME_URL_NAMES.get(regime_id)
    if url_name:
        return redirect(reverse(url_name))
    return redirect(reverse('dept_demo:select_regime'))


# ─────────────────────────────────────────────────────────────────────────────
# SELECT SECTION — Pattern B task list
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_section(request, regime_id):
    """
    Pattern B task-list: all permitted sections in this regime (no schedule).
    Sets return_url in the session so section_done redirects back here.
    Pattern C (schedule-based) section lists are served by core.views_layer1.
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

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

    back_url   = reverse('dept_demo:dept_home')
    return_url = reverse('dept_demo:select_section', kwargs={'regime_id': regime_id})

    regime_sections_url = reverse('dept_demo:regime_demo_sections')
    crumbs = pss.get('breadcrumbs') or [
        {'label': 'HMRC',                 'url': '/demo/'},
        {'label': 'Personal Tax Account', 'url': '/demo/regimes/'},
        {'label': regime.regime_name,     'url': regime_sections_url},
    ]
    regime_home_url = pss.get('regime_home_url', regime_sections_url)

    update_session(request, {
        'return_url':        return_url,
        'schedule_id':       None,
        'breadcrumbs':       crumbs,
        'regime_home_url':   regime_home_url,
        'schedule_list_url': None,
    })

    return render(request, 'dept_demo/nav/select_section.html', {
        'regime':      regime,
        'schedule':    None,
        'sections':    section_data,
        'back_url':    back_url,
        'breadcrumbs': crumbs,
        'acting_for':  get_acting_for_name(pss),
    })
