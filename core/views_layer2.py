"""
Layer 2: Section Processing Engine
===================================
Everything that happens inside a Section once a citizen has selected it.

Responsibility boundary
  Layer 1 (not yet built) gets the citizen to the right section and
  sets the outer PSS session context (user_id, actor_id, regime_id,
  case_id, schedule_id).

  Layer 2 (this file) takes over at section_start and owns the full
  journey:  start → question(s) → review → confirm → done.
  Table sections follow: table landing → add/delete rows → confirm → done.

  The section_id in the URL is the canonical source of truth for which
  section is being processed.  Session carries in-flight state.
"""

import logging
import uuid

from django.contrib.auth.decorators import login_required
from django.db import transaction
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
    Regime,
    Routing,
    Schedule,
    Section,
    SectionStatus,
    User,
)
from .session import clear_section_session, get_session, update_session


# ── Routing evaluation helper ─────────────────────────────────────────────────

_UNSET = object()   # sentinel: "no route found yet"


def _evaluate_routing(routing_table, question_id, answer):
    """Find the next question_id for a given question and answer.

    Returns (next_question_id, found):
      next_question_id — the routing target, or None meaning END
      found            — False if no matching route exists (data error)

    Matching rules:
    - Conditional rows (answer_value not None) are checked first.
      answer_value may be semicolon-delimited; any match is sufficient.
      Comparison is case-insensitive.  answer may be a list (checkbox).
    - If no conditional row matches, the unconditional row (answer_value
      None) is used as fallback.
    """
    conditional_next = _UNSET
    unconditional_next = _UNSET

    for row in routing_table:
        if row['current_question_id'] != question_id:
            continue
        if row['answer_value'] is not None:
            allowed = {v.strip().lower() for v in str(row['answer_value']).split(';')}
            if isinstance(answer, list):
                is_match = any(v.strip().lower() in allowed for v in answer)
            else:
                is_match = str(answer).strip().lower() in allowed
            if is_match:
                conditional_next = row['next_question_id']
                break   # first conditional match wins
        else:
            unconditional_next = row['next_question_id']   # last unconditional wins

    if conditional_next is not _UNSET:
        return conditional_next, True
    if unconditional_next is not _UNSET:
        return unconditional_next, True
    return None, False


# ── Breadcrumb helper ────────────────────────────────────────────────────────

def _build_crumbs(pss, regime, section, last_label=None):
    """Build breadcrumb trail: base crumbs from session + regime + (schedule) + section."""
    crumbs = list(pss.get('breadcrumbs', []))
    crumbs.append({'label': regime.regime_name, 'url': pss.get('return_url')})
    schedule_id = pss.get('schedule_id')
    if schedule_id:
        try:
            schedule = Schedule.objects.get(schedule_id=schedule_id)
            crumbs.append({'label': schedule.schedule_name, 'url': None})
        except Schedule.DoesNotExist:
            pass
    crumbs.append({'label': last_label or section.section_name, 'url': None})
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

    # ── Build routing table ───────────────────────────────────────────────────
    routing_rows = (
        Routing.objects
        .filter(section=section)
        .order_by('order_in_section')
        .select_related('current_question', 'next_question')
    )
    routing_table = [
        {
            'current_question_id': row.current_question_id,
            'answer_value': row.answer_value,
            'next_question_id': row.next_question_id,   # None = END
        }
        for row in routing_rows
    ]

    # ── Build question metadata table ─────────────────────────────────────────
    question_ids_in_section = list(
        dict.fromkeys(r['current_question_id'] for r in routing_table)
    )
    questions = Question.objects.filter(question_id__in=question_ids_in_section)
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

    # ── First question is the one with lowest order_in_section ────────────────
    first_question_id = routing_rows.first().current_question_id if routing_rows.exists() else None
    if not first_question_id:
        # No routing configured — treat as done
        return redirect('core:section_done', section_id=section_id)

    # ── Load confirmed answers from DB ────────────────────────────────────────
    existing_answers = Answer.objects.filter(
        user=request.user, case=case, section=section,
        question_id__in=question_ids_in_section,
    )
    basic_answers = {a.question_id: a.answer for a in existing_answers}

    # ── Determine asked_ids and entry point ───────────────────────────────────
    # Re-entry (answers exist): reconstruct asked_ids in routing order from the
    # DB — only questions the citizen actually answered — then go to review.
    # Fresh start: seed with first question only and go to first question.
    if basic_answers:
        asked_ids = [
            qid for qid in question_ids_in_section
            if qid in basic_answers
        ]
        go_to_review = True
    else:
        asked_ids = [first_question_id]
        go_to_review = False

    # ── Update section status ─────────────────────────────────────────────────
    ss, _ = SectionStatus.objects.get_or_create(
        user=request.user, regime=regime, section=section,
        defaults={'status': 'not_started'},
    )
    if ss.status == 'not_started':
        ss.status = 'in_progress'
        ss.save(update_fields=['status'])

    # ── Write everything to session ───────────────────────────────────────────
    update_session(request, {
        'user_id':        request.user.pk,
        'actor_id':       actor_id,
        'regime_id':      regime.regime_id,
        'case_id':        case.case_id,
        'section_id':     section_id,
        'routing_table':  routing_table,
        'question_table': question_table,
        'asked_ids':      asked_ids,
        'basic_answers':  basic_answers,
    })

    if go_to_review:
        return redirect('core:section_review', section_id=section_id)
    return redirect('core:section_question', section_id=section_id, question_id=first_question_id)


