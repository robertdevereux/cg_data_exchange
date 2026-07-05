from django.urls import path

from . import views_admin_tools

# All admin tools URL patterns.
# Included at tools/ in core/urls.py (→ /tools/) and in each dept's urls.py
# (→ /hmrc/tools/, /dwp/tools/, /demo/tools/) so that the active dept's
# tools are reachable after setting request.session['active_dept'].
#
# The core:tools_* namespace resolves because core/urls.py includes this file
# under the 'core' app_name namespace.

urlpatterns = [

    path('',
         views_admin_tools.tools_home,
         name='tools_index'),

    path('switch-dept/',
         views_admin_tools.tools_switch_dept,
         name='tools_switch_dept'),

    path('questions/',
         views_admin_tools.tools_questions_list,
         name='tools_questions_list'),

    path('questions/add/',
         views_admin_tools.tools_question_add,
         name='tools_question_add'),

    path('questions/<str:question_id>/type/',
         views_admin_tools.tools_question_type_info,
         name='tools_question_type_info'),

    path('sets/',
         views_admin_tools.tools_sets_list,
         name='tools_sets_list'),

    path('sets/add/',
         views_admin_tools.tools_set_add,
         name='tools_set_add'),

    path('sections/',
         views_admin_tools.tools_sections_list,
         name='tools_sections_list'),

    path('sections/create/',
         views_admin_tools.tools_section_create,
         name='tools_section_create'),

    path('sections/copy/',
         views_admin_tools.tools_section_copy_picker,
         name='tools_section_copy_picker'),

    path('regimes/',
         views_admin_tools.tools_regime_list,
         name='tools_regime_list'),

    path('regimes/create/',
         views_admin_tools.tools_regime_create,
         name='tools_regime_create'),

    path('regimes/<str:regime_id>/move-up/',
         views_admin_tools.tools_regime_move_up,
         name='tools_regime_move_up'),

    path('regimes/<str:regime_id>/move-down/',
         views_admin_tools.tools_regime_move_down,
         name='tools_regime_move_down'),

    path('regimes/<str:regime_id>/item/<str:item_id>/move-up/',
         views_admin_tools.tools_regime_item_move_up,
         name='tools_regime_item_move_up'),

    path('regimes/<str:regime_id>/item/<str:item_id>/move-down/',
         views_admin_tools.tools_regime_item_move_down,
         name='tools_regime_item_move_down'),

    path('regimes/<str:regime_id>/add-item/',
         views_admin_tools.tools_regime_item_add,
         name='tools_regime_item_add'),

    path('regimes/<str:regime_id>/delete/',
         views_admin_tools.tools_regime_delete,
         name='tools_regime_delete'),

    path('regimes/<str:regime_id>/',
         views_admin_tools.tools_regime_edit_composite,
         name='tools_regime_edit_composite'),

    path('regimes/<str:regime_id>/edit/',
         views_admin_tools.tools_regime_edit,
         name='tools_regime_edit'),

    path('viewer/',
         views_admin_tools.tools_viewer,
         name='tools_viewer'),

    path('question/<str:question_id>/edit/',
         views_admin_tools.tools_question_edit,
         name='tools_question_edit'),

    path('set/<str:set_id>/edit/',
         views_admin_tools.tools_set_edit,
         name='tools_set_edit'),

    path('set/<str:set_id>/member/add/',
         views_admin_tools.tools_set_member_add,
         name='tools_set_member_add'),

    path('set/<str:set_id>/member/<str:question_id>/remove/',
         views_admin_tools.tools_set_member_remove,
         name='tools_set_member_remove'),

    path('set/<str:set_id>/member/reorder/',
         views_admin_tools.tools_set_member_reorder,
         name='tools_set_member_reorder'),

    path('actors/',
         views_admin_tools.tools_actors,
         name='tools_actors'),

    path('actors/create/',
         views_admin_tools.tools_actor_create,
         name='tools_actor_create'),

    path('actors/revoke/',
         views_admin_tools.tools_actor_revoke,
         name='tools_actor_revoke'),

    path('navigation/',
         views_admin_tools.tools_navigation,
         name='tools_navigation'),

    path('navigation/<str:regime_id>/',
         views_admin_tools.tools_navigation_regime,
         name='tools_navigation_regime'),

    path('schedules/',
         views_admin_tools.tools_schedule_list,
         name='tools_schedule_list'),

    path('schedules/create/',
         views_admin_tools.tools_schedule_create,
         name='tools_schedule_create'),

    path('schedules/<str:schedule_id>/delete/',
         views_admin_tools.tools_schedule_delete,
         name='tools_schedule_delete'),

    path('schedules/<str:schedule_id>/edit/',
         views_admin_tools.tools_schedule_edit,
         name='tools_schedule_edit'),

    path('schedules/<str:schedule_id>/sections/',
         views_admin_tools.tools_schedule_sections,
         name='tools_schedule_sections'),

    path('schedules/<str:schedule_id>/sections/add/',
         views_admin_tools.tools_schedule_section_add,
         name='tools_schedule_section_add'),

    path('schedules/<str:schedule_id>/sections/<str:section_id>/move-up/',
         views_admin_tools.tools_schedule_section_move_up,
         name='tools_schedule_section_move_up'),

    path('schedules/<str:schedule_id>/sections/<str:section_id>/move-down/',
         views_admin_tools.tools_schedule_section_move_down,
         name='tools_schedule_section_move_down'),

    path('schedules/<str:schedule_id>/sections/remove/',
         views_admin_tools.tools_schedule_section_remove,
         name='tools_schedule_section_remove'),

    path('schedules/<str:schedule_id>/sections/reorder/',
         views_admin_tools.tools_schedule_section_reorder,
         name='tools_schedule_section_reorder'),

    path('sections/<str:section_id>/delete/',
         views_admin_tools.tools_section_delete,
         name='tools_section_delete'),

    path('sections/<str:section_id>/edit/',
         views_admin_tools.tools_section_edit,
         name='tools_section_edit'),

    path('sections/<str:section_id>/members/add/',
         views_admin_tools.tools_section_member_add,
         name='tools_section_member_add'),

    path('sections/<str:section_id>/members/<str:node_id>/remove/',
         views_admin_tools.tools_section_member_remove,
         name='tools_section_member_remove'),

    path('sections/<str:section_id>/routing/',
         views_admin_tools.tools_section_routing,
         name='tools_section_routing'),

    path('sections/<str:section_id>/routing/insert/',
         views_admin_tools.tools_routing_insert,
         name='tools_routing_insert'),

    path('sections/<str:section_id>/routing/delete/',
         views_admin_tools.tools_routing_delete,
         name='tools_routing_delete'),

    path('sections/<str:section_id>/routing/delete-condition/',
         views_admin_tools.tools_routing_delete_condition,
         name='tools_routing_delete_condition'),

    path('sections/<str:section_id>/routing/add-condition/',
         views_admin_tools.tools_routing_add_condition,
         name='tools_routing_add_condition'),

    path('create/',
         views_admin_tools.tools_create,
         name='tools_create'),

    path('create/save/',
         views_admin_tools.tools_create_save,
         name='tools_create_save'),

    path('create/abandon/',
         views_admin_tools.tools_create_abandon,
         name='tools_create_abandon'),
]
