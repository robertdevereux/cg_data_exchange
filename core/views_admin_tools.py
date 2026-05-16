"""
Admin Tools: Regime Configuration Viewer and Creation Wizard
=============================================================
Staff-only views for inspecting, editing, and creating regime configuration.

  /tools/                                     — staff landing page
  /tools/viewer/                              — browse regimes / routing tables
  /tools/questions/                           — read-only question bank listing
  /tools/sets/                                — read-only question set listing
  /tools/question/<question_id>/edit/         — edit a single question
  /tools/set/<set_id>/edit/                   — edit a QuestionSet header
  /tools/create/                              — regime creation wizard (task list)
  /tools/create/save/                         — save wizard and exit to /tools/
  /tools/create/abandon/                      — abandon current draft and restart
"""

import os
import uuid

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .interfaces import bootstrap_section_statuses, get_or_create_case
from .models import (
    Answer,
    AnswerTable,
    Case,
    Question,
    QuestionSet,
    Regime,
    Routing,
    Schedule,
    Section,
    SectionStatus,
)
from .session import update_session

staff_required = user_passes_test(lambda u: u.is_staff)


# ─────────────────────────────────────────────────────────────────────────────
# 0. TOOLS HOME
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_home(request):
    """Staff landing page — entry point for all platform admin tools."""
    return render(request, 'core/tools_home.html', {})


