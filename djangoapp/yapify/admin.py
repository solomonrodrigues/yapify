from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, Friendship, Quote, QuoteWitness, QuoteLike, Notification, EmailVerification


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('username', 'display_name', 'bio')}),
        (_('Permissions'), {'fields': ('is_active', 'is_email_verified', 'is_staff', 'is_superuser', 'groups',
                                       'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'display_name', 'password1', 'password2'),
        }),
    )
    list_display = ('email', 'username', 'display_name', 'is_active', 'is_staff')
    search_fields = ('email', 'username', 'display_name')
    ordering = ('-date_joined',)
    filter_horizontal = ('groups', 'user_permissions')
    list_filter = ('is_active', 'is_staff', 'is_superuser')
    readonly_fields = ('date_joined',)


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
    readonly_fields = ("code_hash", "created_at", "used_at", "expires_at")

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
    list_display = ('sender', 'receiver', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('sender__email', 'receiver__email')
    autocomplete_fields = ('sender', 'receiver')


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'author', 'quoted_user', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('text', 'author__email', 'quoted_user__email')
    autocomplete_fields = ('author', 'quoted_user')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(QuoteWitness)
class QuoteWitnessAdmin(admin.ModelAdmin):
    list_display = ('witness', 'quote', 'is_witness', 'created_at')
    list_filter = ('is_witness', 'created_at')
    search_fields = ('witness__email', 'quote__text')
    autocomplete_fields = ('witness', 'quote')


@admin.register(QuoteLike)
class QuoteLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'quote', 'created_at')
    search_fields = ('user__email', 'quote__text')
    autocomplete_fields = ('user', 'quote')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('notification_type', 'recipient', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__email', 'sender__email', 'title')
    autocomplete_fields = ('recipient', 'sender', 'quote', 'friendship')
    readonly_fields = ('created_at',)
