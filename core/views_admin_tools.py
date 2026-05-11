"""
Admin Tools: Regime Configuration Viewer
=========================================
Staff-only views for inspecting and editing regime configuration.

  /tools/viewer/                              — browse regimes / routing tables
  /tools/question/<question_id>/edit/         — edit a single question
  /tools/set/<set_id>/edit/                   — edit a QuestionSet header
"""

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from .models import (
    Question,
    QuestionSet,
    Regime,
    Routing,
    Schedule,
    Section,
)

staff_required = user_passes_test(lambda u: u.is_staff)


# ─────────────────────────────────────────────────────────────────────────────
# 0. TOOLS HOME
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_home(request):
    """Staff landing page — entry point for all platform admin tools."""
    return render(request, 'core/tools_home.html', {})


# ── Back-URL helper ───────────────────────────────────────────────────────────

def _back_url(back_regime, back_schedule, back_section):
    """Reconstruct the viewer URL from saved back-navigation params."""
    params = []
    if back_regime:
        params.append(f'regime={back_regime}')
    if back_schedule:
        params.append(f'schedule={back_schedule}')
    if back_section:
        params.append(f'section={back_section}')
    qs = '&'.join(params)
    return f'/tools/viewer/?{qs}' if qs else '/tools/viewer/'


# ─────────────────────────────────────────────────────────────────────────────
# 1. REGIME CONFIGURATION VIEWER
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_viewer(request):
    """Three-zone viewer: selector bar → routing table → node detail panels."""
    regimes = Regime.objects.exclude(dept_id='PLATFORM')

    selected_regime_id  = request.GET.get('regime', '')
    selected_section_id = request.GET.get('section', '')

    selected_regime          = None
    selected_section         = None
    regime_schedules         = []
    regime_direct_sections   = []
    routing_rows             = []
    detail_questions         = {}   # {question_id: Question}
    detail_sets              = {}   # {set_id: QuestionSet}

    if selected_regime_id:
        selected_regime = get_object_or_404(Regime, regime_id=selected_regime_id)
        regime_schedules = (
            Schedule.objects
            .filter(regime=selected_regime)
            .prefetch_related('sections')
            .order_by('display_order', 'schedule_name')
        )
        regime_direct_sections = (
            Section.objects
            .filter(regime=selected_regime, schedule__isnull=True)
            .order_by('display_order', 'section_name')
        )

    if selected_section_id:
        selected_section = get_object_or_404(Section, section_id=selected_section_id)

        routing_rows = list(
            Routing.objects
            .filter(section=selected_section)
            .order_by('order_in_section')
        )

        # Unique ordered list of all nodes in this section's routing
        node_ids = list(dict.fromkeys(r.current_node for r in routing_rows))

        # Separate Q-nodes (standalone questions) from S-nodes (QuestionSets)
        existing_set_ids = set(
            QuestionSet.objects
            .filter(set_id__in=node_ids)
            .values_list('set_id', flat=True)
        )
        q_node_ids = [nid for nid in node_ids if nid not in existing_set_ids]
        s_node_ids = [nid for nid in node_ids if nid in existing_set_ids]

        if q_node_ids:
            for q in Question.objects.filter(question_id__in=q_node_ids):
                detail_questions[q.question_id] = q

        if s_node_ids:
            for qs in (
                QuestionSet.objects
                .filter(set_id__in=s_node_ids)
                .prefetch_related('members__question')
            ):
                detail_sets[qs.set_id] = qs

    context = {
        'regimes':                regimes,
        'selected_regime':        selected_regime,
        'selected_section':       selected_section,
        'regime_schedules':       regime_schedules,
        'regime_direct_sections': regime_direct_sections,
        'routing_rows':           routing_rows,
        'detail_questions':       detail_questions,
        'detail_sets':            detail_sets,
        'selected_regime_id':     selected_regime_id,
        'selected_section_id':    selected_section_id,
    }
    return render(request, 'core/tools_viewer.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 2. QUESTION EDIT
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_question_edit(request, question_id):
    question = get_object_or_404(Question, question_id=question_id)

    if request.method == 'POST':
        back_regime   = request.POST.get('back_regime', '')
        back_schedule = request.POST.get('back_schedule', '')
        back_section  = request.POST.get('back_section', '')

        question.question_text = request.POST.get('question_text', question.question_text).strip()
        question.question_type = request.POST.get('question_type', question.question_type).strip()
        question.guidance = request.POST.get('guidance', '').strip() or None
        question.hint     = request.POST.get('hint', '').strip() or None
        question.options  = request.POST.get('options', '').strip() or None
        question.save()

        return redirect(_back_url(back_regime, back_schedule, back_section))

    back_regime   = request.GET.get('back_regime', '')
    back_schedule = request.GET.get('back_schedule', '')
    back_section  = request.GET.get('back_section', '')

    context = {
        'question':             question,
        'question_type_choices': Question.QUESTION_TYPE_CHOICES,
        'back_url':             _back_url(back_regime, back_schedule, back_section),
        'back_regime':          back_regime,
        'back_schedule':        back_schedule,
        'back_section':         back_section,
    }
    return render(request, 'core/tools_question_edit.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 3. QUESTION SET EDIT
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_set_edit(request, set_id):
    qs = get_object_or_404(
        QuestionSet.objects.prefetch_related('members__question'),
        set_id=set_id,
    )

    if request.method == 'POST':
        back_regime   = request.POST.get('back_regime', '')
        back_schedule = request.POST.get('back_schedule', '')
        back_section  = request.POST.get('back_section', '')

        qs.set_title = request.POST.get('set_title', qs.set_title).strip()
        qs.set_hint  = request.POST.get('set_hint', '').strip() or None
        qs.save()

        return redirect(_back_url(back_regime, back_schedule, back_section))

    back_regime   = request.GET.get('back_regime', '')
    back_schedule = request.GET.get('back_schedule', '')
    back_section  = request.GET.get('back_section', '')

    context = {
        'qs':           qs,
        'back_url':     _back_url(back_regime, back_schedule, back_section),
        'back_regime':  back_regime,
        'back_schedule': back_schedule,
        'back_section': back_section,
    }
    return render(request, 'core/tools_set_edit.html', context)
