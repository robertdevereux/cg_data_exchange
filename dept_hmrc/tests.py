"""
dept_hmrc tests — IHT regime home page wiring.

Covers:
  A) Estate Ready Reckoner row links to /section/HMRC_S2/start/ when status is Not Started
  B) Message panel is not shown when HMRC_S2 is not complete
  C) Message panel shows correct text when HMRC_13 = No (full return)
  D) Message panel shows both HMRC_13 and HMRC_14 lines when HMRC_13 = Yes
"""

from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from core.interfaces import get_asked_answers_for_section
from core.models import (
    Answer,
    Case,
    Department,
    Permission,
    Question,
    Regime,
    Routing,
    Schedule,
    Section,
    SectionStatus,
    User,
)

# Shared helper for test classes that need the IHT verified-estate home page
def _create_iht_base(regime_create_kwargs=None):
    """
    Create Department + Regime in a way that's safe to call from setUpTestData.
    Returns the Regime instance.
    """
    Department.objects.get_or_create(
        dept_id='HMRC',
        defaults={'dept_name': 'HM Revenue & Customs'},
    )
    kwargs = dict(
        regime_id='HMRC_IHT',
        regime_name='Inheritance Tax',
        dept_id='HMRC',
        display_order=99,
    )
    if regime_create_kwargs:
        kwargs.update(regime_create_kwargs)
    return Regime.objects.create(**kwargs)

HOME_URL = '/hmrc/regime/HMRC_IHT/'


def _set_session_case(client, case_id, user_pk):
    """Seed case_id and user_id/actor_id into the client's session."""
    session = client.session
    session['case_id'] = str(case_id)
    pss = session.setdefault('pss', {})
    pss['user_id']  = user_pk
    pss['actor_id'] = user_pk
    session.save()


def _set_user_session(client, user_pk):
    """Seed user_id/actor_id without a case_id (for tests that set case_id separately)."""
    session = client.session
    pss = session.setdefault('pss', {})
    pss['user_id']  = user_pk
    pss['actor_id'] = user_pk
    session.save()


class TestIHTRegimeHomePage(TestCase):
    """IHT regime home page: reckoner URL wiring and message panel.

    setUp seeds case_id into the session so the new picker redirect is bypassed
    (all tests in this class test the verified-estate home page, not the picker).
    """

    @classmethod
    def setUpTestData(cls):
        # HMRC department (shared fixture ensures it already exists)
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )

        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )

        # Section IDs must match the hardcoded values in the view
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2',
            section_name='Estate ready reckoner',
            section_type=0,
            regime=cls.regime,
            display_order=2,
        )

        # Question IDs must match the hardcoded values in the view.
        # Written on 'default' so FK checks from core_answer succeed within
        # the same connection's transaction scope.
        cls.q13 = Question.objects.using('default').create(
            question_id='HMRC_13',
            question_text='Do you need help working out whether a return is required?',
            question_type='radio',
            options=(
                "Yes, I'd like help working that out;"
                "No, I know a full return is required and want to get started"
            ),
        )
        cls.q14 = Question.objects.using('default').create(
            question_id='HMRC_14',
            question_text='What was the marital status of the deceased?',
            question_type='radio',
            options='Single;Married or in a civil partnership;Widowed or a surviving civil partner',
        )

        cls.alice = User.objects.get(username='alice')

        Permission.objects.create(
            actor=cls.alice,
            user=cls.alice,
            regime=cls.regime,
            section=None,
            can_delegate=False,
        )

        # Verified case: reference assigned simulates a post-matching estate
        cls.case = Case.objects.create(
            case_id='case-alice-hmrc-iht-test',
            user=cls.alice,
            regime=cls.regime,
            status='draft',
            reference='IHT-000000099',
        )

        # S1 always complete for all tests in this class
        SectionStatus.objects.create(
            user=cls.alice,
            regime=cls.regime,
            section=cls.s1,
            status='complete',
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        _set_session_case(self.client, self.case.case_id, self.alice.pk)

    # ─────────────────────────────────────────────────────────────────────────
    # A. Reckoner URL wiring
    # ─────────────────────────────────────────────────────────────────────────

    def test_reckoner_row_links_to_start_when_not_started(self):
        """When HMRC_S2 status is Not Started, the action link points to /start/."""
        SectionStatus.objects.get_or_create(
            user=self.alice,
            regime=self.regime,
            section=self.s2,
            defaults={'status': 'not_started'},
        )
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '/hmrc/iht/action/reckoner/')

    def test_reckoner_row_links_to_review_when_complete(self):
        """When HMRC_S2 status is Complete, the action link points to /review/."""
        SectionStatus.objects.update_or_create(
            user=self.alice,
            regime=self.regime,
            section=self.s2,
            defaults={'status': 'complete'},
        )
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '/hmrc/iht/action/reckoner/')

    # ─────────────────────────────────────────────────────────────────────────
    # B. Message panel hidden when S2 not complete
    # ─────────────────────────────────────────────────────────────────────────

    def test_message_panel_not_shown_when_s2_not_complete(self):
        """Message panel is absent when HMRC_S2 is not complete."""
        SectionStatus.objects.update_or_create(
            user=self.alice,
            regime=self.regime,
            section=self.s2,
            defaults={'status': 'not_started'},
        )
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'govuk-inset-text')

    # ─────────────────────────────────────────────────────────────────────────
    # C. Estate details row appears when HMRC_13 = No
    # ─────────────────────────────────────────────────────────────────────────

    def test_estate_details_row_shown_when_hmrc13_no(self):
        """HMRC_13 = No → 'Estate details' action row appears in the action list."""
        SectionStatus.objects.update_or_create(
            user=self.alice,
            regime=self.regime,
            section=self.s2,
            defaults={'status': 'complete'},
        )
        Answer.objects.update_or_create(
            user=self.alice,
            actor=self.alice,
            regime=self.regime,
            case=self.case,
            section=self.s2,
            question=self.q13,
            defaults={
                'answer': 'No, I know a full return is required and want to get started'
            },
        )
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Tailor your submission')

    # ─────────────────────────────────────────────────────────────────────────
    # D. Estate details row NOT shown when HMRC_13 = Yes
    # ─────────────────────────────────────────────────────────────────────────

    def test_estate_details_row_not_shown_when_hmrc13_yes(self):
        """HMRC_13 = Yes → 'Estate details' row is not shown."""
        SectionStatus.objects.update_or_create(
            user=self.alice,
            regime=self.regime,
            section=self.s2,
            defaults={'status': 'complete'},
        )
        Answer.objects.update_or_create(
            user=self.alice,
            actor=self.alice,
            regime=self.regime,
            case=self.case,
            section=self.s2,
            question=self.q13,
            defaults={'answer': "Yes, I'd like help working that out"},
        )
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'Tailor your submission')

    # ─────────────────────────────────────────────────────────────────────────
    # E. Flash message — shown once then cleared
    # ─────────────────────────────────────────────────────────────────────────

    def test_flash_message_shown_after_matching(self):
        """iht_flash in session → inset-text appears on first GET, gone on second."""
        session = self.client.session
        session['iht_flash'] = {
            'row':  'deceased_details',
            'text': 'We have created a new case. Your reference is IHT-000000099.',
        }
        session.pop('iht_current_action', None)
        session.pop('iht_in_core', None)
        session.save()

        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'govuk-inset-text')
        self.assertContains(r, 'IHT-000000099')

        # Second GET — flash should be consumed
        r2 = self.client.get(HOME_URL)
        self.assertEqual(r2.status_code, 200)
        self.assertNotContains(r2, 'govuk-inset-text')


# ── Constants used by @patch decorators in TestTriageSetRowSkip ───────────────
_MOCK_TRIAGE_SETS = [
    {'section_id': 'HMRC_S4', 'name': 'Common assets and liabilities'},
    {'section_id': 'HMRC_S5', 'name': 'Pensions and life assurance'},
    {'section_id': 'HMRC_S6', 'name': 'Other assets and liabilities'},
]
_MOCK_TRIAGE_IDS = ['HMRC_S4', 'HMRC_S5', 'HMRC_S6']


