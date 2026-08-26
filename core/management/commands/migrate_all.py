from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = (
        "Run migrate against every configured database alias, so router-skipped "
        "migrations (e.g. anything touching PlatformRouter-routed models) aren't "
        "silently left unapplied on the alias that actually needs them."
    )

    def add_arguments(self, parser):
        parser.add_argument('app_label', nargs='?')
        parser.add_argument('migration_name', nargs='?')

    def handle(self, *args, **options):
        for alias in settings.DATABASES:
            self.stdout.write(self.style.MIGRATE_HEADING(f"--- migrating '{alias}' ---"))
            call_command(
                'migrate',
                *([options['app_label']] if options['app_label'] else []),
                *([options['migration_name']] if options['migration_name'] else []),
                database=alias,
            )
