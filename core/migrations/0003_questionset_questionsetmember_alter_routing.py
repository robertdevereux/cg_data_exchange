from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_section_section_type'),
    ]

    operations = [
        # 1. Create QuestionSet
        migrations.CreateModel(
            name='QuestionSet',
            fields=[
                ('set_id', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('set_title', models.CharField(max_length=255)),
                ('set_hint', models.CharField(blank=True, max_length=255, null=True)),
            ],
        ),
        # 2. Create QuestionSetMember
        migrations.CreateModel(
            name='QuestionSetMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('display_order', models.PositiveIntegerField(default=0)),
                ('required', models.BooleanField(default=True)),
                ('question', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='set_memberships',
                    to='core.question',
                    to_field='question_id',
                )),
                ('question_set', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='members',
                    to='core.questionset',
                )),
            ],
            options={
                'ordering': ['display_order'],
                'unique_together': {('question_set', 'question')},
            },
        ),
        # 3. Add current_node (nullable temporarily so existing rows aren't rejected)
        migrations.AddField(
            model_name='routing',
            name='current_node',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Q-prefixed question ID or S-prefixed set ID for this screen',
                max_length=100,
            ),
            preserve_default=False,
        ),
        # 4. Add next_node (nullable — mirrors nullable next_question FK)
        migrations.AddField(
            model_name='routing',
            name='next_node',
            field=models.CharField(
                blank=True,
                null=True,
                help_text='Next screen node ID; null means END (proceed to check your answers)',
                max_length=100,
            ),
        ),
        # 5. Copy FK values into the new CharFields
        migrations.RunSQL(
            sql="""
                UPDATE core_routing
                SET current_node = current_question_id,
                    next_node    = next_question_id;
            """,
            reverse_sql="""
                UPDATE core_routing
                SET current_question_id = current_node,
                    next_question_id    = next_node;
            """,
        ),
        # 6. Drop the old unique constraint that references current_question
        migrations.RemoveConstraint(
            model_name='routing',
            name='unique_routing_rule',
        ),
        # 7. Remove old FK columns
        migrations.RemoveField(
            model_name='routing',
            name='current_question',
        ),
        migrations.RemoveField(
            model_name='routing',
            name='next_question',
        ),
        # 8. Add the new unique constraint on (section, current_node, answer_value)
        migrations.AddConstraint(
            model_name='routing',
            constraint=models.UniqueConstraint(
                fields=['section', 'current_node', 'answer_value'],
                name='unique_routing_rule',
            ),
        ),
    ]
