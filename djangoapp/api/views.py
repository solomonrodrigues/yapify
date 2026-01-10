# views.py
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from rest_framework import generics, status, permissions, exceptions, filters
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.shortcuts import get_object_or_404
from django.db.models import Q, Max, Prefetch
from djangoapp.yapify.models import User, Friendship, Quote, QuoteWitness, QuoteLike, Notification, EmailVerification, \
    QuoteGuess, RecentSearchItem, SavedQuote, HiddenQuote
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
    ResendVerificationSerializer,
    VerifyEmailSerializer,
    QuoteGuessSerializer,
    RecentSearchItemSerializer,
    RecentSearchCreateSerializer,
)
from .utils import send_verification_email, normalize_email


class StandardResultsPagination(PageNumberPagination):
    """Standard pagination configuration"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class RegisterView(generics.CreateAPIView):
    """User registration endpoint"""
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            ver, code = EmailVerification.create_for(user)
            send_verification_email(user, code)
            return Response({
                'user': UserSerializer(user).data,
                'message': 'User created successfully. Verification code sent to email.'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        s = VerifyEmailSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = normalize_email(s.validated_data['email'])
        code = s.validated_data['code']

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Don’t leak existence
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)

        ver = (
            EmailVerification.objects
            .filter(user=user, used_at__isnull=True)
            .order_by('-created_at')
            .first()
        )
        if not ver or not ver.is_valid() or not ver.matches(code):
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)

        ver.used_at = timezone.now()
        ver.save(update_fields=['used_at'])

        if not getattr(user, "is_email_verified", False):
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])

        return Response({"detail": "Email verified."}, status=status.HTTP_200_OK)


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

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
            return Response({"detail": "Email already verified."}, status=status.HTTP_400_BAD_REQUEST)

        ver, code = EmailVerification.create_for(user)
        send_verification_email(user, code)
        return Response({"detail": "Verification code sent."}, status=status.HTTP_200_OK)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT login endpoint"""
    serializer_class = CustomTokenObtainPairSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    """User profile endpoint"""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserSearchView(generics.ListAPIView):
    """Search users by username or display name"""
    serializer_class = PublicUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'display_name']

    def get_queryset(self):
        return User.objects.exclude(id=self.request.user.id)


class FriendListView(generics.ListAPIView):
    """List and search user's friends"""
    serializer_class = PublicUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'display_name']

    def get_queryset(self):
        friends_queryset = self.request.user.get_friends()

        # Apply search if provided
        search_query = self.request.query_params.get('search', '')
        if search_query:
            friends_queryset = friends_queryset.filter(
                Q(username__icontains=search_query) |
                Q(display_name__icontains=search_query)
            )

        return friends_queryset


class RecentQuotedFriendsView(generics.ListAPIView):
    """List up to 5 most recent friends that the user has made quotes for"""
    serializer_class = PublicUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Get user's friends who have been quoted, ordered by most recent quote
        user_friends = self.request.user.get_friends()

        # Get friends that have been quoted by this user, ordered by most recent quote
        quoted_friends = user_friends.filter(
            quotes_about_me__author=self.request.user,
            quotes_about_me__is_active=True
        ).annotate(
            latest_quote_date=Max('quotes_about_me__created_at')
        ).order_by('-latest_quote_date')[:5]

        return quoted_friends


class UserFriendsListView(generics.ListAPIView):
    """
    Get a paginated list of another user's friends.
    """
    serializer_class = PublicUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'display_name']
    lookup_url_kwarg = 'user_id'

    def get_target_user(self):
        """
        Resolve the user whose friends we want to list.
        """
        user_id = self.kwargs.get(self.lookup_url_kwarg)

        try:
            return User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            raise NotFound("User not found.")

    def get_queryset(self):
        """
        Return friends of the target user, optionally filtered by search.
        """
        target_user = self.get_target_user()
        friends_queryset = target_user.get_friends()

        # Apply search if provided (same behaviour as FriendListView)
        search_query = self.request.query_params.get('search', '')
        if search_query:
            friends_queryset = friends_queryset.filter(
                Q(username__icontains=search_query) |
                Q(display_name__icontains=search_query)
            )

        return friends_queryset


