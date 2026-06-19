from django.urls import include, path

from . import views

app_name = 'dept_hmrc'

urlpatterns = [
    path('',                        views.dept_home,   name='dept_home'),
    path('regimes/',                views.regime_list, name='regime_list'),
    path('regime/<str:regime_id>/', views.regime_home, name='regime_home'),

    # Pattern B Layer 1 — section task list (no schedule) under /hmrc/
    path('regime/<str:regime_id>/sections/',
         views.regime_sections,
         name='select_section'),

    # Pattern C Layer 1 — schedule list and schedule-section list under /hmrc/
    path('regime/<str:regime_id>/schedules/',
         views.regime_schedules,
         name='regime_schedules'),
    path('regime/<str:regime_id>/schedule/<str:schedule_id>/sections/',
         views.regime_schedule_sections,
         name='regime_schedule_sections'),

    # IHT reckoner bespoke threshold question
    path('iht/reckoner/threshold/',
         views.iht_reckoner_threshold,
         name='iht_reckoner_threshold'),

    # IHT reckoner compute — intercepts section_done after S3
    path('iht/reckoner/compute/',
         views.iht_reckoner_compute,
         name='iht_reckoner_compute'),

    # IHT action entry points — set current_action then dispatch
    path('iht/action/deceased/', views.iht_action_deceased, name='iht_action_deceased'),
    path('iht/action/reckoner/', views.iht_action_reckoner, name='iht_action_reckoner'),
    path('iht/action/tailor/',   views.iht_action_tailor,   name='iht_action_tailor'),

    path('tools/',                  include('core.urls_tools')),
]
