"""
dept_demo smoke tests — end-to-end navigation flows for all three patterns.

Covers:
  A) Login redirect → /demo/
  B) Dept home: multi-regime user sees card list; single-regime user auto-redirects
  C) DEMO_SIMPLE (Pattern A): start → questions → confirm → returns to regime home
  D) DEMO_SECTIONS (Pattern B): regime home → section task list → section →
     confirm → returns to section task list (not regime home)
  E) DEMO_SCHEDULES (Pattern C): regime home → schedule list → section list →
     section → confirm → returns to section list (not schedule list)
  F) Pre-population: shared questions from alice's SIMPLE_S1 appear as suggestions
     in SECTIONS_S1
  G) section_done fallback: no return_url → /regime/<id>/ (core URL)
  H) solicitor1 via dept_demo: regime_home router handles unknown-to-dept regime
     gracefully (falls back to dept home)
"""

from django.core.management import call_command
from django.test import Client, TestCase

from core.models import SectionStatus, User


# ─────────────────────────────────────────────────────────────────────────────
# Shared test fixture
# ─────────────────────────────────────────────────────────────────────────────

class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('load_test_data', verbosity=0)


# ─────────────────────────────────────────────────────────────────────────────
# A. Login redirect
# ─────────────────────────────────────────────────────────────────────────────

