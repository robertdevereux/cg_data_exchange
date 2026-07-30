"""
End-to-end tests for Layer 2 (section processing) and Layer 1 (navigation
and permission expansion).

Covers the full citizen journey for alice on SIMPLE_S1 — Yes branch and
a backtrack that changes Q_nino_yn from Yes to No, pruning Q_nino_value
from the confirmed answer set.
"""

import json

from django.test import Client, TestCase
from django.urls import reverse

from .models import Answer, AnswerHistory, AnswerTable, Question, QuestionSet, QuestionSetMember, Regime, Routing, Section, SectionMember, SectionStatus, User
from .permissions import get_permitted_sections


class TestSimpleS1YesBranch(TestCase):
    """Walk alice through SIMPLE_S1 via the Yes branch and confirm."""

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        # Clear alice's pre-loaded SIMPLE_S1 answers so section_start treats
        # this as a fresh start (redirects to first question, not review).
        alice = User.objects.get(username='alice')
        Answer.objects.filter(user=alice, section__section_id='SIMPLE_S1').delete()

    def test_yes_branch_complete(self):
        # ── Start — first node is now the SET1 set page ───────────────────────
        r = self.client.get('/section/SIMPLE_S1/start/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/set/SET1/', r['Location'])

        # ── Post SET1 set page (first name, last name) ────────────────────────
        r = self.client.post('/section/SIMPLE_S1/set/SET1/', {
            'TEST_22': 'Alice', 'TEST_23': 'Johnson',
        })
        self.assertEqual(r.status_code, 302, 'POST S1 returned unexpected status')

        # ── Post all Yes-branch questions in routing order ────────────────────
        posts = [
            ('TEST_2',  {'date_day': '15', 'date_month': '6', 'date_year': '1975'}),
            ('TEST_3',  {'answer': 'Yes'}),
            ('TEST_4',  {'answer': 'QQ123456C'}),
            ('TEST_7',  {'answer': 'I am a retired teacher living in Bristol.'}),
            ('TEST_8',  {'answer': 'Yes'}),
            ('TEST_10', {'answer': ['Red', 'Blue']}),
            ('TEST_11', {'answer': '2'}),
        ]
        for qid, data in posts:
            r = self.client.post(f'/section/SIMPLE_S1/question/{qid}/', data)
            self.assertEqual(r.status_code, 302, f'POST {qid} returned {r.status_code}')

        # ── Review page should be reachable ───────────────────────────────────
        r = self.client.get('/section/SIMPLE_S1/review/')
        self.assertEqual(r.status_code, 200)

        # ── Confirm ───────────────────────────────────────────────────────────
        r = self.client.post('/section/SIMPLE_S1/confirm/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/done/', r['Location'])

        # ── Assertions ────────────────────────────────────────────────────────
        alice = User.objects.get(username='alice')

        # Yes branch: S1 members (TEST_22/TEST_23) + TEST_2/TEST_3/TEST_4/TEST_7/TEST_8/TEST_10/TEST_11 = 9
        self.assertEqual(
            Answer.objects.filter(user=alice, section__section_id='SIMPLE_S1').count(),
            9,
            'Expected 9 answers: S1 members TEST_22/TEST_23 + TEST_2/TEST_3/TEST_4/TEST_7/TEST_8/TEST_10/TEST_11',
        )
        self.assertFalse(
            Answer.objects.filter(user=alice, question_id='TEST_9').exists(),
            'TEST_9 (simple_why) should not be present when TEST_8=Yes',
        )
        self.assertEqual(
            SectionStatus.objects.get(user=alice, section__section_id='SIMPLE_S1').status,
            'complete',
        )
        self.assertTrue(
            AnswerHistory.objects.filter(user=alice, section__section_id='SIMPLE_S1').exists(),
            'At least one AnswerHistory record must exist (pre-loaded by fixture)',
        )


class TestBacktrack(TestCase):
    """Backtrack from Q_nino_yn=Yes to No prunes Q_nino_value from confirmed answers."""

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')

    def test_backtrack_prunes_nino_value(self):
        # ── Start — first node is the S1 set page ────────────────────────────
        self.client.get('/section/SIMPLE_S1/start/')

        # ── Post S1 set page ──────────────────────────────────────────────────
        self.client.post('/section/SIMPLE_S1/set/SET1/', {
            'TEST_22': 'Alice', 'TEST_23': 'Johnson',
        })

        # ── Walk Yes branch as far as TEST_4 (NI number value) ───────────────
        self.client.post('/section/SIMPLE_S1/question/TEST_2/',
                         {'date_day': '15', 'date_month': '6', 'date_year': '1975'})
        self.client.post('/section/SIMPLE_S1/question/TEST_3/', {'answer': 'Yes'})
        self.client.post('/section/SIMPLE_S1/question/TEST_4/', {'answer': 'QQ123456C'})

        # ── Backtrack: GET TEST_3 truncates asked_ids to that point ──────────
        self.client.get('/section/SIMPLE_S1/question/TEST_3/')

        # ── Change to No — routing jumps straight to TEST_7 ──────────────────
        self.client.post('/section/SIMPLE_S1/question/TEST_3/', {'answer': 'No'})

        # ── Complete the No branch ────────────────────────────────────────────
        self.client.post('/section/SIMPLE_S1/question/TEST_7/',
                         {'answer': 'I changed my mind about NINO.'})
        self.client.post('/section/SIMPLE_S1/question/TEST_8/', {'answer': 'Yes'})
        self.client.post('/section/SIMPLE_S1/question/TEST_10/', {'answer': ['Green']})
        self.client.post('/section/SIMPLE_S1/question/TEST_11/', {'answer': '1'})

        # ── Confirm ───────────────────────────────────────────────────────────
        r = self.client.post('/section/SIMPLE_S1/confirm/')
        self.assertEqual(r.status_code, 302)

        # ── Assertion: TEST_4 must have been pruned ───────────────────────────
        alice = User.objects.get(username='alice')
        self.assertFalse(
            Answer.objects.filter(user=alice, question_id='TEST_4').exists(),
            'TEST_4 must be pruned when backtrack changes TEST_3 to No',
        )


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: Permission expansion
# ─────────────────────────────────────────────────────────────────────────────

