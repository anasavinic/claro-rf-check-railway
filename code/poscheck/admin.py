from django.contrib import admin

from poscheck.models import PoscheckResult


@admin.register(PoscheckResult)
class PoscheckResultAdmin(admin.ModelAdmin):
    list_display = ("analysis", "overall_status", "error_code", "processed_at")
    list_filter = ("overall_status",)
    readonly_fields = (
        "id",
        "execution",
        "validations",
        "extracted",
        "error_code",
        "error_title",
        "error_detail",
        "processed_at",
    )
