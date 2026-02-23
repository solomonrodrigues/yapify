# serializers.py
from typing import List, Optional
import random

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.conf import settings
from django.utils import timezone

from djangoapp.yapify.models import (
    User, Friendship, Quote, QuoteWitness, QuoteLike, QuoteGuess, RecentSearchItem, Report
)
from djangoapp.notifications.models import Notification
from djangoapp.yapify.choices import ReportReason


class MinimalUserSerializer(serializers.ModelSerializer):
    """User serializer including minimum necessary fields"""

    class Meta:
        model = User
        fields = ('id', 'username', 'display_name', 'profile_color')
        read_only_fields = ('id', 'username', 'display_name', 'profile_color')


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('email', 'username', 'display_name', 'password', 'password_confirm', 'bio')
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': True},
            'display_name': {'required': True},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=8)


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=8)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({"new_password_confirm": "Passwords don't match"})
        return attrs


class DetailResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile"""
    friends_count = serializers.SerializerMethodField()
    quotes_posted = serializers.SerializerMethodField()
    quotes_received = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'display_name', 'bio', 'date_joined',
                  'friends_count', 'quotes_posted', 'quotes_received', 'profile_color',
                  'current_streak', 'longest_streak')
        read_only_fields = ('id', 'email', 'date_joined')

    def get_friends_count(self, obj):
        val = getattr(obj, 'annotated_friends_count', None)
        return val if val is not None else obj.get_friends().count()

    def get_quotes_posted(self, obj):
        val = getattr(obj, 'annotated_quotes_posted', None)
        return val if val is not None else obj.posted_quotes.filter(is_active=True).count()

    def get_quotes_received(self, obj):
        val = getattr(obj, 'annotated_quotes_received', None)
        return val if val is not None else obj.quotes_about_me.filter(is_active=True).count()


class FriendshipSerializer(serializers.ModelSerializer):
    """Serializer for friendship relationships"""
    sender = MinimalUserSerializer(read_only=True)
    receiver = MinimalUserSerializer(read_only=True)

    class Meta:
        model = Friendship
        fields = ('id', 'sender', 'receiver', 'status', 'created_at', 'updated_at')
        read_only_fields = ('id', 'sender', 'receiver', 'created_at', 'updated_at')


class FriendRequestSerializer(serializers.ModelSerializer):
    """Serializer for sending friend requests"""
    receiver_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), write_only=True, required=True, allow_null=False
    )

    class Meta:
        model = Friendship
        fields = ('receiver_id',)

    def create(self, validated_data):
        receiver = validated_data['receiver_id']
        friendship = Friendship.objects.create(
            sender=self.context['request'].user,
            receiver=receiver
        )
        return friendship


class QuoteWitnessSerializer(serializers.ModelSerializer):
    """Serializer for quote witnesses"""
    witness = MinimalUserSerializer(read_only=True)

    class Meta:
        model = QuoteWitness
        fields = ('id', 'witness', 'created_at')
        read_only_fields = ('id', 'witness', 'created_at')


class QuoteGuessSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteGuess
        fields = ["id", "user", "quote", "guessed_user", "correct", "skipped", "created_at"]
        read_only_fields = ["id", "correct", "created_at", "user"]

    def validate(self, data):
        request = self.context["request"]
        user = request.user
        quote = data.get("quote")

        # Visibility check: user must be within the quote's friend-union scope
        blocked_ids = user.get_all_blocked_user_ids()
        friends = user.get_friends().exclude(id__in=blocked_ids)
        is_visible = (
            quote.author_id == user.id
            or quote.quoted_user_id == user.id
            or friends.filter(id=quote.author_id).exists()
            or (quote.quoted_user_id and friends.filter(id=quote.quoted_user_id).exists())
        )
        if not is_visible:
            raise serializers.ValidationError("Quote not found.")

        # Prevent author from guessing their own quote
        if quote.author_id == user.id:
            raise serializers.ValidationError("You cannot guess on a quote you posted.")

        # Prevent quoted user from guessing (they know the answer)
        if quote.quoted_user_id == user.id:
            raise serializers.ValidationError("You cannot guess on a quote about yourself.")

        # enforce skip limit
        if data.get("skipped"):
            from django.conf import settings
            from django.utils.timezone import now
            from datetime import timedelta

            week_ago = now() - timedelta(days=7)
            skips_this_week = QuoteGuess.objects.filter(
                user=user, skipped=True, created_at__gte=week_ago
            ).count()
            if skips_this_week >= settings.QUOTE_GUESS_MAX_SKIPS_PER_WEEK:
                raise serializers.ValidationError(
                    f"You can only skip {settings.QUOTE_GUESS_MAX_SKIPS_PER_WEEK} times per week."
                )

        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class QuoteGuessCreateResponseSerializer(QuoteGuessSerializer):
    """Response serializer for guess creation — includes updated streak values."""
    current_streak = serializers.SerializerMethodField()
    longest_streak = serializers.SerializerMethodField()

    class Meta(QuoteGuessSerializer.Meta):
        fields = QuoteGuessSerializer.Meta.fields + ["current_streak", "longest_streak"]

    def get_current_streak(self, obj) -> int:
        return self.context["request"].user.current_streak

    def get_longest_streak(self, obj) -> int:
        return self.context["request"].user.longest_streak


class QuoteGuessListItemSerializer(serializers.ModelSerializer):
    """Serializer for listing guesses on a quote with friendship status"""
    user = MinimalUserSerializer(read_only=True)
    guessed_user = MinimalUserSerializer(read_only=True)
    friendship_status = serializers.SerializerMethodField()

    class Meta:
        model = QuoteGuess
        fields = ["id", "user", "guessed_user", "correct", "skipped", "created_at", "friendship_status"]
        read_only_fields = fields

    def get_friendship_status(self, obj) -> str | None:
        """Return friendship status between requesting user and the guesser"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None

        current_user = request.user
        guesser = obj.user

        if current_user.id == guesser.id:
            return "self"

        friendship = Friendship.objects.filter(
            Q(sender=current_user, receiver=guesser) |
            Q(sender=guesser, receiver=current_user)
        ).first()

        if friendship:
            return friendship.status
        return None


