from django.shortcuts import render

from .models import Department, Regime


def root_landing(request):
    """
    Root landing page — lists all non-platform departments and their regimes.
    No login required; serves as the entry point for the whole platform.
    """
    depts = Department.objects.exclude(dept_id='PLATFORM').order_by('dept_id')
    dept_data = []
    for dept in depts:
        regimes = Regime.objects.filter(dept_id=dept.dept_id).order_by('display_order', 'regime_id')
        if regimes.exists():
            dept_data.append({'dept': dept, 'regimes': regimes})
    return render(request, 'core/root_landing.html', {'dept_data': dept_data})
