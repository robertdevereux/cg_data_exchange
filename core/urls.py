from django.urls import include, path

from . import views, views_gate, views_layer1, views_layer2

app_name = 'core'

urlpatterns = [

    # ── Root landing page ─────────────────────────────────────────────────────
    path('', views.root_landing, name='root_landing'),

    # ── Regime-scoped identity picker actions ─────────────────────────────────
    path('select-identity/<int:perm_id>/', views_gate.select_identity, name='select_identity'),
    path('select-self/',                    views_gate.select_self,      name='select_self'),

    # ── Admin tools (also mounted at /hmrc/tools/, /dwp/tools/, /demo/tools/) ─
    path('tools/', include('core.urls_tools')),


    # ── Layer 1 navigation — Pattern B (direct section list) ─────────────────
    path('regime/<str:regime_id>/sections/',
         views_layer1.regime_sections,
         name='regime_sections'),

    # ── Layer 1 navigation — mixed top-level (schedules + bare sections) ────────
    path('regime/<str:regime_id>/top/',
         views_layer1.regime_top_level,
         name='regime_top_level'),

    # ── Layer 1 navigation — Pattern C (schedule → section list) ─────────────
    path('regime/<str:regime_id>/schedules/',
         views_layer1.regime_schedules,
         name='regime_schedules'),

    path('regime/<str:regime_id>/schedule/<str:schedule_id>/sections/',
         views_layer1.regime_schedule_sections,
         name='regime_schedule_sections'),

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

    path('section/<str:section_id>/table/add-routed/',
         views_layer2.section_table_routed_add,
         name='section_table_routed_add'),

    path('section/<str:section_id>/table/add-routed/<str:question_or_set_id>/',
         views_layer2.section_table_routed_question,
         name='section_table_routed_question'),

    path('section/<str:section_id>/table/change/<int:row_index>/',
         views_layer2.section_table_routed_change,
         name='section_table_routed_change'),

    path('section/<str:section_id>/table/row-detail/<int:row_index>/',
         views_layer2.section_table_row_detail,
         name='section_table_row_detail'),

    path('section/<str:section_id>/confirm-table/',
         views_layer2.section_confirm_table,
         name='section_confirm_table'),

    # ── Shared ────────────────────────────────────────────────────────────────
    path('section/<str:section_id>/done/',
         views_layer2.section_done,
         name='section_done'),
]