class MinimalQuoteSerializer(serializers.ModelSerializer):
    """Quote serializer including minimum necessary fields"""
    class Meta:
        model = Quote
        fields = ("id", "text", "context", "quoted_user_response", "author", "quoted_user", "quoted_name", "created_at")


class QuoteSerializer(serializers.ModelSerializer):
    """Serializer for quotes"""
    author = MinimalUserSerializer(read_only=True)
    quoted_user = MinimalUserSerializer(read_only=True)
    quoted_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    quoted_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    witness_count = serializers.SerializerMethodField()
    is_witnessed = serializers.SerializerMethodField()
    witnesses = QuoteWitnessSerializer(many=True, read_only=True)
    like_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    is_hidden = serializers.SerializerMethodField()

    # Guessing game support
    can_guess = serializers.SerializerMethodField()
    has_guessed = serializers.SerializerMethodField()
    guess = serializers.SerializerMethodField()
    remaining_skips = serializers.SerializerMethodField()
    guess_options = serializers.SerializerMethodField()

    # Quoted user response
    can_respond = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = (
            'id', 'text', 'context', 'author',
            'quoted_user', 'quoted_user_id', 'quoted_name',
            'quoted_user_response', 'can_respond',
            'created_at', 'updated_at',
            'witness_count', 'is_witnessed', 'witnesses', 'like_count',
            'is_liked', 'is_saved', 'is_hidden',
            'can_guess', 'has_guessed', 'guess', 'remaining_skips', 'guess_options'
        )
        read_only_fields = ('id', 'author', 'created_at', 'updated_at', 'quoted_user_response')

    def get_witness_count(self, obj: Quote) -> int:
        val = getattr(obj, 'annotated_witness_count', None)
        return val if val is not None else obj.get_witness_count()

    def get_is_witnessed(self, obj: Quote) -> bool:
        val = getattr(obj, 'annotated_is_witnessed', None)
        if val is not None:
            return val
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.witnesses.filter(witness=request.user).exists()
        return False

    def get_like_count(self, obj: Quote) -> int:
        val = getattr(obj, 'annotated_like_count', None)
        return val if val is not None else obj.likes.count()

    def get_is_liked(self, obj: Quote) -> bool:
        val = getattr(obj, 'annotated_is_liked', None)
        if val is not None:
            return val
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False

    def get_is_saved(self, obj: Quote) -> bool:
        val = getattr(obj, 'annotated_is_saved', None)
        if val is not None:
            return val
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.saved_quote_links.filter(user=request.user).exists()
        return False

    def get_is_hidden(self, obj: Quote) -> bool:
        val = getattr(obj, 'annotated_is_hidden', None)
        if val is not None:
            return val
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.hidden_quote_links.filter(user=request.user).exists()
        return False

    def get_can_guess(self, obj: Quote) -> bool:
        """Check if current user can guess on this quote"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False

        user = request.user

        # Cannot guess if user is the author
        if obj.author_id == user.id:
            return False

        # Cannot guess if user is the quoted user
        if obj.quoted_user_id == user.id:
            return False

        # Cannot guess if already guessed
        has_guessed = getattr(obj, 'annotated_has_guessed', None)
        if has_guessed is None:
            has_guessed = QuoteGuess.objects.filter(user=user, quote=obj).exists()
        if has_guessed:
            return False

        # Cannot guess if quote doesn't have a real user
        if not obj.quoted_user_id:
            return False

        # Cannot guess if there aren't enough options (need more than 1)
        valid_friends = self.context.get('valid_friends')
        if valid_friends is not None:
            friends = [f for f in valid_friends if f.id != obj.quoted_user_id]
            return len(friends) > 0
        else:
            random_friends = user.get_random_guess_options(exclude=[obj.quoted_user], count=3)
            return len(random_friends) > 0

    def get_has_guessed(self, obj) -> bool:
        val = getattr(obj, 'annotated_has_guessed', None)
        if val is not None:
            return val
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return QuoteGuess.objects.filter(user=request.user, quote=obj).exists()
        return False

    @extend_schema_field(QuoteGuessSerializer(many=False, allow_null=True))
    def get_guess(self, obj) -> Optional[QuoteGuessSerializer]:
        # Try prefetched user_guesses first
        user_guesses = getattr(obj, 'user_guesses', None)
        if user_guesses is not None:
            if user_guesses:
                return QuoteGuessSerializer(user_guesses[0]).data
            return None
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            guess = QuoteGuess.objects.filter(user=request.user, quote=obj).first()
            if guess:
                return QuoteGuessSerializer(guess).data
        return None

    def get_remaining_skips(self, obj) -> int:
        # Use cached value from context if available
        cached = self.context.get('remaining_skips')
        if cached is not None:
            return cached
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        from datetime import timedelta
        used = QuoteGuess.objects.filter(
            user=request.user, skipped=True,
            created_at__gte=timezone.now() - timedelta(days=7),
        ).count()
        return max(settings.QUOTE_GUESS_MAX_SKIPS_PER_WEEK - used, 0)

    @extend_schema_field(MinimalUserSerializer(many=True))
    def get_guess_options(self, obj) -> List[MinimalUserSerializer]:
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []

        user = request.user
        if not obj.quoted_user:
            return []

        seed = hash(f"{user.id}-{obj.id}")

        valid_friends = self.context.get('valid_friends')
        if valid_friends is not None:
            friends = [f for f in valid_friends if f.id != obj.quoted_user_id]
            if not friends:
                return []
            rng = random.Random(seed)
            random_friends = rng.sample(friends, min(len(friends), 3))
        else:
            random_friends = user.get_random_guess_options(exclude=[obj.quoted_user], count=3, seed=seed)

        # Combine correct answer
        options = random_friends + [obj.quoted_user]

        # shuffle deterministically
        rng = random.Random(seed)
        rng.shuffle(options)

        return MinimalUserSerializer(options, many=True).data

    def get_can_respond(self, obj: Quote) -> bool:
        """Check if current user is the quoted user and can respond to this quote"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.quoted_user_id == request.user.id
        return False

    def create(self, validated_data):
        quoted_user = validated_data.pop('quoted_user_id', None)
        if quoted_user:
            validated_data['quoted_user'] = quoted_user
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        quoted_user = validated_data.pop('quoted_user_id', None)
        if quoted_user is not None:
            validated_data['quoted_user'] = quoted_user
            validated_data.setdefault('quoted_name', None)
        return super().update(instance, validated_data)


