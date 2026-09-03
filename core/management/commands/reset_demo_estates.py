"""
Management command: reset_demo_estates
=======================================
Lists (and optionally deletes) User rows that:
  - are not part of the known fixture set, AND
  - are the `user` on at least one Case for the target regime.

This identifies the deceased-proxy records created by promote_case_to_verified()
during IHT (or other department) demo sessions, while leaving unrelated
department accounts untouched.

Default (no flags): list only — nothing is changed.
--regime REGIME_ID: target a specific regime (default: HMRC_IHT).
With --confirm:     delete those users; Django CASCADE removes every
                    dependent Case, Answer, AnswerHistory, AnswerTable,
                    AnswerTableHistory, SectionStatus, ScheduleStatus, and
                    Permission row in one atomic operation.

Usage:
    python manage.py reset_demo_estates                         # list HMRC_IHT
    python manage.py reset_demo_estates --regime HMRC_IHT       # same, explicit
    python manage.py reset_demo_estates --confirm               # delete HMRC_IHT
    python manage.py reset_demo_estates --regime OTHER --confirm # delete OTHER
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

DEFAULT_REGIME = 'HMRC_IHT'

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
        'List (or with --confirm delete) deceased-proxy User rows that are '
        'the user on at least one Case for the target regime, excluding '
        'known fixture accounts.  Defaults to HMRC_IHT; use --regime to '
        'target another regime.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--regime',
            default=DEFAULT_REGIME,
            metavar='REGIME_ID',
            help=f'Regime to target (default: {DEFAULT_REGIME}).',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Delete the listed rows and all dependent data via CASCADE.',
        )

    def handle(self, *args, **options):
        regime_id = options['regime']

        self.stdout.write(f'Regime: {regime_id}')
        self.stdout.write('')

        target_qs = (
            User.objects
            .exclude(username__in=FIXTURE_USERNAMES)
            .filter(cases__regime_id=regime_id)
            .distinct()
        )
        count = target_qs.count()

        if count == 0:
            self.stdout.write(
                f'No estate (deceased-proxy) users with a case in {regime_id} found.'
            )
            return

        self.stdout.write(
            f'Estate users with a case in {regime_id} '
            f'(not in known fixture set): {count}'
        )
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
        # Materialise pk_list so each count query is a simple IN clause,
        # avoiding a subquery that could race against the deletion.
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
