from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from users.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "core_connect_issuer",
        "core_connect_sub",
        "is_staff",
    )
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "core_connect_issuer",
        "core_connect_sub",
    )
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Core Connect",
            {
                "description": ("Access is granted or revoked by Core Connect. Local is_active is not an SSO gate."),
                "fields": (
                    "core_connect_issuer",
                    "core_connect_sub",
                    "avatar_url",
                ),
            },
        ),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "Core Connect",
            {
                "fields": (
                    "core_connect_issuer",
                    "core_connect_sub",
                    "avatar_url",
                )
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and obj.core_connect_issuer and obj.core_connect_sub:
            return (*fields, "core_connect_issuer", "core_connect_sub", "is_active")
        return fields
