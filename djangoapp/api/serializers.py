# serializers.py
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from djangoapp.yapify.models import User, Friendship, Quote, QuoteWitness, QuoteLike, Notification


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
        read_only_fields = ('id', 'sender', 'created_at', 'updated_at')


class FriendRequestSerializer(serializers.ModelSerializer):
    """Serializer for sending friend requests"""
    receiver_email = serializers.EmailField(write_only=True)

    class Meta:
        model = Friendship
        fields = ('receiver_email',)

    def validate_receiver_email(self, value):
        try:
            receiver = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist")

        sender = self.context['request'].user
        if sender == receiver:
            raise serializers.ValidationError("You cannot send a friend request to yourself")

        # Check if friendship already exists
        existing_friendship = Friendship.objects.filter(
            sender=sender, receiver=receiver
        ).first() or Friendship.objects.filter(
            sender=receiver, receiver=sender
        ).first()

        if existing_friendship:
            raise serializers.ValidationError("Friendship request already exists")

        return value

    def create(self, validated_data):
        receiver = User.objects.get(email=validated_data['receiver_email'])
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
        fields = ('id', 'witness', 'is_witness', 'comment', 'created_at')
        read_only_fields = ('id', 'witness', 'created_at')


class QuoteSerializer(serializers.ModelSerializer):
    """Serializer for quotes"""
    author = MinimalUserSerializer(read_only=True)
    quoted_user = MinimalUserSerializer(read_only=True)
    quoted_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    quoted_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    witness_count = serializers.SerializerMethodField()
    witnesses = QuoteWitnessSerializer(many=True, read_only=True)
    like_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = (
            'id', 'text', 'author',
            'quoted_user', 'quoted_user_id', 'quoted_name',
            'created_at', 'updated_at',
            'witness_count', 'witnesses', 'like_count', 'is_liked'
        )
        read_only_fields = ('id', 'author', 'created_at', 'updated_at')

    def get_witness_count(self, obj):
        return obj.get_witness_count()

    def get_like_count(self, obj):
        return obj.likes.count()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False

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


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications"""
    sender = MinimalUserSerializer(read_only=True)

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

            refresh = self.get_token(user)

            return {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
            }

        raise serializers.ValidationError('Must include email and password')
