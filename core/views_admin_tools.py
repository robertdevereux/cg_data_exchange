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
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .interfaces import bootstrap_section_statuses, get_or_create_case
from .models import (
    Answer,
    AnswerTable,
    Case,
    Question,
    QuestionSet,
    QuestionSetMember,
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
            Regime.objects.create(
                regime_id=generated_id,
                regime_name=regime_name,
                dept_id=settings.ACTIVE_DEPT,
                display_order=0,
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
    """Create a new Section record (fields only; routing is Chunk 6)."""
    regimes = (
        Regime.objects
        .filter(dept_id=settings.ACTIVE_DEPT)
        .order_by('regime_id')
    )
    errors = {}
    post = {}

    if request.method == 'POST':
        post = request.POST
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

            Section.objects.create(
                section_id=section_id,
                section_name=section_name,
                section_type=section_type_int,
                display_order=display_order_int,
                regime=regime,
                schedule=None,
                section_guidance=section_guidance,
                column_question_ids=column_question_ids,
                totals_question_ids=totals_question_ids,
            )
            return redirect(f'/tools/sections/{section_id}/routing/')

    context = {
        'regimes':               regimes,
        'section_type_choices':  Section.SECTION_TYPE_CHOICES,
        'errors':                errors,
        'post':                  post,
        'active_dept':           settings.ACTIVE_DEPT,
    }
    return render(request, 'core/tools_section_create.html', context)


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
        'section':         section,
        'tree':            tree,
        'available_nodes': available_nodes,
    })


# ── View: insert node ─────────────────────────────────────────────────────────

@staff_required
def tools_routing_insert(request, section_id):
    """GET: show insert form. POST: create new routing row(s)."""
    section = get_object_or_404(Section, section_id=section_id)
    routing_url = f'/tools/sections/{section_id}/routing/'

    if request.method == 'POST':
        new_node_id  = request.POST.get('new_node_id', '').strip()
        mode         = request.POST.get('mode', '').strip()
        ref_node     = request.POST.get('ref_node', '').strip()
        answer_value = request.POST.get('answer_value', '').strip() or None

        # Validate
        if not new_node_id:
            return redirect(routing_url)
        if Routing.objects.filter(section=section, current_node=new_node_id).exists():
            return redirect(routing_url)

        max_order = (
            Routing.objects.filter(section=section)
            .order_by('-order_in_section')
            .values_list('order_in_section', flat=True)
            .first()
        ) or 0

        if mode == 'first':
            Routing.objects.create(
                section=section,
                current_node=new_node_id,
                answer_value=None,
                next_node=None,
                order_in_section=10,
            )

        elif mode == 'before' and ref_node:
            # All rows pointing to ref_node now point to new_node_id
            Routing.objects.filter(section=section, next_node=ref_node).update(
                next_node=new_node_id
            )
            Routing.objects.create(
                section=section,
                current_node=new_node_id,
                answer_value=None,
                next_node=ref_node,
                order_in_section=max_order + 10,
            )

        elif mode == 'after' and ref_node:
            try:
                out_row = Routing.objects.get(section=section, current_node=ref_node)
            except Routing.DoesNotExist:
                return redirect(routing_url)
            z = out_row.next_node
            out_row.next_node = new_node_id
            out_row.save()
            Routing.objects.create(
                section=section,
                current_node=new_node_id,
                answer_value=None,
                next_node=z,
                order_in_section=max_order + 10,
            )

        elif mode == 'branch' and ref_node:
            try:
                cond_row = Routing.objects.get(
                    section=section,
                    current_node=ref_node,
                    answer_value=answer_value,
                )
            except Routing.DoesNotExist:
                return redirect(routing_url)
            z = cond_row.next_node
            cond_row.next_node = new_node_id
            cond_row.save()
            Routing.objects.create(
                section=section,
                current_node=new_node_id,
                answer_value=None,
                next_node=z,
                order_in_section=max_order + 10,
            )

        _renumber_routing(section)
        return redirect(routing_url)

    # GET — build the form
    mode         = request.GET.get('mode', 'first')
    ref_node     = request.GET.get('node', '')
    answer_value = request.GET.get('answer_value', '')

    existing_node_ids = set(
        Routing.objects.filter(section=section)
        .values_list('current_node', flat=True)
        .distinct()
    )
    questions = Question.objects.exclude(question_id__in=existing_node_ids).order_by('question_id')
    sets = QuestionSet.objects.exclude(set_id__in=existing_node_ids).order_by('set_id')
    available_nodes = (
        [{'id': q.question_id, 'label': f'{q.question_id}  {q.question_text}'} for q in questions]
        + [{'id': s.set_id, 'label': f'{s.set_id}  {s.set_title}'} for s in sets]
    )

    return render(request, 'core/tools_routing_insert.html', {
        'section':         section,
        'mode':            mode,
        'ref_node':        ref_node,
        'answer_value':    answer_value,
        'available_nodes': available_nodes,
        'routing_url':     routing_url,
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
