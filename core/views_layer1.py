"""
Layer 1: Orchestration — getting the citizen to the right Section.

Responsibility boundary
  Layer 1 owns everything from login through to Section selection:
  user resolution, regime navigation, schedule and section menus,
  permission filtering, and Case/SectionStatus bootstrapping.

  Layer 2 (views_layer2.py) takes over the moment a Section is selected.

Navigation patterns
  Pattern A — single permitted section:   go straight to it.
  Pattern B — multiple sections, no schedules: show section task list.
  Pattern C — sections under schedules:   show schedule list first.

Session keys written here and consumed by Layer 2:
  user_id, actor_id, regime_id, regime_name, case_id
"""

import uuid

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Case, Regime, Schedule, Section, SectionStatus, User
from .permissions import get_permitted_regimes, get_permitted_sections
from .session import get_session, update_session


# ── Shared helper: resolve user from session ──────────────────────────────────

def _resolve_user(pss, actor):
    """Return the User the actor is acting for, defaulting to actor themselves."""
    user_id = pss.get('user_id')
    if user_id:
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            pass
    return actor


# ─────────────────────────────────────────────────────────────────────────────
# 1.  HOME
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def home(request):
    """Router: skip user selection if session already has a user_id."""
    pss = get_session(request)
    if pss.get('user_id'):
        return redirect('core:select_regime')
    return redirect('core:choose_user')


# ─────────────────────────────────────────────────────────────────────────────
# 2.  CHOOSE USER
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def choose_user(request):
    """
    Build the list of users this actor can act for and let them choose.

    Auto-selects and skips the screen when the only option is the actor
    themselves (the common single-citizen case).
    """
    actable_users = (
        User.objects
        .filter(permissions_as_subject__actor=request.user)
        .distinct()
        .order_by('first_name', 'last_name', 'username')
    )

    if not actable_users.exists():
        return render(request, 'core/choose_user.html', {
            'users': [],
            'no_access': True,
        })

    # Skip the screen if the only actable user is the actor themselves
    if actable_users.count() == 1 and actable_users.first() == request.user:
        user = actable_users.first()
        update_session(request, {'user_id': user.pk, 'actor_id': request.user.pk})
        return redirect('core:select_regime')

    if request.method == 'POST':
        user_id_raw = request.POST.get('user_id', '')
        try:
            user = actable_users.get(pk=int(user_id_raw))
        except (ValueError, TypeError, User.DoesNotExist):
            return render(request, 'core/choose_user.html', {
                'users': actable_users,
                'error': 'Please select a valid user.',
            })
        update_session(request, {'user_id': user.pk, 'actor_id': request.user.pk})
        return redirect('core:select_regime')

    return render(request, 'core/choose_user.html', {'users': actable_users})


# ─────────────────────────────────────────────────────────────────────────────
# 3.  SELECT REGIME
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_regime(request):
    """
    Present the regime selection menu for this actor/user pair.

    Skips the menu and proceeds directly to regime_start when there is
    exactly one permitted regime.
    """
    pss   = get_session(request)
    actor = request.user
    user  = _resolve_user(pss, actor)

    # Ensure session user_id is set (may have been skipped from choose_user)
    if not pss.get('user_id'):
        update_session(request, {'user_id': user.pk, 'actor_id': actor.pk})

    permitted_regimes = get_permitted_regimes(actor, user)

    if not permitted_regimes.exists():
        return render(request, 'core/select_regime.html', {
            'regimes': [],
            'no_access': True,
        })

    # Auto-skip when there is only one regime
    if permitted_regimes.count() == 1:
        regime = permitted_regimes.first()
        update_session(request, {
            'regime_id':   regime.regime_id,
            'regime_name': regime.regime_name,
        })
        return redirect('core:regime_start', regime_id=regime.regime_id)

    if request.method == 'POST':
        regime_id = request.POST.get('regime_id', '')
        permitted_ids = list(permitted_regimes.values_list('regime_id', flat=True))
        if regime_id not in permitted_ids:
            return render(request, 'core/select_regime.html', {
                'regimes': permitted_regimes,
                'error': 'Please select a valid service.',
            })
        regime = permitted_regimes.get(regime_id=regime_id)
        update_session(request, {
            'regime_id':   regime.regime_id,
            'regime_name': regime.regime_name,
        })
        return redirect('core:regime_start', regime_id=regime_id)

    return render(request, 'core/select_regime.html', {'regimes': permitted_regimes})


