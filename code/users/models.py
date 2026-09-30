from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Local user keyed by Core Connect ``(issuer, sub)``."""

    core_connect_issuer = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Core Connect issuer (OIDC iss) bound with core_connect_sub.",
    )
    core_connect_sub = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable Core Connect subject (OIDC sub).",
    )
    avatar_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="Avatar URL from Core Connect when picture claim is available.",
    )

    class Meta(AbstractUser.Meta):
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.UniqueConstraint(
                fields=["core_connect_issuer", "core_connect_sub"],
                condition=models.Q(
                    core_connect_issuer__isnull=False,
                    core_connect_sub__isnull=False,
                )
                & ~models.Q(core_connect_issuer="")
                & ~models.Q(core_connect_sub=""),
                name="users_user_issuer_sub_uniq",
            ),
        ]

    def __str__(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username or self.email or str(self.pk)

    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.email or self.username

    def initials(self) -> str:
        first = (self.first_name or "").strip()
        last = (self.last_name or "").strip()
        if first and last:
            return f"{first[0]}{last[0]}".upper()
        if first:
            return first[:2].upper()
        source = (self.email or self.username or "?").strip()
        return source[:2].upper()
