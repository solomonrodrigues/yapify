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
    User, Friendship, Quote, QuoteWitness, QuoteLike, Notification, QuoteGuess, RecentSearchItem
)


class MinimalUserSerializer(serializers.ModelSerializer):
    """User serializer including minimum necessary fields"""

    class Meta:
        model = User
        fields = ('id', 'username', 'display_name', 'quote_visibility', 'profile_color')
        read_only_fields = ('id', 'username', 'display_name', 'quote_visibility', 'profile_color')


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


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile"""
    friends_count = serializers.SerializerMethodField()
    quotes_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'display_name', 'bio', 'date_joined',
                  'friends_count', 'quotes_count', 'quote_visibility', 'profile_color')
        read_only_fields = ('id', 'email', 'date_joined')

    def get_friends_count(self, obj):
        return obj.get_friends().count()

    def get_quotes_count(self, obj):
        return obj.quotes_about_me.filter(is_active=True).count()


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


class MinimalQuoteSerializer(serializers.ModelSerializer):
    """Quote serializer including minimum necessary fields"""
    class Meta:
        model = Quote
        fields = ("id", "text", "context", "author", "quoted_user", "quoted_name", "created_at")


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
    has_guessed = serializers.SerializerMethodField()
    guess = serializers.SerializerMethodField()
    remaining_skips = serializers.SerializerMethodField()
    guess_options = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = (
            'id', 'text', 'context', 'author',
            'quoted_user', 'quoted_user_id', 'quoted_name',
            'created_at', 'updated_at',
            'witness_count', 'is_witnessed', 'witnesses', 'like_count',
            'is_liked', 'is_saved', 'is_hidden',
            'has_guessed', 'guess', 'remaining_skips', 'guess_options'
        )
        read_only_fields = ('id', 'author', 'created_at', 'updated_at')

    def get_witness_count(self, obj: Quote) -> int:
        return obj.get_witness_count()

    def get_is_witnessed(self, obj: Quote) -> bool:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.witnesses.filter(witness=request.user).exists()
        return False

    def get_like_count(self, obj: Quote) -> int:
        return obj.likes.count()

    def get_is_liked(self, obj: Quote) -> bool:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False

    def get_is_saved(self, obj: Quote) -> bool:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.saved_quote_links.filter(user=request.user).exists()
        return False

    def get_is_hidden(self, obj: Quote) -> bool:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.hidden_quote_links.filter(user=request.user).exists()
        return False

    def get_has_guessed(self, obj) -> bool:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return QuoteGuess.objects.filter(user=request.user, quote=obj).exists()
        return False

    @extend_schema_field(QuoteGuessSerializer(many=False, allow_null=True))
    def get_guess(self, obj) -> Optional[QuoteGuessSerializer]:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            guess = QuoteGuess.objects.filter(user=request.user, quote=obj).first()
            if guess:
                return QuoteGuessSerializer(guess).data
        return None

    def get_remaining_skips(self, obj) -> int:
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        used = QuoteGuess.objects.filter(
            user=request.user, skipped=True,
            created_at__week=timezone.now().isocalendar().week,
            created_at__year=timezone.now().year
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

        # deterministic seed per user + quote
        seed = hash(f"{user.id}-{obj.id}")
        random_friends = user.get_random_guess_options(exclude=[obj.quoted_user], count=3, seed=seed)

        # Combine correct answer
        options = random_friends + [obj.quoted_user]

        # shuffle again deterministically
        rng = random.Random(seed)
        rng.shuffle(options)

        return MinimalUserSerializer(options, many=True).data

    def create(self, validated_data):
        quoted_user = validated_data.pop('quoted_user_id', None)
        if quoted_user:
            validated_data['quoted_user'] = quoted_user
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


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

    # Quote statistics - public info
    total_quotes_posted = serializers.SerializerMethodField()
    total_quotes_received = serializers.SerializerMethodField()

    # Recent public quotes (limit to 10 most recent)
    recent_quotes_posted = serializers.SerializerMethodField()

    # Relationship info with current user
    friendship = serializers.SerializerMethodField()
    quotes_i_made_about_user = serializers.SerializerMethodField()

    # Join date
    date_joined = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'display_name', 'profile_color', 'date_joined',
            'total_quotes_posted', 'total_quotes_received',
            'recent_quotes_posted', 'friendship', 'quotes_i_made_about_user'
        ]

    def get_current_user(self):
        """Get the current authenticated user from context"""
        return self.context['request'].user

    def get_total_quotes_posted(self, obj) -> int:
        """Total quotes this user has posted"""
        return obj.posted_quotes.filter(is_active=True).count()

    def get_total_quotes_received(self, obj) -> int:
        """Total quotes about this user"""
        return obj.quotes_about_me.filter(is_active=True).count()

    @extend_schema_field(QuoteSerializer(many=True))
    def get_recent_quotes_posted(self, obj):
        """Recent quotes posted by this user (limit 10)"""
        recent_quotes = obj.posted_quotes.filter(
            is_active=True
        ).order_by('-created_at')[:10]
        return QuoteSerializer(recent_quotes, many=True).data

    @extend_schema_field(FriendshipSerializer(many=False, allow_null=True))
    def get_friendship(self, obj):
        """Return friendship object (if exists) between current user and this user"""
        current_user = self.get_current_user()
        if current_user == obj:
            return None  # Don't return friendship with yourself

        friendship = Friendship.objects.filter(
            Q(sender=current_user, receiver=obj) |
            Q(sender=obj, receiver=current_user)
        ).first()

        if friendship:
            return FriendshipSerializer(friendship).data
        return None

    @extend_schema_field(QuoteSerializer(many=True))
    def get_quotes_i_made_about_user(self, obj):
        """Quotes the current user has made about this user (limit 10)"""
        current_user = self.get_current_user()
        if current_user == obj:
            return []  # Don't show quotes about yourself when viewing own profile

        my_quotes_about_user = obj.quotes_about_me.filter(
            author=current_user,
            is_active=True
        ).order_by('-created_at')[:10]
        return QuoteSerializer(my_quotes_about_user, many=True).data


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications"""
    sender = MinimalUserSerializer(read_only=True)
    friendship = FriendshipSerializer(allow_null=True)

    class Meta:
        model = Notification
        fields = ('id', 'sender', 'notification_type', 'title',
                  'message', 'is_read', 'created_at', 'quote', 'friendship')
        read_only_fields = ('id', 'sender', 'created_at')


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
                                username=email, password=password)

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
