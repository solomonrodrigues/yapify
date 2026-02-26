from django.http import Http404
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler


def _normalize_error_detail(error_detail):
    code = getattr(error_detail, 'code', None) or 'invalid'
    return {"code": code.upper(), "detail": str(error_detail)}


def _normalize_field_errors(data):
    result = {}
    for field, errors in data.items():
        if isinstance(errors, list):
            result[field] = [_normalize_error_detail(e) for e in errors]
        elif isinstance(errors, dict):
            result[field] = _normalize_field_errors(errors)
        else:
            result[field] = [_normalize_error_detail(errors)]
    return result


def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler that wraps every non-2xx response in a
    consistent envelope:

      Domain / auth error:
        {"code": "INVALID_CREDENTIALS", "detail": "Invalid credentials."}

      Field validation error:
        {"code": "VALIDATION_ERROR", "errors": {"email": [{"code": "REQUIRED", "detail": "..."}]}}

      All other DRF exceptions (NotFound, PermissionDenied, Throttled, …):
        {"code": "NOT_FOUND", "detail": "Not found."}

    Non-field ValidationErrors (list form) promote the first error's code to
    the top level, making auth errors like INVALID_CREDENTIALS flat.
    DRF's default_code values (snake_case) are uppercased automatically so
    they match the constants in error_codes.py without a manual mapping table.
    """
    if isinstance(exc, Http404):
        exc = exceptions.NotFound(*exc.args)
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied(*exc.args)

    # Delegate to DRF's default handler first to preserve response headers
    # (WWW-Authenticate, Retry-After) and status code logic.
    response = drf_default_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        if isinstance(detail, dict):
            response.data = {
                "code": "VALIDATION_ERROR",
                "errors": _normalize_field_errors(detail),
            }
        else:
            first = detail[0] if detail else None
            code = (getattr(first, 'code', None) or 'invalid').upper()
            response.data = {
                "code": code,
                "detail": str(first) if first else str(exc.default_detail),
            }
    else:
        code = getattr(exc, 'default_code', 'error').upper()
        detail = exc.detail
        if isinstance(detail, list):
            message = str(detail[0]) if detail else str(exc.default_detail)
        elif isinstance(detail, dict):
            message = str(exc)
        else:
            message = str(detail)
        response.data = {"code": code, "detail": message}

    return response


def api_error(code: str, detail: str, status: int) -> Response:
    """Return a standardised error Response for use directly in views."""
    return Response({"code": code, "detail": detail}, status=status)
