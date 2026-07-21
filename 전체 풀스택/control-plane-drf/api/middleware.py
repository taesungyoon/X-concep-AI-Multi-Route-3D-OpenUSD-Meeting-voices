import hmac

from django.conf import settings
from django.http import JsonResponse

from .corporate_auth import CorporateAuthenticationError, verify_token


class InternalApiTokenMiddleware:
    """Protect the control-plane API when a service token is configured.

    The PHP gateway injects this token server-side, so it is never embedded in
    browser JavaScript. Local development remains token-free unless explicitly
    enabled.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        expected = settings.INTERNAL_API_TOKEN
        if expected and request.path.startswith('/api/'):
            supplied = request.headers.get('X-Internal-Token', '')
            if not hmac.compare_digest(supplied, expected):
                return JsonResponse({'error': 'control-plane 인증 토큰이 올바르지 않음'}, status=401)
        return self.get_response(request)


class CorporateAuthMiddleware:
    """Require a signed user token for internal or corporate database auth."""

    PUBLIC_PATHS = {'/api/auth/config', '/api/auth/login', '/api/system-status'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.corporate_user = None
        if (
            settings.AUTH_MODE not in settings.AUTH_REQUIRED_MODES
            or request.method == 'OPTIONS'
            or not request.path.startswith('/api/')
            or request.path in self.PUBLIC_PATHS
        ):
            return self.get_response(request)
        authorization = request.headers.get('Authorization', '')
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() != 'bearer' or not token.strip():
            return JsonResponse({'error': '로그인이 필요함', 'code': 'authentication_required'}, status=401)
        try:
            request.corporate_user = verify_token(token.strip())
        except CorporateAuthenticationError:
            return JsonResponse({'error': '인증 정보가 만료되었거나 올바르지 않음', 'code': 'invalid_token'}, status=401)
        return self.get_response(request)
