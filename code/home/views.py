from django.conf import settings
from django.shortcuts import redirect, render


def index(request):
    if not request.user.is_authenticated:
        return redirect(settings.LOGIN_URL)

    return render(
        request,
        "home/index.html",
        {
            "active_nav": "home",
            "tech_nav": [
                ("2G", "2G"),
                ("3G", "3G"),
                ("4G", "4G"),
                ("5G", "5G NR"),
            ],
        },
    )


def custom_404(request, exception):
    return render(request, "home/404.html", status=404)
