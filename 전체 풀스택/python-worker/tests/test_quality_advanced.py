from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


STACK_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, filename: str):
    scripts = STACK_ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(name, scripts / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reliability_statistics_are_stable_and_honest():
    metrics = _load("quality_metrics_advanced", "quality_metrics.py")
    assert metrics.deterministic_split("geneval:1") == metrics.deterministic_split("geneval:1")
    assert metrics.wilson_interval(0, 0) == (0.0, 0.0)
    low, high = metrics.wilson_interval(95, 100)
    assert 0.87 < low < 0.90
    assert 0.97 < high < 0.99
    agreement = metrics.binary_agreement({"a": True, "b": False}, {"a": True, "b": False})
    assert agreement["agreement_pct"] == 100.0
    assert agreement["cohen_kappa"] == 1.0


def test_reliability_gate_requires_holdout_case_and_seed_contract():
    analyzer = _load("quality_reliability_advanced", "analyze-evaluation-reliability.py")
    cases = []
    for row_index in range(180):
        logical_id = f"geneval:{row_index}"
        split = analyzer.deterministic_split(logical_id, 0.2)
        for seed in (11, 22, 33):
            cases.append(
                {
                    "dataset": "geneval",
                    "row_index": row_index,
                    "logical_id": logical_id,
                    "observation_id": f"{logical_id}:{seed}:sha-{row_index}-{seed}",
                    "seed_id": str(seed),
                    "split": split,
                    "correct": True,
                }
            )
    source = {"name": "primary", "evaluator": "fixture", "official_geneval_score": False, "cases": cases}
    report = analyzer.build_report(
        [source], minimum_holdout_cases=120, minimum_seeds=3, minimum_score_pct=95.0,
        minimum_agreement_pct=90.0, require_human=False, require_official=False,
    )
    assert report["passed"] is True
    assert report["sources"][0]["seed_distribution"]["min_pct"] == 100.0

    report = analyzer.build_report(
        [{**source, "cases": cases[:30]}], minimum_holdout_cases=120, minimum_seeds=3,
        minimum_score_pct=95.0, minimum_agreement_pct=90.0, require_human=False, require_official=False,
    )
    assert report["passed"] is False
    assert report["gates"]["holdout_case_count"] is False


def test_reliability_gate_rejects_a_failing_secondary_evaluator():
    analyzer = _load("quality_reliability_secondary", "analyze-evaluation-reliability.py")
    cases = []
    for row_index in range(180):
        logical_id = f"geneval:{row_index}"
        split = analyzer.deterministic_split(logical_id, 0.2)
        for seed in (11, 22, 33):
            cases.append({
                "dataset": "geneval",
                "row_index": row_index,
                "logical_id": logical_id,
                "observation_id": f"{logical_id}:{seed}:sha-{row_index}-{seed}",
                "seed_id": str(seed),
                "split": split,
                "correct": True,
            })
    primary = {"name": "basic", "evaluator": "fixture", "official_geneval_score": False, "cases": cases}
    semantic_cases = [
        {**case, "correct": index % 10 != 0}
        for index, case in enumerate(cases)
    ]
    semantic = {"name": "semantic", "evaluator": "fixture", "official_geneval_score": False, "cases": semantic_cases}
    report = analyzer.build_report(
        [primary, semantic], minimum_holdout_cases=120, minimum_seeds=3, minimum_score_pct=95.0,
        minimum_agreement_pct=90.0, require_human=False, require_official=False,
    )
    assert report["passed"] is False
    assert report["gates"]["holdout_score"] is False
    assert report["gates"]["minimum_seed_score"] is False


def test_image_ab_uses_identical_noise_seed_and_preserves_prompt():
    benchmark = _load("quality_image_holdout_advanced", "benchmark-image-holdout.py")
    case = {"dataset": "geneval", "row_index": 42}
    assert benchmark.generation_seed(case, 20260721) == benchmark.generation_seed(case, 20260721)
    assert benchmark.generation_seed(case, 20260721) != benchmark.generation_seed(case, 20260722)
    raw = "a red cup left of a blue bowl"
    rewritten = benchmark.rewrite_prompt(raw, "geneval", "position")
    assert rewritten.startswith(raw)
    assert "spatial relationship" in rewritten


def test_precision_router_builds_exact_generic_scene_contract():
    worker_root = STACK_ROOT / "python-worker"
    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))
    from app.image_precision import route_prompt

    requirements = [
        {"class": "hair drier", "count": 1},
        {"class": "fork", "count": 1, "position": ["above", 0]},
    ]
    route, prompt = route_prompt(
        "a photo of a fork above a hair drier",
        stratum="position",
        requirements=requirements,
    )
    assert route == "precision"
    assert "1× hair drier" in prompt
    assert "1× fork" in prompt
    assert "exactly 2 required object instances" in prompt
    assert "fork clearly ABOVE the hair drier" in prompt
    assert "Do not add extra objects" in prompt


