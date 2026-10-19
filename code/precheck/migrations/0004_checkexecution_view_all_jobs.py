# Generated manually for view_all_jobs custom permission.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("precheck", "0003_combined_check"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="checkexecution",
            options={
                "ordering": ("-created_at",),
                "permissions": (("view_all_jobs", "Can view all job executions"),),
            },
        ),
        migrations.AddIndex(
            model_name="checkexecution",
            index=models.Index(fields=["created_by", "created_at"], name="precheck_ch_created_19c995_idx"),
        ),
    ]
