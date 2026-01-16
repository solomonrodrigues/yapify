import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .choices import ProfileColor, QuoteResponse, QuoteVisibility
from .managers import MyUserManager
from .utils import get_random_color
from .validators import yapify_username_validator


class User(AbstractUser):
    # Remove first_name and last_name
    first_name = None
    last_name = None
    # Inherits username, is_staff, is_active, and date_joined from AbstractUser
    email = models.EmailField(unique=True)  # Override to enforce uniqueness
    display_name = models.CharField(max_length=50)
    username = models.CharField(
        max_length=30,
        unique=True,
        validators=[yapify_username_validator]
    )
    is_email_verified = models.BooleanField(default=False)

    # Profile fields
    bio = models.TextField(max_length=500, blank=True, null=True)
    profile_color = models.CharField(choices=ProfileColor, default=get_random_color)
    quote_visibility = models.CharField(
        max_length=20,
        choices=QuoteVisibility.choices,
        default=QuoteVisibility.EXTENDED,
        help_text=(
            "Controls who can see your identity when you are quoted by someone else. "
            "Mutual Friends Only = only people who are friends with both you and the poster. "
            "Friends of Friends = also visible to the poster’s friends who may not know you."
        ),
    )

    # Guess streak
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)

    # Quote buckets
    saved_quotes = models.ManyToManyField(
        'Quote',
        through='SavedQuote',
        related_name='saved_by',
        blank=True,
    )
    hidden_quotes = models.ManyToManyField(
        'Quote',
        through='HiddenQuote',
        related_name='hidden_by',
        blank=True,
    )

    objects = MyUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'display_name']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.display_name

    def get_friends(self):
        """Return all accepted friends"""
        return User.objects.filter(
            models.Q(sent_friendships__receiver=self, sent_friendships__status='accepted') |
            models.Q(received_friendships__sender=self, received_friendships__status='accepted')
        ).distinct()

    def get_pending_friend_requests(self):
        """Return pending friend requests received by this user"""
        return Friendship.objects.filter(receiver=self, status='pending')

    def get_valid_friends(self):
        """Return friends, filtering out inactive or unverified."""
        return self.get_friends().filter(is_active=True, is_email_verified=True)

    def get_random_guess_options(self, exclude=None, count=3, seed=None):
        """Return random friends for multiple choice, optionally excluding some.
        Deterministic if `seed` is provided.
        """
        friends = list(self.get_valid_friends())
        if exclude:
            friends = [f for f in friends if f not in exclude]

        if not friends:
            return []

        rng = random.Random(seed) if seed is not None else random
        # sample without replacement
        return rng.sample(friends, min(len(friends), count))

    def increment_streak(self):
        self.current_streak += 1
        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak
        self.save()

    def reset_streak(self):
        self.current_streak = 0
        self.save()


