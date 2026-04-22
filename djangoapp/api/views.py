# views.py
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from rest_framework import generics, status, permissions, exceptions, filters
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView as BaseTokenRefreshView
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db.models import F, Q, Max, Count, Exists, OuterRef, Prefetch
from djangoapp.yapify.models import User, Friendship, Quote, QuoteWitness, QuoteLike, EmailVerification, \
    QuoteGuess, RecentSearchItem, SavedQuote, HiddenQuote, PasswordReset, Report, \
    Group, GroupMembership, GroupInvite, Block
from djangoapp.notifications.models import Notification, Event, DeviceToken
from djangoapp.notifications.notification_service import emit_event
from .serializers import (
    UserRegistrationSerializer,
    UserSerializer,
    FriendshipSerializer,
    FriendRequestSerializer,
    QuoteSerializer,
    QuoteWitnessSerializer,
    NotificationSerializer,
    CustomTokenObtainPairSerializer,
    PublicUserSerializer,
    PublicUserListSerializer,
    ResendVerificationSerializer,
    VerifyEmailSerializer,
    VerifyEmailResponseSerializer,
    QuoteGuessSerializer,
    QuoteGuessCreateResponseSerializer,
    QuoteGuessListItemSerializer,
    RecentSearchItemSerializer,
    RecentSearchCreateSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    DetailResponseSerializer,
    ReportRequestSerializer,
    ReportResponseSerializer,
    DeviceTokenSerializer,
    RegisterResponseSerializer,
    MessageResponseSerializer,
    FriendRequestActionSerializer,
    FriendshipWithMessageSerializer,
    WitnessResponseSerializer,
    QuoteRespondRequestSerializer,
    QuoteWithMessageSerializer,
    QuoteAssignUserRequestSerializer,
    MarkAllReadResponseSerializer,
    UnreadCountResponseSerializer,
    AppConfigResponseSerializer,
    GroupSerializer,
    GroupCreateSerializer,
    GroupRenameSerializer,
    GroupMemberSerializer,
    GroupInviteSerializer,
    GroupInviteCreateSerializer,
    GroupInviteRespondSerializer,
)
from .utils import send_verification_email, normalize_email, send_password_reset_email
from .exceptions import api_error
from .error_codes import (
    VERIFICATION_CODE_INVALID, EMAIL_ALREADY_VERIFIED, RESET_CODE_INVALID,
    NO_PENDING_REQUEST, NOT_FRIENDS, INVALID_ACTION, CANNOT_BLOCK_SELF,
    INVALID_QUOTE_RESPONSE, QUOTE_ALREADY_HAS_USER, FIELD_REQUIRED,
    CANNOT_REPORT_SELF, ALREADY_REPORTED, REPORT_NOT_FOUND,
    INVALID_TOKEN_FORMAT, NOT_FOUND, MISSING_PARAMETERS, INVALID_PARAMETER,
    NOT_GROUP_MEMBER, NOT_GROUP_ADMIN, ALREADY_GROUP_MEMBER, INVITE_ALREADY_PENDING,
    INVITE_NOT_FOUND, CANNOT_LEAVE_AS_CREATOR, CANNOT_KICK_CREATOR,
)

logger = logging.getLogger(__name__)

THROTTLE_SCOPE_AUTH = 'auth'
THROTTLE_SCOPE_LOGIN = 'login'


def get_optimized_quote_queryset(queryset, user):
    """Apply annotations and prefetches to avoid N+1 queries on QuoteSerializer."""
    user_witnessed = QuoteWitness.objects.filter(quote=OuterRef('pk'), witness=user)
    user_liked = QuoteLike.objects.filter(quote=OuterRef('pk'), user=user)
    user_saved = SavedQuote.objects.filter(quote=OuterRef('pk'), user=user)
    user_hidden = HiddenQuote.objects.filter(quote=OuterRef('pk'), user=user)
    user_guessed = QuoteGuess.objects.filter(quote=OuterRef('pk'), user=user)

    return queryset.annotate(
        annotated_witness_count=Count('witnesses', distinct=True),
        annotated_like_count=Count('likes', distinct=True),
        annotated_is_witnessed=Exists(user_witnessed),
        annotated_is_liked=Exists(user_liked),
        annotated_is_saved=Exists(user_saved),
        annotated_is_hidden=Exists(user_hidden),
        annotated_has_guessed=Exists(user_guessed),
    ).select_related(
        'author', 'quoted_user'
    ).prefetch_related(
        'witnesses__witness',
        Prefetch(
            'guesses',
            queryset=QuoteGuess.objects.filter(user=user).select_related('guessed_user'),
            to_attr='user_guesses',
        ),
    )


def get_visible_quote_or_404(user, quote_id):
    """
    Return the quote if the user is a member of its group (or is author/quoted_user),
    and neither party is blocked.
    """
    blocked_ids = user.get_all_blocked_user_ids()
    user_group_ids = GroupMembership.objects.filter(user=user).values_list('group_id', flat=True)
    qs = (
        Quote.objects.filter(is_active=True)
        .filter(
            Q(group__in=user_group_ids) | Q(author=user) | Q(quoted_user=user)
        )
        .exclude(author__id__in=blocked_ids)
        .exclude(quoted_user__id__in=blocked_ids)
    )
    return get_object_or_404(qs, id=quote_id)


class OptimizedQuoteViewMixin:
    """Mixin that caches request-level data in serializer context for QuoteSerializer."""

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            now = timezone.now()
            used = QuoteGuess.objects.filter(
                user=user, skipped=True,
                created_at__gte=now - timedelta(days=7),
            ).count()
            context['remaining_skips'] = max(settings.QUOTE_GUESS_MAX_SKIPS_PER_WEEK - used, 0)
        return context


def get_optimized_user_queryset(queryset, current_user=None):
    """Annotate User querysets with counts."""
    qs = queryset.annotate(
        annotated_quotes_posted=Count(
            'posted_quotes', filter=Q(posted_quotes__is_active=True), distinct=True,
        ),
        annotated_quotes_received=Count(
            'quotes_about_me', filter=Q(quotes_about_me__is_active=True), distinct=True,
        ),
    )
    return qs