class QuoteLikeSerializer(serializers.ModelSerializer):
    """Serializer for quote likes"""
    user = MinimalUserSerializer(read_only=True)

    class Meta:
        model = QuoteLike
        fields = ('id', 'user', 'created_at')
        read_only_fields = ('id', 'user', 'created_at')


class PublicUserSerializer(serializers.ModelSerializer):
    """Public serializer for viewing other users' details"""
    # Basic public user info
    username = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    profile_color = serializers.CharField(read_only=True)

    # Statistics
    friends_count = serializers.SerializerMethodField()
    quotes_posted = serializers.SerializerMethodField()
    quotes_received = serializers.SerializerMethodField()

    # Recent public quotes (limit to 10 most recent)
    recent_quotes_posted = serializers.SerializerMethodField()

    # Relationship info with current user
    friendship = serializers.SerializerMethodField()

    # Join date
    date_joined = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'display_name', 'profile_color', 'date_joined',
            'friends_count', 'quotes_posted', 'quotes_received',
            'current_streak', 'longest_streak',
            'recent_quotes_posted', 'friendship',
        ]

    def get_current_user(self):
        """Get the current authenticated user from context"""
        return self.context['request'].user

    def get_friends_count(self, obj) -> int:
        """Total friends this user has"""
        val = getattr(obj, 'annotated_friends_count', None)
        return val if val is not None else obj.get_friends().count()

    def get_quotes_posted(self, obj) -> int:
        """Total quotes this user has posted"""
        val = getattr(obj, 'annotated_quotes_posted', None)
        return val if val is not None else obj.posted_quotes.filter(is_active=True).count()

    def get_quotes_received(self, obj) -> int:
        """Total quotes about this user"""
        val = getattr(obj, 'annotated_quotes_received', None)
        return val if val is not None else obj.quotes_about_me.filter(is_active=True).count()

    @extend_schema_field(QuoteSerializer(many=True))
    def get_recent_quotes_posted(self, obj):
        """Recent quotes posted by this user (limit 10)"""
        from djangoapp.api.views import get_optimized_quote_queryset

        request = self.context.get('request')
        user = request.user if request else None

        qs = obj.posted_quotes.filter(is_active=True)

        if user and user.is_authenticated:
            blocked_ids = user.get_all_blocked_user_ids()
            friends = user.get_friends().exclude(id__in=blocked_ids)
            friend_ids = set(friends.values_list('id', flat=True))

            # Exclude hidden quotes and blocked users' quotes
            qs = (
                qs
                .exclude(hidden_quote_links__user=user)
                .exclude(quoted_user__id__in=blocked_ids)
            )

            # Union visibility: user must be friends with author or quoted_user
            # (or be the author/quoted_user themselves)
            qs = qs.filter(
                Q(author__id__in=friend_ids) |
                Q(quoted_user__id__in=friend_ids) |
                Q(author=user) |
                Q(quoted_user=user)
            )

            qs = get_optimized_quote_queryset(qs, user)

        recent_quotes = qs.order_by('-created_at').distinct()[:10]
        return QuoteSerializer(recent_quotes, many=True, context=self.context).data

    @extend_schema_field(FriendshipSerializer(many=False, allow_null=True))
    def get_friendship(self, obj):
        """Return friendship object (if exists) between current user and this user"""
        current_user = self.get_current_user()
        if current_user == obj:
            return None  # Don't return friendship with yourself

        # Use prefetched data if available (from get_optimized_user_queryset)
        sent = getattr(obj, '_friendship_with_me_sent', None)
        received = getattr(obj, '_friendship_with_me_received', None)
        if sent is not None and received is not None:
            matches = list(sent) + list(received)
            if matches:
                return FriendshipSerializer(matches[0]).data
            return None

        # Fallback to query
        friendship = Friendship.objects.filter(
            Q(sender=current_user, receiver=obj) |
            Q(sender=obj, receiver=current_user)
        ).first()

        if friendship:
            return FriendshipSerializer(friendship).data
        return None


