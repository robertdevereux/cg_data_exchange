"""
Management command: reset_demo_estates
=======================================
Lists (and optionally deletes) User rows that are not part of the known
fixture set — i.e. the deceased-proxy records created by
promote_case_to_verified() during IHT demo sessions.

Default (no flags): list only — nothing is changed.
With --confirm:     delete those users; Django CASCADE removes every
                    dependent Case, Answer, AnswerHistory, AnswerTable,
                    AnswerTableHistory, SectionStatus, ScheduleStatus, and
                    Permission row in one atomic operation.

Usage:
    python manage.py reset_demo_estates            # list only
    python manage.py reset_demo_estates --confirm  # delete
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import (
    Answer,
    AnswerHistory,
    AnswerTable,
    AnswerTableHistory,
    Case,
    Permission,
    ScheduleStatus,
    SectionStatus,
)

User = get_user_model()

# Usernames that are part of the known fixture set and must never be deleted.
FIXTURE_USERNAMES = {
    'alice',
    'bob',
    'carla',
    'solicitor1',
    'super_admin',
    'admin',
}


class Command(BaseCommand):
    help = (
        'List (or with --confirm delete) deceased-proxy User rows created '
        'by promote_case_to_verified during IHT demo sessions.  '
        'Known fixture accounts (alice, bob, carla, solicitor1, super_admin, '
        'admin) are always excluded.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Delete the listed rows and all dependent data via CASCADE.',
        )

    def handle(self, *args, **options):
        target_qs = User.objects.exclude(username__in=FIXTURE_USERNAMES)
        count = target_qs.count()

        if count == 0:
            self.stdout.write('No estate (deceased-proxy) users found.')
            return

        self.stdout.write(f'Estate users not in known fixture set: {count}')
        self.stdout.write('')
        for user in target_qs.order_by('username'):
            self.stdout.write(
                f'  pk={user.pk:<6}  '
                f'username={user.username!r:<30}  '
                f'name={user.get_full_name()!r:<30}  '
                f'joined={user.date_joined:%Y-%m-%d}'
            )
        self.stdout.write('')

        if not options['confirm']:
            self.stdout.write(
                'Dry run — nothing deleted.  '
                'Re-run with --confirm to delete these rows and all dependent data.'
            )
            return

        # Gather pre-delete counts for the audit report.
        # Use pk__in so each filter is a simple IN clause — avoids a subquery
        # that could race against the deletion.
        pk_list = list(target_qs.values_list('pk', flat=True))
        pre = {
            'User':               count,
            'Case':               Case.objects.filter(user__pk__in=pk_list).count(),
            'Answer':             Answer.objects.filter(user__pk__in=pk_list).count(),
            'AnswerHistory':      AnswerHistory.objects.filter(user__pk__in=pk_list).count(),
            'AnswerTable':        AnswerTable.objects.filter(user__pk__in=pk_list).count(),
            'AnswerTableHistory': AnswerTableHistory.objects.filter(user__pk__in=pk_list).count(),
            'SectionStatus':      SectionStatus.objects.filter(user__pk__in=pk_list).count(),
            'ScheduleStatus':     ScheduleStatus.objects.filter(user__pk__in=pk_list).count(),
            'Permission':         Permission.objects.filter(user__pk__in=pk_list).count(),
        }

        # One delete call; CASCADE removes all dependent rows atomically.
        User.objects.filter(pk__in=pk_list).delete()

        col_w = max(len(k) for k in pre) + 2
        self.stdout.write(self.style.SUCCESS('Deleted (including cascade):'))
        for model, n in pre.items():
            label = f'{model}:'.ljust(col_w)
            self.stdout.write(f'  {label} {n:>6}')