class StandardResultsPagination(PageNumberPagination):
    """Standard pagination configuration"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@extend_schema(
    summary="Register a new user",
    request=UserRegistrationSerializer,
    responses={201: RegisterResponseSerializer},
    tags=["auth"],
)
class RegisterView(generics.CreateAPIView):
    """User registration endpoint"""
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = THROTTLE_SCOPE_AUTH

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        ver, code = EmailVerification.create_for(user)
        transaction.on_commit(lambda: send_verification_email(user, code))
        return Response({
            'user': UserSerializer(user).data,
            'message': 'User created successfully. Verification code sent to email.'
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Verify email address",
    description=(
        "Verify a user's email address using the 6-digit code sent to their inbox."
        "Returns JWT tokens on success so the user is logged in immediately."
    ),
    request=VerifyEmailSerializer,
    responses={
        200: VerifyEmailResponseSerializer,
        400: DetailResponseSerializer,
    },
    tags=["auth"],
)
class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = THROTTLE_SCOPE_AUTH

    def post(self, request):
        s = VerifyEmailSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = normalize_email(s.validated_data['email'])
        code = s.validated_data['code']

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Don’t leak existence
            return api_error(VERIFICATION_CODE_INVALID, "Invalid or expired code.", status.HTTP_400_BAD_REQUEST)

        ver = (
            EmailVerification.objects
            .filter(user=user, used_at__isnull=True)
            .order_by('-created_at')
            .first()
        )
        if not ver or not ver.is_valid() or not ver.matches(code):
            return api_error(VERIFICATION_CODE_INVALID, "Invalid or expired code.", status.HTTP_400_BAD_REQUEST)

        ver.used_at = timezone.now()
        ver.save(update_fields=['used_at'])

        if not getattr(user, "is_email_verified", False):
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])

        # NOTE: We do not blacklist pre-existing refresh tokens here. Currently
        # this is safe because tokens are only ever issued *after* successful
        # verification (this response). If a future code path issues tokens
        # before verification (e.g. social login, admin-created accounts), this
        # should blacklist outstanding tokens before issuing fresh ones —
        # mirroring the pattern in PasswordResetConfirmView.
        refresh = RefreshToken.for_user(user)
        return Response({
            "detail": "Email verified.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_200_OK)


@extend_schema(
    summary="Resend email verification code",
    request=ResendVerificationSerializer,
    responses={200: DetailResponseSerializer},
    tags=["auth"],
)
class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = THROTTLE_SCOPE_AUTH

    def post(self, request):
        s = ResendVerificationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = normalize_email(s.validated_data['email'])

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Silent success to avoid enumeration
            return Response({"detail": "If an account exists, a code has been sent."}, status=status.HTTP_200_OK)

        if user.is_email_verified:
            return api_error(EMAIL_ALREADY_VERIFIED, "Email already verified.", status.HTTP_400_BAD_REQUEST)

        ver, code = EmailVerification.create_for(user)
        transaction.on_commit(lambda: send_verification_email(user, code))
        return Response({"detail": "Verification code sent."}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Request password reset",
    description="Request a password reset code to be sent to the provided email address.",
    request=PasswordResetRequestSerializer,
    responses={200: DetailResponseSerializer},
    tags=["auth"],
)
class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = THROTTLE_SCOPE_AUTH

    def post(self, request):
        s = PasswordResetRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = normalize_email(s.validated_data['email'])

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Silent success to avoid user enumeration
            return Response({"detail": "If an account exists, a reset code has been sent."}, status=status.HTTP_200_OK)

        # Prevent email flooding: if the user already has a valid, unused reset
        # code, silently succeed without sending another email. A new code will
        # only be issued once the existing one expires, is used, or is exhausted.
        already_active = PasswordReset.objects.filter(
            user=user,
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
            failed_attempts__lt=PasswordReset.MAX_FAILED_ATTEMPTS,
        ).exists()

        if not already_active:
            reset, code = PasswordReset.create_for(user)
            transaction.on_commit(lambda: send_password_reset_email(user, code))

        return Response({"detail": "If an account exists, a reset code has been sent."}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Confirm password reset",
    description="Confirm password reset using the code received via email and set a new password.",
    request=PasswordResetConfirmSerializer,
    responses={
        200: DetailResponseSerializer,
        400: DetailResponseSerializer,
    },
    tags=["auth"],
)
class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = THROTTLE_SCOPE_AUTH

    def post(self, request):
        s = PasswordResetConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = normalize_email(s.validated_data['email'])
        code = s.validated_data['code']
        new_password = s.validated_data['new_password']

        # Resolve user first, so we check only their most recent reset,
        # avoiding cross-user iteration and brute-force enumeration.
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return api_error(RESET_CODE_INVALID, "Invalid or expired code.", status.HTTP_400_BAD_REQUEST)

        reset = PasswordReset.objects.filter(
            user=user,
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
            failed_attempts__lt=PasswordReset.MAX_FAILED_ATTEMPTS,
        ).order_by('-created_at').first()

        if not reset:
            return api_error(RESET_CODE_INVALID, "Invalid or expired code.", status.HTTP_400_BAD_REQUEST)

        if not reset.matches(code):
            reset.failed_attempts = F('failed_attempts') + 1
            reset.save(update_fields=['failed_attempts'])
            return api_error(RESET_CODE_INVALID, "Invalid or expired code.", status.HTTP_400_BAD_REQUEST)

        matched_reset = reset

        with transaction.atomic():
            matched_reset.used_at = timezone.now()
            matched_reset.save(update_fields=['used_at'])

            user.set_password(new_password)
            user.save(update_fields=['password'])

            # Invalidate all outstanding JWT sessions so an attacker holding a
            # live refresh token cannot retain access after the owner resets.
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            tokens = OutstandingToken.objects.filter(user=user)
            BlacklistedToken.objects.bulk_create(
                [BlacklistedToken(token=t) for t in tokens],
                ignore_conflicts=True,
            )

        return Response({"detail": "Password reset successfully."}, status=status.HTTP_200_OK)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT login endpoint"""
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = THROTTLE_SCOPE_LOGIN


class ProfileView(generics.RetrieveUpdateAPIView):
    """User profile endpoint"""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserSearchView(generics.ListAPIView):
    """Search users by username or display name"""
    serializer_class = PublicUserListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'display_name']

    def get_queryset(self):
        user = self.request.user
        blocked_ids = user.get_all_blocked_user_ids()
        qs = User.objects.exclude(id=user.id).exclude(id__in=blocked_ids)
        return get_optimized_user_queryset(qs, current_user=user)


