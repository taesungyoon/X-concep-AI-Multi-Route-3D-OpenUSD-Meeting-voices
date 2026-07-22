import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from api.models import QualityEvidence


class QualityEvidenceImportTests(TestCase):
    def test_import_is_idempotent_and_keeps_report_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'semantic.json'
            report.write_text(json.dumps({
                'schema_version': 1,
                'generated_at': '2026-07-22T00:00:00Z',
                'passed': True,
                'overall_score_pct': 96.5,
                'evaluator': 'grounding-dino-geneval-compatible-v1',
                'model_id': 'pinned/model',
                'case_count': 120,
            }), encoding='utf-8')
            output = io.StringIO()
            with override_settings(MEDIA_ROOT=root):
                call_command('import_quality_evidence', suite='image-semantic', report='semantic.json', stdout=output)
                call_command('import_quality_evidence', suite='image-semantic', report='semantic.json', stdout=output)
            evidence = QualityEvidence.objects.get()
            assert evidence.passed is True
            assert evidence.score_pct == 96.5
            assert evidence.metadata['case_count'] == 120
            assert QualityEvidence.objects.count() == 1

    def test_import_rejects_path_outside_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            with override_settings(MEDIA_ROOT=Path(directory)):
                with self.assertRaises(CommandError):
                    call_command('import_quality_evidence', suite='image-semantic', report='../outside.json')
