from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from .models import (
    User, Friendship, Quote, QuoteWitness, QuoteLike, Notification, EmailVerification, QuoteGuess,
    SavedQuote, HiddenQuote, RecentSearchItem, Report,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('username', 'display_name', 'bio')}),
        (_('Permissions'), {'fields': ('is_active', 'is_email_verified', 'is_staff', 'is_superuser', 'groups',
                                       'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
        (_('Other'), {'fields': ('profile_color', 'current_streak', 'longest_streak')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'display_name', 'password1', 'password2'),
        }),
    )
    list_display = ('id', 'email', 'username', 'display_name', 'is_active', 'is_staff', 'current_streak', 'longest_streak')
    search_fields = ('email', 'username', 'display_name')
    ordering = ('-date_joined',)
    filter_horizontal = ('groups', 'user_permissions')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'is_email_verified', 'profile_color')
    readonly_fields = ('date_joined',)
    date_hierarchy = 'date_joined'
    actions = ['delete_all_guesses', 'reset_streaks', 'verify_email', 'deactivate_users', 'activate_users']

    @admin.action(description="Delete all guesses (and reset streaks) for selected users")
    def delete_all_guesses(self, request, queryset):
        total = 0
        for user in queryset:
            count, _ = QuoteGuess.objects.filter(user=user).delete()
            total += count
            user.current_streak = 0
            user.longest_streak = 0
            user.save(update_fields=['current_streak', 'longest_streak'])
        self.message_user(
            request,
            f"Deleted {total} guess(es) and reset streaks for {queryset.count()} user(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Reset guess streaks for selected users")
    def reset_streaks(self, request, queryset):
        queryset.update(current_streak=0, longest_streak=0)
        self.message_user(request, f"Reset streaks for {queryset.count()} user(s).", messages.SUCCESS)

    @admin.action(description="Mark email as verified for selected users")
    def verify_email(self, request, queryset):
        updated = queryset.filter(is_email_verified=False).update(is_email_verified=True)
        self.message_user(request, f"Verified email for {updated} user(s).", messages.SUCCESS)

    @admin.action(description="Deactivate selected users")
    def deactivate_users(self, request, queryset):
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f"Deactivated {updated} user(s).", messages.SUCCESS)

    @admin.action(description="Activate selected users")
    def activate_users(self, request, queryset):
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f"Activated {updated} user(s).", messages.SUCCESS)


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "created_at",
        "expires_at",
        "used_at",
        "is_valid_display",
    )
    list_filter = ("created_at", "expires_at", "used_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("code_hash", "created_at", "expires_at")

    def is_valid_display(self, obj):
        return obj.is_valid()
    is_valid_display.boolean = True
    is_valid_display.short_description = "Is Valid?"

    def get_queryset(self, request):
        # Prefetch related users to make the list faster
        qs = super().get_queryset(request)
        return qs.select_related("user")


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'receiver', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('sender__email', 'sender__username', 'receiver__email', 'receiver__username')
    autocomplete_fields = ('sender', 'receiver')
    actions = ['accept_friendships', 'reject_friendships']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('sender', 'receiver')

    @admin.action(description="Accept selected friendships")
    def accept_friendships(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='accepted')
        self.message_user(request, f"Accepted {updated} friendship(s).", messages.SUCCESS)

    @admin.action(description="Reject selected friendships")
    def reject_friendships(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='rejected')
        self.message_user(request, f"Rejected {updated} friendship(s).", messages.SUCCESS)


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ('id', '__str__', 'author', 'quoted_user', 'is_active', 'like_count', 'witness_count', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('text', 'author__email', 'author__username', 'quoted_user__email', 'quoted_user__username')
    autocomplete_fields = ('author', 'quoted_user')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    actions = ['deactivate_quotes', 'activate_quotes']

    def get_queryset(self, request):
        from django.db.models import Count
        return super().get_queryset(request).select_related(
            'author', 'quoted_user'
        ).annotate(
            _like_count=Count('likes', distinct=True),
            _witness_count=Count('witnesses', distinct=True),
        )

    def like_count(self, obj):
        return obj._like_count
    like_count.admin_order_field = '_like_count'
    like_count.short_description = 'Likes'

    def witness_count(self, obj):
        return obj._witness_count
    witness_count.admin_order_field = '_witness_count'
    witness_count.short_description = 'Witnesses'

    @admin.action(description="Deactivate selected quotes")
    def deactivate_quotes(self, request, queryset):
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f"Deactivated {updated} quote(s).", messages.SUCCESS)

    @admin.action(description="Activate selected quotes")
    def activate_quotes(self, request, queryset):
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f"Activated {updated} quote(s).", messages.SUCCESS)


