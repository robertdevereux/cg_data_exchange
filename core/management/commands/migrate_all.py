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
        # Run 'platform' before 'default'. Both aliases share one physical DB and
        # one django_migrations table. Whichever alias runs first marks migrations
        # as applied — so the alias that actually needs the operations (platform,
        # for Question/QuestionSet/QuestionSetMember migrations) must go first.
        # If 'platform' runs second, the migration is already recorded from the
        # 'default' run and its AddField operations are silently skipped.
        aliases = sorted(settings.DATABASES, key=lambda a: (0 if a == 'platform' else 1, a))
        for alias in aliases:
            self.stdout.write(self.style.MIGRATE_HEADING(f"--- migrating '{alias}' ---"))
            call_command(
                'migrate',
                *([options['app_label']] if options['app_label'] else []),
                *([options['migration_name']] if options['migration_name'] else []),
                database=alias,
            )
