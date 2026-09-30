from django.conf import settings


class SecurityHeadersMiddleware:
    """Apply optional response policies that Django does not provide natively."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if policy:
            response.setdefault("Content-Security-Policy", policy)
        permissions_policy = getattr(settings, "PERMISSIONS_POLICY", "")
        if permissions_policy:
            response.setdefault("Permissions-Policy", permissions_policy)
        return response
