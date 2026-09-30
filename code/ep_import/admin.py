from django.contrib import admin

from ep_import.models import EpCell, ImportJob


class EpCellInline(admin.TabularInline):
    model = EpCell
    extra = 0
    fields = ("technology", "site_name", "cell_name", "region", "on_air")
    readonly_fields = fields
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "created_by",
        "region",
        "status",
        "stage",
        "created_at",
        "expires_at",
        "finished_at",
    )
    list_filter = ("status", "region")
    search_fields = ("original_filename",)
    readonly_fields = (
        "id",
        "counts",
        "issues",
        "ignored_sheets",
        "error_title",
        "created_at",
        "started_at",
        "finished_at",
        "expires_at",
        "stage",
        "rows_processed",
        "rows_total",
        "content_sha256",
    )
    inlines = [EpCellInline]


@admin.register(EpCell)
class EpCellAdmin(admin.ModelAdmin):
    list_display = ("technology", "site_name", "cell_name", "region", "job")
    list_filter = ("technology", "region")
    search_fields = ("site_name", "cell_name")
