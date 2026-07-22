from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quality_metrics import binary_agreement, binary_summary


STACK_ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _key(row: dict[str, Any]) -> str:
    return f"{row.get('dataset')}:{int(row.get('row_index', -1))}:{int(row.get('benchmark_seed', -1))}"


def compare(
    raw_report: dict[str, Any],
    rewritten_report: dict[str, Any],
    manifest_rows: list[dict[str, Any]],
    minimum_score_pct: float,
    minimum_pairs: int,
    candidate_mode: str = "rewritten",
    candidate_manifest_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw = {_key(row): bool(row["correct"]) for row in raw_report.get("cases") or []}
    rewritten = {_key(row): bool(row["correct"]) for row in rewritten_report.get("cases") or []}
    raw_manifest = {_key(row): row for row in manifest_rows if row.get("prompt_mode") == "raw"}
    candidate_rows = candidate_manifest_rows if candidate_manifest_rows is not None else manifest_rows
    rewritten_manifest = {_key(row): row for row in candidate_rows if row.get("prompt_mode") == candidate_mode}
    shared = sorted(set(raw) & set(rewritten))
    seed_mismatches = [key for key in shared if raw_manifest.get(key, {}).get("seed") != rewritten_manifest.get(key, {}).get("seed")]
    raw_summary = binary_summary(raw[key] for key in shared)
    rewritten_summary = binary_summary(rewritten[key] for key in shared)
    agreement = binary_agreement({key: raw[key] for key in shared}, {key: rewritten[key] for key in shared})
    passed = (
        len(shared) >= minimum_pairs and not seed_mismatches
        and raw_summary["score_pct"] >= minimum_score_pct
        and rewritten_summary["score_pct"] >= minimum_score_pct
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "minimum_score_pct": minimum_score_pct,
        "minimum_pairs": minimum_pairs,
        "candidate_mode": candidate_mode,
        "paired_cases": len(shared),
        "identical_noise_seed": not seed_mismatches,
        "seed_mismatch_sample": seed_mismatches[:20],
        "raw": raw_summary,
        "rewritten": rewritten_summary,
        "rewritten_delta_pct": round(rewritten_summary["score_pct"] - raw_summary["score_pct"], 4),
        "agreement": agreement,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare raw and rewritten semantic scores on identical cases and noise seeds")
    parser.add_argument("--raw-report", type=Path, required=True)
    parser.add_argument("--rewritten-report", "--candidate-report", dest="candidate_report", type=Path, required=True)
    parser.add_argument("--image-manifest", "--raw-manifest", dest="raw_manifest", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--candidate-mode", default="rewritten")
    parser.add_argument("--minimum-score-pct", type=float, default=95.0)
    parser.add_argument("--minimum-pairs", type=int, default=60)
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "image-holdout" / "ab-report.json")
    args = parser.parse_args()
    report = compare(
        json.loads(args.raw_report.read_text(encoding="utf-8")),
        json.loads(args.candidate_report.read_text(encoding="utf-8")),
        _read_jsonl(args.raw_manifest), args.minimum_score_pct, args.minimum_pairs,
        candidate_mode=args.candidate_mode,
        candidate_manifest_rows=_read_jsonl(args.candidate_manifest) if args.candidate_manifest else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "paired_cases", "identical_noise_seed", "rewritten_delta_pct")}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