class UserDetailView(OptimizedQuoteViewMixin, generics.RetrieveAPIView):
    """Retrieve public details about any user"""
    serializer_class = PublicUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    lookup_url_kwarg = 'user_id'

    def get_queryset(self):
        """Allow access to all active users except blocked"""
        blocked_ids = self.request.user.get_all_blocked_user_ids()
        return User.objects.filter(is_active=True).exclude(id__in=blocked_ids)

    def get_object(self):
        """Get user object with optimized queries"""
        user_id = self.kwargs.get('user_id')

        try:
            user = get_optimized_user_queryset(
                self.get_queryset().prefetch_related(
                    'posted_quotes',
                    Prefetch(
                        'quotes_about_me',
                        queryset=Quote.objects.filter(is_active=True)
                    )
                ),
                current_user=self.request.user,
            ).get(id=user_id)

            return user

        except User.DoesNotExist:
            raise NotFound("User not found.")

    def get_serializer_context(self):
        """Add request to serializer context"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class UserPostedQuotesListView(OptimizedQuoteViewMixin, generics.ListAPIView):
    """List quotes posted by a specific user (where they are the author)"""
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    lookup_url_kwarg = 'user_id'

    def get_queryset(self):
        user = self.request.user
        user_id = self.kwargs.get(self.lookup_url_kwarg)
        blocked_ids = user.get_all_blocked_user_ids()

        if user_id in blocked_ids:
            raise NotFound("User not found.")

        target_user = get_object_or_404(User, id=user_id, is_active=True)

        if target_user != user:
            # Must share at least one group
            user_group_ids = set(GroupMembership.objects.filter(user=user).values_list('group_id', flat=True))
            target_group_ids = set(GroupMembership.objects.filter(user=target_user).values_list('group_id', flat=True))
            if not user_group_ids & target_group_ids:
                raise exceptions.PermissionDenied("You can only view quotes of group members.")

        user_group_ids = GroupMembership.objects.filter(user=user).values_list('group_id', flat=True)

        qs = (
            Quote.objects
            .filter(author=target_user, is_active=True, group__in=user_group_ids)
            .exclude(hidden_quote_links__user=user)
            .exclude(quoted_user__id__in=blocked_ids)
            .order_by('-created_at')
        )

        if target_user != user:
            guessed_quote_ids = QuoteGuess.objects.filter(user=user).values_list('quote_id', flat=True)
            qs = qs.filter(
                Q(quoted_user__isnull=True) | Q(id__in=guessed_quote_ids)
            )

        return get_optimized_quote_queryset(qs, user)


class UserReceivedQuotesListView(OptimizedQuoteViewMixin, generics.ListAPIView):
    """List quotes about a specific user (where they are the quoted_user)"""
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    lookup_url_kwarg = 'user_id'

    def get_queryset(self):
        user = self.request.user
        user_id = self.kwargs.get(self.lookup_url_kwarg)
        blocked_ids = user.get_all_blocked_user_ids()

        if user_id in blocked_ids:
            raise NotFound("User not found.")

        target_user = get_object_or_404(User, id=user_id, is_active=True)

        if target_user != user:
            user_group_ids = set(GroupMembership.objects.filter(user=user).values_list('group_id', flat=True))
            target_group_ids = set(GroupMembership.objects.filter(user=target_user).values_list('group_id', flat=True))
            if not user_group_ids & target_group_ids:
                raise exceptions.PermissionDenied("You can only view quotes of group members.")

        user_group_ids = GroupMembership.objects.filter(user=user).values_list('group_id', flat=True)

        qs = (
            Quote.objects
            .filter(quoted_user=target_user, is_active=True, group__in=user_group_ids)
            .exclude(hidden_quote_links__user=user)
            .exclude(author__id__in=blocked_ids)
            .order_by('-created_at')
        )

        if target_user != user:
            guessed_quote_ids = QuoteGuess.objects.filter(user=user).values_list('quote_id', flat=True)
            qs = qs.filter(
                Q(author=user) | Q(id__in=guessed_quote_ids)
            )

        return get_optimized_quote_queryset(qs, user)


class BlockUserView(APIView):
    """
    Block or unblock a user.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Block a user",
        responses={201: DetailResponseSerializer, 200: DetailResponseSerializer},
        tags=["users"],
    )
    @transaction.atomic
    def post(self, request, user_id):
        """Block a user."""
        if user_id == request.user.id:
            return api_error(CANNOT_BLOCK_SELF, "You cannot block yourself.", status.HTTP_400_BAD_REQUEST)

        target_user = get_object_or_404(User, id=user_id, is_active=True)

        _, created = Block.objects.get_or_create(blocker=request.user, blocked=target_user)

        if not created:
            return Response({'detail': 'User is already blocked.'}, status=status.HTTP_200_OK)

        # Delete pending unprocessed events between these users
        Event.objects.filter(
            Q(actor=request.user, recipient=target_user) |
            Q(actor=target_user, recipient=request.user),
            processed_at__isnull=True,
        ).delete()

        return Response({'detail': 'User blocked.'}, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Unblock a user",
        responses={200: DetailResponseSerializer},
        tags=["users"],
    )
    @transaction.atomic
    def delete(self, request, user_id):
        """Unblock a user."""
        target_user = get_object_or_404(User, id=user_id, is_active=True)

        deleted_count, _ = Block.objects.filter(blocker=request.user, blocked=target_user).delete()

        if deleted_count:
            return Response({'detail': 'User unblocked.'}, status=status.HTTP_200_OK)
        return Response({'detail': 'User was not blocked.'}, status=status.HTTP_200_OK)


class BlockedUsersListView(generics.ListAPIView):
    """List users blocked by the current user."""
    serializer_class = PublicUserListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        user = self.request.user
        return get_optimized_user_queryset(user.get_blocked_users())


class QuoteListCreateView(OptimizedQuoteViewMixin, generics.ListCreateAPIView):
    """List and create quotes"""
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        user = self.request.user
        blocked_ids = user.get_all_blocked_user_ids()
        group_id = self.request.query_params.get('group_id')
        user_group_ids = GroupMembership.objects.filter(user=user).values_list('group_id', flat=True)

        qs = Quote.objects.filter(is_active=True)
        if group_id:
            if int(group_id) not in list(user_group_ids):
                return Quote.objects.none()
            qs = qs.filter(group_id=group_id)
        else:
            qs = qs.filter(group__in=user_group_ids)

        qs = (
            qs
            .exclude(hidden_quote_links__user=user)
            .exclude(author__id__in=blocked_ids)
            .exclude(quoted_user__id__in=blocked_ids)
            .distinct()
            .order_by("-created_at")
        )
        return get_optimized_quote_queryset(qs, user)

    def perform_create(self, serializer):
        quote = serializer.save()

        if quote.quoted_user and quote.quoted_user != quote.author:
            emit_event('new_quote', actor=quote.author, recipient=quote.quoted_user, quote=quote)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='year',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Optional filter by creation year.',
            required=False
        ),
        OpenApiParameter(
            name='month',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Optional filter by creation month (1–12).',
            required=False
        ),
    ],
    responses={200: QuoteSerializer(many=True)}
)
class QuoteSearchView(OptimizedQuoteViewMixin, generics.ListAPIView):
    """
    Search quotes by text, quoted user username, display name, or quoted_name.
    Supports optional filtering by year and month.

    For quotes that are guessable by the requesting user (not yet guessed,
    user is not the author, and guess options exist), only text matches are
    returned to avoid leaking attribution through search.
    """
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        user = self.request.user
        blocked_ids = user.get_all_blocked_user_ids()
        user_group_ids = GroupMembership.objects.filter(user=user).values_list('group_id', flat=True)

        qs = (
            Quote.objects
            .filter(is_active=True)
            .filter(group__in=user_group_ids)
            .exclude(hidden_quote_links__user=user)
            .exclude(author__id__in=blocked_ids)
            .exclude(quoted_user__id__in=blocked_ids)
        )

        # Custom filters (not handled by SearchFilter)
        year = self.request.query_params.get('year')
        month = self.request.query_params.get('month')

        if year:
            try:
                year = int(year)
            except ValueError:
                raise ValidationError({'year': 'Must be a valid integer.'})
            qs = qs.filter(created_at__year=year)

        if month:
            try:
                month = int(month)
            except ValueError:
                raise ValidationError({'month': 'Must be a valid integer.'})
            qs = qs.filter(created_at__month=month)

        search = self.request.query_params.get('search', '').strip()
        if not search:
            return qs.none()

        # Attribution fields match (author name/username, quoted user display name/username, quoted_name)
        attribution_q = (
            Q(quoted_name__icontains=search)
            | Q(quoted_user__username__icontains=search)
            | Q(quoted_user__display_name__icontains=search)
        )
        text_q = Q(text__icontains=search)

        # IDs of quotes this user has already guessed
        guessed_quote_ids = QuoteGuess.objects.filter(
            user=user
        ).values_list('quote_id', flat=True)

        # A quote is guessable if: has a quoted_user, user is not the author,
        # user is not the quoted_user, and user hasn't guessed yet.
        guessable_q = (
            Q(quoted_user__isnull=False)
            & ~Q(author=user)
            & ~Q(quoted_user=user)
            & ~Q(id__in=guessed_quote_ids)
        )

        # Use | instead of .union() to preserve annotation support
        combined = (
            qs.filter(~guessable_q).filter(text_q | attribution_q)
            | qs.filter(guessable_q).filter(text_q)
        )
        return get_optimized_quote_queryset(combined.distinct(), user)


