from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Delete notifications and events older than NOTIFICATION_RETENTION_DAYS'

    def handle(self, *args, **options):
        from djangoapp.notifications.tasks import cleanup_notifications
        cleanup_notifications()
        self.stdout.write(self.style.SUCCESS('Notification cleanup complete.'))
