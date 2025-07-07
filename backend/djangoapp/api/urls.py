# urls.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Authentication
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/login/', views.CustomTokenObtainPairView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # User profile
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('users/search/', views.UserSearchView.as_view(), name='user_search'),

    # Friends
    path('friends/', views.FriendListView.as_view(), name='friend_list'),
    path('friends/requests/', views.FriendRequestListView.as_view(), name='friend_requests'),
    path('friends/send/', views.SendFriendRequestView.as_view(), name='send_friend_request'),
    path('friends/respond/<int:friendship_id>/', views.RespondToFriendRequestView.as_view(),
         name='respond_friend_request'),

    # Quotes
    path('quotes/', views.QuoteListCreateView.as_view(), name='quote_list_create'),
    path('quotes/<int:pk>/', views.QuoteDetailView.as_view(), name='quote_detail'),
    path('quotes/<int:quote_id>/witness/', views.WitnessQuoteView.as_view(), name='witness_quote'),
    path('quotes/<int:quote_id>/like/', views.LikeQuoteView.as_view(), name='like_quote'),

    # Notifications
    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:notification_id>/read/', views.MarkNotificationReadView.as_view(),
         name='mark_notification_read'),
]