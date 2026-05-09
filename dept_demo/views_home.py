"""
dept_demo/views_home.py — Department landing page.

Entry point for all citizens arriving at this department's services.
Shows available regimes with completion status.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse

from core.models import SectionStatus
from core.permissions import get_permitted_regimes, get_permitted_sections


@login_required
def dept_home(request):
    """
    Department landing page. Shows available regimes for the logged-in user.
    Self-filing only for now — actor and user are both the logged-in citizen.
    """
    actor = request.user
    user  = request.user

    permitted_regimes = get_permitted_regimes(actor, user)

    if not permitted_regimes.exists():
        return render(request, 'dept_demo/home.html', {
            'regime_data': [],
            'no_access': True,
        })

    # Auto-skip to regime home if only one regime available
    if permitted_regimes.count() == 1:
        regime = permitted_regimes.first()
        return redirect(
            reverse('dept_demo:regime_home', kwargs={'regime_id': regime.regime_id})
        )

    # Build regime card data with completion status
    regime_data = []
    for regime in permitted_regimes:
        permitted = get_permitted_sections(actor, user).filter(
            Q(regime_id=regime.regime_id) | Q(schedule__regime_id=regime.regime_id)
        )
        total = permitted.count()
        complete = SectionStatus.objects.filter(
            user=user,
            regime=regime,
            section__in=permitted,
            status='complete',
        ).count()

        if total == 0 or complete == 0:
            status_text = 'Not started'
        elif complete == total:
            status_text = 'Complete'
        else:
            status_text = f'In progress ({complete} of {total} complete)'

        regime_data.append({
            'regime':       regime,
            'status_text':  status_text,
            'url': reverse('dept_demo:regime_home',
                           kwargs={'regime_id': regime.regime_id}),
        })

    return render(request, 'dept_demo/home.html', {'regime_data': regime_data})
