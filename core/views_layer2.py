"""
Layer 2: Section Processing Engine
===================================
Everything that happens inside a Section once a citizen has selected it.

Responsibility boundary
  Layer 1 (views_layer1.py + interfaces.call_core) gets the citizen to the
  right section and sets the outer PSS session context: user_id, actor_id,
  regime_id, case_id (all via call_core) and schedule_id (via
  regime_schedule_sections; None when there is no enclosing schedule).

  Layer 2 (this file) takes over at section_start and owns the full
  journey:  start → question(s) → review → confirm → done.
  Table sections follow: table landing → add/delete rows → confirm → done.

  The section_id in the URL is the canonical source of truth for which
  section is being processed.  Session carries in-flight state.
"""

import logging
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

from .models import (
    Answer,
    AnswerHistory,
    AnswerTable,
    AnswerTableHistory,
    Case,
    Question,
    QuestionSet,
    QuestionSetMember,
    Regime,
    Routing,
    Section,
    SectionStatus,
    User,
)
from .session import clear_section_session, get_acting_for_name, get_session, update_session


# ── Routing evaluation helper ─────────────────────────────────────────────────

_UNSET = object()   # sentinel: "no route found yet"


def _resolve_routing_answer(routing_table, current_node, all_answers):
    """Return the answer value to test when evaluating routing from current_node.

    If any routing row for current_node has a condition_question_id set, return
    the stored answer for that question. Where all rows share the same
    condition_question_id (the expected pattern), returns that answer.

    If no condition_question_id is set on any row (standard behaviour), returns
    the current node's own answer from all_answers.

    Note: where rows for the same current_node carry *different*
    condition_question_ids the first one found is used. That pattern is out of
    scope for this spec (deferred to the Conditional Table spec).
    """
    for row in routing_table:
        if row['current_node'] == current_node and row.get('condition_question_id'):
            cqid = row['condition_question_id']
            return all_answers.get(cqid, '')
    return all_answers.get(current_node, '')


def _evaluate_routing(routing_table, question_id, answer):
    """Find the next question_id for a given question and answer.

    Returns (next_node, found):
      next_node — the routing target, or None meaning END
      found            — False if no matching route exists (data error)

    Matching rules:
    - Conditional rows (answer_value not None) are checked first.
      • If the row has a non-null comparator and threshold_value, the answer
        is converted to Decimal and compared: decimal(answer) [comparator]
        threshold_value.  If conversion fails, the row does not match.
      • Otherwise answer_value may be semicolon-delimited; any match is
        sufficient.  Comparison is case-insensitive.  answer may be a list
        (checkbox).
    - If no conditional row matches, the unconditional row (answer_value
      None) is used as fallback.
    """
    conditional_next = _UNSET
    unconditional_next = _UNSET

    for row in routing_table:
        if row['current_node'] != question_id:
            continue

        comparator    = row.get('comparator')
        threshold_val = row.get('threshold_value')

        if row['answer_value'] is not None:
            if comparator and threshold_val is not None:
                # Scalar comparison branch
                try:
                    numeric_answer = Decimal(str(answer).strip())
                except (InvalidOperation, ValueError):
                    is_match = False
                else:
                    if comparator == '=':
                        is_match = numeric_answer == threshold_val
                    elif comparator == '<':
                        is_match = numeric_answer < threshold_val
                    elif comparator == '<=':
                        is_match = numeric_answer <= threshold_val
                    elif comparator == '>':
                        is_match = numeric_answer > threshold_val
                    elif comparator == '>=':
                        is_match = numeric_answer >= threshold_val
                    else:
                        is_match = False
            else:
                # Standard equality / set-membership match
                allowed = {v.strip().lower() for v in str(row['answer_value']).split(';')}
                if isinstance(answer, list):
                    is_match = any(v.strip().lower() in allowed for v in answer)
                else:
                    is_match = str(answer).strip().lower() in allowed

            if is_match:
                conditional_next = row['next_node']
                break   # first conditional match wins
        else:
            unconditional_next = row['next_node']   # last unconditional wins

    if conditional_next is not _UNSET:
        return conditional_next, True
    if unconditional_next is not _UNSET:
        return unconditional_next, True
    return None, False


# ── Breadcrumb helper ────────────────────────────────────────────────────────

def _build_crumbs(pss, final_label):
    """Append final_label to the session breadcrumbs built by Layer 1."""
    crumbs = list(pss.get('breadcrumbs', []))
    crumbs.append({'label': final_label, 'url': None})
    return crumbs


# ── Session bootstrap helper (used by section_start) ─────────────────────────

def _get_or_create_case(user, regime):
    """Return the most recent draft Case for user/regime, creating one if needed."""
    case = Case.objects.filter(
        user=user, regime=regime, status='draft'
    ).order_by('-started_at').first()
    if not case:
        case = Case.objects.create(
            case_id=str(uuid.uuid4()),
            user=user,
            regime=regime,
            status='draft',
        )
    return case


# ── Section-tables build helper ──────────────────────────────────────────────

def _build_section_tables(routing_rows):
    """Build the routing, question, and set metadata tables for a section.

    Args:
        routing_rows: QuerySet of Routing rows ordered by order_in_section.

    Returns a dict with keys:
        routing_table       — list of dicts (one per Routing row)
        all_node_ids        — ordered list of unique current_node values
        question_node_ids   — subset of all_node_ids that are Questions
        set_node_ids        — subset of all_node_ids that are QuestionSets
        question_table      — {question_id: metadata_dict}
        set_table           — {set_id: {set_title, set_hint, members: [...]}}
        question_to_set     — {question_id: set_id}
        first_node          — current_node of the first routing row, or None
    """
    routing_table = [
        {
            'current_node':          row.current_node,
            'condition_question_id': row.condition_question_id,
            'answer_value':          row.answer_value,
            'next_node':             row.next_node,
            'comparator':            row.comparator,
            'threshold_value':       row.threshold_value,
        }
        for row in routing_rows
    ]

    all_node_ids = list(dict.fromkeys(r['current_node'] for r in routing_table))

    existing_set_ids = set(
        QuestionSet.objects
        .filter(set_id__in=all_node_ids)
        .values_list('set_id', flat=True)
    )
    set_node_ids      = [nid for nid in all_node_ids if nid in existing_set_ids]
    question_node_ids = [nid for nid in all_node_ids if nid not in existing_set_ids]

    questions = Question.objects.filter(question_id__in=question_node_ids)
    question_table = {
        q.question_id: {
            'question_text': q.question_text,
            'question_type': q.question_type,
            'guidance':      q.guidance or '',
            'hint':          q.hint or '',
            'options':       q.options or '',
        }
        for q in questions
    }

    set_table = {}
    question_to_set = {}
    if set_node_ids:
        set_members = (
            QuestionSetMember.objects
            .filter(question_set_id__in=set_node_ids)
            .select_related('question', 'question_set')
            .order_by('display_order')
        )
        for member in set_members:
            sid = member.question_set_id
            qid = member.question_id
            if sid not in set_table:
                set_table[sid] = {
                    'set_title': member.question_set.set_title,
                    'set_hint':  member.question_set.set_hint or '',
                    'members': [],
                }
            set_table[sid]['members'].append({
                'question_id':   qid,
                'question_text': member.question.question_text,
                'question_type': member.question.question_type,
                'guidance':      member.question.guidance or '',
                'hint':          member.question.hint or '',
                'options':       member.question.options or '',
                'required':      member.required,
            })
            question_to_set[qid] = sid

    first_node = routing_rows[0].current_node if routing_rows else None

    return {
        'routing_table':     routing_table,
        'all_node_ids':      all_node_ids,
        'question_node_ids': question_node_ids,
        'set_node_ids':      set_node_ids,
        'question_table':    question_table,
        'set_table':         set_table,
        'question_to_set':   question_to_set,
        'first_node':        first_node,
    }


# ── Table row commit helper ───────────────────────────────────────────────────

def _commit_table_row(request, section, case, regime, pss, row_answers, row_index=None):
    """Write a completed row to AnswerTable.

    If row_index is None, appends a new row.
    If row_index is an int, replaces the row at that index.
    Returns the saved AnswerTable instance.
    """
    actor_id = pss.get('actor_id') or request.user.pk
    try:
        actor = User.objects.get(pk=actor_id)
    except User.DoesNotExist:
        actor = request.user

    answer_table, _ = AnswerTable.objects.get_or_create(
        user=case.user, case=case, section=section,
        defaults={'actor': actor, 'regime': regime, 'answer': []},
    )

    rows = list(answer_table.answer)
    if row_index is None:
        rows.append(row_answers)
    else:
        if 0 <= row_index < len(rows):
            rows[row_index] = row_answers

    answer_table.answer = rows
    answer_table.save(update_fields=['answer', 'updated_at'])

    SectionStatus.objects.update_or_create(
        user=case.user, regime=regime, section=section,
        defaults={'status': 'in_progress'},
    )

    return answer_table