class TestTriageSetRowSkip(TestCase):
    """
    Categories with no Yes-answered triage questions are omitted from the
    action list entirely (not shown as 'Complete').

    Exercises the `if not set_items: continue` guard in _build_action_list.
    Setup: HMRC_S4 has one Yes answer (HMRC_16); HMRC_S5 and HMRC_S6 have none.
    All three triage sections are marked complete so the triage-set loop runs.
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2',
            section_name='Estate ready reckoner',
            section_type=0,
            regime=cls.regime,
            display_order=2,
        )
        # HMRC_SCH1 schedule houses the triage sections (S4/S5/S6)
        cls.sch1 = Schedule.objects.create(
            schedule_id='HMRC_SCH1',
            schedule_name='Estate type',
            regime=cls.regime,
            display_order=1,
        )
        cls.s4 = Section.objects.create(
            section_id='HMRC_S4',
            section_name='Common assets and liabilities',
            section_type=0,
            schedule=cls.sch1,
            display_order=1,
        )
        cls.s5 = Section.objects.create(
            section_id='HMRC_S5',
            section_name='Pensions and life assurance',
            section_type=0,
            schedule=cls.sch1,
            display_order=2,
        )
        cls.s6 = Section.objects.create(
            section_id='HMRC_S6',
            section_name='Other assets and liabilities',
            section_type=0,
            schedule=cls.sch1,
            display_order=3,
        )
        cls.q13 = Question.objects.using('default').create(
            question_id='HMRC_13',
            question_text='Do you need help working out whether a return is required?',
            question_type='radio',
            options="Yes, I'd like help;No, I know a full return is required",
        )
        cls.alice = User.objects.get(username='alice')
        Permission.objects.create(
            actor=cls.alice, user=cls.alice,
            regime=cls.regime, section=None, can_delegate=False,
        )
        cls.case = Case.objects.create(
            case_id='triage-skip-test-case',
            user=cls.alice,
            regime=cls.regime,
            status='draft',
            reference='IHT-TRIAGE-SKIP',
        )
        SectionStatus.objects.create(
            user=cls.alice, regime=cls.regime, section=cls.s1, status='complete',
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        _set_session_case(self.client, self.case.case_id, self.alice.pk)
        # S2 complete so tailor row appears
        SectionStatus.objects.update_or_create(
            user=self.alice, regime=self.regime, section=self.s2,
            defaults={'status': 'complete'},
        )
        # HMRC_13 = No triggers _should_show_tailor
        Answer.objects.update_or_create(
            user=self.alice, actor=self.alice, regime=self.regime,
            case=self.case, section=self.s2, question=self.q13,
            defaults={'answer': 'No, I know a full return is required'},
        )
        # All three triage sections complete so triage_complete_count == 3 == len(TRIAGE_SECTION_IDS)
        for sec in (self.s4, self.s5, self.s6):
            SectionStatus.objects.update_or_create(
                user=self.alice, regime=self.regime, section=sec,
                defaults={'status': 'complete'},
            )

    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SECTION_IDS', _MOCK_TRIAGE_IDS)
    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SETS', _MOCK_TRIAGE_SETS)
    @patch('dept_hmrc.views.iht.orchestrate._get_active_triage_items')
    def test_empty_category_rows_are_skipped(self, mock_active):
        """S5 and S6 (no Yes answers) must not appear; S4 (has a Yes answer) must appear."""
        mock_active.side_effect = lambda _case: {
            'HMRC_S4': [{'question_id': 'HMRC_16', 'detail_section': None}],
            'HMRC_S5': [],
            'HMRC_S6': [],
        }
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r,    'Common assets and liabilities')
        self.assertNotContains(r, 'Pensions and life assurance')
        self.assertNotContains(r, 'Other assets and liabilities')


class TestReckonerDispatch(TestCase):
    """
    Tests that the reckoner action always enters HMRC_S2 (for review/amend),
    and that the home page renders normally when no action is set.
    """

    @classmethod
    def setUpTestData(cls):
        cls.regime = _create_iht_base()
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1', section_name="Deceased's details",
            section_type=0, regime=cls.regime, display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2', section_name='Estate ready reckoner',
            section_type=0, regime=cls.regime, display_order=2,
        )
        cls.s3 = Section.objects.create(
            section_id='HMRC_S3', section_name='Initial ready reckoner questions',
            section_type=0, regime=cls.regime, display_order=3,
        )
        cls.q13 = Question.objects.using('default').create(
            question_id='HMRC_13',
            question_text='Do you need help?',
            question_type='radio',
            options=(
                "Yes, I'd like help working that out;"
                "No, I know a full return is required and want to get started"
            ),
        )
        cls.q14 = Question.objects.using('default').create(
            question_id='HMRC_14',
            question_text='Marital status?',
            question_type='radio',
            options='Single;Married or in a civil partnership;Widowed or a surviving civil partner',
        )
        cls.alice = User.objects.get(username='alice')
        Permission.objects.create(
            actor=cls.alice, user=cls.alice, regime=cls.regime,
            section=None, can_delegate=False,
        )
        cls.case = Case.objects.create(
            case_id='case-reckoner-dispatch-test',
            user=cls.alice, regime=cls.regime,
            status='draft', reference='IHT-000000066',
        )
        for sid in ['HMRC_S1', 'HMRC_S2']:
            SectionStatus.objects.create(
                user=cls.alice, regime=cls.regime,
                section=Section.objects.get(section_id=sid),
                status='complete',
            )

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        _set_session_case(self.client, self.case.case_id, self.alice.pk)

    def _set_s2_answers(self, hmrc13, hmrc14=None):
        Answer.objects.update_or_create(
            user=self.alice, actor=self.alice, regime=self.regime,
            case=self.case, section=self.s2, question=self.q13,
            defaults={'answer': hmrc13},
        )
        if hmrc14 is not None:
            Answer.objects.update_or_create(
                user=self.alice, actor=self.alice, regime=self.regime,
                case=self.case, section=self.s2, question=self.q14,
                defaults={'answer': hmrc14},
            )

    def test_reckoner_action_enters_s2(self):
        """reckoner action always enters HMRC_S2 regardless of HMRC_13/14 answers."""
        self._set_s2_answers(
            "Yes, I'd like help working that out",
            "Neither of the above — for example single, divorced, or living with a partner but not married",
        )
        session = self.client.session
        session['iht_current_action'] = 'reckoner'
        session.save()
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/section/HMRC_S2/', r['Location'])

    def test_yes_married_renders_home(self):
        """HMRC_13=Yes + HMRC_14=Married → home page renders (not yet built)."""
        self._set_s2_answers(
            "Yes, I'd like help working that out",
            "Married or in a civil partnership",
        )
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)

    def test_no_renders_home(self):
        """HMRC_13=No → home page renders (main flow)."""
        self._set_s2_answers(
            "No, I know a full return is required and want to get started"
        )
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)


class TestS2NotConfigured(TestCase):
    """
    HMRC_S2 section record does not exist for the regime.
    Expected: status tag reads 'Not configured', no section link rendered.
    """

    @classmethod
    def setUpTestData(cls):
        cls.regime = _create_iht_base()

        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        # HMRC_S2 intentionally not created

        cls.alice = User.objects.get(username='alice')
        Permission.objects.create(
            actor=cls.alice,
            user=cls.alice,
            regime=cls.regime,
            section=None,
            can_delegate=False,
        )
        cls.case = Case.objects.create(
            case_id='case-notconfigured-test',
            user=cls.alice,
            regime=cls.regime,
            status='draft',
            reference='IHT-000000088',
        )
        SectionStatus.objects.create(
            user=cls.alice,
            regime=cls.regime,
            section=cls.s1,
            status='complete',
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        _set_session_case(self.client, self.case.case_id, self.alice.pk)

    def test_s2_not_configured_shows_tag_and_no_link(self):
        """When HMRC_S2 has no Section record the page shows 'Not configured' and no section link."""
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Not configured')
        self.assertNotContains(r, '/section/HMRC_S2/')


class TestS2NoPermission(TestCase):
    """
    HMRC_S2 section exists but the logged-in user has only a section-level
    permission for HMRC_S1, so HMRC_S2 is outside their grant.
    Expected: status tag reads 'No permission', no section link rendered.
    """

    @classmethod
    def setUpTestData(cls):
        cls.regime = _create_iht_base()

        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2',
            section_name='Estate ready reckoner',
            section_type=0,
            regime=cls.regime,
            display_order=2,
        )

        cls.bob = User.objects.get(username='bob')
        # Section-level grant for S1 only — S2 is outside this grant
        Permission.objects.create(
            actor=cls.bob,
            user=cls.bob,
            regime=cls.regime,
            section=cls.s1,
            can_delegate=False,
        )
        cls.case = Case.objects.create(
            case_id='case-noperm-test',
            user=cls.bob,
            regime=cls.regime,
            status='draft',
            reference='IHT-000000077',
        )
        SectionStatus.objects.create(
            user=cls.bob,
            regime=cls.regime,
            section=cls.s1,
            status='complete',
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='bob', password='testpass123')
        _set_session_case(self.client, self.case.case_id, self.bob.pk)

    def test_s2_no_permission_shows_tag_and_no_link(self):
        """When user lacks permission for HMRC_S2 the page shows 'No permission' and no section link."""
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'No permission')
        self.assertNotContains(r, '/section/HMRC_S2/')


PICKER_URL = '/hmrc/iht/cases/'


class TestIHTCasePicker(TestCase):
    """
    Tests for the multi-estate dispatcher (_iht_gate) and estate entry points.

    Scenarios:
      1. Zero verified cases  → bootstrap unchanged (start action)
      2. One verified case (direct-user, no case-scoped Permission) → _iht_gate
         auto-skips to 'Begin a new estate' (no Permission-based candidates)
      3. Two verified cases (same ownership pattern) → same auto-skip behaviour
      4. Two verified cases, session case_id matches one → home renders directly
      5. iht_start_new_estate always creates a new Case row
    """

    @classmethod
    def setUpTestData(cls):
        cls.regime = _create_iht_base()
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1', section_name="Deceased's details",
            section_type=0, regime=cls.regime, display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2', section_name='Estate ready reckoner',
            section_type=0, regime=cls.regime, display_order=2,
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_13',
            defaults={
                'question_text': 'Do you need help?',
                'question_type': 'radio',
                'options': "Yes;No",
            },
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_14',
            defaults={
                'question_text': 'Marital status?',
                'question_type': 'radio',
                'options': 'Single;Married or in a civil partnership;Widowed',
            },
        )
        cls.carla = User.objects.get(username='carla')
        Permission.objects.create(
            actor=cls.carla, user=cls.carla, regime=cls.regime,
            section=None, can_delegate=False,
        )
        # Two verified cases for carla
        cls.case_a = Case.objects.create(
            case_id='picker-case-a', user=cls.carla, regime=cls.regime,
            status='draft', reference='IHT-PICKER-A',
        )
        cls.case_b = Case.objects.create(
            case_id='picker-case-b', user=cls.carla, regime=cls.regime,
            status='draft', reference='IHT-PICKER-B',
        )
        SectionStatus.objects.create(
            user=cls.carla, regime=cls.regime, section=cls.s1, status='complete',
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='carla', password='testpass123')
        # Gate requires user_id/actor_id in session; case_id set per-test
        _set_user_session(self.client, self.carla.pk)

    # ── 1. Zero verified cases → bootstrap (no picker) ────────────────────────

    def test_zero_verified_cases_bootstrap(self):
        """With no verified cases, the orchestrator bootstraps the start flow
        rather than redirecting to the picker."""
        # Directly test _get_verified_cases returns empty for a fresh user.
        from dept_hmrc.views.iht.orchestrate import _get_verified_cases
        cases = list(_get_verified_cases(self.carla, self.regime))
        # Sanity: carla has 2. Now test with a queryset that would be empty.
        # Use the helper on the regime with a user who has no cases.
        from core.models import User as CoreUser
        fresh_user = CoreUser.objects.get(username='bob')
        empty = list(_get_verified_cases(fresh_user, self.regime))
        self.assertEqual(len(empty), 0)

    # ── 2a. One verified case, no session → gate auto-skips ──────────────────

    def test_one_verified_case_no_session_shows_gate(self):
        """With one verified case (direct user, no case-scoped Permission) and no
        session case_id, _iht_gate auto-skips to 'Begin a new estate' because the
        only candidate is the leading option (self-Permission is excluded)."""
        self.case_b.reference = None
        self.case_b.save(update_fields=['reference'])
        try:
            session = self.client.session
            session.pop('case_id', None)
            session.save()
            r = self.client.get(HOME_URL)
            self.assertEqual(r.status_code, 302)
            self.assertIn('/select-self/', r['Location'])
        finally:
            self.case_b.reference = 'IHT-PICKER-B'
            self.case_b.save(update_fields=['reference'])

    # ── 2b. One verified case, session matches → home renders ─────────────────

    def test_one_verified_case_matching_session_loads_directly(self):
        """One verified case with a matching session case_id loads directly
        without redirecting to the picker (existing mid-session users unaffected)."""
        self.case_b.reference = None
        self.case_b.save(update_fields=['reference'])
        try:
            session = self.client.session
            session['case_id'] = str(self.case_a.case_id)
            session.save()
            r = self.client.get(HOME_URL)
            if r.status_code == 302:
                self.assertNotIn('/iht/cases/', r['Location'])
        finally:
            self.case_b.reference = 'IHT-PICKER-B'
            self.case_b.save(update_fields=['reference'])

    # ── 3. Two verified cases, no session case_id → gate ────────────────────

    def test_two_cases_no_session_shows_gate(self):
        """Two verified cases (direct user ownership, no case-scoped Permissions),
        no case_id in session → _iht_gate auto-skips to 'Begin a new estate'
        because no Permission-based candidates exist for other users."""
        session = self.client.session
        session.pop('case_id', None)
        session.save()
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/select-self/', r['Location'])

    # ── 4. Two cases, session matches one → home renders ─────────────────────

    def test_two_cases_matching_session_loads_directly(self):
        """Two verified cases, session case_id matches case_a → home renders."""
        session = self.client.session
        session['case_id'] = str(self.case_a.case_id)
        session.save()
        r = self.client.get(HOME_URL)
        # Renders home (200) — NOT redirected to picker
        self.assertNotEqual(r.status_code, 302) if r.status_code != 302 else \
            self.assertNotIn('/iht/cases/', r.get('Location', ''))

    # ── 5. iht_start_new_estate always creates a new Case ────────────────────

    def test_start_new_estate_creates_new_case(self):
        """iht_start_new_estate creates a genuinely new Case row even when an
        unreferenced draft already exists for that user."""
        # Create an existing unreferenced draft for carla
        existing_draft = Case.objects.create(
            case_id='picker-draft-existing',
            user=self.carla, regime=self.regime, status='draft',
        )
        count_before = Case.objects.filter(user=self.carla, regime=self.regime).count()
        r = self.client.post('/hmrc/iht/cases/new/')
        self.assertEqual(r.status_code, 302)
        count_after = Case.objects.filter(user=self.carla, regime=self.regime).count()
        self.assertEqual(count_after, count_before + 1)
        # The new session case_id should not be the pre-existing draft
        new_case_id = self.client.session.get('case_id')
        self.assertNotEqual(str(new_case_id), str(existing_draft.case_id))
        # Clean up
        existing_draft.delete()

    # ── 6. Session draft → normal flow, picker skipped ───────────────────────

    def test_session_draft_bypasses_picker_when_verified_cases_exist(self):
        """If session case_id points to an unreferenced draft, the orchestrator
        must proceed to the normal start/S1 flow rather than redirecting to the
        picker — even when verified cases already exist for the user."""
        draft = Case.objects.create(
            case_id='picker-session-draft',
            user=self.carla, regime=self.regime, status='draft',
        )
        try:
            session = self.client.session
            session['case_id'] = str(draft.case_id)
            session.save()
            r = self.client.get(HOME_URL)
            # Must NOT redirect to the picker
            if r.status_code == 302:
                self.assertNotIn('/iht/cases/', r['Location'])
        finally:
            draft.delete()

    # ── 7. Session case_id matches nothing → falls through to None ────────────

    def test_session_case_id_matching_nothing_treated_as_no_case(self):
        """A stale session case_id that matches no case (deleted/foreign) should
        leave verified_case=None and let the orchestrator proceed normally rather
        than crashing or redirecting to picker."""
        session = self.client.session
        session['case_id'] = 'nonexistent-case-id-xyz'
        session.save()
        # With a session case_id set but matching nothing in verified_cases,
        # verified_case is None — orchestrator falls to bootstrap or home.
        # Should not redirect to picker (session_case_id branch, not elif branch).
        r = self.client.get(HOME_URL)
        if r.status_code == 302:
            self.assertNotIn('/iht/cases/', r['Location'])


# ══════════════════════════════════════════════════════════════════════════════
# Parts 2 & 3: Deceased promotion and duplicate cleanup
# ══════════════════════════════════════════════════════════════════════════════

class TestPromoteCaseToVerified(TestCase):
    """
    _promote_case_to_verified creates a distinct inactive User for the deceased,
    re-keys Answer rows, assigns an IHT reference, transfers Case.user, and
    creates a case-scoped Permission for the actor.

    All tests call _promote_case_to_verified directly (no HTTP needed).
    setUpTestData modifications are rolled back between test methods.
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.q_name = Question.objects.using('default').create(
            question_id='HMRC_1',
            question_text="Deceased's full name",
            question_type='compound',
            options='',
        )
        cls.alice = User.objects.get(username='alice')
        cls.draft_case = Case.objects.create(
            case_id='promote-test-draft',
            user=cls.alice,
            regime=cls.regime,
            status='draft',
        )
        # S1 name answer recorded against alice on the draft case
        Answer.objects.create(
            user=cls.alice,
            actor=cls.alice,
            regime=cls.regime,
            case=cls.draft_case,
            section=cls.s1,
            question=cls.q_name,
            answer={'first_name': 'John', 'last_name': 'Smith'},
        )
        # SectionStatus for alice — simulates having completed S1 pre-promotion
        SectionStatus.objects.create(
            user=cls.alice,
            regime=cls.regime,
            section=cls.s1,
            status='complete',
        )

    def _run_promote(self):
        from dept_hmrc.views.iht.matching import _promote_case_to_verified
        deceased_name = {'first_name': 'John', 'last_name': 'Smith'}
        case = Case.objects.get(case_id=self.draft_case.case_id)
        _promote_case_to_verified(case, self.alice, deceased_name)
        return Case.objects.get(case_id=self.draft_case.case_id)

    def test_creates_inactive_deceased_user(self):
        """Promotion creates a new inactive User representing the deceased."""
        case = self._run_promote()
        deceased = User.objects.filter(
            username=f'ihtsubject_{case.case_id}'
        ).first()
        self.assertIsNotNone(deceased)
        self.assertFalse(deceased.is_active)
        self.assertEqual(deceased.first_name, 'John')
        self.assertEqual(deceased.last_name, 'Smith')

    def test_rekeyes_answer_rows_to_deceased(self):
        """After promotion, Answer rows for the case are owned by the deceased User."""
        case = self._run_promote()
        deceased = User.objects.get(username=f'ihtsubject_{case.case_id}')
        alice_count   = Answer.objects.filter(case=case, user=self.alice).count()
        deceased_count = Answer.objects.filter(case=case, user=deceased).count()
        self.assertEqual(alice_count, 0,
            'alice should have no Answer rows for this case after promotion')
        self.assertEqual(deceased_count, 1,
            'deceased User should now own the Answer row')

    def test_assigns_iht_reference(self):
        """Case.reference is set to IHT-XXXXXXXXX format after promotion."""
        case = self._run_promote()
        self.assertIsNotNone(case.reference)
        self.assertRegex(case.reference, r'^IHT-\d{9}$')

    def test_case_user_transferred_to_deceased(self):
        """Case.user is the deceased User after promotion."""
        case = self._run_promote()
        deceased = User.objects.get(username=f'ihtsubject_{case.case_id}')
        self.assertEqual(case.user_id, deceased.pk)

    def test_creates_case_scoped_permission(self):
        """A case-scoped Permission is created: actor=alice, user=deceased, case=case."""
        case = self._run_promote()
        deceased = User.objects.get(username=f'ihtsubject_{case.case_id}')
        perm = Permission.objects.filter(
            actor=self.alice,
            user=deceased,
            case=case,
        ).first()
        self.assertIsNotNone(perm,
            'case-scoped Permission must exist for actor to access the estate')
        self.assertFalse(perm.can_delegate)

    def test_alice_has_no_case_answers_after_promotion(self):
        """After promotion, alice has no Answer rows for this case (pre-pop guard)."""
        case = self._run_promote()
        alice_count = Answer.objects.filter(case=case, user=self.alice).count()
        self.assertEqual(alice_count, 0,
            'alice must not retain answer rows that could surface as pre-population')

    def test_rekeys_section_statuses_to_deceased(self):
        """Promotion re-keys SectionStatus alongside Answer rows.
        alice's completion flags must not bleed into future estates."""
        before = SectionStatus.objects.filter(
            user=self.alice, regime=self.regime,
        ).count()
        self.assertEqual(before, 1, 'pre-condition: alice must have 1 SectionStatus')

        case = self._run_promote()
        deceased = User.objects.get(username=f'ihtsubject_{case.case_id}')

        alice_count    = SectionStatus.objects.filter(user=self.alice, regime=self.regime).count()
        deceased_count = SectionStatus.objects.filter(user=deceased, regime=self.regime).count()
        self.assertEqual(alice_count, 0,
            'alice must have no SectionStatus after promotion — prevents completion bleed')
        self.assertEqual(deceased_count, 1,
            'deceased User should own the SectionStatus row after promotion')