class UserDetailView(generics.RetrieveAPIView):
    """Retrieve public details about any user"""
    serializer_class = PublicUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    lookup_url_kwarg = 'user_id'

    def get_queryset(self):
        """Allow access to all active users"""
        return User.objects.filter(is_active=True)

    def get_object(self):
        """Get user object with optimized queries"""
        user_id = self.kwargs.get('user_id')

        try:
            # Prefetch related quotes for efficiency
            user = self.get_queryset().prefetch_related(
                'posted_quotes',
                Prefetch(
                    'quotes_about_me',
                    queryset=Quote.objects.filter(is_active=True)
                )
            ).get(id=user_id)

            return user

        except User.DoesNotExist:
            raise NotFound("User not found.")

    def get_serializer_context(self):
        """Add request to serializer context"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class UserPostedQuotesListView(generics.ListAPIView):
    """List quotes posted by a specific user (where they are the author)"""
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    lookup_url_kwarg = 'user_id'

    def get_queryset(self):
        user_id = self.kwargs.get(self.lookup_url_kwarg)
        target_user = get_object_or_404(User, id=user_id, is_active=True)

        return (
            Quote.objects
            .filter(author=target_user, is_active=True)
            .exclude(hidden_quote_links__user=self.request.user)
            .order_by('-created_at')
        )


class UserReceivedQuotesListView(generics.ListAPIView):
    """List quotes about a specific user (where they are the quoted_user)"""
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    lookup_url_kwarg = 'user_id'

    def get_queryset(self):
        user_id = self.kwargs.get(self.lookup_url_kwarg)
        target_user = get_object_or_404(User, id=user_id, is_active=True)

        return (
            Quote.objects
            .filter(quoted_user=target_user, is_active=True)
            .exclude(hidden_quote_links__user=self.request.user)
            .order_by('-created_at')
        )


class FriendRequestListView(generics.ListAPIView):
    """List pending friend requests"""
    serializer_class = FriendshipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.request.user.get_pending_friend_requests()


class SendFriendRequestView(generics.CreateAPIView):
    """Send friend request"""
    serializer_class = FriendRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            friendship = serializer.save()

            # Create notification
            Notification.objects.create(
                recipient=friendship.receiver,
                sender=friendship.sender,
                notification_type='friend_request',
                title='New Friend Request',
                message=f'{friendship.sender.get_full_name()} sent you a friend request',
                friendship=friendship
            )

            return Response({
                'message': 'Friend request sent successfully',
                'friendship': FriendshipSerializer(friendship).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CancelFriendRequestView(APIView):
    """Cancel outgoing pending friend request."""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def delete(self, request, user_id, *args, **kwargs):
        friendship = Friendship.objects.select_for_update().filter(
            sender=request.user,
            receiver__id=user_id,
            status='pending'
        ).first()

        if not friendship:
            return Response(
                {'detail': 'No outgoing pending request to this user.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Clean up any related "friend_request" notifications
        Notification.objects.filter(
            friendship=friendship,
            notification_type='friend_request'
        ).delete()

        friendship.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnfriendView(APIView):
    """Unfriend (remove accepted friendship)."""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def delete(self, request, user_id, *args, **kwargs):
        friendship = Friendship.objects.select_for_update().filter(
            Q(sender=request.user, receiver__id=user_id) | Q(sender__id=user_id, receiver=request.user),
            status='accepted'
        ).first()

        if not friendship:
            return Response(
                {'detail': 'No accepted friendship found with this user.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Clean up any related "friend_accepted" notifications
        Notification.objects.filter(
            friendship=friendship,
            notification_type='friend_accepted'
        ).delete()

        friendship.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RespondToFriendRequestView(APIView):
    """Accept or reject friend request"""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, user_id):
        friendship = get_object_or_404(Friendship, sender_id=user_id, receiver=request.user)
        action = request.data.get('action')

        if action == 'accept':
            friendship.accept()

            # Create notification
            Notification.objects.create(
                recipient=friendship.sender,
                sender=friendship.receiver,
                notification_type='friend_accepted',
                title='Friend Request Accepted',
                message=f'{friendship.receiver.get_full_name()} accepted your friend request',
                friendship=friendship
            )

            return Response({
                'message': 'Friend request accepted',
                'friendship': FriendshipSerializer(friendship).data
            })

        elif action == 'reject':
            friendship.reject()
            return Response({
                'message': 'Friend request rejected',
                'friendship': FriendshipSerializer(friendship).data
            })

        return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)


class QuoteListCreateView(generics.ListCreateAPIView):
    """List and create quotes"""
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        friends = user.get_friends()

        # Get quotes from friends and public quotes
        return (
            Quote.objects
            .filter(
                Q(author__in=friends) |
                Q(author=user) |
                Q(quoted_user=user)
            )
            .filter(is_active=True)
            .exclude(hidden_quote_links__user=user)
            .distinct()
        )

    def perform_create(self, serializer):
        quote = serializer.save()

        # Notify only if quoted_user exists
        if quote.quoted_user and quote.quoted_user != quote.author:
            Notification.objects.create(
                recipient=quote.quoted_user,
                sender=quote.author,
                notification_type='new_quote',
                title='New Quote About You',
                message=f'{quote.author.get_full_name()} posted a quote about you',
                quote=quote
            )


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
class QuoteSearchView(generics.ListAPIView):
    """
    Search quotes by text, quoted user username, display name, or quoted_name.
    Supports optional filtering by year and month.
    """
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'text',
        'quoted_name',
        'quoted_user__username',
        'quoted_user__display_name'
    ]

    def get_queryset(self):
        user = self.request.user
        qs = (
            Quote.objects
            .filter(is_active=True)
            .exclude(hidden_quote_links__user=user)
        )

        # Custom filters (not handled by SearchFilter)
        year = self.request.query_params.get('year')
        month = self.request.query_params.get('month')

        if year:
            year = int(year)
            qs = qs.filter(created_at__year=year)

        if month:
            month = int(month)
            qs = qs.filter(created_at__month=month)

        return qs


class QuoteDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Quote detail view"""
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Quote.objects.filter(is_active=True)

    def perform_update(self, serializer):
        # Only allow author to update
        if self.get_object().author != self.request.user:
            raise exceptions.PermissionDenied("You can only edit your own quotes")
        serializer.save()

    def perform_destroy(self, instance):
        # Only allow author to delete
        if instance.author != self.request.user:
            raise exceptions.PermissionDenied("You can only delete your own quotes")
        instance.is_active = False
        instance.save()


