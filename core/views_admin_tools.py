"""
Admin Tools: Regime Configuration Viewer and Creation Wizard
=============================================================
Staff-only views for inspecting, editing, and creating regime configuration.

  /tools/                                         — staff landing page
  /tools/viewer/                                  — browse regimes / routing tables
  /tools/questions/                               — read-only question bank listing
  /tools/questions/add/                           — add a new question
  /tools/questions/edit/                          — picker: select question to edit
  /tools/sets/                                    — read-only question set listing
  /tools/sets/add/                                — add a new question set
  /tools/sets/edit/                               — picker: select set to edit
  /tools/question/<question_id>/edit/             — edit a single question
  /tools/set/<set_id>/edit/                       — edit a QuestionSet + members
  /tools/set/<set_id>/member/add/                 — add member to a set (POST)
  /tools/set/<set_id>/member/<qid>/remove/        — remove member from a set (POST)
  /tools/sections/                                — list all sections
  /tools/sections/create/                         — create a new section (step 1)
  /tools/create/                                  — regime creation wizard (task list)
  /tools/create/save/                             — save wizard and exit to /tools/
  /tools/create/abandon/                          — abandon current draft and restart
"""

import os
import uuid

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.db import models
from django.db.models import Count, F, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .interfaces import bootstrap_section_statuses, get_or_create_case
from .models import (
    Answer,
    AnswerTable,
    Case,
    Permission,
    Question,
    QuestionSet,
    QuestionSetMember,
    Regime,
    Routing,
    Schedule,
    Section,
    SectionStatus,
    User,
)
from .session import update_session

staff_required = user_passes_test(lambda u: u.is_staff)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING VALIDATOR
# ─────────────────────────────────────────────────────────────────────────────

def validate_section_routing(section):
    """Return {'valid': bool, 'issues': [str]} for a section's routing table."""
    from collections import defaultdict

    # Table sections (type 1) need no routing
    if section.section_type == 1:
        return {'valid': True, 'issues': []}

    rows = list(Routing.objects.filter(section=section).order_by('order_in_section'))

    # Check 1: no routing rows at all
    if not rows:
        return {'valid': False, 'issues': ['No routing rows defined.']}

    # Build node map: current_node → list of outgoing rows
    node_map = defaultdict(list)
    for row in rows:
        node_map[row.current_node].append(row)

    defined_nodes    = set(node_map.keys())
    referenced_nodes = {row.next_node for row in rows if row.next_node}

    issues = []

    # Check 2: dangling next_node references
    dangling = referenced_nodes - defined_nodes
    for node_id in sorted(dangling):
        issues.append(
            f'Node {node_id} is referenced as a destination but has no routing rows defined.'
        )

    # Check 3: unreachable nodes
    entry_node = rows[0].current_node
    reachable  = {entry_node} | referenced_nodes
    for node_id in sorted(defined_nodes - reachable):
        issues.append(
            f'Node {node_id} is defined but cannot be reached from the entry point.'
        )

    # Check 4: conditional-only branching nodes with no unconditional fallback
    for node_id, node_rows in node_map.items():
        has_conditional   = any(r.answer_value is not None for r in node_rows)
        has_unconditional = any(r.answer_value is None     for r in node_rows)
        if has_conditional and not has_unconditional:
            issues.append(
                f'Node {node_id} has conditional routes but no unconditional fallback — '
                f'answers not matching any condition will have no route.'
            )

    return {'valid': len(issues) == 0, 'issues': issues}


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