# ─────────────────────────────────────────────────────────────────────────────
# 2 & 3.  QUESTION VIEW  (GET = render, includes backtrack; POST = process)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_question(request, section_id, question_id):
    section = get_object_or_404(Section, section_id=section_id)
    pss = get_session(request)
    regime = section.get_regime()

    question_table = pss.get('question_table', {})
    q_meta = question_table.get(question_id)
    if not q_meta:
        # Session lost or question not in this section — restart
        return redirect('core:section_start', section_id=section_id)

    if request.method == 'POST':
        return _process_answer(request, section, section_id, question_id, q_meta, pss, regime)

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
        prev_qid = asked_ids[-2]
        back_url = f'/section/{section_id}/question/{prev_qid}/'
    else:
        back_url = f'/section/{section_id}/start/'

    # ── Options list for radio / checkbox ─────────────────────────────────────
    options = [o.strip() for o in q_meta['options'].split(';') if o.strip()]

    context = {
        'section':        section,
        'question_id':    question_id,
        'question_text':  q_meta['question_text'],
        'guidance':       q_meta['guidance'],
        'hint':           q_meta['hint'],
        'question_type':  q_meta['question_type'],
        'options':        options,
        'current_answer': current_answer,
        'suggestion':     suggestion,
        'provenance':     provenance,
        'back_url':       back_url,
        'asked_ids':      asked_ids,
        'breadcrumbs':    _build_crumbs(pss, regime, section),
    }

    template_map = {
        'radio':    'core/question_radio.html',
        'checkbox': 'core/question_checkbox.html',
    }
    template = template_map.get(q_meta['question_type'], 'core/question_text.html')
    return render(request, template, context)


def _process_answer(request, section, section_id, question_id, q_meta, pss, regime):
    """Handle POST for section_question — store answer, advance routing."""
    # ── Extract answer ────────────────────────────────────────────────────────
    if q_meta['question_type'] == 'checkbox':
        answer = request.POST.getlist('answer')
    else:
        answer = request.POST.get('answer', '').strip()

    # Basic non-empty validation
    if not answer and answer != 0:
        # Re-render with error rather than accepting empty answer
        options = [o.strip() for o in q_meta['options'].split(';') if o.strip()]
        asked_ids = pss.get('asked_ids', [question_id])
        if len(asked_ids) > 1 and question_id == asked_ids[-1]:
            prev_qid = asked_ids[-2]
            back_url = f'/section/{section_id}/question/{prev_qid}/'
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
            'breadcrumbs':    _build_crumbs(pss, regime, section),
        }
        template_map = {'radio': 'core/question_radio.html', 'checkbox': 'core/question_checkbox.html'}
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
    next_qid, found = _evaluate_routing(routing_table, question_id, answer)

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
        return redirect('core:section_review', section_id=section_id)

    return redirect('core:section_question', section_id=section_id, question_id=next_qid)


