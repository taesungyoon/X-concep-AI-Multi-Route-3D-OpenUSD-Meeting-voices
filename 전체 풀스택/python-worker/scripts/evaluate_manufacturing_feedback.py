from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.manufacturing_feedback import evaluate_candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, action="append", required=True)
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=float, default=0.95)
    args = parser.parse_args()

    contract = {}
    if args.contract and args.contract.exists():
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
    report = evaluate_candidate(
        reference_path=args.reference,
        candidate_paths=args.candidate,
        glb_path=args.glb,
        contract=contract,
        target=args.target,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "score": report["score"],
        "silhouette_score": report["silhouette_score"],
        "manufacturing_score": report["manufacturing"]["score"],
        "report": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
