from django.urls import path

from . import views_admin_tools, views_layer2

app_name = 'core'

urlpatterns = [

    # ── Admin tools ───────────────────────────────────────────────────────────
    path('tools/',
         views_admin_tools.tools_home,
         name='tools_index'),

    path('tools/questions/',
         views_admin_tools.tools_questions_list,
         name='tools_questions_list'),

    path('tools/questions/add/',
         views_admin_tools.tools_question_add,
         name='tools_question_add'),

    path('tools/questions/edit/',
         views_admin_tools.tools_questions_edit_picker,
         name='tools_questions_edit_picker'),

    path('tools/sets/',
         views_admin_tools.tools_sets_list,
         name='tools_sets_list'),

    path('tools/sets/add/',
         views_admin_tools.tools_set_add,
         name='tools_set_add'),

    path('tools/sets/edit/',
         views_admin_tools.tools_sets_edit_picker,
         name='tools_sets_edit_picker'),

    path('tools/sections/',
         views_admin_tools.tools_sections_list,
         name='tools_sections_list'),

    path('tools/sections/create/',
         views_admin_tools.tools_section_create,
         name='tools_section_create'),

    path('tools/sections/copy/',
         views_admin_tools.tools_section_copy_picker,
         name='tools_section_copy_picker'),

    path('tools/regimes/',
         views_admin_tools.tools_regime_list,
         name='tools_regime_list'),

    path('tools/regimes/create/',
         views_admin_tools.tools_regime_create,
         name='tools_regime_create'),

    path('tools/viewer/',
         views_admin_tools.tools_viewer,
         name='tools_viewer'),

    path('tools/question/<str:question_id>/edit/',
         views_admin_tools.tools_question_edit,
         name='tools_question_edit'),

    path('tools/set/<str:set_id>/edit/',
         views_admin_tools.tools_set_edit,
         name='tools_set_edit'),

    path('tools/set/<str:set_id>/member/add/',
         views_admin_tools.tools_set_member_add,
         name='tools_set_member_add'),

    path('tools/set/<str:set_id>/member/<str:question_id>/remove/',
         views_admin_tools.tools_set_member_remove,
         name='tools_set_member_remove'),

    path('tools/schedules/',
         views_admin_tools.tools_schedule_list,
         name='tools_schedule_list'),

    path('tools/schedules/create/',
         views_admin_tools.tools_schedule_create,
         name='tools_schedule_create'),

    path('tools/schedules/<str:schedule_id>/sections/',
         views_admin_tools.tools_schedule_sections,
         name='tools_schedule_sections'),

    path('tools/schedules/<str:schedule_id>/sections/add/',
         views_admin_tools.tools_schedule_section_add,
         name='tools_schedule_section_add'),

    path('tools/schedules/<str:schedule_id>/sections/remove/',
         views_admin_tools.tools_schedule_section_remove,
         name='tools_schedule_section_remove'),

    path('tools/schedules/<str:schedule_id>/sections/reorder/',
         views_admin_tools.tools_schedule_section_reorder,
         name='tools_schedule_section_reorder'),

    path('tools/sections/<str:section_id>/routing/',
         views_admin_tools.tools_section_routing,
         name='tools_section_routing'),

    path('tools/sections/<str:section_id>/routing/insert/',
         views_admin_tools.tools_routing_insert,
         name='tools_routing_insert'),

    path('tools/sections/<str:section_id>/routing/delete/',
         views_admin_tools.tools_routing_delete,
         name='tools_routing_delete'),

    path('tools/sections/<str:section_id>/routing/delete-condition/',
         views_admin_tools.tools_routing_delete_condition,
         name='tools_routing_delete_condition'),

    path('tools/sections/<str:section_id>/routing/add-condition/',
         views_admin_tools.tools_routing_add_condition,
         name='tools_routing_add_condition'),

    path('tools/create/',
         views_admin_tools.tools_create,
         name='tools_create'),

    path('tools/create/save/',
         views_admin_tools.tools_create_save,
         name='tools_create_save'),

    path('tools/create/abandon/',
         views_admin_tools.tools_create_abandon,
         name='tools_create_abandon'),


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
