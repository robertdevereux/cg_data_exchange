"""
core/management/commands/load_hmrc_s8_routing.py

One-off management command: configure routing for HMRC_S8 (IHT405 property
section). Idempotent — uses get_or_create on the Routing model's unique
constraint (section, current_node, condition_question_id, answer_value).
Safe to re-run; prints created vs. already-existing counts.

Run:
    python manage.py load_hmrc_s8_routing
"""

from django.core.management.base import BaseCommand

from core.models import Routing, Section
from core.views_admin_tools import validate_section_routing

# — means NULL in the table below.
ROWS = [
    # order  current_node  condition_question_id  answer_value        next_node
    (10,  'SET10',   None,        None,                  'HMRC_46'),
    (20,  'HMRC_46', None,        'Sole ownership',      'HMRC_56'),
    (30,  'HMRC_46', None,        'Joint tenants',       'HMRC_48'),
    (40,  'HMRC_46', None,        'Tenants in common',   'HMRC_49'),
    (50,  'HMRC_48', 'HMRC_14',   'Yes',                 'HMRC_50'),
    (60,  'HMRC_48', 'HMRC_14',   None,                  'HMRC_56'),
    (70,  'HMRC_50', None,        None,                  'HMRC_56'),
    (80,  'HMRC_49', 'HMRC_14',   'Yes',                 'HMRC_53'),
    (90,  'HMRC_49', 'HMRC_14',   None,                  'HMRC_51'),
    (100, 'HMRC_53', None,        'Yes',                 'HMRC_54'),
    (110, 'HMRC_53', None,        'No',                  'HMRC_51'),
    (120, 'HMRC_54', None,        None,                  'HMRC_51'),
    (130, 'HMRC_51', None,        'Yes',                 'HMRC_56'),
    (140, 'HMRC_51', None,        'No',                  'HMRC_52'),
    (150, 'HMRC_52', None,        None,                  'HMRC_56'),
    (160, 'HMRC_56', None,        None,                  'HMRC_57'),
    (170, 'HMRC_57', None,        None,                  'HMRC_47'),
    (180, 'HMRC_47', 'HMRC_14',   'Yes',                 'HMRC_55'),
    (190, 'HMRC_47', 'HMRC_14',   None,                  'HMRC_58'),
    (200, 'HMRC_55', None,        'Yes',                 None),
    (210, 'HMRC_55', None,        'No',                  'HMRC_58'),
    (220, 'HMRC_58', None,        None,                  'HMRC_59'),
    (230, 'HMRC_59', None,        None,                  'HMRC_60'),
    (240, 'HMRC_60', None,        None,                  None),
]


class Command(BaseCommand):
    help = 'Load routing rows for HMRC_S8 (IHT405 property section). Idempotent.'

    def handle(self, *args, **options):
        try:
            section = Section.objects.get(section_id='HMRC_S8')
        except Section.DoesNotExist:
            self.stderr.write(self.style.ERROR('Section HMRC_S8 not found.'))
            return

        created_count  = 0
        existing_count = 0

        for order, current_node, condition_qid, answer_value, next_node in ROWS:
            _, created = Routing.objects.get_or_create(
                section=section,
                current_node=current_node,
                condition_question_id=condition_qid,
                answer_value=answer_value,
                defaults={
                    'next_node':        next_node,
                    'order_in_section': order,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(
                    f'  CREATED  order={order:>3}  {current_node}'
                    + (f' [on {condition_qid}]' if condition_qid else '')
                    + f' → {next_node or "END"}'
                    + (f'  (if {answer_value!r})' if answer_value is not None else '  (unconditional)')
                )
            else:
                existing_count += 1
                self.stdout.write(
                    f'  EXISTS   order={order:>3}  {current_node}'
                    + (f' [on {condition_qid}]' if condition_qid else '')
                    + f' → {next_node or "END"}'
                    + (f'  (if {answer_value!r})' if answer_value is not None else '  (unconditional)')
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Done: {created_count} created, {existing_count} already existed.'
            )
        )

        # ── Verification ──────────────────────────────────────────────────────
        total = Routing.objects.filter(section=section).count()
        self.stdout.write(f'Total routing rows for HMRC_S8: {total}')
        if total == len(ROWS):
            self.stdout.write(self.style.SUCCESS(f'Row count correct ({len(ROWS)}).'))
        else:
            self.stdout.write(
                self.style.WARNING(
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
