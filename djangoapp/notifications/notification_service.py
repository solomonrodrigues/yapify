import random as _random
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from djangoapp.notifications.models import Event, Notification


HIGH_TIER = {'friend_request', 'friend_accepted', 'new_quote', 'quote_response'}
LOW_TIER = {'quote_witnessed', 'quote_liked', 'quote_guessed', 'you_were_guessed'}

_MAX_NOTIFICATIONS_PER_USER = 500

_PUSH_TITLES = {
    'friend_request': 'New Friend Request',
    'friend_accepted': 'Friend Request Accepted',
    'new_quote': 'New Quote About You',
    'quote_witnessed': 'Quote Witnessed',
    'quote_liked': 'Quote Liked',
    'quote_guessed': 'Quote Guessed',
    'you_were_guessed': 'People Are Guessing You',
    'quote_response': 'Quote Response',
}

_PUSH_BODIES = {
    'friend_request': '{name} sent you a friend request',
    'friend_accepted': '{name} accepted your friend request',
    'new_quote': '{name} posted a quote about you',
    'quote_witnessed': '{name} witnessed your quote',
    'quote_liked': '{name} liked your quote',
    'quote_guessed': '{name} guessed your quote',
    'you_were_guessed': '{name} guessed it was you',
    'quote_response': '{name} responded to your quote',
}

# Subtitles appended to certain push notifications to nudge users to post.
# Shown below the body on iOS; silently ignored on platforms that don't support it.
_ENGAGEMENT_SUBTITLES = [
    'Anyone say something funny recently?',
    'Catch what they said before they deny it 👀',
    'Your group needs more quotes 📖',
]

_SUBTITLE_TYPES = {'new_quote', 'quote_witnessed', 'quote_liked', 'quote_guessed', 'you_were_guessed'}


def _engagement_subtitle(event_type):
    if event_type not in _SUBTITLE_TYPES:
        return None
    return _random.choice(_ENGAGEMENT_SUBTITLES)


def emit_event(event_type, actor, recipient, quote=None, friendship=None):
    """Create an Event record and enqueue it for async processing."""
    from django_q.tasks import async_task

    event = Event.objects.create(
        event_type=event_type,
        actor=actor,
        recipient=recipient,
        quote=quote,
        friendship=friendship,
    )
    async_task('djangoapp.notifications.tasks.process_event', event.id)


def _is_suppressed(event):
    """Return True if this event should not produce a notification."""
    from djangoapp.yapify.models import Friendship

    if event.actor_id == event.recipient_id:
        return True
    if not event.recipient.is_active:
        return True
    if not event.recipient.is_email_verified:
        return True

    return Friendship.objects.filter(
        status='blocked',
    ).filter(
        Q(sender_id=event.actor_id, receiver_id=event.recipient_id) |
        Q(sender_id=event.recipient_id, receiver_id=event.actor_id)
    ).exists()


def process_event(event_id):
    """Core pipeline: upsert the group Notification record and schedule push."""
    from django_q.models import Schedule
    from django_q.tasks import async_task

    try:
        event = Event.objects.select_related('actor', 'recipient').get(pk=event_id)
    except Event.DoesNotExist:
        return

    # Idempotency guard
    if event.processed_at is not None:
        return

    if _is_suppressed(event):
        event.processed_at = timezone.now()
        event.save(update_fields=['processed_at'])
        return

    with transaction.atomic():
        notification, created = Notification.objects.get_or_create(
            recipient=event.recipient,
            notification_type=event.event_type,
            quote=event.quote,
            friendship=event.friendship,
            defaults={'last_event_at': event.created_at, 'actor_count': 1},
        )
        if not created:
            # Re-acquire with a row lock to prevent concurrent worker corruption
            notification = Notification.objects.select_for_update().get(pk=notification.pk)

        actor_id = event.actor_id
        ids = list(notification.actor_ids)
        is_new_actor = actor_id not in ids
        if actor_id in ids:
            ids.remove(actor_id)
        ids.insert(0, actor_id)
        notification.actor_ids = ids[:50]
        if is_new_actor and not created:
            notification.actor_count += 1
        notification.last_event_at = max(notification.last_event_at, event.created_at)
        notification.is_read = False
        notification.save()

        # Enforce per-user cap: delete oldest notifications beyond the limit.
        excess_ids = list(
            Notification.objects
            .filter(recipient=event.recipient)
            .order_by('-last_event_at')
            .values_list('id', flat=True)[_MAX_NOTIFICATIONS_PER_USER:]
        )
        if excess_ids:
            Notification.objects.filter(id__in=excess_ids).delete()

    event.processed_at = timezone.now()
    event.save(update_fields=['processed_at'])

    # Enqueue push notification
    title = _PUSH_TITLES.get(event.event_type, '')
    body = _PUSH_BODIES.get(event.event_type, '').format(name=event.actor.get_full_name())

    # For quote_response, use the actual confirmed/denied value in the body
    if event.event_type == 'quote_response' and event.quote_id:
        response_val = event.quote.quoted_user_response
        if response_val == 'confirmed':
            body = f'{event.actor.get_full_name()} confirmed your quote'
        elif response_val == 'denied':
            body = f'{event.actor.get_full_name()} disputed your quote'

    subtitle = _engagement_subtitle(event.event_type)
    recipient_id = event.recipient_id
    data = {'notification_type': event.event_type}
    if event.quote_id:
        data['quote_id'] = str(event.quote_id)

    if event.event_type in HIGH_TIER:
        async_task(
            'djangoapp.notifications.tasks.send_push_notification',
            recipient_id, title, body, data, subtitle,
        )
    elif event.event_type in LOW_TIER:
        quote_id = event.quote_id
        now = timezone.now()
        schedule_name = f'flush_push_{recipient_id}_{event.event_type}_{quote_id}'
        Schedule.objects.get_or_create(
            name=schedule_name,
            defaults={
                'func': 'djangoapp.notifications.tasks.flush_batched_push',
                'args': f'{recipient_id},"{event.event_type}",{quote_id},"{now.isoformat()}"',
                'next_run': now + timedelta(minutes=30),
                'schedule_type': Schedule.ONCE,
            }
        )
