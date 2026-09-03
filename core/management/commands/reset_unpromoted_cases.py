"""
Management command: reset_unpromoted_cases
==========================================
Lists (and optionally deletes) Case rows for the target regime where the
case user is a known fixture account — these are abandoned drafts that were
started by an executor (alice, bob, etc.) but never promoted to a deceased
record via promote_case_to_verified().

The fixture User row is never touched.  After a --confirm run the account
can log in and start a completely fresh case with no stale answers or status.

Cascade from Case.delete() removes:
    Answer, AnswerHistory, AnswerTable, AnswerTableHistory, Permission

SectionStatus and ScheduleStatus have no FK to Case and are deleted
explicitly, filtered by (user=case.user, regime=case.regime).

Default (no flags): list only — nothing is changed.
--regime REGIME_ID: target a specific regime (default: HMRC_IHT).
--confirm:          perform the deletion.

Usage:
    python manage.py reset_unpromoted_cases                         # list HMRC_IHT
    python manage.py reset_unpromoted_cases --regime HMRC_IHT       # same, explicit
    python manage.py reset_unpromoted_cases --confirm               # delete HMRC_IHT
    python manage.py reset_unpromoted_cases --regime OTHER --confirm
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
        'List (or with --confirm delete) Case rows for the target regime where '
        'the case user is a known fixture account — abandoned drafts that were '
        'never promoted to a deceased record.  The User row is never deleted.'
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
            help=(
                'Delete the listed Case rows (cascade) and the corresponding '
                'SectionStatus / ScheduleStatus rows (explicit).  '
                'User rows are never deleted.'
            ),
        )

    def handle(self, *args, **options):
        regime_id = options['regime']

        self.stdout.write(f'Regime: {regime_id}')
        self.stdout.write('')

        target_cases = (
            Case.objects
            .filter(user__username__in=FIXTURE_USERNAMES, regime_id=regime_id)
            .select_related('user')
            .order_by('started_at')
        )
        count = target_cases.count()

        if count == 0:
            self.stdout.write(
                f'No unpromoted draft cases for fixture accounts in {regime_id} found.'
            )
            return

        self.stdout.write(
            f'Unpromoted draft cases for fixture accounts in {regime_id}: {count}'
        )
        self.stdout.write('')
        for case in target_cases:
            self.stdout.write(
                f'  case_id={case.case_id!r:<44}  '
                f'user={case.user.username!r:<15}  '
                f'started={case.started_at:%Y-%m-%d}'
            )
        self.stdout.write('')

        if not options['confirm']:
            self.stdout.write(
                'Dry run — nothing deleted.  '
                'Re-run with --confirm to delete these cases and dependent data '
                '(User rows are never deleted).'
            )
            return

        # Materialise IDs before deletion to avoid iterating a live queryset.
        case_ids       = list(target_cases.values_list('case_id', flat=True))
        affected_pks   = list(
            target_cases.values_list('user__pk', flat=True).distinct()
        )

        # Pre-delete counts for the audit report.
        # Case-cascaded tables: filtered by case FK.
        # Status tables: filtered by (user, regime) — they carry no Case FK.
        pre = {
            'Case':               count,
            'Answer':             Answer.objects.filter(case_id__in=case_ids).count(),
            'AnswerHistory':      AnswerHistory.objects.filter(case_id__in=case_ids).count(),
            'AnswerTable':        AnswerTable.objects.filter(case_id__in=case_ids).count(),
            'AnswerTableHistory': AnswerTableHistory.objects.filter(case_id__in=case_ids).count(),
            'Permission':         Permission.objects.filter(case_id__in=case_ids).count(),
            'SectionStatus':      SectionStatus.objects.filter(
                                      user__pk__in=affected_pks, regime_id=regime_id,
                                  ).count(),
            'ScheduleStatus':     ScheduleStatus.objects.filter(
                                      user__pk__in=affected_pks, regime_id=regime_id,
                                  ).count(),
        }

        # Explicit deletion of status rows (no Case FK — cascade won't reach them).
        SectionStatus.objects.filter(
            user__pk__in=affected_pks, regime_id=regime_id,
        ).delete()
        ScheduleStatus.objects.filter(
            user__pk__in=affected_pks, regime_id=regime_id,
        ).delete()

        # Case deletion — cascade removes Answer, AnswerHistory, AnswerTable,
        # AnswerTableHistory, and Permission rows tied to these cases.
        Case.objects.filter(case_id__in=case_ids).delete()

        col_w = max(len(k) for k in pre) + 2
        self.stdout.write(
            self.style.SUCCESS('Deleted (Case cascade + explicit status rows):')
        )
        for model, n in pre.items():
            label = f'{model}:'.ljust(col_w)
            self.stdout.write(f'  {label} {n:>6}')
        self.stdout.write('')
        self.stdout.write(
            'User rows untouched — fixture accounts can log in and start fresh.'
        )