# ─────────────────────────────────────────────────────────────────────────────
# 1.  SECTION START
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_start(request, section_id):
    """Load routing/questions into session and redirect to the first question.

    Also handles the case where no Layer 1 session context exists yet
    (direct URL access for testing) by looking up or creating a Case.
    """
    section = get_object_or_404(Section, section_id=section_id)

    # Table sections have their own entry point.
    if section.section_type in (1, 2):
        return redirect('core:section_table', section_id=section_id)

    regime = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    # ── Resolve case and actor ────────────────────────────────────────────────
    pss = get_session(request)
    if pss.get('case_id'):
        try:
            case = Case.objects.get(case_id=pss['case_id'])
        except Case.DoesNotExist:
            case = _get_or_create_case(request.user, regime)
    else:
        case = _get_or_create_case(request.user, regime)

    actor_id = pss.get('actor_id') or request.user.pk

    # ── Build routing / question / set tables ─────────────────────────────────
    routing_rows = (
        Routing.objects
        .filter(section=section)
        .order_by('order_in_section')
    )
    tables = _build_section_tables(routing_rows)
    routing_table     = tables['routing_table']
    all_node_ids      = tables['all_node_ids']
    question_node_ids = tables['question_node_ids']
    set_node_ids      = tables['set_node_ids']
    question_table    = tables['question_table']
    set_table         = tables['set_table']
    question_to_set   = tables['question_to_set']
    first_node        = tables['first_node']
    existing_set_ids  = set(set_node_ids)

    if not first_node:
        # No routing configured — treat as done
        return redirect('core:section_done', section_id=section_id)

    # ── Load confirmed answers from DB ────────────────────────────────────────
    all_question_ids = question_node_ids + list(question_to_set.keys())
    existing_answers = Answer.objects.filter(
        user=case.user, case=case, section=section,
        question_id__in=all_question_ids,
    )
    basic_answers = {a.question_id: a.answer for a in existing_answers}

    # ── Determine asked_ids and entry point ───────────────────────────────────
    # Re-entry (answers exist): reconstruct asked_ids in routing order — only
    # nodes the citizen actually answered — then go to review.
    # Fresh start: seed with first node only and go to first node.
    if basic_answers:
        asked_ids = []
        for node_id in all_node_ids:
            if node_id in existing_set_ids:
                # Set node: answered if any member question has an answer
                member_qids = [
                    m['question_id']
                    for m in set_table.get(node_id, {}).get('members', [])
                ]
                if any(qid in basic_answers for qid in member_qids):
                    asked_ids.append(node_id)
            else:
                if node_id in basic_answers:
                    asked_ids.append(node_id)
        go_to_review = True
    else:
        asked_ids = [first_node]
        go_to_review = False

    # ── Update section status ─────────────────────────────────────────────────
    ss, _ = SectionStatus.objects.get_or_create(
        user=case.user, regime=regime, section=section,
        defaults={'status': 'not_started'},
    )
    if ss.status == 'not_started':
        ss.status = 'in_progress'
        ss.save(update_fields=['status'])

    # ── Write everything to session ───────────────────────────────────────────
    # Only write user_id if no case_id was already in session (i.e. bootstrap
    # path). When arriving via call_core, the correct user_id is already set.
    session_update = {
        'actor_id':         actor_id,
        'regime_id':        regime.regime_id,
        'case_id':          case.case_id,
        'section_id':       section_id,
        'routing_table':    routing_table,
        'question_table':   question_table,
        'set_table':        set_table,
        'question_to_set':  question_to_set,
        'asked_ids':        asked_ids,
        'basic_answers':    basic_answers,
    }
    if not pss.get('case_id'):
        session_update['user_id'] = case.user.pk
    update_session(request, session_update)

    if go_to_review:
        return redirect('core:section_review', section_id=section_id)
    if first_node in set_table:
        return redirect('core:section_set_page', section_id=section_id, set_id=first_node)
    return redirect('core:section_question', section_id=section_id, question_id=first_node)


# ─────────────────────────────────────────────────────────────────────────────
# 2 & 3.  QUESTION VIEW  (GET = render, includes backtrack; POST = process)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_question(request, section_id, question_id):
    section = get_object_or_404(Section, section_id=section_id)
    pss = get_session(request)

    question_table = pss.get('question_table', {})
    q_meta = question_table.get(question_id)
    if not q_meta:
        # Session lost or question not in this section — restart
        return redirect('core:section_start', section_id=section_id)

    if request.method == 'POST':
        return _process_answer(request, section, section_id, question_id, q_meta, pss)

    # ── GET ───────────────────────────────────────────────────────────────────
    asked_ids    = pss.get('asked_ids', [question_id])
    basic_answers = pss.get('basic_answers', {})

    # Backtrack: if arriving at a question already on the path, truncate.
    if question_id in asked_ids:
        idx = asked_ids.index(question_id)
        asked_ids = asked_ids[:idx + 1]
        update_session(request, {'asked_ids': asked_ids})

    # ── Current answer / cross-regime suggestion ──────────────────────────────
    current_answer = basic_answers.get(question_id)
    suggestion   = None
    provenance   = None

    if current_answer is None:
        pss_case_id = pss.get('case_id')
        prior = (
            Answer.objects
            .filter(user=request.user, question_id=question_id)
            .exclude(case_id=pss_case_id)
            .select_related('regime', 'case')
            .order_by('-updated_at')
            .first()
        )
        if prior:
            suggestion = prior.answer
            provenance = (
                f"Suggested from {prior.regime.regime_name} — "
                f"last confirmed {prior.updated_at.strftime('%d %b %Y')}"
            )

    # ── Back link ─────────────────────────────────────────────────────────────
    if len(asked_ids) > 1 and question_id == asked_ids[-1]:
        prev_node = asked_ids[-2]
        set_table = pss.get('set_table', {})
        if prev_node in set_table:
            back_url = f'/section/{section_id}/set/{prev_node}/'
        else:
            back_url = f'/section/{section_id}/question/{prev_node}/'
    else:
        back_url = f'/section/{section_id}/start/'

    # ── Options list for radio / checkbox ─────────────────────────────────────
    options = [o.strip() for o in q_meta['options'].split(';') if o.strip()]

    # ── Split date answer into parts for pre-population ───────────────────────
    date_parts = None
    if q_meta['question_type'] == 'date':
        source = current_answer if isinstance(current_answer, dict) else (
            suggestion if isinstance(suggestion, dict) else None
        )
        date_parts = {
            'day':   source.get('day', '') if source else '',
            'month': source.get('month', '') if source else '',
            'year':  source.get('year', '') if source else '',
        }

    name_parts = None
    if q_meta['question_type'] == 'personal_name':
        source = current_answer if isinstance(current_answer, dict) else (
            suggestion if isinstance(suggestion, dict) else None
        )
        name_parts = {
            'title':       source.get('title', '')       if source else '',
            'first_name':  source.get('first_name', '')  if source else '',
            'middle_name': source.get('middle_name', '') if source else '',
            'last_name':   source.get('last_name', '')   if source else '',
        }

    address_parts = None
    if q_meta['question_type'] == 'address':
        source = current_answer if isinstance(current_answer, dict) else (
            suggestion if isinstance(suggestion, dict) else None
        )
        address_parts = {
            'line1':    source.get('line1', '')    if source else '',
            'line2':    source.get('line2', '')    if source else '',
            'city':     source.get('city', '')     if source else '',
            'county':   source.get('county', '')   if source else '',
            'postcode': source.get('postcode', '') if source else '',
        }

    compound_parts = None
    if q_meta['question_type'] == 'compound':
        import json as _json
        try:
            components = _json.loads(q_meta['options']) if q_meta['options'] else []
        except (ValueError, TypeError):
            components = []
        source = current_answer if isinstance(current_answer, dict) else (
            suggestion if isinstance(suggestion, dict) else None
        )
        compound_parts = [
            {
                'index': i,
                'label': comp.get('label', f'Component {i + 1}'),
                'type':  comp.get('type', 'text'),
                'value': source.get(comp.get('label', ''), '') if source else '',
                'error': None,
            }
            for i, comp in enumerate(components)
        ]

    context = {
        'section':        section,
        'question_id':    question_id,
        'question_text':  q_meta['question_text'],
        'guidance':       q_meta['guidance'],
        'hint':           q_meta['hint'],
        'question_type':  q_meta['question_type'],
        'options':        options,
        'current_answer': current_answer,
        'date_parts':     date_parts,
        'name_parts':     name_parts,
        'address_parts':  address_parts,
        'compound_parts': compound_parts,
        'compound_errors': [],
        'suggestion':     suggestion,
        'provenance':     provenance,
        'back_url':       back_url,
        'asked_ids':      asked_ids,
        'breadcrumbs':    _build_crumbs(pss, section.section_name),
        'acting_for':     get_acting_for_name(pss),
    }

    template_map = {
        'radio':         'core/question_radio.html',
        'radio_inline':  'core/question_radio_inline.html',
        'checkbox':      'core/question_checkbox.html',
        'date':          'core/question_date.html',
        'personal_name': 'core/question_personal_name.html',
        'address':       'core/question_address.html',
        'compound':      'core/question_compound.html',
    }
    template = template_map.get(q_meta['question_type'], 'core/question_text.html')
    return render(request, template, context)