class TestPermissions(TestCase):
    """Unit tests for get_permitted_sections covering all three grant scopes."""

    def test_alice_acting_for_herself_sees_all_sections(self):
        """alice has regime-level grants for all three regimes → all 8 sections."""
        alice = User.objects.get(username='alice')
        sections = get_permitted_sections(alice, alice)
        self.assertEqual(
            sections.count(), 8,
            'alice should have access to all 8 sections across 3 regimes',
        )

    def test_solicitor1_acting_for_alice_sees_sched_s3_and_s4(self):
        """solicitor1 has section-level grants for SCHED_S3 and SCHED_S4 acting for alice."""
        solicitor1  = User.objects.get(username='solicitor1')
        alice       = User.objects.get(username='alice')
        sections    = get_permitted_sections(solicitor1, alice)
        section_ids = list(sections.values_list('section_id', flat=True))
        self.assertEqual(sections.count(), 2)
        self.assertIn('SCHED_S3', section_ids)
        self.assertIn('SCHED_S4', section_ids)

    def test_no_permissions_returns_empty(self):
        """carla acting for bob has no permissions → empty queryset."""
        carla    = User.objects.get(username='carla')
        bob      = User.objects.get(username='bob')
        sections = get_permitted_sections(carla, bob)
        self.assertEqual(sections.count(), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: solicitor1 → alice navigation flow
# ─────────────────────────────────────────────────────────────────────────────

class TestSolicitor1Flow(TestCase):
    """solicitor1 navigating for alice should reach SCHED_S3 and no further."""

    def setUp(self):
        self.client = Client()
        self.client.login(username='solicitor1', password='testpass123')

    def test_solicitor1_with_multiple_regimes_sees_regime_list(self):
        """
        solicitor1 has access to two regimes (TEST_SCHEDULES for alice,
        TEST_SECTIONS for bob), so /demo/ redirects to the regime card list
        rather than auto-skipping to a single regime's choose_identity page.
        """
        r = self.client.get('/demo/', follow=True)
        self.assertEqual(r.status_code, 200)
        final = r.redirect_chain[-1][0] if r.redirect_chain else ''
        self.assertIn('/demo/regimes/', final)

    def test_solicitor1_reaches_sched_s3_table(self):
        """
        Full flow via dept_demo: choose_identity for TEST_SCHEDULES → select alice
        → regime home → SCHED_FINANCES section list shows Accounts and Declaration.
        """
        from urllib.parse import urlencode
        from django.db.models import Q

        alice      = User.objects.get(username='alice')
        solicitor1 = User.objects.get(username='solicitor1')

        # Find the permission that solicitor1 holds for alice in TEST_SCHEDULES
        from core.models import Permission
        perm = Permission.objects.filter(
            actor=solicitor1, user=alice,
        ).filter(
            Q(regime_id='TEST_SCHEDULES') |
            Q(section__regime_id='TEST_SCHEDULES') |
            Q(section__schedule__regime_id='TEST_SCHEDULES')
        ).first()
        self.assertIsNotNone(perm, 'solicitor1 must have a permission for alice in TEST_SCHEDULES')

        next_url   = reverse('dept_demo:regime_home', kwargs={'regime_id': 'TEST_SCHEDULES'})
        qs         = urlencode({'next': next_url})
        action_url = f"{reverse('core:select_identity', kwargs={'perm_id': perm.pk})}?{qs}"

        # POST to choose_identity selecting alice
        r = self.client.post(
            reverse('dept_demo:choose_identity', kwargs={'regime_id': 'TEST_SCHEDULES'}),
            {'action_url': action_url},
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        final_url = r.redirect_chain[-1][0] if r.redirect_chain else ''
        self.assertIn('/demo/regime/', final_url)

        # Follow into the Financial Information schedule section list
        r2 = self.client.get(
            '/regime/TEST_SCHEDULES/schedule/SCHED_FINANCES/sections/',
            follow=True,
        )
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, 'Accounts')
        self.assertContains(r2, 'Declaration')

    def test_solicitor1_cannot_access_sched_s1(self):
        """SCHED_S1 must not appear in solicitor1's permitted sections for alice."""
        solicitor1 = User.objects.get(username='solicitor1')
        alice      = User.objects.get(username='alice')
        section_ids = list(
            get_permitted_sections(solicitor1, alice).values_list('section_id', flat=True)
        )
        self.assertNotIn('SCHED_S1', section_ids)
        self.assertIn('SCHED_S3', section_ids)


# ─────────────────────────────────────────────────────────────────────────────
# QuestionSet (multi-field page) feature
# ─────────────────────────────────────────────────────────────────────────────

class TestQuestionSetFlow(TestCase):
    """
    Tests for the QuestionSet (multi-field page) feature.
    Covers rendering, validation, navigation, review, and confirm.

    Section: SIMPLE_S1
    Routing: SET1 → Q2 → Q3; Q3=Yes → Q4 → Q7; Q3=No → Q7; Q7 → Q8;
             Q8=Yes → Q10 → Q11 → END; Q8=No → Q9 → END
    SET1 set: 'Your name' — Q22 (First name, text, required),
                          Q23 (Last name, text, required)
    """

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        # Clear alice's pre-loaded SIMPLE_S1 answers so section_start treats
        # this as a fresh start (redirects to the S1 set page, not review).
        alice = User.objects.get(username='alice')
        Answer.objects.filter(user=alice, section__section_id='SIMPLE_S1').delete()
        self.section_id = 'SIMPLE_S1'
        # Bootstrap the session by visiting section_start (follows to set/S1/).
        self.client.get(f'/section/{self.section_id}/start/', follow=True)

    # ── 1. GET renders the set template ──────────────────────────────────────

    def test_set_page_get_renders_correct_template(self):
        """GET /section/{id}/set/SET1/ renders question_set.html."""
        r = self.client.get(f'/section/{self.section_id}/set/SET1/')
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'core/question_set.html')

    def test_set_page_get_shows_all_member_fields(self):
        """Set page shows both S1 member question labels."""
        r = self.client.get(f'/section/{self.section_id}/set/SET1/')
        self.assertContains(r, 'First name')
        self.assertContains(r, 'Last name')

    def test_set_page_get_shows_set_title(self):
        """Set page heading is the set_title value ('Your name')."""
        r = self.client.get(f'/section/{self.section_id}/set/SET1/')
        self.assertContains(r, 'Your name')

    # ── 2. POST — required field blank ────────────────────────────────────────

    def test_set_page_post_missing_required_field_rerenders(self):
        """POST with a required field blank re-renders the set page (200, not 302)."""
        r = self.client.post(f'/section/{self.section_id}/set/SET1/', {
            'TEST_22': '',      # first name — required, left blank
            'TEST_23': 'Smith',
        })
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'core/question_set.html')

    def test_set_page_post_missing_required_field_shows_error_summary(self):
        """Error summary appears when a required field is blank."""
        r = self.client.post(f'/section/{self.section_id}/set/SET1/', {
            'TEST_22': '',
            'TEST_23': 'Smith',
        })
        self.assertContains(r, 'govuk-error-summary')

    def test_set_page_post_missing_required_field_shows_field_error(self):
        """Per-field error class appears on the blank required field."""
        r = self.client.post(f'/section/{self.section_id}/set/SET1/', {
            'TEST_22': '',
            'TEST_23': 'Smith',
        })
        self.assertContains(r, 'govuk-form-group--error')

    # ── 3. POST — all required fields filled advances (302) ──────────────────

    def test_set_page_post_all_required_filled_advances(self):
        """POST with all required fields non-empty redirects to the next node."""
        r = self.client.post(f'/section/{self.section_id}/set/SET1/', {
            'TEST_22': 'Alice',
            'TEST_23': 'Jones',
        })
        self.assertEqual(r.status_code, 302)

    # ── 4. Back navigation ────────────────────────────────────────────────────

    def test_back_link_after_set_points_to_set_url(self):
        """
        After submitting S1 and landing on TEST_2 (the next Q-node),
        the back link on TEST_2 must point to the S1 set URL.
        """
        self.client.post(f'/section/{self.section_id}/set/SET1/', {
            'TEST_22': 'Alice',
            'TEST_23': 'Jones',
        })
        # TEST_2 is the first Q-node after S1 in SIMPLE_S1 routing
        r = self.client.get(f'/section/{self.section_id}/question/TEST_2/')
        self.assertContains(r, f'/section/{self.section_id}/set/SET1/')

    # ── 5. Review page — set renders as grouped block ─────────────────────────

    def test_review_shows_set_title_as_group_heading(self):
        """Review page shows set_title ('Your name') above the member rows."""
        self._complete_section_to_review()
        r = self.client.get(f'/section/{self.section_id}/review/')
        self.assertContains(r, 'Your name')

    def test_review_shows_set_member_answers(self):
        """Review page shows each member question's submitted answer."""
        self._complete_section_to_review()
        r = self.client.get(f'/section/{self.section_id}/review/')
        self.assertContains(r, 'Alice')   # Q22 first name
        self.assertContains(r, 'Jones')   # Q23 last name

    def test_review_change_link_points_to_set_url(self):
        """Change link for a set member row points to the set page, not a question page."""
        self._complete_section_to_review()
        r = self.client.get(f'/section/{self.section_id}/review/')
        self.assertContains(r, f'/section/{self.section_id}/set/SET1/')
        # Member questions must not each have their own Change link
        self.assertNotContains(r, f'/section/{self.section_id}/question/TEST_22/')

    # ── 6. Confirm stores member answers as individual Answer records ──────────

    def test_confirm_stores_all_set_member_answers(self):
        """Confirm writes one Answer record per set member question (TEST_22/TEST_23)."""
        alice = User.objects.get(username='alice')
        self._complete_section_to_review()
        self.client.post(f'/section/{self.section_id}/confirm/')
        for qid in ('TEST_22', 'TEST_23'):
            self.assertTrue(
                Answer.objects.filter(user=alice, question_id=qid).exists(),
                msg=f'Expected Answer record for {qid} after confirm',
            )

    def test_confirm_stores_correct_answer_values(self):
        """Confirmed Answer records hold the values submitted on the set page."""
        alice = User.objects.get(username='alice')
        self._complete_section_to_review()
        self.client.post(f'/section/{self.section_id}/confirm/')
        self.assertEqual(
            Answer.objects.get(user=alice, question_id='TEST_22').answer,
            'Alice',
        )
        self.assertEqual(
            Answer.objects.get(user=alice, question_id='TEST_23').answer,
            'Jones',
        )

    # ── 7. Consistency checker ────────────────────────────────────────────────

    def test_consistency_checker_rejects_unknown_node(self):
        """
        If a routing row references a node ID in neither Question nor QuestionSet,
        the consistency checker must report it.
        Skipped until core/consistency.py is implemented.
        """
        self.skipTest('consistency checker not yet implemented')

    # ── Helper ────────────────────────────────────────────────────────────────

    def _complete_section_to_review(self):
        """
        Submit answers for the full SIMPLE_S1 Yes branch, ending on the review page.

        Routing: SET1 → TEST_2 → TEST_3=Yes → TEST_4 → TEST_7 → TEST_8=Yes → TEST_10 → TEST_11 → END (review)
        """
        # SET1 set page (first name / last name)
        self.client.post(f'/section/{self.section_id}/set/SET1/', {
            'TEST_22': 'Alice',
            'TEST_23': 'Jones',
        })
        # Remaining Q-nodes in routing order (Yes branch throughout)
        self.client.post(f'/section/{self.section_id}/question/TEST_2/',
                         {'date_day': '1', 'date_month': '4', 'date_year': '1980'})
        self.client.post(f'/section/{self.section_id}/question/TEST_3/',
                         {'answer': 'Yes'})    # → TEST_4
        self.client.post(f'/section/{self.section_id}/question/TEST_4/',
                         {'answer': 'AB123456C'})
        self.client.post(f'/section/{self.section_id}/question/TEST_7/',
                         {'answer': 'Some text about me'})
        self.client.post(f'/section/{self.section_id}/question/TEST_8/',
                         {'answer': 'Yes'})    # → TEST_10
        # TEST_10 is a checkbox — must supply a list so getlist() returns non-empty
        self.client.post(f'/section/{self.section_id}/question/TEST_10/',
                         {'answer': ['Blue']})
        self.client.post(f'/section/{self.section_id}/question/TEST_11/',
                         {'answer': '3'})      # → END → review


# ─────────────────────────────────────────────────────────────────────────────
# Compound question type (D6)
# ─────────────────────────────────────────────────────────────────────────────

