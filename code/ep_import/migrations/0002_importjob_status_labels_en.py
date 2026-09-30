from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ep_import", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="importjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("success", "Success"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
    ]
