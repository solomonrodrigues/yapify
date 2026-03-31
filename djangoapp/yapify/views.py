from django.shortcuts import get_object_or_404, render
from django.views.generic import TemplateView

from djangoapp.yapify.models import User

_PROFILE_COLOR_HEX = {
    'RED': '#e53e3e',
    'BLUE': '#3b82f6',
    'GREEN': '#22c55e',
    'YELLOW': '#eab308',
    'ORANGE': '#f97316',
    'PURPLE': '#a855f7',
    'PINK': '#ec4899',
    'BROWN': '#a16207',
    'BLACK': '#1e293b',
    'WHITE': '#cbd5e1',
    'GREY': '#6b7280',
    'CYAN': '#06b6d4',
    'MAGENTA': '#d946ef',
}


class LandingView(TemplateView):
    template_name = 'landing.html'


class PrivacyView(TemplateView):
    template_name = 'privacy.html'


class TermsView(TemplateView):
    template_name = 'terms.html'


def invite_view(request, username):
    user = get_object_or_404(User, username=username, is_active=True)
    display_name = user.display_name or user.username
    color = _PROFILE_COLOR_HEX.get(user.profile_color, '#a855f7')
    return render(request, 'invite.html', {
        'display_name': display_name,
        'color': color,
    })