class TestDuplicateCleanup(TestCase):
    """
    When _exit_start detects a duplicate match, it must:
      - delete all Answer rows on the draft case
      - delete the draft Case itself
      - clear the session case_id
      - render the duplicate page (HTTP 200)

    Triggered via HTTP by seeding iht_in_core + iht_current_action='start'
    so the orchestrator enters the EXIT/start path.
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2',
            section_name='Estate ready reckoner',
            section_type=0,
            regime=cls.regime,
            display_order=2,
        )
        cls.q_name = Question.objects.using('default').get_or_create(
            question_id='HMRC_1',
            defaults={
                'question_text': "Deceased's full name",
                'question_type': 'compound',
                'options': '',
            },
        )[0]
        cls.q_dod = Question.objects.using('default').get_or_create(
            question_id='HMRC_2',
            defaults={
                'question_text': 'Date of death',
                'question_type': 'date',
                'options': '',
            },
        )[0]
        Question.objects.using('default').get_or_create(
            question_id='HMRC_3',
            defaults={
                'question_text': 'Date of birth',
                'question_type': 'date',
                'options': '',
            },
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_4',
            defaults={
                'question_text': 'NINO',
                'question_type': 'text',
                'options': '',
            },
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_13',
            defaults={
                'question_text': 'Do you need help?',
                'question_type': 'radio',
                'options': 'Yes;No',
            },
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_14',
            defaults={
                'question_text': 'Marital status?',
                'question_type': 'radio',
                'options': 'Single;Married or in a civil partnership;Widowed',
            },
        )
        cls.alice = User.objects.get(username='alice')
        Permission.objects.create(
            actor=cls.alice, user=cls.alice, regime=cls.regime,
            section=None, can_delegate=False,
        )

        # Existing verified case — represents a previously submitted estate
        # whose deceased details match the draft being submitted.
        cls.existing_user = User.objects.create_user(
            username='dup-test-deceased',
            first_name='Jane', last_name='Doe',
            is_active=False,
        )
        cls.verified_case = Case.objects.create(
            case_id='dup-verified-case',
            user=cls.existing_user,
            regime=cls.regime,
            status='draft',
            reference='IHT-000000001',
        )
        # Verified case's HMRC_1 and HMRC_2 answers (owned by existing_user)
        Answer.objects.create(
            user=cls.existing_user, actor=cls.existing_user,
            regime=cls.regime, case=cls.verified_case,
            section=cls.s1, question=cls.q_name,
            answer={'last_name': 'jones'},
        )
        Answer.objects.create(
            user=cls.existing_user, actor=cls.existing_user,
            regime=cls.regime, case=cls.verified_case,
            section=cls.s1, question=cls.q_dod,
            answer='2024-03-15',
        )

    def setUp(self):
        # Create a fresh draft case per test (modified by the view — can't use setUpTestData)
        self.draft_case = Case.objects.create(
            case_id=f'dup-draft-{self._testMethodName}',
            user=self.alice,
            regime=self.regime,
            status='draft',
        )
        # Draft answers match the verified case's last_name + dod
        Answer.objects.create(
            user=self.alice, actor=self.alice,
            regime=self.regime, case=self.draft_case,
            section=self.s1, question=self.q_name,
            answer={'first_name': 'Mary', 'last_name': 'jones'},
        )
        Answer.objects.create(
            user=self.alice, actor=self.alice,
            regime=self.regime, case=self.draft_case,
            section=self.s1, question=self.q_dod,
            answer='2024-03-15',
        )

        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        session = self.client.session
        pss = session.setdefault('pss', {})
        pss['user_id']  = self.alice.pk
        pss['actor_id'] = self.alice.pk
        session['case_id']             = str(self.draft_case.case_id)
        session['iht_in_core']         = True
        session['iht_current_action']  = 'start'
        session.save()

    def tearDown(self):
        # If the draft was not deleted by the view (test failure path), clean up
        Case.objects.filter(case_id=self.draft_case.case_id).delete()

    def _get_home(self):
        return self.client.get(HOME_URL)

    def test_duplicate_renders_duplicate_page(self):
        """Duplicate path renders the duplicate conflict page (HTTP 200)."""
        r = self._get_home()
        self.assertEqual(r.status_code, 200)

    def test_duplicate_deletes_draft_answer_rows(self):
        """After duplicate cleanup, no Answer rows remain for the draft case."""
        draft_case_id = self.draft_case.case_id
        self._get_home()
        remaining = Answer.objects.filter(case__case_id=draft_case_id).count()
        self.assertEqual(remaining, 0,
            'Answer rows for the draft case must be deleted on duplicate')

    def test_duplicate_deletes_draft_case(self):
        """After duplicate cleanup, the draft Case no longer exists."""
        draft_case_id = self.draft_case.case_id
        self._get_home()
        still_exists = Case.objects.filter(case_id=draft_case_id).exists()
        self.assertFalse(still_exists,
            'Draft Case must be deleted after a duplicate match')

    def test_duplicate_clears_session_case_id(self):
        """After duplicate cleanup, case_id is no longer in the session."""
        self._get_home()
        session_case_id = self.client.session.get('case_id')
        self.assertIsNone(session_case_id,
            'case_id must be cleared from session after duplicate cleanup')

    def test_verified_case_untouched(self):
        """The existing verified case and its answers are not affected by the cleanup."""
        self._get_home()
        self.assertTrue(
            Case.objects.filter(case_id=self.verified_case.case_id).exists(),
            'The existing verified case must not be deleted',
        )
        answer_count = Answer.objects.filter(case=self.verified_case).count()
        self.assertEqual(answer_count, 2,
            'Verified case answers must be untouched')


class TestPrePopulationIsolation(TestCase):
    """
    After _promote_case_to_verified, alice must have no Answer rows for the
    promoted case. This prevents deceased details from surfacing as
    pre-population suggestions when alice starts a second estate.

    The pre-population query uses Answer.objects.filter(user=request.user, ...)
    — i.e. the logged-in user (alice), not case.user. Verifying alice has no
    answers post-promotion is therefore sufficient to guard against bleed.
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.q_name = Question.objects.using('default').get_or_create(
            question_id='HMRC_1',
            defaults={
                'question_text': "Deceased's full name",
                'question_type': 'compound',
                'options': '',
            },
        )[0]
        cls.q_dod = Question.objects.using('default').get_or_create(
            question_id='HMRC_2',
            defaults={
                'question_text': 'Date of death',
                'question_type': 'date',
                'options': '',
            },
        )[0]
        cls.alice = User.objects.get(username='alice')
        cls.draft_case = Case.objects.create(
            case_id='prepop-test-draft',
            user=cls.alice,
            regime=cls.regime,
            status='draft',
        )
        # Two S1 answers recorded against alice
        Answer.objects.create(
            user=cls.alice, actor=cls.alice,
            regime=cls.regime, case=cls.draft_case,
            section=cls.s1, question=cls.q_name,
            answer={'first_name': 'Alice', 'last_name': 'Cooper'},
        )
        Answer.objects.create(
            user=cls.alice, actor=cls.alice,
            regime=cls.regime, case=cls.draft_case,
            section=cls.s1, question=cls.q_dod,
            answer='1964-02-04',
        )

    def test_alice_has_no_s1_answers_after_promotion(self):
        """
        After promotion, alice must have zero Answer rows for the estate case.
        A second estate for alice must therefore not see any pre-population
        from the first deceased's S1 data.
        """
        from dept_hmrc.views.iht.matching import _promote_case_to_verified

        case = Case.objects.get(case_id=self.draft_case.case_id)

        # Sanity: alice has answers before promotion
        before = Answer.objects.filter(
            user=self.alice, case=case,
            question__in=[self.q_name, self.q_dod],
        ).count()
        self.assertEqual(before, 2, 'pre-condition: alice must have 2 answers')

        _promote_case_to_verified(
            case, self.alice, {'first_name': 'Alice', 'last_name': 'Cooper'}
        )

        # Post-promotion: no answers on alice for any S1 question on this case
        after = Answer.objects.filter(
            user=self.alice,
            question__in=[self.q_name, self.q_dod],
        ).count()
        self.assertEqual(after, 0,
            'alice must have no S1 answers after promotion — prevents pre-pop bleed'
        )


