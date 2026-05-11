"""
End-to-end tests for Layer 2 (section processing) and Layer 1 (navigation
and permission expansion).

Covers the full citizen journey for alice on SIMPLE_S1 — Yes branch and
a backtrack that changes Q_nino_yn from Yes to No, pruning Q_nino_value
from the confirmed answer set.
"""

from django.test import Client, TestCase

from .models import Answer, AnswerHistory, SectionStatus, User
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

        # ── Post S1 set page (title, first name, last name) ───────────────────
        r = self.client.post('/section/SIMPLE_S1/set/S1/', {
            'Q21': 'Ms', 'Q22': 'Alice', 'Q23': 'Johnson',
        })
        self.assertEqual(r.status_code, 302, 'POST S1 returned unexpected status')

        # ── Post all Yes-branch questions in routing order ────────────────────
        posts = [
            ('Q2',  {'answer': '1975-06-15'}),
            ('Q3',  {'answer': 'Yes'}),
            ('Q4',  {'answer': 'QQ123456C'}),
            ('Q7',  {'answer': 'I am a retired teacher living in Bristol.'}),
            ('Q8',  {'answer': 'Yes'}),
            ('Q10', {'answer': ['Red', 'Blue']}),
            ('Q11', {'answer': '2'}),
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

        # Yes branch: S1 members (Q21/Q22/Q23) + Q2/Q3/Q4/Q7/Q8/Q10/Q11 = 10
        self.assertEqual(
            Answer.objects.filter(user=alice, section__section_id='SIMPLE_S1').count(),
            10,
            'Expected 10 answers: S1 members Q21/Q22/Q23 + Q2/Q3/Q4/Q7/Q8/Q10/Q11',
        )
        self.assertFalse(
            Answer.objects.filter(user=alice, question_id='Q9').exists(),
            'Q9 (simple_why) should not be present when Q8=Yes',
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
        # ── Start ─────────────────────────────────────────────────────────────
        self.client.get('/section/SIMPLE_S1/start/')

        # ── Walk Yes branch as far as Q_nino_value ────────────────────────────
        self.client.post('/section/SIMPLE_S1/question/Q_full_name/', {'answer': 'Alice Johnson'})
        self.client.post('/section/SIMPLE_S1/question/Q_dob/',       {'answer': '1975-06-15'})
        self.client.post('/section/SIMPLE_S1/question/Q_nino_yn/',   {'answer': 'Yes'})
        self.client.post('/section/SIMPLE_S1/question/Q_nino_value/', {'answer': 'QQ123456C'})

        # ── Backtrack: GET Q_nino_yn truncates asked_ids to that point ────────
        self.client.get('/section/SIMPLE_S1/question/Q_nino_yn/')

        # ── Change to No — routing jumps straight to Q_simple_about ──────────
        self.client.post('/section/SIMPLE_S1/question/Q_nino_yn/', {'answer': 'No'})

        # ── Complete the No branch ────────────────────────────────────────────
        self.client.post('/section/SIMPLE_S1/question/Q_simple_about/', {'answer': 'I changed my mind about NINO.'})
        self.client.post('/section/SIMPLE_S1/question/Q_simple_agree/', {'answer': 'Yes'})
        self.client.post('/section/SIMPLE_S1/question/Q_simple_colour/', {'answer': ['Green']})
        self.client.post('/section/SIMPLE_S1/question/Q_simple_count/', {'answer': '1'})

        # ── Confirm ───────────────────────────────────────────────────────────
        r = self.client.post('/section/SIMPLE_S1/confirm/')
        self.assertEqual(r.status_code, 302)

        # ── Assertion: Q_nino_value must have been pruned ─────────────────────
        alice = User.objects.get(username='alice')
        self.assertFalse(
            Answer.objects.filter(user=alice, question_id='Q_nino_value').exists(),
            'Q_nino_value must be pruned when backtrack changes Q_nino_yn to No',
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
        # Step 2: follow into the Financial Information schedule section list
        r2 = self.client.get(
            '/demo/regime/DEMO_SCHEDULES/schedule/SCHED_FINANCES/sections/',
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
