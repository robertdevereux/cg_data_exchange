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
    Regime,
    Routing,
    Schedule,
    Section,
    SectionStatus,
    User,
)


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
            dict(question_id='Q_full_name',
                 question_text='What is your full name?',
                 question_type='text'),
            dict(question_id='Q_dob',
                 question_text='What is your date of birth?',
                 question_type='text',
                 answer_type='date',
                 hint='For example, 27 3 1980'),
            dict(question_id='Q_nino_yn',
                 question_text='Do you have a National Insurance number?',
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='Q_nino_value',
                 question_text='What is your National Insurance number?',
                 question_type='text',
                 hint='For example, QQ 12 34 56 C'),
            dict(question_id='Q_address_line1',
                 question_text='Address line 1',
                 question_type='text'),
            dict(question_id='Q_address_postcode',
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
            dict(question_id='Q_simple_about',
                 question_text='Tell us a little about yourself',
                 question_type='textarea',
                 hint='2-3 sentences is fine'),
            dict(question_id='Q_simple_agree',
                 question_text='Do you agree to the terms and conditions?',
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='Q_simple_why',
                 question_text='Why do you not agree?',
                 question_type='text',
                 hint='We will take your feedback into account'),
            dict(question_id='Q_simple_colour',
                 question_text='Which colours do you like?',
                 question_type='checkbox',
                 options='Red;Green;Blue;Yellow;Purple'),
            dict(question_id='Q_simple_count',
                 question_text='How many colours did you select above?',
                 question_type='number',
                 answer_type='number'),
            # DEMO_SECTIONS — SECTIONS_S2 (table) and SECTIONS_S3
            dict(question_id='Q_fin_type',
                 question_text='Type of account',
                 question_type='radio',
                 options='Current account;Savings account;ISA;Other'),
            dict(question_id='Q_fin_provider',
                 question_text='Bank or provider name',
                 question_type='text'),
            dict(question_id='Q_fin_balance',
                 question_text='Balance (£)',
                 question_type='number',
                 answer_type='number'),
            dict(question_id='Q_additional_yn',
                 question_text='Is there anything else you would like to tell us?',
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='Q_additional_detail',
                 question_text='Please provide details',
                 question_type='textarea'),
            # DEMO_SCHEDULES — SCHED_S2
            dict(question_id='Q_phone',
                 question_text='Phone number',
                 question_type='text',
                 hint='We will only call if we need to discuss your application'),
            dict(question_id='Q_email',
                 question_text='Email address',
                 question_type='text'),
            # DEMO_SCHEDULES — SCHED_S4
            dict(question_id='Q_declare_yn',
                 question_text=(
                     'Do you declare that the information you have provided '
                     'is accurate and complete to the best of your knowledge?'
                 ),
                 question_type='radio',
                 options='Yes;No'),
            dict(question_id='Q_declare_why',
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
                 column_question_ids='Q_fin_type;Q_fin_provider;Q_fin_balance',
                 totals_question_ids='Q_fin_balance'),
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
                 column_question_ids='Q_fin_type;Q_fin_provider;Q_fin_balance',
                 totals_question_ids='Q_fin_balance'),
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
        #   Q_full_name → Q_dob → Q_nino_yn
        #     Yes → Q_nino_value → Q_simple_about → Q_simple_agree
        #     No  →               Q_simple_about → Q_simple_agree
        #   Q_simple_agree = Yes → Q_simple_colour → Q_simple_count → END
        #   Q_simple_agree = No  → Q_simple_why → END

        s = _s('SIMPLE_S1')
        route(s, 'Q_full_name',    None,    'Q_dob',           1, counters)
        route(s, 'Q_dob',          None,    'Q_nino_yn',       2, counters)
        route(s, 'Q_nino_yn',      'Yes',   'Q_nino_value',    3, counters)
        route(s, 'Q_nino_yn',      'No',    'Q_simple_about',  4, counters)
        route(s, 'Q_nino_value',   None,    'Q_simple_about',  5, counters)
        route(s, 'Q_simple_about', None,    'Q_simple_agree',  6, counters)
        route(s, 'Q_simple_agree', 'Yes',   'Q_simple_colour', 7, counters)
        route(s, 'Q_simple_agree', 'No',    'Q_simple_why',    8, counters)
        route(s, 'Q_simple_colour',None,    'Q_simple_count',  9, counters)
        route(s, 'Q_simple_count', None,    None,             10, counters)  # END
        route(s, 'Q_simple_why',   None,    None,             11, counters)  # END

        # ── SECTIONS_S1: personal details with nino branch ────────────────────
        #   Q_full_name → Q_dob → Q_nino_yn
        #     Yes → Q_nino_value → Q_address_line1 → Q_address_postcode → END
        #     No  →               Q_address_line1 → Q_address_postcode → END

        s = _s('SECTIONS_S1')
        route(s, 'Q_full_name',        None,  'Q_dob',               1, counters)
        route(s, 'Q_dob',              None,  'Q_nino_yn',           2, counters)
        route(s, 'Q_nino_yn',          'Yes', 'Q_nino_value',        3, counters)
        route(s, 'Q_nino_yn',          'No',  'Q_address_line1',     4, counters)
        route(s, 'Q_nino_value',       None,  'Q_address_line1',     5, counters)
        route(s, 'Q_address_line1',    None,  'Q_address_postcode',  6, counters)
        route(s, 'Q_address_postcode', None,  None,                  7, counters)  # END

        # ── SECTIONS_S2: table section — field sequence per row ───────────────
        s = _s('SECTIONS_S2')
        route(s, 'Q_fin_type',     None, 'Q_fin_provider', 1, counters)
        route(s, 'Q_fin_provider', None, 'Q_fin_balance',  2, counters)
        route(s, 'Q_fin_balance',  None, None,             3, counters)  # END

        # ── SECTIONS_S3: additional information with yes/no branch ────────────
        #   Q_additional_yn = Yes → Q_additional_detail → END
        #   Q_additional_yn = No  → END
        s = _s('SECTIONS_S3')
        route(s, 'Q_additional_yn',     'Yes', 'Q_additional_detail', 1, counters)
        route(s, 'Q_additional_yn',     'No',  None,                  2, counters)  # END
        route(s, 'Q_additional_detail', None,  None,                  3, counters)  # END

        # ── SCHED_S1: identity — nino branch, ends at END (no address) ────────
        #   Q_full_name → Q_dob → Q_nino_yn
        #     Yes → Q_nino_value → END
        #     No  → END
        s = _s('SCHED_S1')
        route(s, 'Q_full_name',  None,  'Q_dob',        1, counters)
        route(s, 'Q_dob',        None,  'Q_nino_yn',    2, counters)
        route(s, 'Q_nino_yn',    'Yes', 'Q_nino_value', 3, counters)
        route(s, 'Q_nino_yn',    'No',  None,           4, counters)  # END
        route(s, 'Q_nino_value', None,  None,           5, counters)  # END

        # ── SCHED_S2: contact details — linear ───────────────────────────────
        s = _s('SCHED_S2')
        route(s, 'Q_address_line1',    None, 'Q_address_postcode', 1, counters)
        route(s, 'Q_address_postcode', None, 'Q_phone',            2, counters)
        route(s, 'Q_phone',            None, 'Q_email',            3, counters)
        route(s, 'Q_email',            None, None,                 4, counters)  # END

        # ── SCHED_S3: accounts table — field sequence per row ─────────────────
        s = _s('SCHED_S3')
        route(s, 'Q_fin_type',     None, 'Q_fin_provider', 1, counters)
        route(s, 'Q_fin_provider', None, 'Q_fin_balance',  2, counters)
        route(s, 'Q_fin_balance',  None, None,             3, counters)  # END

        # ── SCHED_S4: declaration — yes/no branch ─────────────────────────────
        #   Q_declare_yn = Yes → END
        #   Q_declare_yn = No  → Q_declare_why → END
        s = _s('SCHED_S4')
        route(s, 'Q_declare_yn',  'Yes', None,           1, counters)  # END
        route(s, 'Q_declare_yn',  'No',  'Q_declare_why', 2, counters)
        route(s, 'Q_declare_why', None,  None,            3, counters)  # END

        # ── 8. PERMISSIONS ────────────────────────────────────────────────────
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

        # ── 9. CASES ──────────────────────────────────────────────────────────
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

        # ── 10. ALICE'S COMPLETED ANSWERS FOR SIMPLE_S1 ───────────────────────
        # Alice took the Yes branch on Q_nino_yn and Yes on Q_simple_agree.
        self.stdout.write('Creating answers for alice (SIMPLE_S1)…')

        simple_s1 = _s('SIMPLE_S1')
        alice_answers = [
            ('Q_full_name',     'Alice Johnson'),
            ('Q_dob',           '1975-06-15'),
            ('Q_nino_yn',       'Yes'),
            ('Q_nino_value',    'QQ123456C'),
            ('Q_simple_about',  'I am a retired teacher living in Bristol.'),
            ('Q_simple_agree',  'Yes'),
            ('Q_simple_colour', ['Red', 'Blue']),
            ('Q_simple_count',  '2'),
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

        # ── 11. ALICE'S ANSWER HISTORY (previous value for Q_full_name) ───────
        self.stdout.write('Creating answer history for alice…')

        # Delete any existing history records for this question (which may include
        # duplicates created before idempotency was in place), then ensure exactly
        # one canonical record exists with a fixed timestamp.
        confirmed_at = datetime.datetime(2026, 5, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
        existing = AnswerHistory.objects.filter(
            user=alice, actor=alice,
            regime=r_simple, case=alice_case,
            section=simple_s1, question=_q('Q_full_name'),
        )
        if existing.count() == 1 and existing.filter(
            answer='A. Johnson', confirmed_at=confirmed_at
        ).exists():
            pass  # already correct — no action needed
        else:
            existing.delete()
            AnswerHistory.objects.create(
                user=alice, actor=alice,
                regime=r_simple, case=alice_case,
                section=simple_s1, question=_q('Q_full_name'),
                answer='A. Johnson',
                confirmed_at=confirmed_at,
            )
            counters['AnswerHistory'] += 1

        # ── 12. ALICE'S SECTION STATUS ────────────────────────────────────────
        _, created = SectionStatus.objects.update_or_create(
            user=alice, regime=r_simple, section=simple_s1,
            defaults={'status': 'complete'},
        )
        if created:
            counters['SectionStatus'] += 1

        # ── 13. BOB'S COMPLETED ANSWERS FOR SECTIONS_S1 ──────────────────────
        # Bob took the No branch on Q_nino_yn (no NI number).
        self.stdout.write('Creating answers for bob (SECTIONS_S1)…')

        sections_s1 = _s('SECTIONS_S1')
        bob_answers = [
            ('Q_full_name',        'Bob Smith'),
            ('Q_dob',              '1982-03-22'),
            ('Q_nino_yn',          'No'),
            ('Q_address_line1',    '14 Acacia Avenue'),
            ('Q_address_postcode', 'BS1 4TR'),
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

        # ── 14. BOB'S SECTION STATUSES ────────────────────────────────────────
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

        # ── 15. SUMMARY ───────────────────────────────────────────────────────
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
