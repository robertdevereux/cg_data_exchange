from django.urls import include, path

from . import (
    views_home,
    views_nav,
    views_regime_schedules,
    views_regime_sections,
    views_regime_simple,
)

app_name = 'dept_demo'

urlpatterns = [
    # Entry point — regime selection (identity picker follows after regime chosen)
    path('',
         views_nav.select_regime,
         name='select_regime'),

    # Per-regime identity picker — runs after regime is selected
    path('regime/<str:regime_id>/choose/',
         views_nav.choose_identity,
         name='choose_identity'),

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
    # Pattern B: section task list (no schedule)
    path('regime/<str:regime_id>/sections/',
         views_nav.select_section,
         name='select_section'),
    # Pattern C: schedule list and schedule-section list are served by core
    # at /regime/<regime_id>/schedules/ and /regime/<id>/schedule/<id>/sections/

    path('tools/', include('core.urls_tools')),
]
