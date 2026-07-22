from django.db import models
import uuid

class Project(models.Model):
    CATEGORY_CHOICES = [('equipment','equipment'),('module','module'),('part','part')]
    id = models.CharField(primary_key=True, max_length=32)
    prompt = models.TextField(blank=True)
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default='equipment')
    status = models.CharField(max_length=40, default='created')
    progress = models.PositiveSmallIntegerField(default=0)
    step = models.CharField(max_length=16, default='input')
    selected_2d_id = models.CharField(max_length=80, blank=True, null=True)
    revision = models.PositiveIntegerField(default=1)
    analysis = models.JSONField(blank=True, null=True)
    pipeline = models.JSONField(blank=True, null=True)
    result_3d = models.JSONField(blank=True, null=True)
    design_state = models.JSONField(blank=True, null=True)
    generation_plan = models.JSONField(blank=True, null=True)
    validation_report = models.JSONField(blank=True, null=True)
    validation_grade = models.CharField(max_length=40, default='concept')
    output_goal = models.CharField(max_length=40, default='auto')
    quality_profile = models.CharField(max_length=40, default='standard')
    generation_history = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Asset(models.Model):
    project = models.ForeignKey(Project, related_name='assets', on_delete=models.CASCADE)
    kind = models.CharField(max_length=40)
    original_name = models.CharField(max_length=255, blank=True)
    relative_path = models.CharField(max_length=1000)
    public_url = models.CharField(max_length=1000)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Concept2D(models.Model):
    project = models.ForeignKey(Project, related_name='concepts', on_delete=models.CASCADE)
    concept_id = models.CharField(max_length=80)
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    public_url = models.CharField(max_length=1000)
    relative_path = models.CharField(max_length=1000)
    metadata = models.JSONField(default=dict, blank=True)
    class Meta:
        unique_together = [('project', 'concept_id')]

class MeetingSession(models.Model):
    project = models.OneToOneField(Project, related_name='meeting', on_delete=models.CASCADE)
    status = models.CharField(max_length=40, default='idle')
    transcript = models.TextField(blank=True)
    analysis = models.JSONField(blank=True, null=True)
    chunk_count = models.PositiveIntegerField(default=0)
    provider = models.CharField(max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

class TranscriptSegment(models.Model):
    meeting = models.ForeignKey(MeetingSession, related_name='segments', on_delete=models.CASCADE)
    chunk_index = models.PositiveIntegerField(default=0)
    start = models.FloatField(default=0)
    end = models.FloatField(default=0)
    speaker = models.CharField(max_length=80, default='SPEAKER_00')
    text = models.TextField()
    confidence = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

class GenerationJob(models.Model):
    STATUS_CHOICES = [('queued','queued'),('running','running'),('completed','completed'),('failed','failed')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, related_name='jobs', on_delete=models.CASCADE)
    job_type = models.CharField(max_length=40)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued')
    progress = models.PositiveSmallIntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(blank=True, null=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class QualityEvidence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    suite = models.CharField(max_length=80)
    run_id = models.CharField(max_length=120)
    passed = models.BooleanField()
    score_pct = models.FloatField(blank=True, null=True)
    target_pct = models.FloatField(default=95.0)
    evaluator = models.CharField(max_length=160, blank=True)
    model_name = models.CharField(max_length=255, blank=True)
    report_path = models.CharField(max_length=1000)
    report_sha256 = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['suite', 'report_sha256'], name='quality_evidence_suite_sha_uniq'),
        ]
        indexes = [
            models.Index(fields=['suite', '-created_at'], name='quality_suite_created_idx'),
        ]
