from django.conf import settings
from post_office import mail

from djangoapp.yapify.models import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def send_verification_email(user: User, code: str) -> None:
    if settings.EMAILS_ENABLED:
        verification_message = (
            f"Hi {user.display_name},\n\n"
            f"Your verification code is: {code}\n\n"
            "Enter this code in the app to verify your email address.\n\n"
            "If you didn't request this, you can ignore this email."
        )

        verification_html = f"""
            <p>Hi {user.display_name},</p>
            <p>Your verification code is:</p>
            <h2 style="color:#2d89ef;">{code}</h2>
            <p>Enter this code in the app to verify your email address.</p>
            <p style="font-size:12px;color:#666;">
                If you didn't request this, you can safely ignore this email.
            </p>
        """

        mail.send(
            recipients=user.email,
            sender=settings.DEFAULT_FROM_EMAIL,
            subject="Verify your email address",
            message=verification_message,
            html_message=verification_html,
        )


def send_password_reset_email(user: User, code: str) -> None:
    if settings.EMAILS_ENABLED:
        reset_message = (
            f"Hi {user.display_name},\n\n"
            f"Your password reset code is: {code}\n\n"
            "Enter this code in the app to reset your password.\n\n"
            "This code will expire in 15 minutes.\n\n"
            "If you didn't request this, you can ignore this email."
        )

        reset_html = f"""
            <p>Hi {user.display_name},</p>
            <p>Your password reset code is:</p>
            <h2 style="color:#2d89ef;">{code}</h2>
            <p>Enter this code in the app to reset your password.</p>
            <p>This code will expire in 15 minutes.</p>
            <p style="font-size:12px;color:#666;">
                If you didn't request this, you can safely ignore this email.
            </p>
        """

        mail.send(
            recipients=user.email,
            sender=settings.DEFAULT_FROM_EMAIL,
            subject="Reset your password",
            message=reset_message,
            html_message=reset_html,
        )

