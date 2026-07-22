from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import QualityEvidence


def _value(payload, dotted_path):
    current = payload
    for token in dotted_path.split('.'):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _default_score(payload):
    for path in ('overall_score_pct', 'acceptance_rate_pct', 'score_pct'):
        try:
            return float(_value(payload, path))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return None


class Command(BaseCommand):
    help = 'Import an immutable JSON quality report summary into the internal application database.'

    def add_arguments(self, parser):
        parser.add_argument('--suite', required=True)
        parser.add_argument('--report', required=True, help='Path relative to STORAGE_PATH/MEDIA_ROOT')
        parser.add_argument('--score-path')
        parser.add_argument('--target-pct', type=float, default=95.0)

    def handle(self, *args, **options):
        storage_root = Path(settings.MEDIA_ROOT).resolve()
        report_path = (storage_root / options['report']).resolve()
        try:
            report_path.relative_to(storage_root)
        except ValueError as exc:
            raise CommandError('Report path must stay inside STORAGE_PATH') from exc
        if not report_path.is_file():
            raise CommandError(f'Report not found: {report_path}')

        report_bytes = report_path.read_bytes()
        try:
            payload = json.loads(report_bytes.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandError(f'Report must be UTF-8 JSON: {type(exc).__name__}') from exc
        if not isinstance(payload, dict) or not isinstance(payload.get('passed'), bool):
            raise CommandError('Report must contain a boolean passed field')

        if options['score_path']:
            try:
                score_pct = float(_value(payload, options['score_path']))
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise CommandError(f'Invalid --score-path: {options["score_path"]}') from exc
        else:
            score_pct = _default_score(payload)

        digest = hashlib.sha256(report_bytes).hexdigest()
        relative_path = report_path.relative_to(storage_root).as_posix()
        run_id = str(payload.get('generated_at') or payload.get('run_id') or digest[:16])[:120]
        metadata = {
            key: payload[key]
            for key in (
                'schema_version', 'generated_at', 'case_count', 'correct_count', 'task_scores', 'gates',
                'runtime_contract_case_count', 'requested_route', 'selected_route', 'selection_reason',
                'seed_match', 'elapsed_seconds', 'independent_evaluation', 'model_revision', 'device',
            )
            if key in payload
        }
        defaults = {
            'run_id': run_id,
            'passed': payload['passed'],
            'score_pct': score_pct,
            'target_pct': options['target_pct'],
            'evaluator': str(payload.get('evaluator') or '')[:160],
            'model_name': str(payload.get('model_id') or payload.get('model') or '')[:255],
            'report_path': relative_path,
            'metadata': metadata,
        }
        with transaction.atomic(using='default'):
            evidence, created = QualityEvidence.objects.get_or_create(
                suite=options['suite'], report_sha256=digest, defaults=defaults,
            )
        self.stdout.write(json.dumps({
            'id': str(evidence.id), 'created': created, 'suite': evidence.suite,
            'passed': evidence.passed, 'score_pct': evidence.score_pct,
            'report_sha256': evidence.report_sha256,
        }, ensure_ascii=False))
