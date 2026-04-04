from django.conf import settings
from django.db import models


NOTIFICATION_TYPES = [
    ('friend_request', 'Friend Request'),
    ('friend_accepted', 'Friend Request Accepted'),
    ('new_quote', 'New Quote About You'),
    ('quote_witnessed', 'Quote Witnessed'),
    ('quote_liked', 'Quote Liked'),
    ('quote_guessed', 'Quote Guessed'),
    ('you_were_guessed', 'You Were Guessed'),
    ('quote_response', 'Quote Confirmed or Denied'),
]


class Notification(models.Model):
    """
    One row per notification group: (recipient, notification_type, quote, friendship).
    Maintained by the pipeline via upsert — never created directly in views.
    """
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    quote = models.ForeignKey(
        'yapify.Quote',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    friendship = models.ForeignKey(
        'yapify.Friendship',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # Group state — maintained by the pipeline
    actor_ids = models.JSONField(default=list)
    # Capped at 50 entries (display list); most-recent actor first.
    # actor_count is the true all-time distinct-actor total and may exceed len(actor_ids).
    actor_count = models.IntegerField(default=0)
    is_read = models.BooleanField(default=False)
    last_event_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('recipient', 'notification_type', 'quote', 'friendship')]
        ordering = ['-last_event_at']
        indexes = [
            models.Index(fields=['recipient']),
            models.Index(fields=['recipient', 'is_read', 'last_event_at']),
        ]

    def __str__(self):
        return f'{self.notification_type} for {self.recipient}'

    def mark_as_read(self):
        self.is_read = True
        self.save(update_fields=['is_read'])

    def mark_as_unread(self):
        self.is_read = False
        self.save(update_fields=['is_read'])


class Event(models.Model):
    """
    Raw audit log — one row per user action that may produce a notification.
    processed_at=None means the worker hasn't handled it yet.
    """
    event_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='emitted_events',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_events',
    )
    quote = models.ForeignKey(
        'yapify.Quote',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    friendship = models.ForeignKey(
        'yapify.Friendship',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['recipient', 'event_type', 'created_at']),
            models.Index(fields=['processed_at', 'created_at']),
            models.Index(fields=['quote', 'event_type']),
        ]

    def __str__(self):
        return f'{self.event_type}: {self.actor} → {self.recipient}'


class DeviceToken(models.Model):
    """
    Expo push token for a user's device.

    Token lifecycle
    ---------------
    is_active=False is set when:
      - The user explicitly logs out and the DELETE /api/devices/ call succeeds.
      - The user's app calls DELETE without auth on the next cold start (pending-deregistration
        retry queue — handles the case where the logout call failed due to no network).
      - The Expo push service returns DeviceNotRegistered, meaning the app was uninstalled or
        the OS revoked the token.

    Known limitation
    ----------------
    If a device logs out with no network AND never opens the app again, the token stays active
    indefinitely. The last_refreshed_at field provides a bounded upper limit: tokens not seen
    within PUSH_TOKEN_STALE_DAYS are skipped at send time. See docs/push-notification-token-lifecycle.md.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='device_tokens',
    )
    token = models.CharField(max_length=200, unique=True)  # ExponentPushToken[...]
    is_active = models.BooleanField(default=True)  # False when Expo reports DeviceNotRegistered
    # Updated on registration and on every successful JWT refresh. Used to suppress
    # notifications to tokens that haven't been seen in PUSH_TOKEN_STALE_DAYS.
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'is_active'])]

    def __str__(self):
        return f'{self.user} — {self.token[:30]}…'
