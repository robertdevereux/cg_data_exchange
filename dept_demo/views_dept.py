"""
dept_demo/views_dept.py — Person-picker landing page.

Shown immediately after login. If the actor has agent permissions for other
people they see a person-picker; otherwise they skip straight to dept_home.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.models import Permission
from core.session import update_session

# Non-agent users go through select_regime so single-regime auto-skip still works
_SELF_ONLY_REDIRECT = 'dept_demo:select_regime'


@login_required
def choose_user(request):
    actor = request.user

    # Find all users this actor can act for (excluding themselves)
    clients = list(
        Permission.objects
        .filter(actor=actor)
        .exclude(user=actor)
        .select_related('user')
        .values('user__pk', 'user__first_name', 'user__last_name')
        .distinct()
    )

    if not clients:
        # Acting only for themselves — skip picker, route via select_regime
        # so single-regime users still get the auto-skip to their regime home.
        update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
        return redirect(_SELF_ONLY_REDIRECT)

    if request.method == 'POST':
        chosen_pk = request.POST.get('user_id')
        valid_pks = [str(c['user__pk']) for c in clients]
        if chosen_pk not in valid_pks:
            return redirect('dept_demo:choose_user')
        update_session(request, {
            'user_id':  int(chosen_pk),
            'actor_id': actor.pk,
        })
        return redirect('dept_demo:dept_home')

    return render(request, 'dept_demo/choose_user.html', {
        'clients': clients,
        'actor':   actor,
    })
