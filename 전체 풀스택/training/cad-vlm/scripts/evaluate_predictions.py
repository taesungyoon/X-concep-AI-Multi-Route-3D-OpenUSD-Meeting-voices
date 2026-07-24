from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from xconcep_cad_vlm.dataset import load_records, validate_dataset
from xconcep_cad_vlm.evaluation import evaluate_predictions


def _load_predictions(path: Path) -> dict[str, dict[str, Any] | None]:
    predictions: dict[str, dict[str, Any] | None] = {}
    if path.is_dir():
        for candidate in sorted(path.glob("*.json")):
            try:
                value = json.loads(candidate.read_text(encoding="utf-8"))
                record_id = str(value.get("id") or candidate.stem) if isinstance(value, dict) else candidate.stem
                predictions[record_id] = value if isinstance(value, dict) else None
            except (OSError, json.JSONDecodeError):
                predictions[candidate.stem] = None
        return predictions
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid prediction JSONL at line {line_number}: {exc}") from exc
        if not isinstance(value, dict) or not str(value.get("id") or "").strip():
            raise ValueError(f"prediction line {line_number} requires an id")
        prediction = value.get("prediction", value.get("design_spec", value))
        predictions[str(value["id"])] = prediction if isinstance(prediction, dict) else None
    return predictions


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate CAD VLM predictions on an independent split")
    parser.add_argument("--dataset", default=str(PACKAGE_ROOT / "data" / "examples"))
    parser.add_argument("--predictions", type=Path, required=True, help="Directory of <id>.json files or JSONL")
    parser.add_argument("--split", default="eval", choices=("train", "eval", "test"))
    parser.add_argument("--dimension-tolerance-pct", type=float, default=5.0)
    parser.add_argument("--target", type=float, default=0.95)
    parser.add_argument("--min-cases-per-category", type=int, default=200)
    parser.add_argument("--output", type=Path, default=Path("evaluation_report.json"))
    args = parser.parse_args()

    validate_dataset(args.dataset)
    records = [record for record in load_records(args.dataset) if record.get("split") == args.split]
    if not records:
        raise ValueError(f"dataset has no records for split={args.split}")
    report = evaluate_predictions(
        records,
        _load_predictions(args.predictions),
        dimension_tolerance_pct=args.dimension_tolerance_pct,
        target=args.target,
        min_cases_per_category=args.min_cases_per_category,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "summary": report["summary"],
        "target_achieved": report["target_achieved"],
        "report": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["total"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
