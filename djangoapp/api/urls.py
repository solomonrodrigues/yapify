# urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from djangoapp.api import views
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

from djangoapp.api.views import QuoteSearchView

urlpatterns = [
    # OpenAPI Schema download
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    # Redoc UI
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Authentication
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/login/', views.CustomTokenObtainPairView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/verify-email/', views.VerifyEmailView.as_view(), name='verify_email'),
    path('auth/resend-verification/', views.ResendVerificationView.as_view(), name='resend_verification'),

    # User profile
    path('profile/', views.ProfileView.as_view(), name='profile'),

    # Users
    path('users/search/', views.UserSearchView.as_view(), name='user_search'),
    path('users/<int:user_id>/', views.UserDetailView.as_view(), name='user-detail'),

    # Recent searches
    path("recents/", views.RecentSearchView.as_view(), name="recent-search"),

    # Friends
    path('friends/', views.FriendListView.as_view(), name='friend_list'),
    path('friends/recent-quoted/', views.RecentQuotedFriendsView.as_view(), name='recent_quoted_friends'),
    path('friends/requests/', views.FriendRequestListView.as_view(), name='friend_requests'),
    path('friends/send/', views.SendFriendRequestView.as_view(), name='send_friend_request'),
    path('friends/<int:user_id>/cancel/', views.CancelFriendRequestView.as_view(), name='cancel_friend_request'),
    path('friends/<int:user_id>/unfriend/', views.UnfriendView.as_view(), name='unfriend'),
    path('friends/<int:user_id>/respond/', views.RespondToFriendRequestView.as_view(),
         name='respond_friend_request'),

    # Quotes
    path('quotes/', views.QuoteListCreateView.as_view(), name='quote_list_create'),
    path('quotes/<int:pk>/', views.QuoteDetailView.as_view(), name='quote_detail'),
    path('quotes/<int:quote_id>/witness/', views.WitnessQuoteView.as_view(), name='witness_quote'),
    path('quotes/<int:quote_id>/like/', views.LikeQuoteView.as_view(), name='like_quote'),
    path("search/quotes/", QuoteSearchView.as_view(), name="search_quotes"),


    # Guesses
    path("guesses/create/", views.QuoteGuessCreateView.as_view(), name="quote-guess-create"),

    # Notifications
    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:notification_id>/read/', views.MarkNotificationReadView.as_view(),
         name='mark_notification_read'),
]
