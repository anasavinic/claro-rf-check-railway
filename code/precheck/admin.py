from django.contrib import admin

from precheck.models import CheckAnalysis, CheckExecution, CheckReturnFile, CombinedCheck, PrecheckResult


@admin.register(CombinedCheck)
class CombinedCheckAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "technologies", "site_names", "created_at")
    list_filter = ("status",)
    search_fields = ("id",)
    readonly_fields = ("id", "created_at", "updated_at")


class CheckReturnFileInline(admin.TabularInline):
    model = CheckReturnFile
    extra = 0
    fields = ("check_type", "original_filename", "content_sha256", "uploaded_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class CheckExecutionInline(admin.TabularInline):
    model = CheckExecution
    extra = 0
    fields = ("scope", "status", "stage", "result_status", "task_id", "created_at", "finished_at")
    readonly_fields = fields
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class PrecheckResultInline(admin.StackedInline):
    model = PrecheckResult
    extra = 0
    fields = (
        "execution",
        "overall_status",
        "validations",
        "extracted",
        "error_code",
        "error_title",
        "error_detail",
        "processed_at",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CheckAnalysis)
class CheckAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "technology",
        "site_name",
        "status",
        "pre_check",
        "full_check",
        "combined_check",
        "created_by",
        "created_at",
    )
    list_filter = ("technology", "status", "pre_check", "full_check")
    search_fields = ("site_name",)
    readonly_fields = ("id", "created_at", "updated_at", "selected_cells", "combined_check")
    raw_id_fields = ("combined_check", "ep_job")
    inlines = [CheckReturnFileInline, CheckExecutionInline, PrecheckResultInline]


@admin.register(CheckReturnFile)
class CheckReturnFileAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "check_type", "analysis", "uploaded_at")
    list_filter = ("check_type",)
    search_fields = ("original_filename",)
    readonly_fields = ("id", "content_sha256", "uploaded_at")


@admin.register(CheckExecution)
class CheckExecutionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "analysis",
        "scope",
        "status",
        "stage",
        "result_status",
        "created_at",
        "finished_at",
    )
    list_filter = ("scope", "status", "stage")
    search_fields = ("task_id", "error_code")
    readonly_fields = (
        "id",
        "analysis",
        "created_by",
        "scope",
        "status",
        "stage",
        "selection_version",
        "pre_return_sha256",
        "full_return_sha256",
        "task_id",
        "result_status",
        "error_code",
        "error_title",
        "redirect_url",
        "created_at",
        "started_at",
        "finished_at",
    )


@admin.register(PrecheckResult)
class PrecheckResultAdmin(admin.ModelAdmin):
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