# ─────────────────────────────────────────────────────────────────────────────
# 4.  REGIME HOME  (landing page + bootstrap; formerly regime_start)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def regime_start(request, regime_id):
    """
    Landing page for a regime.  Also bootstraps Case and SectionStatus records
    on first visit (idempotent — uses get_or_create).

    Shows:
      - Regime name + placeholder guidance
      - Action group 1: completion summary + Start/Continue/Review button
        whose target URL is determined by pattern A / B / C
      - Action group 2: Declare and submit (only when all sections complete)
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    # Permitted sections for this regime
    permitted = get_permitted_sections(actor, user).filter(
        Q(regime_id=regime_id) | Q(schedule__regime_id=regime_id)
    )
    section_count = permitted.count()

    # ── Bootstrap Case ────────────────────────────────────────────────────────
    case = (
        Case.objects
        .filter(user=user, regime=regime, status='draft')
        .order_by('-started_at')
        .first()
    )
    if not case:
        case = Case.objects.create(
            case_id=str(uuid.uuid4()),
            user=user,
            regime=regime,
            status='draft',
        )

    # Write the full Layer 2 session context
    update_session(request, {
        'user_id':     user.pk,
        'actor_id':    actor.pk,
        'regime_id':   regime_id,
        'regime_name': regime.regime_name,
        'case_id':     case.case_id,
    })

    # ── Bootstrap SectionStatus records (not_started by default) ─────────────
    for section in permitted:
        SectionStatus.objects.get_or_create(
            user=user, regime=regime, section=section,
            defaults={'status': 'not_started'},
        )

    # ── Completion state ──────────────────────────────────────────────────────
    statuses = list(
        SectionStatus.objects.filter(
            user=user, regime=regime, section__in=permitted,
        ).values_list('status', flat=True)
    )
    complete_count = statuses.count('complete')
    all_complete   = section_count > 0 and complete_count == section_count
    any_started    = any(s in ('in_progress', 'complete') for s in statuses)

    if all_complete:
        button_label = 'Review or amend your answers'
    elif any_started:
        button_label = 'Continue'
    else:
        button_label = 'Start'

    # ── Layer 1 entry-point URL (patterns A, B, C) ────────────────────────────
    if section_count == 0:
        entry_url = f'/regime/{regime_id}/sections/'
    elif section_count == 1:
        section = permitted.first()
        if all_complete:
            entry_url = f'/section/{section.section_id}/review/'
        elif section.section_type in (1, 2):
            entry_url = f'/section/{section.section_id}/table/'
        else:
            entry_url = f'/section/{section.section_id}/start/'
    elif permitted.filter(schedule__isnull=False).exists():
        # Pattern C — schedules present
        entry_url = f'/regime/{regime_id}/schedules/'
    else:
        # Pattern B — multiple sections, no schedules
        entry_url = f'/regime/{regime_id}/sections/'

    return render(request, 'core/regime_home.html', {
        'regime':         regime,
        'section_count':  section_count,
        'complete_count': complete_count,
        'all_complete':   all_complete,
        'button_label':   button_label,
        'entry_url':      entry_url,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 5.  SELECT SCHEDULE  (Pattern C — first level)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_schedule(request, regime_id):
    """Show schedules that contain at least one permitted section."""
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime, regime_id=regime_id)

    permitted = get_permitted_sections(actor, user).filter(
        schedule__regime_id=regime_id
    ).select_related('schedule')

    schedule_ids = list(
        permitted.values_list('schedule_id', flat=True).distinct()
    )
    schedules = (
        Schedule.objects
        .filter(schedule_id__in=schedule_ids)
        .order_by('display_order')
    )

    # Section statuses for the user, keyed by section_id
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
        section_count  = sched_sections.count()

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
            'section_count':  section_count,
            'status':         sched_status,
            'status_display': _status_label[sched_status],
            'url':            f'/regime/{regime_id}/schedule/{sched.schedule_id}/sections/',
        })

    return render(request, 'core/select_schedule.html', {
        'regime':    regime,
        'schedules': schedule_data,
        'back_url':  '/select-regime/',
    })


# ─────────────────────────────────────────────────────────────────────────────
# 6.  SELECT SECTION  (Pattern B task list; also Pattern C second level)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_section(request, regime_id, schedule_id=None):
    """
    Task-list view: all permitted sections for this regime (filtered by
    schedule_id when coming from the schedule menu).

    Each section shows its status and an action link:
      complete     → /section/<id>/review/  (allow amendment)
      not started  → /section/<id>/start/ or /section/<id>/table/
      in progress  → /section/<id>/start/ or /section/<id>/table/
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

        if status == 'complete':
            action_url = f'/section/{section.section_id}/review/'
        elif section.section_type in (1, 2):
            action_url = f'/section/{section.section_id}/table/'
        else:
            action_url = f'/section/{section.section_id}/start/'

        section_data.append({
            'section':        section,
            'status':         status,
            'status_display': _status_label.get(status, 'Not started'),
            'action_url':     action_url,
        })

    if schedule_id:
        back_url = f'/regime/{regime_id}/schedules/'
    else:
        back_url = '/select-regime/'

    return render(request, 'core/select_section.html', {
        'regime':   regime,
        'schedule': schedule,
        'sections': section_data,
        'back_url': back_url,
    })