class TestCompoundQuestion(TestCase):
    """
    Tests for the 'compound' question type.

    Covers: rendering, validation, answer storage (JSON keyed by label),
    pre-population on re-visit, and admin tools create/edit of component definitions.

    A fresh section (COMP_TEST_S1) with a single compound question (COMP_TEST_1)
    is created in setUpTestData so alice can navigate it via section_start.
    """

    _COMPONENTS = [
        {'label': 'Year 1 — most recent year', 'type': 'number'},
        {'label': 'Year 2', 'type': 'number'},
    ]

    @classmethod
    def setUpTestData(cls):
        r_simple = Regime.objects.get(regime_id='TEST_SIMPLE')
        cls.compound_q = Question.objects.create(
            question_id='COMP_TEST_1',
            question_text='Enter your income figures',
            question_type='compound',
            options=json.dumps(cls._COMPONENTS),
            is_platform=True,   # needed so super_admin can edit via tools
        )
        cls.section = Section.objects.create(
            section_id='COMP_TEST_S1',
            section_name='Income Figures',
            section_type=0,
            regime=r_simple,
        )
        # Single unconditional route: COMP_TEST_1 → END
        Routing.objects.create(
            section=cls.section,
            current_node='COMP_TEST_1',
            answer_value=None,
            next_node=None,
            order_in_section=10,
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')
        self.section_id = 'COMP_TEST_S1'
        # Bootstrap session (follows redirect to first question page)
        self.client.get(f'/section/{self.section_id}/start/', follow=True)

    # ── 1. GET rendering ──────────────────────────────────────────────────────

    def test_get_uses_compound_template(self):
        """GET renders question_compound.html for a compound question."""
        r = self.client.get(f'/section/{self.section_id}/question/COMP_TEST_1/')
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'core/question_compound.html')

    def test_get_renders_component_labels(self):
        """All component labels appear on the page."""
        r = self.client.get(f'/section/{self.section_id}/question/COMP_TEST_1/')
        self.assertContains(r, 'Year 1 — most recent year')
        self.assertContains(r, 'Year 2')

    def test_get_renders_number_inputs(self):
        """Number-type components render with inputmode=numeric."""
        r = self.client.get(f'/section/{self.section_id}/question/COMP_TEST_1/')
        self.assertContains(r, 'inputmode="numeric"')

    def test_get_renders_named_inputs(self):
        """Inputs are named component_0 and component_1."""
        r = self.client.get(f'/section/{self.section_id}/question/COMP_TEST_1/')
        self.assertContains(r, 'name="component_0"')
        self.assertContains(r, 'name="component_1"')

    # ── 2. POST — happy path stores JSON answer ───────────────────────────────

    def test_post_valid_answer_redirects(self):
        """Valid POST returns 302."""
        r = self.client.post(f'/section/{self.section_id}/question/COMP_TEST_1/', {
            'component_0': '10000',
            'component_1': '8000',
        })
        self.assertEqual(r.status_code, 302)

    def test_post_serialises_answer_as_dict_keyed_by_label(self):
        """
        POST stores compound answer in the session as a dict keyed by
        component labels.  The compound-specific serialisation is in
        _process_answer; the confirm step (which writes to Answer) is
        generic and covered by TestSimpleS1YesBranch.
        """
        self.client.post(f'/section/{self.section_id}/question/COMP_TEST_1/', {
            'component_0': '10000',
            'component_1': '8000',
        })
        # Inspect session directly — no confirm call (avoids cross-DB FK issue)
        pss = self.client.session.get('pss', {})
        basic_answers = pss.get('basic_answers', {})
        ans = basic_answers.get('COMP_TEST_1')
        self.assertIsInstance(ans, dict, 'Compound answer must be a dict')
        self.assertEqual(ans.get('Year 1 — most recent year'), '10000')
        self.assertEqual(ans.get('Year 2'), '8000')

    # ── 3. GET pre-population from existing session answer ────────────────────

    def test_get_prepopulates_values_from_session_answer(self):
        """After a valid POST, GET pre-fills component inputs from session."""
        self.client.post(f'/section/{self.section_id}/question/COMP_TEST_1/', {
            'component_0': '12345',
            'component_1': '67890',
        })
        # Navigate back (backtrack)
        r = self.client.get(f'/section/{self.section_id}/question/COMP_TEST_1/')
        self.assertContains(r, '12345')
        self.assertContains(r, '67890')

    # ── 4. Validation ─────────────────────────────────────────────────────────

    def test_post_blank_field_rerenders_with_error(self):
        """Blank required field re-renders compound template with error summary."""
        r = self.client.post(f'/section/{self.section_id}/question/COMP_TEST_1/', {
            'component_0': '',
            'component_1': '8000',
        })
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'core/question_compound.html')
        self.assertContains(r, 'govuk-error-summary')

    def test_post_non_numeric_value_shows_error(self):
        """Non-numeric value in a number component shows a 'must be a number' error."""
        r = self.client.post(f'/section/{self.section_id}/question/COMP_TEST_1/', {
            'component_0': 'not-a-number',
            'component_1': '8000',
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'must be a number')

    # ── 5. Admin tools: create compound question ──────────────────────────────

    def test_admin_add_compound_question_saves_json_options(self):
        """
        POST to tools_question_add with type=compound and JSON options
        saves the options field verbatim (the JS serialises on the real page;
        in the test we supply the JSON directly).
        """
        self.client.logout()
        self.client.login(username='super_admin', password='password123')
        components = [
            {'label': 'Revenue', 'type': 'number'},
            {'label': 'Expenses', 'type': 'number'},
        ]
        r = self.client.post('/tools/questions/add/', {
            'prefix': 'P',
            'question_text': 'Enter financial figures',
            'question_type': 'compound',
            'options': json.dumps(components),
        })
        self.assertEqual(r.status_code, 302)
        q = Question.objects.filter(question_text='Enter financial figures').first()
        self.assertIsNotNone(q)
        self.assertEqual(q.question_type, 'compound')
        parsed = json.loads(q.options)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]['label'], 'Revenue')
        self.assertEqual(parsed[1]['type'], 'number')

    # ── 6. Admin tools: edit compound question reloads components ────────────

    def test_admin_edit_compound_question_updates_options(self):
        """
        POST to tools_question_edit with updated JSON options saves correctly.
        The JS pre-population on the real page is out of scope for server tests;
        here we verify the view persists whatever JSON the client submits.
        """
        self.client.logout()
        self.client.login(username='super_admin', password='password123')
        new_components = [
            {'label': 'Year 1', 'type': 'number'},
            {'label': 'Year 2', 'type': 'number'},
            {'label': 'Year 3', 'type': 'number'},
        ]
        r = self.client.post('/tools/question/COMP_TEST_1/edit/', {
            'question_text': 'Updated income question',
            'question_type': 'compound',
            'options': json.dumps(new_components),
            'back': 'picker',
            'back_regime': '',
            'back_schedule': '',
            'back_section': '',
        })
        self.assertEqual(r.status_code, 302)
        q = Question.objects.get(question_id='COMP_TEST_1')
        self.assertEqual(q.question_text, 'Updated income question')
        parsed = json.loads(q.options)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[2]['label'], 'Year 3')

    # ── 7. Existing question types unaffected ─────────────────────────────────

    def test_existing_text_question_still_works(self):
        """text-type questions in SIMPLE_S1 still render with question_text.html."""
        # Bootstrap SIMPLE_S1 session
        self.client.get('/section/SIMPLE_S1/start/', follow=True)
        self.client.post('/section/SIMPLE_S1/set/SET1/', {
            'TEST_22': 'Alice', 'TEST_23': 'Johnson',
        })
        self.client.post('/section/SIMPLE_S1/question/TEST_2/',
                         {'date_day': '1', 'date_month': '6', 'date_year': '1990'})
        self.client.post('/section/SIMPLE_S1/question/TEST_3/', {'answer': 'No'})
        r = self.client.get('/section/SIMPLE_S1/question/TEST_7/')
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'core/question_text.html')


