import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0002_multiroute_fields")]

    operations = [
        migrations.CreateModel(
            name="QualityEvidence",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("suite", models.CharField(max_length=80)),
                ("run_id", models.CharField(max_length=120)),
                ("passed", models.BooleanField()),
                ("score_pct", models.FloatField(blank=True, null=True)),
                ("target_pct", models.FloatField(default=95.0)),
                ("evaluator", models.CharField(blank=True, max_length=160)),
                ("model_name", models.CharField(blank=True, max_length=255)),
                ("report_path", models.CharField(max_length=1000)),
                ("report_sha256", models.CharField(max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "indexes": [models.Index(fields=["suite", "-created_at"], name="quality_suite_created_idx")],
                "constraints": [models.UniqueConstraint(fields=("suite", "report_sha256"), name="quality_evidence_suite_sha_uniq")],
            },
        ),
    ]
