from django.db import migrations


def backfill_section_members(apps, schema_editor):
    Section = apps.get_model('core', 'Section')
    Routing = apps.get_model('core', 'Routing')
    Question = apps.get_model('core', 'Question')
    QuestionSet = apps.get_model('core', 'QuestionSet')
    SectionMember = apps.get_model('core', 'SectionMember')

    question_ids = set(Question.objects.values_list('question_id', flat=True))
    set_ids = set(QuestionSet.objects.values_list('set_id', flat=True))

    for section in Section.objects.all():
        node_ids = set()
        for r in Routing.objects.filter(section=section):
            if r.current_node:
                node_ids.add(r.current_node)
            if r.next_node:
                node_ids.add(r.next_node)

        order = 10
        for node_id in sorted(node_ids):
            if node_id in question_ids:
                node_type = 'Q'
            elif node_id in set_ids:
                node_type = 'S'
            else:
                continue  # stale/orphaned reference — skip, don't fabricate
            SectionMember.objects.get_or_create(
                section=section, node_id=node_id,
                defaults={'node_type': node_type, 'added_order': order},
            )
            order += 10


class Migration(migrations.Migration):
    dependencies = [('core', '0015_alter_question_question_type_and_more')]
    operations = [migrations.RunPython(backfill_section_members, migrations.RunPython.noop)]
