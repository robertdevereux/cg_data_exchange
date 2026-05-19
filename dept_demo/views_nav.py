"""
dept_demo/views_nav.py — Layer 1 navigation views for dept_demo.

Implements all three navigation patterns using the platform interfaces and
reference implementations from core.nav_reference, adapted for dept_demo's
URL structure (/demo/ prefix) and templates.

Flow:
  /demo/ → choose_user → select_regime → regime_home router
         → specific regime home → (Layer 2 section journey)
         → section_done → return_url (set by this layer)
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import Permission, Regime, SectionStatus, User
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_regimes, get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session


# ── Regime slug map (regime_id → named URL) ───────────────────────────────────

_REGIME_URL_NAMES = {
    'DEMO_SIMPLE':    'dept_demo:regime_demo_simple',
    'DEMO_SECTIONS':  'dept_demo:regime_demo_sections',
    'DEMO_SCHEDULES': 'dept_demo:regime_demo_schedules',
}


# ─────────────────────────────────────────────────────────────────────────────
# CHOOSE USER — who is the actor filing for?
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def choose_user(request):
    """
    Present a choice of users the actor can act for.
    Auto-skips to select_regime when there is only one candidate (including
    the common case where a citizen is only filing for themselves).
    """
    actor = request.user

    # Find users this actor can act for (other than themselves)
    other_user_ids = (
        Permission.objects
        .filter(actor=actor)
        .exclude(user=actor)
        .values_list('user_id', flat=True)
        .distinct()
    )

    self_has_perms = Permission.objects.filter(
        actor=actor, user=actor
    ).exists()

    candidate_users = []
    if self_has_perms:
        candidate_users.append({
            'user':  actor,
            'label': 'Myself',
            'value': actor.pk,
        })
    for u in User.objects.filter(pk__in=other_user_ids).order_by('first_name', 'last_name'):
        candidate_users.append({
            'user':  u,
            'label': u.get_full_name() or u.username,
            'value': u.pk,
        })

    # No permissions at all
    if not candidate_users:
        return render(request, 'dept_demo/nav/no_permissions.html')

    # Only one candidate — skip the screen
    if len(candidate_users) == 1:
        selected = candidate_users[0]['user']
        update_session(request, {
            'user_id':  selected.pk,
            'actor_id': actor.pk,
        })
        return redirect('dept_demo:select_regime')

    # POST: process selection
    if request.method == 'POST':
        selected_pk = request.POST.get('user_id', '')
        valid_pks   = [str(c['value']) for c in candidate_users]
        if selected_pk not in valid_pks:
            return render(request, 'dept_demo/nav/choose_user.html', {
                'candidates': candidate_users,
                'error':      'Please select an option.',
            })
        selected = User.objects.get(pk=int(selected_pk))
        update_session(request, {
            'user_id':  selected.pk,
            'actor_id': actor.pk,
        })
        return redirect('dept_demo:select_regime')

    # GET: show choice
    return render(request, 'dept_demo/nav/choose_user.html', {
        'candidates': candidate_users,
    })


# ─────────────────────────────────────────────────────────────────────────────
# SELECT REGIME
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_regime(request):
    """
    Show available regimes for the actor/user pair established by choose_user.
    Auto-skips when only one regime is available.
    Multiple regimes: redirect to the dept home (regime card list).
    """
    if request.user.is_staff:
        return redirect('/tools/')

    pss   = get_session(request)
    actor = request.user
    user  = _resolve_user(pss, actor)

    if not pss.get('user_id'):
        update_session(request, {'user_id': user.pk, 'actor_id': actor.pk})

    regimes = get_permitted_regimes(actor, user)

    if not regimes.exists():
        return render(request, 'dept_demo/nav/select_regime.html', {
            'regimes':   [],
            'no_access': True,
        })

    # Auto-skip when exactly one regime
    if regimes.count() == 1:
        return redirect(
            reverse('dept_demo:regime_home',
                    kwargs={'regime_id': regimes.first().regime_id})
        )

    # Multiple regimes — send to the regime card list
    return redirect(reverse('dept_demo:dept_home'))


# ─────────────────────────────────────────────────────────────────────────────
# REGIME HOME ROUTER
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def regime_home(request, regime_id):
    """
    Router: sends the citizen to the correct regime-specific home page.
    Unknown regime_ids fall back to choose_user (dept_demo:choose_user).
    """
    request.session['active_dept'] = 'DEMO'
    url_name = _REGIME_URL_NAMES.get(regime_id)
    if url_name:
        return redirect(reverse(url_name))
    return redirect(reverse('dept_demo:choose_user'))


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

    # Pattern B: breadcrumbs read from session (set by regime home) or built from defaults
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
