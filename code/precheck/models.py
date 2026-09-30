import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class CheckAnalysisStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    AWAITING_RETURNS = "awaiting_returns", "Awaiting returns"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    INCONSISTENT = "inconsistent", "Inconsistent"
    FAILED = "failed", "Failed"


class CheckType(models.TextChoices):
    PRECHECK = "precheck", "Pre-check"
    FULL_CHECK = "full_check", "Full Check"


class PrecheckResultStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    INCONSISTENT = "inconsistent", "Inconsistent"
    EXECUTION_FAILURE = "execution_failure", "Execution failure"


class CheckExecutionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class CheckExecutionScope(models.TextChoices):
    PRECHECK = "precheck", "Pre-check"
    FULL_CHECK = "full_check", "Full Check"
    BOTH = "both", "Pre-check and Full Check"


class CheckExecutionStage(models.TextChoices):
    QUEUED = "queued", "Queued"
    READING = "reading", "Reading"
    PARSING = "parsing", "Parsing"
    VALIDATING = "validating", "Validating"
    PERSISTING = "persisting", "Persisting"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


class CombinedCheck(models.Model):
    """Multi-technology RF check grouping one or more child CheckAnalysis rows."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="combined_checks",
    )
    ep_job = models.ForeignKey(
        "ep_import.ImportJob",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="combined_checks",
    )
    technologies = models.JSONField(default=list, blank=True)
    site_names = models.JSONField(default=list, blank=True)
    pre_check = models.BooleanField(default=False)
    full_check = models.BooleanField(default=True)
    status = models.CharField(
        max_length=32,
        choices=CheckAnalysisStatus.choices,
        default=CheckAnalysisStatus.DRAFT,
        db_index=True,
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        techs = "+".join(self.technologies or []) or "?"
        return f"combined:{techs}:{self.status}"


class CheckAnalysis(models.Model):
    """User analysis selection linking an imported EP to check execution."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="check_analyses",
    )
    ep_job = models.ForeignKey(
        "ep_import.ImportJob",
        on_delete=models.PROTECT,
        related_name="check_analyses",
    )
    combined_check = models.ForeignKey(
        CombinedCheck,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="analyses",
    )
    technology = models.CharField(max_length=8, default="5G", db_index=True)
    site_name = models.CharField(max_length=255)
    selected_cells = models.JSONField(default=list, blank=True)
    pre_check = models.BooleanField(default=False)
    full_check = models.BooleanField(default=False)
    status = models.CharField(
        max_length=32,
        choices=CheckAnalysisStatus.choices,
        default=CheckAnalysisStatus.DRAFT,
        db_index=True,
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["ep_job", "technology", "site_name"]),
            models.Index(fields=["combined_check", "technology"]),
        ]

    def __str__(self) -> str:
        return f"{self.technology}:{self.site_name}:{self.status}"


class CheckReturnFile(models.Model):
    """Gerência return file uploaded for a specific check type."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.ForeignKey(
        CheckAnalysis,
        on_delete=models.CASCADE,
        related_name="return_files",
    )
    check_type = models.CharField(max_length=16, choices=CheckType.choices, db_index=True)
    original_filename = models.CharField(max_length=255)
    stored_file = models.FileField(upload_to="check_returns/%Y/%m/%d/")
    content_sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-uploaded_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["analysis", "check_type"],
                name="uniq_checkreturn_analysis_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.check_type}:{self.original_filename}"


class CheckExecution(models.Model):
    """Async job record for a Pre-check / Full Check run (history like ImportJob)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.ForeignKey(
        CheckAnalysis,
        on_delete=models.CASCADE,
        related_name="executions",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="check_executions",
    )
    scope = models.CharField(max_length=16, choices=CheckExecutionScope.choices, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=CheckExecutionStatus.choices,
        default=CheckExecutionStatus.PENDING,
        db_index=True,
    )
    stage = models.CharField(
        max_length=16,
        choices=CheckExecutionStage.choices,
        default=CheckExecutionStage.QUEUED,
        blank=True,
    )
    selection_version = models.CharField(max_length=64, blank=True, default="", db_index=True)
    pre_return_sha256 = models.CharField(max_length=64, blank=True, default="")
    full_return_sha256 = models.CharField(max_length=64, blank=True, default="")
    task_id = models.CharField(max_length=255, blank=True, default="")
    result_status = models.CharField(max_length=32, blank=True, default="")
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_title = models.CharField(max_length=255, blank=True, default="")
    redirect_url = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["analysis", "status"]),
            models.Index(fields=["analysis", "selection_version", "pre_return_sha256", "full_return_sha256"]),
        ]

    def __str__(self) -> str:
        return f"check:{self.scope}:{self.status}:{self.id}"


class PrecheckResult(models.Model):
    """Consolidated 5G pre-check outcome for one analysis."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.OneToOneField(
        CheckAnalysis,
        on_delete=models.CASCADE,
        related_name="precheck_result",
    )
    execution = models.ForeignKey(
        CheckExecution,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="precheck_results",
    )
    overall_status = models.CharField(
        max_length=32,
        choices=PrecheckResultStatus.choices,
        db_index=True,
    )
    validations = models.JSONField(default=list, blank=True)
    extracted = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_title = models.CharField(max_length=255, blank=True, default="")
    error_detail = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-processed_at",)

    def __str__(self) -> str:
        return f"precheck:{self.analysis_id}:{self.overall_status}"
