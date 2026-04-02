# urls.py
from django.urls import path
from djangoapp.api import views
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView


urlpatterns = [
    # App config (public — version check + store URLs)
    path('config/', views.AppConfigView.as_view(), name='app-config'),

    # OpenAPI Schema download
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    # Redoc UI
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Authentication
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/login/', views.CustomTokenObtainPairView.as_view(), name='login'),
    path('auth/refresh/', views.TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/verify-email/', views.VerifyEmailView.as_view(), name='verify_email'),
    path('auth/resend-verification/', views.ResendVerificationView.as_view(), name='resend_verification'),
    path('auth/password-reset/', views.PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('auth/password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('auth/me/', views.DeleteAccountView.as_view(), name='delete_account'),

    # User profile
    path('profile/', views.ProfileView.as_view(), name='profile'),

    # Users
    path('users/search/', views.UserSearchView.as_view(), name='user_search'),
    path('users/<int:user_id>/', views.UserDetailView.as_view(), name='user-detail'),
    path('users/<int:user_id>/friends/', views.UserFriendsListView.as_view(), name='user-friends-list'),
    path('users/<int:user_id>/quotes/posted/', views.UserPostedQuotesListView.as_view(), name='user-posted-quotes'),
    path('users/<int:user_id>/quotes/received/', views.UserReceivedQuotesListView.as_view(), name='user-received-quotes'),

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

    # Blocking
    path('users/<int:user_id>/block/', views.BlockUserView.as_view(), name='block-user'),
    path('users/blocked/', views.BlockedUsersListView.as_view(), name='blocked-users-list'),

    # Reports
    path('quotes/<int:quote_id>/report/', views.ReportQuoteView.as_view(), name='quote-report'),
    path('users/<int:user_id>/report/', views.ReportUserView.as_view(), name='user-report'),

    # Quotes
    path('quotes/', views.QuoteListCreateView.as_view(), name='quote_list_create'),
    path('quotes/<int:pk>/', views.QuoteDetailView.as_view(), name='quote_detail'),
    path('quotes/<int:quote_id>/witness/', views.WitnessQuoteView.as_view(), name='witness_quote'),
    path('quotes/<int:quote_id>/like/', views.LikeQuoteView.as_view(), name='like_quote'),
    path('quotes/<int:quote_id>/respond/', views.RespondToQuoteView.as_view(), name='quote-respond'),
    path('quotes/<int:quote_id>/assign-user/', views.QuoteAssignUserView.as_view(), name='quote-assign-user'),
    path('quotes/<int:quote_id>/likes/', views.QuoteLikesListView.as_view(), name='quote-likes-list'),
    path('quotes/<int:quote_id>/witnesses/', views.QuoteWitnessesListView.as_view(), name='quote-witnesses-list'),
    path("quotes/search/", views.QuoteSearchView.as_view(), name="quote_search"),
    path('quotes/<int:quote_id>/save/', views.SaveQuoteView.as_view(), name='quote-save'),
    path('quotes/<int:quote_id>/hide/', views.HideQuoteView.as_view(), name='quote-hide'),
    path('quotes/saved/', views.SavedQuoteListView.as_view(), name='quote-saved-list'),
    path('quotes/hidden/', views.HiddenQuoteListView.as_view(), name='quote-hidden-list'),
    path('quotes/guessable/', views.GuessableQuotesListView.as_view(), name='quote-guessable-list'),
    path('quotes/respondable/', views.RespondableQuotesListView.as_view(), name='quote-respondable-list'),

    # Guesses
    path("guesses/create/", views.QuoteGuessCreateView.as_view(), name="quote-guess-create"),
    path("quotes/<int:quote_id>/guesses/", views.QuoteGuessesListView.as_view(), name="quote-guesses-list"),

    # Notifications
    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('notifications/read/', views.MarkAllNotificationsReadView.as_view(), name='mark_all_notifications_read'),
    path('notifications/unread-count/', views.UnreadNotificationCountView.as_view(), name='unread_notification_count'),
    path('notifications/<int:notification_id>/read/', views.MarkNotificationReadView.as_view(), name='mark_notification_read'),
    path('notifications/<int:notification_id>/unread/', views.MarkNotificationUnreadView.as_view(), name='mark_notification_unread'),
    path('notifications/<int:notification_id>/', views.DeleteNotificationView.as_view(), name='delete_notification'),

    # Devices
    path('devices/', views.DeviceTokenView.as_view(), name='device-tokens'),
]
