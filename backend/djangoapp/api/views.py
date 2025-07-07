# views.py
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth import get_user_model
from .models import User, Friendship, Quote, QuoteWitness, QuoteLike, Notification
from .serializers import (
    UserRegistrationSerializer, UserSerializer, FriendshipSerializer,
    FriendRequestSerializer, QuoteSerializer, QuoteWitnessSerializer,
    QuoteLikeSerializer, NotificationSerializer, CustomTokenObtainPairSerializer
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """User registration endpoint"""
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                'user': UserSerializer(user).data,
                'message': 'User created successfully'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
    """Search users by email or name"""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        query = self.request.query_params.get('q', '')
        if not query:
            return User.objects.none()

        return User.objects.filter(
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        ).exclude(id=self.request.user.id)[:20]


class FriendListView(generics.ListAPIView):
    """List user's friends"""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.request.user.get_friends()


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


class RespondToFriendRequestView(APIView):
    """Accept or reject friend request"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, friendship_id):
        friendship = get_object_or_404(Friendship, id=friendship_id, receiver=request.user)
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
        return Quote.objects.filter(
            Q(author__in=friends) | Q(quoted_user=user) | Q(is_public=True)
        ).filter(is_active=True).distinct()

    def perform_create(self, serializer):
        quote = serializer.save()

        # Create notification for quoted user
        if quote.quoted_user != quote.author:
            Notification.objects.create(
                recipient=quote.quoted_user,
                sender=quote.author,
                notification_type='new_quote',
                title='New Quote About You',
                message=f'{quote.author.get_full_name()} posted a quote about you',
                quote=quote
            )


class QuoteDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Quote detail view"""
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Quote.objects.filter(is_active=True)

    def perform_update(self, serializer):
        # Only allow author to update
        if self.get_object().author != self.request.user:
            raise permissions.PermissionDenied("You can only edit your own quotes")
        serializer.save()

    def perform_destroy(self, instance):
        # Only allow author to delete
        if instance.author != self.request.user:
            raise permissions.PermissionDenied("You can only delete your own quotes")
        instance.is_active = False
        instance.save()


class WitnessQuoteView(APIView):
    """Witness a quote"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, quote_id):
        quote = get_object_or_404(Quote, id=quote_id, is_active=True)
        is_witness = request.data.get('is_witness', True)
        comment = request.data.get('comment', '')

        # Check if user can witness this quote
        if request.user == quote.author:
            return Response({'error': 'You cannot witness your own quote'},
                            status=status.HTTP_400_BAD_REQUEST)

        if request.user == quote.quoted_user:
            return Response({'error': 'You cannot witness quotes about yourself'},
                            status=status.HTTP_400_BAD_REQUEST)

        witness, created = QuoteWitness.objects.get_or_create(
            quote=quote,
            witness=request.user,
            defaults={'is_witness': is_witness, 'comment': comment}
        )

        if not created:
            witness.is_witness = is_witness
            witness.comment = comment
            witness.save()

        # Create notification
        Notification.objects.create(
            recipient=quote.author,
            sender=request.user,
            notification_type='quote_witnessed',
            title='Quote Witnessed',
            message=f'{request.user.get_full_name()} witnessed your quote',
            quote=quote
        )

        return Response({
            'message': 'Quote witnessed successfully',
            'witness': QuoteWitnessSerializer(witness).data
        })


class LikeQuoteView(APIView):
    """Like/unlike a quote"""
    permission_classes = [permissions.IsAuthenticated]

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
