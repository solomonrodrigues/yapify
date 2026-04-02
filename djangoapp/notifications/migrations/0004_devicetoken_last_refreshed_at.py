from django.db import migrations, models
from django.db.models import F


def backfill_last_refreshed_at(apps, schema_editor):
    """
    Seed last_refreshed_at from updated_at for all existing tokens so that
    recently-active devices are not immediately treated as stale after deploy.
    """
    DeviceToken = apps.get_model('notifications', 'DeviceToken')
    DeviceToken.objects.all().update(last_refreshed_at=F('updated_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_notification_recipient_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='devicetoken',
            name='last_refreshed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_last_refreshed_at, migrations.RunPython.noop),
    ]
