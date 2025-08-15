import re
from django.core.exceptions import ValidationError


def yapify_username_validator(value):
    """
    Validates that the username only contains lowercase letters, dots, or underscores.
    """
    if not re.fullmatch(r'[a-z._]+', value):
        raise ValidationError(
            'Username may only contain lowercase letters, dots, and underscores.'
        )
