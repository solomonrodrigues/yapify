from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('yapify', '0022_group_models'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Friendship',
        ),
    ]
