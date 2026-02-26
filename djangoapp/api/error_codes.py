# ── Auth ──────────────────────────────────────────────────────────────────────
INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
MISSING_CREDENTIALS = "MISSING_CREDENTIALS"
VERIFICATION_CODE_INVALID = "VERIFICATION_CODE_INVALID"
EMAIL_ALREADY_VERIFIED = "EMAIL_ALREADY_VERIFIED"
RESET_CODE_INVALID = "RESET_CODE_INVALID"

# ── Friends ───────────────────────────────────────────────────────────────────
NO_PENDING_REQUEST = "NO_PENDING_REQUEST"
NOT_FRIENDS = "NOT_FRIENDS"
INVALID_ACTION = "INVALID_ACTION"
CANNOT_BLOCK_SELF = "CANNOT_BLOCK_SELF"

# ── Quotes ────────────────────────────────────────────────────────────────────
ALREADY_GUESSED = "ALREADY_GUESSED"
CANNOT_GUESS_OWN_QUOTE = "CANNOT_GUESS_OWN_QUOTE"
CANNOT_GUESS_SELF = "CANNOT_GUESS_SELF"
SKIP_LIMIT_EXCEEDED = "SKIP_LIMIT_EXCEEDED"
QUOTE_ALREADY_HAS_USER = "QUOTE_ALREADY_HAS_USER"
INVALID_QUOTE_RESPONSE = "INVALID_QUOTE_RESPONSE"

# ── Reports ───────────────────────────────────────────────────────────────────
CANNOT_REPORT_SELF = "CANNOT_REPORT_SELF"
ALREADY_REPORTED = "ALREADY_REPORTED"
REPORT_NOT_FOUND = "REPORT_NOT_FOUND"

# ── Devices ───────────────────────────────────────────────────────────────────
INVALID_TOKEN_FORMAT = "INVALID_TOKEN_FORMAT"

# ── General ───────────────────────────────────────────────────────────────────
NOT_FOUND = "NOT_FOUND"
VALIDATION_ERROR = "VALIDATION_ERROR"
MISSING_PARAMETERS = "MISSING_PARAMETERS"
INVALID_PARAMETER = "INVALID_PARAMETER"
FIELD_REQUIRED = "FIELD_REQUIRED"
PASSWORDS_DO_NOT_MATCH = "PASSWORDS_DO_NOT_MATCH"

# ── DRF framework codes ────────────────────────────────────────────────────────
# Emitted automatically by the custom exception handler (exceptions.py), which
# uppercases each built-in DRF exception's default_code attribute. No application
# view or serializer raises these directly.
# Ref: https://www.django-rest-framework.org/api-guide/exceptions/
NOT_AUTHENTICATED = "NOT_AUTHENTICATED"  # NotAuthenticated (401)
AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"  # AuthenticationFailed (401)
PERMISSION_DENIED = "PERMISSION_DENIED"  # PermissionDenied (403)
METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"  # MethodNotAllowed (405)
NOT_ACCEPTABLE = "NOT_ACCEPTABLE"  # NotAcceptable (406)
UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"  # UnsupportedMediaType (415)
THROTTLED = "THROTTLED"  # Throttled (429)
