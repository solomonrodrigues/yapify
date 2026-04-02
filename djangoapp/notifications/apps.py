from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'djangoapp.notifications'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_setup_cleanup_schedule, sender=self)


def _setup_cleanup_schedule(sender, **kwargs):
    """Create the nightly cleanup schedule after migrations run."""
    try:
        from django_q.models import Schedule
        Schedule.objects.update_or_create(
            name='cleanup_notifications_nightly',
            defaults={
                'func': 'djangoapp.notifications.tasks.cleanup_notifications',
                'schedule_type': Schedule.CRON,
                'cron': '0 3 * * *',
            }
        )
    except Exception:
        pass
