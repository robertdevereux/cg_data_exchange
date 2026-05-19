from django.conf import settings
from django.contrib.auth import logout as auth_logout
from django.shortcuts import render

from .models import Department, Regime


def root_landing(request):
    """
    Root landing page — lists all non-platform departments and their regimes.
    No login required; serves as the entry point for the whole platform.
    Logs out any authenticated user so every visit starts a fresh session.
    """
    if request.user.is_authenticated:
        auth_logout(request)
    depts = Department.objects.exclude(dept_id__in=['PLATFORM', 'DWP', 'DEMO']).order_by('dept_id')
    dept_base_urls = settings.DEPT_BASE_URLS
    dept_data = []
    for dept in depts:
        base = dept_base_urls.get(dept.dept_id, '')
        prefix = dept.dept_id.lower()
        regimes = Regime.objects.filter(dept_id=dept.dept_id).order_by('display_order', 'regime_id')
        if regimes.exists():
            dept_data.append({
                'dept':     dept,
                'dept_url': f'{base}/{prefix}/' if base else f'/{prefix}/',
                'regimes':  [
                    {
                        'regime': r,
                        'url':    f'{base}/{prefix}/regime/{r.regime_id}/' if base else f'/{prefix}/regime/{r.regime_id}/',
                    }
                    for r in regimes
                ],
            })
    return render(request, 'core/root_landing.html', {'dept_data': dept_data})
