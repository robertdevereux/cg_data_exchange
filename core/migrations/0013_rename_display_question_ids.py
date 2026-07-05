from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_add_section_show_confirmation'),
    ]

    operations = [
        migrations.RenameField(
            model_name='section',
            old_name='column_question_ids',
            new_name='display_question_ids',
        ),
    ]
