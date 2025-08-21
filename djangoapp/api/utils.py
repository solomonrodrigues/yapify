from djangoapp.yapify.models import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def send_verification_email(user: User, code: str) -> None:
    # ToDo: Set up django post office to send emails
    pass
