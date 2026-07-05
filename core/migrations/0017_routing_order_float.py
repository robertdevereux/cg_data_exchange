from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_backfill_section_members'),
    ]

    operations = [
        migrations.AlterField(
            model_name='routing',
            name='order_in_section',
            field=models.FloatField(default=0),
        ),
    ]
