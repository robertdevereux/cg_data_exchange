"""
Management command: load_test_data
===================================
Loads a complete, idempotent set of test fixture data covering:
  - All three Layer 1 navigation patterns (single section / section menu /
    schedule→section menu)
  - All question types and routing branch patterns for Layer 2
  - Cross-regime pre-population via shared questions
  - Pre-loaded answers + answer history for alice
  - Intermediary access (solicitor1 acting for alice on one section)

Run with:
    python manage.py load_test_data

Safe to run multiple times — uses get_or_create / update_or_create throughout.
"""

import datetime

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    Answer,
    AnswerHistory,
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


# ── Question ID registry ──────────────────────────────────────────────────────
# Q1   full_name (retired — replaced by S1 set in sections using name capture)
# Q2   date of birth
# Q3   do you have a NI number (yes/no)
# Q4   NI number value
# Q5   address line 1
# Q6   postcode
# Q7   simple_about
# Q8   simple_agree
# Q9   simple_why
# Q10  simple_colour
# Q11  simple_count
# Q12  financial type
# Q13  financial provider
# Q14  financial balance
# Q15  additional yes/no
# Q16  additional detail
# Q17  phone
# Q18  email
# Q19  declaration yes/no
# Q20  declaration why
# Q21  retired (title — removed from S1 set)
# Q22  first name                                — S1 member
# Q23  last name                                 — S1 member
# Q24  address line 1                            — S2 member
# Q25  address line 2 (optional)                 — S2 member
# Q26  town or city                              — S2 member
# Q27  county (optional)                         — S2 member
# Q28  postcode                                  — S2 member
# Q29  name on account                           — S3 member
# Q30  sort code                                 — S3 member
# Q31  account number                            — S3 member
# Q32  building society roll number (optional)   — S3 member
# ─────────────────────────────────────────────────────────────────────────────

# ── Helpers ───────────────────────────────────────────────────────────────────

def _q(question_id):
    """Retrieve a Question by primary key (raises if missing)."""
    return Question.objects.get(question_id=question_id)


def _s(section_id):
    """Retrieve a Section by primary key."""
    return Section.objects.get(section_id=section_id)


def route(section, current_qid, answer_value, next_qid, order, counters):
    """
    Create or update a single Routing row.

    answer_value=None  → unconditional route
    next_qid=None      → END (citizen proceeds to check-your-answers)

    The unique constraint is on (section, current_node, answer_value).
    Django translates answer_value=None into WHERE answer_value IS NULL,
    so unconditional routes are idempotent correctly.
    """
    obj, created = Routing.objects.update_or_create(
        section=section,
        current_node=current_qid,
        answer_value=answer_value,
        defaults={
            'next_node': next_qid if next_qid else None,
            'order_in_section': order,
        },
    )
    if created:
        counters['Routing'] += 1