class PublicUserListSerializer(PublicUserSerializer):
    """Lighter serializer for user list views — excludes expensive nested quotes."""

    class Meta(PublicUserSerializer.Meta):
        fields = [f for f in PublicUserSerializer.Meta.fields if f != 'recent_quotes_posted']


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for grouped notification records."""
    actors = serializers.SerializerMethodField()
    friendship = FriendshipSerializer(read_only=True, allow_null=True)

    def get_actors(self, obj):
        # _actors is attached by NotificationListView.list() via batch fetch
        return MinimalUserSerializer(obj._actors, many=True).data

    class Meta:
        model = Notification
        fields = (
            'id', 'notification_type', 'actors', 'actor_count',
            'quote', 'friendship', 'is_read', 'last_event_at',
        )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT token serializer"""
    username_field = 'email'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'] = serializers.EmailField()
        self.fields['password'] = serializers.CharField()
        if 'username' in self.fields:
            del self.fields['username']

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(request=self.context.get('request'),
                                username=email.lower(), password=password)

            if not user:
                raise serializers.ValidationError('Invalid credentials')

            if not user.is_active:
                raise serializers.ValidationError('User account is disabled')

            if not user.is_email_verified:
                raise serializers.ValidationError('Email not verified')

            refresh = self.get_token(user)

            return {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
            }

        raise serializers.ValidationError('Must include email and password')