def _process_answer(request, section, section_id, question_id, q_meta, pss):
    """Handle POST for section_question — store answer, advance routing."""
    import json as _json

    # ── Extract answer ────────────────────────────────────────────────────────
    if q_meta['question_type'] == 'checkbox':
        answer = request.POST.getlist('answer')
    elif q_meta['question_type'] == 'date':
        day   = request.POST.get('date_day', '').strip()
        month = request.POST.get('date_month', '').strip()
        year  = request.POST.get('date_year', '').strip()
        answer = {'day': day, 'month': month, 'year': year}
    elif q_meta['question_type'] == 'personal_name':
        answer = {
            'title':       request.POST.get('personal_name_title', '').strip(),
            'first_name':  request.POST.get('personal_name_first_name', '').strip(),
            'middle_name': request.POST.get('personal_name_middle_name', '').strip(),
            'last_name':   request.POST.get('personal_name_last_name', '').strip(),
        }
    elif q_meta['question_type'] == 'address':
        answer = {
            'line1':    request.POST.get('address_line1', '').strip(),
            'line2':    request.POST.get('address_line2', '').strip(),
            'city':     request.POST.get('address_city', '').strip(),
            'county':   request.POST.get('address_county', '').strip(),
            'postcode': request.POST.get('address_postcode', '').strip(),
        }
    elif q_meta['question_type'] == 'compound':
        try:
            _components = _json.loads(q_meta['options']) if q_meta['options'] else []
        except (ValueError, TypeError):
            _components = []
        answer = {
            comp.get('label', f'Component {i + 1}'): request.POST.get(f'component_{i}', '').strip()
            for i, comp in enumerate(_components)
        }
    else:
        answer = request.POST.get('answer', '').strip()

    # ── Date validation ───────────────────────────────────────────────────────
    if q_meta['question_type'] == 'date':
        errors = []
        day   = answer.get('day', '')
        month = answer.get('month', '')
        year  = answer.get('year', '')
        if not day or not day.isdigit() or not (1 <= int(day) <= 31):
            errors.append('Enter a valid day (1–31)')
        if not month or not month.isdigit() or not (1 <= int(month) <= 12):
            errors.append('Enter a valid month (1–12)')
        if not year or not year.isdigit() or len(year) != 4:
            errors.append('Enter a valid year (4 digits)')
        if errors:
            asked_ids = pss.get('asked_ids', [question_id])
            if len(asked_ids) > 1 and question_id == asked_ids[-1]:
                prev_node = asked_ids[-2]
                _set_table = pss.get('set_table', {})
                if prev_node in _set_table:
                    back_url = f'/section/{section_id}/set/{prev_node}/'
                else:
                    back_url = f'/section/{section_id}/question/{prev_node}/'
            else:
                back_url = f'/section/{section_id}/start/'
            date_parts = {'day': day, 'month': month, 'year': year}
            context = {
                'section':        section,
                'question_id':    question_id,
                'question_text':  q_meta['question_text'],
                'guidance':       q_meta['guidance'],
                'hint':           q_meta['hint'],
                'question_type':  q_meta['question_type'],
                'options':        [],
                'current_answer': answer,
                'date_parts':     date_parts,
                'suggestion':     None,
                'provenance':     None,
                'back_url':       back_url,
                'asked_ids':      asked_ids,
                'error':          ' / '.join(errors),
                'breadcrumbs':    _build_crumbs(pss, section.section_name),
                'acting_for':     get_acting_for_name(pss),
            }
            return render(request, 'core/question_date.html', context)

    # ── personal_name validation ──────────────────────────────────────────────
    if q_meta['question_type'] == 'personal_name':
        errors = []
        if not answer.get('first_name'):
            errors.append('Enter a first name')
        if not answer.get('last_name'):
            errors.append('Enter a last name')
        if errors:
            asked_ids = pss.get('asked_ids', [question_id])
            if len(asked_ids) > 1 and question_id == asked_ids[-1]:
                prev_node = asked_ids[-2]
                _set_table = pss.get('set_table', {})
                if prev_node in _set_table:
                    back_url = f'/section/{section_id}/set/{prev_node}/'
                else:
                    back_url = f'/section/{section_id}/question/{prev_node}/'
            else:
                back_url = f'/section/{section_id}/start/'
            name_parts = answer
            context = {
                'section':        section,
                'question_id':    question_id,
                'question_text':  q_meta['question_text'],
                'guidance':       q_meta['guidance'],
                'hint':           q_meta['hint'],
                'question_type':  q_meta['question_type'],
                'options':        [],
                'current_answer': answer,
                'name_parts':     name_parts,
                'suggestion':     None,
                'provenance':     None,
                'back_url':       back_url,
                'asked_ids':      asked_ids,
                'error':          ' / '.join(errors),
                'breadcrumbs':    _build_crumbs(pss, section.section_name),
                'acting_for':     get_acting_for_name(pss),
            }
            return render(request, 'core/question_personal_name.html', context)

    # ── address validation ────────────────────────────────────────────────────
    if q_meta['question_type'] == 'address':
        errors = []
        if not answer.get('line1'):
            errors.append('Enter the first line of the address')
        if not answer.get('city'):
            errors.append('Enter a town or city')
        if not answer.get('postcode'):
            errors.append('Enter a postcode')
        if errors:
            asked_ids = pss.get('asked_ids', [question_id])
            if len(asked_ids) > 1 and question_id == asked_ids[-1]:
                prev_node = asked_ids[-2]
                _set_table = pss.get('set_table', {})
                if prev_node in _set_table:
                    back_url = f'/section/{section_id}/set/{prev_node}/'
                else:
                    back_url = f'/section/{section_id}/question/{prev_node}/'
            else:
                back_url = f'/section/{section_id}/start/'
            address_parts = answer
            context = {
                'section':        section,
                'question_id':    question_id,
                'question_text':  q_meta['question_text'],
                'guidance':       q_meta['guidance'],
                'hint':           q_meta['hint'],
                'question_type':  q_meta['question_type'],
                'options':        [],
                'current_answer': answer,
                'address_parts':  address_parts,
                'suggestion':     None,
                'provenance':     None,
                'back_url':       back_url,
                'asked_ids':      asked_ids,
                'error':          ' / '.join(errors),
                'breadcrumbs':    _build_crumbs(pss, section.section_name),
                'acting_for':     get_acting_for_name(pss),
            }
            return render(request, 'core/question_address.html', context)

    # ── Compound validation ───────────────────────────────────────────────────
    if q_meta['question_type'] == 'compound':
        try:
            _components = _json.loads(q_meta['options']) if q_meta['options'] else []
        except (ValueError, TypeError):
            _components = []
        compound_errors = []
        compound_parts = []
        for i, comp in enumerate(_components):
            label = comp.get('label', f'Component {i + 1}')
            ctype = comp.get('type', 'text')
            val   = answer.get(label, '')
            err   = None
            if not val:
                err = f'Enter {label}'
                compound_errors.append(err)
            elif ctype == 'number':
                try:
                    float(val)
                except ValueError:
                    err = f'{label} must be a number'
                    compound_errors.append(err)
            compound_parts.append({'index': i, 'label': label, 'type': ctype,
                                   'value': val, 'error': err})
        if compound_errors:
            asked_ids = pss.get('asked_ids', [question_id])
            if len(asked_ids) > 1 and question_id == asked_ids[-1]:
                prev_node = asked_ids[-2]
                _set_table = pss.get('set_table', {})
                if prev_node in _set_table:
                    back_url = f'/section/{section_id}/set/{prev_node}/'
                else:
                    back_url = f'/section/{section_id}/question/{prev_node}/'
            else:
                back_url = f'/section/{section_id}/start/'
            context = {
                'section':        section,
                'question_id':    question_id,
                'question_text':  q_meta['question_text'],
                'guidance':       q_meta['guidance'],
                'hint':           q_meta['hint'],
                'question_type':  q_meta['question_type'],
                'options':        [],
                'current_answer': answer,
                'compound_parts': compound_parts,
                'compound_errors': compound_errors,
                'suggestion':     None,
                'provenance':     None,
                'back_url':       back_url,
                'asked_ids':      asked_ids,
                'error':          compound_errors[0],
                'breadcrumbs':    _build_crumbs(pss, section.section_name),
                'acting_for':     get_acting_for_name(pss),
            }
            return render(request, 'core/question_compound.html', context)

    # ── Basic non-empty validation for non-date types ─────────────────────────
    elif not answer and answer != 0:
        # Re-render with error rather than accepting empty answer
        options = [o.strip() for o in q_meta['options'].split(';') if o.strip()]
        asked_ids = pss.get('asked_ids', [question_id])
        if len(asked_ids) > 1 and question_id == asked_ids[-1]:
            prev_node = asked_ids[-2]
            _set_table = pss.get('set_table', {})
            if prev_node in _set_table:
                back_url = f'/section/{section_id}/set/{prev_node}/'
            else:
                back_url = f'/section/{section_id}/question/{prev_node}/'
        else:
            back_url = f'/section/{section_id}/start/'
        context = {
            'section':        section,
            'question_id':    question_id,
            'question_text':  q_meta['question_text'],
            'guidance':       q_meta['guidance'],
            'hint':           q_meta['hint'],
            'question_type':  q_meta['question_type'],
            'options':        options,
            'current_answer': None,
            'suggestion':     None,
            'provenance':     None,
            'back_url':       back_url,
            'asked_ids':      asked_ids,
            'error':          'Please answer this question before continuing.',
            'breadcrumbs':    _build_crumbs(pss, section.section_name),
            'acting_for':     get_acting_for_name(pss),
        }
        template_map = {'radio': 'core/question_radio.html', 'radio_inline': 'core/question_radio_inline.html', 'checkbox': 'core/question_checkbox.html'}
        template = template_map.get(q_meta['question_type'], 'core/question_text.html')
        return render(request, template, context)

    # ── Store answer in session ───────────────────────────────────────────────
    basic_answers = pss.get('basic_answers', {})
    basic_answers[question_id] = answer
    asked_ids = pss.get('asked_ids', [])

    # Ensure current question is in asked_ids (safety; should already be there)
    if question_id not in asked_ids:
        asked_ids.append(question_id)

    # ── Evaluate routing ──────────────────────────────────────────────────────
    routing_table = pss.get('routing_table', [])
    routing_answer = _resolve_routing_answer(routing_table, question_id, basic_answers)
    next_qid, found = _evaluate_routing(routing_table, question_id, routing_answer)

    if not found:
        # Routing data error — fall through to review as a safe fallback
        update_session(request, {'basic_answers': basic_answers, 'asked_ids': asked_ids})
        return redirect('core:section_review', section_id=section_id)

    # ── Advance asked_ids ─────────────────────────────────────────────────────
    if next_qid is not None and next_qid not in asked_ids:
        asked_ids.append(next_qid)

    update_session(request, {'basic_answers': basic_answers, 'asked_ids': asked_ids})

    if next_qid is None:
        # END
        if not section.show_confirmation:
            _commit_section_answers(request, section)
            clear_section_session(request)
            return redirect('core:section_done', section_id=section_id)
        return redirect('core:section_review', section_id=section_id)

    if next_qid in pss.get('set_table', {}):
        return redirect('core:section_set_page', section_id=section_id, set_id=next_qid)
    return redirect('core:section_question', section_id=section_id, question_id=next_qid)


