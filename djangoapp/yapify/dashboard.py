import json
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone


def dashboard_callback(request, context):
    from .models import User, Quote, Friendship, QuoteLike, Report

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # KPI metrics
    context["kpi"] = {
        "total_users": User.objects.count(),
        "new_users_this_month": User.objects.filter(date_joined__gte=start_of_month).count(),
        "monthly_active_users": User.objects.filter(last_login__gte=thirty_days_ago).count(),
        "total_quotes": Quote.objects.count(),
        "quotes_this_month": Quote.objects.filter(created_at__gte=start_of_month).count(),
        "active_friendships": Friendship.objects.filter(status="accepted").count(),
        "total_likes": QuoteLike.objects.count(),
        "recent_reports": Report.objects.filter(created_at__gte=thirty_days_ago).count(),
    }

    # Build a consistent set of the last 6 months
    months = []
    cursor = start_of_month
    for _ in range(6):
        months.insert(0, cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    six_months_ago = months[0]

    user_trend = dict(
        User.objects.filter(date_joined__gte=six_months_ago)
        .annotate(month=TruncMonth("date_joined"))
        .values("month")
        .annotate(count=Count("id"))
        .values_list("month", "count")
    )

    quote_trend = dict(
        Quote.objects.filter(created_at__gte=six_months_ago)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
        .values_list("month", "count")
    )

    labels = [m.strftime("%b %Y") for m in months]
    user_data = [user_trend.get(m, 0) for m in months]
    quote_data = [quote_trend.get(m, 0) for m in months]

    context["chart_data"] = json.dumps({
        "labels": labels,
        "datasets": [
            {
                "label": "New Users",
                "data": user_data,
                "backgroundColor": "rgba(99, 102, 241, 0.5)",
                "borderColor": "rgb(99, 102, 241)",
                "borderWidth": 1,
            },
            {
                "label": "New Quotes",
                "data": quote_data,
                "backgroundColor": "rgba(244, 114, 182, 0.5)",
                "borderColor": "rgb(244, 114, 182)",
                "borderWidth": 1,
            },
        ],
    })

    return context
