from django.contrib import admin
from django.contrib import messages
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from .models import DeviceToken, Event, Notification


@admin.register(Notification)
class NotificationAdmin(UnfoldModelAdmin):
    list_display = ('notification_type', 'recipient', 'actor_count', 'is_read', 'last_event_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('recipient__email', 'recipient__username')
    readonly_fields = ('actor_ids', 'actor_count', 'last_event_at', 'created_at')
    date_hierarchy = 'last_event_at'
    actions = ['mark_as_read', 'mark_as_unread']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('recipient')

    @admin.action(description='Mark selected notifications as read')
    def mark_as_read(self, request, queryset):
        updated = queryset.filter(is_read=False).update(is_read=True)
        self.message_user(request, f'Marked {updated} notification(s) as read.', messages.SUCCESS)

    @admin.action(description='Mark selected notifications as unread')
    def mark_as_unread(self, request, queryset):
        updated = queryset.filter(is_read=True).update(is_read=False)
        self.message_user(request, f'Marked {updated} notification(s) as unread.', messages.SUCCESS)


@admin.register(Event)
class EventAdmin(UnfoldModelAdmin):
    list_display = ('event_type', 'actor', 'recipient', 'processed_at', 'created_at')
    list_filter = ('event_type',)
    search_fields = ('actor__email', 'actor__username', 'recipient__email', 'recipient__username')
    readonly_fields = ('processed_at', 'created_at')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('actor', 'recipient')


@admin.register(DeviceToken)
class DeviceTokenAdmin(UnfoldModelAdmin):
    list_display = ('user', 'token_truncated', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('user__email', 'user__username', 'token')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['deactivate_tokens', 'activate_tokens']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    def token_truncated(self, obj):
        return obj.token[:40] + '…' if len(obj.token) > 40 else obj.token
    token_truncated.short_description = 'Token'

    @admin.action(description='Deactivate selected tokens')
    def deactivate_tokens(self, request, queryset):
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f'Deactivated {updated} token(s).', messages.SUCCESS)

    @admin.action(description='Activate selected tokens')
    def activate_tokens(self, request, queryset):
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f'Activated {updated} token(s).', messages.SUCCESS)
