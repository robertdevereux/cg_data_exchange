"""
dept_dwp smoke tests — DWP shell app navigation and view coverage.

Both /demo/ and /dwp/ are always registered in urlpatterns, so these tests
hit /dwp/... directly without needing to toggle ACTIVE_DEPT.

Covers:
  A) DWP entry point — authenticated access to /dwp/
  B) choose_user — citizen skips person-picker; agent sees it
  C) dept_home — renders for a permitted user even when no DWP-specific regimes exist
  D) regime_home generic view — unknown regime_id → 404; valid regime → 200
  E) select_schedule and select_section — return 200 for valid regimes; handle
     absent session keys gracefully
"""

from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase

from core.models import Permission, User


# ─────────────────────────────────────────────────────────────────────────────
# A. DWP entry point
# ─────────────────────────────────────────────────────────────────────────────

class TestDWPEntryPoint(TestCase):
    """Authenticated users can reach /dwp/; unauthenticated are redirected to login."""

    def setUp(self):
        self.client = Client()
        self.client.login(username='dwp_alice', password='testpass123')

    def test_dwp_root_accessible_when_logged_in(self):
        """/dwp/ returns 200 (following any redirects) for a logged-in user."""
        r = self.client.get('/dwp/', follow=True)
        self.assertEqual(r.status_code, 200)

    def test_unauthenticated_redirected_to_login(self):
        r = Client().get('/dwp/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])


# ─────────────────────────────────────────────────────────────────────────────
# B. choose_user
# ─────────────────────────────────────────────────────────────────────────────

class TestDWPChooseUser(TestCase):
    """
    choose_user: a citizen with no agent clients skips the person-picker and
    redirects straight to dept_home; an agent with clients sees the picker.
    """

    def test_citizen_skips_picker_and_redirects(self):
        """
        dwp_alice has only a self-permission — no one else acts on her behalf
        in the other direction.  When she visits /dwp/, choose_user finds no
        clients for her actor role and redirects to dept_home (/dwp/regimes/).
        """
        c = Client()
        c.login(username='dwp_alice', password='testpass123')
        r = c.get('/dwp/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/dwp/regimes/', r['Location'])

    def test_agent_sees_person_picker(self):
        """
        dwp_agent1 has a blanket permission acting for dwp_alice.
        When they visit /dwp/, choose_user finds dwp_alice as a client
        and renders the person-picker form (status 200).
        """
        c = Client()
        c.login(username='dwp_agent1', password='testpass123')
        r = c.get('/dwp/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Alice')  # dwp_alice's first name in the picker

    def test_agent_post_invalid_user_id_redirects_back(self):
        """POSTing an invalid user_id to choose_user bounces back to the picker."""
        c = Client()
        c.login(username='dwp_agent1', password='testpass123')
        r = c.post('/dwp/', {'user_id': '9999999'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/dwp/', r['Location'])

    def test_agent_post_valid_user_id_proceeds_to_dept_home(self):
        """POSTing a valid user_id redirects to dept_home (multi-regime user)."""
        dwp_alice = User.objects.get(username='dwp_alice')
        c = Client()
        c.login(username='dwp_agent1', password='testpass123')
        r = c.post('/dwp/', {'user_id': str(dwp_alice.pk)})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/dwp/regimes/', r['Location'])


# ─────────────────────────────────────────────────────────────────────────────
# C. dept_home
# ─────────────────────────────────────────────────────────────────────────────

class TestDWPDeptHome(TestCase):
    """
    dept_home renders for a permitted user.  No DWP-specific regimes exist in
    the fixture yet (they are created via the wizard in Part 5), so we verify
    the page returns 200 without a 500 error.  dwp_alice has a blanket
    permission, so she sees whatever non-PLATFORM regimes are in the DB.
    """

    def setUp(self):
        self.client = Client()
        self.client.login(username='dwp_alice', password='testpass123')

    def test_dept_home_renders(self):
        r = self.client.get('/dwp/regimes/')
        self.assertEqual(r.status_code, 200)

    def test_dept_home_requires_login(self):
        r = Client().get('/dwp/regimes/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])

    def test_dept_home_no_perms_renders_gracefully(self):
        """
        A user with no Permission records sees an empty regime list, not a 500.
        Permission enforcement is at the section level; dept_home is open to
        all authenticated users.
        """
        u, _ = User.objects.get_or_create(
            username='dwp_noperms',
            defaults={
                'password':   make_password('testpass123'),
                'first_name': 'No',
                'last_name':  'Perms',
            }
        )
        Permission.objects.filter(actor=u).delete()
        c = Client()
        c.login(username='dwp_noperms', password='testpass123')
        r = c.get('/dwp/regimes/')
        self.assertEqual(r.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# D. regime_home generic view
# ─────────────────────────────────────────────────────────────────────────────

class TestDWPRegimeHome(TestCase):
    """
    regime_generic_home: an unknown regime_id returns 404; a known non-PLATFORM
    regime renders the generic home page.  Full DWP-specific regime testing is
    deferred to Part 5 once the BSP regime is created via the wizard.
    """

    def setUp(self):
        self.client = Client()
        self.client.login(username='dwp_alice', password='testpass123')

    def test_unknown_regime_id_returns_404(self):
        r = self.client.get('/dwp/regime/NONEXISTENT_REGIME_XYZ/')
        self.assertEqual(r.status_code, 404)

    def test_known_regime_renders(self):
        """
        DEMO_SIMPLE exists in the fixture and is not excluded (dept_id='DEMO').
        dwp_alice (blanket perms) can reach its generic home page.
        """
        r = self.client.get('/dwp/regime/DEMO_SIMPLE/')
        self.assertEqual(r.status_code, 200)

    def test_regime_home_requires_login(self):
        r = Client().get('/dwp/regime/DEMO_SIMPLE/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])


# ─────────────────────────────────────────────────────────────────────────────
# E. select_schedule and select_section
# ─────────────────────────────────────────────────────────────────────────────

class TestDWPNavViews(TestCase):
    """
    select_schedule and select_section return 200 for valid regimes.
    Session keys may be absent (first visit without going via choose_user);
    _resolve_user falls back to the actor in that case, so no crash.
    """

    def setUp(self):
        self.client = Client()
        self.client.login(username='dwp_alice', password='testpass123')

    def test_select_schedule_renders_for_schedules_regime(self):
        """DEMO_SCHEDULES has two schedules; schedule list (now at core) should render 200."""
        r = self.client.get('/regime/DEMO_SCHEDULES/schedules/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Personal Information')
        self.assertContains(r, 'Financial Information')

    def test_select_schedule_unknown_regime_returns_404(self):
        r = self.client.get('/regime/NONEXISTENT/schedules/')
        self.assertEqual(r.status_code, 404)

    def test_select_section_renders_for_sections_regime(self):
        """DEMO_SECTIONS has three direct sections; select_section should render 200."""
        r = self.client.get('/dwp/regime/DEMO_SECTIONS/sections/')
        self.assertEqual(r.status_code, 200)
        for section_id in ('SECTIONS_S1', 'SECTIONS_S2', 'SECTIONS_S3'):
            self.assertContains(r, section_id,
                                msg_prefix=f'{section_id} missing from section list')

    def test_select_section_in_schedule_renders(self):
        """Filtered section list for a specific schedule renders 200 (now at core)."""
        r = self.client.get(
            '/regime/DEMO_SCHEDULES/schedule/SCHED_PERSONAL/sections/'
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'SCHED_S1')
        self.assertContains(r, 'SCHED_S2')

    def test_select_section_without_prior_session_does_not_crash(self):
        """
        Accessing select_section without visiting choose_user first (no session
        state) must not raise an exception — _resolve_user falls back to actor.
        """
        fresh = Client()
        fresh.login(username='dwp_alice', password='testpass123')
        r = fresh.get('/dwp/regime/DEMO_SECTIONS/sections/')
        self.assertEqual(r.status_code, 200)
