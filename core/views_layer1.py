"""
core/views_layer1.py — Temporary Layer 1 navigation.

NOTE: This file contains Layer 1 navigation views that currently live in core
for convenience. These will move to dept_demo/ in the next refactoring step.
They are reference implementations, not platform code.

See core/nav_reference.py for the pattern library.
See core/interfaces.py for the platform interface.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .interfaces import bootstrap_section_statuses, get_or_create_case
from .models import Regime, SectionStatus, User
from .nav_reference import (  # re-exported so urls.py can import via views_layer1
    _resolve_user,
    resolve_layer1_entry_url,
    select_schedule,
    select_section,
)
from .permissions import get_permitted_regimes, get_permitted_sections
from .session import get_session, update_session


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
# 4.  REGIME HOME  (landing page + bootstrap)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def regime_start(request, regime_id):
    """
    Landing page for a regime.  Bootstraps Case and SectionStatus on first
    visit (idempotent) via the platform interface.

    Shows:
      - Regime name + placeholder guidance
      - Action group 1: completion summary + Start/Continue/Review button
        whose target URL is resolved by resolve_layer1_entry_url()
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

    # ── Bootstrap via platform interface ─────────────────────────────────────
    case = get_or_create_case(user, regime)

    update_session(request, {
        'user_id':     user.pk,
        'actor_id':    actor.pk,
        'regime_id':   regime_id,
        'regime_name': regime.regime_name,
        'case_id':     case.case_id,
    })

    bootstrap_section_statuses(user, regime, permitted)

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

    entry_url = resolve_layer1_entry_url(permitted, regime_id, all_complete)

    return render(request, 'core/regime_home.html', {
        'regime':         regime,
        'section_count':  section_count,
        'complete_count': complete_count,
        'all_complete':   all_complete,
        'button_label':   button_label,
        'entry_url':      entry_url,
    })
