"""
End-to-end tests for Layer 2 (section processing) and Layer 1 (navigation
and permission expansion).

Covers the full citizen journey for alice on SIMPLE_S1 — Yes branch and
a backtrack that changes Q_nino_yn from Yes to No, pruning Q_nino_value
from the confirmed answer set.
"""

import json

from django.test import Client, TestCase

from .models import Answer, AnswerHistory, Question, Regime, Routing, Section, SectionStatus, User
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
        # ── Start — first node is now the S1 set page ─────────────────────────
        r = self.client.get('/section/SIMPLE_S1/start/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/set/S1/', r['Location'])

        # ── Post S1 set page (first name, last name) ──────────────────────────
        r = self.client.post('/section/SIMPLE_S1/set/S1/', {
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
        self.client.post('/section/SIMPLE_S1/set/S1/', {
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

    def test_choose_user_shows_two_candidates(self):
        """
        solicitor1 can act for alice and bob (no self-permissions),
        so choose_user at /demo/ renders the choice page rather than auto-skipping.
        """
        r = self.client.get('/demo/')
        self.assertEqual(r.status_code, 200)

    def test_solicitor1_reaches_sched_s3_table(self):
        """
        Full redirect chain via dept_demo: /demo/ → choose_user (select alice)
        → dept_home (regime list). Following into SCHED_FINANCES shows SCHED_S3.
        """
        alice = User.objects.get(username='alice')
        # Step 1: select alice at the person-picker → lands on dept_home
        r = self.client.post('/demo/', {'user_id': alice.pk}, follow=True)
        self.assertEqual(r.status_code, 200)
        final_url = r.redirect_chain[-1][0] if r.redirect_chain else ''
        self.assertIn('/demo/regimes/', final_url)
        # Step 2: follow into the Financial Information schedule section list (core URL)
        r2 = self.client.get(
            '/regime/TEST_SCHEDULES/schedule/SCHED_FINANCES/sections/',
            follow=True,
        )
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, 'Accounts')     # SCHED_S3 section name
        self.assertContains(r2, 'Declaration')  # SCHED_S4 section name

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
    Routing: S1 → Q2 → Q3; Q3=Yes → Q4 → Q7; Q3=No → Q7; Q7 → Q8;
             Q8=Yes → Q10 → Q11 → END; Q8=No → Q9 → END
    S1 set: 'Your name' — Q22 (First name, text, required),
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
        """GET /section/{id}/set/S1/ renders question_set.html."""
        r = self.client.get(f'/section/{self.section_id}/set/S1/')
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'core/question_set.html')

    def test_set_page_get_shows_all_member_fields(self):
        """Set page shows both S1 member question labels."""
        r = self.client.get(f'/section/{self.section_id}/set/S1/')
        self.assertContains(r, 'First name')
        self.assertContains(r, 'Last name')

    def test_set_page_get_shows_set_title(self):
        """Set page heading is the set_title value ('Your name')."""
        r = self.client.get(f'/section/{self.section_id}/set/S1/')
        self.assertContains(r, 'Your name')

    # ── 2. POST — required field blank ────────────────────────────────────────

    def test_set_page_post_missing_required_field_rerenders(self):
        """POST with a required field blank re-renders the set page (200, not 302)."""
        r = self.client.post(f'/section/{self.section_id}/set/S1/', {
            'TEST_22': '',      # first name — required, left blank
            'TEST_23': 'Smith',
        })
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'core/question_set.html')

    def test_set_page_post_missing_required_field_shows_error_summary(self):
        """Error summary appears when a required field is blank."""
        r = self.client.post(f'/section/{self.section_id}/set/S1/', {
            'TEST_22': '',
            'TEST_23': 'Smith',
        })
        self.assertContains(r, 'govuk-error-summary')

    def test_set_page_post_missing_required_field_shows_field_error(self):
        """Per-field error class appears on the blank required field."""
        r = self.client.post(f'/section/{self.section_id}/set/S1/', {
            'TEST_22': '',
            'TEST_23': 'Smith',
        })
        self.assertContains(r, 'govuk-form-group--error')

    # ── 3. POST — all required fields filled advances (302) ──────────────────

    def test_set_page_post_all_required_filled_advances(self):
        """POST with all required fields non-empty redirects to the next node."""
        r = self.client.post(f'/section/{self.section_id}/set/S1/', {
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
        self.client.post(f'/section/{self.section_id}/set/S1/', {
            'TEST_22': 'Alice',
            'TEST_23': 'Jones',
        })
        # TEST_2 is the first Q-node after S1 in SIMPLE_S1 routing
        r = self.client.get(f'/section/{self.section_id}/question/TEST_2/')
        self.assertContains(r, f'/section/{self.section_id}/set/S1/')

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
        self.assertContains(r, f'/section/{self.section_id}/set/S1/')
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

        Routing: S1 → TEST_2 → TEST_3=Yes → TEST_4 → TEST_7 → TEST_8=Yes → TEST_10 → TEST_11 → END (review)
        """
        # S1 set page (first name / last name)
        self.client.post(f'/section/{self.section_id}/set/S1/', {
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
        self.client.post('/section/SIMPLE_S1/set/S1/', {
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

    def test_routing_tree_page_contains_end_option_label(self):
        """The next_node dropdown contains the END option label."""
        r = self.client.get('/tools/sections/RT_TEST_S1/routing/')
        self.assertContains(r, 'END (return to home page)')

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

    def test_routing_tree_embeds_question_data_json(self):
        """The routing tree page embeds ROUTING_QUESTION_DATA with correct types."""
        r = self.client.get('/tools/sections/RT_TEST_S1/routing/')
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        self.assertIn('ROUTING_QUESTION_DATA', content)
        # TEST_3 is radio, TEST_11 is number — both should appear
        self.assertIn('"radio"', content)
        self.assertIn('"number"', content)

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
        with next_node='' (END) saves next_node=None.
        This exercises the add-cond-form that is now shown for all question nodes."""
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
