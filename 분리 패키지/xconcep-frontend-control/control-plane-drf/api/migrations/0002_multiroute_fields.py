from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0001_initial")]

    operations = [
        migrations.AddField(model_name="project", name="design_state", field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name="project", name="generation_plan", field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name="project", name="validation_report", field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name="project", name="validation_grade", field=models.CharField(default="concept", max_length=40)),
        migrations.AddField(model_name="project", name="output_goal", field=models.CharField(default="auto", max_length=40)),
        migrations.AddField(model_name="project", name="quality_profile", field=models.CharField(default="standard", max_length=40)),
        migrations.AddField(model_name="project", name="generation_history", field=models.JSONField(blank=True, default=list)),
    ]
