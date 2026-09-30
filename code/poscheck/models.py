import uuid

from django.db import models
from django.utils import timezone

from precheck.models import CheckAnalysis, PrecheckResultStatus


class PoscheckResult(models.Model):
    """Consolidated Full Check (pos-check) outcome for one analysis."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.OneToOneField(
        CheckAnalysis,
        on_delete=models.CASCADE,
        related_name="poscheck_result",
    )
    execution = models.ForeignKey(
        "precheck.CheckExecution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="poscheck_results",
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
        return f"poscheck:{self.analysis_id}:{self.overall_status}"