# ─────────────────────────────────────────────────────────────────────────────
# 4.  REVIEW
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_review(request, section_id):
    from .interfaces import format_answer_for_display
    section = get_object_or_404(Section, section_id=section_id)
    pss = get_session(request)

    asked_ids     = pss.get('asked_ids', [])
    basic_answers = pss.get('basic_answers', {})
    set_table     = pss.get('set_table', {})

    # Guard: empty session means arrived here without going through section_start
    if not asked_ids:
        return redirect('core:section_start', section_id=section_id)
    question_table = pss.get('question_table', {})

    # Load answer history first so we can attach it per-question
    case_id = pss.get('case_id')
    history_by_qid = {}
    if case_id:
        try:
            _review_case = Case.objects.get(case_id=case_id)
            _review_user = _review_case.user
        except Case.DoesNotExist:
            _review_user = request.user
        for h in (
            AnswerHistory.objects
            .filter(user=_review_user, case_id=case_id, section=section)
            .select_related('question', 'actor')
            .order_by('-confirmed_at')
        ):
            history_by_qid.setdefault(h.question_id, []).append(h)

    # Build ordered rows for the citizen's actual path only.
    # Q-prefixed nodes render as a single row.
    # S-prefixed nodes render as a grouped block (set title + one row per member).
    rows = []
    for node_id in asked_ids:
        if node_id.startswith('S'):
            set_meta = set_table.get(node_id, {})
            member_rows = []
            for m in set_meta.get('members', []):
                qid    = m['question_id']
                answer = basic_answers.get(qid)
                display_answer = format_answer_for_display(
                    m.get('question_type', ''), answer
                )
                member_rows.append({
                    'question_id':   qid,
                    'question_text': m['question_text'],
                    'answer':        display_answer,
                    'change_url':    f'/section/{section_id}/set/{node_id}/',
                    'history':       history_by_qid.get(qid, []),
                })
            rows.append({
                'type':        'set',
                'set_id':      node_id,
                'set_title':   set_meta.get('set_title', ''),
                'member_rows': member_rows,
            })
        else:
            q_meta = question_table.get(node_id, {})
            answer  = basic_answers.get(node_id)
            display_answer = format_answer_for_display(
                q_meta.get('question_type', ''), answer
            )
            rows.append({
                'type':          'question',
                'question_id':   node_id,
                'question_text': q_meta.get('question_text', node_id),
                'answer':        display_answer,
                'change_url':    f'/section/{section_id}/question/{node_id}/',
                'history':       history_by_qid.get(node_id, []),
            })

    context = {
        'section':     section,
        'rows':        rows,
        'confirm_url': f'/section/{section_id}/confirm/',
        'breadcrumbs': _build_crumbs(pss, 'Check your answers'),
        'acting_for':  get_acting_for_name(pss),
    }
    return render(request, 'core/review.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 5.  CONFIRM  (standard sections)
# ─────────────────────────────────────────────────────────────────────────────

def _commit_section_answers(request, section):
    """Persist session answers to DB with full audit trail.

    Shared by section_confirm (explicit review → confirm flow) and the
    auto-save path triggered when section.show_confirmation is False.

    Delta logic:
      changed_qids — in both old and new snapshots, value differs
      removed_qids — in old snapshot but not in new asked_ids
                     (abandoned branch that was previously confirmed)

    All history writes, deletes and inserts are wrapped in a single
    atomic transaction to prevent partial-failure inconsistency.
    """
    pss = get_session(request)

    asked_ids   = pss.get('asked_ids', [])
    raw_answers = pss.get('basic_answers', {})
    case_id     = pss.get('case_id')
    actor_id    = pss.get('actor_id') or request.user.pk
    regime_id   = pss.get('regime_id')
    set_table   = pss.get('set_table', {})

    # Build committed answer set — expand S-nodes to their member question IDs
    new_answers = {}
    for node_id in asked_ids:
        if node_id.startswith('S'):
            member_qids = [
                m['question_id']
                for m in set_table.get(node_id, {}).get('members', [])
            ]
            for qid in member_qids:
                if qid in raw_answers:
                    new_answers[qid] = raw_answers[qid]
        else:
            if node_id in raw_answers:
                new_answers[node_id] = raw_answers[node_id]

    # Resolve related objects
    regime = get_object_or_404(Regime, regime_id=regime_id) if regime_id else section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')
    try:
        case = Case.objects.get(case_id=case_id)
    except Case.DoesNotExist:
        case = _get_or_create_case(request.user, regime)
    try:
        actor = User.objects.get(pk=actor_id)
    except User.DoesNotExist:
        actor = request.user

    # Load previous live answers for this section/case
    previous_qs = Answer.objects.filter(
        user=case.user, case=case, section=section,
    ).select_related('question', 'actor')
    previous_answers = {a.question_id: a for a in previous_qs}

    # Compute delta
    changed_qids = [
        qid for qid in new_answers
        if qid in previous_answers
        and previous_answers[qid].answer != new_answers[qid]
    ]
    removed_qids = [
        qid for qid in previous_answers
        if qid not in new_answers
    ]

    now = timezone.now()

    with transaction.atomic():
        # a) Archive old values for changed and removed questions
        history_records = []
        for qid in changed_qids + removed_qids:
            old = previous_answers[qid]
            history_records.append(AnswerHistory(
                user=case.user,
                actor=old.actor,
                regime=regime,
                case=case,
                section=section,
                question=old.question,
                answer=old.answer,
                confirmed_at=now,
            ))
        if history_records:
            AnswerHistory.objects.bulk_create(history_records)

        # b) Delete all existing answers for this section/case
        Answer.objects.filter(
            user=case.user, case=case, section=section,
        ).delete()

        # c) Bulk-insert new answers
        questions_qs = Question.objects.filter(question_id__in=list(new_answers.keys()))
        questions_map = {q.question_id: q for q in questions_qs}
        new_records = [
            Answer(
                user=case.user,
                actor=actor,
                regime=regime,
                case=case,
                section=section,
                question=questions_map[qid],
                answer=new_answers[qid],
            )
            for qid in new_answers
            if qid in questions_map
        ]
        Answer.objects.bulk_create(new_records)

        # d) Mark section complete
        SectionStatus.objects.update_or_create(
            user=case.user, regime=regime, section=section,
            defaults={'status': 'complete'},
        )


@login_required
@require_POST
def section_confirm(request, section_id):
    """Commit answers to DB via the explicit check-your-answers flow."""
    section = get_object_or_404(Section, section_id=section_id)
    _commit_section_answers(request, section)
    clear_section_session(request)
    return redirect('core:section_done', section_id=section_id)


# ─────────────────────────────────────────────────────────────────────────────
# 6.  TABLE SECTION — LANDING PAGE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_table(request, section_id):
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    # Bootstrap session context if arriving directly (no Layer 1)
    if not pss.get('case_id'):
        case = _get_or_create_case(request.user, regime)
        update_session(request, {
            'user_id':    request.user.pk,
            'actor_id':   request.user.pk,
            'regime_id':  regime.regime_id,
            'case_id':    case.case_id,
            'section_id': section_id,
        })
    else:
        try:
            case = Case.objects.get(case_id=pss['case_id'])
        except Case.DoesNotExist:
            case = _get_or_create_case(request.user, regime)
            update_session(request, {'case_id': case.case_id})

    # ── Column questions ──────────────────────────────────────────────────────
    col_qids = [
        qid.strip()
        for qid in (section.display_question_ids or '').split(';')
        if qid.strip()
    ]
    col_questions = {
        q.question_id: q
        for q in Question.objects.filter(question_id__in=col_qids)
    }
    # Preserve the order defined in display_question_ids
    ordered_columns = [col_questions[qid] for qid in col_qids if qid in col_questions]

    # ── Totals columns ────────────────────────────────────────────────────────
    total_qids = [
        qid.strip()
        for qid in (section.totals_question_ids or '').split(';')
        if qid.strip()
    ]

    # ── Existing rows ─────────────────────────────────────────────────────────
    try:
        answer_table = AnswerTable.objects.get(
            user=case.user, case=case, section=section,
        )
        rows = answer_table.answer  # list of dicts
    except AnswerTable.DoesNotExist:
        rows = []

    # ── Compute totals ────────────────────────────────────────────────────────
    raw_totals = {}
    for qid in total_qids:
        total = 0.0
        for row in rows:
            try:
                total += float(row.get(qid, 0) or 0)
            except (ValueError, TypeError):
                pass
        raw_totals[qid] = total

    # Format totals with comma thousands separator and 2 dp
    totals_formatted = {
        qid: f'{v:,.2f}'
        for qid, v in raw_totals.items()
    }

    # Build totals_row as structured dicts carrying text + alignment
    totals_row = [
        {
            'text':  totals_formatted[q.question_id] if q.question_id in totals_formatted else '',
            'align': 'right' if q.question_type == 'number' else 'left',
        }
        for q in ordered_columns
    ]
    has_totals = any(v['text'] != '' for v in totals_row)

    # ── Build display rows (values in column order) ───────────────────────────
    def _fmt(val, is_numeric):
        """Format number-type values with comma separator and 2 dp; pass others through."""
        if not is_numeric:
            return val if val not in (None, '') else '—'
        try:
            return f'{float(val):,.2f}'
        except (ValueError, TypeError):
            return val if val not in (None, '') else '—'

    is_routed = (section.section_type == 2)
    display_rows = []
    for i, row in enumerate(rows):
        row_dict = {
            'index':  i,
            'values': [
                {
                    'text':  _fmt(row.get(q.question_id), q.question_type == 'number'),
                    'align': 'right' if q.question_type == 'number' else 'left',
                }
                for q in ordered_columns
            ],
            'delete_url': f'/section/{section_id}/table/delete/{i}/',
        }
        if is_routed:
            row_dict['view_url'] = f'/section/{section_id}/table/row-review/{i}/'
        display_rows.append(row_dict)

    add_url = (
        f'/section/{section_id}/table/add-routed/'
        if is_routed
        else f'/section/{section_id}/table/add/'
    )

    context = {
        'section':       section,
        'columns':       ordered_columns,
        'display_rows':  display_rows,
        'totals_row':    totals_row,
        'has_totals':    has_totals,
        'add_url':       add_url,
        'confirm_url':   f'/section/{section_id}/confirm-table/',
        'has_rows':      bool(rows),
        'is_routed':     is_routed,
        'breadcrumbs':   _build_crumbs(pss, section.section_name),
        'acting_for':    get_acting_for_name(pss),
    }
    return render(request, 'core/table_landing.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 7.  TABLE ROW ADD
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_table_add(request, section_id):
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    col_qids = [
        qid.strip()
        for qid in (section.display_question_ids or '').split(';')
        if qid.strip()
    ]
    col_questions_qs = Question.objects.filter(question_id__in=col_qids)
    col_questions = {q.question_id: q for q in col_questions_qs}
    ordered_columns = [col_questions[qid] for qid in col_qids if qid in col_questions]

    if request.method == 'POST':
        # Build row dict from POST
        row = {}
        for q in ordered_columns:
            if q.question_type == 'checkbox':
                val = request.POST.getlist(q.question_id)
            else:
                val = request.POST.get(q.question_id, '').strip()
            row[q.question_id] = val

        # Resolve case
        case_id   = pss.get('case_id')
        actor_id  = pss.get('actor_id') or request.user.pk
        try:
            case = Case.objects.get(case_id=case_id)
        except Case.DoesNotExist:
            case = _get_or_create_case(request.user, regime)
            update_session(request, {'case_id': case.case_id})
        try:
            actor = User.objects.get(pk=actor_id)
        except User.DoesNotExist:
            actor = request.user

        # Append row to AnswerTable
        answer_table, _ = AnswerTable.objects.get_or_create(
            user=case.user, case=case, section=section,
            defaults={'actor': actor, 'regime': regime, 'answer': []},
        )
        answer_table.answer.append(row)
        answer_table.save(update_fields=['answer', 'updated_at'])

        # At least one row → in_progress (confirm will set complete)
        SectionStatus.objects.update_or_create(
            user=case.user, regime=regime, section=section,
            defaults={'status': 'in_progress'},
        )

        return redirect('core:section_table', section_id=section_id)

    # GET — build column dicts with options pre-split so the template
    # doesn't need any custom filters
    column_dicts = [
        {
            'question_id':   q.question_id,
            'question_text': q.question_text,
            'question_type': q.question_type,
            'hint':          q.hint or '',
            'options':       [o.strip() for o in (q.options or '').split(';') if o.strip()],
        }
        for q in ordered_columns
    ]
    context = {
        'section':    section,
        'columns':    column_dicts,
        'back_url':   f'/section/{section_id}/table/',
        'acting_for': get_acting_for_name(pss),
    }
    return render(request, 'core/table_add.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 8.  TABLE ROW ADD — ROUTED (section_type=2)
# ─────────────────────────────────────────────────────────────────────────────

def _table_row_ns_get(request, section_id):
    """Return the _table_row namespace dict for section_id (may be empty)."""
    return (request.session.get('_table_row') or {}).get(section_id) or {}


def _table_row_ns_set(request, section_id, row_data):
    """Write row_data back into _table_row[section_id] in the session."""
    ns = request.session.get('_table_row') or {}
    ns[section_id] = row_data
    request.session['_table_row'] = ns
    request.session.modified = True


def _table_row_ns_clear(request, section_id):
    """Remove _table_row[section_id] from the session."""
    ns = request.session.get('_table_row') or {}
    ns.pop(section_id, None)
    request.session['_table_row'] = ns
    request.session.modified = True


@login_required
def section_table_routed_add(request, section_id):
    """Initialise a fresh row journey and redirect to the first node."""
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    routing_rows = (
        Routing.objects
        .filter(section=section)
        .order_by('order_in_section')
    )
    tables = _build_section_tables(routing_rows)
    if not tables['first_node']:
        return redirect('core:section_table', section_id=section_id)

    # Bootstrap case if needed
    if not pss.get('case_id'):
        case = _get_or_create_case(request.user, regime)
        update_session(request, {'case_id': case.case_id})

    # Initialise fresh row namespace (row_index=None → new row)
    _table_row_ns_set(request, section_id, {
        '_asked_ids': [tables['first_node']],
        '_row_index': None,
    })

    first = tables['first_node']
    if first in tables['set_table']:
        return redirect('core:section_table_routed_question',
                        section_id=section_id, question_or_set_id=first)
    return redirect('core:section_table_routed_question',
                    section_id=section_id, question_or_set_id=first)


@login_required
def section_table_routed_change(request, section_id, row_index):
    """Initialise a change-row journey by pre-populating the session from the saved row."""
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    case_id = pss.get('case_id')
    try:
        case = Case.objects.get(case_id=case_id)
    except Case.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    try:
        answer_table = AnswerTable.objects.get(
            user=case.user, case=case, section=section,
        )
    except AnswerTable.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    rows = answer_table.answer
    if row_index < 0 or row_index >= len(rows):
        return redirect('core:section_table', section_id=section_id)

    saved_row = rows[row_index]

    routing_rows = (
        Routing.objects
        .filter(section=section)
        .order_by('order_in_section')
    )
    tables = _build_section_tables(routing_rows)
    if not tables['first_node']:
        return redirect('core:section_table', section_id=section_id)

    routing_table   = tables['routing_table']
    all_node_ids    = tables['all_node_ids']
    question_table  = tables['question_table']
    set_table       = tables['set_table']
    question_to_set = tables['question_to_set']

    # Reconstruct the asked_ids path by replaying routing on saved answers
    asked_ids = []
    node = tables['first_node']
    while node is not None:
        asked_ids.append(node)
        # Build combined answers dict for routing resolution
        all_answers = dict(saved_row)
        routing_answer = _resolve_routing_answer(routing_table, node, all_answers)
        next_node, found = _evaluate_routing(routing_table, node, routing_answer)
        if not found:
            break
        node = next_node

    # Seed session namespace with saved answers + metadata
    row_data = dict(saved_row)
    row_data['_asked_ids'] = asked_ids
    row_data['_row_index'] = row_index
    _table_row_ns_set(request, section_id, row_data)

    first = tables['first_node']
    return redirect('core:section_table_routed_question',
                    section_id=section_id, question_or_set_id=first)


@login_required
def section_table_routed_question(request, section_id, question_or_set_id):
    """Workhorse view: render/process one question or set page within a row journey."""
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    # Bootstrap case if needed
    if not pss.get('case_id'):
        case = _get_or_create_case(request.user, regime)
        update_session(request, {'case_id': case.case_id})
    else:
        try:
            case = Case.objects.get(case_id=pss['case_id'])
        except Case.DoesNotExist:
            case = _get_or_create_case(request.user, regime)
            update_session(request, {'case_id': case.case_id})

    routing_rows = (
        Routing.objects
        .filter(section=section)
        .order_by('order_in_section')
    )
    tables = _build_section_tables(routing_rows)
    if not tables['first_node']:
        return redirect('core:section_table', section_id=section_id)

    routing_table   = tables['routing_table']
    question_table  = tables['question_table']
    set_table       = tables['set_table']
    question_to_set = tables['question_to_set']

    node_id  = question_or_set_id
    is_set   = node_id in set_table
    is_q     = node_id in question_table

    if not is_set and not is_q:
        return redirect('core:section_table', section_id=section_id)

    row_data  = _table_row_ns_get(request, section_id)
    asked_ids = row_data.get('_asked_ids', [node_id])
    row_index = row_data.get('_row_index')  # None = new row, int = change

    # Back-navigation: truncate asked_ids if re-visiting an earlier node
    if node_id in asked_ids:
        idx = asked_ids.index(node_id)
        asked_ids = asked_ids[:idx + 1]
        row_data['_asked_ids'] = asked_ids
        _table_row_ns_set(request, section_id, row_data)

    # Determine back URL
    if len(asked_ids) > 1:
        prev_node = asked_ids[-2]
        back_url  = f'/section/{section_id}/table/add-routed/{prev_node}/?back=1'
    else:
        back_url  = f'/section/{section_id}/table/'

    if request.method == 'GET' and request.GET.get('back'):
        # Back button pressed — just render this node with pre-filled values
        pass

    if request.method == 'POST':
        if is_set:
            # Collect field values for all set members
            members = set_table[node_id]['members']
            field_values = {}
            for m in members:
                qid = m['question_id']
                if m['question_type'] == 'checkbox':
                    field_values[qid] = request.POST.getlist(qid)
                elif m['question_type'] == 'address':
                    field_values[qid] = {
                        'line1':    request.POST.get(f'address_line1_{qid}', '').strip(),
                        'line2':    request.POST.get(f'address_line2_{qid}', '').strip(),
                        'city':     request.POST.get(f'address_city_{qid}', '').strip(),
                        'county':   request.POST.get(f'address_county_{qid}', '').strip(),
                        'postcode': request.POST.get(f'address_postcode_{qid}', '').strip(),
                    }
                else:
                    field_values[qid] = request.POST.get(qid, '').strip()

            # Routing answer: resolve via condition_question_id if set
            all_answers = {**{k: v for k, v in row_data.items() if not k.startswith('_')},
                           **field_values}
            routing_answer = _resolve_routing_answer(routing_table, node_id, all_answers)
            next_node, found = _evaluate_routing(routing_table, node_id, routing_answer)

            if not found:
                logger.error(
                    'section_table_routed_question: no matching route for section=%s '
                    'node=%s routing_answer=%r — routing data error, row not committed.',
                    section_id, node_id, routing_answer,
                )
                meta = set_table[node_id]
                member_dicts = []
                for m in meta['members']:
                    qid = m['question_id']
                    mdict = {
                        'question_id':   qid,
                        'question_text': m['question_text'],
                        'question_type': m['question_type'],
                        'hint':          m['hint'],
                        'options':       [o.strip() for o in m['options'].split(';') if o.strip()],
                        'required':      m['required'],
                        'current_value': field_values.get(qid, ''),
                    }
                    if m['question_type'] == 'address':
                        src = field_values.get(qid) or {}
                        mdict['address_parts'] = {
                            'line1':    src.get('line1', '') if isinstance(src, dict) else '',
                            'line2':    src.get('line2', '') if isinstance(src, dict) else '',
                            'city':     src.get('city', '') if isinstance(src, dict) else '',
                            'county':   src.get('county', '') if isinstance(src, dict) else '',
                            'postcode': src.get('postcode', '') if isinstance(src, dict) else '',
                        }
                    member_dicts.append(mdict)
                context = {
                    'section':    section,
                    'set_id':     node_id,
                    'set_title':  meta['set_title'],
                    'set_hint':   meta['set_hint'],
                    'members':    member_dicts,
                    'back_url':   back_url,
                    'acting_for': get_acting_for_name(pss),
                    'routing_error': (
                        'There is a configuration problem with this section. '
                        'Your answer could not be processed. Please contact support.'
                    ),
                }
                return render(request, 'core/table_routed_set.html', context)

            # Save field values into row_data
            row_data.update(field_values)
        else:
            q_meta = question_table[node_id]
            if q_meta['question_type'] == 'checkbox':
                answer = request.POST.getlist(node_id)
            else:
                answer = request.POST.get(node_id, '').strip()

            all_answers = {**{k: v for k, v in row_data.items() if not k.startswith('_')},
                           node_id: answer}
            routing_answer = _resolve_routing_answer(routing_table, node_id, all_answers)
            next_node, found = _evaluate_routing(routing_table, node_id, routing_answer)

            if not found:
                logger.error(
                    'section_table_routed_question: no matching route for section=%s '
                    'node=%s routing_answer=%r — routing data error, row not committed.',
                    section_id, node_id, routing_answer,
                )
                question_dict = {
                    'question_id':   node_id,
                    'question_text': q_meta['question_text'],
                    'question_type': q_meta['question_type'],
                    'guidance':      q_meta['guidance'],
                    'hint':          q_meta['hint'],
                    'options':       [o.strip() for o in q_meta['options'].split(';') if o.strip()],
                    'current_value': answer,
                }
                context = {
                    'section':    section,
                    'question':   question_dict,
                    'back_url':   back_url,
                    'acting_for': get_acting_for_name(pss),
                    'routing_error': (
                        'There is a configuration problem with this section. '
                        'Your answer could not be processed. Please contact support.'
                    ),
                }
                return render(request, 'core/table_routed_question.html', context)

            row_data[node_id] = answer

        if next_node is None:
            # END — commit row, pruning to asked_ids to drop stale answers from diverged paths.
            # S-nodes store their member answers under each member's own question_id, not the
            # set's node ID — so expand asked_ids to include member question_ids before filtering.
            asked_ids = row_data.get('_asked_ids', [])
            if asked_ids:
                allowed_keys: set = set()
                for _node in asked_ids:
                    if _node in set_table:
                        allowed_keys.update(m['question_id'] for m in set_table[_node]['members'])
                    else:
                        allowed_keys.add(_node)
                row_to_save = {k: v for k, v in row_data.items()
                               if not k.startswith('_') and k in allowed_keys}
            else:
                row_to_save = {k: v for k, v in row_data.items() if not k.startswith('_')}
            _commit_table_row(request, section, case, regime, pss, row_to_save, row_index)
            _table_row_ns_clear(request, section_id)
            return redirect('core:section_table', section_id=section_id)

        # Advance to next node
        if next_node not in asked_ids:
            asked_ids.append(next_node)
        row_data['_asked_ids'] = asked_ids
        _table_row_ns_set(request, section_id, row_data)

        return redirect('core:section_table_routed_question',
                        section_id=section_id, question_or_set_id=next_node)

    # ── GET ───────────────────────────────────────────────────────────────────
    if is_set:
        meta = set_table[node_id]
        member_dicts = []
        for m in meta['members']:
            qid = m['question_id']
            mdict = {
                'question_id':   qid,
                'question_text': m['question_text'],
                'question_type': m['question_type'],
                'hint':          m['hint'],
                'options':       [o.strip() for o in m['options'].split(';') if o.strip()],
                'required':      m['required'],
                'current_value': row_data.get(qid, ''),
            }
            if m['question_type'] == 'address':
                src = row_data.get(qid) or {}
                mdict['address_parts'] = {
                    'line1':    src.get('line1', '') if isinstance(src, dict) else '',
                    'line2':    src.get('line2', '') if isinstance(src, dict) else '',
                    'city':     src.get('city', '') if isinstance(src, dict) else '',
                    'county':   src.get('county', '') if isinstance(src, dict) else '',
                    'postcode': src.get('postcode', '') if isinstance(src, dict) else '',
                }
            member_dicts.append(mdict)
        context = {
            'section':    section,
            'set_id':     node_id,
            'set_title':  meta['set_title'],
            'set_hint':   meta['set_hint'],
            'members':    member_dicts,
            'back_url':   back_url,
            'acting_for': get_acting_for_name(pss),
        }
        return render(request, 'core/table_routed_set.html', context)
    else:
        q_meta = question_table[node_id]
        question_dict = {
            'question_id':   node_id,
            'question_text': q_meta['question_text'],
            'question_type': q_meta['question_type'],
            'guidance':      q_meta['guidance'],
            'hint':          q_meta['hint'],
            'options':       [o.strip() for o in q_meta['options'].split(';') if o.strip()],
            'current_value': row_data.get(node_id, ''),
        }
        context = {
            'section':    section,
            'question':   question_dict,
            'back_url':   back_url,
            'acting_for': get_acting_for_name(pss),
        }
        return render(request, 'core/table_routed_question.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 9.  TABLE ROW DETAIL (read-only, section_type=2)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_table_row_detail(request, section_id, row_index):
    """Read-only display of the extra (non-display-column) answers for one row."""
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    case_id = pss.get('case_id')
    try:
        case = Case.objects.get(case_id=case_id)
    except Case.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    try:
        answer_table = AnswerTable.objects.get(
            user=case.user, case=case, section=section,
        )
    except AnswerTable.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    rows = answer_table.answer
    if row_index < 0 or row_index >= len(rows):
        return redirect('core:section_table', section_id=section_id)

    row = rows[row_index]

    display_qids = {
        qid.strip()
        for qid in (section.display_question_ids or '').split(';')
        if qid.strip()
    }
    extra_qids = [qid for qid in row if qid not in display_qids]
    q_map = {
        q.question_id: q
        for q in Question.objects.filter(question_id__in=extra_qids)
    }
    extras = [
        {
            'question_text': q_map[qid].question_text if qid in q_map else qid,
            'answer':        row.get(qid, ''),
        }
        for qid in extra_qids
        if qid in q_map
    ]

    from django.urls import reverse
    context = {
        'section':    section,
        'row_number': row_index + 1,
        'extras':     extras,
        'back_url':   reverse('core:section_table', kwargs={'section_id': section_id}),
        'breadcrumbs': _build_crumbs(pss, f'Row {row_index + 1} details'),
        'acting_for': get_acting_for_name(pss),
    }
    return render(request, 'core/table_row_detail.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 10.  TABLE ROW DELETE
# ─────────────────────────────────────────────────────────────────────────────
# 10b.  TABLE ROW REVIEW (check-your-answers for one type-2 row)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_table_row_review(request, section_id, row_index):
    """
    Check-your-answers page for a single type-2 row.

    Replays routing on the saved answers to reconstruct asked_ids, then builds
    the same `rows` list that section_review builds for type-0 sections.
    Renders review.html with confirm_url=None (no confirm step — user picks a
    field to change or goes back to the table).
    """
    from .interfaces import format_answer_for_display
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    case_id = pss.get('case_id')
    try:
        case = Case.objects.get(case_id=case_id)
    except Case.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    try:
        answer_table = AnswerTable.objects.get(user=case.user, case=case, section=section)
    except AnswerTable.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    rows_data = answer_table.answer
    if row_index < 0 or row_index >= len(rows_data):
        return redirect('core:section_table', section_id=section_id)

    saved_row = rows_data[row_index]

    routing_rows = (
        Routing.objects
        .filter(section=section)
        .order_by('order_in_section')
    )
    tables = _build_section_tables(routing_rows)
    if not tables['first_node']:
        return redirect('core:section_table', section_id=section_id)

    routing_table  = tables['routing_table']
    question_table = tables['question_table']
    set_table      = tables['set_table']

    # Reconstruct asked_ids by replaying routing on saved answers
    asked_ids = []
    node = tables['first_node']
    while node is not None:
        asked_ids.append(node)
        routing_answer = _resolve_routing_answer(routing_table, node, dict(saved_row))
        next_node, found = _evaluate_routing(routing_table, node, routing_answer)
        if not found:
            break
        node = next_node

    # Build rows list in the same format expected by review.html
    rows = []
    for node_id in asked_ids:
        amend_url = f'/section/{section_id}/table/amend/{row_index}/{node_id}/'
        if node_id in set_table:
            meta = set_table[node_id]
            member_rows = []
            for m in meta['members']:
                qid    = m['question_id']
                answer = saved_row.get(qid, '')
                member_rows.append({
                    'question_id':   qid,
                    'question_text': m['question_text'],
                    'answer':        format_answer_for_display(m.get('question_type', ''), answer),
                    'change_url':    amend_url,
                    'history':       [],
                })
            rows.append({
                'type':        'set',
                'set_id':      node_id,
                'set_title':   meta.get('set_title', ''),
                'member_rows': member_rows,
            })
        else:
            q_meta = question_table.get(node_id, {})
            answer  = saved_row.get(node_id, '')
            rows.append({
                'type':          'question',
                'question_id':   node_id,
                'question_text': q_meta.get('question_text', node_id),
                'answer':        format_answer_for_display(q_meta.get('question_type', ''), answer),
                'change_url':    amend_url,
                'history':       [],
            })

    from django.urls import reverse as _reverse
    context = {
        'section':     section,
        'rows':        rows,
        'confirm_url': None,
        'back_url':    _reverse('core:section_table', kwargs={'section_id': section_id}),
        'breadcrumbs': _build_crumbs(pss, f'Record {row_index + 1}'),
        'acting_for':  get_acting_for_name(pss),
    }
    return render(request, 'core/review.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 10c.  TABLE ROW AMEND (per-node entry point for type-2 row amendment)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_table_routed_amend(request, section_id, row_index, node_id):
    """
    Entry point to amend a specific node in a saved type-2 row.

    Like section_table_routed_change but:
    - Redirects to node_id specifically (not always first_node).
    - Truncates asked_ids at node_id before seeding the session, so that
      the re-walk from node_id builds the correct new tail.  This ensures
      stale downstream answers (from the old routing branch) are dropped at
      commit time by the asked_ids pruning logic in section_table_routed_question.
    """
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    case_id = pss.get('case_id')
    try:
        case = Case.objects.get(case_id=case_id)
    except Case.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    try:
        answer_table = AnswerTable.objects.get(user=case.user, case=case, section=section)
    except AnswerTable.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    rows_data = answer_table.answer
    if row_index < 0 or row_index >= len(rows_data):
        return redirect('core:section_table', section_id=section_id)

    saved_row = rows_data[row_index]

    routing_rows = (
        Routing.objects
        .filter(section=section)
        .order_by('order_in_section')
    )
    tables = _build_section_tables(routing_rows)
    if not tables['first_node']:
        return redirect('core:section_table', section_id=section_id)

    routing_table = tables['routing_table']

    # Replay routing to reconstruct the full asked_ids path
    asked_ids = []
    node = tables['first_node']
    while node is not None:
        asked_ids.append(node)
        routing_answer = _resolve_routing_answer(routing_table, node, dict(saved_row))
        next_node, found = _evaluate_routing(routing_table, node, routing_answer)
        if not found:
            break
        node = next_node

    # Truncate at node_id: keep only nodes up to and including it.
    # Nodes after node_id were on the old path; the re-walk from node_id
    # will append the correct new nodes, so stale ones are not present
    # in asked_ids at commit time.
    if node_id in asked_ids:
        idx = asked_ids.index(node_id)
        asked_ids = asked_ids[:idx + 1]

    # Seed session with saved answers, truncated path, and row index
    row_data = dict(saved_row)
    row_data['_asked_ids'] = asked_ids
    row_data['_row_index'] = row_index
    _table_row_ns_set(request, section_id, row_data)

    return redirect('core:section_table_routed_question',
                    section_id=section_id, question_or_set_id=node_id)


# ─────────────────────────────────────────────────────────────────────────────
# 10.  TABLE ROW DELETE

@login_required
def section_table_delete(request, section_id, row_index):
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    case_id = pss.get('case_id')
    try:
        case = Case.objects.get(case_id=case_id)
    except Case.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    try:
        answer_table = AnswerTable.objects.get(
            user=case.user, case=case, section=section,
        )
    except AnswerTable.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    rows = answer_table.answer
    if 0 <= row_index < len(rows):
        del rows[row_index]
        answer_table.answer = rows
        answer_table.save(update_fields=['answer', 'updated_at'])

    # If no rows remain, revert section to in_progress
    if not rows:
        SectionStatus.objects.update_or_create(
            user=case.user, regime=regime, section=section,
            defaults={'status': 'in_progress'},
        )

    return redirect('core:section_table', section_id=section_id)


# ─────────────────────────────────────────────────────────────────────────────
# 9.  TABLE CONFIRM
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def section_confirm_table(request, section_id):
    """Snapshot the current table state to history and mark section complete."""
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()
    if regime is None:
        raise Http404('Section is not yet assigned to a regime.')

    case_id  = pss.get('case_id')
    actor_id = pss.get('actor_id') or request.user.pk
    try:
        case = Case.objects.get(case_id=case_id)
    except Case.DoesNotExist:
        case = _get_or_create_case(request.user, regime)
    try:
        actor = User.objects.get(pk=actor_id)
    except User.DoesNotExist:
        actor = request.user

    now = timezone.now()

    with transaction.atomic():
        try:
            answer_table = AnswerTable.objects.get(
                user=case.user, case=case, section=section,
            )
            # Archive current rows as a history snapshot
            AnswerTableHistory.objects.create(
                user=case.user,
                actor=actor,
                regime=regime,
                case=case,
                section=section,
                answer=answer_table.answer,
                confirmed_at=now,
            )
        except AnswerTable.DoesNotExist:
            pass   # Nothing to snapshot

        SectionStatus.objects.update_or_create(
            user=case.user, regime=regime, section=section,
            defaults={'status': 'complete'},
        )

    return redirect('core:section_done', section_id=section_id)


# ─────────────────────────────────────────────────────────────────────────────
# 10.  SECTION DONE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_done(request, section_id):
    section = get_object_or_404(Section, section_id=section_id)
    pss = get_session(request)

    # ── Post-confirm hook: dept views can redirect to a bespoke handler ───────
    # Set request.session['post_confirm_redirect'] = '/path/' before entering
    # the section journey; it is popped here so it fires exactly once.
    post_confirm_redirect = request.session.pop('post_confirm_redirect', None)
    if post_confirm_redirect:
        return redirect(post_confirm_redirect)

    user_id           = pss.get('user_id')
    regime_id         = pss.get('regime_id')
    schedule_id       = pss.get('schedule_id')
    regime_home_url   = pss.get('regime_home_url')
    schedule_list_url = pss.get('schedule_list_url')
    return_url        = pss.get('return_url')

    if user_id and regime_id and regime_home_url:
        # All sections in the regime complete?
        all_complete = not SectionStatus.objects.filter(
            user_id=user_id,
            regime_id=regime_id,
        ).exclude(status='complete').exists()

        if all_complete:
            return redirect(regime_home_url)

        # All sections in the current schedule complete?
        if schedule_id and schedule_list_url:
            schedule_complete = not SectionStatus.objects.filter(
                user_id=user_id,
                regime_id=regime_id,
                section__schedule_id=schedule_id,
            ).exclude(status='complete').exists()

            if schedule_complete:
                return redirect(schedule_list_url)

        if return_url:
            return redirect(return_url)

    if return_url:
        return redirect(return_url)

    logger.warning(
        'section_done: no return_url in session for section %s (user %s) — '
        'falling back to /. Layer 1 must set return_url before entering Layer 2.',
        section_id, request.user,
    )
    return redirect('/')


# ─────────────────────────────────────────────────────────────────────────────
# 11.  QUESTION SET PAGE  (stub — multi-field screen for a QuestionSet node)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_set_page(request, section_id, set_id):
    """
    GET  — render a multi-field set page.
    POST — validate all member fields, store answers, advance routing.
    """
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)

    set_table     = pss.get('set_table', {})
    basic_answers = pss.get('basic_answers', {})
    asked_ids     = pss.get('asked_ids', [])

    set_meta = set_table.get(set_id)
    if not set_meta:
        # Session lost or set not in this section — restart
        return redirect('core:section_start', section_id=section_id)

    if request.method == 'POST':
        return _process_set_answer(request, section, section_id, set_id, set_meta, pss)

    # ── GET ───────────────────────────────────────────────────────────────────
    # Backtrack: if arriving at a set already on the path, truncate asked_ids
    if set_id in asked_ids:
        idx = asked_ids.index(set_id)
        asked_ids = asked_ids[:idx + 1]
        update_session(request, {'asked_ids': asked_ids})

    # ── Back link ─────────────────────────────────────────────────────────────
    if len(asked_ids) > 1 and set_id == asked_ids[-1]:
        prev_node = asked_ids[-2]
        if prev_node in set_table:
            back_url = f'/section/{section_id}/set/{prev_node}/'
        else:
            back_url = f'/section/{section_id}/question/{prev_node}/'
    else:
        back_url = f'/section/{section_id}/start/'

    # ── Build field list with current answers ─────────────────────────────────
    fields = []
    for m in set_meta['members']:
        qid = m['question_id']
        options = [o.strip() for o in m['options'].split(';') if o.strip()]
        current = basic_answers.get(qid)
        field_dict = {
            'question_id':    qid,
            'question_text':  m['question_text'],
            'question_type':  m['question_type'],
            'hint':           m['hint'],
            'options':        options,
            'required':       m['required'],
            'current_answer': current,
            'error':          None,
        }
        if m['question_type'] == 'date':
            parsed = current
            if isinstance(parsed, str):
                try:
                    import json
                    parsed = json.loads(parsed)
                except (ValueError, TypeError):
                    parsed = {}
            field_dict['date_parts'] = {
                'day':   parsed.get('day', '') if isinstance(parsed, dict) else '',
                'month': parsed.get('month', '') if isinstance(parsed, dict) else '',
                'year':  parsed.get('year', '') if isinstance(parsed, dict) else '',
            }
        if m['question_type'] == 'personal_name':
            src = current if isinstance(current, dict) else {}
            field_dict['name_parts'] = {
                'title':       src.get('title', ''),
                'first_name':  src.get('first_name', ''),
                'middle_name': src.get('middle_name', ''),
                'last_name':   src.get('last_name', ''),
            }
        if m['question_type'] == 'address':
            src = current if isinstance(current, dict) else {}
            field_dict['address_parts'] = {
                'line1':    src.get('line1', ''),
                'line2':    src.get('line2', ''),
                'city':     src.get('city', ''),
                'county':   src.get('county', ''),
                'postcode': src.get('postcode', ''),
            }
        fields.append(field_dict)

    context = {
        'section':     section,
        'set_id':      set_id,
        'set_title':   set_meta['set_title'],
        'set_hint':    set_meta['set_hint'],
        'fields':      fields,
        'errors':      [],
        'back_url':    back_url,
        'breadcrumbs': _build_crumbs(pss, section.section_name),
        'acting_for':  get_acting_for_name(pss),
    }
    return render(request, 'core/question_set.html', context)


def _process_set_answer(request, section, section_id, set_id, set_meta, pss):
    """Handle POST for section_set_page — validate all fields, store, advance."""
    basic_answers = pss.get('basic_answers', {})
    asked_ids     = pss.get('asked_ids', [])
    routing_table = pss.get('routing_table', [])
    set_table     = pss.get('set_table', {})

    # ── Extract and validate all member fields ────────────────────────────────
    field_values = {}
    field_errors = {}
    for m in set_meta['members']:
        qid = m['question_id']
        if m['question_type'] == 'checkbox':
            value = request.POST.getlist(qid)
        elif m['question_type'] == 'date':
            value = {
                'day':   request.POST.get(f'{qid}_day', '').strip(),
                'month': request.POST.get(f'{qid}_month', '').strip(),
                'year':  request.POST.get(f'{qid}_year', '').strip(),
            }
        elif m['question_type'] == 'personal_name':
            value = {
                'title':       request.POST.get(f'personal_name_title_{qid}', '').strip(),
                'first_name':  request.POST.get(f'personal_name_first_name_{qid}', '').strip(),
                'middle_name': request.POST.get(f'personal_name_middle_name_{qid}', '').strip(),
                'last_name':   request.POST.get(f'personal_name_last_name_{qid}', '').strip(),
            }
        elif m['question_type'] == 'address':
            value = {
                'line1':    request.POST.get(f'address_line1_{qid}', '').strip(),
                'line2':    request.POST.get(f'address_line2_{qid}', '').strip(),
                'city':     request.POST.get(f'address_city_{qid}', '').strip(),
                'county':   request.POST.get(f'address_county_{qid}', '').strip(),
                'postcode': request.POST.get(f'address_postcode_{qid}', '').strip(),
            }
        else:
            value = request.POST.get(qid, '').strip()
        if m['required']:
            if m['question_type'] == 'personal_name':
                sub_errors = []
                if not value.get('first_name'):
                    sub_errors.append('Enter a first name')
                if not value.get('last_name'):
                    sub_errors.append('Enter a last name')
                if sub_errors:
                    field_errors[qid] = ' / '.join(sub_errors)
            elif m['question_type'] == 'address':
                sub_errors = []
                if not value.get('line1'):
                    sub_errors.append('Enter the first line of the address')
                if not value.get('city'):
                    sub_errors.append('Enter a town or city')
                if not value.get('postcode'):
                    sub_errors.append('Enter a postcode')
                if sub_errors:
                    field_errors[qid] = ' / '.join(sub_errors)
            elif not value and value != 0:
                field_errors[qid] = 'Enter ' + m['question_text'].lower().rstrip('?').rstrip('.')
        field_values[qid] = value

    # ── Re-render with errors if any field failed ─────────────────────────────
    if field_errors:
        if len(asked_ids) > 1 and set_id == asked_ids[-1]:
            prev_node = asked_ids[-2]
            back_url = (
                f'/section/{section_id}/set/{prev_node}/'
                if prev_node in set_table
                else f'/section/{section_id}/question/{prev_node}/'
            )
        else:
            back_url = f'/section/{section_id}/start/'

        fields = []
        for m in set_meta['members']:
            qid = m['question_id']
            options = [o.strip() for o in m['options'].split(';') if o.strip()]
            current = field_values.get(qid)
            field_dict = {
                'question_id':    qid,
                'question_text':  m['question_text'],
                'question_type':  m['question_type'],
                'hint':           m['hint'],
                'options':        options,
                'required':       m['required'],
                'current_answer': current,
                'error':          field_errors.get(qid),
            }
            if m['question_type'] == 'date':
                field_dict['date_parts'] = {
                    'day':   current.get('day', '') if isinstance(current, dict) else '',
                    'month': current.get('month', '') if isinstance(current, dict) else '',
                    'year':  current.get('year', '') if isinstance(current, dict) else '',
                }
            if m['question_type'] == 'personal_name':
                src = current if isinstance(current, dict) else {}
                field_dict['name_parts'] = {
                    'first_name':  src.get('first_name', ''),
                    'middle_name': src.get('middle_name', ''),
                    'last_name':   src.get('last_name', ''),
                }
            if m['question_type'] == 'address':
                src = current if isinstance(current, dict) else {}
                field_dict['address_parts'] = {
                    'line1':    src.get('line1', ''),
                    'line2':    src.get('line2', ''),
                    'city':     src.get('city', ''),
                    'county':   src.get('county', ''),
                    'postcode': src.get('postcode', ''),
                }
            fields.append(field_dict)

        error_summary = [
            {'qid': qid, 'message': msg}
            for qid, msg in field_errors.items()
        ]

        context = {
            'section':     section,
            'set_id':      set_id,
            'set_title':   set_meta['set_title'],
            'set_hint':    set_meta['set_hint'],
            'fields':      fields,
            'errors':      error_summary,
            'back_url':    back_url,
            'breadcrumbs': _build_crumbs(pss, section.section_name),
            'acting_for':  get_acting_for_name(pss),
        }
        return render(request, 'core/question_set.html', context)

    # ── All valid — store answers into session ────────────────────────────────
    for qid, value in field_values.items():
        basic_answers[qid] = value

    # Ensure set node is in asked_ids
    if set_id not in asked_ids:
        asked_ids.append(set_id)

    # ── Evaluate routing ──────────────────────────────────────────────────────
    # Resolve which answer drives routing for this set node.
    # field_values contains all answers just submitted; merge with basic_answers
    # so condition_question_id can reference any answered question.
    routing_answer = _resolve_routing_answer(
        routing_table, set_id, {**basic_answers, **field_values}
    )
    next_node, found = _evaluate_routing(routing_table, set_id, routing_answer)

    if not found:
        update_session(request, {'basic_answers': basic_answers, 'asked_ids': asked_ids})
        return redirect('core:section_review', section_id=section_id)

    if next_node is not None and next_node not in asked_ids:
        asked_ids.append(next_node)

    update_session(request, {'basic_answers': basic_answers, 'asked_ids': asked_ids})

    if next_node is None:
        return redirect('core:section_review', section_id=section_id)
    if next_node in set_table:
        return redirect('core:section_set_page', section_id=section_id, set_id=next_node)
    return redirect('core:section_question', section_id=section_id, question_id=next_node)
