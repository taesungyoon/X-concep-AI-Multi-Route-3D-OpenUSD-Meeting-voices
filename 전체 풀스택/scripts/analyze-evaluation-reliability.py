from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quality_metrics import binary_agreement, binary_summary, deterministic_split, score_distribution


STACK_ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _parse_named_path(value: str) -> tuple[str, Path]:
    name, separator, raw_path = value.partition("=")
    if not separator or not name.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    return name.strip(), Path(raw_path.strip()).resolve()


def _logical_id(case: dict[str, Any]) -> str:
    return f"{case.get('dataset', 'unknown')}:{int(case.get('row_index', -1))}"


def _observation_id(case: dict[str, Any], report: dict[str, Any]) -> str:
    image_identity = case.get("image_sha256") or case.get("path")
    seed_identity = case.get("benchmark_seed", case.get("run_seed", case.get("seed", report.get("seed", "unknown"))))
    return f"{_logical_id(case)}:{seed_identity}:{image_identity or 'unknown-image'}"


def _seed_id(case: dict[str, Any], report: dict[str, Any]) -> str:
    return str(case.get("benchmark_seed", case.get("run_seed", case.get("seed", report.get("seed", "unknown")))))


def normalize_report(name: str, path: Path, calibration_fraction: float, prompt_mode: str | None = None) -> dict[str, Any]:
    if path.suffix.lower() == ".jsonl":
        report = {
            "evaluator": "basic-image-quality-v1",
            "official_geneval_score": False,
            "cases": [
                {**row, "correct": row.get("basic_quality_passed")}
                for row in _read_jsonl(path)
                if row.get("basic_quality_passed") is not None
            ],
        }
    else:
        report = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for source in report.get("cases") or []:
        if prompt_mode and source.get("prompt_mode", "raw") != prompt_mode:
            continue
        if source.get("correct") is None and source.get("passed") is None:
            continue
        case = dict(source)
        case["correct"] = bool(source.get("correct", source.get("passed")))
        case["logical_id"] = _logical_id(case)
        case["observation_id"] = _observation_id(case, report)
        case["seed_id"] = _seed_id(case, report)
        case["split"] = deterministic_split(case["logical_id"], calibration_fraction)
        cases.append(case)
    return {
        "name": name,
        "path": str(path),
        "evaluator": report.get("evaluator", name),
        "official_geneval_score": bool(report.get("official_geneval_score", False)),
        "model_id": report.get("model_id"),
        "model_revision": report.get("model_revision"),
        "cases": cases,
    }


def load_human_labels(path: Path | None, calibration_fraction: float) -> dict[str, Any] | None:
    if path is None:
        return None
    cases = []
    for source in _read_jsonl(path):
        if source.get("correct") is None:
            continue
        case = dict(source)
        case["correct"] = bool(case["correct"])
        case["logical_id"] = _logical_id(case)
        case["observation_id"] = str(case.get("observation_id") or _observation_id(case, {}))
        case["seed_id"] = str(case.get("benchmark_seed", case.get("run_seed", case.get("seed", "unknown"))))
        case["split"] = deterministic_split(case["logical_id"], calibration_fraction)
        cases.append(case)
    return {"name": "human", "path": str(path), "evaluator": "human-review", "official_geneval_score": False, "cases": cases}


def summarize_source(source: dict[str, Any]) -> dict[str, Any]:
    cases = source["cases"]
    split_summaries = {}
    for split in ("calibration", "holdout"):
        subset = [case for case in cases if case["split"] == split]
        split_summaries[split] = {
            **binary_summary(case["correct"] for case in subset),
            "logical_case_count": len({case["logical_id"] for case in subset}),
        }
    seed_summaries = {}
    for seed_id in sorted({case["seed_id"] for case in cases}):
        subset = [case for case in cases if case["seed_id"] == seed_id and case["split"] == "holdout"]
        seed_summaries[seed_id] = binary_summary(case["correct"] for case in subset)
    return {
        "name": source["name"],
        "evaluator": source["evaluator"],
        "official_geneval_score": source["official_geneval_score"],
        "model_id": source.get("model_id"),
        "model_revision": source.get("model_revision"),
        "all": binary_summary(case["correct"] for case in cases),
        "splits": split_summaries,
        "seeds": seed_summaries,
        "seed_distribution": score_distribution(value["score_pct"] for value in seed_summaries.values()),
    }


