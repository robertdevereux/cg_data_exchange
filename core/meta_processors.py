"""
core/meta_processors.py — Post-confirmation processors for META regime sections.

Each processor reads confirmed answers from AnswerTable (or Answer for the
standard section) and writes update_or_create calls to the target platform
tables. All processors are idempotent.

Called by section_confirm and section_confirm_table immediately after
the answer is committed, when section.section_id starts with 'META_'.
"""

import logging

from .models import (
    Answer, AnswerTable, Question, QuestionSet, QuestionSetMember,
    Regime, Schedule, Section,
)

logger = logging.getLogger(__name__)


def dispatch_meta_processor(section, case, user):
    """
    Called after confirmation of any META section.
    Dispatches to the appropriate processor based on section_id.
    """
    processors = {
        'META_ADD_REGIME':      process_meta_regime,
        'META_ADD_SCHEDULES':   process_meta_schedules,
        'META_ADD_SECTIONS':    process_meta_sections,
        'META_ADD_QUESTIONS':   process_meta_questions,
        'META_ADD_SETS':        process_meta_sets,
        'META_ADD_SETMEMBERS':  process_meta_setmembers,
    }
    fn = processors.get(section.section_id)
    if fn:
        try:
            fn(case, user)
            logger.info('META processor %s completed for case %s',
                        section.section_id, case.case_id)
        except Exception as e:
            logger.error('META processor %s failed for case %s: %s',
                         section.section_id, case.case_id, e)
            raise


# ── Standard section processor ────────────────────────────────────────────────

def process_meta_regime(case, user):
    """Read META_ADD_REGIME answers and write to Regime table."""
    section = Section.objects.get(section_id='META_ADD_REGIME')
    answers = {
        a.question_id: a.answer
        for a in Answer.objects.filter(user=user, case=case, section=section)
    }
    regime_id   = answers.get('Q53', '').strip()
    regime_name = answers.get('Q54', '').strip()
    dept_id     = answers.get('Q55', '').strip()

    if not regime_id or not regime_name:
        logger.warning('process_meta_regime: missing regime_id or regime_name')
        return

    Regime.objects.update_or_create(
        regime_id=regime_id,
        defaults={
            'regime_name':   regime_name,
            'dept_id':       dept_id or None,
            'display_order': 0,
        }
    )


# ── Table section processors ──────────────────────────────────────────────────

def _get_table_rows(case, user, section_id):
    """Return the list of row dicts from AnswerTable for a given section."""
    try:
        section = Section.objects.get(section_id=section_id)
        at = AnswerTable.objects.get(user=user, case=case, section=section)
        return at.answer  # list of dicts
    except (Section.DoesNotExist, AnswerTable.DoesNotExist):
        return []


def process_meta_schedules(case, user):
    """Read META_ADD_SCHEDULES rows and write to Schedule table."""
    rows = _get_table_rows(case, user, 'META_ADD_SCHEDULES')
    for row in rows:
        schedule_id   = (row.get('Q50') or '').strip()
        schedule_name = (row.get('Q51') or '').strip()
        display_order = row.get('Q52', 0)
        if not schedule_id or not schedule_name:
            continue
        # Regime must already exist (process_meta_regime runs first)
        # Find it from the META_ADD_REGIME answer for this case
        regime = _get_target_regime(case, user)
        if not regime:
            continue
        try:
            display_order = int(display_order)
        except (ValueError, TypeError):
            display_order = 0
        Schedule.objects.update_or_create(
            schedule_id=schedule_id,
            defaults={
                'schedule_name': schedule_name,
                'regime':        regime,
                'display_order': display_order,
            }
        )


def process_meta_sections(case, user):
    """Read META_ADD_SECTIONS rows and write to Section table."""
    rows = _get_table_rows(case, user, 'META_ADD_SECTIONS')
    regime = _get_target_regime(case, user)
    if not regime:
        return
    for row in rows:
        section_id       = (row.get('Q46') or '').strip()
        section_name     = (row.get('Q47') or '').strip()
        section_type_str = (row.get('Q48') or 'Standard').strip()
        schedule_id      = (row.get('Q49') or '').strip()
        if not section_id or not section_name:
            continue
        section_type = 1 if section_type_str == 'Table' else 0
        schedule = None
        if schedule_id:
            try:
                schedule = Schedule.objects.get(schedule_id=schedule_id)
            except Schedule.DoesNotExist:
                logger.warning('process_meta_sections: schedule %s not found',
                               schedule_id)
        Section.objects.update_or_create(
            section_id=section_id,
            defaults={
                'section_name': section_name,
                'section_type': section_type,
                'regime':       None if schedule else regime,
                'schedule':     schedule,
                'display_order': 0,
            }
        )


def process_meta_questions(case, user):
    """Read META_ADD_QUESTIONS rows and write to Question table."""
    rows = _get_table_rows(case, user, 'META_ADD_QUESTIONS')
    for row in rows:
        question_id   = (row.get('Q33') or '').strip()
        question_text = (row.get('Q34') or '').strip()
        question_type = (row.get('Q35') or 'text').strip()
        hint          = (row.get('Q36') or '').strip() or None
        guidance      = (row.get('Q37') or '').strip() or None
        options       = (row.get('Q38') or '').strip() or None
        if not question_id or not question_text:
            continue
        Question.objects.update_or_create(
            question_id=question_id,
            defaults={
                'question_text': question_text,
                'question_type': question_type,
                'hint':          hint,
                'guidance':      guidance,
                'options':       options,
            }
        )


def process_meta_sets(case, user):
    """Read META_ADD_SETS rows and write to QuestionSet table."""
    rows = _get_table_rows(case, user, 'META_ADD_SETS')
    for row in rows:
        set_id    = (row.get('Q39') or '').strip()
        set_title = (row.get('Q40') or '').strip()
        set_hint  = (row.get('Q41') or '').strip() or None
        if not set_id or not set_title:
            continue
        QuestionSet.objects.update_or_create(
            set_id=set_id,
            defaults={
                'set_title': set_title,
                'set_hint':  set_hint,
            }
        )


def process_meta_setmembers(case, user):
    """Read META_ADD_SETMEMBERS rows and write to QuestionSetMember table."""
    rows = _get_table_rows(case, user, 'META_ADD_SETMEMBERS')
    for row in rows:
        set_id        = (row.get('Q42') or '').strip()
        question_id   = (row.get('Q43') or '').strip()
        display_order = row.get('Q44', 0)
        required_str  = (row.get('Q45') or 'Yes').strip()
        if not set_id or not question_id:
            continue
        try:
            display_order = int(display_order)
        except (ValueError, TypeError):
            display_order = 0
        required = required_str != 'No'
        try:
            qset     = QuestionSet.objects.get(set_id=set_id)
            question = Question.objects.get(question_id=question_id)
        except (QuestionSet.DoesNotExist, Question.DoesNotExist) as e:
            logger.warning('process_meta_setmembers: %s', e)
            continue
        QuestionSetMember.objects.update_or_create(
            question_set=qset,
            question=question,
            defaults={
                'display_order': display_order,
                'required':      required,
            }
        )


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_target_regime(case, user):
    """
    Find the target regime ID from the META_ADD_REGIME answer for this case.
    Returns a Regime instance or None.
    """
    try:
        section = Section.objects.get(section_id='META_ADD_REGIME')
        answer  = Answer.objects.get(
            user=user, case=case, section=section, question_id='Q53'
        )
        return Regime.objects.get(regime_id=answer.answer.strip())
    except (Section.DoesNotExist, Answer.DoesNotExist, Regime.DoesNotExist):
        return None
