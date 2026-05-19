from django.urls import path, include
from . import views
from core.views_layer1 import regime_schedules, regime_schedule_sections, regime_sections

app_name = 'dept_defra'

urlpatterns = [
    path('',
         views.dept_home,
         name='dept_home'),
    path('regimes/',
         views.dept_home,
         name='regime_list'),
    path('regime/<str:regime_id>/',
         views.regime_home,
         name='regime_home'),
    path('regime/<str:regime_id>/sections/',
         regime_sections,
         name='regime_sections'),
    path('<str:regime_id>/schedules/',
         regime_schedules,
         name='regime_schedules'),
    path('<str:regime_id>/schedule/<str:schedule_id>/sections/',
         regime_schedule_sections,
         name='regime_schedule_sections'),
    path('tools/', include('core.urls_tools')),
]