def build_report(
    sources: list[dict[str, Any]],
    *,
    minimum_holdout_cases: int,
    minimum_seeds: int,
    minimum_score_pct: float,
    minimum_agreement_pct: float,
    require_human: bool,
    require_official: bool,
) -> dict[str, Any]:
    if not sources:
        raise ValueError("at least one evaluator report is required")
    summaries = [summarize_source(source) for source in sources]
    comparisons = []
    mappings = {
        source["name"]: {case["observation_id"]: case["correct"] for case in source["cases"] if case["split"] == "holdout"}
        for source in sources
    }
    for left_index, left in enumerate(sources):
        for right in sources[left_index + 1 :]:
            comparisons.append({"left": left["name"], "right": right["name"], **binary_agreement(mappings[left["name"]], mappings[right["name"]])})

    primary = summaries[0]
    human_comparisons = [item for item in comparisons if "human" in {item["left"], item["right"]}]
    official_available = any(source["official_geneval_score"] for source in sources)
    gates = {
        "holdout_case_count": primary["splits"]["holdout"]["logical_case_count"] >= minimum_holdout_cases,
        "seed_count": all(len(summary["seeds"]) >= minimum_seeds for summary in summaries),
        "holdout_score": all(
            summary["splits"]["holdout"]["score_pct"] >= minimum_score_pct
            for summary in summaries
        ),
        "minimum_seed_score": all(
            bool(summary["seeds"])
            and summary["seed_distribution"]["min_pct"] >= minimum_score_pct
            for summary in summaries
        ),
        "human_agreement": (
            bool(human_comparisons) and all((item["agreement_pct"] or 0.0) >= minimum_agreement_pct for item in human_comparisons)
        ) if require_human else None,
        "official_geneval": official_available if require_official else None,
    }
    required_gate_values = [value for value in gates.values() if value is not None]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract": {
            "minimum_holdout_cases": minimum_holdout_cases,
            "minimum_seeds": minimum_seeds,
            "minimum_score_pct": minimum_score_pct,
            "minimum_human_agreement_pct": minimum_agreement_pct,
            "require_human": require_human,
            "require_official_geneval": require_official,
        },
        "passed": all(required_gate_values),
        "gates": gates,
        "sources": summaries,
        "pairwise_agreement": comparisons,
        "measurement_status": {
            "human_labels": any(source["name"] == "human" for source in sources),
            "official_geneval": official_available,
        },
    }


def write_human_template(path: Path, source: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    unique: dict[str, dict[str, Any]] = {}
    for case in source["cases"]:
        unique.setdefault(
            case["observation_id"],
            {
                "dataset": case.get("dataset"),
                "row_index": case.get("row_index"),
                "benchmark_seed": case["seed_id"],
                "image_sha256": case.get("image_sha256"),
                "observation_id": case["observation_id"],
                "correct": None,
                "reviewer": "",
                "note": "",
            },
        )
    with path.open("w", encoding="utf-8", newline="\n") as target:
        for row in unique.values():
            target.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Evaluation Reliability Report",
        "",
        f"- Result: **{'PASS' if report['passed'] else 'FAIL'}**",
        f"- Human labels measured: `{report['measurement_status']['human_labels']}`",
        f"- Official GenEval measured: `{report['measurement_status']['official_geneval']}`",
        "",
        "| Evaluator | Holdout logical cases | Holdout score | Wilson 95% CI | Seeds | Min seed | Variance |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for source in report["sources"]:
        holdout = source["splits"]["holdout"]
        distribution = source["seed_distribution"]
        interval = "–".join(f"{value:.2f}%" for value in holdout["wilson_95ci_pct"])
        lines.append(
            f"| {source['name']} | {holdout['logical_case_count']} | {holdout['score_pct']:.2f}% | {interval} | "
            f"{distribution['count']} | {distribution['min_pct']:.2f}% | {distribution['variance']:.6f} |"
        )
    if report["pairwise_agreement"]:
        lines.extend(["", "| Pair | Shared observations | Agreement | Cohen's κ |", "|---|---:|---:|---:|"])
        for item in report["pairwise_agreement"]:
            agreement = "-" if item["agreement_pct"] is None else f"{item['agreement_pct']:.2f}%"
            kappa = "-" if item["cohen_kappa"] is None else f"{item['cohen_kappa']:.4f}"
            lines.append(f"| {item['left']} ↔ {item['right']} | {item['shared_cases']} | {agreement} | {kappa} |")
    lines.extend(["", "95% threshold is an automated quality contract, not a manufacturing or human-perception guarantee.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure holdout, repeated-seed, evaluator, and human-label reliability")
    parser.add_argument("--report", action="append", type=_parse_named_path, required=True, metavar="NAME=PATH")
    parser.add_argument("--human-labels", type=Path)
    parser.add_argument("--prompt-mode", choices=("raw", "rewritten", "precision", "selected"))
    parser.add_argument("--write-human-template", type=Path)
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "reliability")
    parser.add_argument("--calibration-fraction", type=float, default=0.2)
    parser.add_argument("--minimum-holdout-cases", type=int, default=120)
    parser.add_argument("--minimum-seeds", type=int, default=3)
    parser.add_argument("--minimum-score-pct", type=float, default=95.0)
    parser.add_argument("--minimum-agreement-pct", type=float, default=90.0)
    parser.add_argument("--require-human", action="store_true")
    parser.add_argument("--require-official-geneval", action="store_true")
    args = parser.parse_args()

    sources = [normalize_report(name, path, args.calibration_fraction, args.prompt_mode) for name, path in args.report]
    human = load_human_labels(args.human_labels.resolve() if args.human_labels else None, args.calibration_fraction)
    if human:
        sources.append(human)
    if args.write_human_template:
        write_human_template(args.write_human_template.resolve(), sources[0])
    report = build_report(
        sources,
        minimum_holdout_cases=args.minimum_holdout_cases,
        minimum_seeds=args.minimum_seeds,
        minimum_score_pct=args.minimum_score_pct,
        minimum_agreement_pct=args.minimum_agreement_pct,
        require_human=args.require_human,
        require_official=args.require_official_geneval,
    )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "report.md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "gates": report["gates"]}, ensure_ascii=False))
    print(f"Report: {output / 'report.md'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
