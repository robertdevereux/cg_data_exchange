"""
dept_dwp/views_dept.py — Person-picker landing page for DWP.

If the actor has agent permissions for other people they see a person-picker;
otherwise they skip straight to dept_home.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.models import Permission
from core.session import clear_working_session, update_session

_SELF_ONLY_REDIRECT = 'dept_dwp:dept_home'


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
        # Acting only for themselves — skip picker, go straight to dept_home
        update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
        return redirect(_SELF_ONLY_REDIRECT)

    if request.method == 'POST':
        chosen_pk = request.POST.get('user_id')
        valid_pks = [str(c['user__pk']) for c in clients]
        if chosen_pk not in valid_pks:
            return redirect('dept_dwp:choose_user')
        update_session(request, {
            'user_id':  int(chosen_pk),
            'actor_id': actor.pk,
        })
        return redirect('dept_dwp:dept_home')

    # GET — clear any working state from a previous client
    clear_working_session(request)

    return render(request, 'dept_dwp/choose_user.html', {
        'clients': clients,
        'actor':   actor,
    })
