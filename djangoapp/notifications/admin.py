from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.db.models import Count, IntegerField, OuterRef, Subquery, Q
from django.utils import timezone
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from .models import DeviceToken, Event, Notification


class EventProcessingFilter(admin.SimpleListFilter):
    title = 'processing status'
    parameter_name = 'processed'

    def lookups(self, request, model_admin):
        return [
            ('pending', 'Pending'),
            ('done', 'Processed'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'pending':
            return queryset.filter(processed_at__isnull=True)
        if self.value() == 'done':
            return queryset.filter(processed_at__isnull=False)
        return queryset


class StaleTokenFilter(admin.SimpleListFilter):
    title = 'staleness'
    parameter_name = 'stale'

    def lookups(self, request, model_admin):
        return [
            ('stale', f'Stale (>{settings.PUSH_TOKEN_STALE_DAYS}d)'),
            ('fresh', 'Fresh'),
        ]

    def queryset(self, request, queryset):
        cutoff = timezone.now() - timedelta(days=settings.PUSH_TOKEN_STALE_DAYS)
        if self.value() == 'stale':
            return queryset.filter(
                Q(last_refreshed_at__isnull=True) | Q(last_refreshed_at__lt=cutoff)
            )
        if self.value() == 'fresh':
            return queryset.filter(last_refreshed_at__gte=cutoff)
        return queryset


@admin.register(Notification)
class NotificationAdmin(UnfoldModelAdmin):
    list_display = ('notification_type', 'recipient', 'actor_count', 'is_read', 'last_event_at', 'recipient_active_tokens')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('recipient__email', 'recipient__username')
    autocomplete_fields = ('recipient', 'quote', 'group_invite')
    readonly_fields = ('actor_ids', 'actor_count', 'last_event_at', 'created_at')
    date_hierarchy = 'last_event_at'
    actions = ['mark_as_read', 'mark_as_unread']

    def get_queryset(self, request):
        stale_cutoff = timezone.now() - timedelta(days=settings.PUSH_TOKEN_STALE_DAYS)
        active_token_subquery = (
            DeviceToken.objects
            .filter(user=OuterRef('recipient'), is_active=True, last_refreshed_at__gte=stale_cutoff)
            .values('user')
            .annotate(c=Count('id'))
            .values('c')
        )
        return (
            super().get_queryset(request)
            .select_related('recipient', 'quote', 'group_invite')
            .annotate(_active_token_count=Subquery(active_token_subquery, output_field=IntegerField()))
        )

    def recipient_active_tokens(self, obj):
        count = obj._active_token_count or 0
        return count
    recipient_active_tokens.short_description = 'Active Tokens'
    recipient_active_tokens.admin_order_field = '_active_token_count'

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
    list_display = ('event_type', 'actor', 'recipient', 'is_processed', 'processed_at', 'created_at')
    list_filter = ('event_type', EventProcessingFilter)
    search_fields = ('actor__email', 'actor__username', 'recipient__email', 'recipient__username')
    autocomplete_fields = ('actor', 'recipient', 'quote', 'group_invite')
    readonly_fields = ('processed_at', 'created_at')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('actor', 'recipient', 'quote', 'group_invite')

    def is_processed(self, obj):
        return obj.processed_at is not None
    is_processed.boolean = True
    is_processed.short_description = 'Processed'
    is_processed.admin_order_field = 'processed_at'


@admin.register(DeviceToken)
class DeviceTokenAdmin(UnfoldModelAdmin):
    list_display = ('user', 'token_truncated', 'is_active', 'is_stale', 'last_refreshed_at', 'created_at')
    list_filter = ('is_active', StaleTokenFilter)
    search_fields = ('user__email', 'user__username', 'token')
    autocomplete_fields = ('user',)
    readonly_fields = ('last_refreshed_at', 'created_at', 'updated_at')
    actions = ['deactivate_tokens', 'activate_tokens']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    def token_truncated(self, obj):
        return obj.token[:40] + '…' if len(obj.token) > 40 else obj.token
    token_truncated.short_description = 'Token'

    def is_stale(self, obj):
        if not obj.last_refreshed_at:
            return True
        cutoff = timezone.now() - timedelta(days=settings.PUSH_TOKEN_STALE_DAYS)
        return obj.last_refreshed_at < cutoff
    is_stale.boolean = True
    is_stale.short_description = 'Stale'

    @admin.action(description='Deactivate selected tokens')
    def deactivate_tokens(self, request, queryset):
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f'Deactivated {updated} token(s).', messages.SUCCESS)

    @admin.action(description='Activate selected tokens')
    def activate_tokens(self, request, queryset):
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f'Activated {updated} token(s).', messages.SUCCESS)
