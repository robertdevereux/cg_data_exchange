from django.urls import path

from . import views_layer1, views_layer2

app_name = 'core'

urlpatterns = [
    # ── Layer 1: navigation ───────────────────────────────────────────────────
    path('',
         views_layer1.home,
         name='home'),

    path('choose-user/',
         views_layer1.choose_user,
         name='choose_user'),

    path('select-regime/',
         views_layer1.select_regime,
         name='select_regime'),

    path('regime/<str:regime_id>/',
         views_layer1.regime_start,
         name='regime_start'),

    path('regime/<str:regime_id>/schedules/',
         views_layer1.select_schedule,
         name='select_schedule'),

    path('regime/<str:regime_id>/sections/',
         views_layer1.select_section,
         name='select_section'),

    path('regime/<str:regime_id>/schedule/<str:schedule_id>/sections/',
         views_layer1.select_section,
         name='select_section_by_schedule'),

    # ── Standard section flow ─────────────────────────────────────────────────
    path('section/<str:section_id>/start/',
         views_layer2.section_start,
         name='section_start'),

    path('section/<str:section_id>/question/<str:question_id>/',
         views_layer2.section_question,
         name='section_question'),

    path('section/<str:section_id>/review/',
         views_layer2.section_review,
         name='section_review'),

    path('section/<str:section_id>/confirm/',
         views_layer2.section_confirm,
         name='section_confirm'),

    # ── Table section flow ────────────────────────────────────────────────────
    path('section/<str:section_id>/table/',
         views_layer2.section_table,
         name='section_table'),

    path('section/<str:section_id>/table/add/',
         views_layer2.section_table_add,
         name='section_table_add'),

    path('section/<str:section_id>/table/delete/<int:row_index>/',
         views_layer2.section_table_delete,
         name='section_table_delete'),

    path('section/<str:section_id>/confirm-table/',
         views_layer2.section_confirm_table,
         name='section_confirm_table'),

    # ── Shared ────────────────────────────────────────────────────────────────
    path('section/<str:section_id>/done/',
         views_layer2.section_done,
         name='section_done'),
]