class WitnessQuoteView(APIView):
    """Witness/unwitness a quote"""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

        witness, created = QuoteWitness.objects.get_or_create(
            quote=quote,
            witness=request.user,
        )

        if created:
            # Create notification
            if quote.author != request.user:
                Notification.objects.create(
                    recipient=quote.author,
                    sender=request.user,
                    notification_type='quote_witnessed',
                    title='Quote Witnessed',
                    message=f'{request.user.get_full_name()} witnessed your quote',
                    quote=quote
                )
            return Response({
                'message': 'Quote witnessed',
                'witness': QuoteWitnessSerializer(witness).data
            })
        else:
            witness.delete()
            return Response({'message': 'Quote unwitnessed'})


class LikeQuoteView(APIView):
    """Like/unlike a quote"""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

        like, created = QuoteLike.objects.get_or_create(
            quote=quote,
            user=request.user
        )

        if created:
            # Create notification
            if quote.author != request.user:
                Notification.objects.create(
                    recipient=quote.author,
                    sender=request.user,
                    notification_type='quote_liked',
                    title='Quote Liked',
                    message=f'{request.user.get_full_name()} liked your quote',
                    quote=quote
                )

            return Response({'message': 'Quote liked'})
        else:
            like.delete()
            return Response({'message': 'Quote unliked'})


class QuoteLikesListView(generics.ListAPIView):
    """List users who liked a specific quote"""
    serializer_class = PublicUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        quote_id = self.kwargs.get('quote_id')
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

        return User.objects.filter(
            liked_quotes__quote=quote
        ).order_by('-liked_quotes__created_at')


class QuoteWitnessesListView(generics.ListAPIView):
    """List users who witnessed a specific quote"""
    serializer_class = PublicUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        quote_id = self.kwargs.get('quote_id')
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

        return User.objects.filter(
            witnessed_quotes__quote=quote
        ).order_by('-witnessed_quotes__created_at')


class SaveQuoteView(APIView):
    """
    Save / unsave a quote.

    POST   -> ensure quote is saved for the current user.
    DELETE -> ensure quote is not saved for the current user.
    """
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

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

    @transaction.atomic
    def delete(self, request, quote_id):
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

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

    @transaction.atomic
    def post(self, request, quote_id):
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

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

    @transaction.atomic
    def delete(self, request, quote_id):
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)

        deleted_count, _ = HiddenQuote.objects.filter(
            user=request.user,
            quote=quote,
        ).delete()

        if deleted_count:
            return Response({'detail': 'Quote unhidden.'}, status=status.HTTP_200_OK)
        else:
            # Idempotent: already not hidden
            return Response({'detail': 'Quote was not hidden.'}, status=status.HTTP_200_OK)


class SavedQuoteListView(generics.ListAPIView):
    """
    List the current user's saved quotes
    """
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        user = self.request.user

        return (
            Quote.objects
            .filter(
                saved_quote_links__user=user,
                is_active=True,
            )
            .order_by('-saved_quote_links__created_at')
            .distinct()
        )


class HiddenQuoteListView(generics.ListAPIView):
    """
    List the current user's hidden quotes
    """
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        user = self.request.user

        return (
            Quote.objects
            .filter(
                hidden_quote_links__user=user,
                is_active=True,
            )
            .order_by('-hidden_quote_links__created_at')
            .distinct()
        )


class NotificationListView(generics.ListAPIView):
    """List user notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.request.user.notifications.all()


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


class MarkAllNotificationsReadView(APIView):
    """Mark all notifications as read."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        qs = Notification.objects.filter(
            recipient=self.request.user,
            is_read=False,
        )
        count = qs.count()
        for n in qs:
            n.mark_as_read()
        return Response(
            {
                'message': 'All notifications marked as read',
                'count': count,
            },
            status=status.HTTP_200_OK,
        )


class QuoteGuessCreateView(generics.CreateAPIView):
    queryset = QuoteGuess.objects.all()
    serializer_class = QuoteGuessSerializer
    permission_classes = [permissions.IsAuthenticated]


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
