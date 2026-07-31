"""
core/management/commands/load_hmrc_s8_routing.py

Idempotent management command: replace all routing for HMRC_S8 (IHT405
property section) with the 25-row table below.

Strategy: delete all existing rows for the section, then bulk-create
fresh. Idempotent — safe to re-run; each run produces an identical result.

Changes from the original 24-row version:
  - Tenure (HMRC_56) and letting status (HMRC_57) moved from the
    unconditional trunk into the "no professional valuation" branch.
  - HMRC_60 (professional valuation gateway) is now a genuine Yes/No
    branch: Yes → END (no further questions), No → HMRC_56 (tenure etc.).
  - All convergence paths that previously led to HMRC_56 now lead to
    HMRC_47 (open market value), skipping tenure/letting unless needed.

Run:
    python manage.py load_hmrc_s8_routing
"""

from django.core.management.base import BaseCommand

from core.models import Routing, Section
from core.views_admin_tools import validate_section_routing

# — means NULL in the table below.
ROWS = [
    # order  current_node  condition_question_id  answer_value                      next_node
    (10,  'SET10',   None,       None,                             'HMRC_46'),
    (20,  'HMRC_46', None,       'Sole ownership of the deceased', 'HMRC_47'),
    (30,  'HMRC_46', None,       'Joint names',                   'HMRC_48'),
    (40,  'HMRC_46', None,       'Tenants in common',             'HMRC_49'),
    (50,  'HMRC_48', 'HMRC_14',  'Yes',                           'HMRC_50'),
    (60,  'HMRC_48', 'HMRC_14',  None,                            'HMRC_47'),
    (70,  'HMRC_50', None,       None,                            'HMRC_47'),
    (80,  'HMRC_49', 'HMRC_14',  'Yes',                           'HMRC_53'),
    (90,  'HMRC_49', 'HMRC_14',  None,                            'HMRC_51'),
    (100, 'HMRC_53', None,       'Yes',                           'HMRC_54'),
    (110, 'HMRC_53', None,       'No',                            'HMRC_51'),
    (120, 'HMRC_54', None,       None,                            'HMRC_51'),
    (130, 'HMRC_51', None,       'Yes',                           'HMRC_47'),
    (140, 'HMRC_51', None,       'No',                            'HMRC_52'),
    (150, 'HMRC_52', None,       None,                            'HMRC_47'),
    (160, 'HMRC_47', 'HMRC_14',  'Yes',                           'HMRC_55'),
    (170, 'HMRC_47', 'HMRC_14',  None,                            'HMRC_60'),
    (180, 'HMRC_55', None,       'Yes',                           None),
    (190, 'HMRC_55', None,       'No',                            'HMRC_60'),
    (200, 'HMRC_60', None,       'Yes',                           None),
    (210, 'HMRC_60', None,       'No',                            'HMRC_56'),
    (220, 'HMRC_56', None,       None,                            'HMRC_57'),
    (230, 'HMRC_57', None,       None,                            'HMRC_58'),
    (240, 'HMRC_58', None,       None,                            'HMRC_59'),
    (250, 'HMRC_59', None,       None,                            None),
]


class Command(BaseCommand):
    help = (
        'Replace all routing rows for HMRC_S8 (IHT405 property section) '
        'with the current 25-row specification. Idempotent.'
    )

    def handle(self, *args, **options):
        try:
            section = Section.objects.get(section_id='HMRC_S8')
        except Section.DoesNotExist:
            self.stderr.write(self.style.ERROR('Section HMRC_S8 not found.'))
            return

        # ── Replace existing rows ─────────────────────────────────────────────
        deleted, _ = Routing.objects.filter(section=section).delete()
        self.stdout.write(f'Deleted {deleted} existing routing row(s) for HMRC_S8.')

        for order, current_node, condition_qid, answer_value, next_node in ROWS:
            Routing.objects.create(
                section=section,
                current_node=current_node,
                condition_question_id=condition_qid,
                answer_value=answer_value,
                next_node=next_node,
                order_in_section=order,
            )
            self.stdout.write(
                f'  CREATED  order={order:>3}  {current_node}'
                + (f' [on {condition_qid}]' if condition_qid else '')
                + f' → {next_node or "END"}'
                + (f'  (if {answer_value!r})' if answer_value is not None else '  (unconditional)')
            )

        # ── Verification ──────────────────────────────────────────────────────
        self.stdout.write('')
        total = Routing.objects.filter(section=section).count()
        self.stdout.write(f'Total routing rows for HMRC_S8: {total}')
        if total == len(ROWS):
            self.stdout.write(self.style.SUCCESS(f'Row count correct ({len(ROWS)}).'))
        else:
            self.stdout.write(
                self.style.ERROR(
                    f'UNEXPECTED count: expected {len(ROWS)}, got {total}.'
                )
            )

        # ── Routing validation ────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write('Running validate_section_routing …')
        result = validate_section_routing(section)
        if result['valid']:
            self.stdout.write(self.style.SUCCESS("Validation: {'valid': True, 'issues': []}"))
        else:
            self.stdout.write(self.style.ERROR(f"Validation FAILED: {result}"))
            for issue in result['issues']:
                self.stdout.write(self.style.ERROR(f'  • {issue}'))
