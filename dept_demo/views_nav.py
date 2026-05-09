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

from core.models import Permission, Regime, Schedule, SectionStatus, User
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_regimes, get_permitted_sections
from core.session import get_session, update_session


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
    Unknown regime_ids fall back to choose_user (dept_demo:home).
    """
    url_name = _REGIME_URL_NAMES.get(regime_id)
    if url_name:
        return redirect(reverse(url_name))
    return redirect(reverse('dept_demo:home'))


# ─────────────────────────────────────────────────────────────────────────────
# SELECT SCHEDULE — Pattern C first level
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_schedule(request, regime_id):
    """Show schedules containing at least one permitted section."""
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    permitted = get_permitted_sections(actor, user).filter(
        schedule__regime_id=regime_id
    ).select_related('schedule')

    schedule_ids = list(permitted.values_list('schedule_id', flat=True).distinct())
    schedules = (
        Schedule.objects
        .filter(schedule_id__in=schedule_ids)
        .order_by('display_order')
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

    schedule_data = []
    for sched in schedules:
        sched_sections = permitted.filter(schedule=sched)
        statuses = [
            section_statuses.get(s.section_id, 'not_started')
            for s in sched_sections
        ]
        if all(s == 'complete' for s in statuses):
            sched_status = 'complete'
        elif any(s in ('in_progress', 'complete') for s in statuses):
            sched_status = 'in_progress'
        else:
            sched_status = 'not_started'

        schedule_data.append({
            'schedule':       sched,
            'section_count':  sched_sections.count(),
            'status':         sched_status,
            'status_display': _status_label[sched_status],
            'url': reverse(
                'dept_demo:select_section_in_schedule',
                kwargs={'regime_id': regime_id, 'schedule_id': sched.schedule_id},
            ),
        })

    regime_home_url = reverse('dept_demo:regime_home', kwargs={'regime_id': regime_id})
    base_crumbs = pss.get('breadcrumbs', [])
    return render(request, 'dept_demo/nav/select_schedule.html', {
        'regime':      regime,
        'schedules':   schedule_data,
        'back_url':    reverse('dept_demo:dept_home'),
        'breadcrumbs': base_crumbs + [
            {'label': regime.regime_name, 'url': regime_home_url},
        ],
    })


# ─────────────────────────────────────────────────────────────────────────────
# SELECT SECTION — Pattern B task list; Pattern C second level
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_section(request, regime_id, schedule_id=None):
    """
    Task-list view for all permitted sections in this regime (filtered by
    schedule_id when coming from the schedule menu).

    Sets return_url in the session so section_done redirects back here.
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    permitted = get_permitted_sections(actor, user).filter(
        Q(regime_id=regime_id) | Q(schedule__regime_id=regime_id)
    )

    if schedule_id:
        schedule = get_object_or_404(Schedule, schedule_id=schedule_id)
        permitted = permitted.filter(schedule_id=schedule_id)
    else:
        schedule = None

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

    # Set return_url so section_done redirects back to the right level
    if schedule_id:
        back_url   = reverse('dept_demo:select_schedule',
                             kwargs={'regime_id': regime_id})
        return_url = reverse('dept_demo:select_section_in_schedule',
                             kwargs={'regime_id': regime_id,
                                     'schedule_id': schedule_id})
    else:
        back_url   = reverse('dept_demo:dept_home')
        return_url = reverse('dept_demo:select_section',
                             kwargs={'regime_id': regime_id})

    update_session(request, {
        'return_url':  return_url,
        'schedule_id': schedule_id,
    })

    regime_home_url = reverse('dept_demo:regime_home', kwargs={'regime_id': regime_id})
    base_crumbs = pss.get('breadcrumbs', [])
    crumbs = base_crumbs + [{'label': regime.regime_name, 'url': regime_home_url}]
    if schedule:
        crumbs.append({'label': schedule.schedule_name, 'url': None})

    return render(request, 'dept_demo/nav/select_section.html', {
        'regime':      regime,
        'schedule':    schedule,
        'sections':    section_data,
        'back_url':    back_url,
        'breadcrumbs': crumbs,
    })