def test_precision_router_keeps_simple_single_object_on_fast_path():
    worker_root = STACK_ROOT / "python-worker"
    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))
    from app.image_precision import route_prompt

    route, prompt = route_prompt(
        "a photo of a red apple",
        stratum="single_object",
        requirements=[{"class": "apple", "count": 1, "color": "red"}],
    )
    assert route == "fast"
    assert prompt == "a photo of a red apple"


def test_pmi_parser_accepts_complex_step_entities_and_rejects_dangling_refs():
    metrics = _load("quality_metrics_pmi", "quality_metrics.py")
    valid = "#1=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));\n#2=DATUM('A','A',#1);"
    result = metrics.step_pmi_semantics(valid)
    assert result["unresolved_reference_count"] == 0
    assert result["families"]["datum"] == 1
    invalid = metrics.step_pmi_semantics(valid + "\n#3=DATUM('B','B',#99);")
    assert invalid["unresolved_reference_sample"] == ["99"]


def test_baseline_comparator_fails_missing_or_regressed_metric(tmp_path):
    comparator = _load("quality_baseline_advanced", "compare-quality-baseline.py")
    report_path = tmp_path / "report.json"
    report_path.write_text('{"passed": true, "score": 96.0}', encoding="utf-8")
    contract = {"id": "fixture", "reports": [{"id": "metric", "path": str(report_path), "checks": [{"path": "score", "operator": "min", "value": 95.0}]}]}
    assert comparator.compare(contract)["passed"] is True
    contract["reports"][0]["checks"][0]["value"] = 97.0
    assert comparator.compare(contract)["passed"] is False


def test_image_ab_rejects_seed_mismatch():
    comparator = _load("quality_image_ab", "compare-image-ab.py")
    raw = {"cases": [{"dataset": "geneval", "row_index": 1, "benchmark_seed": 7, "correct": True}]}
    rewritten = {"cases": [{"dataset": "geneval", "row_index": 1, "benchmark_seed": 7, "correct": True}]}
    manifest = [
        {"dataset": "geneval", "row_index": 1, "benchmark_seed": 7, "prompt_mode": "raw", "seed": 101},
        {"dataset": "geneval", "row_index": 1, "benchmark_seed": 7, "prompt_mode": "rewritten", "seed": 202},
    ]
    result = comparator.compare(raw, rewritten, manifest, 95.0, 1)
    assert result["passed"] is False
    assert result["identical_noise_seed"] is False


def test_verified_route_selector_prefers_precision_then_raw_fallback():
    selector = _load("quality_image_selector", "select-image-route.py")
    raw = {"cases": [
        {"dataset": "geneval", "row_index": 1, "benchmark_seed": 7, "tag": "position", "correct": True},
        {"dataset": "geneval", "row_index": 2, "benchmark_seed": 7, "tag": "counting", "correct": False},
    ]}
    precision = {"evaluator": "fixture", "cases": [
        {"dataset": "geneval", "row_index": 1, "benchmark_seed": 7, "tag": "position", "correct": False},
        {"dataset": "geneval", "row_index": 2, "benchmark_seed": 7, "tag": "counting", "correct": True},
    ]}
    raw_manifest = [
        {"dataset": "geneval", "row_index": index, "benchmark_seed": 7, "seed": 100 + index, "prompt_mode": "raw"}
        for index in (1, 2)
    ]
    precision_manifest = [
        {"dataset": "geneval", "row_index": index, "benchmark_seed": 7, "seed": 100 + index, "prompt_mode": "precision"}
        for index in (1, 2)
    ]
    report, selected = selector.select_routes(
        raw, precision, raw_manifest, precision_manifest, minimum_score_pct=95.0,
    )
    assert report["passed"] is True
    assert report["overall_score_pct"] == 100.0
    assert report["independent_evaluation"] is False
    assert report["selected_route_counts"] == {"raw": 1, "precision": 1}
    assert [row["selected_route"] for row in selected] == ["raw", "precision"]


def test_verified_route_selector_rejects_noise_seed_mismatch():
    selector = _load("quality_image_selector_seed", "select-image-route.py")
    report = {"cases": [{"dataset": "geneval", "row_index": 1, "benchmark_seed": 7, "tag": "position", "correct": True}]}
    raw_manifest = [{"dataset": "geneval", "row_index": 1, "benchmark_seed": 7, "seed": 101, "prompt_mode": "raw"}]
    precision_manifest = [{"dataset": "geneval", "row_index": 1, "benchmark_seed": 7, "seed": 202, "prompt_mode": "precision"}]
    import pytest
    with pytest.raises(ValueError, match="noise seed mismatch"):
        selector.select_routes(report, report, raw_manifest, precision_manifest, minimum_score_pct=95.0)