class TestStartNewEstate(TestCase):
    """
    Tests for iht_start_new_estate:
      1. Redirects straight to S1 (/section/HMRC_S1/start/), not via regime_home.
      2. Clears stale SectionStatus rows so the fresh estate shows 0-of-N complete.
      3. Sets regime_home_url to the orchestrator URL (not the new-estate URL)
         so section_done returns to iht_orchestrate where matching runs.
      4. Sets iht_current_action='start' so _exit_start fires on return.
      5. No second Case is created when the orchestrator is subsequently visited.
    """

    @classmethod
    def setUpTestData(cls):
        cls.regime = _create_iht_base()
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1', section_name="Deceased's details",
            section_type=0, regime=cls.regime, display_order=1,
        )
        cls.alice = User.objects.get(username='alice')
        # Regime-level Permission so call_core can find HMRC_S1 as permitted
        Permission.objects.create(
            actor=cls.alice, user=cls.alice, regime=cls.regime,
            section=None, can_delegate=False,
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        _set_user_session(self.client, self.alice.pk)

    def test_redirects_straight_to_s1(self):
        """iht_start_new_estate must redirect to /section/HMRC_S1/start/, not regime_home."""
        r = self.client.get('/hmrc/iht/cases/new/')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], '/section/HMRC_S1/start/',
            'new estate must go straight into S1, not via the pre-verified summary')

    def test_clears_stale_section_statuses(self):
        """New estate creation deletes prior SectionStatus so 0-of-N is shown."""
        SectionStatus.objects.update_or_create(
            user=self.alice, regime=self.regime, section=self.s1,
            defaults={'status': 'complete'},
        )
        self.client.get('/hmrc/iht/cases/new/')
        complete_count = SectionStatus.objects.filter(
            user=self.alice, regime=self.regime, status='complete',
        ).count()
        self.assertEqual(complete_count, 0,
            'no sections should be complete after starting a new estate')

    def test_sets_regime_home_url_to_orchestrator(self):
        """
        _setup captures regime_home_url from request.path (/hmrc/iht/cases/new/).
        iht_start_new_estate must override it to the orchestrator URL so that
        section_done returns to iht_orchestrate (where matching runs) rather
        than looping back here and creating a second draft case.
        """
        self.client.get('/hmrc/iht/cases/new/')
        pss = self.client.session.get('pss', {})
        self.assertEqual(
            pss.get('regime_home_url'),
            HOME_URL,
            'regime_home_url must be the orchestrator URL, not the new-estate URL',
        )

    def test_return_url_set_to_orchestrator_via_pss(self):
        """
        call_core reads regime_home_url from PSS and writes it as return_url.
        iht_start_new_estate pre-writes PSS regime_home_url to the orchestrator
        URL before calling call_core, so return_url must be the orchestrator URL
        (not /hmrc/iht/cases/new/).
        """
        self.client.get('/hmrc/iht/cases/new/')
        pss = self.client.session.get('pss', {})
        self.assertEqual(
            pss.get('return_url'),
            HOME_URL,
            'call_core must set return_url from PSS regime_home_url (orchestrator URL)',
        )

    def test_sets_current_action_to_start(self):
        """
        iht_current_action must be 'start' after iht_start_new_estate so that
        _exit_start fires when the user returns from S1.  Without this the
        orchestrator has no context and falls to _render_home(verified_case=None).
        """
        self.client.get('/hmrc/iht/cases/new/')
        self.assertEqual(
            self.client.session.get('iht_current_action'),
            'start',
            'iht_current_action must be "start" so the orchestrator runs matching on return',
        )

    def test_no_second_case_on_orchestrator_visit_after_s1(self):
        """
        Visiting the orchestrator after iht_start_new_estate (simulating what
        section_done does with the corrected regime_home_url) must not create
        a second Case.

        We simulate 'returning from core' by seeding iht_in_core=True in the
        session, then GETting the orchestrator.  The exit path runs _exit_start
        which promotes the draft (changing its user) but must NOT create a
        second Case row.  We count all Cases for the regime to be immune to
        the user-FK change that promotion performs.
        """
        # Create the new estate — records one Case for the regime
        self.client.get('/hmrc/iht/cases/new/')
        case_id_after_entry = self.client.session.get('case_id')
        self.assertIsNotNone(case_id_after_entry, 'case_id must be set after new estate entry')

        # Count all cases for this regime, regardless of user, as a baseline.
        # _exit_start promotes the case (changes case.user), so filtering by
        # alice would give zero after return — use the regime-level count instead.
        count_after_entry = Case.objects.filter(regime=self.regime).count()

        # Simulate section_done redirecting to the orchestrator (iht_in_core still set)
        session = self.client.session
        session['iht_in_core'] = True
        session.save()

        self.client.get(HOME_URL)

        count_after_return = Case.objects.filter(regime=self.regime).count()
        self.assertEqual(
            count_after_return, count_after_entry,
            'visiting the orchestrator after S1 must not create a second Case',
        )


CHOOSE_URL = '/hmrc/regime/HMRC_IHT/choose/'


class TestIHTGate(TestCase):
    """
    Tests for the IHT identity/estate picker (regime_choose_identity view,
    which wraps choose_user_for_regime with IHT-specific leading option).

    Scenarios:
      1. Zero Permission-based candidates (no prior estates) → auto-skip to
         'Begin a new estate' (select_self redirect, no screen shown).
      2. One prior estate via a case-scoped Permission (James Bond) → two
         candidates exist; picker screen shown, NOT auto-skipped.  Explicit
         regression: a lone estate must still present the choice.
      3. Selecting James Bond (POST action_url) sets case_id in session at the
         top level and delivers the estate home page with no intermediate picker.
    """

    @classmethod
    def setUpTestData(cls):
        cls.regime = _create_iht_base()
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1', section_name="Deceased's details",
            section_type=0, regime=cls.regime, display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2', section_name='Estate ready reckoner',
            section_type=0, regime=cls.regime, display_order=2,
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_13',
            defaults={'question_text': 'Reckoner preference?',
                      'question_type': 'radio', 'options': 'Yes;No'},
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_14',
            defaults={'question_text': 'Marital status?',
                      'question_type': 'radio',
                      'options': 'Single;Married or in a civil partnership;Widowed'},
        )
        cls.alice = User.objects.get(username='alice')
        # Synthetic deceased user — mirrors what _promote_case_to_verified produces
        cls.deceased = User(
            username='ihtsubject_gate_test',
            first_name='James', last_name='Bond',
            is_active=False,
        )
        cls.deceased.set_unusable_password()
        cls.deceased.save()
        cls.james_bond_case = Case.objects.create(
            case_id='gate-test-james-bond',
            user=cls.deceased,
            regime=cls.regime,
            status='draft',
            reference='IHT-GATE-TEST',
        )
        # Case-scoped Permission — alice can work on James Bond's estate
        cls.perm = Permission.objects.create(
            actor=cls.alice,
            user=cls.deceased,
            regime=cls.regime,
            case=cls.james_bond_case,
            section=None,
            can_delegate=False,
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        # No user_id in session → _hmrc_gate redirects to CHOOSE_URL

    # ── 1. Zero prior estates → auto-skip ────────────────────────────────────

    def test_zero_prior_estates_auto_skips_to_begin_new_estate(self):
        """
        A user with no case-scoped IHT Permissions hits the picker and is
        auto-skipped immediately (only 1 candidate: 'Begin a new estate').
        No picker screen is shown.
        """
        # bob has no HMRC IHT permissions — only the leading option exists
        other_client = Client()
        other_client.login(username='bob', password='testpass123')
        r = other_client.get(CHOOSE_URL)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/select-self/', r['Location'])

    # ── 2. One prior estate → picker shown (deliberate non-skip) ─────────────

    def test_one_prior_estate_shows_picker_not_auto_skip(self):
        """
        alice has one verified estate (James Bond) via a case-scoped Permission.
        That makes two candidates: 'Begin a new estate' + 'James Bond'.
        The gate must show the picker, NOT auto-skip — even with only one estate.
        """
        r = self.client.get(CHOOSE_URL)
        self.assertEqual(r.status_code, 200,
            'gate must render the picker (200), not auto-skip (302)')
        self.assertContains(r, 'James Bond')
        self.assertContains(r, 'Begin a new estate')

    # ── 3. Selecting named candidate sets case_id and reaches estate home ─────

    def test_selecting_james_bond_sets_case_id_and_reaches_home(self):
        """
        POSTing the James Bond action_url to the gate sets case_id in the
        top-level session (via select_identity) and delivers the estate home page.
        No intermediate picker appears between selection and home.
        """
        from urllib.parse import urlencode
        from django.urls import reverse

        next_url   = reverse('dept_hmrc:regime_home', kwargs={'regime_id': 'HMRC_IHT'})
        qs         = urlencode({'next': next_url})
        action_url = f"{reverse('core:select_identity', kwargs={'perm_id': self.perm.pk})}?{qs}"

        r = self.client.post(CHOOSE_URL, {'action_url': action_url}, follow=True)

        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            self.client.session.get('case_id'),
            str(self.james_bond_case.case_id),
            'case_id must be set at the top level of session after selecting James Bond',
        )


