from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone


def process_event(event_id):
    """Thin wrapper so Django Q can call the service by dotted path."""
    from djangoapp.notifications.notification_service import process_event as _process
    _process(event_id)


def send_push_notification(recipient_id, title, body, data):
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        return

    from exponent_server_sdk import (
        DeviceNotRegisteredError,
        PushClient,
        PushMessage,
        PushServerError,
    )
    from djangoapp.notifications.models import DeviceToken

    stale_cutoff = timezone.now() - timedelta(days=settings.PUSH_TOKEN_STALE_DAYS)

    tokens = list(
        DeviceToken.objects.filter(
            user_id=recipient_id,
            is_active=True,
            # Skip tokens not refreshed recently — likely logged-out devices where
            # deregistration failed and was never retried (e.g. persistent no-network).
            # Null tokens (pre-migration) were backfilled from updated_at, so they
            # are also covered by this filter.
            last_refreshed_at__gte=stale_cutoff,
        ).values_list('token', flat=True)
    )
    if not tokens:
        return

    messages = [
        PushMessage(to=token, title=title, body=body, data=data)
        for token in tokens
    ]

    try:
        responses = PushClient().publish_multiple(messages)
        for token, response in zip(tokens, responses):
            try:
                response.validate_response()
            except DeviceNotRegisteredError:
                DeviceToken.objects.filter(token=token).update(is_active=False)
    except (PushServerError, Exception):
        pass  # Don't let push failures crash the worker


def flush_batched_push(recipient_id, notification_type, quote_id, window_start_iso):
    from djangoapp.notifications.models import Event

    recipient_id = int(recipient_id)
    quote_id = int(quote_id) if quote_id not in (None, 'None', '') else None
    window_start = datetime.fromisoformat(window_start_iso)

    window_events = (
        Event.objects.filter(
            recipient_id=recipient_id,
            event_type=notification_type,
            quote_id=quote_id,
            created_at__gte=window_start,
            processed_at__isnull=False,
        )
        .select_related('actor')
        .order_by('-created_at')
    )

    # Distinct actor count for this window
    actor_ids = list(window_events.values_list('actor_id', flat=True).distinct())
    count = len(actor_ids)
    if count == 0:
        return

    recent_event = window_events.first()
    actor_name = recent_event.actor.get_full_name()

    _labels = {
        'quote_witnessed': ('Quote Witnessed', 'witnessed'),
        'quote_liked': ('Quote Liked', 'liked'),
    }
    title, verb = _labels.get(notification_type, ('Notification', 'interacted with'))
    body = (
        f'{actor_name} {verb} your quote'
        if count == 1
        else f'{count} people {verb} your quote'
    )

    data = {'notification_type': notification_type}
    if quote_id:
        data['quote_id'] = str(quote_id)
    send_push_notification(recipient_id, title, body, data)


def cleanup_notifications():
    from datetime import timedelta
    from djangoapp.notifications.models import Event, Notification

    cutoff = timezone.now() - timedelta(days=settings.NOTIFICATION_RETENTION_DAYS)
    Notification.objects.filter(last_event_at__lt=cutoff).delete()
    Event.objects.filter(created_at__lt=cutoff).delete()