# ─────────────────────────────────────────────────────────────────────────────
# 4.  REVIEW
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_review(request, section_id):
    section = get_object_or_404(Section, section_id=section_id)
    pss = get_session(request)

    asked_ids     = pss.get('asked_ids', [])
    basic_answers = pss.get('basic_answers', {})

    # Guard: empty session means arrived here without going through section_start
    if not asked_ids:
        return redirect('core:section_start', section_id=section_id)
    question_table = pss.get('question_table', {})

    # Load answer history first so we can attach it per-question
    case_id = pss.get('case_id')
    history_by_qid = {}
    if case_id:
        for h in (
            AnswerHistory.objects
            .filter(user=request.user, case_id=case_id, section=section)
            .select_related('question', 'actor')
            .order_by('-confirmed_at')
        ):
            history_by_qid.setdefault(h.question_id, []).append(h)

    # Build ordered rows for the citizen's actual path only
    rows = []
    for qid in asked_ids:
        q_meta = question_table.get(qid, {})
        answer  = basic_answers.get(qid)
        # Display lists as comma-separated
        if isinstance(answer, list):
            display_answer = ', '.join(answer)
        else:
            display_answer = answer or '—'
        rows.append({
            'question_id':   qid,
            'question_text': q_meta.get('question_text', qid),
            'answer':        display_answer,
            'change_url':    f'/section/{section_id}/question/{qid}/',
            'history':       history_by_qid.get(qid, []),
        })

    regime = section.get_regime()
    context = {
        'section':     section,
        'rows':        rows,
        'confirm_url': f'/section/{section_id}/confirm/',
        'breadcrumbs': _build_crumbs(pss, regime, section, last_label='Check your answers'),
    }
    return render(request, 'core/review.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 5.  CONFIRM  (standard sections)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def section_confirm(request, section_id):
    """Commit answers to DB with full audit trail.

    Delta logic (mirrors confirm_section_single in the reference):
      changed_qids — in both old and new snapshots, value differs
      removed_qids — in old snapshot but not in new asked_ids
                     (abandoned branch that was previously confirmed)

    All history writes, deletes and inserts happen inside a single
    atomic transaction so a partial failure leaves no inconsistency.
    """
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)

    asked_ids     = pss.get('asked_ids', [])
    raw_answers   = pss.get('basic_answers', {})
    case_id       = pss.get('case_id')
    actor_id      = pss.get('actor_id') or request.user.pk
    regime_id     = pss.get('regime_id')

    # Build the committed answer set (asked path only — prune stale branches)
    new_answers = {qid: raw_answers[qid] for qid in asked_ids if qid in raw_answers}

    # Resolve related objects
    regime = get_object_or_404(Regime, regime_id=regime_id) if regime_id else section.get_regime()
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
        user=request.user, case=case, section=section,
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
                user=request.user,
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
            user=request.user, case=case, section=section,
        ).delete()

        # c) Bulk-insert new answers
        questions_qs = Question.objects.filter(question_id__in=list(new_answers.keys()))
        questions_map = {q.question_id: q for q in questions_qs}
        new_records = [
            Answer(
                user=request.user,
                actor=actor,
                regime=regime,
                case=case,
                section=section,
                question=questions_map[qid],
                answer=new_answers[qid],
            )
            for qid in asked_ids
            if qid in new_answers and qid in questions_map
        ]
        Answer.objects.bulk_create(new_records)

        # d) Mark section complete
        SectionStatus.objects.update_or_create(
            user=request.user, regime=regime, section=section,
            defaults={'status': 'complete'},
        )

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
        for qid in (section.column_question_ids or '').split(';')
        if qid.strip()
    ]
    col_questions = {
        q.question_id: q
        for q in Question.objects.filter(question_id__in=col_qids)
    }
    # Preserve the order defined in column_question_ids
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
            user=request.user, case=case, section=section,
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

    # Format totals as always 2 dp (financial data)
    totals_formatted = {
        qid: f'{v:.2f}'
        for qid, v in raw_totals.items()
    }

    # Pre-ordered list aligned to columns (empty string for non-total columns)
    totals_row = [
        totals_formatted[q.question_id] if q.question_id in totals_formatted else ''
        for q in ordered_columns
    ]
    has_totals = any(v != '' for v in totals_row)

    # ── Build display rows (values in column order) ───────────────────────────
    def _fmt(val, qid):
        """Format numeric columns (those in total_qids) to 2 dp; pass others through."""
        if qid not in total_qids:
            return val if val not in (None, '') else '—'
        try:
            return f'{float(val):.2f}'
        except (ValueError, TypeError):
            return val if val not in (None, '') else '—'

    display_rows = []
    for i, row in enumerate(rows):
        display_rows.append({
            'index':  i,
            'values': [_fmt(row.get(q.question_id), q.question_id) for q in ordered_columns],
            'delete_url': f'/section/{section_id}/table/delete/{i}/',
        })

    context = {
        'section':       section,
        'columns':       ordered_columns,
        'display_rows':  display_rows,
        'totals_row':    totals_row,
        'has_totals':    has_totals,
        'add_url':       f'/section/{section_id}/table/add/',
        'confirm_url':   f'/section/{section_id}/confirm-table/',
        'has_rows':      bool(rows),
        'breadcrumbs':   _build_crumbs(pss, regime, section),
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

    col_qids = [
        qid.strip()
        for qid in (section.column_question_ids or '').split(';')
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
            user=request.user, case=case, section=section,
            defaults={'actor': actor, 'regime': regime, 'answer': []},
        )
        answer_table.answer.append(row)
        answer_table.save(update_fields=['answer', 'updated_at'])

        # At least one row → in_progress (confirm will set complete)
        SectionStatus.objects.update_or_create(
            user=request.user, regime=regime, section=section,
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
        'section':  section,
        'columns':  column_dicts,
        'back_url': f'/section/{section_id}/table/',
    }
    return render(request, 'core/table_add.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 8.  TABLE ROW DELETE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def section_table_delete(request, section_id, row_index):
    section = get_object_or_404(Section, section_id=section_id)
    pss     = get_session(request)
    regime  = section.get_regime()

    case_id = pss.get('case_id')
    try:
        case = Case.objects.get(case_id=case_id)
    except Case.DoesNotExist:
        return redirect('core:section_table', section_id=section_id)

    try:
        answer_table = AnswerTable.objects.get(
            user=request.user, case=case, section=section,
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
            user=request.user, regime=regime, section=section,
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
                user=request.user, case=case, section=section,
            )
            # Archive current rows as a history snapshot
            AnswerTableHistory.objects.create(
                user=request.user,
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
            user=request.user, regime=regime, section=section,
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
    return_url = pss.get('return_url')
    if return_url:
        return redirect(return_url)
    logger.warning(
        'section_done: no return_url in session for section %s (user %s) — '
        'falling back to /. Layer 1 must set return_url before entering Layer 2.',
        section_id, request.user,
    )
    return redirect('/')
