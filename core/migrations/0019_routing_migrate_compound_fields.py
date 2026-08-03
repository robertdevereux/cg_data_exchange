"""
Phase 4 data migration: backfill compound-condition fields on Routing rows.

Decision table (reviewed and approved 3 Aug 2026):

  Old fields                                   New fields
  ─────────────────────────────────────────    ────────────────────────────────────────
  av=null (any cqid)           → unconditional  all five new fields = null
  av set, cqid=null, no comp   → slot-1 eq      comparator_1='=', test_value_1=av
  av set, cqid=null, comp+thresh → slot-1 num   comparator_1=comp, test_value_1=str(thresh)
  av set, cqid set,  no comp   → slot-2 eq      alternate_condition_id=cqid,
                                                  comparator_2='=', test_value_2=av
  av set, cqid set,  comp+thresh → slot-2 num   alternate_condition_id=cqid,
                                                  comparator_2=comp, test_value_2=str(thresh)

Critical invariant: rows with cqid set NEVER get comparator_1/test_value_1
populated. The original logic tested cqid's answer INSTEAD OF the current
node's answer; populating slot-1 would AND both conditions, which is
strictly more restrictive than the original.

Safe to reverse: backwards() clears all five new fields (restores to the
all-null state produced by migration 0018).

Atomicity: RunPython(atomic=True) wraps the operation in a savepoint;
the surrounding migration transaction provides the outer boundary. On any
error the entire migration rolls back.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    Routing = apps.get_model('core', 'Routing')

    rows = list(Routing.objects.all())  # load all into memory before bulk_update

    for row in rows:
        cqid   = row.condition_question_id or None   # normalise '' → None
        av     = row.answer_value
        comp   = row.comparator
        thresh = row.threshold_value

        if av is None:
            # Cases 1 & 4: unconditional — all new fields stay null.
            row.comparator_1          = None
            row.test_value_1          = None
            row.alternate_condition_id = None
            row.comparator_2          = None
            row.test_value_2          = None

        elif cqid:
            # Cases 5 & 6: slot-1 always null; slot-2 tests cqid's answer.
            row.comparator_1          = None
            row.test_value_1          = None
            row.alternate_condition_id = cqid
            if comp and thresh is not None:
                # Case 6: numeric on cqid's answer
                row.comparator_2 = comp
                row.test_value_2 = str(thresh)
            else:
                # Case 5: equality on cqid's answer
                row.comparator_2 = '='
                row.test_value_2 = av

        else:
            # Cases 2 & 3: slot-1 tests current-node answer; slot-2 null.
            row.alternate_condition_id = None
            row.comparator_2          = None
            row.test_value_2          = None
            if comp and thresh is not None:
                # Case 3: numeric on current-node answer
                row.comparator_1 = comp
                row.test_value_1 = str(thresh)
            else:
                # Case 2: equality on current-node answer
                row.comparator_1 = '='
                row.test_value_1 = av

    if rows:
        Routing.objects.bulk_update(rows, [
            'comparator_1',
            'test_value_1',
            'alternate_condition_id',
            'comparator_2',
            'test_value_2',
        ])


def backwards(apps, schema_editor):
    """Clear all compound-condition fields — restores to the 0018 all-null state."""
    Routing = apps.get_model('core', 'Routing')
    Routing.objects.all().update(
        comparator_1=None,
        test_value_1=None,
        alternate_condition_id=None,
        comparator_2=None,
        test_value_2=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_routing_add_compound_fields'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards, atomic=True),
    ]