class TestLoginRedirect(_Base):
    """POST to login should redirect to /demo/ (LOGIN_REDIRECT_URL)."""

    def test_login_lands_at_demo(self):
        r = self.client.post(
            '/accounts/login/',
            {'username': 'alice', 'password': 'testpass123'},
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        final = r.redirect_chain[-1][0] if r.redirect_chain else ''
        self.assertIn('/demo/', final,
                      f'Login should redirect to /demo/, got chain: {r.redirect_chain}')


# ─────────────────────────────────────────────────────────────────────────────
# B. Department home
# ─────────────────────────────────────────────────────────────────────────────

class TestDeptHome(_Base):
    """Multi-regime user sees cards; single-regime user is auto-redirected."""

    def setUp(self):
        self.alice  = Client()
        self.alice.login(username='alice', password='testpass123')
        self.carla  = Client()
        self.carla.login(username='carla', password='testpass123')

    def test_alice_sees_three_regime_cards(self):
        """
        Alice has 3 regimes. /demo/ → choose_user (auto-skip) → select_regime
        → redirect to /demo/regimes/ (dept_home). Cards for all three regimes
        must appear.
        """
        r = self.alice.get('/demo/', follow=True)
        self.assertEqual(r.status_code, 200)
        final = r.redirect_chain[-1][0] if r.redirect_chain else ''
        self.assertIn('/demo/regimes/', final,
                      f'Multi-regime user should land at /demo/regimes/, chain: {r.redirect_chain}')
        for regime_id in ('DEMO_SIMPLE', 'DEMO_SECTIONS', 'DEMO_SCHEDULES'):
            self.assertContains(r, regime_id,
                                msg_prefix=f'{regime_id} card missing from regime list')

    def test_carla_auto_redirected_to_only_regime(self):
        """Carla has only DEMO_SIMPLE — /demo/ auto-redirects to regime home."""
        r = self.carla.get('/demo/', follow=True)
        self.assertEqual(r.status_code, 200)
        # Should end up at the specific regime home page
        final = r.redirect_chain[-1][0] if r.redirect_chain else ''
        self.assertIn('demo-simple', final,
                      f'Carla should be redirected to demo-simple, chain: {r.redirect_chain}')

    def test_unauthenticated_redirected_to_login(self):
        r = self.client.get('/demo/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])


# ─────────────────────────────────────────────────────────────────────────────
# C. DEMO_SIMPLE — Pattern A (single section, direct jump)
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternA_DemoSimple(_Base):
    """
    Full DEMO_SIMPLE journey for carla (fresh user, no prior answers).
    Pattern A: regime home → Start → section_start → questions → confirm
             → section_done → return_url (regime home)
    """

    def setUp(self):
        self.client = Client()
        self.client.login(username='carla', password='testpass123')

    # ── C1. Regime home router ────────────────────────────────────────────────

    def test_regime_home_router_redirects_to_demo_simple(self):
        """Generic /demo/regime/DEMO_SIMPLE/ router → /demo/regime/demo-simple/."""
        r = self.client.get('/demo/regime/DEMO_SIMPLE/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('demo-simple', r['Location'])

    # ── C2. Regime home page ─────────────────────────────────────────────────

    def test_regime_simple_home_renders(self):
        r = self.client.get('/demo/regime/demo-simple/')
        self.assertEqual(r.status_code, 200)

    def test_regime_simple_home_has_start_button(self):
        r = self.client.get('/demo/regime/demo-simple/')
        self.assertContains(r, 'Start')

    def test_regime_simple_home_entry_url_is_section_start(self):
        """Pattern A entry URL must point directly at the section, not a task list."""
        r = self.client.get('/demo/regime/demo-simple/')
        # The entry_url in context should be /section/SIMPLE_S1/start/
        self.assertContains(r, '/section/SIMPLE_S1/start/')

    # ── C3. Full question journey + redirect back to regime home ──────────────

    def test_full_simple_journey_returns_to_regime_home(self):
        """
        Carla starts DEMO_SIMPLE, answers all Yes-branch questions, confirms,
        and section_done must redirect to /demo/regime/demo-simple/ (not / or /regime/...).
        """
        # Visit regime home first so session gets return_url set
        self.client.get('/demo/regime/demo-simple/')

        # Start the section
        r = self.client.get('/section/SIMPLE_S1/start/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('Q_full_name', r['Location'])

        # Answer all Yes-branch questions
        for qid, data in [
            ('Q_full_name',     {'answer': 'Carla Garcia'}),
            ('Q_dob',           {'answer': '1985-03-22'}),
            ('Q_nino_yn',       {'answer': 'No'}),
            ('Q_simple_about',  {'answer': 'I am a software developer.'}),
            ('Q_simple_agree',  {'answer': 'Yes'}),
            ('Q_simple_colour', {'answer': ['Blue', 'Green']}),
            ('Q_simple_count',  {'answer': '2'}),
        ]:
            r = self.client.post(f'/section/SIMPLE_S1/question/{qid}/', data)
            self.assertEqual(r.status_code, 302, f'POST {qid} returned {r.status_code}')

        # Confirm
        r = self.client.post('/section/SIMPLE_S1/confirm/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/done/', r['Location'])

        # Follow the done redirect — must land at /demo/regime/demo-simple/
        r = self.client.get(r['Location'], follow=True)
        self.assertEqual(r.status_code, 200)
        final = r.redirect_chain[-1][0] if r.redirect_chain else r.wsgi_request.path
        self.assertIn('/demo/regime/demo-simple/', final,
                      f'section_done should return to regime home, got: {final}')

    def test_regime_home_shows_amend_after_completion(self):
        """After completing SIMPLE_S1, regime home button label changes to 'Amend'."""
        # Complete the section (quick path)
        self.client.get('/demo/regime/demo-simple/')
        self.client.get('/section/SIMPLE_S1/start/')
        for qid, data in [
            ('Q_full_name',     {'answer': 'Carla Garcia'}),
            ('Q_dob',           {'answer': '1985-03-22'}),
            ('Q_nino_yn',       {'answer': 'No'}),
            ('Q_simple_about',  {'answer': 'Quick test.'}),
            ('Q_simple_agree',  {'answer': 'Yes'}),
            ('Q_simple_colour', {'answer': ['Red']}),
            ('Q_simple_count',  {'answer': '1'}),
        ]:
            self.client.post(f'/section/SIMPLE_S1/question/{qid}/', data)
        self.client.post('/section/SIMPLE_S1/confirm/')

        # Re-visit regime home
        r = self.client.get('/demo/regime/demo-simple/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Amend',
                            msg_prefix='Button should say "Amend your answers" after completion')


# ─────────────────────────────────────────────────────────────────────────────
# D. DEMO_SECTIONS — Pattern B (section task list)
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternB_DemoSections(_Base):
    """
    DEMO_SECTIONS journey for bob (fresh for this regime).
    Pattern B: regime home → Start → section task list → section →
               confirm → section_done → section task list (not regime home)
    """

    def setUp(self):
        self.client = Client()
        self.client.login(username='bob', password='testpass123')

    def test_regime_home_router_redirects_to_demo_sections(self):
        r = self.client.get('/demo/regime/DEMO_SECTIONS/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('demo-sections', r['Location'])

    def test_regime_sections_home_renders(self):
        r = self.client.get('/demo/regime/demo-sections/')
        self.assertEqual(r.status_code, 200)

    def test_regime_sections_home_entry_url_is_task_list(self):
        """Pattern B entry URL must be the section task list (/demo/regime/.../sections/)."""
        r = self.client.get('/demo/regime/demo-sections/')
        self.assertContains(r, '/demo/regime/DEMO_SECTIONS/sections/',
                            msg_prefix='entry_url should point to section task list')

    def test_section_task_list_renders(self):
        r = self.client.get('/demo/regime/DEMO_SECTIONS/sections/')
        self.assertEqual(r.status_code, 200)

    def test_section_task_list_shows_all_sections(self):
        """All three DEMO_SECTIONS sections must appear in the task list."""
        # Visit regime home first to bootstrap statuses
        self.client.get('/demo/regime/demo-sections/')
        r = self.client.get('/demo/regime/DEMO_SECTIONS/sections/')
        self.assertEqual(r.status_code, 200)
        for section_id in ('SECTIONS_S1', 'SECTIONS_S2', 'SECTIONS_S3'):
            self.assertContains(r, section_id,
                                msg_prefix=f'{section_id} missing from task list')

    def test_section_done_returns_to_task_list_not_regime_home(self):
        """
        Critical: after confirming SECTIONS_S1, section_done must redirect
        to the section task list (/demo/regime/DEMO_SECTIONS/sections/),
        NOT to the regime home (/demo/regime/demo-sections/).
        """
        # Visit regime home → task list (sets return_url in session)
        self.client.get('/demo/regime/demo-sections/')
        self.client.get('/demo/regime/DEMO_SECTIONS/sections/')

        # Start and answer SECTIONS_S1
        self.client.get('/section/SECTIONS_S1/start/')
        for qid, data in [
            ('Q_full_name',        {'answer': 'Bob Smith'}),
            ('Q_dob',              {'answer': '1990-07-04'}),
            ('Q_nino_yn',          {'answer': 'No'}),
            ('Q_address_line1',    {'answer': '10 Downing Street'}),
            ('Q_address_postcode', {'answer': 'SW1A 2AA'}),
        ]:
            self.client.post(f'/section/SECTIONS_S1/question/{qid}/', data)

        r = self.client.post('/section/SECTIONS_S1/confirm/')
        self.assertEqual(r.status_code, 302)
        done_url = r['Location']

        # Follow section_done
        r = self.client.get(done_url, follow=True)
        self.assertEqual(r.status_code, 200)
        final = r.redirect_chain[-1][0] if r.redirect_chain else r.wsgi_request.path
        self.assertIn('/demo/regime/DEMO_SECTIONS/sections/', final,
                      f'section_done should return to task list, got: {final}')
        # Must NOT be the regime home
        self.assertNotIn('demo-sections', final,
                         'section_done must not return to regime home page')

    def test_additional_info_section_no_branch(self):
        """SECTIONS_S3 via the No branch (single question, no detail required)."""
        self.client.get('/demo/regime/demo-sections/')
        self.client.get('/demo/regime/DEMO_SECTIONS/sections/')
        self.client.get('/section/SECTIONS_S3/start/')
        r = self.client.post(
            '/section/SECTIONS_S3/question/Q_additional_yn/', {'answer': 'No'}
        )
        self.assertEqual(r.status_code, 302)
        # Should go to review (routing ends after Q_additional_yn=No)
        r = self.client.get('/section/SECTIONS_S3/review/')
        self.assertEqual(r.status_code, 200)
        r = self.client.post('/section/SECTIONS_S3/confirm/')
        self.assertEqual(r.status_code, 302)

        bob = User.objects.get(username='bob')
        self.assertEqual(
            SectionStatus.objects.get(
                user=bob, section__section_id='SECTIONS_S3'
            ).status,
            'complete',
        )


# ─────────────────────────────────────────────────────────────────────────────
# E. DEMO_SCHEDULES — Pattern C (schedule → section task list)
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternC_DemoSchedules(_Base):
    """
    DEMO_SCHEDULES journey for alice.
    Pattern C: regime home → Start → schedule list → section list →
               section → confirm → section_done → section list (not schedule list)
    """

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')

    def test_regime_home_router_redirects_to_demo_schedules(self):
        r = self.client.get('/demo/regime/DEMO_SCHEDULES/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('demo-schedules', r['Location'])

    def test_regime_schedules_home_renders(self):
        r = self.client.get('/demo/regime/demo-schedules/')
        self.assertEqual(r.status_code, 200)

    def test_regime_schedules_home_entry_url_is_schedule_list(self):
        """Pattern C entry URL must be the schedule list (/demo/regime/.../schedules/)."""
        r = self.client.get('/demo/regime/demo-schedules/')
        self.assertContains(r, '/demo/regime/DEMO_SCHEDULES/schedules/',
                            msg_prefix='entry_url should point to schedule list')

    def test_schedule_list_renders_with_both_schedules(self):
        self.client.get('/demo/regime/demo-schedules/')
        r = self.client.get('/demo/regime/DEMO_SCHEDULES/schedules/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Personal Information')
        self.assertContains(r, 'Financial Information')

    def test_section_list_for_personal_schedule_renders(self):
        self.client.get('/demo/regime/demo-schedules/')
        r = self.client.get(
            '/demo/regime/DEMO_SCHEDULES/schedule/SCHED_PERSONAL/sections/'
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'SCHED_S1')
        self.assertContains(r, 'SCHED_S2')

    def test_section_done_returns_to_section_list_not_schedule_list(self):
        """
        Critical: after confirming SCHED_S1, section_done must redirect
        to /demo/regime/DEMO_SCHEDULES/schedule/SCHED_PERSONAL/sections/
        NOT to the schedule list.
        """
        # Set up navigation context (sets return_url to section list)
        self.client.get('/demo/regime/demo-schedules/')
        self.client.get('/demo/regime/DEMO_SCHEDULES/schedules/')
        self.client.get(
            '/demo/regime/DEMO_SCHEDULES/schedule/SCHED_PERSONAL/sections/'
        )

        # Answer SCHED_S1 (Identity: name, DOB, NINO branch)
        self.client.get('/section/SCHED_S1/start/')
        for qid, data in [
            ('Q_full_name',  {'answer': 'Alice Johnson'}),
            ('Q_dob',        {'answer': '1975-06-15'}),
            ('Q_nino_yn',    {'answer': 'Yes'}),
            ('Q_nino_value', {'answer': 'QQ123456C'}),
        ]:
            self.client.post(f'/section/SCHED_S1/question/{qid}/', data)

        r = self.client.post('/section/SCHED_S1/confirm/')
        self.assertEqual(r.status_code, 302)
        done_url = r['Location']

        # Follow section_done
        r = self.client.get(done_url, follow=True)
        self.assertEqual(r.status_code, 200)
        final = r.redirect_chain[-1][0] if r.redirect_chain else r.wsgi_request.path
        self.assertIn(
            '/demo/regime/DEMO_SCHEDULES/schedule/SCHED_PERSONAL/sections/',
            final,
            f'section_done should return to section list, got: {final}',
        )
        # Must NOT go to the schedule list level
        self.assertNotIn('/schedules/', final,
                         'section_done must not jump up to schedule list')

    def test_finances_schedule_section_list_renders(self):
        """Finances schedule shows SCHED_S3 (table) and SCHED_S4 (declaration)."""
        self.client.get('/demo/regime/demo-schedules/')
        r = self.client.get(
            '/demo/regime/DEMO_SCHEDULES/schedule/SCHED_FINANCES/sections/'
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'SCHED_S3')
        self.assertContains(r, 'SCHED_S4')


# ─────────────────────────────────────────────────────────────────────────────
# F. Pre-population (cross-regime suggestions)
# ─────────────────────────────────────────────────────────────────────────────

class TestPrePopulation(_Base):
    """
    Alice has completed SIMPLE_S1. When she starts SECTIONS_S1, shared
    questions (Q_full_name, Q_dob, Q_nino_yn) should appear as suggestions.
    """

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')

    def test_shared_question_suggestion_appears_in_sections_s1(self):
        """
        Arriving at Q_full_name in SECTIONS_S1, alice should see her SIMPLE_S1
        answer 'Alice Johnson' offered as a suggestion.
        """
        # Navigate to regime and task list to set session context
        self.client.get('/demo/regime/demo-sections/')
        self.client.get('/demo/regime/DEMO_SECTIONS/sections/')
        self.client.get('/section/SECTIONS_S1/start/')

        r = self.client.get('/section/SECTIONS_S1/question/Q_full_name/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(
            r, 'Alice Johnson',
            msg_prefix='Pre-population suggestion "Alice Johnson" missing from Q_full_name',
        )


# ─────────────────────────────────────────────────────────────────────────────
# G. section_done fallback (no return_url in session)
# ─────────────────────────────────────────────────────────────────────────────

class TestSectionDoneFallback(_Base):
    """
    When section_done is reached with no return_url in session, it should
    fall back to /regime/<regime_id>/ (the core Layer 1 URL, not /demo/).
    """

    def setUp(self):
        self.client = Client()
        # Login without visiting any dept_demo page — no return_url in session
        self.client.login(username='carla', password='testpass123')

    def test_no_return_url_falls_back_to_root(self):
        # Start section directly (bypassing dept_demo Layer 1 — no return_url in session)
        self.client.get('/section/SIMPLE_S1/start/')
        for qid, data in [
            ('Q_full_name',     {'answer': 'Carla Garcia'}),
            ('Q_dob',           {'answer': '1985-03-22'}),
            ('Q_nino_yn',       {'answer': 'No'}),
            ('Q_simple_about',  {'answer': 'Direct access test.'}),
            ('Q_simple_agree',  {'answer': 'Yes'}),
            ('Q_simple_colour', {'answer': ['Yellow']}),
            ('Q_simple_count',  {'answer': '1'}),
        ]:
            self.client.post(f'/section/SIMPLE_S1/question/{qid}/', data)

        r = self.client.post('/section/SIMPLE_S1/confirm/')
        done_url = r['Location']   # → /section/SIMPLE_S1/done/

        # section_done with no return_url falls back to /
        r = self.client.get(done_url)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], '/',
                         'Fallback with no return_url should redirect to /')


# ─────────────────────────────────────────────────────────────────────────────
# H. regime_home router — unknown regime falls back to dept home
# ─────────────────────────────────────────────────────────────────────────────

class TestRegimeHomeRouter(_Base):
    """regime_home router handles unmapped regime_id gracefully."""

    def setUp(self):
        self.client = Client()
        self.client.login(username='alice', password='testpass123')

    def test_unknown_regime_id_redirects_to_dept_home(self):
        r = self.client.get('/demo/regime/UNKNOWN_REGIME/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/demo/', r['Location'])

    def test_known_regimes_route_correctly(self):
        mapping = {
            'DEMO_SIMPLE':    'demo-simple',
            'DEMO_SECTIONS':  'demo-sections',
            'DEMO_SCHEDULES': 'demo-schedules',
        }
        for regime_id, slug in mapping.items():
            r = self.client.get(f'/demo/regime/{regime_id}/')
            self.assertEqual(r.status_code, 302,
                             f'/demo/regime/{regime_id}/ should redirect')
            self.assertIn(slug, r['Location'],
                          f'{regime_id} should route to {slug}')
