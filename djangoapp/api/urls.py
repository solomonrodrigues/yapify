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
    path('users/<int:user_id>/quotes/posted/', views.UserPostedQuotesListView.as_view(), name='user-posted-quotes'),
    path('users/<int:user_id>/quotes/received/', views.UserReceivedQuotesListView.as_view(), name='user-received-quotes'),

    # Recent searches
    path("recents/", views.RecentSearchView.as_view(), name="recent-search"),

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

    # Groups
    path('groups/', views.GroupListCreateView.as_view(), name='group-list-create'),
    path('groups/invites/', views.GroupInviteListView.as_view(), name='group-invite-list'),
    path('groups/invites/<int:invite_id>/respond/', views.GroupInviteRespondView.as_view(), name='group-invite-respond'),
    path('groups/invites/<int:invite_id>/', views.GroupInviteCancelView.as_view(), name='group-invite-cancel'),
    path('groups/<int:group_id>/', views.GroupDetailView.as_view(), name='group-detail'),
    path('groups/<int:group_id>/members/', views.GroupMembersListView.as_view(), name='group-members'),
    path('groups/<int:group_id>/members/<int:user_id>/', views.GroupKickMemberView.as_view(), name='group-kick-member'),
    path('groups/<int:group_id>/leave/', views.GroupLeaveView.as_view(), name='group-leave'),
    path('groups/<int:group_id>/invite/', views.GroupInviteView.as_view(), name='group-invite'),
]
