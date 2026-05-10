"""
Custom test runner that loads test fixtures exactly once per suite.

Django's default behaviour calls setUpTestData once per TestCase class,
which means load_test_data (a slow Neon network call) runs N times where
N is the number of test classes.  This runner loads the data a single time
after the test database is created, outside any class-level savepoint.

Django's TestCase still wraps every individual test method in a transaction
that rolls back on completion, so per-test mutations (e.g. deleting alice's
answers in setUp) are fully undone before the next test runs.
"""

from django.core.management import call_command
from django.test.runner import DiscoverRunner


class LoadOnceTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        result = super().setup_databases(**kwargs)
        call_command('load_test_data', verbosity=0)
        return result