class TestShowConfirmation(TestCase):
    """
    Tests for the show_confirmation flag on Section.

    show_confirmation=True (default): answering the last question redirects to the
    check-your-answers review page.
    show_confirmation=False: answering the last question auto-saves answers to DB
    and redirects directly to section_done, skipping review entirely.

    Both test sections use TEST_11 (a number question already committed by
    load_test_data) so Answer FK constraints are satisfied without any
    cross-DB transaction visibility issues.
    """

    @classmethod
    def setUpTestData(cls):
        r_simple = Regime.objects.get(regime_id='TEST_SIMPLE')

        cls.section_with = Section.objects.create(
            section_id='SC_TEST_S1',
            section_name='SC With Confirmation',
            section_type=0,
            regime=r_simple,
            show_confirmation=True,
        )
        Routing.objects.create(
            section=cls.section_with,
            current_node='TEST_11',
            answer_value=None,
            next_node=None,
            order_in_section=10,
        )

        cls.section_without = Section.objects.create(
            section_id='SC_TEST_S2',
            section_name='SC Without Confirmation',
            section_type=0,
            regime=r_simple,
            show_confirmation=False,
        )
        Routing.objects.create(
            section=cls.section_without,
            current_node='TEST_11',
            answer_value=None,
            next_node=None,
            order_in_section=10,
        )

    def setUp(self):
        self.client = Client()
        # Use carla: no prior answers, so no unique-constraint conflicts when
        # SC_TEST_S2 auto-saves a TEST_11 answer.
        self.client.login(username='carla', password='testpass123')

    # ── show_confirmation=True (default behaviour) ────────────────────────────

    def test_with_confirmation_redirects_to_review(self):
        """show_confirmation=True: last question POST redirects to check-your-answers."""
        self.client.get('/section/SC_TEST_S1/start/', follow=True)
        r = self.client.post('/section/SC_TEST_S1/question/TEST_11/', {'answer': '42'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/review/', r['Location'])

    def test_with_confirmation_does_not_save_to_db(self):
        """show_confirmation=True: answers are NOT committed until confirm is POSTed."""
        carla = User.objects.get(username='carla')
        self.client.get('/section/SC_TEST_S1/start/', follow=True)
        self.client.post('/section/SC_TEST_S1/question/TEST_11/', {'answer': '42'})

        self.assertFalse(
            Answer.objects.filter(user=carla, section__section_id='SC_TEST_S1').exists(),
            'Answers must not be committed until the confirm step',
        )

    # ── show_confirmation=False (auto-save path) ──────────────────────────────

    def test_without_confirmation_redirects_to_done(self):
        """show_confirmation=False: last question POST skips review and redirects to done."""
        self.client.get('/section/SC_TEST_S2/start/', follow=True)
        r = self.client.post('/section/SC_TEST_S2/question/TEST_11/', {'answer': '42'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/done/', r['Location'])

    def test_without_confirmation_saves_answers(self):
        """show_confirmation=False: answers are committed to DB on last question POST."""
        carla = User.objects.get(username='carla')
        self.client.get('/section/SC_TEST_S2/start/', follow=True)
        self.client.post('/section/SC_TEST_S2/question/TEST_11/', {'answer': '42'})

        self.assertTrue(
            Answer.objects.filter(user=carla, section__section_id='SC_TEST_S2').exists(),
            'Answers must be committed immediately when show_confirmation=False',
        )

    def test_without_confirmation_marks_section_complete(self):
        """show_confirmation=False: SectionStatus is set to complete."""
        carla = User.objects.get(username='carla')
        self.client.get('/section/SC_TEST_S2/start/', follow=True)
        self.client.post('/section/SC_TEST_S2/question/TEST_11/', {'answer': '42'})

        status = SectionStatus.objects.filter(
            user=carla, section__section_id='SC_TEST_S2',
        ).first()
        self.assertIsNotNone(status)
        self.assertEqual(status.status, 'complete')

    def test_without_confirmation_clears_section_session(self):
        """show_confirmation=False: section-scoped session keys are removed after save."""
        self.client.get('/section/SC_TEST_S2/start/', follow=True)
        self.client.post('/section/SC_TEST_S2/question/TEST_11/', {'answer': '42'})

        pss = self.client.session.get('pss', {})
        self.assertNotIn('basic_answers', pss)
        self.assertNotIn('asked_ids', pss)
        self.assertNotIn('routing_table', pss)

    # ── Admin tools: create and edit show_confirmation ────────────────────────

    def test_admin_create_section_saves_show_confirmation_false(self):
        """tools_section_create stores show_confirmation=False when checkbox omitted."""
        self.client.logout()
        self.client.login(username='super_admin', password='password123')
        r = self.client.post('/tools/sections/create/', {
            'section_name': 'Nav Section',
            'section_type': '0',
            # show_confirmation checkbox not submitted → False
        })
        self.assertEqual(r.status_code, 302)
        s = Section.objects.filter(section_name='Nav Section').first()
        self.assertIsNotNone(s)
        self.assertFalse(s.show_confirmation)

    def test_admin_create_section_saves_show_confirmation_true(self):
        """tools_section_create stores show_confirmation=True when checkbox submitted."""
        self.client.logout()
        self.client.login(username='super_admin', password='password123')
        r = self.client.post('/tools/sections/create/', {
            'section_name': 'Standard Section',
            'section_type': '0',
            'show_confirmation': 'on',
        })
        self.assertEqual(r.status_code, 302)
        s = Section.objects.filter(section_name='Standard Section').first()
        self.assertIsNotNone(s)
        self.assertTrue(s.show_confirmation)

    def test_admin_edit_section_updates_show_confirmation(self):
        """tools_section_edit saves updated show_confirmation value."""
        self.client.logout()
        self.client.login(username='super_admin', password='password123')
        # SC_TEST_S2 was created with show_confirmation=False; flip it to True
        r = self.client.post('/tools/sections/SC_TEST_S2/edit/', {
            'section_name': 'SC Without Confirmation',
            'section_type': '0',
            'show_confirmation': 'on',
        })
        self.assertEqual(r.status_code, 302)
        s = Section.objects.get(section_id='SC_TEST_S2')
        self.assertTrue(s.show_confirmation)


class TestRoutingAdminTools(TestCase):
    """
    Tests for C1 (END in next_node dropdown), C2 (question-type info endpoint),
    and C3 (scalar condition storage).

    Uses TEST_3 (radio, Yes/No) and TEST_11 (number) — both already committed
    by load_test_data, so no cross-DB FK issues.
    """

    @classmethod
    def setUpTestData(cls):
        r_simple = Regime.objects.get(regime_id='TEST_SIMPLE')

        cls.section = Section.objects.create(
            section_id='RT_TEST_S1',
            section_name='Routing Admin Test',
            section_type=0,
            regime=r_simple,
        )
        # Pool members must be registered before routing
        SectionMember.objects.create(section=cls.section, node_id='TEST_3',  node_type='Q', added_order=10)
        SectionMember.objects.create(section=cls.section, node_id='TEST_11', node_type='Q', added_order=20)

        # TEST_3 (radio) as branching entry node: Yes → TEST_11, No → END
        Routing.objects.create(
            section=cls.section,
            current_node='TEST_3',
            answer_value='Yes',
            next_node='TEST_11',
            order_in_section=10,
        )
        Routing.objects.create(
            section=cls.section,
            current_node='TEST_3',
            answer_value='No',
            next_node=None,
            order_in_section=20,
        )
        # TEST_11 (number) linear, routes to END
        Routing.objects.create(
            section=cls.section,
            current_node='TEST_11',
            answer_value=None,
            next_node=None,
            order_in_section=30,
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='super_admin', password='password123')

    # ── C1: END in next_node ──────────────────────────────────────────────────

    def test_add_condition_default_next_node_is_end(self):
        """Adding a condition without specifying next_node stores next_node=None (END)."""
        r = self.client.post(
            '/tools/sections/RT_TEST_S1/routing/add-condition/',
            {'node_id': 'TEST_3', 'answer_value': 'Maybe'},
        )
        self.assertEqual(r.status_code, 302)
        row = Routing.objects.get(
            section__section_id='RT_TEST_S1', current_node='TEST_3', answer_value='Maybe'
        )
        self.assertIsNone(row.next_node)

    def test_add_condition_with_explicit_next_node(self):
        """Adding a condition with next_node set stores the given routing target."""
        r = self.client.post(
            '/tools/sections/RT_TEST_S1/routing/add-condition/',
            {'node_id': 'TEST_3', 'answer_value': 'Perhaps', 'next_node': 'TEST_11'},
        )
        self.assertEqual(r.status_code, 302)
        row = Routing.objects.get(
            section__section_id='RT_TEST_S1', current_node='TEST_3', answer_value='Perhaps'
        )
        self.assertEqual(row.next_node, 'TEST_11')

    def test_add_condition_invalid_next_node_falls_back_to_end(self):
        """An invalid (non-existent) next_node value is silently ignored — END is stored."""
        r = self.client.post(
            '/tools/sections/RT_TEST_S1/routing/add-condition/',
            {'node_id': 'TEST_3', 'answer_value': 'Possibly', 'next_node': 'NONEXISTENT_Q'},
        )
        self.assertEqual(r.status_code, 302)
        row = Routing.objects.get(
            section__section_id='RT_TEST_S1', current_node='TEST_3', answer_value='Possibly'
        )
        self.assertIsNone(row.next_node)

    def test_routing_tree_page_contains_end(self):
        """The routing tree page renders and includes the word END."""
        r = self.client.get('/tools/sections/RT_TEST_S1/routing/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'END')

    def test_routing_tree_page_shows_end_destination(self):
        """Condition rows that route to END display 'END' in the tree."""
        r = self.client.get('/tools/sections/RT_TEST_S1/routing/')
        # TEST_3 No → END and TEST_11 default → END are both in the tree
        self.assertContains(r, 'END')

    # ── C2: Question type info endpoint ──────────────────────────────────────

    def test_question_type_view_returns_radio(self):
        """GET /tools/questions/TEST_3/type/ returns question_type=radio."""
        r = self.client.get('/tools/questions/TEST_3/type/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['question_type'], 'radio')
        self.assertIn('Yes', data['options'])

    def test_question_type_view_returns_number(self):
        """GET /tools/questions/TEST_11/type/ returns question_type=number."""
        r = self.client.get('/tools/questions/TEST_11/type/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['question_type'], 'number')

    def test_question_type_view_unknown_returns_404(self):
        """GET for a non-existent question_id returns 404."""
        r = self.client.get('/tools/questions/NONEXISTENT_Q999/type/')
        self.assertEqual(r.status_code, 404)

    def test_routing_tree_renders_question_nodes(self):
        """The routing tree page renders correctly and shows both question node IDs."""
        r = self.client.get('/tools/sections/RT_TEST_S1/routing/')
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        # Both question nodes should appear as labels in the tree
        self.assertIn('TEST_3', content)
        self.assertIn('TEST_11', content)

    # ── C3: Scalar condition storage ──────────────────────────────────────────

    def test_scalar_condition_stores_comparator_and_threshold(self):
        """Adding a scalar condition correctly stores comparator and threshold_value."""
        r = self.client.post(
            '/tools/sections/RT_TEST_S1/routing/add-condition/',
            {
                'node_id':         'TEST_11',
                'comparator':      '>=',
                'threshold_value': '50000',
            },
        )
        self.assertEqual(r.status_code, 302)
        rows = Routing.objects.filter(
            section__section_id='RT_TEST_S1',
            current_node='TEST_11',
            comparator='>=',
        )
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.comparator, '>=')
        self.assertIsNotNone(row.threshold_value)
        self.assertEqual(int(row.threshold_value), 50000)

    def test_scalar_condition_auto_labels_answer_value(self):
        """Scalar conditions without explicit answer_value get an auto-generated label."""
        self.client.post(
            '/tools/sections/RT_TEST_S1/routing/add-condition/',
            {
                'node_id':         'TEST_11',
                'comparator':      '<',
                'threshold_value': '10000',
            },
        )
        row = Routing.objects.filter(
            section__section_id='RT_TEST_S1',
            current_node='TEST_11',
            comparator='<',
        ).first()
        self.assertIsNotNone(row)
        self.assertIn('<', row.answer_value)
        self.assertIn('10000', row.answer_value)

    # ── Gap fix: per-option END destination ──────────────────────────────────

    def test_insert_branching_question_no_default_dest_omits_default_row(self):
        """Leaving default_dest blank ('Not set') should create only specific
        condition rows — no unconditional default row."""
        regime = Regime.objects.get(regime_id='TEST_SIMPLE')
        section = Section.objects.create(
            section_id='RT_BRANCH_INSERT',
            section_name='Branch Insert Test',
            section_type=0,
            regime=regime,
        )
        SectionMember.objects.create(section=section, node_id='TEST_3', node_type='Q', added_order=10)
        r = self.client.post(
            '/tools/sections/RT_BRANCH_INSERT/routing/insert/',
            {
                'position':            'first',
                'anchor_node':         '',
                'anchor_answer_value': '',
                'node_type':           'question',
                'node_id':             'TEST_3',
                'branching':           'yes',
                'condition_0_value':   'Yes',
                'condition_0_dest':    '',   # END
                'condition_1_value':   'No',
                'condition_1_dest':    '',   # END
                'default_dest':        '',   # Not set — no default row
            },
        )
        self.assertEqual(r.status_code, 302)
        rows = Routing.objects.filter(section=section, current_node='TEST_3')
        # Only 2 specific condition rows — no default row created
        self.assertEqual(rows.count(), 2)
        for row in rows:
            self.assertIsNone(row.next_node)

    def test_insert_branching_question_with_end_destination_saves_null_next_node(self):
        """Inserting a branching question with default_dest='__END__' creates a
        default row with next_node=None."""
        regime = Regime.objects.get(regime_id='TEST_SIMPLE')
        section = Section.objects.create(
            section_id='RT_BRANCH_INSERT2',
            section_name='Branch Insert Test 2',
            section_type=0,
            regime=regime,
        )
        SectionMember.objects.create(section=section, node_id='TEST_3', node_type='Q', added_order=10)
        r = self.client.post(
            '/tools/sections/RT_BRANCH_INSERT2/routing/insert/',
            {
                'position':            'first',
                'anchor_node':         '',
                'anchor_answer_value': '',
                'node_type':           'question',
                'node_id':             'TEST_3',
                'branching':           'yes',
                'condition_0_value':   'Yes',
                'condition_0_dest':    '',        # END
                'condition_1_value':   'No',
                'condition_1_dest':    '',        # END
                'default_dest':        '__END__', # explicit END → creates default row
            },
        )
        self.assertEqual(r.status_code, 302)
        rows = Routing.objects.filter(section=section, current_node='TEST_3')
        # 2 specific conditions + 1 default row = 3 rows
        self.assertEqual(rows.count(), 3)
        for row in rows:
            self.assertIsNone(row.next_node)

    def test_first_condition_on_linear_question_with_end_destination(self):
        """Adding the first branch condition to a linear (non-branching) question
        with next_node='' (END) saves next_node=None."""
        # TEST_11 is currently linear (one row, answer_value=None) in RT_TEST_S1.
        r = self.client.post(
            '/tools/sections/RT_TEST_S1/routing/add-condition/',
            {'node_id': 'TEST_11', 'answer_value': 'high', 'next_node': ''},
        )
        self.assertEqual(r.status_code, 302)
        row = Routing.objects.get(
            section__section_id='RT_TEST_S1',
            current_node='TEST_11',
            answer_value='high',
        )
        self.assertIsNone(row.next_node)

    def test_branch_condition_with_end_destination_saves_null_next_node(self):
        """Submitting a branch condition with next_node='' (END) stores next_node=None."""
        r = self.client.post(
            '/tools/sections/RT_TEST_S1/routing/add-condition/',
            {'node_id': 'TEST_3', 'answer_value': 'Yes_End', 'next_node': ''},
        )
        self.assertEqual(r.status_code, 302)
        row = Routing.objects.get(
            section__section_id='RT_TEST_S1',
            current_node='TEST_3',
            answer_value='Yes_End',
        )
        self.assertIsNone(row.next_node)

    def test_insert_after_branching_anchor_creates_new_routing_row(self):
        """Regression: inserting after a branching node (multiple Routing rows sharing one
        current_node, all with non-null answer_value) must create the new node's routing row.

        Previously the view silently no-oped because it looked only for an unconditional
        (answer_value=None) anchor row, found none, and redirected without writing anything.
        The fix (_next_order_value) computes a midpoint float order from the anchor's first
        row — no existing rows are modified.
        """
        regime = Regime.objects.get(regime_id='TEST_SIMPLE')
        section = Section.objects.create(
            section_id='RT_BRANCH_AFTER_S1',
            section_name='Insert After Branching Node Test',
            section_type=0,
            regime=regime,
        )
        # TEST_3 is a branching anchor: Yes → END, No → END (no unconditional row)
        SectionMember.objects.create(section=section, node_id='TEST_3', node_type='Q', added_order=10)
        SectionMember.objects.create(section=section, node_id='TEST_7', node_type='Q', added_order=20)
        Routing.objects.create(section=section, current_node='TEST_3', answer_value='Yes', next_node=None, order_in_section=10)
        Routing.objects.create(section=section, current_node='TEST_3', answer_value='No',  next_node=None, order_in_section=20)

        r = self.client.post(
            '/tools/sections/RT_BRANCH_AFTER_S1/routing/insert/',
            {
                'position':            'after',
                'anchor_node':         'TEST_3',
                'anchor_answer_value': '',
                'node_type':           'question',
                'node_id':             'TEST_7',
                'branching':           'no',
                'single_dest':         '',
            },
        )
        self.assertEqual(r.status_code, 302)

        # New node's routing row must exist — the old bug silently no-oped here
        new_row = Routing.objects.filter(section=section, current_node='TEST_7').first()
        self.assertIsNotNone(new_row, "No routing row was created for the inserted node TEST_7")
        # Anchor rows must be untouched (insert never modifies existing rows)
        anchor_rows = Routing.objects.filter(section=section, current_node='TEST_3')
        self.assertEqual(anchor_rows.count(), 2)
        for row in anchor_rows:
            self.assertIsNone(row.next_node, f"Anchor branch '{row.answer_value}' was unexpectedly modified")

    def test_repeated_inserts_produce_midpoint_sequence(self):
        """Repeated inserts into the same gap produce midpoint float values:
        existing 20/30 gap → insert gives 25.0 → next insert gives 27.5 → next 28.75."""
        from .views_admin_tools import _next_order_value

        regime = Regime.objects.get(regime_id='TEST_SIMPLE')
        section = Section.objects.create(
            section_id='RT_MIDPOINT_S1',
            section_name='Midpoint Float Test',
            section_type=0,
            regime=regime,
        )
        r_a = Routing.objects.create(section=section, current_node='TEST_4', answer_value=None, next_node='TEST_5', order_in_section=20.0)
        r_b = Routing.objects.create(section=section, current_node='TEST_5', answer_value=None, next_node=None,     order_in_section=30.0)

        # First insert after TEST_4 → midpoint(20, 30) = 25.0
        v1 = _next_order_value(section, anchor_node='TEST_4', position='after')
        self.assertEqual(v1, 25.0)
        r_c = Routing.objects.create(section=section, current_node='TEST_6', answer_value=None, next_node=None, order_in_section=v1)

        # Second insert after TEST_4 → midpoint(20, 25) = 22.5
        v2 = _next_order_value(section, anchor_node='TEST_4', position='after')
        self.assertEqual(v2, 22.5)
        r_d = Routing.objects.create(section=section, current_node='TEST_7', answer_value=None, next_node=None, order_in_section=v2)

        # Third insert after TEST_4 → midpoint(20, 22.5) = 21.25
        v3 = _next_order_value(section, anchor_node='TEST_4', position='after')
        self.assertEqual(v3, 21.25)

    def test_insert_above_first_row_produces_half_order(self):
        """Insert-above the first node uses position='first', which returns
        rows[0].order_in_section / 2 — placing the new row before the current entry."""
        from .views_admin_tools import _next_order_value

        regime = Regime.objects.get(regime_id='TEST_SIMPLE')
        section = Section.objects.create(
            section_id='RT_FIRST_S1',
            section_name='Insert First Test',
            section_type=0,
            regime=regime,
        )
        Routing.objects.create(section=section, current_node='TEST_4', answer_value=None, next_node=None, order_in_section=10.0)

        v = _next_order_value(section, position='first')
        self.assertEqual(v, 5.0)  # 10.0 / 2

    def test_bracket_shortcut_prefills_node_id_in_insert_form(self):
        """GET tools_routing_insert with ?prefill_node=X passes prefill_node to the
        template context, allowing JS to pre-select the question dropdown."""
        r = self.client.get(
            '/tools/sections/RT_TEST_S1/routing/insert/?prefill_node=TEST_11'
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['prefill_node'], 'TEST_11')
        # The node ID must appear in the rendered HTML (inside the JS prefill block)
        self.assertContains(r, 'TEST_11')

    def test_bracket_link_inserts_after_anchor_not_at_front(self):
        """Bracket link carries position=after&anchor_node=A so the new node lands
        after A, not at the front of the list.

        Setup: section with A(order=10) → [B] dangling.
        Bracket link for B: position=after, anchor_node=A, prefill_node=B.
        After submitting B → END, B's row should have order_in_section > A's (10),
        not less than or equal to it.
        """
        regime = Regime.objects.get(regime_id='TEST_SIMPLE')
        section = Section.objects.create(
            section_id='RT_BRACKET_ANCHOR_S1',
            section_name='Bracket Anchor Test',
            section_type=0,
            regime=regime,
        )
        # TEST_3 (A) → TEST_7 (B, dangling)
        SectionMember.objects.create(section=section, node_id='TEST_3', node_type='Q', added_order=10)
        SectionMember.objects.create(section=section, node_id='TEST_7', node_type='Q', added_order=20)
        Routing.objects.create(section=section, current_node='TEST_3', answer_value=None,
                               next_node='TEST_7', order_in_section=10.0)

        a_order = Routing.objects.get(section=section, current_node='TEST_3').order_in_section

        r = self.client.post(
            '/tools/sections/RT_BRACKET_ANCHOR_S1/routing/insert/?position=after&anchor_node=TEST_3&prefill_node=TEST_7',
            {
                'position':            'after',
                'anchor_node':         'TEST_3',
                'anchor_answer_value': '',
                'node_type':           'question',
                'node_id':             'TEST_7',
                'branching':           'no',
                'single_dest':         '',
            },
        )
        self.assertEqual(r.status_code, 302)

        b_row = Routing.objects.filter(section=section, current_node='TEST_7').first()
        self.assertIsNotNone(b_row, "TEST_7 routing row was not created")
        self.assertGreater(
            b_row.order_in_section, a_order,
            f"TEST_7 order ({b_row.order_in_section}) should be > TEST_3 order ({a_order})",
        )

    def test_convergence_node_header_renders_without_brackets(self):
        """A convergence node (is_convergence=True) must render its own row header
        as plain text — never [NODE_ID]. Brackets belong only on dangling destination
        references in condition lines, not on a node's own header.

        convergence_nodes requires two *different* current_nodes pointing at the same
        destination. Setup:
          TEST_3: Yes → TEST_11, No → TEST_7   (TEST_3 points at TEST_7)
          TEST_11: None → TEST_7               (TEST_11 also points at TEST_7)
          TEST_7: None → None
        TEST_7 is referenced from both TEST_3 and TEST_11 → is_convergence=True.
        """
        regime = Regime.objects.get(regime_id='TEST_SIMPLE')
        section = Section.objects.create(
            section_id='RT_CONVERGENCE_HDR_S1',
            section_name='Convergence Header Test',
            section_type=0,
            regime=regime,
        )
        Routing.objects.create(section=section, current_node='TEST_3',  answer_value='Yes', next_node='TEST_11', order_in_section=10)
        Routing.objects.create(section=section, current_node='TEST_3',  answer_value='No',  next_node='TEST_7',  order_in_section=20)
        Routing.objects.create(section=section, current_node='TEST_11', answer_value=None,  next_node='TEST_7',  order_in_section=30)
        Routing.objects.create(section=section, current_node='TEST_7',  answer_value=None,  next_node=None,      order_in_section=40)

        r = self.client.get('/tools/sections/RT_CONVERGENCE_HDR_S1/edit/')
        self.assertEqual(r.status_code, 200)

        # Confirm TEST_7 is flagged as convergence in the tree context
        tree = r.context['tree']
        test7_node = next((n for n in tree if n['type'] == 'question' and n['node_id'] == 'TEST_7'), None)
        self.assertIsNotNone(test7_node)
        self.assertTrue(test7_node['is_convergence'], "TEST_7 should be a convergence node")

        # The rendered page must NOT contain a bracketed header for TEST_7
        content = r.content.decode()
        self.assertNotIn('[TEST_7]', content)


class TestRoutedTableSection(TestCase):
    """
    Tests for section_type=2 (Table with routing).

    Uses TEST_3 (radio Yes/No) as the entry question.
    Yes branch → TEST_11 (number) → END.
    No  branch → END.
    display_question_ids='TEST_3' so TEST_11 is an "extra" detail question.

    The new flow: add-routed/ initialises the row session and redirects to
    add-routed/<node_id>/; that URL handles GET/POST for each node.
    """

    @classmethod
    def setUpTestData(cls):
        r_simple = Regime.objects.get(regime_id='TEST_SIMPLE')

        cls.section = Section.objects.create(
            section_id='RT2_TEST_S1',
            section_name='Routed Table Test',
            section_type=2,
            regime=r_simple,
            display_question_ids='TEST_3',
        )
        # TEST_3: Yes → TEST_11
        Routing.objects.create(
            section=cls.section,
            current_node='TEST_3',
            answer_value='Yes',
            next_node='TEST_11',
            order_in_section=10,
        )
        # TEST_3: No → END
        Routing.objects.create(
            section=cls.section,
            current_node='TEST_3',
            answer_value='No',
            next_node=None,
            order_in_section=20,
        )
        # TEST_11: unconditional → END
        Routing.objects.create(
            section=cls.section,
            current_node='TEST_11',
            answer_value=None,
            next_node=None,
            order_in_section=30,
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='carla', password='testpass123')

    def _set_session_case(self):
        """Prime the session with a case_id so views can resolve the case."""
        from .models import Case
        carla = User.objects.get(username='carla')
        r_simple = Regime.objects.get(regime_id='TEST_SIMPLE')
        case, _ = Case.objects.get_or_create(
            user=carla, regime=r_simple,
            defaults={'case_id': '00000000-0000-0000-0000-000000000002', 'status': 'draft'},
        )
        session = self.client.session
        session['case_id']  = case.case_id
        session['user_id']  = carla.pk
        session['actor_id'] = carla.pk
        session['regime_id'] = r_simple.regime_id
        session.save()
        return case

    def _do_add_journey(self, answers):
        """Run a complete add-routed row journey.

        answers: list of (question_id, post_data) pairs.
        Follows the init redirect then POSTs each step.
        Returns the final redirect response.
        """
        # Initialise: GET add-routed/ redirects to first question node
        r = self.client.get('/section/RT2_TEST_S1/table/add-routed/')
        self.assertIn('/add-routed/', r['Location'])
        for qid, data in answers:
            r = self.client.post(f'/section/RT2_TEST_S1/table/add-routed/{qid}/', data)
            self.assertEqual(r.status_code, 302)
        return r

    def test_landing_uses_routed_add_url(self):
        """Table landing for section_type=2 uses the add-routed URL."""
        self._set_session_case()
        r = self.client.get('/section/RT2_TEST_S1/table/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '/table/add-routed/')

    def test_routed_add_redirects_to_first_question(self):
        """GET /table/add-routed/ initialises session and redirects to TEST_3."""
        self._set_session_case()
        r = self.client.get('/section/RT2_TEST_S1/table/add-routed/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('TEST_3', r['Location'])

    def test_routed_question_get_shows_question(self):
        """GET /table/add-routed/TEST_3/ renders the question form."""
        self._set_session_case()
        self.client.get('/section/RT2_TEST_S1/table/add-routed/')  # init
        r = self.client.get('/section/RT2_TEST_S1/table/add-routed/TEST_3/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'TEST_3')

    def test_routed_add_no_branch_saves_row_immediately(self):
        """POST 'No' to TEST_3 hits END → row saved to AnswerTable."""
        case = self._set_session_case()
        carla = User.objects.get(username='carla')
        self._do_add_journey([('TEST_3', {'TEST_3': 'No'})])
        at = AnswerTable.objects.get(user=carla, case=case, section=self.section)
        self.assertEqual(len(at.answer), 1)
        self.assertEqual(at.answer[0].get('TEST_3'), 'No')

    def test_routed_add_yes_branch_advances_to_next_question(self):
        """POST 'Yes' to TEST_3 redirects to TEST_11."""
        self._set_session_case()
        self.client.get('/section/RT2_TEST_S1/table/add-routed/')  # init
        r = self.client.post('/section/RT2_TEST_S1/table/add-routed/TEST_3/', {'TEST_3': 'Yes'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('TEST_11', r['Location'])

    def test_routed_add_complete_journey_saves_full_row(self):
        """Yes → TEST_11 value → END saves a two-field row to AnswerTable."""
        case = self._set_session_case()
        carla = User.objects.get(username='carla')
        self._do_add_journey([
            ('TEST_3',  {'TEST_3': 'Yes'}),
            ('TEST_11', {'TEST_11': '9999'}),
        ])
        at = AnswerTable.objects.get(user=carla, case=case, section=self.section)
        self.assertEqual(len(at.answer), 1)
        self.assertEqual(at.answer[0].get('TEST_3'), 'Yes')
        self.assertEqual(at.answer[0].get('TEST_11'), '9999')

    def test_row_detail_shows_extra_field(self):
        """Row detail page shows TEST_11 (not in display_question_ids) as extra detail."""
        self._set_session_case()
        self._do_add_journey([
            ('TEST_3',  {'TEST_3': 'Yes'}),
            ('TEST_11', {'TEST_11': '5678'}),
        ])
        r = self.client.get('/section/RT2_TEST_S1/table/row-detail/0/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '5678')


class TestConditionQuestionId(TestCase):
    """
    Tests for condition_question_id on Routing.

    Verifies that when condition_question_id is set on a routing row, the
    engine uses that question's stored answer rather than the current node's
    own answer. Also covers the null/regression path, consistency checker,
    and admin round-trip.
    """

    @classmethod
    def setUpTestData(cls):
        r_simple = Regime.objects.get(regime_id='TEST_SIMPLE')

        # ── Section A: question node conditioned on an earlier question ──────────
        # Route: TEST_3 (radio) → TEST_11 (number) → TEST_7 or END
        # TEST_11's routing rows both have condition_question_id='TEST_3':
        #   if TEST_3=Yes → TEST_7;  fallback → END
        cls.q_section = Section.objects.create(
            section_id='CQ_TEST_S1',
            section_name='Condition Q Test',
            section_type=0,
            regime=r_simple,
        )
        Routing.objects.create(
            section=cls.q_section, current_node='TEST_3',
            answer_value=None, next_node='TEST_11', order_in_section=10,
        )
        Routing.objects.create(
            section=cls.q_section, current_node='TEST_11',
            condition_question_id='TEST_3',
            answer_value='Yes', next_node='TEST_7', order_in_section=20,
        )
        Routing.objects.create(
            section=cls.q_section, current_node='TEST_11',
            condition_question_id='TEST_3',
            answer_value=None, next_node=None, order_in_section=30,
        )
        Routing.objects.create(
            section=cls.q_section, current_node='TEST_7',
            answer_value=None, next_node=None, order_in_section=40,
        )

        # ── Section B: set node conditioned on a member question ─────────────────
        # Set CQ_TEST_SET: members TEST_22 (text) + TEST_3 (radio Yes/No)
        # Routing for the set node uses condition_question_id='TEST_3':
        #   Yes → TEST_11;  fallback → END
        cls.cq_set = QuestionSet.objects.create(
            set_id='CQ_TEST_SET', set_title='Condition Set',
        )
        QuestionSetMember.objects.create(
            question_set=cls.cq_set, question_id='TEST_22', display_order=1,
        )
        QuestionSetMember.objects.create(
            question_set=cls.cq_set, question_id='TEST_3', display_order=2,
        )
        cls.set_section = Section.objects.create(
            section_id='CQ_TEST_S2',
            section_name='Condition Set Test',
            section_type=0,
            regime=r_simple,
        )
        Routing.objects.create(
            section=cls.set_section, current_node='CQ_TEST_SET',
            condition_question_id='TEST_3',
            answer_value='Yes', next_node='TEST_11', order_in_section=10,
        )
        Routing.objects.create(
            section=cls.set_section, current_node='CQ_TEST_SET',
            condition_question_id='TEST_3',
            answer_value=None, next_node=None, order_in_section=20,
        )
        Routing.objects.create(
            section=cls.set_section, current_node='TEST_11',
            answer_value=None, next_node=None, order_in_section=30,
        )

        # ── Section C: for consistency checker test ───────────────────────────────
        cls.bogus_section = Section.objects.create(
            section_id='CQ_TEST_S3',
            section_name='Bogus Condition',
            section_type=0,
            regime=r_simple,
        )
        Routing.objects.create(
            section=cls.bogus_section, current_node='TEST_3',
            condition_question_id='BOGUS_Q999',
            answer_value='Yes', next_node=None, order_in_section=10,
        )

        # ── Section D: for admin round-trip test ──────────────────────────────────
        cls.admin_section = Section.objects.create(
            section_id='CQ_TEST_S4',
            section_name='Admin Round-trip',
            section_type=0,
            regime=r_simple,
        )
        SectionMember.objects.create(section=cls.admin_section, node_id='TEST_3', node_type='Q', added_order=10)

    def setUp(self):
        self.client = Client()
        self.client.login(username='carla', password='testpass123')

    # ── Test 1: Null condition_question_id (regression) ──────────────────────────

    def test_null_condition_question_id_routes_by_own_answer(self):
        """Standard routing (condition_question_id=None) still uses the current
        node's own answer after the field was added."""
        self.client.get('/section/CQ_TEST_S1/start/', follow=True)
        # TEST_3 row has condition_question_id=None → uses TEST_3's answer
        # answer_value=None (unconditional) → next_node=TEST_11
        r = self.client.post('/section/CQ_TEST_S1/question/TEST_3/', {'answer': 'No'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/question/TEST_11/', r['Location'])

    # ── Test 2: Set node with condition_question_id ───────────────────────────────

    def test_set_node_condition_question_id_yes_routes_to_next(self):
        """Set page: TEST_3=Yes → routing uses TEST_3's answer, routes to TEST_11."""
        self.client.get('/section/CQ_TEST_S2/start/', follow=True)
        r = self.client.post('/section/CQ_TEST_S2/set/CQ_TEST_SET/', {
            'TEST_22': 'Alice',
            'TEST_3':  'Yes',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('/question/TEST_11/', r['Location'])

    def test_set_node_condition_question_id_fallback_routes_to_end(self):
        """Set page: TEST_3=No → no specific match → unconditional row → END → review."""
        self.client.get('/section/CQ_TEST_S2/start/', follow=True)
        r = self.client.post('/section/CQ_TEST_S2/set/CQ_TEST_SET/', {
            'TEST_22': 'Alice',
            'TEST_3':  'No',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('/review/', r['Location'])

    # ── Test 3: Non-set node conditioned on earlier question ─────────────────────

    def test_question_node_condition_question_id_ignores_own_answer(self):
        """TEST_11 routing uses TEST_3's stored answer, not TEST_11's own value.
        TEST_3=Yes was answered first, so TEST_11 → TEST_7 regardless of TEST_11's value."""
        self.client.get('/section/CQ_TEST_S1/start/', follow=True)
        self.client.post('/section/CQ_TEST_S1/question/TEST_3/', {'answer': 'Yes'})
        # Submit any number for TEST_11 — the routing should use TEST_3=Yes
        r = self.client.post('/section/CQ_TEST_S1/question/TEST_11/', {'answer': '99'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/question/TEST_7/', r['Location'])

    # ── Test 4: Consistency checker ───────────────────────────────────────────────

    def test_consistency_checker_flags_unknown_condition_question_id(self):
        """validate_section_routing returns invalid when condition_question_id is unknown."""
        from .views_admin_tools import validate_section_routing
        result = validate_section_routing(self.bogus_section)
        self.assertFalse(result['valid'])
        self.assertTrue(
            any('BOGUS_Q999' in issue for issue in result['issues']),
            f'Expected BOGUS_Q999 in issues: {result["issues"]}',
        )

    # ── Test 5: Admin round-trip ──────────────────────────────────────────────────

    def test_admin_routing_insert_saves_condition_question_id(self):
        """Inserting a routing node via admin tool with condition_question_id stores it."""
        admin = Client()
        admin.login(username='super_admin', password='password123')
        admin.post(
            '/tools/sections/CQ_TEST_S4/routing/insert/',
            {
                'position':              'first',
                'anchor_node':           '',
                'anchor_answer_value':   '',
                'node_type':             'question',
                'node_id':               'TEST_3',
                'branching':             'no',
                'condition_question_id': 'TEST_11',
                'single_dest':           '',
            },
        )
        row = Routing.objects.filter(
            section__section_id='CQ_TEST_S4', current_node='TEST_3',
        ).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.condition_question_id, 'TEST_11')


class TestConditionalTableSection(TestCase):
    """
    Full tests for the section_type=2 Conditional Table Section implementation.

    Section layout:
        TEST_3 (radio Yes/No)
            Yes → TEST_11 (number) → END
            No  → END
        display_question_ids = 'TEST_3'
        TEST_11 is an "extra" (non-display) field.

    Covers: add journey, change journey, back-navigation, multiple rows,
    landing page action links, detail URL conditional display, and
    tools_section_edit shows routing editor for section_type=2.
    """

    @classmethod
    def setUpTestData(cls):
        from .models import Case
        r_simple = Regime.objects.get(regime_id='TEST_SIMPLE')

        cls.section = Section.objects.create(
            section_id='CTS_TEST_S1',
            section_name='Conditional Table Test',
            section_type=2,
            regime=r_simple,
            display_question_ids='TEST_3',
        )
        Routing.objects.create(
            section=cls.section, current_node='TEST_3',
            answer_value='Yes', next_node='TEST_11', order_in_section=10,
        )
        Routing.objects.create(
            section=cls.section, current_node='TEST_3',
            answer_value='No', next_node=None, order_in_section=20,
        )
        Routing.objects.create(
            section=cls.section, current_node='TEST_11',
            answer_value=None, next_node=None, order_in_section=30,
        )

        # Section for radio_inline rendering test (D20)
        cls.ri_question = Question.objects.create(
            question_id='CTS_RI_Q1',
            question_text='What is the ownership type?',
            question_type='radio_inline',
            answer_type='text',
            options='Sole;Joint',
        )
        cls.ri_section = Section.objects.create(
            section_id='CTS_TEST_S2',
            section_name='Radio Inline Table Test',
            section_type=2,
            regime=r_simple,
            display_question_ids='CTS_RI_Q1',
        )
        Routing.objects.create(
            section=cls.ri_section, current_node='CTS_RI_Q1',
            answer_value=None, next_node=None, order_in_section=10,
        )

        # Section for routing-error (silent-END) test: routing only covers 'Yes',
        # so submitting 'No' has no match — should surface error, not commit row.
        cls.re_question = Question.objects.create(
            question_id='CTS_RE_Q1',
            question_text='Is this a test?',
            question_type='radio',
            answer_type='text',
            options='Yes;No',
        )
        cls.re_section = Section.objects.create(
            section_id='CTS_TEST_S3',
            section_name='Routing Error Test',
            section_type=2,
            regime=r_simple,
            display_question_ids='CTS_RE_Q1',
        )
        Routing.objects.create(
            section=cls.re_section, current_node='CTS_RE_Q1',
            answer_value='Yes', next_node=None, order_in_section=10,
        )

        carla = User.objects.get(username='carla')
        cls.case, _ = Case.objects.get_or_create(
            user=carla, regime=r_simple,
            defaults={
                'case_id': '00000000-0000-0000-0000-000000000099',
                'status': 'draft',
            },
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='carla', password='testpass123')
        carla = User.objects.get(username='carla')
        # Clear any rows from previous tests
        AnswerTable.objects.filter(
            user=carla, section=self.section,
        ).delete()
        session = self.client.session
        session['case_id']  = self.case.case_id
        session['user_id']  = carla.pk
        session['actor_id'] = carla.pk
        session['regime_id'] = 'TEST_SIMPLE'
        session.save()

    def _add_yes_row(self, val='9999'):
        """Add a Yes-branch row (TEST_3=Yes, TEST_11=val)."""
        self.client.get('/section/CTS_TEST_S1/table/add-routed/')
        self.client.post('/section/CTS_TEST_S1/table/add-routed/TEST_3/', {'TEST_3': 'Yes'})
        self.client.post('/section/CTS_TEST_S1/table/add-routed/TEST_11/', {'TEST_11': val})

    def _add_no_row(self):
        """Add a No-branch row (TEST_3=No → END)."""
        self.client.get('/section/CTS_TEST_S1/table/add-routed/')
        self.client.post('/section/CTS_TEST_S1/table/add-routed/TEST_3/', {'TEST_3': 'No'})

    # ── Test 1: init redirect ─────────────────────────────────────────────────

    def test_add_routed_init_redirects_to_first_node(self):
        """GET /table/add-routed/ redirects to /table/add-routed/TEST_3/."""
        r = self.client.get('/section/CTS_TEST_S1/table/add-routed/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('TEST_3', r['Location'])

    # ── Test 2: No-branch saves row ───────────────────────────────────────────

    def test_no_branch_saves_row_and_redirects_to_table(self):
        """No-branch journey: TEST_3=No → END → row saved → redirect to table."""
        carla = User.objects.get(username='carla')
        self._add_no_row()
        at = AnswerTable.objects.get(user=carla, case=self.case, section=self.section)
        self.assertEqual(len(at.answer), 1)
        self.assertEqual(at.answer[0]['TEST_3'], 'No')

    # ── Test 3: Yes-branch full journey ──────────────────────────────────────

    def test_yes_branch_saves_two_field_row(self):
        """Yes-branch journey: TEST_3=Yes, TEST_11=1234 → row with both fields."""
        carla = User.objects.get(username='carla')
        self._add_yes_row('1234')
        at = AnswerTable.objects.get(user=carla, case=self.case, section=self.section)
        self.assertEqual(len(at.answer), 1)
        row = at.answer[0]
        self.assertEqual(row['TEST_3'], 'Yes')
        self.assertEqual(row['TEST_11'], '1234')

    # ── Test 4: Multiple rows accumulate ─────────────────────────────────────

    def test_multiple_rows_accumulate(self):
        """Adding two rows saves both to AnswerTable.answer."""
        carla = User.objects.get(username='carla')
        self._add_yes_row('100')
        self._add_no_row()
        at = AnswerTable.objects.get(user=carla, case=self.case, section=self.section)
        self.assertEqual(len(at.answer), 2)

    # ── Test 5: Change journey replaces existing row ──────────────────────────

    def test_change_journey_replaces_row(self):
        """change/<row_index>/ pre-populates session; submitting updates the row."""
        carla = User.objects.get(username='carla')
        self._add_yes_row('OLD')

        # Change row 0: update TEST_11 to 'NEW'
        r = self.client.get('/section/CTS_TEST_S1/table/change/0/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('TEST_3', r['Location'])

        # Re-answer TEST_3=Yes (pre-filled journey)
        self.client.post('/section/CTS_TEST_S1/table/add-routed/TEST_3/', {'TEST_3': 'Yes'})
        self.client.post('/section/CTS_TEST_S1/table/add-routed/TEST_11/', {'TEST_11': 'NEW'})

        at = AnswerTable.objects.get(user=carla, case=self.case, section=self.section)
        self.assertEqual(len(at.answer), 1)
        self.assertEqual(at.answer[0]['TEST_11'], 'NEW')

    # ── Test 6: Change pre-populates question value ───────────────────────────

    def test_change_prefills_current_answer(self):
        """GET the question page in a change journey shows the saved answer pre-filled."""
        self._add_yes_row('PRE')
        # Init change journey
        r = self.client.get('/section/CTS_TEST_S1/table/change/0/')
        self.assertEqual(r.status_code, 302)
        # GET the question page
        r2 = self.client.get('/section/CTS_TEST_S1/table/add-routed/TEST_3/')
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, 'value="Yes"')  # pre-filled radio

    # ── Test 7: Back navigation renders earlier node ──────────────────────────

    def test_back_navigation_shows_earlier_node(self):
        """GET with ?back=1 on TEST_3 after advancing to TEST_11 renders TEST_3."""
        self.client.get('/section/CTS_TEST_S1/table/add-routed/')
        self.client.post('/section/CTS_TEST_S1/table/add-routed/TEST_3/', {'TEST_3': 'Yes'})
        # Now go back to TEST_3
        r = self.client.get('/section/CTS_TEST_S1/table/add-routed/TEST_3/?back=1')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'TEST_3')

    # ── Test 8: Landing page shows Change link for routed rows ───────────────

    def test_landing_page_shows_change_link(self):
        """Table landing for section_type=2 includes a Change link for each row."""
        self._add_yes_row()
        r = self.client.get('/section/CTS_TEST_S1/table/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '/table/change/0/')

    # ── Test 9: detail_url only present when row has extra fields ─────────────

    def test_detail_url_present_for_yes_row(self):
        """Yes row has TEST_11 (extra field) → detail_url shown on landing."""
        self._add_yes_row()
        r = self.client.get('/section/CTS_TEST_S1/table/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '/table/row-detail/0/')

    def test_detail_url_absent_for_no_row(self):
        """No row has only TEST_3 (display field) → no Other details link."""
        self._add_no_row()
        r = self.client.get('/section/CTS_TEST_S1/table/')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'row-detail')

    # ── Test 10: tools_section_edit shows routing editor for section_type=2 ──

    def test_tools_section_edit_shows_routing_editor_for_type2(self):
        """tools_section_edit does NOT show the 'no routing' inset for type=2."""
        admin = Client()
        admin.login(username='super_admin', password='password123')
        r = admin.get(f'/tools/sections/{self.section.section_id}/edit/')
        self.assertEqual(r.status_code, 200)
        # The inset text is only for type=1
        self.assertNotContains(r, 'Flat table sections do not use routing')
        # The routing editor heading should be present
        self.assertContains(r, 'Routing')

    def test_radio_inline_question_renders_inline_class_not_text_input(self):
        """
        D20: table_routed_question.html must render govuk-radios--inline for
        radio_inline questions, not fall through to the plain <input type="text">
        fallback.
        """
        r = self.client.get(
            f'/section/{self.ri_section.section_id}/table/add-routed/CTS_RI_Q1/'
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'govuk-radios--inline')
        self.assertContains(r, 'type="radio"')
        self.assertNotContains(r, 'type="text"')

    def test_routing_mismatch_surfaces_error_and_does_not_commit_row(self):
        """
        Part B silent-END fix: when an answer has no matching routing row
        (data error), section_table_routed_question must re-render the page
        with a routing_error message and must NOT commit a row to AnswerTable.
        Submitting 'No' to CTS_RE_Q1 has no routing coverage (only 'Yes' is
        defined), so it must be caught and surfaced rather than silently
        treated as END and committed.
        """
        carla = User.objects.get(username='carla')
        # Initiate row journey
        self.client.get(f'/section/{self.re_section.section_id}/table/add-routed/')
        # Submit answer with no routing coverage
        r = self.client.post(
            f'/section/{self.re_section.section_id}/table/add-routed/CTS_RE_Q1/',
            {'CTS_RE_Q1': 'No'},
        )
        # Must re-render (200), not redirect (302)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'There is a configuration problem')
        # Must not have committed a row
        self.assertEqual(
            AnswerTable.objects.filter(user=carla, section=self.re_section).count(),
            0,
            'No AnswerTable row should be committed on a routing mismatch',
        )


# ─────────────────────────────────────────────────────────────────────────────
# Table-journey identity scoping
# ─────────────────────────────────────────────────────────────────────────────

class TestTableJourneyIdentityScoping(TestCase):
    """
    Table-journey DB writes (AnswerTable, AnswerTableHistory, SectionStatus)
    must use case.user (the subject / deceased), not request.user (the actor).

    Also verifies that section_start does NOT overwrite the session user_id
    when a case_id is already in the session.
    """

    @classmethod
    def setUpTestData(cls):
        from .models import Case, Permission, AnswerTableHistory
        r_simple = Regime.objects.get(regime_id='TEST_SIMPLE')

        cls.regime = r_simple

        cls.section = Section.objects.create(
            section_id='TJ_SCOPE_S1',
            section_name='Table Journey Scope Test',
            section_type=1,                   # flat table section
            regime=r_simple,
            display_question_ids='TEST_3',
        )

        cls.actor = User.objects.get(username='carla')

        # Synthetic deceased subject — case.user ≠ actor
        cls.subject = User(
            username='ihtsubject_tablejrny_scope',
            first_name='Table', last_name='Subject',
            is_active=False,
        )
        cls.subject.set_unusable_password()
        cls.subject.save()

        # Verified case: case.user = subject, actor = carla
        cls.case = Case.objects.create(
            case_id='tj-scope-test-case-001',
            user=cls.subject,
            regime=r_simple,
            status='draft',
            reference='TJ-SCOPE-001',
        )

        Permission.objects.create(
            actor=cls.actor,
            user=cls.subject,
            regime=r_simple,
            case=cls.case,
            section=None,
            can_delegate=False,
        )

    def setUp(self):
        from .models import AnswerTable, AnswerTableHistory
        self.client = Client()
        self.client.login(username='carla', password='testpass123')
        # Clear any rows from previous test runs
        AnswerTable.objects.filter(case=self.case, section=self.section).delete()
        AnswerTableHistory.objects.filter(case=self.case, section=self.section).delete()
        SectionStatus.objects.filter(regime=self.regime, section=self.section).delete()

    def _seed_session(self, extra=None):
        """Seed PSS with a verified-case context (subject ≠ actor)."""
        session = self.client.session
        pss = session.setdefault('pss', {})
        pss['user_id']   = self.subject.pk    # subject
        pss['actor_id']  = self.actor.pk      # actor (logged-in)
        pss['case_id']   = str(self.case.case_id)
        pss['regime_id'] = self.regime.regime_id
        session['case_id'] = str(self.case.case_id)
        if extra:
            pss.update(extra)
        session.save()

    def test_table_section_commit_writes_under_case_user(self):
        """
        POST to section_confirm_table writes AnswerTable, AnswerTableHistory,
        and SectionStatus all under case.user (subject), not request.user (actor).
        """
        from .models import Case, AnswerTableHistory

        # Pre-create an AnswerTable row under the subject so confirm_table has
        # something to snapshot.
        AnswerTable.objects.create(
            user=self.subject,
            actor=self.actor,
            regime=self.regime,
            case=self.case,
            section=self.section,
            answer=[{'TEST_3': 'Yes'}],
        )

        self._seed_session()
        r = self.client.post(f'/section/{self.section.section_id}/confirm-table/')
        self.assertEqual(r.status_code, 302)

        # AnswerTableHistory must be owned by subject
        subject_hist = AnswerTableHistory.objects.filter(
            user=self.subject, case=self.case, section=self.section,
        ).count()
        actor_hist = AnswerTableHistory.objects.filter(
            user=self.actor, case=self.case, section=self.section,
        ).count()
        self.assertEqual(subject_hist, 1,
            'AnswerTableHistory must be owned by case.user (subject)')
        self.assertEqual(actor_hist, 0,
            'No AnswerTableHistory must be written under the actor')

        # SectionStatus must be owned by subject
        subject_ss = SectionStatus.objects.filter(
            user=self.subject, regime=self.regime, section=self.section,
            status='complete',
        ).count()
        actor_ss = SectionStatus.objects.filter(
            user=self.actor, regime=self.regime, section=self.section,
        ).count()
        self.assertEqual(subject_ss, 1,
            'SectionStatus must be owned by case.user (subject)')
        self.assertEqual(actor_ss, 0,
            'No SectionStatus must be written under the actor')

    def test_section_start_does_not_overwrite_user_id(self):
        """
        GET section/<id>/start/ must NOT clobber pss['user_id'] when a case_id
        is already in the session.  It should remain as subject.pk, not actor.pk.

        Uses a section_type=0 section because section_start immediately redirects
        type-1/2 sections to section_table without touching the session.
        """
        # Need a type=0 section so section_start runs its full logic
        section_q, _ = Section.objects.get_or_create(
            section_id='TJ_SCOPE_S0',
            defaults={
                'section_name': 'Table Journey Scope Start Test',
                'section_type': 0,
                'regime': self.regime,
                'display_order': 99,
            },
        )
        Routing.objects.get_or_create(
            section=section_q, current_node='TEST_3',
            answer_value=None, next_node=None,
            defaults={'order_in_section': 1},
        )

        self._seed_session()
        self.client.get(f'/section/{section_q.section_id}/start/')

        # Read the session after the request
        session = self.client.session
        pss = session.get('pss', {})
        self.assertEqual(
            pss.get('user_id'), self.subject.pk,
            'pss[user_id] must remain as subject.pk after section_start re-entry',
        )


class TestResetSectionProgress(TestCase):
    """
    reset_section_progress(user, regime) deletes all SectionStatus rows for
    the given user/regime and leaves rows for other users/regimes untouched.
    """

    @classmethod
    def setUpTestData(cls):
        cls.regime_a = Regime.objects.get(regime_id='TEST_SIMPLE')
        cls.regime_b = Regime.objects.get(regime_id='TEST_SECTIONS')
        cls.user_a = User.objects.get(username='alice')
        cls.user_b = User.objects.get(username='carla')
        cls.section = Section.objects.filter(regime=cls.regime_a).first()

    def setUp(self):
        SectionStatus.objects.filter(
            user__in=[self.user_a, self.user_b],
            regime__in=[self.regime_a, self.regime_b],
        ).delete()

    def tearDown(self):
        SectionStatus.objects.filter(
            user__in=[self.user_a, self.user_b],
            regime__in=[self.regime_a, self.regime_b],
        ).delete()

    def test_deletes_matching_rows_and_leaves_others_untouched(self):
        from core.interfaces import reset_section_progress

        # Rows for user_a / regime_a — should be deleted
        SectionStatus.objects.create(
            user=self.user_a, regime=self.regime_a, section=self.section,
            status='complete',
        )
        # Rows for user_b / regime_a — different user, must survive
        SectionStatus.objects.create(
            user=self.user_b, regime=self.regime_a, section=self.section,
            status='in_progress',
        )
        # Rows for user_a / regime_b — different regime, must survive
        section_b = Section.objects.filter(regime=self.regime_b).first()
        if section_b:
            SectionStatus.objects.create(
                user=self.user_a, regime=self.regime_b, section=section_b,
                status='not_started',
            )

        reset_section_progress(self.user_a, self.regime_a)

        self.assertEqual(
            SectionStatus.objects.filter(user=self.user_a, regime=self.regime_a).count(),
            0,
            'reset_section_progress must delete all rows for user_a/regime_a',
        )
        self.assertEqual(
            SectionStatus.objects.filter(user=self.user_b, regime=self.regime_a).count(),
            1,
            'rows for a different user must be untouched',
        )
        if section_b:
            self.assertEqual(
                SectionStatus.objects.filter(user=self.user_a, regime=self.regime_b).count(),
                1,
                'rows for a different regime must be untouched',
            )


class TestCompletionReturnToTopLevel(TestCase):
    """
    regime_top_level must write return_url to itself so that section_done
    redirects back to the top-level list, not to regime_home_url.

    This covers the fix that added `top_level_url` and wrote it via
    update_session in core/views_layer1.py::regime_top_level.
    """

    @classmethod
    def setUpTestData(cls):
        from .models import Case
        from core.models import Permission

        cls.regime = Regime.objects.create(
            regime_id='TEST_TOPLEVEL',
            regime_name='Top Level Test Regime',
            dept_id='TEST',
            display_order=99,
        )
        cls.section_a = Section.objects.create(
            section_id='TL_S_A',
            section_name='Top Level Section A',
            section_type=0,
            regime=cls.regime,
            display_order=1,
        )
        cls.section_b = Section.objects.create(
            section_id='TL_S_B',
            section_name='Top Level Section B',
            section_type=0,
            regime=cls.regime,
            display_order=2,
        )
        cls.carla = User.objects.get(username='carla')
        Permission.objects.create(
            actor=cls.carla,
            user=cls.carla,
            regime=cls.regime,
            section=None,
            case=None,
            can_delegate=False,
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='carla', password='testpass123')
        self.top_url = reverse('core:regime_top_level',
                               kwargs={'regime_id': 'TEST_TOPLEVEL'})
        self.regime_home = '/fake-regime-home/'

        session = self.client.session
        pss = session.setdefault('pss', {})
        pss['user_id']        = self.carla.pk
        pss['actor_id']       = self.carla.pk
        pss['regime_id']      = 'TEST_TOPLEVEL'
        pss['regime_home_url'] = self.regime_home
        pss['top_level_items'] = [
            {'type': 'section', 'id': 'TL_S_A'},
            {'type': 'section', 'id': 'TL_S_B'},
        ]
        session.save()

    def tearDown(self):
        SectionStatus.objects.filter(regime=self.regime).delete()

    def test_regime_top_level_sets_return_url_to_itself(self):
        """GET regime_top_level must write pss['return_url'] = its own URL."""
        response = self.client.get(self.top_url)
        self.assertEqual(response.status_code, 200)
        pss = self.client.session.get('pss', {})
        self.assertEqual(
            pss.get('return_url'), self.top_url,
            'regime_top_level must write return_url to its own URL',
        )

    def test_section_done_returns_to_top_level_not_regime_home(self):
        """
        After visiting the top-level list (which sets return_url), completing
        a section should redirect back to the list, not to regime_home_url.
        """
        # Visit top-level list to set return_url in session
        self.client.get(self.top_url)

        # Make section B in-progress so the regime-complete rollup doesn't fire
        SectionStatus.objects.create(
            user=self.carla,
            regime=self.regime,
            section=self.section_b,
            status='in_progress',
        )

        response = self.client.get(
            reverse('core:section_done', kwargs={'section_id': 'TL_S_A'}),
        )
        self.assertRedirects(response, self.top_url, fetch_redirect_response=False,
                             msg_prefix='section_done must return to top-level list URL')
        self.assertNotEqual(response['Location'], self.regime_home,
                            'section_done must NOT redirect to regime_home_url')
