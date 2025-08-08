from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

from .managers import MyUserManager


class User(AbstractUser):
    """
    Custom user model that uses email as the username field
    """
    username = None  # Remove username field
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=False)
    last_name = models.CharField(max_length=30, blank=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    # Profile fields
    bio = models.TextField(max_length=500, blank=True, null=True)
    # Currently leaving out, to keep simple and save DB space for MVP - perhaps use emojis instead for the time being?
    # profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)

    objects = MyUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_friends(self):
        """Return all accepted friends"""
        return User.objects.filter(
            models.Q(sent_friendships__receiver=self, sent_friendships__status='accepted') |
            models.Q(received_friendships__sender=self, received_friendships__status='accepted')
        ).distinct()

    def get_pending_friend_requests(self):
        """Return pending friend requests received by this user"""
        return Friendship.objects.filter(receiver=self, status='pending')


class Friendship(models.Model):
    """
    Model to handle friend relationships between users
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('blocked', 'Blocked'),
    ]

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_friendships'
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_friendships'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('sender', 'receiver')
        indexes = [
            models.Index(fields=['sender', 'status']),
            models.Index(fields=['receiver', 'status']),
        ]

    def clean(self):
        # Prevent users from sending friend requests to themselves
        if self.sender == self.receiver:
            raise ValidationError("Users cannot send friend requests to themselves.")

        # Check if reverse friendship already exists
        if Friendship.objects.filter(sender=self.receiver, receiver=self.sender).exists():
            raise ValidationError("A friendship request already exists between these users.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sender} -> {self.receiver} ({self.status})"

    def accept(self):
        """Accept the friendship request"""
        self.status = 'accepted'
        self.save()

    def reject(self):
        """Reject the friendship request"""
        self.status = 'rejected'
        self.save()


class Quote(models.Model):
    """
    Model to store quotes that users post about their friends
    """
    text = models.TextField(max_length=1000)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posted_quotes',
        help_text="User who posted the quote"
    )
    quoted_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quotes_about_me',
        help_text="User who said the quote"
    )
    context = models.TextField(
        max_length=500,
        blank=True,
        help_text="Optional context about when/where the quote was said"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    # Privacy settings
    is_public = models.BooleanField(
        default=False,
        help_text="Whether the quote is visible to all users or just friends"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['author', 'created_at']),
            models.Index(fields=['quoted_user', 'created_at']),
            models.Index(fields=['is_public', 'created_at']),
        ]

    def clean(self):
        # Ensure users can only quote their friends
        friendship_exists = Friendship.objects.filter(
            models.Q(sender=self.author, receiver=self.quoted_user, status='accepted') |
            models.Q(sender=self.quoted_user, receiver=self.author, status='accepted')
        ).exists()

        if not friendship_exists:
            raise ValidationError("You can only quote your friends.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'"{self.text[:50]}..." - {self.quoted_user} (by {self.author})'

    def get_witness_count(self):
        """Return the number of witnesses for this quote"""
        return self.witnesses.filter(is_witness=True).count()

    def get_witnesses(self):
        """Return users who witnessed this quote"""
        return User.objects.filter(
            witnessed_quotes__quote=self,
            witnessed_quotes__is_witness=True
        )


class QuoteWitness(models.Model):
    """
    Model to track who has witnessed a quote to verify its authenticity
    """
    quote = models.ForeignKey(
        Quote,
        on_delete=models.CASCADE,
        related_name='witnesses'
    )
    witness = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='witnessed_quotes'
    )
    is_witness = models.BooleanField(
        default=True,
        help_text="True if confirming they witnessed it, False if denying"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(
        max_length=200,
        blank=True,
        help_text="Optional comment about witnessing the quote"
    )

    class Meta:
        unique_together = ('quote', 'witness')
        indexes = [
            models.Index(fields=['quote', 'is_witness']),
            models.Index(fields=['witness', 'created_at']),
        ]

    def clean(self):
        # Prevent the quote author from witnessing their own quote
        if self.witness == self.quote.author:
            raise ValidationError("Quote authors cannot witness their own quotes.")

        # Prevent the quoted user from witnessing quotes about themselves
        if self.witness == self.quote.quoted_user:
            raise ValidationError("Users cannot witness quotes about themselves.")

        # Ensure witness is friends with either the author or quoted user
        is_friend_of_author = Friendship.objects.filter(
            models.Q(sender=self.witness, receiver=self.quote.author, status='accepted') |
            models.Q(sender=self.quote.author, receiver=self.witness, status='accepted')
        ).exists()

        is_friend_of_quoted_user = Friendship.objects.filter(
            models.Q(sender=self.witness, receiver=self.quote.quoted_user, status='accepted') |
            models.Q(sender=self.quote.quoted_user, receiver=self.witness, status='accepted')
        ).exists()

        if not (is_friend_of_author or is_friend_of_quoted_user):
            raise ValidationError("You can only witness quotes involving your friends.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        action = "witnessed" if self.is_witness else "denied witnessing"
        return f"{self.witness} {action} quote by {self.quote.author}"


class QuoteLike(models.Model):
    """
    Model to track likes on quotes
    """
    quote = models.ForeignKey(
        Quote,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='liked_quotes'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('quote', 'user')
        indexes = [
            models.Index(fields=['quote', 'created_at']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user} liked quote by {self.quote.author}"


class Notification(models.Model):
    """
    Model to handle notifications for users
    """
    NOTIFICATION_TYPES = [
        ('friend_request', 'Friend Request'),
        ('friend_accepted', 'Friend Request Accepted'),
        ('new_quote', 'New Quote About You'),
        ('quote_witnessed', 'Quote Witnessed'),
        ('quote_liked', 'Quote Liked'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
        null=True,
        blank=True
    )
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=100)
    message = models.TextField(max_length=300)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Generic foreign key fields for linking to related objects
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, null=True, blank=True)
    friendship = models.ForeignKey(Friendship, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', 'created_at']),
            models.Index(fields=['notification_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.notification_type} for {self.recipient}"

    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.save()
