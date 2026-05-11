from django.urls import path

from . import views_admin_tools, views_layer2

app_name = 'core'

urlpatterns = [

    # ── Admin tools ───────────────────────────────────────────────────────────
    path('tools/',
         views_admin_tools.tools_home,
         name='tools_index'),

    path('tools/viewer/',
         views_admin_tools.tools_viewer,
         name='tools_viewer'),

    path('tools/question/<str:question_id>/edit/',
         views_admin_tools.tools_question_edit,
         name='tools_question_edit'),

    path('tools/set/<str:set_id>/edit/',
         views_admin_tools.tools_set_edit,
         name='tools_set_edit'),


    # ── Standard section flow ─────────────────────────────────────────────────
    path('section/<str:section_id>/start/',
         views_layer2.section_start,
         name='section_start'),

    path('section/<str:section_id>/question/<str:question_id>/',
         views_layer2.section_question,
         name='section_question'),

    path('section/<str:section_id>/set/<str:set_id>/',
         views_layer2.section_set_page,
         name='section_set_page'),

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