class QuoteDetailView(OptimizedQuoteViewMixin, generics.RetrieveUpdateDestroyAPIView):
    """Quote detail view"""
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        blocked_ids = user.get_all_blocked_user_ids()
        user_group_ids = GroupMembership.objects.filter(user=user).values_list('group_id', flat=True)

        qs = (
            Quote.objects
            .filter(is_active=True)
            .filter(
                Q(group__in=user_group_ids) | Q(author=user) | Q(quoted_user=user)
            )
            .exclude(author__id__in=blocked_ids)
            .exclude(quoted_user__id__in=blocked_ids)
            .distinct()
        )
        return get_optimized_quote_queryset(qs, user)

    def perform_update(self, serializer):
        from django.conf import settings
        from django.utils import timezone
        quote = self.get_object()
        if quote.author != self.request.user:
            raise exceptions.PermissionDenied("You can only edit your own quotes")
        if timezone.now() - quote.created_at > settings.QUOTE_EDIT_WINDOW:
            raise exceptions.PermissionDenied("Quotes can no longer be edited after 15 minutes")
        serializer.save()

    def perform_destroy(self, instance):
        # Only allow author to delete
        if instance.author != self.request.user:
            raise exceptions.PermissionDenied("You can only delete your own quotes")
        instance.is_active = False
        instance.save()


@extend_schema(
    summary="Witness or unwitness a quote",
    responses={200: WitnessResponseSerializer},
    tags=["quotes"],
)
class WitnessQuoteView(APIView):
    """Witness/unwitness a quote"""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_visible_quote_or_404(request.user, quote_id)

        witness, created = QuoteWitness.objects.get_or_create(
            quote=quote,
            witness=request.user,
        )

        if created:
            if quote.author != request.user:
                emit_event('quote_witnessed', actor=request.user, recipient=quote.author, quote=quote)
            return Response({
                'message': 'Quote witnessed',
                'witness': QuoteWitnessSerializer(witness).data
            })
        else:
            witness.delete()
            return Response({'message': 'Quote unwitnessed'})


@extend_schema(
    summary="Like or unlike a quote",
    responses={200: MessageResponseSerializer},
    tags=["quotes"],
)
class LikeQuoteView(APIView):
    """Like/unlike a quote"""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_visible_quote_or_404(request.user, quote_id)

        like, created = QuoteLike.objects.get_or_create(
            quote=quote,
            user=request.user
        )

        if created:
            if quote.author != request.user:
                emit_event('quote_liked', actor=request.user, recipient=quote.author, quote=quote)

            return Response({'message': 'Quote liked'})
        else:
            like.delete()
            return Response({'message': 'Quote unliked'})


class QuoteLikesListView(generics.ListAPIView):
    """List users who liked a specific quote"""
    serializer_class = PublicUserListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        quote_id = self.kwargs.get('quote_id')
        quote = get_visible_quote_or_404(self.request.user, quote_id)
        blocked_ids = self.request.user.get_all_blocked_user_ids()

        qs = User.objects.filter(
            liked_quotes__quote=quote
        ).exclude(id__in=blocked_ids).order_by('-liked_quotes__created_at')
        return get_optimized_user_queryset(qs, current_user=self.request.user)


class QuoteWitnessesListView(generics.ListAPIView):
    """List users who witnessed a specific quote"""
    serializer_class = PublicUserListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        quote_id = self.kwargs.get('quote_id')
        quote = get_visible_quote_or_404(self.request.user, quote_id)
        blocked_ids = self.request.user.get_all_blocked_user_ids()

        qs = User.objects.filter(
            witnessed_quotes__quote=quote
        ).exclude(id__in=blocked_ids).order_by('-witnessed_quotes__created_at')
        return get_optimized_user_queryset(qs, current_user=self.request.user)


@extend_schema(
    summary="Confirm or deny a quote attribution",
    request=QuoteRespondRequestSerializer,
    responses={200: QuoteWithMessageSerializer},
    tags=["quotes"],
)
class RespondToQuoteView(APIView):
    """
    Allow the quoted user to confirm or deny a quote attributed to them.

    POST with {"response": "confirmed"} or {"response": "denied"} or {"response": null}
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, quote_id):
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

        # Only the quoted user can respond
        if quote.quoted_user != request.user:
            raise exceptions.PermissionDenied("Only the quoted user can respond to this quote.")

        response_value = request.data.get('response')

        # Validate the response value
        valid_responses = ['confirmed', 'denied', None]
        if response_value not in valid_responses:
            return api_error(INVALID_QUOTE_RESPONSE, "Invalid response.", status.HTTP_400_BAD_REQUEST)

        quote.quoted_user_response = response_value
        quote.save(update_fields=['quoted_user_response'])

        # Notify the author when the quoted user responds (skip if clearing the response)
        if response_value is not None and quote.author != request.user:
            emit_event('quote_response', actor=request.user, recipient=quote.author, quote=quote)

        optimized_quote = get_optimized_quote_queryset(
            Quote.objects.filter(pk=quote.pk), request.user
        ).first()
        return Response({
            'message': 'Quote response updated.',
            'quote': QuoteSerializer(optimized_quote, context={'request': request}).data
        })


class SaveQuoteView(APIView):
    """
    Save / unsave a quote.

    POST   -> ensure quote is saved for the current user.
    DELETE -> ensure quote is not saved for the current user.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Save a quote",
        responses={201: DetailResponseSerializer, 200: DetailResponseSerializer},
        tags=["quotes"],
    )
    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_visible_quote_or_404(request.user, quote_id)

        saved, created = SavedQuote.objects.get_or_create(
            user=request.user,
            quote=quote,
        )

        if created:
            return Response(
                {'detail': 'Quote saved.'},
                status=status.HTTP_201_CREATED,
            )
        else:
            # Already saved; idempotent success
            return Response(
                {'detail': 'Quote already saved.'},
                status=status.HTTP_200_OK,
            )

    @extend_schema(
        summary="Unsave a quote",
        responses={200: DetailResponseSerializer},
        tags=["quotes"],
    )
    @transaction.atomic
    def delete(self, request, quote_id):
        quote = get_visible_quote_or_404(request.user, quote_id)

        deleted_count, _ = SavedQuote.objects.filter(
            user=request.user,
            quote=quote,
        ).delete()

        if deleted_count:
            return Response({'detail': 'Quote unsaved.'}, status=status.HTTP_200_OK)
        else:
            # Idempotent: already not saved
            return Response({'detail': 'Quote was not saved.'}, status=status.HTTP_200_OK)