KIND_CHOICES = (("user", "user"), ("quote", "quote"))


class RecentSearchCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=KIND_CHOICES)
    target_id = serializers.CharField()
    query = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        kind = attrs["kind"]
        tid = attrs["target_id"]
        if kind == "user":
            try:
                attrs["_target"] = User.objects.get(pk=tid)
            except User.DoesNotExist:
                raise serializers.ValidationError({"target_id": "User not found."})
        else:
            try:
                attrs["_target"] = Quote.objects.get(pk=tid)
            except Quote.DoesNotExist:
                raise serializers.ValidationError({"target_id": "Quote not found."})
        return attrs


class RecentSearchItemSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    data = serializers.SerializerMethodField()

    class Meta:
        model = RecentSearchItem
        fields = ("kind", "target_id", "touched_at", "last_query", "data")

    def get_kind(self, obj):
        return "user" if obj.user_target_id else "quote"

    def get_target_id(self, obj):
        return str(obj.user_target_id or obj.quote_target_id)

    def get_data(self, obj):
        if obj.user_target_id and obj.user_target:
            return MinimalUserSerializer(obj.user_target).data
        if obj.quote_target_id and obj.quote_target:
            return MinimalQuoteSerializer(obj.quote_target).data
        return None


class ReportRequestSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReportReason.choices)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        if attrs.get('reason') == ReportReason.OTHER and not attrs.get('description'):
            raise serializers.ValidationError(
                {"description": "Description is required when reason is 'other'."}
            )
        return attrs


class ReportResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ('id', 'reason', 'description', 'created_at')
        read_only_fields = fields
