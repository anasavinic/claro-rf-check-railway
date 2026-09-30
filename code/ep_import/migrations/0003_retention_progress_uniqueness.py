from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ep_import", "0002_importjob_status_labels_en"),
    ]

    operations = [
        migrations.AddField(
            model_name="importjob",
            name="content_sha256",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="importjob",
            name="expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="importjob",
            name="rows_processed",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="importjob",
            name="rows_total",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="importjob",
            name="stage",
            field=models.CharField(
                blank=True,
                choices=[
                    ("queued", "Queued"),
                    ("validating", "Validating"),
                    ("persisting", "Persisting"),
                    ("done", "Done"),
                    ("failed", "Failed"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="importjob",
            name="task_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddConstraint(
            model_name="epcell",
            constraint=models.UniqueConstraint(
                fields=("job", "technology", "site_name", "cell_name"),
                name="uniq_epcell_job_tech_site_cell",
            ),
        ),
    ]
