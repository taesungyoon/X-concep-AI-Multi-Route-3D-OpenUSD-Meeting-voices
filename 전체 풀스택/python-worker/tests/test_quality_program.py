from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest


STACK_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, STACK_ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deterministic_sample_is_stable_and_unique():
    sync = _load("quality_sync", "sync-quality-datasets.py")
    first = sync.deterministic_indices(1632, 64, 20260721, "parti-prompts")
    second = sync.deterministic_indices(1632, 64, 20260721, "parti-prompts")
    assert first == second
    assert first == sorted(first)
    assert len(first) == len(set(first)) == 64
    assert first != sync.deterministic_indices(1632, 64, 20260722, "parti-prompts")


def test_required_not_measured_never_passes_gate():
    runner = _load("quality_runner", "run-quality-program.py")
    tier = {
        "phase_minimum_score_pct": {"3": 100},
        "phase1_critical_checks": [],
    }
    phase = runner.summarize_phase(3, [runner._check("semantic", None, "missing", required=True)], tier)
    assert phase["passed"] is False
    assert phase["score_pct"] == 0


def test_optional_not_measured_does_not_reduce_readiness_score():
    runner = _load("quality_runner_optional", "run-quality-program.py")
    tier = {
        "phase_minimum_score_pct": {"4": 100},
        "phase1_critical_checks": [],
    }
    checks = [
        runner._check("adapter", True, "ready"),
        runner._check("full_corpus", None, "opt-in", required=False),
    ]
    phase = runner.summarize_phase(4, checks, tier)
    assert phase["passed"] is True
    assert phase["score_pct"] == 100


def test_zip_sync_rejects_path_traversal(tmp_path):
    sync = _load("quality_sync_zip", "sync-quality-datasets.py")
    archive = tmp_path / "fixture.zip"
    with ZipFile(archive, "w") as target:
        target.writestr("../escape.stp", "ISO-10303-21;")
    dataset = {
        "archive_member_pattern": ".*",
        "archive_max_member_bytes": 1024,
        "archive_max_total_bytes": 2048,
    }
    with pytest.raises(RuntimeError, match="Unsafe ZIP member"):
        sync._safe_zip_records(dataset, archive, tmp_path / "dataset", tmp_path)
    assert not (tmp_path.parent / "escape.stp").exists()


def test_semantic_report_is_bound_to_dataset_model_and_images(tmp_path):
    runner = _load("quality_runner_semantic", "run-quality-program.py")
    dataset_root = tmp_path / "datasets"
    image_root = tmp_path / "images"
    image_root.mkdir(parents=True)
    image_path = image_root / "case.png"
    image_path.write_bytes(b"pinned-image-bytes")
    prompt_sha = hashlib.sha256(b"a cow").hexdigest()
    image_manifest = image_root / "manifest.jsonl"
    image_manifest.write_text(
        json.dumps({"dataset": "geneval", "row_index": 1, "path": "case.png", "prompt_sha256": prompt_sha}) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "toolchain_references": [
            {
                "id": "owlvit-geneval-evaluator",
                "model_id": "google/owlvit-base-patch32",
                "revision": "model-revision",
                "license": "Apache-2.0",
            }
        ]
    }
    lock_map = {
        "geneval": {
            "revision": "dataset-revision",
            "artifacts": [{"sha256": "dataset-sha"}],
            "sample": {"selected_indices": [1]},
        }
    }
    gates = {
        "thresholds": {"geneval_required_tags": ["single_object"], "image_semantic_score_pct": 80.0},
        "semantic_evaluator": {
            "toolchain_id": "owlvit-geneval-evaluator",
            "evaluator": "owlvit-geneval-compatible-v1",
            "official_geneval_score": False,
        },
    }
    tier = {"semantic_score_required": True, "semantic_min_result_count": 1}
    report_path = image_root / "semantic.json"
    report = {
        "evaluator": "owlvit-geneval-compatible-v1",
        "official_geneval_score": False,
        "model_id": "google/owlvit-base-patch32",
        "model_revision": "model-revision",
        "model_license": "Apache-2.0",
        "dataset_revision": "dataset-revision",
        "dataset_source_sha256": "dataset-sha",
        "image_manifest_sha256": runner.sha256_file(image_manifest),
        "case_count": 1,
        "correct_count": 1,
        "overall_score_pct": 100.0,
        "task_scores": {"single_object": {"count": 1, "correct": 1}},
        "cases": [
            {
                "dataset": "geneval",
                "row_index": 1,
                "prompt_sha256": prompt_sha,
                "image_sha256": runner.sha256_file(image_path),
                "correct": True,
            }
        ],
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    checks = runner._evaluate_semantic_report(manifest, dataset_root, lock_map, gates, tier, image_manifest, report_path)
    assert [check["status"] for check in checks] == ["passed", "passed", "passed"]

    image_path.write_bytes(b"tampered")
    checks = runner._evaluate_semantic_report(manifest, dataset_root, lock_map, gates, tier, image_manifest, report_path)
    assert checks[0]["status"] == "failed"