class HideQuoteView(APIView):
    """
    Hide / unhide a quote.

    POST   -> ensure quote is hidden for the current user.
    DELETE -> ensure quote is not hidden for the current user.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Hide a quote",
        responses={201: DetailResponseSerializer, 200: DetailResponseSerializer},
        tags=["quotes"],
    )
    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_visible_quote_or_404(request.user, quote_id)

        hidden, created = HiddenQuote.objects.get_or_create(
            user=request.user,
            quote=quote,
        )

        if created:
            return Response(
                {'detail': 'Quote hidden.'},
                status=status.HTTP_201_CREATED,
            )
        else:
            # Already hidden; idempotent success
            return Response(
                {'detail': 'Quote already hidden.'},
                status=status.HTTP_200_OK,
            )

    @extend_schema(
        summary="Unhide a quote",
        responses={200: DetailResponseSerializer},
        tags=["quotes"],
    )
    @transaction.atomic
    def delete(self, request, quote_id):
        quote = get_visible_quote_or_404(request.user, quote_id)

        deleted_count, _ = HiddenQuote.objects.filter(
            user=request.user,
            quote=quote,
        ).delete()

        if deleted_count:
            return Response({'detail': 'Quote unhidden.'}, status=status.HTTP_200_OK)
        else:
            # Idempotent: already not hidden
            return Response({'detail': 'Quote was not hidden.'}, status=status.HTTP_200_OK)


class SavedQuoteListView(OptimizedQuoteViewMixin, generics.ListAPIView):
    """
    List the current user's saved quotes
    """
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        user = self.request.user
        blocked_ids = user.get_all_blocked_user_ids()

        qs = (
            Quote.objects
            .filter(
                saved_quote_links__user=user,
                is_active=True,
            )
            .exclude(author__id__in=blocked_ids)
            .exclude(quoted_user__id__in=blocked_ids)
            .order_by('-saved_quote_links__created_at')
            .distinct()
        )
        return get_optimized_quote_queryset(qs, user)


class HiddenQuoteListView(OptimizedQuoteViewMixin, generics.ListAPIView):
    """
    List the current user's hidden quotes
    """
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        user = self.request.user
        blocked_ids = user.get_all_blocked_user_ids()

        qs = (
            Quote.objects
            .filter(
                hidden_quote_links__user=user,
                is_active=True,
            )
            .exclude(author__id__in=blocked_ids)
            .exclude(quoted_user__id__in=blocked_ids)
            .order_by('-hidden_quote_links__created_at')
            .distinct()
        )
        return get_optimized_quote_queryset(qs, user)


class GuessableQuotesListView(OptimizedQuoteViewMixin, generics.ListAPIView):
    """
    List quotes the current user can guess on (and hasn't yet).
    """
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        user = self.request.user
        blocked_ids = user.get_all_blocked_user_ids()
        user_group_ids = GroupMembership.objects.filter(user=user).values_list('group_id', flat=True)

        guessed_quote_ids = QuoteGuess.objects.filter(user=user).values_list('quote_id', flat=True)

        qs = (
            Quote.objects
            .filter(
                is_active=True,
                quoted_user__isnull=False,
                group__in=user_group_ids,
            )
            .exclude(author=user)
            .exclude(quoted_user=user)
            .exclude(id__in=guessed_quote_ids)
            .exclude(hidden_quote_links__user=user)
            .exclude(author__id__in=blocked_ids)
            .exclude(quoted_user__id__in=blocked_ids)
            .order_by('-created_at')
            .distinct()
        )

        # Filter out quotes where there aren't enough other group members for guess options
        # (need at least 1 wrong-answer candidate besides quoted_user in the group)
        valid_qs = []
        for quote in qs:
            other_members = GroupMembership.objects.filter(
                group=quote.group
            ).exclude(user=user).exclude(user_id=quote.quoted_user_id).filter(
                user__is_active=True, user__is_email_verified=True
            ).exists()
            if other_members:
                valid_qs.append(quote.id)

        return get_optimized_quote_queryset(qs.filter(id__in=valid_qs), user)


class RespondableQuotesListView(OptimizedQuoteViewMixin, generics.ListAPIView):
    """
    List quotes the current user can respond to (confirm/deny) and hasn't yet.
    """
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        user = self.request.user
        blocked_ids = user.get_all_blocked_user_ids()

        qs = (
            Quote.objects
            .filter(
                is_active=True,
                quoted_user=user,  # Quotes about the current user
                quoted_user_response__isnull=True,  # No response yet
            )
            .exclude(hidden_quote_links__user=user)  # Not hidden
            .exclude(author__id__in=blocked_ids)  # Not from blocked users
            .order_by('-created_at')
        )
        return get_optimized_quote_queryset(qs, user)


@extend_schema(
    summary="Assign a user to a quote",
    request=QuoteAssignUserRequestSerializer,
    responses={200: QuoteSerializer},
    tags=["quotes"],
)
class QuoteAssignUserView(APIView):
    """
    Allow the author of a quote to replace a quoted_name with a quoted_user.
    The quoted_user must be a friend of the author.
    """
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

        # Only the author can assign a user
        if quote.author != request.user:
            raise exceptions.PermissionDenied("Only the author can assign a user to this quote.")

        # Quote must currently have a quoted_name (not already assigned to a user)
        if quote.quoted_user is not None:
            return api_error(QUOTE_ALREADY_HAS_USER, "This quote already has a quoted user.", status.HTTP_400_BAD_REQUEST)

        user_id = request.data.get('quoted_user_id')
        if not user_id:
            return api_error(FIELD_REQUIRED, "quoted_user_id is required.", status.HTTP_400_BAD_REQUEST)

        target_user = get_object_or_404(User, id=user_id, is_active=True)

        # Perform the swap.
        # Intentionally not gated by QUOTE_EDIT_WINDOW: assigning a quoted_user is
        # a one-way, non-reversible attribution action that doesn't alter the quote
        # text. The 15-minute window applies to text edits only.
        quote.quoted_user = target_user
        quote.quoted_name = None
        quote.save(update_fields=['quoted_user', 'quoted_name', 'updated_at'])

        if target_user != request.user:
            emit_event('new_quote', actor=request.user, recipient=target_user, quote=quote)

        optimized_quote = get_optimized_quote_queryset(
            Quote.objects.filter(pk=quote.pk), request.user
        ).first()
        return Response(
            QuoteSerializer(optimized_quote, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="List notifications",
    responses={200: NotificationSerializer(many=True)},
    tags=["notifications"],
)
class NotificationListView(generics.ListAPIView):
    """List user notifications.

    Groups are pre-built by the pipeline (one row per type/quote/friendship).
    Actor User objects are batch-fetched in one query per page and blocked
    actors are stripped in Python.  Groups where all actors are blocked are
    excluded from the response.
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return (
            self.request.user.notifications
            .select_related('quote', 'group_invite', 'group_invite__group')
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        items = page if page is not None else list(queryset)

        # Batch-fetch all actor User objects across the page in one query
        all_actor_ids = [uid for n in items for uid in n.actor_ids]
        actors_by_id = {u.id: u for u in User.objects.filter(id__in=all_actor_ids)}

        # Strip blocked actors; exclude groups where no visible actors remain
        blocked_ids = set(request.user.get_all_blocked_user_ids())
        visible = []
        for n in items:
            n._actors = [
                actors_by_id[i] for i in n.actor_ids
                if i in actors_by_id and i not in blocked_ids
            ]
            if n._actors:
                visible.append(n)

        if page is not None:
            serializer = self.get_serializer(visible, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(visible, many=True)
        return Response(serializer.data)


class DeviceTokenView(APIView):
    """Register or deregister an Expo push token for the authenticated user."""

    def get_permissions(self):
        # DELETE is intentionally open: the push token itself is the credential.
        # This allows the pending-deregistration retry queue on the client to fire
        # after a network-down logout, without requiring an active session.
        if self.request.method == 'DELETE':
            return []
        return [permissions.IsAuthenticated()]

    @extend_schema(
        summary="Register device push token",
        request=DeviceTokenSerializer,
        responses={201: DetailResponseSerializer, 200: DetailResponseSerializer},
    )
    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data['token']

        device_token, created = DeviceToken.objects.get_or_create(
            token=token,
            defaults={'user': request.user, 'is_active': True, 'last_refreshed_at': timezone.now()},
        )
        if not created:
            if device_token.user_id != request.user.id:
                logger.warning(
                    "DeviceToken ownership transfer: token %s from user %s to user %s",
                    token[:20],
                    device_token.user_id,
                    request.user.id,
                )
            if not device_token.is_active or device_token.user_id != request.user.id:
                device_token.user = request.user
                device_token.is_active = True
                device_token.last_refreshed_at = timezone.now()
                device_token.save(update_fields=['user', 'is_active', 'last_refreshed_at', 'updated_at'])

        return Response(
            {'detail': 'Device registered.'},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Deregister device push token",
        request=DeviceTokenSerializer,
        responses={204: None},
    )
    def delete(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data['token']

        if request.user and request.user.is_authenticated:
            # Authenticated path: hard-delete, verify ownership.
            deleted, _ = DeviceToken.objects.filter(user=request.user, token=token).delete()
            if not deleted:
                return api_error(NOT_FOUND, "Token not found.", status.HTTP_404_NOT_FOUND)
        else:
            # Unauthenticated path: pending-deregistration retry.
            # Deactivate by token value alone — ownership verified implicitly because
            # only the originating device knows the full token string.
            DeviceToken.objects.filter(token=token, is_active=True).update(is_active=False)

        return Response(status=status.HTTP_204_NO_CONTENT)


class TokenRefreshView(BaseTokenRefreshView):
    """
    Wraps simplejwt's TokenRefreshView to update last_refreshed_at on the specific
    device making the request. The client optionally passes `push_token` in the
    request body alongside `refresh`. Only that token's timestamp is updated —
    not all of the user's tokens — so a stale token on a logged-out device is
    not kept alive by activity on a different device.
    """
    def post(self, request, *args, **kwargs):
        push_token = request.data.get('push_token')
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and push_token:
            try:
                DeviceToken.objects.filter(token=push_token, is_active=True).update(
                    last_refreshed_at=timezone.now()
                )
            except Exception:
                pass  # Never let a push-token update break token refresh
        return response


@extend_schema(
    summary="Mark a notification as read",
    responses={200: MessageResponseSerializer},
    tags=["notifications"],
)
class MarkNotificationReadView(APIView):
    """Mark notification as read"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, notification_id):
        notification = get_object_or_404(
            Notification,
            id=notification_id,
            recipient=request.user
        )
        notification.mark_as_read()
        return Response({'message': 'Notification marked as read'})


@extend_schema(
    summary="Mark all notifications as read",
    responses={200: MarkAllReadResponseSerializer},
    tags=["notifications"],
)
class MarkAllNotificationsReadView(APIView):
    """Mark all notifications as read."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        qs = Notification.objects.filter(
            recipient=self.request.user,
            is_read=False,
        )
        count = qs.update(is_read=True)
        return Response(
            {
                'message': 'All notifications marked as read',
                'count': count,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Mark a notification as unread",
    responses={200: MessageResponseSerializer},
    tags=["notifications"],
)
class MarkNotificationUnreadView(APIView):
    """Mark notification as unread"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, notification_id):
        notification = get_object_or_404(
            Notification,
            id=notification_id,
            recipient=request.user
        )
        notification.mark_as_unread()
        return Response({'message': 'Notification marked as unread'})


@extend_schema(
    summary="Get unread notification count",
    responses={200: UnreadCountResponseSerializer},
    tags=["notifications"],
)
class UnreadNotificationCountView(APIView):
    """Return the count of unread notifications"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        blocked_ids = set(request.user.get_all_blocked_user_ids())
        unread = Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).values_list('actor_ids', flat=True)
        unread_count = sum(
            1 for actor_ids in unread
            if any(uid not in blocked_ids for uid in actor_ids)
        )
        return Response({'unread_count': unread_count})


@extend_schema(
    summary="Delete a notification",
    responses={204: None},
    tags=["notifications"],
)
class DeleteNotificationView(APIView):
    """Delete a single notification"""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, notification_id):
        notification = get_object_or_404(
            Notification,
            id=notification_id,
            recipient=request.user
        )
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(responses={201: QuoteGuessCreateResponseSerializer})
class QuoteGuessCreateView(generics.CreateAPIView):
    queryset = QuoteGuess.objects.all()
    serializer_class = QuoteGuessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guess = serializer.save()
        request.user.refresh_from_db(fields=['current_streak', 'longest_streak'])

        # Notify recipients on non-skip guesses (batched)
        if not guess.skipped:
            # Author sees all guesses
            if guess.quote.author != request.user:
                emit_event('quote_guessed', actor=request.user, recipient=guess.quote.author, quote=guess.quote)
            # Quoted user only sees correct guesses (people who identified them)
            if guess.correct and guess.quote.quoted_user and guess.quote.quoted_user != request.user:
                emit_event('you_were_guessed', actor=request.user, recipient=guess.quote.quoted_user, quote=guess.quote)

        response_serializer = QuoteGuessCreateResponseSerializer(guess, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class QuoteGuessesListView(generics.ListAPIView):
    """
    List all guesses for a specific quote.

    Only accessible to:
    - Users who have guessed on this quote
    - The author of the quote
    - The quoted user
    """
    serializer_class = QuoteGuessListItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_quote(self):
        quote_id = self.kwargs.get('quote_id')
        return get_object_or_404(Quote, id=quote_id, is_active=True)

    def check_access(self, quote):
        user = self.request.user

        # Author can view
        if quote.author_id == user.id:
            return True

        # Quoted user can view
        if quote.quoted_user_id == user.id:
            return True

        # Users who have guessed can view
        if QuoteGuess.objects.filter(quote=quote, user=user).exists():
            return True

        return False

    def get_queryset(self):
        quote = self.get_quote()

        if not self.check_access(quote):
            raise exceptions.PermissionDenied(
                "You must be the author, quoted user, or have guessed on this quote to view guesses."
            )

        blocked_ids = self.request.user.get_all_blocked_user_ids()

        return (
            QuoteGuess.objects
            .filter(quote=quote)
            .exclude(user__id__in=blocked_ids)
            .select_related('user', 'guessed_user')
            .order_by('-created_at')
        )


class RecentSearchView(APIView):
    """Get and create recent search items (users & quotes)"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List recent search items",
        parameters=[
            OpenApiParameter(name="kind", required=False, type=str, description="user | quote"),
            OpenApiParameter(name="limit", required=False, type=int, description="Max items (<=50). Default 10"),
        ],
        responses={200: RecentSearchItemSerializer(many=True)},
        tags=["recents"],
    )
    def get(self, request):
        kind = request.query_params.get("kind")
        try:
            limit = min(int(request.query_params.get("limit", 10)), 50)
        except ValueError:
            limit = 10

        qs = RecentSearchItem.objects.filter(owner=request.user).select_related(
            "user_target", "quote_target"
        )

        if kind == "user":
            qs = qs.filter(user_target__isnull=False)
        elif kind == "quote":
            qs = qs.filter(quote_target__isnull=False)

        items = list(qs.order_by("-touched_at")[:limit])
        data = RecentSearchItemSerializer(items, many=True).data
        # Filter out deleted targets (shouldn't happen due to FK, but safe)
        data = [d for d in data if d.get("data") is not None][:limit]
        return Response(data)

    @transaction.atomic
    @extend_schema(
        summary="Touch (upsert) a recent item",
        request=RecentSearchCreateSerializer,
        responses={204: OpenApiResponse(description="Updated")},
        tags=["recents"],
    )
    def post(self, request):
        ser = RecentSearchCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        target = ser.validated_data["_target"]
        query = ser.validated_data.get("query")
        now = timezone.now()
        user = request.user

        # Enforce visibility: users can only record searches for targets they can actually see.
        if isinstance(target, User):
            if target.pk != user.pk:
                blocked_ids = user.get_all_blocked_user_ids()
                user_group_ids = set(GroupMembership.objects.filter(user=user).values_list('group_id', flat=True))
                target_group_ids = set(GroupMembership.objects.filter(user=target).values_list('group_id', flat=True))
                if target.id in blocked_ids or not (user_group_ids & target_group_ids):
                    return api_error(NOT_FOUND, "Not found.", status.HTTP_404_NOT_FOUND)
        else:  # Quote
            blocked_ids = user.get_all_blocked_user_ids()
            user_group_ids = GroupMembership.objects.filter(user=user).values_list('group_id', flat=True)
            is_visible = Quote.objects.filter(
                pk=target.pk,
                is_active=True,
                group__in=user_group_ids,
            ).exclude(author__id__in=blocked_ids).exclude(quoted_user__id__in=blocked_ids).exists()
            if not is_visible:
                return api_error(NOT_FOUND, "Not found.", status.HTTP_404_NOT_FOUND)

        if isinstance(target, User):
            rec, created = RecentSearchItem.objects.select_for_update().get_or_create(
                owner=request.user, user_target=target,
                defaults={"touched_at": now, "last_query": query},
            )
        else:  # Quote
            rec, created = RecentSearchItem.objects.select_for_update().get_or_create(
                owner=request.user, quote_target=target,
                defaults={"touched_at": now, "last_query": query},
            )

        if not created:
            rec.touched_at = now
            if query is not None:
                rec.last_query = query
            rec.save(update_fields=["touched_at", "last_query"])

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Delete recent search items for a target",
        parameters=[
            OpenApiParameter(name="kind", required=True, type=str, description="user | quote"),
            OpenApiParameter(name="target_id", required=True, type=int, description="Target user or quote ID"),
        ],
        responses={204: OpenApiResponse(description="Deleted")},
        tags=["recents"],
    )
    def delete(self, request):
        kind = request.query_params.get("kind")
        target_id = request.query_params.get("target_id")
        if not kind or not target_id:
            return api_error(MISSING_PARAMETERS, "Query parameters 'kind' and 'target_id' are required.", status.HTTP_400_BAD_REQUEST)
        if kind not in ("user", "quote"):
            return api_error(INVALID_PARAMETER, "kind must be 'user' or 'quote'.", status.HTTP_400_BAD_REQUEST)

        qs = RecentSearchItem.objects.filter(owner=request.user)
        if kind == "user":
            qs = qs.filter(user_target_id=target_id)
        else:
            qs = qs.filter(quote_target_id=target_id)

        deleted, _ = qs.delete()
        if not deleted:
            raise NotFound("Recent search item not found.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReportQuoteView(APIView):
    """Report or unreport a quote."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Report a quote",
        request=ReportRequestSerializer,
        responses={
            201: ReportResponseSerializer,
            400: DetailResponseSerializer,
        },
        tags=["reports"],
    )
    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_visible_quote_or_404(request.user, quote_id)

        if quote.author_id == request.user.id:
            return api_error(CANNOT_REPORT_SELF, "You cannot report your own quote.", status.HTTP_400_BAD_REQUEST)

        if Report.objects.filter(reporter=request.user, reported_quote=quote).exists():
            return api_error(ALREADY_REPORTED, "You have already reported this quote.", status.HTTP_400_BAD_REQUEST)

        serializer = ReportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        snapshot = {
            'type': 'quote',
            'quote_id': quote.id,
            'text': quote.text,
            'context': quote.context,
            'author': {
                'id': quote.author.id,
                'username': quote.author.username,
                'display_name': quote.author.display_name,
            },
            'quoted_user': {
                'id': quote.quoted_user.id,
                'username': quote.quoted_user.username,
                'display_name': quote.quoted_user.display_name,
            } if quote.quoted_user else None,
            'quoted_name': quote.quoted_name,
            'created_at': quote.created_at.isoformat(),
        }

        report = Report.objects.create(
            reporter=request.user,
            reported_quote=quote,
            reason=serializer.validated_data['reason'],
            description=serializer.validated_data.get('description'),
            content_snapshot=snapshot,
        )

        return Response(
            ReportResponseSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Cancel a quote report",
        request=None,
        responses={
            204: OpenApiResponse(description="Report cancelled"),
            400: DetailResponseSerializer,
        },
        tags=["reports"],
    )
    @transaction.atomic
    def delete(self, request, quote_id):
        quote = get_visible_quote_or_404(request.user, quote_id)

        deleted_count, _ = Report.objects.filter(
            reporter=request.user,
            reported_quote=quote,
        ).delete()

        if not deleted_count:
            return api_error(REPORT_NOT_FOUND, "You have not reported this quote.", status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)


class ReportUserView(APIView):
    """Report or unreport a user."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Report a user",
        request=ReportRequestSerializer,
        responses={
            201: ReportResponseSerializer,
            400: DetailResponseSerializer,
        },
        tags=["reports"],
    )
    @transaction.atomic
    def post(self, request, user_id):
        target = get_object_or_404(User, id=user_id, is_active=True)

        if target.id == request.user.id:
            return api_error(CANNOT_REPORT_SELF, "You cannot report yourself.", status.HTTP_400_BAD_REQUEST)

        if Report.objects.filter(reporter=request.user, reported_user=target).exists():
            return api_error(ALREADY_REPORTED, "You have already reported this user.", status.HTTP_400_BAD_REQUEST)

        serializer = ReportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        snapshot = {
            'type': 'user',
            'user_id': target.id,
            'username': target.username,
            'display_name': target.display_name,
            'email': target.email,
            'bio': target.bio,
        }

        report = Report.objects.create(
            reporter=request.user,
            reported_user=target,
            reason=serializer.validated_data['reason'],
            description=serializer.validated_data.get('description'),
            content_snapshot=snapshot,
        )

        return Response(
            ReportResponseSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Cancel a user report",
        request=None,
        responses={
            204: OpenApiResponse(description="Report cancelled"),
            400: DetailResponseSerializer,
        },
        tags=["reports"],
    )
    @transaction.atomic
    def delete(self, request, user_id):
        target = get_object_or_404(User, id=user_id, is_active=True)

        deleted_count, _ = Report.objects.filter(
            reporter=request.user,
            reported_user=target,
        ).delete()

        if not deleted_count:
            return api_error(REPORT_NOT_FOUND, "You have not reported this user.", status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)


class GroupListCreateView(generics.ListCreateAPIView):
    """List user's groups / create a new group."""
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return GroupCreateSerializer
        return GroupSerializer

    def get_queryset(self):
        from django.db.models import Count
        user = self.request.user
        group_ids = GroupMembership.objects.filter(user=user).values_list('group_id', flat=True)
        return (
            Group.objects.filter(id__in=group_ids)
            .annotate(annotated_member_count=Count('memberships', distinct=True))
            .select_related('created_by')
            .order_by('name')
        )

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = GroupSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = GroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = Group.objects.create(
            name=serializer.validated_data['name'],
            created_by=request.user,
        )
        GroupMembership.objects.create(group=group, user=request.user)
        return Response(
            GroupSerializer(group, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class GroupDetailView(APIView):
    """Retrieve / rename (admin) / delete (admin) a group."""
    permission_classes = [permissions.IsAuthenticated]

    def _get_group_and_membership(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        membership = GroupMembership.objects.filter(group=group, user=request.user).first()
        if not membership:
            raise exceptions.PermissionDenied("You are not a member of this group.")
        return group, membership

    def get(self, request, group_id):
        from django.db.models import Count
        group = get_object_or_404(Group, id=group_id)
        if not GroupMembership.objects.filter(group=group, user=request.user).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")
        group.annotated_member_count = group.memberships.count()
        return Response(GroupSerializer(group, context={'request': request}).data)

    @transaction.atomic
    def patch(self, request, group_id):
        group, _ = self._get_group_and_membership(request, group_id)
        if group.created_by_id != request.user.id:
            return api_error(NOT_GROUP_ADMIN, "Only the group admin can rename the group.", status.HTTP_403_FORBIDDEN)
        serializer = GroupRenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group.name = serializer.validated_data['name']
        group.save(update_fields=['name', 'updated_at'])
        group.annotated_member_count = group.memberships.count()
        return Response(GroupSerializer(group, context={'request': request}).data)

    @transaction.atomic
    def delete(self, request, group_id):
        group, _ = self._get_group_and_membership(request, group_id)
        if group.created_by_id != request.user.id:
            return api_error(NOT_GROUP_ADMIN, "Only the group admin can delete the group.", status.HTTP_403_FORBIDDEN)
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GroupMembersListView(generics.ListAPIView):
    """List members of a group."""
    serializer_class = GroupMemberSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['user__username', 'user__display_name']

    def get_queryset(self):
        group_id = self.kwargs['group_id']
        group = get_object_or_404(Group, id=group_id)
        if not GroupMembership.objects.filter(group=group, user=self.request.user).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")
        return GroupMembership.objects.filter(group=group).select_related('user').order_by('joined_at')


class GroupKickMemberView(APIView):
    """Kick a member from a group (admin only)."""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def delete(self, request, group_id, user_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupMembership.objects.filter(group=group, user=request.user).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")
        if group.created_by_id != request.user.id:
            return api_error(NOT_GROUP_ADMIN, "Only the group admin can kick members.", status.HTTP_403_FORBIDDEN)
        if user_id == request.user.id:
            return api_error(CANNOT_KICK_CREATOR, "The group creator cannot be kicked.", status.HTTP_400_BAD_REQUEST)
        deleted, _ = GroupMembership.objects.filter(group=group, user_id=user_id).delete()
        if not deleted:
            return api_error(NOT_GROUP_MEMBER, "User is not a member of this group.", status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GroupLeaveView(APIView):
    """Leave a group."""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if group.created_by_id == request.user.id:
            return api_error(CANNOT_LEAVE_AS_CREATOR, "The creator cannot leave — delete the group instead.", status.HTTP_400_BAD_REQUEST)
        deleted, _ = GroupMembership.objects.filter(group=group, user=request.user).delete()
        if not deleted:
            return api_error(NOT_GROUP_MEMBER, "You are not a member of this group.", status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GroupInviteView(APIView):
    """Invite a user to a group (any member)."""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        if not GroupMembership.objects.filter(group=group, user=request.user).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")

        serializer = GroupInviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_user = serializer.validated_data['user_id']

        if GroupMembership.objects.filter(group=group, user=target_user).exists():
            return api_error(ALREADY_GROUP_MEMBER, "User is already a member of this group.", status.HTTP_400_BAD_REQUEST)

        if GroupInvite.objects.filter(group=group, invited_user=target_user, status='pending').exists():
            return api_error(INVITE_ALREADY_PENDING, "A pending invite already exists for this user.", status.HTTP_400_BAD_REQUEST)

        invite = GroupInvite.objects.create(
            group=group,
            invited_user=target_user,
            invited_by=request.user,
        )

        from djangoapp.notifications.notification_service import emit_event
        emit_event('group_invite', actor=request.user, recipient=target_user, group_invite=invite)

        return Response(
            GroupInviteSerializer(invite, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class GroupInviteListView(generics.ListAPIView):
    """List pending group invites received by the current user."""
    serializer_class = GroupInviteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return (
            GroupInvite.objects
            .filter(invited_user=self.request.user, status='pending')
            .select_related('group', 'group__created_by', 'invited_by')
            .order_by('-created_at')
        )


class GroupInviteRespondView(APIView):
    """Accept or decline a group invite."""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, invite_id):
        invite = get_object_or_404(GroupInvite, id=invite_id, invited_user=request.user, status='pending')

        serializer = GroupInviteRespondSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']

        from django.utils import timezone as tz
        invite.responded_at = tz.now()

        if action == 'accept':
            invite.status = 'accepted'
            invite.save(update_fields=['status', 'responded_at'])
            GroupMembership.objects.get_or_create(
                group=invite.group,
                user=request.user,
                defaults={'invited_by': invite.invited_by},
            )
            from djangoapp.notifications.notification_service import emit_event
            emit_event('group_invite_accepted', actor=request.user, recipient=invite.invited_by, group_invite=invite)
        else:
            invite.status = 'declined'
            invite.save(update_fields=['status', 'responded_at'])

        return Response(GroupInviteSerializer(invite, context={'request': request}).data)


class GroupInviteCancelView(APIView):
    """Cancel a sent invite (inviter or admin)."""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def delete(self, request, invite_id):
        invite = get_object_or_404(GroupInvite, id=invite_id, status='pending')
        group = invite.group
        is_inviter = invite.invited_by_id == request.user.id
        is_admin = group.created_by_id == request.user.id
        if not (is_inviter or is_admin):
            raise exceptions.PermissionDenied("You cannot cancel this invite.")
        invite.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    summary="Get app config",
    responses={200: AppConfigResponseSerializer},
    tags=["config"],
)
class AppConfigView(APIView):
    """Public endpoint returning the minimum supported app version and store URLs."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from djangoapp.yapify.models import AppVersionConfig
        config = AppVersionConfig.get_current()
        return Response({
            'minimum_version': config.minimum_version,
            'ios_store_url': config.ios_store_url,
            'android_store_url': config.android_store_url,
        })


class DeleteAccountView(APIView):
    """
    Permanently delete the authenticated user's account.

    Quotes posted by friends where this user is the quoted_user are preserved —
    their display_name is snapshotted into quoted_name so the quote remains
    readable. All other data (authored quotes, friendships, notifications,
    device tokens, etc.) is hard-deleted via CASCADE.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Delete account",
        description=(
            "Permanently deletes the authenticated user's account and all associated data. "
            "Quotes posted by friends where this user appears as the quoted user are preserved "
            "with their display name snapshotted, so friends' content is not lost."
        ),
        responses={204: OpenApiResponse(description="Account deleted")},
        tags=["auth"],
    )
    @transaction.atomic
    def delete(self, request):
        user = request.user
        # Snapshot the display_name onto any quotes where this user is the
        # quoted_user before the FK is nulled, so the quote stays meaningful.
        Quote.objects.filter(quoted_user=user).update(
            quoted_name=user.display_name,
            quoted_user=None,
        )
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