# ─────────────────────────────────────────────────────────────────────────────
# 0d. ADD QUESTION
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_question_add(request):
    """Form to create a new Question record."""
    errors = {}
    post = {}

    if request.method == 'POST':
        post = request.POST
        question_id   = post.get('question_id', '').strip()
        question_text = post.get('question_text', '').strip()
        question_type = post.get('question_type', '').strip()
        hint          = post.get('hint', '').strip() or None
        guidance      = post.get('guidance', '').strip() or None
        options       = post.get('options', '').strip() or None

        if not question_id:
            errors['question_id'] = 'Enter a question ID'
        elif Question.objects.filter(question_id=question_id).exists():
            errors['question_id'] = f'Question ID "{question_id}" already exists'

        if not question_text:
            errors['question_text'] = 'Enter the question text'

        if not question_type:
            errors['question_type'] = 'Select a question type'

        if not errors:
            Question.objects.create(
                question_id=question_id,
                question_text=question_text,
                question_type=question_type,
                hint=hint,
                guidance=guidance,
                options=options,
            )
            return redirect(f'/tools/questions/?added={question_id}')

    context = {
        'errors':                errors,
        'post':                  post,
        'question_type_choices': Question.QUESTION_TYPE_CHOICES,
    }
    return render(request, 'core/tools_question_add.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 0e. ADD QUESTION SET
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_set_add(request):
    """Form to create a new QuestionSet with member questions."""
    errors = {}
    post = {}
    all_questions = Question.objects.all().order_by('question_id')

    if request.method == 'POST':
        post = request.POST
        set_id    = post.get('set_id', '').strip()
        set_title = post.get('set_title', '').strip()
        set_hint  = post.get('set_hint', '').strip() or None

        if not set_id:
            errors['set_id'] = 'Enter a set ID'
        elif QuestionSet.objects.filter(set_id=set_id).exists():
            errors['set_id'] = f'Set ID "{set_id}" already exists'

        if not set_title:
            errors['set_title'] = 'Enter a title for this set'

        # Collect member rows
        members = []
        n = 0
        while True:
            q_id = post.get(f'members-{n}-question_id', '').strip()
            if not q_id:
                break
            order    = post.get(f'members-{n}-display_order', str((n + 1) * 10)).strip()
            required = post.get(f'members-{n}-required', '') == 'on'
            try:
                question = Question.objects.get(question_id=q_id)
            except Question.DoesNotExist:
                errors[f'members-{n}-question_id'] = f'Question "{q_id}" not found'
                question = None
            try:
                order_int = int(order)
            except ValueError:
                order_int = (n + 1) * 10
            members.append({
                'question':      question,
                'display_order': order_int,
                'required':      required,
                'n':             n,
            })
            n += 1

        if not members:
            errors['members'] = 'Add at least one member question'

        if not errors:
            qs = QuestionSet.objects.create(
                set_id=set_id,
                set_title=set_title,
                set_hint=set_hint,
            )
            for m in members:
                QuestionSetMember.objects.create(
                    question_set=qs,
                    question=m['question'],
                    display_order=m['display_order'],
                    required=m['required'],
                )
            return redirect(f'/tools/sets/?added={set_id}')

    context = {
        'errors':        errors,
        'post':          post,
        'all_questions': all_questions,
    }
    return render(request, 'core/tools_set_add.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 0f. EDIT QUESTION PICKER
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_questions_edit_picker(request):
    """List all questions so the user can pick one to edit."""
    questions = Question.objects.all().order_by('question_id')
    return render(request, 'core/tools_questions_edit_picker.html', {
        'questions': questions,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 0g. EDIT SET PICKER
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_sets_edit_picker(request):
    """List all question sets so the user can pick one to edit."""
    sets = (
        QuestionSet.objects
        .all()
        .prefetch_related('members__question')
        .order_by('set_id')
    )
    return render(request, 'core/tools_sets_edit_picker.html', {
        'sets': sets,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 0h. ADD MEMBER TO SET
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_set_member_add(request, set_id):
    """POST only. Adds a QuestionSetMember to an existing set."""
    if request.method != 'POST':
        return redirect(f'/tools/set/{set_id}/edit/')

    qs = get_object_or_404(QuestionSet, set_id=set_id)

    back          = request.POST.get('back', '')
    back_regime   = request.POST.get('back_regime', '')
    back_schedule = request.POST.get('back_schedule', '')
    back_section  = request.POST.get('back_section', '')
    edit_url      = f'/tools/set/{set_id}/edit/?back={back}&back_regime={back_regime}&back_schedule={back_schedule}&back_section={back_section}'

    question_id   = request.POST.get('question_id', '').strip()
    display_order = request.POST.get('display_order', '').strip()
    required      = request.POST.get('required', '') == 'on'

    try:
        question = Question.objects.get(question_id=question_id)
    except Question.DoesNotExist:
        return redirect(edit_url)

    already_member = qs.members.filter(question_id=question_id).exists()
    if already_member:
        return redirect(edit_url)

    try:
        order_int = int(display_order)
    except (ValueError, TypeError):
        max_order = qs.members.order_by('-display_order').values_list('display_order', flat=True).first()
        order_int = (max_order or 0) + 10

    QuestionSetMember.objects.create(
        question_set=qs,
        question=question,
        display_order=order_int,
        required=required,
    )
    return redirect(edit_url)


# ─────────────────────────────────────────────────────────────────────────────
# 0i. REMOVE MEMBER FROM SET
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_set_member_remove(request, set_id, question_id):
    """POST only. Removes a QuestionSetMember from a set."""
    if request.method != 'POST':
        return redirect(f'/tools/set/{set_id}/edit/')

    qs = get_object_or_404(QuestionSet, set_id=set_id)

    back          = request.POST.get('back', '')
    back_regime   = request.POST.get('back_regime', '')
    back_schedule = request.POST.get('back_schedule', '')
    back_section  = request.POST.get('back_section', '')
    edit_url      = f'/tools/set/{set_id}/edit/?back={back}&back_regime={back_regime}&back_schedule={back_schedule}&back_section={back_section}'

    QuestionSetMember.objects.filter(question_set=qs, question_id=question_id).delete()
    return redirect(edit_url)


# ─────────────────────────────────────────────────────────────────────────────
# 0j. SECTIONS LIST
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_sections_list(request):
    """List all sections with routing row counts."""
    sections = (
        Section.objects
        .annotate(routing_count=Count('routing_rules'))
        .select_related('regime', 'schedule')
        .order_by('section_id')
    )
    return render(request, 'core/tools_sections_list.html', {
        'sections':  sections,
        'added':     request.GET.get('added', ''),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 0l-bis. SCHEDULE VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_schedule_list(request):
    """List all schedules for the active department."""
    schedules = (
        Schedule.objects
        .filter(regime__dept_id=settings.ACTIVE_DEPT)
        .annotate(section_count=Count('sections', distinct=True))
        .select_related('regime')
        .order_by('regime__regime_id', 'display_order')
    )
    return render(request, 'core/tools_schedule_list.html', {
        'schedules': schedules,
        'added':     request.GET.get('added', ''),
    })


@staff_required
def tools_schedule_create(request):
    """Create a new schedule and redirect straight to section assignment."""
    regimes = Regime.objects.filter(dept_id=settings.ACTIVE_DEPT).order_by('regime_id')
    errors = {}
    post = {}

    if request.method == 'POST':
        post = request.POST
        schedule_name = post.get('schedule_name', '').strip()
        regime_id     = post.get('regime', '').strip()
        display_order = post.get('display_order', '0').strip()

        if not schedule_name:
            errors['schedule_name'] = 'Enter a schedule name'

        regime = None
        if not regime_id:
            errors['regime'] = 'Select a regime'
        else:
            try:
                regime = Regime.objects.get(regime_id=regime_id, dept_id=settings.ACTIVE_DEPT)
            except Regime.DoesNotExist:
                errors['regime'] = 'Select a valid regime'

        if not errors:
            # Auto-generate schedule_id: <regime_id>_SCH<N>
            prefix = f'{regime_id}_SCH'
            existing = (
                Schedule.objects
                .filter(schedule_id__istartswith=prefix)
                .values_list('schedule_id', flat=True)
            )
            nums = []
            for sid in existing:
                suffix = sid[len(prefix):]
                if suffix.isdigit():
                    nums.append(int(suffix))
            next_num = (max(nums) + 1) if nums else 1
            schedule_id = f'{prefix}{next_num}'

            try:
                display_order_int = int(display_order)
            except ValueError:
                display_order_int = 0

            Schedule.objects.create(
                schedule_id=schedule_id,
                schedule_name=schedule_name,
                regime=regime,
                display_order=display_order_int,
            )
            return redirect(f'/tools/schedules/{schedule_id}/sections/')

    context = {
        'regimes':      regimes,
        'errors':       errors,
        'post':         post,
        'active_dept':  settings.ACTIVE_DEPT,
    }
    return render(request, 'core/tools_schedule_create.html', context)


@staff_required
def tools_schedule_sections(request, schedule_id):
    """Manage sections assigned to a schedule."""
    schedule = get_object_or_404(
        Schedule.objects.select_related('regime'),
        schedule_id=schedule_id,
    )
    members = (
        Section.objects
        .filter(schedule=schedule)
        .annotate(routing_count=Count('routing_rules'))
        .order_by('display_order', 'section_id')
    )
    available = (
        Section.objects
        .filter(regime=schedule.regime, schedule__isnull=True)
        .order_by('section_id')
    )
    max_order = members.aggregate(m=Max('display_order'))['m'] or 0
    next_order = max_order + 10

    routing_warning_id   = request.GET.get('routing_warning', '')
    routing_warning_name = ''
    if routing_warning_id:
        try:
            routing_warning_name = Section.objects.get(section_id=routing_warning_id).section_name
        except Section.DoesNotExist:
            pass

    context = {
        'schedule':             schedule,
        'members':              members,
        'available':            available,
        'next_order':           next_order,
        'routing_warning_id':   routing_warning_id,
        'routing_warning_name': routing_warning_name,
    }
    return render(request, 'core/tools_schedule_sections.html', context)


@staff_required
def tools_schedule_section_add(request, schedule_id):
    """POST: assign a section to this schedule."""
    if request.method != 'POST':
        return redirect(f'/tools/schedules/{schedule_id}/sections/')
    schedule = get_object_or_404(Schedule.objects.select_related('regime'), schedule_id=schedule_id)
    section_id    = request.POST.get('section_id', '').strip()
    display_order = request.POST.get('display_order', '0').strip()
    try:
        section = Section.objects.get(section_id=section_id)
    except Section.DoesNotExist:
        return redirect(f'/tools/schedules/{schedule_id}/sections/')
    try:
        order_int = int(display_order)
    except ValueError:
        order_int = 0
    section.schedule      = schedule
    section.regime        = None
    section.display_order = order_int
    section.save()
    result = validate_section_routing(section)
    if not result['valid']:
        return redirect(f'/tools/schedules/{schedule_id}/sections/?routing_warning={section_id}')
    return redirect(f'/tools/schedules/{schedule_id}/sections/')


@staff_required
def tools_schedule_section_remove(request, schedule_id):
    """POST: return a section to direct regime ownership."""
    if request.method != 'POST':
        return redirect(f'/tools/schedules/{schedule_id}/sections/')
    schedule = get_object_or_404(Schedule.objects.select_related('regime'), schedule_id=schedule_id)
    section_id = request.POST.get('section_id', '').strip()
    try:
        section = Section.objects.get(section_id=section_id, schedule=schedule)
    except Section.DoesNotExist:
        return redirect(f'/tools/schedules/{schedule_id}/sections/')
    section.schedule = None
    section.regime   = schedule.regime
    section.save()
    return redirect(f'/tools/schedules/{schedule_id}/sections/')


@staff_required
def tools_schedule_section_reorder(request, schedule_id):
    """POST: swap display_order with adjacent section (up or down)."""
    if request.method != 'POST':
        return redirect(f'/tools/schedules/{schedule_id}/sections/')
    schedule  = get_object_or_404(Schedule, schedule_id=schedule_id)
    section_id = request.POST.get('section_id', '').strip()
    direction  = request.POST.get('direction', '').strip()
    try:
        section = Section.objects.get(section_id=section_id, schedule=schedule)
    except Section.DoesNotExist:
        return redirect(f'/tools/schedules/{schedule_id}/sections/')

    members = list(
        Section.objects
        .filter(schedule=schedule)
        .order_by('display_order', 'section_id')
    )
    idx = next((i for i, s in enumerate(members) if s.section_id == section_id), None)
    if idx is None:
        return redirect(f'/tools/schedules/{schedule_id}/sections/')

    if direction == 'up' and idx > 0:
        neighbour = members[idx - 1]
    elif direction == 'down' and idx < len(members) - 1:
        neighbour = members[idx + 1]
    else:
        return redirect(f'/tools/schedules/{schedule_id}/sections/')

    # Swap display_order values
    section.display_order, neighbour.display_order = neighbour.display_order, section.display_order
    # If equal, force a gap
    if section.display_order == neighbour.display_order:
        if direction == 'up':
            section.display_order -= 1
        else:
            section.display_order += 1
    section.save()
    neighbour.save()
    return redirect(f'/tools/schedules/{schedule_id}/sections/')


# ─────────────────────────────────────────────────────────────────────────────
# 0p. NAVIGATION PATTERN WIZARD
# ─────────────────────────────────────────────────────────────────────────────

def _infer_pattern(direct_count, schedule_count):
    """Return a short label describing the current navigation structure."""
    if direct_count == 0 and schedule_count == 0:
        return 'Not configured'
    if schedule_count > 0:
        return 'Pattern C (schedule menu)'
    if direct_count == 1:
        return 'Pattern A (single section)'
    return 'Pattern B (section menu)'


@staff_required
def tools_navigation(request):
    """Landing page: list regimes with their inferred navigation pattern."""
    regimes = (
        Regime.objects
        .filter(dept_id=settings.ACTIVE_DEPT)
        .annotate(
            direct_count=Count('direct_sections', distinct=True),
            schedule_count=Count('schedules', distinct=True),
        )
        .order_by('regime_id')
    )
    rows = []
    for r in regimes:
        rows.append({
            'regime':   r,
            'pattern':  _infer_pattern(r.direct_count, r.schedule_count),
        })
    confirmed_id = request.GET.get('confirmed', '')
    confirmed_name = ''
    if confirmed_id:
        try:
            confirmed_name = Regime.objects.get(regime_id=confirmed_id).regime_name
        except Regime.DoesNotExist:
            pass
    return render(request, 'core/tools_navigation.html', {
        'rows':           rows,
        'confirmed_id':   confirmed_id,
        'confirmed_name': confirmed_name,
    })


@staff_required
def tools_navigation_regime(request, regime_id):
    """Three-step wizard (session-backed) for choosing and confirming a navigation pattern."""
    regime = get_object_or_404(Regime, regime_id=regime_id, dept_id=settings.ACTIVE_DEPT)

    # Session keys namespaced per regime so multiple regimes don't collide
    sk_step    = f'nav_{regime_id}_step'
    sk_pattern = f'nav_{regime_id}_pattern'

    # ── Helper: gather structure counts ──────────────────────────────────────
    direct_sections = list(
        Section.objects
        .filter(regime=regime, schedule__isnull=True)
        .order_by('display_order', 'section_id')
    )
    schedules = list(
        Schedule.objects
        .filter(regime=regime)
        .order_by('display_order', 'schedule_id')
    )
    direct_count   = len(direct_sections)
    schedule_count = len(schedules)

    errors = {}

    if request.method == 'POST':
        action = request.POST.get('action', '')

        # ── Step 1 POST — choose pattern ─────────────────────────────────────
        if action == 'choose_pattern':
            chosen = request.POST.get('pattern', '').strip()
            if not chosen:
                errors['pattern'] = 'Select a pattern'
            elif chosen == 'A':
                if direct_count != 1 or schedule_count != 0:
                    errors['pattern'] = (
                        f'Pattern A requires exactly one section and no schedules. '
                        f'This regime has {direct_count} direct section'
                        f'{"s" if direct_count != 1 else ""} and '
                        f'{schedule_count} schedule{"s" if schedule_count != 1 else ""}.'
                    )
            elif chosen == 'B':
                if schedule_count > 0:
                    errors['pattern'] = (
                        'Pattern B requires no schedules. '
                        'Remove schedules first or choose Pattern C.'
                    )
            elif chosen == 'C':
                orphaned = Section.objects.filter(regime=regime, schedule__isnull=True).count()
                if orphaned > 0:
                    errors['pattern'] = (
                        f'Pattern C requires all sections to be in a schedule. '
                        f'{orphaned} section{"s are" if orphaned != 1 else " is"} '
                        f'not assigned to any schedule.'
                    )
            else:
                errors['pattern'] = 'Select a valid pattern'

            if not errors:
                request.session[sk_pattern] = chosen
                # Pattern A has nothing to order — skip straight to step 3
                request.session[sk_step] = 3 if chosen == 'A' else 2
                return redirect('core:tools_navigation_regime', regime_id=regime_id)

        # ── Step 2 POST — reorder ─────────────────────────────────────────────
        elif action == 'reorder':
            chosen  = request.session.get(sk_pattern, '')
            obj_id  = request.POST.get('obj_id', '').strip()
            direction = request.POST.get('direction', '').strip()

            if chosen == 'C':
                objs = list(
                    Schedule.objects
                    .filter(regime=regime)
                    .order_by('display_order', 'schedule_id')
                )
                try:
                    target = Schedule.objects.get(schedule_id=obj_id, regime=regime)
                except Schedule.DoesNotExist:
                    target = None
            else:
                objs = list(
                    Section.objects
                    .filter(regime=regime, schedule__isnull=True)
                    .order_by('display_order', 'section_id')
                )
                try:
                    target = Section.objects.get(section_id=obj_id, regime=regime, schedule__isnull=True)
                except Section.DoesNotExist:
                    target = None

            if target is not None:
                idx = next((i for i, o in enumerate(objs)
                            if (o.schedule_id if chosen == 'C' else o.section_id) == obj_id), None)
                if idx is not None:
                    if direction == 'up' and idx > 0:
                        neighbour = objs[idx - 1]
                    elif direction == 'down' and idx < len(objs) - 1:
                        neighbour = objs[idx + 1]
                    else:
                        neighbour = None
                    if neighbour is not None:
                        target.display_order, neighbour.display_order = (
                            neighbour.display_order, target.display_order
                        )
                        if target.display_order == neighbour.display_order:
                            if direction == 'up':
                                target.display_order -= 1
                            else:
                                target.display_order += 1
                        target.save()
                        neighbour.save()
            return redirect('core:tools_navigation_regime', regime_id=regime_id)

        elif action == 'confirm_order':
            request.session[sk_step] = 3
            return redirect('core:tools_navigation_regime', regime_id=regime_id)

        elif action == 'save':
            # Clear wizard session keys and redirect to landing with success banner
            request.session.pop(sk_step, None)
            request.session.pop(sk_pattern, None)
            return redirect(f'/tools/navigation/?confirmed={regime_id}')

        elif action == 'back_to_step2':
            request.session[sk_step] = 2
            return redirect('core:tools_navigation_regime', regime_id=regime_id)

    # ── GET: determine which step to render ───────────────────────────────────
    step           = request.session.get(sk_step, 1)
    chosen_pattern = request.session.get(sk_pattern, '')

    # Refresh lists after any reorder
    if chosen_pattern == 'C':
        order_items = list(
            Schedule.objects
            .filter(regime=regime)
            .order_by('display_order', 'schedule_id')
        )
    else:
        order_items = list(
            Section.objects
            .filter(regime=regime, schedule__isnull=True)
            .order_by('display_order', 'section_id')
        )

    # Step 3: validate routing across all sections in this regime
    section_validations = {}
    any_invalid = False
    if step == 3:
        from django.db.models import Q as DQ
        all_sections = Section.objects.filter(
            DQ(regime=regime) | DQ(schedule__regime=regime)
        ).order_by('section_id')
        for s in all_sections:
            result = validate_section_routing(s)
            section_validations[s.section_id] = result
            if not result['valid']:
                any_invalid = True

    context = {
        'regime':              regime,
        'step':                step,
        'chosen_pattern':      chosen_pattern,
        'direct_sections':     direct_sections,
        'schedules':           schedules,
        'direct_count':        direct_count,
        'schedule_count':      schedule_count,
        'current_pattern':     _infer_pattern(direct_count, schedule_count),
        'order_items':         order_items,
        'errors':              errors,
        'section_validations': section_validations,
        'any_invalid':         any_invalid,
    }
    return render(request, 'core/tools_navigation_regime.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 0l. REGIME LIST
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_regime_list(request):
    """List regimes for the active department."""
    regimes = (
        Regime.objects
        .filter(dept_id=settings.ACTIVE_DEPT)
        .annotate(
            section_count=Count('direct_sections', distinct=True),
            schedule_count=Count('schedules', distinct=True),
        )
        .order_by('regime_id')
    )
    return render(request, 'core/tools_regime_list.html', {
        'regimes': regimes,
        'added':   request.GET.get('added', ''),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 0m. REGIME CREATE
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_regime_create(request):
    """Create a new regime shell for the active department."""
    errors = {}
    post = {}

    if request.method == 'POST':
        post = request.POST
        regime_code = post.get('regime_code', '').strip().upper()
        regime_name = post.get('regime_name', '').strip()

        if not regime_code:
            errors['regime_code'] = 'Enter a regime code'
        elif not regime_code.isalpha():
            errors['regime_code'] = 'Regime code must be uppercase letters only, e.g. IHT'

        generated_id = f'{settings.ACTIVE_DEPT}_{regime_code}' if regime_code else ''

        if not errors.get('regime_code') and generated_id:
            if Regime.objects.filter(regime_id=generated_id).exists():
                errors['regime_code'] = f'Regime ID {generated_id} already exists'

        if not regime_name:
            errors['regime_name'] = 'Enter a regime name'

        if not errors:
            regime = Regime.objects.create(
                regime_id=generated_id,
                regime_name=regime_name,
                dept_id=settings.ACTIVE_DEPT,
                display_order=0,
            )
            # Auto-grant to all non-actor users
            actor_ids = (
                Permission.objects
                .exclude(actor_id=F('user_id'))
                .values_list('actor_id', flat=True)
                .distinct()
            )
            for u in User.objects.exclude(pk__in=actor_ids):
                Permission.objects.get_or_create(
                    actor=u, user=u, regime=regime, section=None,
                    defaults={'can_delegate': False, 'granted_by': None},
                )
            return redirect(f'/tools/regimes/?added={generated_id}')

    context = {
        'errors':      errors,
        'post':        post,
        'active_dept': settings.ACTIVE_DEPT,
    }
    return render(request, 'core/tools_regime_create.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 0k. SECTION CREATE (step 1 — fields form)
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_section_create(request):
    """Create a new Section record (fields only; routing is Chunk 6).

    Supports ?copy_from=<section_id> on GET to pre-fill fields from an
    existing section.  The source section's Routing rows are copied verbatim
    to the new section after creation.
    """
    regimes = (
        Regime.objects
        .filter(dept_id=settings.ACTIVE_DEPT)
        .order_by('regime_id')
    )
    errors = {}
    post = {}
    copy_source = None

    if request.method == 'POST':
        post = request.POST
        copy_from_id        = post.get('copy_from', '').strip()
        section_name        = post.get('section_name', '').strip()
        section_type        = post.get('section_type', '0').strip()
        display_order       = post.get('display_order', '0').strip()
        regime_id           = post.get('regime', '').strip()
        section_guidance    = post.get('section_guidance', '').strip() or None
        column_question_ids = post.get('column_question_ids', '').strip() or None
        totals_question_ids = post.get('totals_question_ids', '').strip() or None

        if not section_name:
            errors['section_name'] = 'Enter a section name'

        regime = None
        if not regime_id:
            errors['regime'] = 'Select a regime'
        else:
            try:
                regime = Regime.objects.get(regime_id=regime_id)
            except Regime.DoesNotExist:
                errors['regime'] = 'Select a valid regime'

        if not errors:
            # Auto-generate section_id: <regime_id>_S<N>
            prefix = f'{regime_id}_S'
            existing = (
                Section.objects
                .filter(section_id__istartswith=prefix)
                .values_list('section_id', flat=True)
            )
            nums = []
            for sid in existing:
                suffix = sid[len(prefix):]
                if suffix.isdigit():
                    nums.append(int(suffix))
            next_num = (max(nums) + 1) if nums else 1
            section_id = f'{prefix}{next_num}'

            try:
                section_type_int  = int(section_type)
            except ValueError:
                section_type_int = 0
            try:
                display_order_int = int(display_order)
            except ValueError:
                display_order_int = 0

            new_section = Section.objects.create(
                section_id=section_id,
                section_name=section_name,
                section_type=section_type_int,
                display_order=display_order_int,
                regime=regime,
                schedule=None,
                section_guidance=section_guidance,
                column_question_ids=column_question_ids,
                totals_question_ids=totals_question_ids,
                copied_from=copy_from_id or None,
            )

            # Copy routing rows from the source section if requested
            if copy_from_id:
                source_rows = (
                    Routing.objects
                    .filter(section_id=copy_from_id)
                    .order_by('order_in_section')
                )
                Routing.objects.bulk_create([
                    Routing(
                        section=new_section,
                        current_node=r.current_node,
                        answer_value=r.answer_value,
                        next_node=r.next_node,
                        order_in_section=r.order_in_section,
                    )
                    for r in source_rows
                ])

            if section_type_int == 1:
                # Table (no routing) → back to list with success banner
                return redirect(f'/tools/sections/?added={section_id}')
            else:
                # Standard (0) or Table with routing (2) → routing editor
                return redirect(f'/tools/sections/{section_id}/routing/')

    else:
        # GET — check for copy_from param
        copy_from_id = request.GET.get('copy_from', '').strip()
        if copy_from_id:
            try:
                copy_source = Section.objects.get(section_id=copy_from_id)
                post = {
                    'section_name':        copy_source.section_name,
                    'section_type':        str(copy_source.section_type),
                    'display_order':       str(copy_source.display_order),
                    'section_guidance':    copy_source.section_guidance or '',
                    'column_question_ids': copy_source.column_question_ids or '',
                    'totals_question_ids': copy_source.totals_question_ids or '',
                    'copy_from':           copy_from_id,
                }
            except Section.DoesNotExist:
                copy_from_id = ''

    context = {
        'regimes':               regimes,
        'has_regimes':           regimes.exists(),
        'section_type_choices':  Section.SECTION_TYPE_CHOICES,
        'errors':                errors,
        'post':                  post,
        'active_dept':           settings.ACTIVE_DEPT,
        'copy_source':           copy_source,
    }
    return render(request, 'core/tools_section_create.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 0n. SECTION COPY PICKER
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_section_copy_picker(request):
    """List all sections so the admin can pick one to copy."""
    sections = (
        Section.objects
        .annotate(routing_count=Count('routing_rules'))
        .select_related('regime', 'schedule')
        .order_by('section_id')
    )
    return render(request, 'core/tools_section_copy_picker.html', {
        'sections': sections,
    })


# ─────────────────────────────────────────────────────────────────────────────
# CHUNK 6 — SECTION ROUTING EDITOR
# ─────────────────────────────────────────────────────────────────────────────

# ── Routing helper functions ──────────────────────────────────────────────────

def _reachable_from(outgoing, start_node):
    """
    BFS: return the set of all node IDs reachable from start_node via the
    outgoing map {node_id: [next_node, ...]}.  start_node itself is included.
    None values (END) are never added to the set.
    """
    visited = set()
    queue = [start_node]
    while queue:
        node = queue.pop()
        if node is None or node in visited:
            continue
        visited.add(node)
        for nxt in outgoing.get(node, []):
            if nxt is not None and nxt not in visited:
                queue.append(nxt)
    return visited


def _node_first_order(rows):
    """
    Return a list of distinct current_node values in the order they first
    appear when rows are sorted by order_in_section.
    """
    seen = []
    seen_set = set()
    for row in sorted(rows, key=lambda r: r.order_in_section):
        if row.current_node not in seen_set:
            seen.append(row.current_node)
            seen_set.add(row.current_node)
    return seen


def _build_outgoing(rows):
    """
    Build outgoing map: {node_id: [next_node, ...]} — one entry per routing row.
    The lists preserve the order rows appear (by order_in_section).
    """
    outgoing = {}
    for row in sorted(rows, key=lambda r: r.order_in_section):
        outgoing.setdefault(row.current_node, [])
        outgoing[row.current_node].append(row.next_node)
    return outgoing


def build_routing_tree(section):
    """
    Build and return an ordered list of display-node dicts for the routing
    tree of *section*.

    Algorithm
    ---------
    Pre-compute:
      • rows        – all Routing rows sorted by order_in_section
      • outgoing    – {node_id: [next_node, ...]}  (multiple entries = branching)
      • row_map     – {(current_node, answer_value): Routing row}
      • node_order  – distinct current_nodes in first-appearance order

    The recursive helper _emit(node_id, indent, excluded):
      1. If node_id is None, already visited, or in excluded → emit END / return.
      2. Mark node_id as visited; look up its outgoing edges.
      3. Non-branching (one edge): emit question node, recurse at same indent.
      4. Branching (>1 edge):
         a. For each condition row (in section order):
            • branch_only_i = reachable(next_i) - reachable(every other next)
            • emit 'condition' node at indent+1
            • recurse into branch_only_i at indent+2, excluded = all other
              branches' reachable sets ∪ outer excluded
         b. Find convergence = first node in node_order that is in
            intersection(reachable(all nexts)) and not yet visited.
         c. Continue from convergence at same indent.

    Display node dict keys
    ----------------------
    type, node_id, label, indent, is_branching, conditions, answer_value,
    next_node, routing_row_id, condition_empty
    """
    rows = list(
        Routing.objects.filter(section=section).order_by('order_in_section')
    )

    if not rows:
        return [{'type': 'end', 'node_id': None, 'label': 'END', 'indent': 0,
                 'is_branching': False, 'conditions': [], 'answer_value': None,
                 'next_node': None, 'routing_row_id': None, 'condition_empty': False}]

    outgoing = _build_outgoing(rows)
    node_order = _node_first_order(rows)

    # Build label lookup for questions and sets
    all_node_ids = set(r.current_node for r in rows)
    q_labels = {
        q.question_id: q.question_text
        for q in Question.objects.filter(question_id__in=all_node_ids)
    }
    s_labels = {
        qs.set_id: qs.set_title
        for qs in QuestionSet.objects.filter(set_id__in=all_node_ids)
    }

    def node_label(node_id):
        text = q_labels.get(node_id) or s_labels.get(node_id) or ''
        return f'{node_id}  {text}' if text else node_id

    # row_map: (current_node, answer_value) → Routing row
    row_map = {}
    for row in rows:
        row_map[(row.current_node, row.answer_value)] = row

    visited = set()
    result = []

    def _emit(node_id, indent, excluded):
        if node_id is None:
            result.append({
                'type': 'end', 'node_id': None, 'label': 'END', 'indent': indent,
                'is_branching': False, 'conditions': [], 'answer_value': None,
                'next_node': None, 'routing_row_id': None, 'condition_empty': False,
            })
            return

        if node_id in visited or node_id in excluded:
            return

        visited.add(node_id)

        nexts = outgoing.get(node_id, [])   # list of next_node values (one per row)

        if len(nexts) <= 1:
            # Non-branching
            next_node = nexts[0] if nexts else None
            row = row_map.get((node_id, None)) or row_map.get((node_id, nexts[0] if nexts else None))
            # Find the actual routing row for this node (unconditional)
            actual_row = None
            for row in rows:
                if row.current_node == node_id:
                    actual_row = row
                    break
            result.append({
                'type': 'question',
                'node_id': node_id,
                'label': node_label(node_id),
                'indent': indent,
                'is_branching': False,
                'conditions': [],
                'answer_value': None,
                'next_node': next_node,
                'routing_row_id': actual_row.pk if actual_row else None,
                'condition_empty': False,
            })
            _emit(next_node, indent, excluded)
        else:
            # Branching: collect condition rows in section order
            cond_rows = sorted(
                [r for r in rows if r.current_node == node_id],
                key=lambda r: r.order_in_section,
            )
            conditions_labels = [r.answer_value for r in cond_rows]

            # Reachability for each branch
            branch_reachable = [_reachable_from(outgoing, r.next_node) for r in cond_rows]

            # Convergence = first node in node_order that is in ALL branches'
            # reachable sets and not yet visited
            if branch_reachable:
                common = branch_reachable[0].copy()
                for br in branch_reachable[1:]:
                    common &= br
            else:
                common = set()
            convergence = None
            for nid in node_order:
                if nid in common and nid not in visited and nid != node_id:
                    convergence = nid
                    break

            # First routing row for this node (for routing_row_id)
            first_row = cond_rows[0] if cond_rows else None

            result.append({
                'type': 'question',
                'node_id': node_id,
                'label': node_label(node_id),
                'indent': indent,
                'is_branching': True,
                'conditions': conditions_labels,
                'answer_value': None,
                'next_node': None,
                'routing_row_id': first_row.pk if first_row else None,
                'condition_empty': False,
            })

            for i, cond_row in enumerate(cond_rows):
                branch_next = cond_row.next_node
                # branch_only = nodes reachable from this branch's start but
                # NOT reachable from any other branch's start
                other_reachable = set()
                for j, br in enumerate(branch_reachable):
                    if j != i:
                        other_reachable |= br
                branch_only = branch_reachable[i] - other_reachable
                # Also exclude convergence from branch_only
                if convergence:
                    branch_only.discard(convergence)

                branch_has_nodes = bool(branch_only - visited)

                result.append({
                    'type': 'condition',
                    'node_id': node_id,
                    'label': cond_row.answer_value or '(unconditional)',
                    'indent': indent + 1,
                    'is_branching': False,
                    'conditions': [],
                    'answer_value': cond_row.answer_value,
                    'next_node': branch_next,
                    'routing_row_id': cond_row.pk,
                    'condition_empty': not branch_has_nodes,
                })

                # Emit branch-only nodes at indent+2
                new_excluded = excluded | (other_reachable - branch_only)
                if convergence:
                    new_excluded.add(convergence)
                _emit(branch_next, indent + 2, new_excluded)

            # Continue from convergence at same indent
            if convergence:
                _emit(convergence, indent, excluded)
            else:
                # All branches end (next_node=None) — emit END
                result.append({
                    'type': 'end', 'node_id': None, 'label': 'END', 'indent': indent,
                    'is_branching': False, 'conditions': [], 'answer_value': None,
                    'next_node': None, 'routing_row_id': None, 'condition_empty': False,
                })

    # Find entry node = first in node_order that is never a next_node of another
    # (i.e. it has no predecessor inside this section)
    all_nexts = set(r.next_node for r in rows if r.next_node is not None)
    entry = None
    for nid in node_order:
        if nid not in all_nexts:
            entry = nid
            break
    if entry is None:
        entry = node_order[0] if node_order else None

    _emit(entry, 0, set())

    # If nothing emitted an END at the top level, add one
    if not result or result[-1]['type'] != 'end':
        result.append({
            'type': 'end', 'node_id': None, 'label': 'END', 'indent': 0,
            'is_branching': False, 'conditions': [], 'answer_value': None,
            'next_node': None, 'routing_row_id': None, 'condition_empty': False,
        })

    return result


def _renumber_routing(section):
    """
    Reassign order_in_section as 10, 20, 30, ... using the same traversal
    order as build_routing_tree, so that re-running build_routing_tree after
    renumbering produces an identical tree.

    We walk the tree and collect (current_node, answer_value) tuples in
    display order, then update the corresponding Routing rows.
    """
    rows = list(
        Routing.objects.filter(section=section).order_by('order_in_section')
    )
    if not rows:
        return

    outgoing = _build_outgoing(rows)
    node_order = _node_first_order(rows)

    # Find entry node (no predecessor)
    all_nexts = set(r.next_node for r in rows if r.next_node is not None)
    entry = None
    for nid in node_order:
        if nid not in all_nexts:
            entry = nid
            break
    if entry is None:
        entry = node_order[0] if node_order else None

    ordered_keys = []   # list of (current_node, answer_value) in traversal order
    visited = set()

    def _walk(node_id, excluded):
        if node_id is None or node_id in visited or node_id in excluded:
            return
        visited.add(node_id)
        nexts = outgoing.get(node_id, [])
        node_rows = sorted(
            [r for r in rows if r.current_node == node_id],
            key=lambda r: r.order_in_section,
        )
        for r in node_rows:
            ordered_keys.append((r.current_node, r.answer_value))

        if len(nexts) <= 1:
            next_node = nexts[0] if nexts else None
            _walk(next_node, excluded)
        else:
            cond_rows = node_rows  # already sorted
            branch_reachable = [_reachable_from(outgoing, r.next_node) for r in cond_rows]

            if branch_reachable:
                common = branch_reachable[0].copy()
                for br in branch_reachable[1:]:
                    common &= br
            else:
                common = set()
            convergence = None
            for nid in node_order:
                if nid in common and nid not in visited and nid != node_id:
                    convergence = nid
                    break

            for i, cond_row in enumerate(cond_rows):
                branch_next = cond_row.next_node
                other_reachable = set()
                for j, br in enumerate(branch_reachable):
                    if j != i:
                        other_reachable |= br
                branch_only = branch_reachable[i] - other_reachable
                if convergence:
                    branch_only.discard(convergence)

                new_excluded = excluded | (other_reachable - branch_only)
                if convergence:
                    new_excluded.add(convergence)
                _walk(branch_next, new_excluded)

            if convergence:
                _walk(convergence, excluded)

    _walk(entry, set())

    # Build a row lookup by (current_node, answer_value)
    row_lookup = {(r.current_node, r.answer_value): r for r in rows}

    new_order = 10
    updated = []
    seen_keys = set()
    for key in ordered_keys:
        if key in seen_keys:
            continue
        seen_keys.add(key)
        row = row_lookup.get(key)
        if row:
            row.order_in_section = new_order
            updated.append(row)
            new_order += 10

    if updated:
        Routing.objects.bulk_update(updated, ['order_in_section'])


# ── View: section routing display ─────────────────────────────────────────────

@staff_required
def tools_section_routing(request, section_id):
    """Display the routing tree for a section with action menus."""
    section = get_object_or_404(Section, section_id=section_id)
    tree = build_routing_tree(section)

    existing_node_ids = set(
        Routing.objects.filter(section=section)
        .values_list('current_node', flat=True)
        .distinct()
    )

    # Build available_nodes from all Questions + QuestionSets not already in routing
    questions = Question.objects.exclude(question_id__in=existing_node_ids).order_by('question_id')
    sets = QuestionSet.objects.exclude(set_id__in=existing_node_ids).order_by('set_id')

    available_nodes = (
        [{'id': q.question_id, 'label': f'{q.question_id}  {q.question_text}'} for q in questions]
        + [{'id': s.set_id, 'label': f'{s.set_id}  {s.set_title}'} for s in sets]
    )

    return render(request, 'core/tools_section_routing.html', {
        'section':            section,
        'tree':               tree,
        'available_nodes':    available_nodes,
        'routing_validation': validate_section_routing(section),
    })


# ── Routing redirect helper ───────────────────────────────────────────────────

def _routing_redirect(section_id):
    """Redirect to the routing editor for the given section."""
    return redirect(f'/tools/sections/{section_id}/routing/')


# ── View: insert node ─────────────────────────────────────────────────────────

@staff_required
def tools_routing_insert(request, section_id):
    """GET: show insert form. POST: create new routing row(s)."""
    section = get_object_or_404(Section, section_id=section_id)

    if request.method == 'POST':
        position            = request.POST.get('position', '').strip()
        anchor_node         = request.POST.get('anchor_node', '').strip()
        anchor_answer_value = request.POST.get('anchor_answer_value', '').strip() or None
        node_type           = request.POST.get('node_type', 'question').strip()
        new_node_id         = request.POST.get('node_id', '').strip()
        new_answer_value    = request.POST.get('answer_value', '').strip() or None

        # Validate node exists and is not already in this section's routing
        if not new_node_id:
            return _routing_redirect(section_id)
        if node_type == 'question':
            if not Question.objects.filter(question_id=new_node_id).exists():
                return _routing_redirect(section_id)
        else:
            if not QuestionSet.objects.filter(set_id=new_node_id).exists():
                return _routing_redirect(section_id)
        if Routing.objects.filter(section=section, current_node=new_node_id).exists():
            return _routing_redirect(section_id)

        max_order = (
            Routing.objects.filter(section=section)
            .order_by('-order_in_section')
            .values_list('order_in_section', flat=True)
            .first()
        ) or 0

        if position == 'first':
            Routing.objects.create(
                section=section,
                current_node=new_node_id,
                answer_value=None,
                next_node=None,
                order_in_section=10,
            )

        elif position == 'before' and anchor_node:
            # All rows pointing to anchor_node → new_node_id
            Routing.objects.filter(section=section, next_node=anchor_node).update(
                next_node=new_node_id
            )
            Routing.objects.create(
                section=section,
                current_node=new_node_id,
                answer_value=new_answer_value,
                next_node=anchor_node,
                order_in_section=max_order + 10,
            )

        elif position == 'after' and anchor_node:
            if anchor_answer_value is not None:
                # Branch insert: find the specific condition row and splice in
                try:
                    cond_row = Routing.objects.get(
                        section=section,
                        current_node=anchor_node,
                        answer_value=anchor_answer_value,
                    )
                except Routing.DoesNotExist:
                    return _routing_redirect(section_id)
                z = cond_row.next_node
                cond_row.next_node = new_node_id
                cond_row.save()
            else:
                # Simple linear after: anchor has one unconditional row
                anchor_row = (
                    Routing.objects
                    .filter(section=section, current_node=anchor_node, answer_value__isnull=True)
                    .first()
                )
                if anchor_row is None:
                    return _routing_redirect(section_id)
                z = anchor_row.next_node
                anchor_row.next_node = new_node_id
                anchor_row.save()
            Routing.objects.create(
                section=section,
                current_node=new_node_id,
                answer_value=new_answer_value,
                next_node=z,
                order_in_section=max_order + 10,
            )

        _renumber_routing(section)
        return _routing_redirect(section_id)

    # GET — build the form
    position            = request.GET.get('position', 'first')
    anchor_node         = request.GET.get('anchor_node', '')
    anchor_answer_value = request.GET.get('anchor_answer_value', '')

    existing_node_ids = set(
        Routing.objects.filter(section=section)
        .values_list('current_node', flat=True)
        .distinct()
    )
    questions = Question.objects.exclude(question_id__in=existing_node_ids).order_by('question_id')
    sets      = QuestionSet.objects.exclude(set_id__in=existing_node_ids).order_by('set_id')

    return render(request, 'core/tools_routing_insert.html', {
        'section':             section,
        'position':            position,
        'anchor_node':         anchor_node,
        'anchor_answer_value': anchor_answer_value,
        'questions':           questions,
        'sets':                sets,
    })


# ── View: delete node ─────────────────────────────────────────────────────────

@staff_required
def tools_routing_delete(request, section_id):
    """POST only. Delete a node and its downstream routing."""
    if request.method != 'POST':
        return redirect(f'/tools/sections/{section_id}/routing/')

    section = get_object_or_404(Section, section_id=section_id)
    routing_url = f'/tools/sections/{section_id}/routing/'

    node_id     = request.POST.get('node_id', '').strip()
    delete_mode = request.POST.get('delete_mode', 'promote')

    if not node_id:
        return redirect(routing_url)

    rows = list(Routing.objects.filter(section=section).order_by('order_in_section'))
    outgoing = _build_outgoing(rows)
    node_order = _node_first_order(rows)

    if delete_mode == 'delete_all':
        reachable_from_node = _reachable_from(outgoing, node_id)

        # Find entry node
        all_nexts = set(r.next_node for r in rows if r.next_node is not None)
        entry = None
        for nid in node_order:
            if nid not in all_nexts:
                entry = nid
                break
        if entry is None and node_order:
            entry = node_order[0]

        # Reachable from entry while skipping node_id
        def reachable_skipping(start, skip):
            """BFS from start, never entering skip node."""
            if start is None or start == skip:
                return set()
            visited_local = set()
            queue = [start]
            while queue:
                n = queue.pop()
                if n is None or n in visited_local or n == skip:
                    continue
                visited_local.add(n)
                for nxt in outgoing.get(n, []):
                    if nxt is not None and nxt not in visited_local and nxt != skip:
                        queue.append(nxt)
            return visited_local

        still_reachable = reachable_skipping(entry, node_id)
        nodes_to_delete = reachable_from_node - still_reachable

        # Update predecessors to point to None
        Routing.objects.filter(section=section, next_node=node_id).update(next_node=None)
        # Delete all rows for nodes_to_delete
        Routing.objects.filter(section=section, current_node__in=nodes_to_delete).delete()

    else:  # promote
        node_rows = sorted(
            [r for r in rows if r.current_node == node_id],
            key=lambda r: r.order_in_section,
        )
        nexts_list = outgoing.get(node_id, [])

        if len(nexts_list) <= 1:
            # Non-branching: wire predecessors to node's single successor
            z = nexts_list[0] if nexts_list else None
            Routing.objects.filter(section=section, next_node=node_id).update(next_node=z)
            Routing.objects.filter(section=section, current_node=node_id).delete()

        else:
            # Branching: inline all branches in order
            cond_rows = node_rows
            branch_reachable = [_reachable_from(outgoing, r.next_node) for r in cond_rows]

            if branch_reachable:
                common = branch_reachable[0].copy()
                for br in branch_reachable[1:]:
                    common &= br
            else:
                common = set()
            convergence = None
            for nid in node_order:
                if nid in common and nid != node_id:
                    convergence = nid
                    break

            # Build ordered branch chains: branch_only nodes in traversal order
            def branch_chain(branch_next, branch_only):
                """Return ordered list of branch-only nodes starting from branch_next."""
                chain = []
                visited_local = set()
                current = branch_next
                while current is not None and current in branch_only and current not in visited_local:
                    visited_local.add(current)
                    chain.append(current)
                    nexts = outgoing.get(current, [])
                    current = nexts[0] if nexts else None
                return chain

            chains = []
            for i, cond_row in enumerate(cond_rows):
                other_reachable = set()
                for j, br in enumerate(branch_reachable):
                    if j != i:
                        other_reachable |= br
                branch_only = branch_reachable[i] - other_reachable
                if convergence:
                    branch_only.discard(convergence)
                chains.append(branch_chain(cond_row.next_node, branch_only))

            # Flatten chains: predecessors → first of chain[0],
            # end of chain[i] → first of chain[i+1], end of last → convergence
            flat_chain = [nid for chain in chains for nid in chain]

            if flat_chain:
                first_of_chain = flat_chain[0]
                # Predecessors (currently pointing to node_id) → first_of_chain
                Routing.objects.filter(section=section, next_node=node_id).update(
                    next_node=first_of_chain
                )
                # Wire chain segments together (rows that pointed to convergence
                # from within a chain should now point to next chain segment)
                for ci, chain in enumerate(chains):
                    if not chain:
                        continue
                    last_in_chain = chain[-1]
                    # What did the last node in this chain point to?
                    # It should have pointed to convergence (or None).
                    if ci + 1 < len(chains):
                        next_chain_start = None
                        for c2 in chains[ci + 1:]:
                            if c2:
                                next_chain_start = c2[0]
                                break
                        if next_chain_start:
                            Routing.objects.filter(
                                section=section,
                                current_node=last_in_chain,
                                next_node=convergence,
                            ).update(next_node=next_chain_start)
                    # else: last chain → convergence already correct
            else:
                # All branches are empty — predecessors → convergence
                Routing.objects.filter(section=section, next_node=node_id).update(
                    next_node=convergence
                )

            Routing.objects.filter(section=section, current_node=node_id).delete()

    _renumber_routing(section)
    return redirect(routing_url)


# ── View: delete condition ────────────────────────────────────────────────────

@staff_required
def tools_routing_delete_condition(request, section_id):
    """POST only. Remove one condition branch from a branching node."""
    if request.method != 'POST':
        return redirect(f'/tools/sections/{section_id}/routing/')

    section = get_object_or_404(Section, section_id=section_id)
    routing_url = f'/tools/sections/{section_id}/routing/'

    node_id      = request.POST.get('node_id', '').strip()
    answer_value = request.POST.get('answer_value', '').strip() or None

    if not node_id:
        return redirect(routing_url)

    rows = list(Routing.objects.filter(section=section).order_by('order_in_section'))
    outgoing = _build_outgoing(rows)

    # Identify this condition's branch_only nodes
    all_cond_rows = [r for r in rows if r.current_node == node_id]
    try:
        this_cond = next(r for r in all_cond_rows if r.answer_value == answer_value)
    except StopIteration:
        return redirect(routing_url)

    other_cond_rows = [r for r in all_cond_rows if r.answer_value != answer_value]
    this_reachable = _reachable_from(outgoing, this_cond.next_node)
    other_reachable = set()
    for r in other_cond_rows:
        other_reachable |= _reachable_from(outgoing, r.next_node)

    branch_only = this_reachable - other_reachable

    # Delete the condition row
    this_cond.delete()
    # Delete branch-only rows
    Routing.objects.filter(section=section, current_node__in=branch_only).delete()

    _renumber_routing(section)
    return redirect(routing_url)


# ── View: add condition ───────────────────────────────────────────────────────

@staff_required
def tools_routing_add_condition(request, section_id):
    """POST only. Add a new answer_value condition to a branching node."""
    if request.method != 'POST':
        return redirect(f'/tools/sections/{section_id}/routing/')

    section = get_object_or_404(Section, section_id=section_id)
    routing_url = f'/tools/sections/{section_id}/routing/'

    node_id      = request.POST.get('node_id', '').strip()
    answer_value = request.POST.get('answer_value', '').strip() or None

    if not node_id or not answer_value:
        return redirect(routing_url)

    max_order = (
        Routing.objects.filter(section=section)
        .order_by('-order_in_section')
        .values_list('order_in_section', flat=True)
        .first()
    ) or 0

    Routing.objects.get_or_create(
        section=section,
        current_node=node_id,
        answer_value=answer_value,
        defaults={'next_node': None, 'order_in_section': max_order + 10},
    )

    _renumber_routing(section)
    return redirect(routing_url)


# ─────────────────────────────────────────────────────────────────────────────
# ACTOR MANAGEMENT VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def tools_actors(request):
    """List all actor arrangements and offer a create button."""
    # Rows where actor acts FOR someone else
    arrangements = (
        Permission.objects
        .exclude(actor_id=F('user_id'))
        .select_related('actor', 'user', 'regime', 'section')
        .order_by('actor__username', 'user__username')
    )
    added = request.GET.get('added', '')
    return render(request, 'core/tools_actors.html', {
        'arrangements': arrangements,
        'added':        added,
    })


@staff_required
def tools_actor_create(request):
    """Multi-step session wizard for setting up an actor arrangement."""
    SK_STEP     = 'actor_create_step'
    SK_ACTOR    = 'actor_create_actor_id'
    SK_USERS    = 'actor_create_user_ids'
    SK_GRANTS   = 'actor_create_grants'    # {user_id: 'full' | [section_id, ...]}

    def _clear_session():
        for k in (SK_STEP, SK_ACTOR, SK_USERS, SK_GRANTS):
            request.session.pop(k, None)

    errors = {}

    if request.method == 'POST':
        action = request.POST.get('action', '')

        # ── Step 1: choose / create actor ────────────────────────────────────
        if action == 'set_actor':
            actor_source = request.POST.get('actor_source', 'existing')
            if actor_source == 'existing':
                actor_id = request.POST.get('actor_user_id', '').strip()
                if not actor_id:
                    errors['actor'] = 'Select a user'
                else:
                    try:
                        User.objects.get(pk=actor_id)
                    except (User.DoesNotExist, ValueError):
                        errors['actor'] = 'Select a valid user'
                if not errors:
                    request.session[SK_ACTOR] = int(actor_id)
                    request.session[SK_STEP]  = 2
                    return redirect('core:tools_actor_create')
            else:
                username = request.POST.get('new_username', '').strip()
                password = request.POST.get('new_password', '').strip()
                if not username:
                    errors['actor'] = 'Enter a username'
                elif User.objects.filter(username=username).exists():
                    errors['actor'] = f'Username "{username}" is already taken'
                if not errors and not password:
                    errors['actor'] = 'Enter a password'
                if not errors:
                    new_user = User.objects.create_user(username=username, password=password)
                    request.session[SK_ACTOR] = new_user.pk
                    request.session[SK_STEP]  = 2
                    return redirect('core:tools_actor_create')

        # ── Step 2: choose users actor acts for ──────────────────────────────
        elif action == 'set_users':
            user_ids = request.POST.getlist('user_ids')
            if not user_ids:
                errors['users'] = 'Select at least one user'
            if not errors:
                request.session[SK_USERS] = [int(uid) for uid in user_ids]
                request.session[SK_STEP]  = 3
                return redirect('core:tools_actor_create')

        # ── Step 3: grant scope per user ─────────────────────────────────────
        elif action == 'set_grants':
            user_ids = request.session.get(SK_USERS, [])
            grants = {}
            for uid in user_ids:
                scope = request.POST.get(f'scope_{uid}', 'full')
                if scope == 'full':
                    grants[str(uid)] = 'full'
                else:
                    selected = request.POST.getlist(f'sections_{uid}')
                    grants[str(uid)] = selected
            request.session[SK_GRANTS] = grants
            request.session[SK_STEP]   = 4
            return redirect('core:tools_actor_create')

        # ── Step 4: save ─────────────────────────────────────────────────────
        elif action == 'save':
            actor_id = request.session.get(SK_ACTOR)
            user_ids = request.session.get(SK_USERS, [])
            grants   = request.session.get(SK_GRANTS, {})
            try:
                actor = User.objects.get(pk=actor_id)
            except (User.DoesNotExist, TypeError):
                _clear_session()
                return redirect('core:tools_actor_create')

            all_regimes = Regime.objects.exclude(dept_id='PLATFORM')
            for uid in user_ids:
                try:
                    target_user = User.objects.get(pk=uid)
                except User.DoesNotExist:
                    continue
                scope = grants.get(str(uid), 'full')
                if scope == 'full':
                    for regime in all_regimes:
                        Permission.objects.get_or_create(
                            actor=actor, user=target_user,
                            regime=regime, section=None,
                            defaults={'can_delegate': False, 'granted_by': None},
                        )
                else:
                    for section_id in scope:
                        try:
                            section = Section.objects.get(section_id=section_id)
                        except Section.DoesNotExist:
                            continue
                        Permission.objects.get_or_create(
                            actor=actor, user=target_user,
                            regime=None, section=section,
                            defaults={'can_delegate': False, 'granted_by': None},
                        )

            actor_username = actor.username
            _clear_session()
            return redirect(f'/tools/actors/?added={actor_username}')

        elif action == 'cancel':
            _clear_session()
            return redirect('core:tools_actors')

    # ── GET: render current step ──────────────────────────────────────────────
    step     = request.session.get(SK_STEP, 1)
    actor_id = request.session.get(SK_ACTOR)
    user_ids = request.session.get(SK_USERS, [])
    grants   = request.session.get(SK_GRANTS, {})

    actor = None
    if actor_id:
        try:
            actor = User.objects.get(pk=actor_id)
        except User.DoesNotExist:
            pass

    # Users available to act for (exclude the actor themselves)
    actor_pk_set = {actor_id} if actor_id else set()
    candidate_users = User.objects.exclude(pk__in=actor_pk_set).order_by('username')

    # Users selected in step 2
    selected_users = list(User.objects.filter(pk__in=user_ids).order_by('username'))

    # All sections grouped by regime for step 3 partial scope
    regimes_with_sections = []
    for regime in Regime.objects.exclude(dept_id='PLATFORM').order_by('regime_id'):
        secs = list(Section.objects.filter(
            models.Q(regime=regime) | models.Q(schedule__regime=regime)
        ).order_by('section_id'))
        if secs:
            regimes_with_sections.append({'regime': regime, 'sections': secs})

    # Resolve grants for step 4 summary
    grant_summary = []
    for uid in user_ids:
        try:
            u = User.objects.get(pk=uid)
        except User.DoesNotExist:
            continue
        scope = grants.get(str(uid), 'full')
        if scope == 'full':
            grant_summary.append({'user': u, 'scope': 'Full access (all regimes)', 'sections': []})
        else:
            secs = list(Section.objects.filter(section_id__in=scope).order_by('section_id'))
            grant_summary.append({'user': u, 'scope': 'Partial', 'sections': secs})

    context = {
        'step':                  step,
        'actor':                 actor,
        'candidate_users':       candidate_users,
        'selected_users':        selected_users,
        'regimes_with_sections': regimes_with_sections,
        'grant_summary':         grant_summary,
        'errors':                errors,
    }
    return render(request, 'core/tools_actor_create.html', context)


@staff_required
def tools_actor_revoke(request):
    """POST only. Delete one Permission row."""
    if request.method != 'POST':
        return redirect('core:tools_actors')
    perm_id = request.POST.get('permission_id', '').strip()
    try:
        Permission.objects.get(pk=perm_id).delete()
    except (Permission.DoesNotExist, ValueError):
        pass
    return redirect('core:tools_actors')


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
        back         = request.POST.get('back', '')
        back_regime   = request.POST.get('back_regime', '')
        back_schedule = request.POST.get('back_schedule', '')
        back_section  = request.POST.get('back_section', '')

        question.question_text = request.POST.get('question_text', question.question_text).strip()
        question.question_type = request.POST.get('question_type', question.question_type).strip()
        question.guidance = request.POST.get('guidance', '').strip() or None
        question.hint     = request.POST.get('hint', '').strip() or None
        question.options  = request.POST.get('options', '').strip() or None
        question.save()

        if back == 'picker':
            return redirect('/tools/questions/edit/')
        return redirect(_back_url(back_regime, back_schedule, back_section))

    back          = request.GET.get('back', '')
    back_regime   = request.GET.get('back_regime', '')
    back_schedule = request.GET.get('back_schedule', '')
    back_section  = request.GET.get('back_section', '')

    if back == 'picker':
        computed_back_url = '/tools/questions/edit/'
    else:
        computed_back_url = _back_url(back_regime, back_schedule, back_section)

    context = {
        'question':              question,
        'question_type_choices': Question.QUESTION_TYPE_CHOICES,
        'back_url':              computed_back_url,
        'back':                  back,
        'back_regime':           back_regime,
        'back_schedule':         back_schedule,
        'back_section':          back_section,
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
        back          = request.POST.get('back', '')
        back_regime   = request.POST.get('back_regime', '')
        back_schedule = request.POST.get('back_schedule', '')
        back_section  = request.POST.get('back_section', '')

        qs.set_title = request.POST.get('set_title', qs.set_title).strip()
        qs.set_hint  = request.POST.get('set_hint', '').strip() or None
        qs.save()

        if back == 'picker':
            return redirect('/tools/sets/edit/')
        return redirect(_back_url(back_regime, back_schedule, back_section))

    back          = request.GET.get('back', '')
    back_regime   = request.GET.get('back_regime', '')
    back_schedule = request.GET.get('back_schedule', '')
    back_section  = request.GET.get('back_section', '')

    if back == 'picker':
        computed_back_url = '/tools/sets/edit/'
    else:
        computed_back_url = _back_url(back_regime, back_schedule, back_section)

    # Questions not already in this set, for the "add member" dropdown
    existing_q_ids = qs.members.values_list('question_id', flat=True)
    available_questions = (
        Question.objects
        .exclude(question_id__in=existing_q_ids)
        .order_by('question_id')
    )
    max_order = (
        qs.members.order_by('-display_order')
        .values_list('display_order', flat=True)
        .first()
    ) or 0
    next_order = max_order + 10

    context = {
        'qs':                  qs,
        'back_url':            computed_back_url,
        'back':                back,
        'back_regime':         back_regime,
        'back_schedule':       back_schedule,
        'back_section':        back_section,
        'available_questions': available_questions,
        'next_order':          next_order,
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
