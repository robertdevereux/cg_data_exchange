"""
core/views_gate.py — Regime-scoped identity picker gate.

choose_user_for_regime is called by each department's choose_identity wrapper
after a regime has been selected.  It presents a list of identities the actor
can file for within that specific regime, auto-skipping when there is only one.

select_self and select_identity are the two URL-dispatchable actions that write
session state (user_id / actor_id / case_id) and redirect to next_url.
"""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import Permission
from core.session import update_session


def choose_user_for_regime(request, regime, leading_option, next_url):
    """
    Show a picker of identities the actor can file for within a specific regime.

    leading_option: dict {'label': str, 'action_url': str} — always shown first.
    For self-filing regimes this is 'Myself' → core:select_self.
    For IHT this is 'Begin a new estate' → iht_start_new_estate (via select_self).

    Other candidates come from Permission rows scoped to this regime, including:
      - regime-level grants (Permission.regime = regime)
      - section-level grants where section belongs to this regime (direct or via schedule)
    Deduplicated by user so each person appears at most once.

    Auto-skips when there is exactly one candidate (the common single-user case).
    """
    actor = request.user

    perms_qs = (
        Permission.objects
        .filter(actor=actor)
        .filter(
            Q(regime=regime) |
            Q(section__regime=regime) |
            Q(section__schedule__regime=regime)
        )
        .exclude(user=actor)
        .select_related('user', 'case')
        .order_by('-regime_id')          # regime-scoped perms first
    )

    # Deduplicate by user_id — one candidate per person, best perm wins
    seen = {}
    for perm in perms_qs:
        if perm.user_id not in seen:
            seen[perm.user_id] = perm

    candidates = [leading_option]
    for perm in seen.values():
        candidates.append({
            'label':      perm.user.get_full_name() or perm.user.username,
            'action_url': _build_select_identity_url(perm, next_url),
        })

    # Single candidate — skip the screen entirely
    if len(candidates) == 1:
        return redirect(candidates[0]['action_url'])

    # POST — validate the chosen action_url and redirect to it
    if request.method == 'POST':
        chosen = request.POST.get('action_url', '')
        valid  = {c['action_url'] for c in candidates}
        if chosen in valid:
            return redirect(chosen)
        return render(request, 'core/choose_user.html', {
            'candidates': candidates,
            'error':      'Please select an option.',
        })

    # GET — show choice
    return render(request, 'core/choose_user.html', {'candidates': candidates})


def _build_select_identity_url(perm, next_url):
    """
    Build the URL for a permission-based candidate.  Visiting this URL will
    write user_id / actor_id (and case_id when the perm is case-scoped) to
    the session, then redirect to next_url.
    """
    qs = urlencode({'next': next_url})
    return f"{reverse('core:select_identity', kwargs={'perm_id': perm.pk})}?{qs}"


@login_required
def select_identity(request, perm_id):
    """
    Write session state from a Permission row and redirect to ?next=.
    The actor must own the permission (enforced by the actor= filter on get_object_or_404).
    """
    perm     = get_object_or_404(Permission, pk=perm_id, actor=request.user)
    raw_next = request.GET.get('next', '/')
    next_url = raw_next if (raw_next.startswith('/') and not raw_next.startswith('//')) else '/'
    update_session(request, {'user_id': perm.user_id, 'actor_id': request.user.pk})
    if perm.case_id:
        # case_id lives at the top level of request.session (not inside pss)
        # to match the convention used throughout the orchestrators.
        request.session['case_id'] = str(perm.case_id)
        request.session.modified = True
    return redirect(next_url)


@login_required
def select_self(request):
    """
    Set user_id = actor_id = request.user.pk in session and redirect to ?next=.
    Used as the action_url for the 'Myself' leading option (and IHT's 'Begin a
    new estate' option, which chains into iht_start_new_estate after session setup).
    """
    raw_next = request.GET.get('next', '/')
    next_url = raw_next if (raw_next.startswith('/') and not raw_next.startswith('//')) else '/'
    update_session(request, {'user_id': request.user.pk, 'actor_id': request.user.pk})
    return redirect(next_url)
