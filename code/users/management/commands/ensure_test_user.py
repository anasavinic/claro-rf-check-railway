"""Idempotent local user for the Railway test deploy."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update the local test user from CLARO_RF_TEST_USERNAME and CLARO_RF_TEST_PASSWORD."

    def handle(self, *args, **options):
        username = os.environ.get("CLARO_RF_TEST_USERNAME", "").strip()
        password = os.environ.get("CLARO_RF_TEST_PASSWORD", "")
        if not username and not password:
            self.stdout.write("CLARO_RF_TEST_USERNAME is unset; skipping local user.")
            return
        if not username or not password:
            raise CommandError("Set both CLARO_RF_TEST_USERNAME and CLARO_RF_TEST_PASSWORD.")

        email = os.environ.get("CLARO_RF_TEST_EMAIL", "").strip()
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(username=username, defaults={"email": email})
        if email:
            user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} test user {username}."))