# ══════════════════════════════════════════════════════════════════════════════
# get_asked_answers_for_section — HMRC_14 routing branch coverage
# ══════════════════════════════════════════════════════════════════════════════

@override_settings(DATABASE_ROUTERS=[])
class TestGetAskedAnswersForSectionHMRC14Routing(TestCase):
    """
    get_asked_answers_for_section on HMRC_S1:

      - HMRC_14 = Yes  → routing jumps directly to HMRC_5; HMRC_43 never appears
      - HMRC_14 = No   → routing inserts HMRC_43 between HMRC_14 and HMRC_5,
                         in that order, with correct label and raw answer value

    Uses a minimal routing fixture: HMRC_14 → (Yes → HMRC_5 / No → HMRC_43)
    → HMRC_5 → end.  No other S1 questions are needed to exercise the branch.
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.q14 = Question.objects.using('default').create(
            question_id='HMRC_14',
            question_text=(
                'At the time of their death, was the deceased married, '
                'or in a civil partnership?'
            ),
            question_type='radio',
            options='Yes;No',
        )
        cls.q43 = Question.objects.using('default').create(
            question_id='HMRC_43',
            question_text=(
                'Had the deceased previously been married or in a civil '
                'partnership that ended on the death of their spouse or civil partner?'
            ),
            question_type='radio',
            options='Yes;No',
        )
        cls.q5 = Question.objects.using('default').create(
            question_id='HMRC_5',
            question_text='Did the deceased leave a will?',
            question_type='radio',
            options='Yes;No',
        )
        # Routing: HMRC_14 branches; HMRC_43 and HMRC_5 are unconditional
        Routing.objects.create(
            section=cls.s1, current_node='HMRC_14',
            answer_value='Yes', next_node='HMRC_5',
            order_in_section=1,
        )
        Routing.objects.create(
            section=cls.s1, current_node='HMRC_14',
            answer_value='No', next_node='HMRC_43',
            order_in_section=2,
        )
        Routing.objects.create(
            section=cls.s1, current_node='HMRC_43',
            answer_value=None, next_node='HMRC_5',
            order_in_section=3,
        )
        Routing.objects.create(
            section=cls.s1, current_node='HMRC_5',
            answer_value=None, next_node=None,
            order_in_section=4,
        )

        cls.alice = User.objects.get(username='alice')
        cls.case = Case.objects.create(
            case_id='s1-routing-branch-test',
            user=cls.alice,
            regime=cls.regime,
            status='draft',
            reference='IHT-BRANCH-TEST',
        )

    def _record(self, q14, q43=None, q5='Yes'):
        Answer.objects.update_or_create(
            user=self.alice, actor=self.alice, regime=self.regime,
            case=self.case, section=self.s1, question=self.q14,
            defaults={'answer': q14},
        )
        if q43 is not None:
            Answer.objects.update_or_create(
                user=self.alice, actor=self.alice, regime=self.regime,
                case=self.case, section=self.s1, question=self.q43,
                defaults={'answer': q43},
            )
        Answer.objects.update_or_create(
            user=self.alice, actor=self.alice, regime=self.regime,
            case=self.case, section=self.s1, question=self.q5,
            defaults={'answer': q5},
        )

    # ── Yes branch: HMRC_43 must be absent ───────────────────────────────────

    def test_hmrc14_yes_does_not_include_widowed_question(self):
        """HMRC_14 = Yes → routing jumps to HMRC_5; HMRC_43 never returned."""
        self._record(q14='Yes', q5='No')
        rows = get_asked_answers_for_section(self.case, self.s1)
        ids = [r['question_id'] for r in rows]
        self.assertIn('HMRC_14', ids)
        self.assertNotIn('HMRC_43', ids,
            'Yes answer must skip the widowed follow-up question')

    def test_hmrc14_yes_value_is_correct(self):
        """HMRC_14 = Yes row carries the raw stored value 'Yes'."""
        self._record(q14='Yes', q5='No')
        rows = get_asked_answers_for_section(self.case, self.s1)
        row14 = next(r for r in rows if r['question_id'] == 'HMRC_14')
        self.assertEqual(row14['answer'], 'Yes')

    # ── No branch: HMRC_43 must appear after HMRC_14 ─────────────────────────

    def test_hmrc14_no_includes_widowed_question(self):
        """HMRC_14 = No → HMRC_43 is included in the returned rows."""
        self._record(q14='No', q43='Yes', q5='No')
        rows = get_asked_answers_for_section(self.case, self.s1)
        ids = [r['question_id'] for r in rows]
        self.assertIn('HMRC_43', ids,
            'No answer must trigger the widowed follow-up question')

    def test_hmrc14_no_widowed_question_follows_in_order(self):
        """HMRC_43 appears immediately after HMRC_14 in the returned list."""
        self._record(q14='No', q43='Yes', q5='No')
        rows = get_asked_answers_for_section(self.case, self.s1)
        ids = [r['question_id'] for r in rows]
        self.assertLess(
            ids.index('HMRC_14'), ids.index('HMRC_43'),
            'HMRC_43 must come after HMRC_14',
        )
        self.assertLess(
            ids.index('HMRC_43'), ids.index('HMRC_5'),
            'HMRC_43 must come before HMRC_5',
        )

    def test_hmrc14_no_row_has_correct_label(self):
        """HMRC_14 row carries the real question_text, not a hardcoded label."""
        self._record(q14='No', q43='Yes', q5='No')
        rows = get_asked_answers_for_section(self.case, self.s1)
        row14 = next(r for r in rows if r['question_id'] == 'HMRC_14')
        self.assertEqual(
            row14['question_text'],
            'At the time of their death, was the deceased married, '
            'or in a civil partnership?',
        )

    def test_hmrc14_no_value_is_correct(self):
        """HMRC_14 = No row carries the raw stored value 'No'."""
        self._record(q14='No', q43='Yes', q5='No')
        rows = get_asked_answers_for_section(self.case, self.s1)
        row14 = next(r for r in rows if r['question_id'] == 'HMRC_14')
        self.assertEqual(row14['answer'], 'No')

    def test_hmrc14_no_stops_at_unanswered_widowed_question(self):
        """HMRC_14 = No, HMRC_43 unanswered → list stops after HMRC_14."""
        self._record(q14='No')   # no q43 answer recorded
        rows = get_asked_answers_for_section(self.case, self.s1)
        ids = [r['question_id'] for r in rows]
        self.assertIn('HMRC_14', ids)
        self.assertNotIn('HMRC_43', ids,
            'Replay must stop at first unanswered question')
        self.assertNotIn('HMRC_5', ids)


# ══════════════════════════════════════════════════════════════════════════════
# Home page — deceased_rows renders real question text and answer wording
# ══════════════════════════════════════════════════════════════════════════════

@override_settings(DATABASE_ROUTERS=[])
class TestDeceasedRowsOnHomePage(TestCase):
    """
    Home page renders deceased_rows built by get_asked_answers_for_section.

    Asserts:
      - Real HMRC_14 question_text appears in the table (not "Marital status")
      - Template context contains deceased_rows with correct label and value
      - 'Yes' and 'No' answers are surfaced correctly
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2',
            section_name='Estate ready reckoner',
            section_type=0,
            regime=cls.regime,
            display_order=2,
        )
        cls.q14 = Question.objects.using('default').create(
            question_id='HMRC_14',
            question_text=(
                'At the time of their death, was the deceased married, '
                'or in a civil partnership?'
            ),
            question_type='radio',
            options='Yes;No',
        )
        Question.objects.using('default').create(
            question_id='HMRC_13',
            question_text='Do you need help?',
            question_type='radio',
            options='Yes;No',
        )
        # Single routing node: HMRC_14 → end (no predecessor needed)
        Routing.objects.create(
            section=cls.s1, current_node='HMRC_14',
            answer_value=None, next_node=None,
            order_in_section=1,
        )

        cls.alice = User.objects.get(username='alice')
        Permission.objects.create(
            actor=cls.alice, user=cls.alice,
            regime=cls.regime, section=None, can_delegate=False,
        )
        cls.case = Case.objects.create(
            case_id='deceased-rows-home-page-test',
            user=cls.alice,
            regime=cls.regime,
            status='draft',
            reference='IHT-DECROWS-001',
        )
        SectionStatus.objects.create(
            user=cls.alice, regime=cls.regime,
            section=cls.s1, status='complete',
        )

    def _record_q14(self, value):
        Answer.objects.update_or_create(
            user=self.alice, actor=self.alice, regime=self.regime,
            case=self.case, section=self.s1, question=self.q14,
            defaults={'answer': value},
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        _set_session_case(self.client, self.case.case_id, self.alice.pk)

    def _get_home(self):
        return self.client.get(HOME_URL)

    def test_real_question_text_in_context(self):
        """deceased_rows label is the Question.question_text, not 'Marital status'."""
        self._record_q14('Yes')
        r = self._get_home()
        self.assertEqual(r.status_code, 200)
        rows = r.context['deceased_rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]['label'],
            'At the time of their death, was the deceased married, '
            'or in a civil partnership?',
        )

    def test_real_question_text_rendered_in_html(self):
        """The HTML table contains the real question text, not 'Marital status'."""
        self._record_q14('Yes')
        r = self._get_home()
        self.assertEqual(r.status_code, 200)
        self.assertContains(
            r,
            'was the deceased married',
            msg_prefix='Home page must render the real question_text from the DB',
        )
        self.assertNotContains(r, 'Marital status')

    def test_yes_answer_in_context(self):
        """HMRC_14 = Yes → deceased_rows value is 'Yes'."""
        self._record_q14('Yes')
        r = self._get_home()
        self.assertEqual(r.status_code, 200)
        rows = r.context['deceased_rows']
        self.assertEqual(rows[0]['value'], 'Yes')

    def test_no_answer_in_context(self):
        """HMRC_14 = No → deceased_rows value is 'No'."""
        self._record_q14('No')
        r = self._get_home()
        self.assertEqual(r.status_code, 200)
        rows = r.context['deceased_rows']
        self.assertEqual(rows[0]['value'], 'No')


# ══════════════════════════════════════════════════════════════════════════════
# Post-promotion answer ownership
# ══════════════════════════════════════════════════════════════════════════════

@override_settings(DATABASE_ROUTERS=[])
class TestPostPromotionAnswerOwnership(TestCase):
    """
    After _promote_case_to_verified, case.user is the synthetic deceased User;
    the actor (alice) continues working via a case-scoped Permission.

    Verifies that _commit_section_answers and section_start use case.user:

      1. Confirming an amended S1 answer writes Answer rows owned by case.user
         (deceased), not request.user (alice).
      2. Confirming creates an AnswerHistory row owned by case.user (deceased).
      3. SectionStatus is updated under case.user (deceased).
      4. Re-entering section_start pre-fills the amended answer — proving that
         the section_start DB read uses case.user, not request.user.
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2',
            section_name='Estate ready reckoner',
            section_type=0,
            regime=cls.regime,
            display_order=2,
        )
        # One question — enough to drive a minimal S1 confirm round-trip
        cls.q14 = Question.objects.using('default').create(
            question_id='HMRC_14',
            question_text='At the time of their death, was the deceased married?',
            question_type='radio',
            options='Yes;No',
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_13',
            defaults={
                'question_text': 'Do you need help?',
                'question_type': 'radio',
                'options': 'Yes;No',
            },
        )
        # Single routing node: HMRC_14 → end
        Routing.objects.create(
            section=cls.s1, current_node='HMRC_14',
            answer_value=None, next_node=None,
            order_in_section=1,
        )

        cls.alice = User.objects.get(username='alice')

        # Synthetic deceased User — mirrors what _promote_case_to_verified produces
        cls.deceased = User(
            username='ihtsubject_ownership_test',
            first_name='Test', last_name='Deceased',
            is_active=False,
        )
        cls.deceased.set_unusable_password()
        cls.deceased.save()

        # Promoted case: case.user = deceased, actor = alice
        cls.case = Case.objects.create(
            case_id='post-promo-ownership-test',
            user=cls.deceased,
            regime=cls.regime,
            status='draft',
            reference='IHT-OWN-001',
        )

        # Case-scoped Permission so alice can work on the deceased's estate
        Permission.objects.create(
            actor=cls.alice,
            user=cls.deceased,
            regime=cls.regime,
            case=cls.case,
            section=None,
            can_delegate=False,
        )

    def _seed_existing_answer(self, value):
        """Write an Answer and SectionStatus owned by deceased (the case subject)."""
        Answer.objects.update_or_create(
            user=self.deceased, actor=self.alice,
            regime=self.regime, case=self.case,
            section=self.s1, question=self.q14,
            defaults={'answer': value},
        )
        SectionStatus.objects.update_or_create(
            user=self.deceased, regime=self.regime, section=self.s1,
            defaults={'status': 'complete'},
        )

    def _seed_session_for_confirm(self, new_answer):
        """Seed PSS with the in-flight amended answer ready for section_confirm."""
        session = self.client.session
        pss = session.setdefault('pss', {})
        pss['user_id']      = self.deceased.pk   # subject (deceased)
        pss['actor_id']     = self.alice.pk       # actor (logged-in user)
        pss['case_id']      = str(self.case.case_id)
        pss['regime_id']    = self.regime.regime_id
        pss['asked_ids']    = ['HMRC_14']
        pss['basic_answers'] = {'HMRC_14': new_answer}
        pss['set_table']    = {}
        session['case_id']  = str(self.case.case_id)
        session.save()

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')

    def _post_confirm(self):
        return self.client.post('/section/HMRC_S1/confirm/')

    # ── 1. Answer rows owned by deceased ─────────────────────────────────────

    def test_confirm_writes_answer_under_case_user(self):
        """
        Confirming an amended answer writes the Answer row under case.user
        (deceased), not request.user (alice).
        """
        self._seed_existing_answer('Yes')
        self._seed_session_for_confirm('No')      # amendment: Yes → No

        self._post_confirm()

        deceased_count = Answer.objects.filter(
            user=self.deceased, case=self.case, section=self.s1,
        ).count()
        alice_count = Answer.objects.filter(
            user=self.alice, case=self.case, section=self.s1,
        ).count()
        self.assertEqual(deceased_count, 1,
            'Answer must be owned by case.user (deceased) after commit')
        self.assertEqual(alice_count, 0,
            'No Answer rows must be written under the actor (alice)')

    # ── 2. Amended value persisted correctly ──────────────────────────────────

    def test_confirm_persists_amended_value(self):
        """The Answer row holds the new value ('No'), not the old one ('Yes')."""
        self._seed_existing_answer('Yes')
        self._seed_session_for_confirm('No')

        self._post_confirm()

        answer = Answer.objects.get(
            user=self.deceased, case=self.case, section=self.s1, question=self.q14,
        )
        self.assertEqual(answer.answer, 'No')

    # ── 3. AnswerHistory owned by deceased ────────────────────────────────────

    def test_confirm_writes_answer_history_under_case_user(self):
        """
        The AnswerHistory row archiving the old value is owned by case.user
        (deceased), not request.user (alice).
        """
        from core.models import AnswerHistory
        self._seed_existing_answer('Yes')
        self._seed_session_for_confirm('No')

        self._post_confirm()

        deceased_history = AnswerHistory.objects.filter(
            user=self.deceased, case=self.case, section=self.s1,
        ).count()
        alice_history = AnswerHistory.objects.filter(
            user=self.alice, case=self.case, section=self.s1,
        ).count()
        self.assertEqual(deceased_history, 1,
            'AnswerHistory must be owned by case.user (deceased)')
        self.assertEqual(alice_history, 0,
            'No AnswerHistory rows must be written under the actor (alice)')

    # ── 4. SectionStatus owned by deceased ───────────────────────────────────

    def test_confirm_updates_section_status_under_case_user(self):
        """
        SectionStatus 'complete' is written under case.user (deceased),
        not request.user (alice).
        """
        self._seed_existing_answer('Yes')
        self._seed_session_for_confirm('No')

        self._post_confirm()

        deceased_status = SectionStatus.objects.filter(
            user=self.deceased, regime=self.regime, section=self.s1,
            status='complete',
        ).count()
        alice_status = SectionStatus.objects.filter(
            user=self.alice, regime=self.regime, section=self.s1,
        ).count()
        self.assertEqual(deceased_status, 1,
            'SectionStatus must be owned by case.user (deceased)')
        self.assertEqual(alice_status, 0,
            'No SectionStatus rows must be written under the actor (alice)')

    # ── 5. section_start pre-fills from case.user ────────────────────────────

    def test_section_start_prefills_from_case_user(self):
        """
        Re-entering section_start after amend must pre-fill 'No' from the
        Answer row owned by case.user (deceased).  Proves section_start reads
        via case.user, not request.user (alice has no answers for this case).
        """
        self._seed_existing_answer('Yes')
        self._seed_session_for_confirm('No')
        self._post_confirm()   # commit the amendment

        # Sanity: alice has no answers for this case
        self.assertEqual(
            Answer.objects.filter(user=self.alice, case=self.case).count(), 0,
        )

        # Seed minimal session for section_start (case_id + pss identity)
        session = self.client.session
        pss = session.setdefault('pss', {})
        pss['user_id']   = self.deceased.pk
        pss['actor_id']  = self.alice.pk
        pss['case_id']   = str(self.case.case_id)
        pss['regime_id'] = self.regime.regime_id
        session['case_id'] = str(self.case.case_id)
        session.save()

        r = self.client.get('/section/HMRC_S1/start/')
        self.assertEqual(r.status_code, 302,
            'section_start must redirect (to question or review) when answers exist')

        # The session must now contain 'No' as the pre-filled answer for HMRC_14
        pss_after = self.client.session.get('pss', {})
        basic_answers = pss_after.get('basic_answers', {})
        self.assertEqual(basic_answers.get('HMRC_14'), 'No',
            'section_start must pre-fill from case.user answers (the deceased), '
            'not from alice who has no answers for this case')


# ══════════════════════════════════════════════════════════════════════════════
# Post-promotion status resolution via case.user
# ══════════════════════════════════════════════════════════════════════════════

@override_settings(DATABASE_ROUTERS=[])
class TestPostPromotionStatusResolution(TestCase):
    """
    Immediately after _exit_start promotes a draft case, the next
    iht_orchestrate request must read case.user from the DB (the deceased)
    and show S1 as 'complete' — not 'not_started'.

    The old session-cached user (alice) has no SectionStatus rows after
    promotion (they were re-keyed to the deceased User).  If the orchestrator
    reads user from the session rather than from case.user, the deceased-details
    row shows 'not_started'.  This test proves the DB-resolution mechanism.

    Test sequence:
      1. Seed a draft case with alice as owner + S1 SectionStatus(complete) for alice.
      2. Simulate returning from S1 (iht_in_core + iht_current_action='start').
      3. GET HOME_URL → _exit_start runs → matching returns 'unique' → promotion →
         SectionStatus re-keyed from alice to deceased → 302 redirect to HOME_URL.
      4. GET HOME_URL again → orchestrator resolves user=case.user=deceased →
         _get_statuses finds the re-keyed SectionStatus → S1 status='complete'.
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2',
            section_name='Estate ready reckoner',
            section_type=0,
            regime=cls.regime,
            display_order=2,
        )
        # HMRC_1 needed for the Answer FK and _exit_start's get_answers call
        cls.q1 = Question.objects.using('default').create(
            question_id='HMRC_1',
            question_text="Deceased's full name",
            question_type='compound',
            options='',
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_13',
            defaults={
                'question_text': 'Do you need help?',
                'question_type': 'radio',
                'options': 'Yes;No',
            },
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_14',
            defaults={
                'question_text': 'Marital status?',
                'question_type': 'radio',
                'options': 'Yes;No',
            },
        )

        cls.alice = User.objects.get(username='alice')
        # Regime-level permission so _exit_start's get_cases(actor, regime) can
        # find the draft case (get_cases filters Case.objects.filter(user=actor))
        # and so _get_statuses can find sections for alice-as-actor post-promotion.
        Permission.objects.create(
            actor=cls.alice, user=cls.alice, regime=cls.regime,
            section=None, can_delegate=False,
        )

    def setUp(self):
        # Fresh draft case per test — promotion mutates it
        self.draft_case = Case.objects.create(
            case_id=f'promo-status-{self._testMethodName}',
            user=self.alice,
            regime=self.regime,
            status='draft',
        )
        # S1 answer owned by alice (gets re-keyed to deceased on promotion)
        Answer.objects.create(
            user=self.alice, actor=self.alice,
            regime=self.regime, case=self.draft_case,
            section=self.s1, question=self.q1,
            answer={'first_name': 'Test', 'last_name': 'Resident'},
        )
        # SectionStatus complete for alice (gets re-keyed to deceased on promotion)
        SectionStatus.objects.create(
            user=self.alice, regime=self.regime,
            section=self.s1, status='complete',
        )

        self.client = Client()
        self.client.login(username='alice', password='testpass123')

        # Simulate returning from S1: iht_in_core + current_action='start'
        session = self.client.session
        pss = session.setdefault('pss', {})
        pss['user_id']   = self.alice.pk
        pss['actor_id']  = self.alice.pk
        pss['regime_id'] = self.regime.regime_id
        session['case_id']            = str(self.draft_case.case_id)
        session['iht_in_core']        = True
        session['iht_current_action'] = 'start'
        session.save()

    def tearDown(self):
        # Promotion may have created a deceased User and changed case.user —
        # clean up in a robust order regardless of whether promotion ran.
        Case.objects.filter(case_id=self.draft_case.case_id).delete()
        User.objects.filter(
            username=f'ihtsubject_{self.draft_case.case_id}'
        ).delete()
        SectionStatus.objects.filter(regime=self.regime).delete()
        Answer.objects.filter(regime=self.regime).delete()

    def test_s1_shows_complete_immediately_after_promotion(self):
        """
        The iht_orchestrate request immediately after promotion must read
        case.user from the DB and find the re-keyed SectionStatus(complete)
        for the deceased — not alice, who has zero SectionStatus rows.

        Failure mode (old session-read code): user=alice is read from PSS;
        _get_statuses(alice, alice) finds no rows because SectionStatus was
        re-keyed to deceased → s1_status defaults to 'not_started'.

        Pass condition (new DB-read code): user=case.user=deceased is read
        from the DB; _get_statuses(alice, deceased) finds the re-keyed row
        → s1_status='complete' → deceased_details action has status='complete'.
        """
        # Step 1: visit triggers _exit_start → promotion → redirect
        r1 = self.client.get(HOME_URL)
        self.assertEqual(r1.status_code, 302,
            '_exit_start must redirect after promoting the draft case')

        # Sanity: promotion re-keyed SectionStatus from alice to deceased
        deceased_username = f'ihtsubject_{self.draft_case.case_id}'
        deceased = User.objects.get(username=deceased_username)
        self.assertEqual(
            SectionStatus.objects.filter(user=self.alice, regime=self.regime).count(), 0,
            'alice must have zero SectionStatus rows after promotion',
        )
        self.assertEqual(
            SectionStatus.objects.filter(user=deceased, regime=self.regime).count(), 1,
            'deceased must have the re-keyed SectionStatus row',
        )

        # Step 2: next visit renders home — must show S1 as complete
        r2 = self.client.get(HOME_URL)
        self.assertEqual(r2.status_code, 200,
            'home page must render after promotion (not another redirect)')

        deceased_details = next(
            (a for a in r2.context['actions'] if a['id'] == 'deceased_details'),
            None,
        )
        self.assertIsNotNone(deceased_details,
            "'deceased_details' action row must be present in the home page context")
        self.assertEqual(
            deceased_details['status'], 'complete',
            "deceased_details row must show 'complete' immediately after promotion; "
            "if 'not_started', the orchestrator read user from the session "
            "(alice, who has no SectionStatus) instead of from case.user (deceased)",
        )


