# Generated manually for PoscheckResult

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("precheck", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PoscheckResult",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "overall_status",
                    models.CharField(
                        choices=[
                            ("completed", "Completed"),
                            ("inconsistent", "Inconsistent"),
                            ("execution_failure", "Execution failure"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("validations", models.JSONField(blank=True, default=list)),
                ("extracted", models.JSONField(blank=True, default=dict)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("error_title", models.CharField(blank=True, default="", max_length=255)),
                ("error_detail", models.TextField(blank=True, default="")),
                (
                    "processed_at",
                    models.DateTimeField(db_index=True, default=django.utils.timezone.now),
                ),
                (
                    "analysis",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="poscheck_result",
                        to="precheck.checkanalysis",
                    ),
                ),
            ],
            options={
                "ordering": ("-processed_at",),
            },
        ),
    ]
