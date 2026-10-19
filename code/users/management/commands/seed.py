"""Seed default RBAC groups (Admin, Manager, Operator).

Permission *rows* are created by Django on migrate from model Meta.
This command only creates Groups and assigns existing Permissions.
"""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from users.permissions import (
    ADMIN,
    MANAGER,
    OPERATOR,
    SEED_GROUP_NAMES,
    permissions_for_seed_group,
)


def describe_seed() -> list[str]:
    """Human-readable lines describing what seed will create/assign."""
    return [
        "Roles (Django Groups + permission assignments):",
        f"  - {ADMIN}",
        "      · all assignable RBAC permissions",
        f"  - {MANAGER}",
        "      · all assignable RBAC permissions except auth.add/change/delete_group",
        "      · can assign roles/permissions to users (manage_roles)",
        "      · cannot create/edit/delete Groups in the Roles UI",
        f"  - {OPERATOR}",
        "      · no permissions (default end user; assigned on SSO create)",
        "",
        "Not seeded (create separately as needed):",
        "  - Superuser (use createsuperuser)",
        "  - Permission rows (Django migrate / post_migrate)",
    ]


class Command(BaseCommand):
    help = "Seed default RBAC groups (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be seeded without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        for line in describe_seed():
            self.stdout.write(line)

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run — no changes written."))
            return

        self.stdout.write("")
        for group_name in SEED_GROUP_NAMES:
            group, created = Group.objects.get_or_create(name=group_name)
            perms = permissions_for_seed_group(group_name)
            before = set(group.permissions.values_list("id", flat=True))
            group.permissions.set(perms)
            after = set(group.permissions.values_list("id", flat=True))
            action = "created" if created else "updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"Group {group_name!r} {action} ({len(after)} permission(s); {len(after - before)} newly linked)"
                )
            )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
