"""
Custom test runner that loads test fixtures exactly once per suite.

Django's default behaviour calls setUpTestData once per TestCase class,
which means load_test_data (a slow Neon network call) runs N times where
N is the number of test classes.  This runner loads the data a single time
after the test database is created, outside any class-level savepoint.

Django's TestCase still wraps every individual test method in a transaction
that rolls back on completion, so per-test mutations (e.g. deleting alice's
answers in setUp) are fully undone before the next test runs.

Migration ordering note
-----------------------
The PlatformRouter routes Question/QuestionSet/QuestionSetMember to the
'platform' DB alias only.  Because core_routing has a FK to core_question,
and other 'default' models reference core_question, we temporarily bypass
the router restriction during test DB setup so that all tables are created
by the single 'migrate --database=default' call.
"""

from django.core.management import call_command
from django.test import TransactionTestCase
from django.test.runner import DiscoverRunner


class LoadOnceTestRunner(DiscoverRunner):
    def run_tests(self, test_labels, **kwargs):
        # Allow queries to 'platform' in all test cases.  The 'platform' DB
        # is configured with TEST: {MIRROR: 'default'} so no separate test DB
        # is created — both aliases hit the same physical test database.
        TransactionTestCase.databases = {'default', 'platform'}
        return super().run_tests(test_labels, **kwargs)

    def setup_databases(self, **kwargs):
        # During test DB creation, temporarily allow platform models to
        # migrate on 'default'.  This ensures core_question (and related
        # tables) are created before core_routing's FK constraint runs.
        from config.routers import PlatformRouter
        original_allow_migrate = PlatformRouter.allow_migrate

        def permissive_allow_migrate(self, db, app_label, model_name=None, **hints):
            # Allow everything on default during test setup
            if db == 'default':
                return True
            # Block everything on platform (avoid duplicate table creation)
            return False

        PlatformRouter.allow_migrate = permissive_allow_migrate

        try:
            result = super().setup_databases(**kwargs)
        finally:
            # Restore the original router after DB setup
            PlatformRouter.allow_migrate = original_allow_migrate

        # The 'platform' connection may have been opened (and cached) while
        # pointing at the production DB before setup_databases updated its
        # settings_dict['NAME'] to test_neondb.  Force-close it so the next
        # query reconnects to test_neondb.
        from django.db import connections
        connections['platform'].close()

        call_command('load_test_data', verbosity=0)
        return result
