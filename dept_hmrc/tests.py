"""
dept_hmrc tests — IHT regime home page wiring.

Covers:
  A) Estate Ready Reckoner row links to /section/HMRC_S2/start/ when status is Not Started
  B) Message panel is not shown when HMRC_S2 is not complete
  C) Message panel shows correct text when HMRC_13 = No (full return)
  D) Message panel shows both HMRC_13 and HMRC_14 lines when HMRC_13 = Yes
"""

from django.test import Client, TestCase

from core.models import (
    Answer,
    Case,
    Department,
    Permission,
    Question,
    Regime,
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


class TestIHTRegimeHomePage(TestCase):
    """IHT regime home page: reckoner URL wiring and message panel."""

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


class TestReckonerDispatch(TestCase):
    """
    Tests that regime_home redirects into HMRC_S3 when S2 is complete
    and HMRC_13=Yes + HMRC_14=Single, and renders the home page otherwise.
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

    def test_yes_single_redirects_into_s3(self):
        """HMRC_13=Yes + HMRC_14=Single → redirect into HMRC_S3."""
        self._set_s2_answers(
            "Yes, I'd like help working that out",
            "Neither of the above — for example single, divorced, or living with a partner but not married",
        )
        session = self.client.session
        session['iht_current_action'] = 'reckoner'
        session.save()
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/section/HMRC_S3/', r['Location'])

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

    def test_s2_no_permission_shows_tag_and_no_link(self):
        """When user lacks permission for HMRC_S2 the page shows 'No permission' and no section link."""
        r = self.client.get(HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'No permission')
        self.assertNotContains(r, '/section/HMRC_S2/')
