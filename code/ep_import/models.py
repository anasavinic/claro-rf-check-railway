import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


class ImportJobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class ImportStage(models.TextChoices):
    QUEUED = "queued", "Queued"
    VALIDATING = "validating", "Validating"
    PERSISTING = "persisting", "Persisting"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


def retention_deadline():
    days = int(getattr(settings, "EP_IMPORT_RETENTION_DAYS", 15))
    return timezone.now() + timedelta(days=days)


class ImportJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        get_user_model(),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ep_imports",
    )
    original_filename = models.CharField(max_length=255)
    stored_file = models.FileField(upload_to="ep_imports/%Y/%m/%d/")
    region = models.CharField(max_length=16, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=ImportJobStatus.choices,
        default=ImportJobStatus.PENDING,
        db_index=True,
    )
    counts = models.JSONField(default=dict, blank=True)
    issues = models.JSONField(default=list, blank=True)
    ignored_sheets = models.JSONField(default=list, blank=True)
    error_title = models.CharField(max_length=255, blank=True, default="")
    stage = models.CharField(max_length=16, choices=ImportStage.choices, blank=True, default="")
    rows_processed = models.PositiveIntegerField(default=0)
    rows_total = models.PositiveIntegerField(null=True, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    task_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        # Retention is fixed at creation. Re-analysis / re-upload must not renew expires_at.
        if self.expires_at is None:
            self.expires_at = retention_deadline()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.status})"


class EpCell(models.Model):
    """Normalized EP cell row available to check modules."""

    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="cells")
    technology = models.CharField(max_length=8, db_index=True)
    region = models.CharField(max_length=16, blank=True, default="", db_index=True)
    state = models.CharField(max_length=8, blank=True, default="")
    site_name = models.CharField(max_length=255, db_index=True)
    cell_name = models.CharField(max_length=255, db_index=True)
    on_air = models.CharField(max_length=32, blank=True, default="")
    raw = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "technology", "site_name", "cell_name"],
                name="uniq_epcell_job_tech_site_cell",
            ),
        ]
        indexes = [
            models.Index(fields=["job", "technology", "site_name"]),
            models.Index(fields=["job", "technology", "cell_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.technology}:{self.site_name}:{self.cell_name}"
