from django.urls import include, path

from . import views

app_name = 'dept_hmrc'

urlpatterns = [
    path('',                        views.dept_home,   name='dept_home'),
    path('regimes/',                views.regime_list, name='regime_list'),
    path('regime/<str:regime_id>/', views.regime_home, name='regime_home'),

    # Pattern C Layer 1 — schedule list and schedule-section list under /hmrc/
    path('regime/<str:regime_id>/schedules/',
         views.regime_schedules,
         name='regime_schedules'),
    path('regime/<str:regime_id>/schedule/<str:schedule_id>/sections/',
         views.regime_schedule_sections,
         name='regime_schedule_sections'),

    path('tools/',                  include('core.urls_tools')),
]
