from django.core.cache import cache
from django.http import JsonResponse

_EXEMPT_PREFIXES = ('/api/schema', '/admin')


def _parse_version(v):
    try:
        return tuple(int(x) for x in v.strip().split('.'))
    except (ValueError, AttributeError):
        return None


class AppVersionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        header = request.headers.get('X-App-Version')

        if header and not any(request.path.startswith(p) for p in _EXEMPT_PREFIXES):
            client_ver = _parse_version(header)
            if client_ver is not None:
                config = cache.get('app_version_config')
                if config is None:
                    from djangoapp.yapify.models import AppVersionConfig
                    config = AppVersionConfig.get_current()
                    cache.set('app_version_config', config, timeout=60)

                min_ver = _parse_version(config.minimum_version)
                if min_ver is not None and client_ver < min_ver:
                    return JsonResponse({
                        'code': 'UPDATE_REQUIRED',
                        'update_required': True,
                        'minimum_version': config.minimum_version,
                        'ios_store_url': config.ios_store_url,
                        'android_store_url': config.android_store_url,
                    }, status=426)

        return self.get_response(request)
