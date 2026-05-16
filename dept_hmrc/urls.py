from django.urls import path

from . import views

app_name = 'dept_hmrc'

urlpatterns = [
    path('',                        views.dept_home,   name='dept_home'),
    path('regimes/',                views.regime_list, name='regime_list'),
    path('regime/<str:regime_id>/', views.regime_home, name='regime_home'),
]
