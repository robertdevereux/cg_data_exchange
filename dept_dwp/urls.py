from django.urls import path

from . import views_dept, views_home, views_nav, views_regime_generic

app_name = 'dept_dwp'

urlpatterns = [
    # Entry point — person-picker (agents) or straight to select_regime
    path('',
         views_dept.choose_user,
         name='choose_user'),

    # Regime selection
    path('select-regime/',
         views_nav.select_regime,
         name='select_regime'),

    # Regime card list
    path('regimes/',
         views_home.dept_home,
         name='dept_home'),

    # Generic regime home — all DWP regime IDs route here directly
    path('regime/<str:regime_id>/',
         views_regime_generic.regime_generic_home,
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