class EmailVerification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_verifications')
    code_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def create_for(cls, user, ttl_minutes: int = 15):
        code = f"{random.randint(0, 999999):06d}"
        obj = cls.objects.create(
            user=user,
            code_hash=make_password(code),
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes)
        )
        return obj, code  # return plaintext so the caller can email it

    def is_valid(self) -> bool:
        return self.used_at is None and timezone.now() <= self.expires_at

    def matches(self, code: str) -> bool:
        return check_password(code, self.code_hash)


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
    context = models.TextField(max_length=1000, blank=True, null=True)
    quoted_user_response = models.CharField(
        max_length=20,
        choices=QuoteResponse.choices,
        blank=True,
        null=True,
        help_text="Whether the quoted user has confirmed or denied this quote"
    )
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
        null=True,
        blank=True,
        help_text="User who said the quote"
    )
    quoted_name = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Name of the person quoted (if not a registered user)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['author', 'created_at']),
            models.Index(fields=['quoted_user', 'created_at']),
        ]

    def clean(self):
        if not self.quoted_user and not self.quoted_name:
            raise ValidationError("You must specify either a quoted user or a quoted name.")

        if self.quoted_user and self.quoted_name:
            raise ValidationError("Specify either quoted_user OR quoted_name, not both.")

        # Only enforce friendship check if quoted_user is set
        if self.quoted_user:
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
        who = self.quoted_user if self.quoted_user else self.quoted_name
        return f'"{self.text[:50]}..." - {who} (by {self.author})'

    def has_real_user(self):
        return self.quoted_user is not None

    def get_witness_count(self):
        """Return the number of witnesses for this quote"""
        return self.witnesses.count()

    def get_witnesses(self):
        """Return users who witnessed this quote"""
        return User.objects.filter(
            witnessed_quotes__quote=self,
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('quote', 'witness')
        indexes = [
            models.Index(fields=['quote']),
            models.Index(fields=['witness', 'created_at']),
        ]

    def clean(self):
        # Ensure witness is the author, or is friends with either the author or quoted user
        is_author = self.witness_id == self.quote.author_id
        is_friend_of_author = Friendship.objects.filter(
            models.Q(sender=self.witness, receiver=self.quote.author, status='accepted') |
            models.Q(sender=self.quote.author, receiver=self.witness, status='accepted')
        ).exists()

        has_real_user = self.quote.has_real_user()

        if has_real_user:
            is_friend_of_quoted_user = Friendship.objects.filter(
                models.Q(sender=self.witness, receiver=self.quote.quoted_user, status='accepted') |
                models.Q(sender=self.quote.quoted_user, receiver=self.witness, status='accepted')
            ).exists()
        else:
            is_friend_of_quoted_user = False

        if not (is_author or is_friend_of_author or (has_real_user and is_friend_of_quoted_user)):
            raise ValidationError("You can only witness quotes involving your friends.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.witness} witnessed quote by {self.quote.author}"


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


class SavedQuote(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_quote_links',
    )
    quote = models.ForeignKey(
        'Quote',
        on_delete=models.CASCADE,
        related_name='saved_quote_links',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'quote')
        ordering = ['-created_at']


class HiddenQuote(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hidden_quote_links',
    )
    quote = models.ForeignKey(
        'Quote',
        on_delete=models.CASCADE,
        related_name='hidden_quote_links',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'quote')
        ordering = ['-created_at']


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


class QuoteGuess(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guesses")
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="guesses")
    guessed_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guessed_by",
        help_text="The friend they guessed. Null if skipped.",
    )
    correct = models.BooleanField(null=True, blank=True)
    skipped = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "quote")
        ordering = ["-created_at"]
        verbose_name_plural = "Quote guesses"

    def save(self, *args, **kwargs):
        if self.skipped:
            self.guessed_user = None
            self.correct = None
        else:
            # must have guessed_user
            if not self.guessed_user:
                raise ValueError("guessed_user required unless skipped=True")
            # correctness check
            self.correct = self.guessed_user_id == self.quote.quoted_user_id

        # Handle streak
        creating = self._state.adding  # only adjust streak on first save
        super().save(*args, **kwargs)

        if creating:
            user = self.user
            if self.skipped:
                pass  # skip does not break streak, just no increment
            elif self.correct:
                user.increment_streak()
            else:
                user.reset_streak()  # wrong guess breaks streak


class RecentSearchItem(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="recent_search_items",
    )

    # Exactly one of these must be non-null
    user_target = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="recently_searched_by",
    )
    quote_target = models.ForeignKey(
        Quote,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="recently_searched_by",
    )

    touched_at = models.DateTimeField(default=timezone.now)
    last_query = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        ordering = ["-touched_at"]
        constraints = [
            # XOR: exactly one of user_target, quote_target is non-null
            models.CheckConstraint(
                condition=(
                    # (user is not null AND quote is null) OR (user is null AND quote is not null)
                    (Q(user_target__isnull=False) & Q(quote_target__isnull=True)) |
                    (Q(user_target__isnull=True) & Q(quote_target__isnull=False))
                ),
                name="recent_target_exactly_one_set",
            ),
            # Uniqueness per kind (Postgres supports partial unique constraints)
            models.UniqueConstraint(
                fields=["owner", "user_target"],
                condition=Q(user_target__isnull=False),
                name="unique_recent_owner_user",
            ),
            models.UniqueConstraint(
                fields=["owner", "quote_target"],
                condition=Q(quote_target__isnull=False),
                name="unique_recent_owner_quote",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "touched_at"]),
            models.Index(fields=["user_target"]),
            models.Index(fields=["quote_target"]),
        ]

    def __str__(self):
        tgt = self.user_target_id or self.quote_target_id
        kind = "user" if self.user_target_id else "quote"
        return f"{self.owner_id} → {kind}:{tgt} @ {self.touched_at}"