# ─────────────────────────────────────────────────────────────────────────────
# 0b. QUESTION BANK LISTING
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_questions_list(request):
    """Read-only listing of all Question records ordered by question_id."""
    questions = Question.objects.all().order_by('question_id')
    return render(request, 'core/tools_questions_list.html', {
        'questions': questions,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 0c. QUESTION SET LISTING
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_sets_list(request):
    """Read-only listing of all QuestionSet records with their members."""
    sets = (
        QuestionSet.objects
        .all()
        .prefetch_related('members__question')
        .order_by('set_id')
    )
    return render(request, 'core/tools_sets_list.html', {
        'sets': sets,
    })


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


# ─────────────────────────────────────────────────────────────────────────────
# 4. REGIME CREATION WIZARD
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_create(request):
    """
    Regime creation wizard.
    Creates/finds a draft Case against META regime for the admin user,
    shows six steps as a GDS task list, each linking into Layer 2.
    Processors run automatically on confirmation of each step.
    """
    try:
        meta_regime = Regime.objects.get(regime_id='META')
    except Regime.DoesNotExist:
        return render(request, 'core/tools_create.html', {
            'error': 'META regime not found — run load_test_data first.'
        })

    # ── Find or create a draft case for this admin user ───────────────────────
    case = (
        Case.objects
        .filter(user=request.user, regime=meta_regime, status=Case.DRAFT)
        .order_by('-started_at')
        .first()
    )
    if not case:
        case = Case.objects.create(
            case_id=str(uuid.uuid4()),
            user=request.user,
            regime=meta_regime,
            status=Case.DRAFT,
        )

    # ── Bootstrap section statuses ────────────────────────────────────────────
    meta_sections = Section.objects.filter(
        regime=meta_regime, schedule__isnull=True
    ).order_by('display_order')

    bootstrap_section_statuses(request.user, meta_regime, meta_sections)

    statuses = {
        ss.section_id: ss.status
        for ss in SectionStatus.objects.filter(
            user=request.user, regime=meta_regime, section__in=meta_sections,
        )
    }

    # ── Build task list ───────────────────────────────────────────────────────
    steps = []
    for section in meta_sections:
        status = statuses.get(section.section_id, 'not_started')
        if section.section_type in (1, 2):
            action_url = f'/section/{section.section_id}/table/'
        else:
            action_url = f'/section/{section.section_id}/start/'

        if status == 'complete':
            link_label   = f'Amend — {section.section_name}'
            status_label = 'Completed'
            status_tag   = ''  # green by default
        elif status == 'in_progress':
            link_label   = section.section_name
            status_label = 'In progress'
            status_tag   = 'govuk-tag--blue'
        else:
            link_label   = section.section_name
            status_label = 'Not yet started'
            status_tag   = 'govuk-tag--grey'

        steps.append({
            'section':      section,
            'status':       status,
            'status_label': status_label,
            'status_tag':   status_tag,
            'link_label':   link_label,
            'action_url':   action_url,
        })

    REQUIRED_STEPS = {
        'META_ADD_REGIME',
        'META_ADD_SECTIONS',
        'META_ADD_ROUTING',
    }
    all_complete = all(
        statuses.get(sid) == 'complete'
        for sid in REQUIRED_STEPS
    )

    # Do NOT auto-submit the case here — submission is explicit
    # via the "Save new regime and exit" button (tools_create_save view).

    # ── Read target regime ID from META_ADD_REGIME answer ─────────────────────
    target_regime_id = ''
    try:
        meta_section = Section.objects.get(section_id='META_ADD_REGIME')
        ans = Answer.objects.get(
            user=request.user,
            case=case,
            section=meta_section,
            question_id='Q53',
        )
        target_regime_id = ans.answer.strip()
    except (Section.DoesNotExist, Answer.DoesNotExist):
        pass

    # ── Check whether a regime home file was generated for this regime ────────
    generated_file_path = None
    if target_regime_id:
        filename = f'{target_regime_id.lower()}_home.html'
        filepath = os.path.join(settings.BASE_DIR, '_generated', filename)
        if os.path.exists(filepath):
            generated_file_path = os.path.join('_generated', filename)

    # ── Set session so Layer 2 knows how to navigate ──────────────────────────
    update_session(request, {
        'user_id':         request.user.pk,
        'actor_id':        request.user.pk,
        'regime_id':       meta_regime.regime_id,
        'case_id':         case.case_id,
        'return_url':      '/tools/create/',
        'regime_home_url': '/tools/create/',
        'breadcrumbs': [
            {'label': 'Platform administration', 'url': '/tools/'},
            {'label': 'Create new regime',       'url': '/tools/create/'},
        ],
    })

    context = {
        'steps':                steps,
        'all_complete':         all_complete,
        'case_id':              case.case_id,
        'target_regime_id':     target_regime_id,
        'save_url':             '/tools/create/save/',
        'generated_file_path':  generated_file_path,
    }
    return render(request, 'core/tools_create.html', context)


@staff_required
def tools_create_save(request):
    """
    POST only. Saves and exits the creation wizard:
    - Marks the META case as SUBMITTED
    - Deletes Answer and AnswerTable records for this case
      (processors have already written to real tables)
    - Deletes SectionStatus records for this case
    - Redirects to /tools/
    """
    if request.method != 'POST':
        return redirect('/tools/create/')

    try:
        meta_regime = Regime.objects.get(regime_id='META')
    except Regime.DoesNotExist:
        return redirect('/tools/')

    case = (
        Case.objects
        .filter(user=request.user, regime=meta_regime, status=Case.DRAFT)
        .order_by('-started_at')
        .first()
    )
    if case:
        case.status = Case.SUBMITTED
        case.save()

        Answer.objects.filter(user=request.user, case=case).delete()
        AnswerTable.objects.filter(user=request.user, case=case).delete()

        SectionStatus.objects.filter(
            user=request.user,
            section__regime=meta_regime,
        ).delete()

    return redirect('/tools/')


@staff_required
def tools_create_abandon(request):
    """
    Discards the current draft and restarts the creation wizard.
    Lapses draft/submitted META cases, deletes their answers and
    section statuses, then redirects back to /tools/create/.
    """
    if request.method != 'POST':
        return redirect('/tools/create/')

    try:
        meta_regime = Regime.objects.get(regime_id='META')
    except Regime.DoesNotExist:
        return redirect('/tools/create/')

    cases = Case.objects.filter(
        user=request.user,
        regime=meta_regime,
        status__in=[Case.DRAFT, Case.SUBMITTED],
    )
    for case in cases:
        Answer.objects.filter(user=request.user, case=case).delete()
        AnswerTable.objects.filter(user=request.user, case=case).delete()
    cases.update(status=Case.LAPSED)

    SectionStatus.objects.filter(
        user=request.user,
        section__regime=meta_regime,
    ).delete()

    return redirect('/tools/create/')
