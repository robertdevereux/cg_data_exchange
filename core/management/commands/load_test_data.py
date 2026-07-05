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
    Department,
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
# ── META regime columns ───────────────────────────────────────────────────────
# M_1   META question ID                          — META_ADD_QUESTIONS column
# M_2   META question text                        — META_ADD_QUESTIONS column
# M_3   META question type                        — META_ADD_QUESTIONS column
# M_4   META hint text                            — META_ADD_QUESTIONS column
# M_5   META guidance                             — META_ADD_QUESTIONS column
# M_6   META options                              — META_ADD_QUESTIONS column
# M_7   META set ID                               — META_ADD_SETS column
# M_8   META set title                            — META_ADD_SETS column
# M_9   META set hint                             — META_ADD_SETS column
# M_10  META set ID (for member)                  — META_ADD_SETMEMBERS column
# M_11  META question ID (for member)             — META_ADD_SETMEMBERS column
# M_12  META display order                        — META_ADD_SETMEMBERS column
# M_13  META required?                            — META_ADD_SETMEMBERS column
# M_14  META section ID                           — META_ADD_SECTIONS column
# M_15  META section name                         — META_ADD_SECTIONS column
# M_16  META section type                         — META_ADD_SECTIONS column
# M_17  META schedule ID                          — META_ADD_SECTIONS column
# M_18  META schedule ID                          — META_ADD_SCHEDULES column
# M_19  META schedule name                        — META_ADD_SCHEDULES column
# M_20  META schedule display order               — META_ADD_SCHEDULES column
# M_21  META regime ID                            — META_ADD_REGIME question
# M_22  META regime name                          — META_ADD_REGIME question
# M_23  META department ID                        — META_ADD_REGIME question
# M_24  META section ID                           — META_ADD_ROUTING column
# M_25  META current node                         — META_ADD_ROUTING column
# M_26  META answer value                         — META_ADD_ROUTING column
# M_27  META next node                            — META_ADD_ROUTING column
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
            # Q2–Q20 and Q22–Q32 migrated to DEMO_-prefixed IDs then renamed to TEST_
            'Q2', 'Q3', 'Q4', 'Q5', 'Q6',
            'Q7', 'Q8', 'Q9', 'Q10', 'Q11',
            'Q12', 'Q13', 'Q14', 'Q15', 'Q16', 'Q17', 'Q18', 'Q19', 'Q20',
            'Q22', 'Q23', 'Q24', 'Q25', 'Q26', 'Q27', 'Q28', 'Q29', 'Q30', 'Q31', 'Q32',
            # DEMO_-prefixed IDs renamed to TEST_
            'DEMO_2', 'DEMO_3', 'DEMO_4', 'DEMO_5', 'DEMO_6',
            'DEMO_7', 'DEMO_8', 'DEMO_9', 'DEMO_10', 'DEMO_11',
            'DEMO_12', 'DEMO_13', 'DEMO_14', 'DEMO_15', 'DEMO_16', 'DEMO_17', 'DEMO_18', 'DEMO_19', 'DEMO_20',
            'DEMO_22', 'DEMO_23', 'DEMO_24', 'DEMO_25', 'DEMO_26', 'DEMO_27', 'DEMO_28', 'DEMO_29', 'DEMO_30', 'DEMO_31', 'DEMO_32',
            # Q33–Q59 META wizard questions renamed to M_-prefixed IDs
            'Q33', 'Q34', 'Q35', 'Q36', 'Q37', 'Q38',
            'Q39', 'Q40', 'Q41',
            'Q42', 'Q43', 'Q44', 'Q45',
            'Q46', 'Q47', 'Q48', 'Q49',
            'Q50', 'Q51', 'Q52',
            'Q53', 'Q54', 'Q55',
            'Q56', 'Q57', 'Q58', 'Q59',
            # P1-P6 renamed to P_1-P_6 (underscore format)
            'P1', 'P2', 'P3', 'P4', 'P5', 'P6',
        ]
        Question.objects.filter(question_id__in=old_ids).delete()
        QuestionSet.objects.filter(set_id__in=['SET1', 'SET2', 'SET3']).delete()
        # Remove stale routing rows — current_node is a CharField (no FK cascade).
        # old_ids covers both the original Q_-prefixed node names and the retired Q1.
        # Also purge old S-prefix set IDs that were renamed to SET-prefix.
        Routing.objects.filter(current_node__in=old_ids).delete()
        Routing.objects.filter(current_node__in=['S1', 'S2', 'S3', 'S4', 'S5', 'S6',
                                                  'S7', 'S8', 'S9']).delete()

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

        User.objects.update_or_create(
            username='admin',
            defaults={
                'first_name': 'Admin',
                'last_name':  'User',
                'email':      'admin@example.com',
                'is_staff':   True,
                'password':   pw,
            }
        )

        super_admin, _ = User.objects.get_or_create(
            username='super_admin',
            defaults={
                'first_name':   'Super',
                'last_name':    'Admin',
                'email':        'super_admin@example.com',
                'is_staff':     True,
                'is_superuser': True,
            }
        )
        super_admin.set_password('password123')
        super_admin.save()

        # ── DWP test users ────────────────────────────────────────────────────
        for username, first, last in [
            ('dwp_alice',  'Alice', 'Chapman'),
            ('dwp_bob',    'Bob',   'Chapman'),
            ('dwp_agent1', 'Agent', 'One'),
        ]:
            u, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first,
                    'last_name':  last,
                    'email':      f'{username}@example.com',
                    'password':   pw,
                },
            )
            if created:
                counters['User'] += 1

        # ── DEFRA test users ──────────────────────────────────────────────────
        u, created = User.objects.get_or_create(
            username='defra_alice',
            defaults={
                'first_name': 'Alice',
                'last_name':  'DEFRA',
                'email':      'defra_alice@example.com',
                'password':   pw,
            },
        )
        if created:
            counters['User'] += 1

        alice      = User.objects.get(username='alice')
        bob        = User.objects.get(username='bob')
        carla      = User.objects.get(username='carla')  # noqa: F841
        solicitor1 = User.objects.get(username='solicitor1')
        dwp_alice  = User.objects.get(username='dwp_alice')
        dwp_bob    = User.objects.get(username='dwp_bob')
        dwp_agent1 = User.objects.get(username='dwp_agent1')

        # ── 2. SHARED QUESTION POOL ───────────────────────────────────────────
        self.stdout.write('Creating shared questions…')

        shared_questions = [
            dict(question_id='TEST_2',
                 question_text='What is your date of birth?',
                 question_type='date',
                 answer_type='date',
                 hint='For example, 27 3 1980'),
            dict(question_id='TEST_3',
                 question_text='Do you have a National Insurance number?',
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='TEST_4',
                 question_text='What is your National Insurance number?',
                 question_type='text',
                 hint='For example, QQ 12 34 56 C'),
            dict(question_id='TEST_5',
                 question_text='Address line 1',
                 question_type='text'),
            dict(question_id='TEST_6',
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
            # TEST_SIMPLE — SIMPLE_S1
            dict(question_id='TEST_7',
                 question_text='Tell us a little about yourself',
                 question_type='textarea',
                 hint='2-3 sentences is fine'),
            dict(question_id='TEST_8',
                 question_text='Do you agree to the terms and conditions?',
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='TEST_9',
                 question_text='Why do you not agree?',
                 question_type='text',
                 hint='We will take your feedback into account'),
            dict(question_id='TEST_10',
                 question_text='Which colours do you like?',
                 question_type='checkbox',
                 options='Red;Green;Blue;Yellow;Purple'),
            dict(question_id='TEST_11',
                 question_text='How many colours did you select above?',
                 question_type='number',
                 answer_type='number'),
            # TEST_SECTIONS — SECTIONS_S2 (table) and SECTIONS_S3
            dict(question_id='TEST_12',
                 question_text='Type of account',
                 question_type='radio',
                 options='Current account;Savings account;ISA;Other'),
            dict(question_id='TEST_13',
                 question_text='Bank or provider name',
                 question_type='text'),
            dict(question_id='TEST_14',
                 question_text='Balance (£)',
                 question_type='number',
                 answer_type='number'),
            dict(question_id='TEST_15',
                 question_text='Is there anything else you would like to tell us?',
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='TEST_16',
                 question_text='Please provide details',
                 question_type='textarea'),
            # TEST_SCHEDULES — SCHED_S2
            dict(question_id='TEST_17',
                 question_text='Phone number',
                 question_type='text',
                 hint='We will only call if we need to discuss your application'),
            dict(question_id='TEST_18',
                 question_text='Email address',
                 question_type='text'),
            # TEST_SCHEDULES — SCHED_S4
            dict(question_id='TEST_19',
                 question_text=(
                     'Do you declare that the information you have provided '
                     'is accurate and complete to the best of your knowledge?'
                 ),
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='TEST_20',
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
                     options=None, hint=None, answer_type=None, is_platform=False):
            _, created = Question.objects.update_or_create(
                question_id=qid,
                defaults={
                    'question_text': question_text,
                    'question_type': question_type,
                    'options':       options or '',
                    'hint':          hint or '',
                    'answer_type':   answer_type,
                    'is_platform':   is_platform,
                },
            )
            if created:
                counters['Question'] += 1

        question('TEST_22', 'First name', 'text')
        question('TEST_23', 'Last name', 'text')
        question('TEST_24', 'Address line 1', 'text')
        question('TEST_25', 'Address line 2', 'text')
        question('TEST_26', 'Town or city', 'text')
        question('TEST_27', 'County', 'text')
        question('TEST_28', 'Postcode', 'text')
        question('TEST_29', 'Name on account', 'text')
        question('TEST_30', 'Sort code', 'text', hint='Must be 6 digits long')
        question('TEST_31', 'Account number', 'text', hint='Must be 8 digits long')
        question('TEST_32', 'Building society roll number',
                 'text', hint='You can find it on your card or bank statement')

        # ── META regime column questions ──────────────────────────────────────
        # META_ADD_QUESTIONS columns
        question('M_1', 'Question ID', 'text',
                 hint='Unique identifier, e.g. Q99. Must not already exist.',
                 is_platform=True)
        question('M_2', 'Question text', 'text',
                 hint='The question as shown to the citizen.',
                 is_platform=True)
        question('M_3', 'Question type', 'radio',
                 options='text;textarea;number;radio;checkbox;date',
                 is_platform=True)
        question('M_4', 'Hint text', 'text',
                 hint='Optional short hint shown below the question text.',
                 is_platform=True)
        question('M_5', 'Guidance', 'textarea',
                 hint='Optional longer guidance shown above the question.',
                 is_platform=True)
        question('M_6', 'Options', 'text',
                 hint='Semicolon-delimited options for radio or checkbox questions.',
                 is_platform=True)

        # META_ADD_SETS columns
        question('M_7', 'Set ID', 'text',
                 hint='Unique identifier, e.g. S9. Must not already exist.',
                 is_platform=True)
        question('M_8', 'Set title', 'text',
                 hint='Heading shown to the citizen on the set page.',
                 is_platform=True)
        question('M_9', 'Set hint', 'text',
                 hint='Optional hint shown below the set title.',
                 is_platform=True)

        # META_ADD_SETMEMBERS columns
        question('M_10', 'Set ID', 'text',
                 hint='The set this question belongs to.',
                 is_platform=True)
        question('M_11', 'Question ID', 'text',
                 hint='The question to add to the set.',
                 is_platform=True)
        question('M_12', 'Display order', 'number',
                 hint='Order within the set (1, 2, 3...).',
                 is_platform=True)
        question('M_13', 'Required?', 'radio',
                 options='Yes;No',
                 is_platform=True)

        # META_ADD_SECTIONS columns
        question('M_14', 'Section ID', 'text',
                 hint='Unique identifier, e.g. DWP_S1.',
                 is_platform=True)
        question('M_15', 'Section name', 'text',
                 hint='Name shown to the citizen.',
                 is_platform=True)
        question('M_16', 'Section type', 'radio',
                 options='Standard;Table',
                 is_platform=True)
        question('M_17', 'Schedule ID', 'text',
                 hint='Leave blank if this section belongs directly to the regime.',
                 is_platform=True)

        # META_ADD_SCHEDULES columns
        question('M_18', 'Schedule ID', 'text',
                 hint='Unique identifier, e.g. DWP_SCHED1.',
                 is_platform=True)
        question('M_19', 'Schedule name', 'text',
                 hint='Name shown to the citizen.',
                 is_platform=True)
        question('M_20', 'Display order', 'number',
                 hint='Order within the regime (1, 2, 3...).',
                 is_platform=True)

        # META_ADD_REGIME columns (standard section)
        question('M_21', 'Regime ID', 'text',
                 hint='Unique identifier, e.g. DWP_BSP. Must not already exist.',
                 is_platform=True)
        question('M_22', 'Regime name', 'text',
                 hint='Full name of the service.',
                 is_platform=True)
        # M_23 is a radio question; options are set dynamically below after
        # Department records are created. Re-run load_test_data after adding a
        # new Department to keep M_23 in sync with the Department table.
        question('M_23', 'Department ID', 'radio',
                 hint='Select the department for this regime.',
                 is_platform=True)

        # META_ADD_ROUTING columns
        question('M_24', 'Section ID', 'text',
                 hint='The section this routing row belongs to.',
                 is_platform=True)
        question('M_25', 'Current node', 'text',
                 hint='Q-number or S-number for this screen.',
                 is_platform=True)
        question('M_26', 'Answer value', 'text',
                 hint='The answer that triggers this route. Blank means always follow this route.',
                 is_platform=True)
        question('M_27', 'Next node', 'text',
                 hint='Q-number or S-number for the next screen. Blank means END.',
                 is_platform=True)

        # ── 4. DEPARTMENTS ────────────────────────────────────────────────────
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        Department.objects.get_or_create(
            dept_id='DWP',
            defaults={'dept_name': 'Department for Work and Pensions'},
        )
        Department.objects.get_or_create(
            dept_id='DEFRA',
            defaults={'dept_name': 'Department for Environment, Food and Rural Affairs'},
        )
        Department.objects.get_or_create(
            dept_id='TEST',
            defaults={'dept_name': 'Test Department'},
        )

        # Populate M_23 options from Department records so the wizard dropdown
        # always reflects the current set of participating departments.
        # Re-run load_test_data after adding a new Department to keep in sync.
        dept_options = ';'.join(
            Department.objects.order_by('dept_id').values_list('dept_id', flat=True)
        )
        Question.objects.filter(question_id='M_23').update(options=dept_options)

        # ── Platform questions (P-series) ────────────────────────────────────
        self.stdout.write('Creating platform questions…')

        platform_questions = [
            ('P_1', {
                'question_text': 'What is your name?',
                'question_type': 'personal_name',
                'is_platform':   True,
                'hint':          '',
            }),
            ('P_2', {
                'question_text': 'What is your address?',
                'question_type': 'address',
                'is_platform':   True,
                'hint':          '',
            }),
            ('P_3', {
                'question_text': 'What is your date of birth?',
                'question_type': 'date',
                'is_platform':   True,
                'hint':          'For example, 27 3 1970',
                'answer_type':   'date',
            }),
            ('P_4', {
                'question_text': 'What is your email address?',
                'question_type': 'text',
                'is_platform':   True,
                'hint':          '',
            }),
            ('P_5', {
                'question_text': 'What is your mobile telephone number?',
                'question_type': 'text',
                'is_platform':   True,
                'hint':          '',
            }),
            ('P_6', {
                'question_text': 'What is your landline telephone number?',
                'question_type': 'text',
                'is_platform':   True,
                'hint':          '',
            }),
        ]
        for qid, defaults in platform_questions:
            _, created = Question.objects.get_or_create(
                question_id=qid, defaults=defaults,
            )
            if created:
                counters['Question'] += 1

        # ── 5. REGIMES ────────────────────────────────────────────────────────
        self.stdout.write('Creating regimes…')

        for rid, name, order in [
            ('TEST_SIMPLE',    'Test Simple (single section)',          1),
            ('TEST_SECTIONS',  'Test Sections (section menu)',          2),
            ('TEST_SCHEDULES', 'Test Schedules (schedule + section)',   3),
        ]:
            _, created = Regime.objects.update_or_create(
                regime_id=rid,
                defaults={'regime_name': name, 'dept_id': 'TEST', 'display_order': order},
            )
            if created:
                counters['Regime'] += 1

        r_simple    = Regime.objects.get(regime_id='TEST_SIMPLE')
        r_sections  = Regime.objects.get(regime_id='TEST_SECTIONS')
        r_schedules = Regime.objects.get(regime_id='TEST_SCHEDULES')

        # ── META regime ───────────────────────────────────────────────────────
        Regime.objects.update_or_create(
            regime_id='META',
            defaults={
                'regime_name':   'Platform Configuration',
                'dept_id':       'PLATFORM',
                'display_order': 999,
            }
        )

        # ── 5. SCHEDULES (TEST_SCHEDULES only) ───────────────────────────────
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
            # TEST_SIMPLE — single section attached directly to regime
            dict(section_id='SIMPLE_S1',   section_name='About You',
                 section_type=0, display_order=1,
                 regime=r_simple,    schedule=None),
            # TEST_SECTIONS — three sections attached directly to regime
            dict(section_id='SECTIONS_S1', section_name='Personal Details',
                 section_type=0, display_order=1,
                 regime=r_sections,  schedule=None),
            dict(section_id='SECTIONS_S2', section_name='Your Finances',
                 section_type=1, display_order=2,
                 regime=r_sections,  schedule=None,
                 display_question_ids='TEST_12;TEST_13;TEST_14',
                 totals_question_ids='TEST_14'),
            dict(section_id='SECTIONS_S3', section_name='Additional Information',
                 section_type=0, display_order=3,
                 regime=r_sections,  schedule=None),
            # TEST_SCHEDULES — four sections under two schedules
            dict(section_id='SCHED_S1', section_name='Identity',
                 section_type=0, display_order=1,
                 regime=None, schedule=sched_personal),
            dict(section_id='SCHED_S2', section_name='Contact Details',
                 section_type=0, display_order=2,
                 regime=None, schedule=sched_personal),
            dict(section_id='SCHED_S3', section_name='Accounts',
                 section_type=1, display_order=1,
                 regime=None, schedule=sched_finances,
                 display_question_ids='TEST_12;TEST_13;TEST_14',
                 totals_question_ids='TEST_14'),
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

        # ── META sections ─────────────────────────────────────────────────────
        meta_regime = Regime.objects.get(regime_id='META')

        Section.objects.update_or_create(
            section_id='META_ADD_REGIME',
            defaults={
                'section_name': 'Define new regime',
                'section_type': 0,
                'regime':       meta_regime,
                'schedule':     None,
                'display_order': 1,
            }
        )
        Section.objects.update_or_create(
            section_id='META_ADD_SCHEDULES',
            defaults={
                'section_name':        'Add schedules',
                'section_type':        1,
                'regime':              meta_regime,
                'schedule':            None,
                'display_order':       2,
                'display_question_ids': 'M_18;M_19;M_20',
            }
        )
        Section.objects.update_or_create(
            section_id='META_ADD_SECTIONS',
            defaults={
                'section_name':        'Add sections',
                'section_type':        1,
                'regime':              meta_regime,
                'schedule':            None,
                'display_order':       3,
                'display_question_ids': 'M_14;M_15;M_16;M_17',
            }
        )
        Section.objects.update_or_create(
            section_id='META_ADD_QUESTIONS',
            defaults={
                'section_name':        'Add questions',
                'section_type':        1,
                'regime':              meta_regime,
                'schedule':            None,
                'display_order':       4,
                'display_question_ids': 'M_1;M_2;M_3;M_4;M_5;M_6',
            }
        )
        Section.objects.update_or_create(
            section_id='META_ADD_SETS',
            defaults={
                'section_name':        'Add sets',
                'section_type':        1,
                'regime':              meta_regime,
                'schedule':            None,
                'display_order':       5,
                'display_question_ids': 'M_7;M_8;M_9',
            }
        )
        Section.objects.update_or_create(
            section_id='META_ADD_SETMEMBERS',
            defaults={
                'section_name':        'Add set members',
                'section_type':        1,
                'regime':              meta_regime,
                'schedule':            None,
                'display_order':       6,
                'display_question_ids': 'M_10;M_11;M_12;M_13',
            }
        )
        Section.objects.update_or_create(
            section_id='META_ADD_ROUTING',
            defaults={
                'section_name':        'Add routing',
                'section_type':        1,
                'regime':              meta_regime,
                'schedule':            None,
                'display_order':       7,
                'display_question_ids': 'M_24;M_25;M_26;M_27',
            }
        )

        # ── 7. ROUTING ────────────────────────────────────────────────────────
        self.stdout.write('Creating routing rules…')

        # ── SIMPLE_S1: all 5 question types, branching on nino_yn and agree ──
        #   Q1 → Q2 → Q3
        #     Yes → Q4 → Q7 → Q8
        #     No  →               Q7 → Q8
        #   Q8 = Yes → Q10 → Q11 → END
        #   Q8 = No  → Q9 → END

        s = _s('SIMPLE_S1')
        route(s, 'SET1',     None,  'TEST_2',  1, counters)
        route(s, 'TEST_2',   None,  'TEST_3',  2, counters)
        route(s, 'TEST_3',   'Yes', 'TEST_4',  3, counters)
        route(s, 'TEST_3',   'No',  'TEST_7',  4, counters)
        route(s, 'TEST_4',   None,  'TEST_7',  5, counters)
        route(s, 'TEST_7',   None,  'TEST_8',  6, counters)
        route(s, 'TEST_8',   'Yes', 'TEST_10', 7, counters)
        route(s, 'TEST_8',   'No',  'TEST_9',  8, counters)
        route(s, 'TEST_10',  None,  'TEST_11', 9, counters)
        route(s, 'TEST_11',  None,  None,      10, counters)  # END
        route(s, 'TEST_9',   None,  None,      11, counters)  # END

        # ── SECTIONS_S1: personal details with nino branch ────────────────────
        #   SET1 → TEST_2 → TEST_3
        #     Yes → TEST_4 → TEST_5 → TEST_6 → END
        #     No  →                   TEST_5 → TEST_6 → END

        s = _s('SECTIONS_S1')
        route(s, 'SET1',    None,  'TEST_2', 1, counters)
        route(s, 'TEST_2',  None,  'TEST_3', 2, counters)
        route(s, 'TEST_3',  'Yes', 'TEST_4', 3, counters)
        route(s, 'TEST_3',  'No',  'TEST_5', 4, counters)
        route(s, 'TEST_4',  None,  'TEST_5', 5, counters)
        route(s, 'TEST_5',  None,  'TEST_6', 6, counters)
        route(s, 'TEST_6',  None,  None,     7, counters)  # END

        # ── SECTIONS_S2: table section — field sequence per row ───────────────
        s = _s('SECTIONS_S2')
        route(s, 'TEST_12', None, 'TEST_13', 1, counters)
        route(s, 'TEST_13', None, 'TEST_14', 2, counters)
        route(s, 'TEST_14', None, None,       3, counters)  # END

        # ── SECTIONS_S3: additional information with yes/no branch ────────────
        #   TEST_15 = Yes → TEST_16 → END
        #   TEST_15 = No  → END
        s = _s('SECTIONS_S3')
        route(s, 'TEST_15', 'Yes', 'TEST_16', 1, counters)
        route(s, 'TEST_15', 'No',  None,       2, counters)  # END
        route(s, 'TEST_16', None,  None,       3, counters)  # END

        # ── SCHED_S1: identity — nino branch, ends at END (no address) ────────
        #   SET1 → TEST_2 → TEST_3
        #     Yes → TEST_4 → END
        #     No  → END
        s = _s('SCHED_S1')
        route(s, 'SET1',    None,  'TEST_2', 1, counters)
        route(s, 'TEST_2',  None,  'TEST_3', 2, counters)
        route(s, 'TEST_3',  'Yes', 'TEST_4', 3, counters)
        route(s, 'TEST_3',  'No',  None,     4, counters)  # END
        route(s, 'TEST_4',  None,  None,     5, counters)  # END

        # ── SCHED_S2: contact details — linear ───────────────────────────────
        s = _s('SCHED_S2')
        route(s, 'TEST_5',  None, 'TEST_6',  1, counters)
        route(s, 'TEST_6',  None, 'TEST_17', 2, counters)
        route(s, 'TEST_17', None, 'TEST_18', 3, counters)
        route(s, 'TEST_18', None, None,      4, counters)  # END

        # ── SCHED_S3: accounts table — field sequence per row ─────────────────
        s = _s('SCHED_S3')
        route(s, 'TEST_12', None, 'TEST_13', 1, counters)
        route(s, 'TEST_13', None, 'TEST_14', 2, counters)
        route(s, 'TEST_14', None, None,       3, counters)  # END

        # ── SCHED_S4: declaration — yes/no branch ─────────────────────────────
        #   TEST_19 = Yes → END
        #   TEST_19 = No  → TEST_20 → END
        s = _s('SCHED_S4')
        route(s, 'TEST_19', 'Yes', None,      1, counters)  # END
        route(s, 'TEST_19', 'No',  'TEST_20', 2, counters)
        route(s, 'TEST_20', None,  None,      3, counters)  # END

        # ── META_ADD_REGIME routing (table sections need no routing) ──────────
        meta_regime_section = Section.objects.get(section_id='META_ADD_REGIME')

        # Delete stale routing for this section before recreating
        Routing.objects.filter(section=meta_regime_section).delete()

        route(meta_regime_section, 'M_21', None, 'M_22', 1, counters)
        route(meta_regime_section, 'M_22', None, 'M_23', 2, counters)
        route(meta_regime_section, 'M_23', None, None,   3, counters)

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
        qset('SET1', 'Your name', None, [
            ('TEST_22', 1, True),   # first name
            ('TEST_23', 2, True),   # last name
        ])

        qset('SET2', 'Your address', None, [
            ('TEST_24', 1, True),   # address line 1
            ('TEST_25', 2, False),  # address line 2 (optional)
            ('TEST_26', 3, True),   # town or city
            ('TEST_27', 4, False),  # county (optional)
            ('TEST_28', 5, True),   # postcode
        ])

        qset('SET3', 'Your bank account details',
             'Enter the details from your bank statement', [
            ('TEST_29', 1, True),   # name on account
            ('TEST_30', 2, True),   # sort code
            ('TEST_31', 3, True),   # account number
            ('TEST_32', 4, False),  # roll number (optional)
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

        # bob — TEST_SIMPLE, TEST_SECTIONS and TEST_SCHEDULES
        for regime in [r_simple, r_sections, r_schedules]:
            _, created = Permission.objects.get_or_create(
                actor=bob, user=bob, regime=regime, section=None,
                defaults={'can_delegate': False, 'granted_by': None},
            )
            if created:
                counters['Permission'] += 1

        # carla — TEST_SIMPLE only
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

        # ── DWP user permissions ──────────────────────────────────────────────
        # Blanket all-regime permissions (regime=None, section=None).
        # Grants access to all non-PLATFORM regimes — including any DWP-specific
        # regimes created later via the wizard.
        for u in [dwp_alice, dwp_bob]:
            _, created = Permission.objects.get_or_create(
                actor=u, user=u, regime=None, section=None,
                defaults={'can_delegate': False, 'granted_by': None},
            )
            if created:
                counters['Permission'] += 1

        # dwp_agent1 acting for dwp_alice (blanket scope)
        _, created = Permission.objects.get_or_create(
            actor=dwp_agent1, user=dwp_alice, regime=None, section=None,
            defaults={'can_delegate': False, 'granted_by': None},
        )
        if created:
            counters['Permission'] += 1

        # ── 10. CASES ─────────────────────────────────────────────────────────
        self.stdout.write('Creating cases…')

        alice_case, created = Case.objects.get_or_create(
            case_id='case-alice-test-simple',
            defaults={'user': alice, 'regime': r_simple, 'status': 'draft'},
        )
        if created:
            counters['Case'] += 1

        bob_case, created = Case.objects.get_or_create(
            case_id='case-bob-test-sections',
            defaults={'user': bob, 'regime': r_sections, 'status': 'draft'},
        )
        if created:
            counters['Case'] += 1

        # ── 11. ALICE'S COMPLETED ANSWERS FOR SIMPLE_S1 ──────────────────────
        # Alice took the Yes branch on Q3 and Yes on Q8.
        self.stdout.write('Creating answers for alice (SIMPLE_S1)…')

        simple_s1 = _s('SIMPLE_S1')
        alice_answers = [
            ('TEST_22', 'Alice'),
            ('TEST_23', 'Johnson'),
            ('TEST_2',  {'day': '15', 'month': '6', 'year': '1975'}),
            ('TEST_3',  'Yes'),
            ('TEST_4',  'QQ123456C'),
            ('TEST_7',  'I am a retired teacher living in Bristol.'),
            ('TEST_8',  'Yes'),
            ('TEST_10', ['Red', 'Blue']),
            ('TEST_11', '2'),
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
            section=simple_s1, question=_q('TEST_22'),
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
                section=simple_s1, question=_q('TEST_22'),
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
            ('TEST_22', 'Bob'),
            ('TEST_23', 'Smith'),
            ('TEST_2',  {'day': '22', 'month': '3', 'year': '1982'}),
            ('TEST_3',  'No'),
            ('TEST_5',  '14 Acacia Avenue'),
            ('TEST_6',  'BS1 4TR'),
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

        # ── Neon cleanup: run this SQL once to remove old DEMO_ records ───────
        # DELETE FROM core_section WHERE section_id LIKE 'DEMO_%';
        # DELETE FROM core_schedule WHERE schedule_id LIKE 'DEMO_%';
        # DELETE FROM core_regime WHERE regime_id LIKE 'DEMO_%';

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
        self.stdout.write('            dwp_alice / dwp_bob / dwp_agent1  (pw: testpass123)')
        self.stdout.write('            defra_alice                        (pw: testpass123)')
        self.stdout.write('Regimes:    TEST_SIMPLE · TEST_SECTIONS · TEST_SCHEDULES')
        self.stdout.write('Alice:      SIMPLE_S1 complete, answer history present')
        self.stdout.write('Bob:        SECTIONS_S1 complete, S2+S3 not started')
        self.stdout.write('Carla:      no answers (fresh start)')
        self.stdout.write('solicitor1: SCHED_S3+S4 (Financial Information) for alice; SECTIONS_S2 (Your Finances) for bob')
        self.stdout.write('dwp_alice:  blanket all-regime permission (self)')
        self.stdout.write('dwp_bob:    blanket all-regime permission (self)')
        self.stdout.write('dwp_agent1: blanket permission acting for dwp_alice')
        self.stdout.write(self.style.SUCCESS('─' * 50))