class Command(BaseCommand):
    help = 'Load complete test fixture data for all three regimes.'

    def handle(self, *args, **options):
        counters = {m: 0 for m in [
            'User', 'Question', 'Regime', 'Schedule', 'Section',
            'Routing', 'Permission', 'Case', 'Answer', 'AnswerHistory',
            'SectionStatus',
        ]}

        # ── Remove retired and renamed question IDs ───────────────────────────
        old_ids = [
            'Q_full_name', 'Q_dob', 'Q_nino_yn', 'Q_nino_value',
            'Q_address_line1', 'Q_address_postcode', 'Q_simple_about',
            'Q_simple_agree', 'Q_simple_why', 'Q_simple_colour', 'Q_simple_count',
            'Q_fin_type', 'Q_fin_provider', 'Q_fin_balance',
            'Q_additional_yn', 'Q_additional_detail',
            'Q_phone', 'Q_email', 'Q_declare_yn', 'Q_declare_why',
            'Q1',  # retired — full name as single field; replaced by S1
            'Q21', # retired — title field removed from S1 set
        ]
        Question.objects.filter(question_id__in=old_ids).delete()
        QuestionSet.objects.filter(set_id__in=['S1', 'S2', 'S3']).delete()
        # Remove stale routing rows — current_node is a CharField (no FK cascade).
        # old_ids covers both the original Q_-prefixed node names and the retired Q1.
        Routing.objects.filter(current_node__in=old_ids).delete()

        # ── 1. USERS ──────────────────────────────────────────────────────────
        self.stdout.write('Creating users…')

        pw = make_password('testpass123')
        for username, first, last in [
            ('alice',      'Alice',     'Johnson'),
            ('bob',        'Bob',       'Smith'),
            ('carla',      'Carla',     'Garcia'),
            ('solicitor1', 'William',   'Williams'),
        ]:
            u, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'email': f'{username}@example.com',
                    'password': pw,
                },
            )
            if created:
                counters['User'] += 1

        alice      = User.objects.get(username='alice')
        bob        = User.objects.get(username='bob')
        carla      = User.objects.get(username='carla')  # noqa: F841
        solicitor1 = User.objects.get(username='solicitor1')

        # ── 2. SHARED QUESTION POOL ───────────────────────────────────────────
        self.stdout.write('Creating shared questions…')

        shared_questions = [
            dict(question_id='Q1',
                 question_text='What is your full name?',
                 question_type='text'),
            dict(question_id='Q2',
                 question_text='What is your date of birth?',
                 question_type='text',
                 answer_type='date',
                 hint='For example, 27 3 1980'),
            dict(question_id='Q3',
                 question_text='Do you have a National Insurance number?',
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='Q4',
                 question_text='What is your National Insurance number?',
                 question_type='text',
                 hint='For example, QQ 12 34 56 C'),
            dict(question_id='Q5',
                 question_text='Address line 1',
                 question_type='text'),
            dict(question_id='Q6',
                 question_text='Postcode',
                 question_type='text'),
        ]
        for qdata in shared_questions:
            qid = qdata.pop('question_id')
            _, created = Question.objects.update_or_create(
                question_id=qid, defaults=qdata
            )
            if created:
                counters['Question'] += 1

        # ── 3. REGIME-SPECIFIC QUESTIONS ──────────────────────────────────────
        self.stdout.write('Creating regime-specific questions…')

        specific_questions = [
            # DEMO_SIMPLE — SIMPLE_S1
            dict(question_id='Q7',
                 question_text='Tell us a little about yourself',
                 question_type='textarea',
                 hint='2-3 sentences is fine'),
            dict(question_id='Q8',
                 question_text='Do you agree to the terms and conditions?',
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='Q9',
                 question_text='Why do you not agree?',
                 question_type='text',
                 hint='We will take your feedback into account'),
            dict(question_id='Q10',
                 question_text='Which colours do you like?',
                 question_type='checkbox',
                 options='Red;Green;Blue;Yellow;Purple'),
            dict(question_id='Q11',
                 question_text='How many colours did you select above?',
                 question_type='number',
                 answer_type='number'),
            # DEMO_SECTIONS — SECTIONS_S2 (table) and SECTIONS_S3
            dict(question_id='Q12',
                 question_text='Type of account',
                 question_type='radio',
                 options='Current account;Savings account;ISA;Other'),
            dict(question_id='Q13',
                 question_text='Bank or provider name',
                 question_type='text'),
            dict(question_id='Q14',
                 question_text='Balance (£)',
                 question_type='number',
                 answer_type='number'),
            dict(question_id='Q15',
                 question_text='Is there anything else you would like to tell us?',
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='Q16',
                 question_text='Please provide details',
                 question_type='textarea'),
            # DEMO_SCHEDULES — SCHED_S2
            dict(question_id='Q17',
                 question_text='Phone number',
                 question_type='text',
                 hint='We will only call if we need to discuss your application'),
            dict(question_id='Q18',
                 question_text='Email address',
                 question_type='text'),
            # DEMO_SCHEDULES — SCHED_S4
            dict(question_id='Q19',
                 question_text=(
                     'Do you declare that the information you have provided '
                     'is accurate and complete to the best of your knowledge?'
                 ),
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='Q20',
                 question_text='Please explain why you cannot make this declaration',
                 question_type='text'),
        ]
        for qdata in specific_questions:
            qid = qdata.pop('question_id')
            _, created = Question.objects.update_or_create(
                question_id=qid, defaults=qdata
            )
            if created:
                counters['Question'] += 1

        # ── Standard set member questions ─────────────────────────────────────

        def question(qid, question_text, question_type,
                     options=None, hint=None, answer_type=None):
            _, created = Question.objects.update_or_create(
                question_id=qid,
                defaults={
                    'question_text': question_text,
                    'question_type': question_type,
                    'options':       options or '',
                    'hint':          hint or '',
                    'answer_type':   answer_type,
                },
            )
            if created:
                counters['Question'] += 1

        question('Q22', 'First name',
                 'text')
        question('Q23', 'Last name',
                 'text')
        question('Q24', 'Address line 1',
                 'text')
        question('Q25', 'Address line 2',
                 'text')
        question('Q26', 'Town or city',
                 'text')
        question('Q27', 'County',
                 'text')
        question('Q28', 'Postcode',
                 'text')
        question('Q29', 'Name on account',
                 'text')
        question('Q30', 'Sort code',
                 'text', hint='Must be 6 digits long')
        question('Q31', 'Account number',
                 'text', hint='Must be 8 digits long')
        question('Q32', 'Building society roll number',
                 'text', hint='You can find it on your card or bank statement')

        # ── 4. REGIMES ────────────────────────────────────────────────────────
        self.stdout.write('Creating regimes…')

        for rid, name, order in [
            ('DEMO_SIMPLE',    'Demo Simple (single section)',          1),
            ('DEMO_SECTIONS',  'Demo Sections (section menu)',          2),
            ('DEMO_SCHEDULES', 'Demo Schedules (schedule + section)',   3),
        ]:
            _, created = Regime.objects.update_or_create(
                regime_id=rid,
                defaults={'regime_name': name, 'dept_id': 'DEMO', 'display_order': order},
            )
            if created:
                counters['Regime'] += 1

        r_simple    = Regime.objects.get(regime_id='DEMO_SIMPLE')
        r_sections  = Regime.objects.get(regime_id='DEMO_SECTIONS')
        r_schedules = Regime.objects.get(regime_id='DEMO_SCHEDULES')

        # ── 5. SCHEDULES (DEMO_SCHEDULES only) ───────────────────────────────
        self.stdout.write('Creating schedules…')

        for sid, name, order in [
            ('SCHED_PERSONAL',  'Personal Information',  1),
            ('SCHED_FINANCES',  'Financial Information', 2),
        ]:
            _, created = Schedule.objects.update_or_create(
                schedule_id=sid,
                defaults={'schedule_name': name, 'regime': r_schedules, 'display_order': order},
            )
            if created:
                counters['Schedule'] += 1

        sched_personal  = Schedule.objects.get(schedule_id='SCHED_PERSONAL')
        sched_finances  = Schedule.objects.get(schedule_id='SCHED_FINANCES')

        # ── 6. SECTIONS ───────────────────────────────────────────────────────
        self.stdout.write('Creating sections…')

        sections_spec = [
            # DEMO_SIMPLE — single section attached directly to regime
            dict(section_id='SIMPLE_S1',   section_name='About You',
                 section_type=0, display_order=1,
                 regime=r_simple,    schedule=None),
            # DEMO_SECTIONS — three sections attached directly to regime
            dict(section_id='SECTIONS_S1', section_name='Personal Details',
                 section_type=0, display_order=1,
                 regime=r_sections,  schedule=None),
            dict(section_id='SECTIONS_S2', section_name='Your Finances',
                 section_type=1, display_order=2,
                 regime=r_sections,  schedule=None,
                 column_question_ids='Q12;Q13;Q14',
                 totals_question_ids='Q14'),
            dict(section_id='SECTIONS_S3', section_name='Additional Information',
                 section_type=0, display_order=3,
                 regime=r_sections,  schedule=None),
            # DEMO_SCHEDULES — four sections under two schedules
            dict(section_id='SCHED_S1', section_name='Identity',
                 section_type=0, display_order=1,
                 regime=None, schedule=sched_personal),
            dict(section_id='SCHED_S2', section_name='Contact Details',
                 section_type=0, display_order=2,
                 regime=None, schedule=sched_personal),
            dict(section_id='SCHED_S3', section_name='Accounts',
                 section_type=1, display_order=1,
                 regime=None, schedule=sched_finances,
                 column_question_ids='Q12;Q13;Q14',
                 totals_question_ids='Q14'),
            dict(section_id='SCHED_S4', section_name='Declaration',
                 section_type=0, display_order=2,
                 regime=None, schedule=sched_finances),
        ]
        for sdata in sections_spec:
            sid = sdata.pop('section_id')
            _, created = Section.objects.update_or_create(
                section_id=sid, defaults=sdata
            )
            if created:
                counters['Section'] += 1

        # ── 7. ROUTING ────────────────────────────────────────────────────────
        self.stdout.write('Creating routing rules…')

        # ── SIMPLE_S1: all 5 question types, branching on nino_yn and agree ──
        #   Q1 → Q2 → Q3
        #     Yes → Q4 → Q7 → Q8
        #     No  →               Q7 → Q8
        #   Q8 = Yes → Q10 → Q11 → END
        #   Q8 = No  → Q9 → END

        s = _s('SIMPLE_S1')
        route(s, 'S1',    None,    'Q2',           1, counters)
        route(s, 'Q2',          None,    'Q3',       2, counters)
        route(s, 'Q3',      'Yes',   'Q4',    3, counters)
        route(s, 'Q3',      'No',    'Q7',  4, counters)
        route(s, 'Q4',   None,    'Q7',  5, counters)
        route(s, 'Q7', None,    'Q8',  6, counters)
        route(s, 'Q8', 'Yes',   'Q10', 7, counters)
        route(s, 'Q8', 'No',    'Q9',    8, counters)
        route(s, 'Q10',None,    'Q11',  9, counters)
        route(s, 'Q11', None,    None,             10, counters)  # END
        route(s, 'Q9',   None,    None,             11, counters)  # END

        # ── SECTIONS_S1: personal details with nino branch ────────────────────
        #   Q1 → Q2 → Q3
        #     Yes → Q4 → Q5 → Q6 → END
        #     No  →               Q5 → Q6 → END

        s = _s('SECTIONS_S1')
        route(s, 'S1',        None,  'Q2',               1, counters)
        route(s, 'Q2',              None,  'Q3',           2, counters)
        route(s, 'Q3',          'Yes', 'Q4',        3, counters)
        route(s, 'Q3',          'No',  'Q5',     4, counters)
        route(s, 'Q4',       None,  'Q5',     5, counters)
        route(s, 'Q5',    None,  'Q6',  6, counters)
        route(s, 'Q6', None,  None,                  7, counters)  # END

        # ── SECTIONS_S2: table section — field sequence per row ───────────────
        s = _s('SECTIONS_S2')
        route(s, 'Q12',     None, 'Q13', 1, counters)
        route(s, 'Q13', None, 'Q14',  2, counters)
        route(s, 'Q14',  None, None,             3, counters)  # END

        # ── SECTIONS_S3: additional information with yes/no branch ────────────
        #   Q15 = Yes → Q16 → END
        #   Q15 = No  → END
        s = _s('SECTIONS_S3')
        route(s, 'Q15',     'Yes', 'Q16', 1, counters)
        route(s, 'Q15',     'No',  None,                  2, counters)  # END
        route(s, 'Q16', None,  None,                  3, counters)  # END

        # ── SCHED_S1: identity — nino branch, ends at END (no address) ────────
        #   Q1 → Q2 → Q3
        #     Yes → Q4 → END
        #     No  → END
        s = _s('SCHED_S1')
        route(s, 'S1',  None,  'Q2',        1, counters)
        route(s, 'Q2',        None,  'Q3',    2, counters)
        route(s, 'Q3',    'Yes', 'Q4', 3, counters)
        route(s, 'Q3',    'No',  None,           4, counters)  # END
        route(s, 'Q4', None,  None,           5, counters)  # END

        # ── SCHED_S2: contact details — linear ───────────────────────────────
        s = _s('SCHED_S2')
        route(s, 'Q5',    None, 'Q6', 1, counters)
        route(s, 'Q6', None, 'Q17',            2, counters)
        route(s, 'Q17',            None, 'Q18',            3, counters)
        route(s, 'Q18',            None, None,                 4, counters)  # END

        # ── SCHED_S3: accounts table — field sequence per row ─────────────────
        s = _s('SCHED_S3')
        route(s, 'Q12',     None, 'Q13', 1, counters)
        route(s, 'Q13', None, 'Q14',  2, counters)
        route(s, 'Q14',  None, None,             3, counters)  # END

        # ── SCHED_S4: declaration — yes/no branch ─────────────────────────────
        #   Q19 = Yes → END
        #   Q19 = No  → Q20 → END
        s = _s('SCHED_S4')
        route(s, 'Q19',  'Yes', None,           1, counters)  # END
        route(s, 'Q19',  'No',  'Q20', 2, counters)
        route(s, 'Q20', None,  None,            3, counters)  # END

        # ── 8. QUESTION SETS ──────────────────────────────────────────────────

        def qset(set_id, set_title, set_hint, members):
            """
            members: list of (question_id, display_order, required) tuples
            """
            qs, _ = QuestionSet.objects.update_or_create(
                set_id=set_id,
                defaults={'set_title': set_title, 'set_hint': set_hint or ''},
            )
            # Rebuild members from scratch to avoid stale display_order issues
            QuestionSetMember.objects.filter(question_set=qs).delete()
            for question_id, display_order, required in members:
                QuestionSetMember.objects.create(
                    question_set=qs,
                    question_id=question_id,
                    display_order=display_order,
                    required=required,
                )

        # ── Standard sets ──────────────────────────────────────────────────────
        qset('S1', 'Your name', None, [
            ('Q22', 1, True),   # first name
            ('Q23', 2, True),   # last name
        ])

        qset('S2', 'Your address', None, [
            ('Q24', 1, True),   # address line 1
            ('Q25', 2, False),  # address line 2 (optional)
            ('Q26', 3, True),   # town or city
            ('Q27', 4, False),  # county (optional)
            ('Q28', 5, True),   # postcode
        ])

        qset('S3', 'Your bank account details',
             'Enter the details from your bank statement', [
            ('Q29', 1, True),   # name on account
            ('Q30', 2, True),   # sort code
            ('Q31', 3, True),   # account number
            ('Q32', 4, False),  # roll number (optional)
        ])

        # ── 9. PERMISSIONS ────────────────────────────────────────────────────
        # Strategy: one Permission per regime with section=None means "all sections
        # of that regime". For solicitor1, one permission for the specific section.
        self.stdout.write('Creating permissions…')

        # alice — all three regimes in full
        for regime in [r_simple, r_sections, r_schedules]:
            _, created = Permission.objects.get_or_create(
                actor=alice, user=alice, regime=regime, section=None,
                defaults={'can_delegate': False, 'granted_by': None},
            )
            if created:
                counters['Permission'] += 1

        # bob — DEMO_SIMPLE, DEMO_SECTIONS and DEMO_SCHEDULES
        for regime in [r_simple, r_sections, r_schedules]:
            _, created = Permission.objects.get_or_create(
                actor=bob, user=bob, regime=regime, section=None,
                defaults={'can_delegate': False, 'granted_by': None},
            )
            if created:
                counters['Permission'] += 1

        # carla — DEMO_SIMPLE only
        _, created = Permission.objects.get_or_create(
            actor=carla, user=carla, regime=r_simple, section=None,
            defaults={'can_delegate': False, 'granted_by': None},
        )
        if created:
            counters['Permission'] += 1

        # solicitor1 acting for alice: Financial Information schedule only
        for section_id in ['SCHED_S3', 'SCHED_S4']:
            _, created = Permission.objects.get_or_create(
                actor=solicitor1,
                user=alice,
                section=_s(section_id),
                defaults={'can_delegate': False},
            )
            if created:
                counters['Permission'] += 1

        # solicitor1 acting for bob: Your Finances section only
        _, created = Permission.objects.get_or_create(
            actor=solicitor1,
            user=bob,
            section=_s('SECTIONS_S2'),
            defaults={'can_delegate': False},
        )
        if created:
            counters['Permission'] += 1

        # ── 10. CASES ─────────────────────────────────────────────────────────
        self.stdout.write('Creating cases…')

        alice_case, created = Case.objects.get_or_create(
            case_id='case-alice-demo-simple',
            defaults={'user': alice, 'regime': r_simple, 'status': 'draft'},
        )
        if created:
            counters['Case'] += 1

        bob_case, created = Case.objects.get_or_create(
            case_id='case-bob-demo-sections',
            defaults={'user': bob, 'regime': r_sections, 'status': 'draft'},
        )
        if created:
            counters['Case'] += 1

        # ── 11. ALICE'S COMPLETED ANSWERS FOR SIMPLE_S1 ──────────────────────
        # Alice took the Yes branch on Q3 and Yes on Q8.
        self.stdout.write('Creating answers for alice (SIMPLE_S1)…')

        simple_s1 = _s('SIMPLE_S1')
        alice_answers = [
            ('Q22', 'Alice'),
            ('Q23', 'Johnson'),
            ('Q2',  '1975-06-15'),
            ('Q3',  'Yes'),
            ('Q4',  'QQ123456C'),
            ('Q7',  'I am a retired teacher living in Bristol.'),
            ('Q8',  'Yes'),
            ('Q10', ['Red', 'Blue']),
            ('Q11', '2'),
        ]
        for qid, value in alice_answers:
            _, created = Answer.objects.update_or_create(
                user=alice, actor=alice,
                regime=r_simple, case=alice_case,
                section=simple_s1, question=_q(qid),
                defaults={'answer': value},
            )
            if created:
                counters['Answer'] += 1

        # ── 12. ALICE'S ANSWER HISTORY (previous first name for Q22) ────────────
        self.stdout.write('Creating answer history for alice…')

        # Delete any existing history records for this question (which may include
        # duplicates created before idempotency was in place), then ensure exactly
        # one canonical record exists with a fixed timestamp.
        confirmed_at = datetime.datetime(2026, 5, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
        existing = AnswerHistory.objects.filter(
            user=alice, actor=alice,
            regime=r_simple, case=alice_case,
            section=simple_s1, question=_q('Q22'),
        )
        if existing.count() == 1 and existing.filter(
            answer='A.', confirmed_at=confirmed_at
        ).exists():
            pass  # already correct — no action needed
        else:
            existing.delete()
            AnswerHistory.objects.create(
                user=alice, actor=alice,
                regime=r_simple, case=alice_case,
                section=simple_s1, question=_q('Q22'),
                answer='A.',
                confirmed_at=confirmed_at,
            )
            counters['AnswerHistory'] += 1

        # ── 13. ALICE'S SECTION STATUS ────────────────────────────────────────
        _, created = SectionStatus.objects.update_or_create(
            user=alice, regime=r_simple, section=simple_s1,
            defaults={'status': 'complete'},
        )
        if created:
            counters['SectionStatus'] += 1

        # ── 14. BOB'S COMPLETED ANSWERS FOR SECTIONS_S1 ──────────────────────
        # Bob took the No branch on Q3 (no NI number).
        self.stdout.write('Creating answers for bob (SECTIONS_S1)…')

        sections_s1 = _s('SECTIONS_S1')
        bob_answers = [
            ('Q22', 'Bob'),
            ('Q23', 'Smith'),
            ('Q2',  '1982-03-22'),
            ('Q3',  'No'),
            ('Q5',  '14 Acacia Avenue'),
            ('Q6',  'BS1 4TR'),
        ]
        for qid, value in bob_answers:
            _, created = Answer.objects.update_or_create(
                user=bob, actor=bob,
                regime=r_sections, case=bob_case,
                section=sections_s1, question=_q(qid),
                defaults={'answer': value},
            )
            if created:
                counters['Answer'] += 1

        # ── 15. BOB'S SECTION STATUSES ────────────────────────────────────────
        self.stdout.write('Creating section statuses for bob…')

        section_statuses = [
            ('SECTIONS_S1', 'complete'),
            ('SECTIONS_S2', 'not_started'),
            ('SECTIONS_S3', 'not_started'),
        ]
        for sid, status in section_statuses:
            _, created = SectionStatus.objects.update_or_create(
                user=bob, regime=r_sections, section=_s(sid),
                defaults={'status': status},
            )
            if created:
                counters['SectionStatus'] += 1

        # ── 16. SUMMARY ───────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('─' * 50))
        self.stdout.write(self.style.SUCCESS('Test data loaded successfully'))
        self.stdout.write(self.style.SUCCESS('─' * 50))

        col_w = max(len(k) for k in counters) + 2
        for model, count in counters.items():
            label = f'{model}:'.ljust(col_w)
            if count:
                self.stdout.write(self.style.SUCCESS(f'  {label} {count:>3} created'))
            else:
                self.stdout.write(f'  {label} {count:>3} (already existed)')

        self.stdout.write('')
        self.stdout.write('Users:      alice / bob / carla / solicitor1  (pw: testpass123)')
        self.stdout.write('Regimes:    DEMO_SIMPLE · DEMO_SECTIONS · DEMO_SCHEDULES')
        self.stdout.write('Alice:      SIMPLE_S1 complete, answer history present')
        self.stdout.write('Bob:        SECTIONS_S1 complete, S2+S3 not started')
        self.stdout.write('Carla:      no answers (fresh start)')
        self.stdout.write('solicitor1: SCHED_S3+S4 (Financial Information) for alice; SECTIONS_S2 (Your Finances) for bob')
        self.stdout.write(self.style.SUCCESS('─' * 50))
