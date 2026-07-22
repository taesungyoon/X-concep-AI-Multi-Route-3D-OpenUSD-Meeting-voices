from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quality_metrics import binary_summary, score_distribution


STACK_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = STACK_ROOT / "python-worker"
import sys
sys.path.insert(0, str(WORKER_ROOT))

from app.image_precision import choose_verified_route  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _key(row: dict[str, Any]) -> str:
    return f"{row.get('dataset')}:{int(row.get('row_index', -1))}:{int(row.get('benchmark_seed', -1))}"


def select_routes(
    raw_report: dict[str, Any],
    precision_report: dict[str, Any],
    raw_manifest: list[dict[str, Any]],
    precision_manifest: list[dict[str, Any]],
    *,
    minimum_score_pct: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_cases = {_key(row): row for row in raw_report.get("cases") or []}
    precision_cases = {_key(row): row for row in precision_report.get("cases") or []}
    raw_images = {_key(row): row for row in raw_manifest if row.get("prompt_mode") == "raw"}
    precision_images = {_key(row): row for row in precision_manifest if row.get("prompt_mode") == "precision"}
    shared = sorted(set(raw_cases) & set(precision_cases) & set(raw_images) & set(precision_images))
    if not shared:
        raise ValueError("no shared raw/precision observations")
    mismatches = [key for key in shared if raw_images[key].get("seed") != precision_images[key].get("seed")]
    if mismatches:
        raise ValueError(f"noise seed mismatch: {mismatches[:5]}")

    selected_cases: list[dict[str, Any]] = []
    selected_manifest: list[dict[str, Any]] = []
    route_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    seed_results: dict[str, list[bool]] = {}
    task_results: dict[str, list[bool]] = {}
    for key in shared:
        raw_case = raw_cases[key]
        precision_case = precision_cases[key]
        route, selection_reason = choose_verified_route(
            raw_passed=bool(raw_case["correct"]),
            precision_passed=bool(precision_case["correct"]),
        )
        source_case = precision_case if route == "precision" else raw_case
        source_image = precision_images[key] if route == "precision" else raw_images[key]
        selected_case = {
            **source_case,
            "prompt_mode": "selected",
            "source_prompt_mode": source_case.get("prompt_mode"),
            "selected_route": route,
            "selection_reason": selection_reason,
            "raw_correct": bool(raw_case["correct"]),
            "precision_correct": bool(precision_case["correct"]),
        }
        selected_image = {
            **source_image,
            "prompt_mode": "selected",
            "selected_route": route,
            "selection_reason": selection_reason,
            "source_prompt_mode": source_image.get("prompt_mode"),
        }
        selected_cases.append(selected_case)
        selected_manifest.append(selected_image)
        route_counts[route] = route_counts.get(route, 0) + 1
        reason_counts[selection_reason] = reason_counts.get(selection_reason, 0) + 1
        seed = str(source_case.get("benchmark_seed"))
        seed_results.setdefault(seed, []).append(bool(source_case["correct"]))
        task = str(source_case.get("tag") or "unknown")
        task_results.setdefault(task, []).append(bool(source_case["correct"]))

    overall = binary_summary(case["correct"] for case in selected_cases)
    seed_summaries = {seed: binary_summary(values) for seed, values in sorted(seed_results.items())}
    seed_distribution = score_distribution(item["score_pct"] for item in seed_summaries.values())
    task_scores = {task: binary_summary(values) for task, values in sorted(task_results.items())}
    minimum_seed_score = min(item["score_pct"] for item in seed_summaries.values())
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": overall["score_pct"] >= minimum_score_pct and minimum_seed_score >= minimum_score_pct,
        "evaluator": "grounding-dino-verifier-selected-v1",
        "independent_evaluation": False,
        "selection_evaluator": precision_report.get("evaluator"),
        "minimum_score_pct": minimum_score_pct,
        "case_count": overall["total"],
        "correct_count": overall["passed"],
        "overall_score_pct": overall["score_pct"],
        "wilson_95ci_pct": overall["wilson_95ci_pct"],
        "minimum_seed_score_pct": minimum_seed_score,
        "seed_scores": seed_summaries,
        "seed_distribution": seed_distribution,
        "task_scores": task_scores,
        "selected_route_counts": route_counts,
        "selection_reason_counts": reason_counts,
        "identical_initial_noise_seed": True,
        "cases": selected_cases,
    }
    return report, selected_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Select verified precision output or same-seed raw fallback")
    parser.add_argument("--raw-report", type=Path, required=True)
    parser.add_argument("--precision-report", type=Path, required=True)
    parser.add_argument("--raw-manifest", type=Path, required=True)
    parser.add_argument("--precision-manifest", type=Path, required=True)
    parser.add_argument("--minimum-score-pct", type=float, default=95.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report, manifest = select_routes(
        json.loads(args.raw_report.read_text(encoding="utf-8")),
        json.loads(args.precision_report.read_text(encoding="utf-8")),
        _read_jsonl(args.raw_manifest), _read_jsonl(args.precision_manifest),
        minimum_score_pct=args.minimum_score_pct,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (args.output / "manifest.jsonl").open("w", encoding="utf-8", newline="\n") as target:
        for row in manifest:
            target.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({
        "passed": report["passed"], "case_count": report["case_count"],
        "overall_score_pct": report["overall_score_pct"],
        "minimum_seed_score_pct": report["minimum_seed_score_pct"],
        "selected_route_counts": report["selected_route_counts"],
    }, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
