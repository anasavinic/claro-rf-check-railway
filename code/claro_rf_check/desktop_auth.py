"""Sign in the local desktop user so the window opens ready to use."""

from django.contrib.auth import get_user_model, login


class DesktopAutoLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and request.path not in {"/healthz", "/readyz"}:
            user = get_user_model().objects.filter(username="desktop").first()
            if user is not None:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)
