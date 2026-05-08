"""
End-to-end tests for Layer 2 (section processing) and Layer 1 (navigation
and permission expansion).

Covers the full citizen journey for alice on SIMPLE_S1 — Yes branch and
a backtrack that changes Q_nino_yn from Yes to No, pruning Q_nino_value
from the confirmed answer set.
"""

from django.core.management import call_command
from django.test import Client, TestCase

from .models import Answer, AnswerHistory, SectionStatus, User
from .permissions import get_permitted_sections


class TestSimpleS1YesBranch(TestCase):
    """Walk alice through SIMPLE_S1 via the Yes branch and confirm."""

    @classmethod
    def setUpTestData(cls):
        call_command('load_test_data', verbosity=0)

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')

    def test_yes_branch_complete(self):
        # ── Start ─────────────────────────────────────────────────────────────
        r = self.client.get('/section/SIMPLE_S1/start/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/question/Q_full_name/', r['Location'])

        # ── Post all Yes-branch questions in routing order ────────────────────
        posts = [
            ('Q_full_name',     {'answer': 'Alice Johnson'}),
            ('Q_dob',           {'answer': '1975-06-15'}),
            ('Q_nino_yn',       {'answer': 'Yes'}),
            ('Q_nino_value',    {'answer': 'QQ123456C'}),
            ('Q_simple_about',  {'answer': 'I am a retired teacher living in Bristol.'}),
            ('Q_simple_agree',  {'answer': 'Yes'}),
            ('Q_simple_colour', {'answer': ['Red', 'Blue']}),
            ('Q_simple_count',  {'answer': '2'}),
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

        self.assertEqual(
            Answer.objects.filter(user=alice, section__section_id='SIMPLE_S1').count(),
            8,
            'Expected exactly 8 answers (full Yes-branch path)',
        )
        self.assertFalse(
            Answer.objects.filter(user=alice, question_id='Q_simple_why').exists(),
            'Q_simple_why should not be present when Q_simple_agree=Yes',
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

    @classmethod
    def setUpTestData(cls):
        call_command('load_test_data', verbosity=0)

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

    @classmethod
    def setUpTestData(cls):
        call_command('load_test_data', verbosity=0)

    def test_alice_acting_for_herself_sees_all_sections(self):
        """alice has regime-level grants for all three regimes → all 8 sections."""
        alice = User.objects.get(username='alice')
        sections = get_permitted_sections(alice, alice)
        self.assertEqual(
            sections.count(), 8,
            'alice should have access to all 8 sections across 3 regimes',
        )

    def test_solicitor1_acting_for_alice_sees_only_sched_s3(self):
        """solicitor1 has a section-level grant for SCHED_S3 acting for alice."""
        solicitor1 = User.objects.get(username='solicitor1')
        alice      = User.objects.get(username='alice')
        sections   = get_permitted_sections(solicitor1, alice)
        self.assertEqual(sections.count(), 1)
        self.assertEqual(sections.first().section_id, 'SCHED_S3')

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

    @classmethod
    def setUpTestData(cls):
        call_command('load_test_data', verbosity=0)

    def setUp(self):
        self.client = Client()
        self.client.login(username='solicitor1', password='testpass123')

    def test_choose_user_shows_alice(self):
        """solicitor1 has alice as an actable user — choose_user renders with alice."""
        alice = User.objects.get(username='alice')
        r = self.client.get('/choose-user/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, str(alice.pk))

    def test_solicitor1_reaches_sched_s3_table(self):
        """
        Full redirect chain: choose_user → select_regime (auto) → regime_start
        (auto) → SCHED_S3 table.
        """
        alice = User.objects.get(username='alice')
        r = self.client.post('/choose-user/', {'user_id': alice.pk}, follow=True)
        self.assertEqual(r.status_code, 200)
        final_url = r.redirect_chain[-1][0] if r.redirect_chain else ''
        self.assertIn('SCHED_S3', final_url)

    def test_solicitor1_cannot_access_sched_s1(self):
        """SCHED_S1 must not appear in solicitor1's permitted sections for alice."""
        solicitor1 = User.objects.get(username='solicitor1')
        alice      = User.objects.get(username='alice')
        section_ids = list(
            get_permitted_sections(solicitor1, alice).values_list('section_id', flat=True)
        )
        self.assertNotIn('SCHED_S1', section_ids)
        self.assertIn('SCHED_S3', section_ids)
