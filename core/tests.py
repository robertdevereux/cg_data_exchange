"""
End-to-end tests for Layer 2: Section Processing Engine.

Covers the full citizen journey for alice on SIMPLE_S1 — Yes branch and
a backtrack that changes Q_nino_yn from Yes to No, pruning Q_nino_value
from the confirmed answer set.
"""

from django.core.management import call_command
from django.test import Client, TestCase

from .models import Answer, AnswerHistory, SectionStatus, User


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
