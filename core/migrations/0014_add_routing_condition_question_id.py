from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_rename_display_question_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='routing',
            name='condition_question_id',
            field=models.CharField(
                max_length=100,
                blank=True,
                null=True,
                help_text=(
                    'Optional. If set, routing evaluates the answer to this question '
                    'rather than the current node\'s own answer. The question must have '
                    'been answered earlier in the journey (or on the current set page). '
                    'Leave blank to use the current node\'s own answer (standard behaviour).'
                ),
            ),
        ),
        migrations.RemoveConstraint(
            model_name='routing',
            name='unique_routing_rule',
        ),
        migrations.AddConstraint(
            model_name='routing',
            constraint=models.UniqueConstraint(
                fields=['section', 'current_node', 'condition_question_id', 'answer_value'],
                name='unique_routing_rule',
            ),
        ),
    ]