@admin.register(QuoteWitness)
class QuoteWitnessAdmin(admin.ModelAdmin):
    list_display = ('witness', 'quote', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('witness__email', 'witness__username', 'quote__text')
    autocomplete_fields = ('witness', 'quote')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('witness', 'quote', 'quote__author')


@admin.register(QuoteLike)
class QuoteLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'quote', 'created_at')
    search_fields = ('user__email', 'user__username', 'quote__text')
    autocomplete_fields = ('user', 'quote')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'quote', 'quote__author')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('notification_type', 'recipient', 'sender', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__email', 'recipient__username', 'sender__email', 'sender__username', 'title')
    autocomplete_fields = ('recipient', 'sender', 'quote', 'friendship')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    actions = ['mark_as_read', 'mark_as_unread']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('recipient', 'sender')

    @admin.action(description="Mark selected notifications as read")
    def mark_as_read(self, request, queryset):
        updated = queryset.filter(is_read=False).update(is_read=True)
        self.message_user(request, f"Marked {updated} notification(s) as read.", messages.SUCCESS)

    @admin.action(description="Mark selected notifications as unread")
    def mark_as_unread(self, request, queryset):
        updated = queryset.filter(is_read=True).update(is_read=False)
        self.message_user(request, f"Marked {updated} notification(s) as unread.", messages.SUCCESS)


@admin.register(QuoteGuess)
class QuoteGuessAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "quote_short",
        "guessed_user",
        "correct",
        "skipped",
        "created_at",
    )
    list_filter = ("correct", "skipped", "created_at")
    search_fields = (
        "user__username",
        "user__email",
        "quote__text",
        "guessed_user__username",
        "guessed_user__email",
    )
    autocomplete_fields = ("user", "quote", "guessed_user")
    readonly_fields = ("correct", "created_at")
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'quote', 'quote__author', 'guessed_user')

    def quote_short(self, obj):
        return (obj.quote.text[:50] + "...") if obj.quote.text else ""
    quote_short.short_description = "Quote"


@admin.register(SavedQuote)
class SavedQuoteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "quote_short",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "user__email",
        "user__username",
        "quote__text",
    )
    autocomplete_fields = ("user", "quote")
    readonly_fields = ("created_at",)

    def quote_short(self, obj):
        return obj.quote.text[:50] + "…" if obj.quote.text else ""
    quote_short.short_description = "Quote"


@admin.register(HiddenQuote)
class HiddenQuoteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "quote_short",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "user__email",
        "user__username",
        "quote__text",
    )
    autocomplete_fields = ("user", "quote")
    readonly_fields = ("created_at",)

    def quote_short(self, obj):
        return obj.quote.text[:50] + "…" if obj.quote.text else ""
    quote_short.short_description = "Quote"


@admin.register(RecentSearchItem)
class RecentSearchItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "owner",
        "target_type",
        "target_display",
        "last_query",
        "touched_at",
    )
    list_filter = ("touched_at",)
    search_fields = (
        "owner__email",
        "owner__username",
        "user_target__email",
        "user_target__username",
        "quote_target__text",
        "last_query",
    )
    autocomplete_fields = ("owner", "user_target", "quote_target")
    readonly_fields = ("touched_at",)

    def target_type(self, obj):
        return "User" if obj.user_target_id else "Quote"
    target_type.short_description = "Target Type"

    def target_display(self, obj):
        if obj.user_target:
            return str(obj.user_target)
        if obj.quote_target:
            return obj.quote_target.text[:50] + "…" if obj.quote_target.text else ""
        return "-"
    target_display.short_description = "Target"


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reporter",
        "target_type",
        "target_display",
        "reason",
        "created_at",
    )
    list_filter = ("reason", "created_at")
    search_fields = (
        "reporter__email",
        "reporter__username",
        "reported_quote__text",
        "reported_user__email",
        "reported_user__username",
    )
    autocomplete_fields = ("reporter", "reported_quote", "reported_user")
    readonly_fields = ("created_at", "content_snapshot")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('reporter', 'reported_quote', 'reported_user')

    def target_type(self, obj):
        snapshot = obj.content_snapshot or {}
        return snapshot.get("type", "unknown").capitalize()
    target_type.short_description = "Target Type"

    def target_display(self, obj):
        # Prefer live data, fall back to snapshot
        if obj.reported_quote:
            return obj.reported_quote.text[:50] + "…" if obj.reported_quote.text else ""
        if obj.reported_user:
            return str(obj.reported_user)
        # Target was deleted — use snapshot
        snapshot = obj.content_snapshot or {}
        if snapshot.get("type") == "quote":
            text = snapshot.get("text", "")
            return (text[:50] + "…" if len(text) > 50 else text) + " [deleted]"
        if snapshot.get("type") == "user":
            return f'{snapshot.get("username", "?")} [deleted]'
        return "-"
    target_display.short_description = "Target"
