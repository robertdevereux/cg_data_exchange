from django.urls import path

from . import (
    views_home,
    views_nav,
    views_regime_schedules,
    views_regime_sections,
    views_regime_simple,
)

app_name = 'dept_demo'

urlpatterns = [
    # Entry point — establishes actor/user context
    path('',
         views_nav.choose_user,
         name='home'),

    # Regime selection (multi-regime users)
    path('select-regime/',
         views_nav.select_regime,
         name='select_regime'),

    # Regime card list (reached from select_regime when count > 1)
    path('regimes/',
         views_home.dept_home,
         name='dept_home'),

    # ── Specific regime home pages — MUST come before the generic router ──
    path('regime/demo-simple/',
         views_regime_simple.regime_simple_home,
         name='regime_demo_simple'),

    path('regime/demo-sections/',
         views_regime_sections.regime_sections_home,
         name='regime_demo_sections'),

    path('regime/demo-schedules/',
         views_regime_schedules.regime_schedules_home,
         name='regime_demo_schedules'),

    # Generic router — maps regime_id → correct regime home page
    path('regime/<str:regime_id>/',
         views_nav.regime_home,
         name='regime_home'),

    # ── Layer 1 navigation patterns ───────────────────────────────────────
    path('regime/<str:regime_id>/schedules/',
         views_nav.select_schedule,
         name='select_schedule'),

    path('regime/<str:regime_id>/sections/',
         views_nav.select_section,
         name='select_section'),

    path('regime/<str:regime_id>/schedule/<str:schedule_id>/sections/',
         views_nav.select_section,
         name='select_section_in_schedule'),
]