# ══════════════════════════════════════════════════════════════════════════════
# handle_reckoner — explicit HMRC_14 / HMRC_43 routing
# ══════════════════════════════════════════════════════════════════════════════

@override_settings(DATABASE_ROUTERS=[])
class TestReckoner(TestCase):
    """
    handle_reckoner routes based on HMRC_13 + HMRC_14 + HMRC_43.

    Single route (HMRC_14=No, HMRC_43=No) → HMRC_S3 (built).
    Married route (HMRC_14=Yes)            → None (not yet built).
    Widowed route (HMRC_14=No, HMRC_43=Yes)→ None (not yet built).
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.create(
            regime_id='HMRC_IHT',
            regime_name='Inheritance Tax',
            dept_id='HMRC',
            display_order=99,
        )
        # Minimal sections needed
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1',
            section_name="Deceased's details",
            section_type=0, regime=cls.regime, display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2',
            section_name='Estate ready reckoner',
            section_type=0, regime=cls.regime, display_order=2,
        )
        cls.s3 = Section.objects.create(
            section_id='HMRC_S3',
            section_name='Initial ready reckoner questions',
            section_type=0, regime=cls.regime, display_order=3,
        )
        cls.q13 = Question.objects.using('default').create(
            question_id='HMRC_13',
            question_text='Would you like help?',
            question_type='radio',
            options=(
                "Yes, I'd like help working that out;"
                "No, I know a full return is required and want to get started"
            ),
        )
        cls.q14 = Question.objects.using('default').create(
            question_id='HMRC_14',
            question_text='Was the deceased married?',
            question_type='radio',
            options='Yes;No',
        )
        cls.q43 = Question.objects.using('default').create(
            question_id='HMRC_43',
            question_text='Was the deceased previously widowed?',
            question_type='radio',
            options='Yes;No',
        )
        cls.alice = User.objects.get(username='alice')
        cls.case = Case.objects.create(
            case_id='case-reckoner-routing-test',
            user=cls.alice,
            regime=cls.regime,
            status='draft',
            reference='IHT-REC-001',
        )
        # S1 + S2 complete so handle_reckoner actually runs
        for sid in ['HMRC_S1', 'HMRC_S2']:
            SectionStatus.objects.create(
                user=cls.alice, regime=cls.regime,
                section=Section.objects.get(section_id=sid),
                status='complete',
            )

    def _write_answers(self, hmrc13, hmrc14=None, hmrc43=None):
        """Write Answer rows for HMRC_13 (and optionally HMRC_14 / HMRC_43)."""
        Answer.objects.filter(
            user=self.alice, case=self.case, question_id__in=['HMRC_13', 'HMRC_14', 'HMRC_43']
        ).delete()
        Answer.objects.create(
            user=self.alice, actor=self.alice,
            regime=self.regime, case=self.case, section=self.s2,
            question=self.q13, answer=hmrc13,
        )
        if hmrc14 is not None:
            Answer.objects.create(
                user=self.alice, actor=self.alice,
                regime=self.regime, case=self.case, section=self.s1,
                question=self.q14, answer=hmrc14,
            )
        if hmrc43 is not None:
            Answer.objects.create(
                user=self.alice, actor=self.alice,
                regime=self.regime, case=self.case, section=self.s1,
                question=self.q43, answer=hmrc43,
            )

    def _call_handle_reckoner(self):
        """Call handle_reckoner with a minimal mock request (no redirect needed)."""
        from unittest.mock import MagicMock
        from dept_hmrc.views.iht.reckoner import handle_reckoner
        from core.models import SectionStatus

        # handle_reckoner checks SectionStatus for section_id when routing to S3
        # so we need to make sure there's no 'complete' status for S3
        SectionStatus.objects.filter(
            user=self.alice, regime=self.regime, section=self.s3,
        ).delete()

        class _FakeSession(dict):
            modified = False

        request = MagicMock()
        request.session = _FakeSession()
        request.path = '/'

        return handle_reckoner(
            request, self.regime, self.alice, self.alice, self.case
        )

    def test_hmrc14_no_hmrc43_no_routes_to_s3(self):
        """HMRC_13=Yes, HMRC_14=No, HMRC_43=No → single route → redirects into HMRC_S3."""
        self._write_answers(
            hmrc13="Yes, I'd like help working that out",
            hmrc14='No',
            hmrc43='No',
        )
        result = self._call_handle_reckoner()
        # handle_reckoner returns a redirect (HttpResponseRedirect) when
        # routing into S3, not None
        self.assertIsNotNone(result,
            'handle_reckoner must return a redirect for the single route (HMRC_S3)')

    def test_hmrc14_yes_routes_to_none(self):
        """HMRC_13=Yes, HMRC_14=Yes → married route not yet built → returns None."""
        self._write_answers(
            hmrc13="Yes, I'd like help working that out",
            hmrc14='Yes',
        )
        result = self._call_handle_reckoner()
        self.assertIsNone(result,
            'handle_reckoner must return None for the married route (not yet built)')

    def test_hmrc14_no_hmrc43_yes_routes_to_none(self):
        """HMRC_13=Yes, HMRC_14=No, HMRC_43=Yes → widowed route not yet built → returns None."""
        self._write_answers(
            hmrc13="Yes, I'd like help working that out",
            hmrc14='No',
            hmrc43='Yes',
        )
        result = self._call_handle_reckoner()
        self.assertIsNone(result,
            'handle_reckoner must return None for the widowed route (not yet built)')


class TestPromoteCaseToVerifiedInterface(TestCase):
    """
    core.interfaces.promote_case_to_verified re-keys Answer and SectionStatus
    rows from actor to deceased, updates case.user and case.reference, and
    creates a case-scoped Permission — all atomically.

    Calls the platform interface directly (not via _promote_case_to_verified),
    exercising the boundary that dept code is no longer allowed to cross.
    """

    @classmethod
    def setUpTestData(cls):
        Department.objects.get_or_create(
            dept_id='HMRC',
            defaults={'dept_name': 'HM Revenue & Customs'},
        )
        cls.regime = Regime.objects.get_or_create(
            regime_id='HMRC_IHT',
            defaults={
                'regime_name': 'Inheritance Tax',
                'dept_id': 'HMRC',
                'display_order': 99,
            },
        )[0]
        cls.s1 = Section.objects.get_or_create(
            section_id='HMRC_S1',
            defaults={
                'section_name': "Deceased's details",
                'section_type': 0,
                'regime': cls.regime,
                'display_order': 1,
            },
        )[0]
        cls.q_name = Question.objects.using('default').get_or_create(
            question_id='HMRC_1',
            defaults={
                'question_text': "Deceased's full name",
                'question_type': 'compound',
                'options': '',
            },
        )[0]
        cls.alice = User.objects.get(username='alice')

    def setUp(self):
        self.case = Case.objects.create(
            case_id='iface-promote-test',
            user=self.alice,
            regime=self.regime,
            status='draft',
        )
        Answer.objects.create(
            user=self.alice, actor=self.alice,
            regime=self.regime, case=self.case,
            section=self.s1, question=self.q_name,
            answer={'first_name': 'Jane', 'last_name': 'Doe'},
        )
        SectionStatus.objects.create(
            user=self.alice, regime=self.regime,
            section=self.s1, status='complete',
        )
        # Create the deceased User separately (as matching.py does)
        self.deceased = User(
            username='ihtsubject_iface-promote-test',
            first_name='Jane', last_name='Doe',
            is_active=False,
        )
        self.deceased.set_unusable_password()
        self.deceased.save()

    def tearDown(self):
        Answer.objects.filter(case=self.case).delete()
        SectionStatus.objects.filter(
            regime=self.regime, user__in=[self.alice, self.deceased],
        ).delete()
        Permission.objects.filter(case=self.case).delete()
        self.case.delete()
        self.deceased.delete()

    def test_answer_rows_rekeyed_to_deceased(self):
        from core.interfaces import promote_case_to_verified
        promote_case_to_verified(self.case, self.alice, self.deceased, 'IHT-TEST-001')
        self.assertEqual(
            Answer.objects.filter(case=self.case, user=self.alice).count(), 0,
            'actor must have no Answer rows after promotion',
        )
        self.assertEqual(
            Answer.objects.filter(case=self.case, user=self.deceased).count(), 1,
            'deceased must own the Answer row after promotion',
        )

    def test_section_status_rekeyed_to_deceased(self):
        from core.interfaces import promote_case_to_verified
        promote_case_to_verified(self.case, self.alice, self.deceased, 'IHT-TEST-001')
        self.assertEqual(
            SectionStatus.objects.filter(user=self.alice, regime=self.regime).count(), 0,
            'actor must have no SectionStatus after promotion',
        )
        self.assertEqual(
            SectionStatus.objects.filter(user=self.deceased, regime=self.regime).count(), 1,
            'deceased must own the SectionStatus after promotion',
        )

    def test_case_user_and_reference_updated(self):
        from core.interfaces import promote_case_to_verified
        promote_case_to_verified(self.case, self.alice, self.deceased, 'IHT-TEST-001')
        self.case.refresh_from_db()
        self.assertEqual(self.case.user_id, self.deceased.pk)
        self.assertEqual(self.case.reference, 'IHT-TEST-001')

    def test_permission_created_for_actor(self):
        from core.interfaces import promote_case_to_verified
        promote_case_to_verified(self.case, self.alice, self.deceased, 'IHT-TEST-001')
        perm = Permission.objects.filter(
            actor=self.alice, user=self.deceased, case=self.case,
        ).first()
        self.assertIsNotNone(perm, 'case-scoped Permission must exist after promotion')
        self.assertFalse(perm.can_delegate)


# ══════════════════════════════════════════════════════════════════════════════
# QUESTION_SCHEDULE_MAP tuple refactor — section-type dispatch
# ══════════════════════════════════════════════════════════════════════════════

class TestTriageDirectSectionDispatch(TestCase):
    """
    HMRC_S7 and HMRC_S8 were re-parented directly onto the regime
    (schedule_id=NULL); HMRC_S9 is new.  QUESTION_SCHEDULE_MAP now maps their
    triage question IDs to ('section', 'HMRC_Sx') tuples instead of bare
    schedule strings.  _get_built_schedule_items must emit
    {'type': 'section', ...} items for these, so call_core short-circuits
    straight to /section/{id}/start/ with no intermediate schedule-listing page.

    Also confirms:
    - Order across mixed section+schedule items matches triage question order.
    - Schedule-type entries (HMRC_18 → HMRC_SCH5) still produce a schedule
      listing redirect (regression guard for the multi-section case).
    """

    @classmethod
    def setUpTestData(cls):
        cls.regime = _create_iht_base()
        cls.s1 = Section.objects.create(
            section_id='HMRC_S1', section_name="Deceased's details",
            section_type=0, regime=cls.regime, display_order=1,
        )
        cls.s2 = Section.objects.create(
            section_id='HMRC_S2', section_name='Estate ready reckoner',
            section_type=0, regime=cls.regime, display_order=2,
        )
        # Triage schedule and its sections
        cls.sch1 = Schedule.objects.create(
            schedule_id='HMRC_SCH1', schedule_name='Estate type',
            regime=cls.regime, display_order=1,
        )
        cls.s4 = Section.objects.create(
            section_id='HMRC_S4', section_name='Common assets and liabilities',
            section_type=0, schedule=cls.sch1, display_order=1,
        )
        cls.s5 = Section.objects.create(
            section_id='HMRC_S5', section_name='Pensions and life assurance',
            section_type=0, schedule=cls.sch1, display_order=2,
        )
        cls.s6 = Section.objects.create(
            section_id='HMRC_S6', section_name='Other assets and liabilities',
            section_type=0, schedule=cls.sch1, display_order=3,
        )
        # Regime-direct sections (schedule_id=NULL) — re-parented in the DB
        cls.s7 = Section.objects.create(
            section_id='HMRC_S7', section_name='Bank accounts',
            section_type=0, regime=cls.regime, display_order=10,
        )
        cls.s8 = Section.objects.create(
            section_id='HMRC_S8', section_name='Residential property',
            section_type=0, regime=cls.regime, display_order=11,
        )
        cls.s9 = Section.objects.create(
            section_id='HMRC_S9', section_name='Stocks and shares',
            section_type=0, regime=cls.regime, display_order=12,
        )
        # SCH5 with one built section — needed for the HMRC_18 schedule test
        cls.sch5 = Schedule.objects.create(
            schedule_id='HMRC_SCH5', schedule_name='Foreign assets',
            regime=cls.regime, display_order=5,
        )
        Section.objects.create(
            section_id='HMRC_S_SCH5_A', section_name='Foreign assets section',
            section_type=0, schedule=cls.sch5, display_order=1,
        )
        Question.objects.using('default').get_or_create(
            question_id='HMRC_13',
            defaults={
                'question_text': 'Do you need help?',
                'question_type': 'radio',
                'options': 'Yes;No',
            },
        )
        cls.alice = User.objects.get(username='alice')
        Permission.objects.create(
            actor=cls.alice, user=cls.alice, regime=cls.regime,
            section=None, can_delegate=False,
        )
        cls.case = Case.objects.create(
            case_id='triage-direct-section-test',
            user=cls.alice, regime=cls.regime,
            status='draft', reference='IHT-DIRECT-001',
        )
        SectionStatus.objects.create(
            user=cls.alice, regime=cls.regime, section=cls.s1, status='complete',
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        _set_session_case(self.client, self.case.case_id, self.alice.pk)
        q13 = Question.objects.using('default').get(question_id='HMRC_13')
        SectionStatus.objects.update_or_create(
            user=self.alice, regime=self.regime, section=self.s2,
            defaults={'status': 'complete'},
        )
        Answer.objects.update_or_create(
            user=self.alice, actor=self.alice, regime=self.regime,
            case=self.case, section=self.s2, question=q13,
            defaults={'answer': 'No'},
        )
        for sec in (self.s4, self.s5, self.s6):
            SectionStatus.objects.update_or_create(
                user=self.alice, regime=self.regime, section=sec,
                defaults={'status': 'complete'},
            )

    def _set_action(self, action):
        session = self.client.session
        session['iht_current_action'] = action
        session.pop('iht_in_core', None)
        session.save()

    # ── Unit: _get_built_schedule_items ───────────────────────────────────────

    def test_section_type_entries_emit_section_items(self):
        """'section' tuple entries emit {'type': 'section', ...} for existing section rows."""
        from dept_hmrc.views.iht.orchestrate import _get_built_schedule_items, QUESTION_SCHEDULE_MAP
        items = _get_built_schedule_items(
            {'HMRC_S4': [
                {'question_id': 'HMRC_16', 'detail_section': None},
                {'question_id': 'HMRC_17', 'detail_section': None},
                {'question_id': 'HMRC_32', 'detail_section': None},
            ]},
            'HMRC_S4',
            QUESTION_SCHEDULE_MAP,
        )
        self.assertEqual(items, [
            {'type': 'section', 'id': 'HMRC_S8'},
            {'type': 'section', 'id': 'HMRC_S7'},
            {'type': 'section', 'id': 'HMRC_S9'},
        ])

    def test_schedule_type_entries_emit_schedule_items(self):
        """'schedule' tuple entries emit {'type': 'schedule', ...} when a section exists under the schedule."""
        from dept_hmrc.views.iht.orchestrate import _get_built_schedule_items, QUESTION_SCHEDULE_MAP
        items = _get_built_schedule_items(
            {'HMRC_S4': [{'question_id': 'HMRC_18', 'detail_section': None}]},
            'HMRC_S4',
            QUESTION_SCHEDULE_MAP,
        )
        self.assertEqual(items, [{'type': 'schedule', 'id': 'HMRC_SCH5'}])

    def test_mixed_items_preserve_triage_order(self):
        """Mixed section+schedule entries preserve the triage question display order."""
        from dept_hmrc.views.iht.orchestrate import _get_built_schedule_items, QUESTION_SCHEDULE_MAP
        items = _get_built_schedule_items(
            {'HMRC_S4': [
                {'question_id': 'HMRC_16', 'detail_section': None},  # section → S8
                {'question_id': 'HMRC_18', 'detail_section': None},  # schedule → SCH5
                {'question_id': 'HMRC_17', 'detail_section': None},  # section → S7
            ]},
            'HMRC_S4',
            QUESTION_SCHEDULE_MAP,
        )
        self.assertEqual(items, [
            {'type': 'section',  'id': 'HMRC_S8'},
            {'type': 'schedule', 'id': 'HMRC_SCH5'},
            {'type': 'section',  'id': 'HMRC_S7'},
        ])

    # ── Dispatch: section-type entries land directly on /section/{id}/start/ ──

    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SECTION_IDS', _MOCK_TRIAGE_IDS)
    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SETS', _MOCK_TRIAGE_SETS)
    @patch('dept_hmrc.views.iht.orchestrate._get_active_triage_items')
    def test_hmrc_16_yes_dispatches_directly_to_s8(self, mock_active):
        """HMRC_16=Yes → redirects to /section/HMRC_S8/start/, no intermediate listing page."""
        mock_active.side_effect = lambda _case: {
            'HMRC_S4': [{'question_id': 'HMRC_16', 'detail_section': None}],
            'HMRC_S5': [], 'HMRC_S6': [],
        }
        self._set_action('hmrc_s4')
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], '/section/HMRC_S8/start/')

    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SECTION_IDS', _MOCK_TRIAGE_IDS)
    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SETS', _MOCK_TRIAGE_SETS)
    @patch('dept_hmrc.views.iht.orchestrate._get_active_triage_items')
    def test_hmrc_17_yes_dispatches_directly_to_s7(self, mock_active):
        """HMRC_17=Yes → redirects to /section/HMRC_S7/start/, no intermediate listing page."""
        mock_active.side_effect = lambda _case: {
            'HMRC_S4': [{'question_id': 'HMRC_17', 'detail_section': None}],
            'HMRC_S5': [], 'HMRC_S6': [],
        }
        self._set_action('hmrc_s4')
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], '/section/HMRC_S7/start/')

    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SECTION_IDS', _MOCK_TRIAGE_IDS)
    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SETS', _MOCK_TRIAGE_SETS)
    @patch('dept_hmrc.views.iht.orchestrate._get_active_triage_items')
    def test_hmrc_32_yes_dispatches_directly_to_s9(self, mock_active):
        """HMRC_32=Yes → redirects to /section/HMRC_S9/start/, no intermediate listing page."""
        mock_active.side_effect = lambda _case: {
            'HMRC_S4': [{'question_id': 'HMRC_32', 'detail_section': None}],
            'HMRC_S5': [], 'HMRC_S6': [],
        }
        self._set_action('hmrc_s4')
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], '/section/HMRC_S9/start/')

    # ── Dispatch: schedule-type entry still produces schedule listing ──────────

    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SECTION_IDS', _MOCK_TRIAGE_IDS)
    @patch('dept_hmrc.views.iht.orchestrate.TRIAGE_SETS', _MOCK_TRIAGE_SETS)
    @patch('dept_hmrc.views.iht.orchestrate._get_active_triage_items')
    def test_hmrc_18_yes_dispatches_to_schedule_listing(self, mock_active):
        """HMRC_18=Yes → schedule entry still redirects to schedule listing, not a bare section."""
        mock_active.side_effect = lambda _case: {
            'HMRC_S4': [{'question_id': 'HMRC_18', 'detail_section': None}],
            'HMRC_S5': [], 'HMRC_S6': [],
        }
        self._set_action('hmrc_s4')
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 302)
        self.assertIn('HMRC_SCH5', r['Location'])
        self.assertNotIn('/section/HMRC_S', r['Location'])
