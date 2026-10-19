"""Local account used by the desktop window. No password prompt."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the local desktop user if it does not exist."

    def handle(self, *args, **options):
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(username="desktop")
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        if not user.has_usable_password():
            user.set_unusable_password()
        user.save()
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} desktop user."))
