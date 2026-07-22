from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


STACK_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = STACK_ROOT / "python-worker"
sys.path.insert(0, str(WORKER_ROOT))

from app.openai_image_client import GPTImageClient  # noqa: E402
from app.settings import get_settings  # noqa: E402


KST = timezone(timedelta(hours=9))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="실제 ComfyUI+로컬 의미 검증기 라우팅 smoke")
    parser.add_argument("--prompt", default="a photo of four computer keyboards")
    parser.add_argument("--object-class", default="computer keyboard")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--noise-seed", type=int, default=1178368085068869730)
    parser.add_argument("--comfyui-url", default="http://127.0.0.1:8188")
    parser.add_argument("--verifier-url", default="http://127.0.0.1:8191")
    parser.add_argument("--project-id", default="RUNTIME-SEMANTIC-SMOKE")
    parser.add_argument(
        "--output",
        type=Path,
        default=STACK_ROOT / "storage" / "quality-results" / "runtime-semantic-smoke",
    )
    parser.add_argument("--require-raw-fallback", action="store_true")
    args = parser.parse_args()

    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "report.json"
    started_at = datetime.now(KST)
    started = time.monotonic()
    report = {
        "suite": "runtime-image-semantic-routing-smoke-v1",
        "started_at_kst": started_at.isoformat(),
        "prompt": args.prompt,
        "requirements": [{"class": args.object_class, "count": args.count}],
        "requested_noise_seed": args.noise_seed,
        "require_raw_fallback": args.require_raw_fallback,
        "comfyui_url": args.comfyui_url,
        "verifier_url": args.verifier_url,
        "passed": False,
    }

    settings = replace(
        get_settings(),
        storage_path=output_root,
        openai_image_mode="comfyui",
        image_concept_count=1,
        comfyui_base_url=args.comfyui_url.rstrip("/"),
        comfyui_max_attempts=1,
        image_semantic_verifier_url=args.verifier_url.rstrip("/"),
    )
    analysis = {
        "image_task": "counting",
        "image_requirements": report["requirements"],
        "concept_variants": [{"name": "four-keyboards", "image_prompt": args.prompt}],
    }

    try:
        with patch("app.openai_image_client.secrets.randbits", return_value=args.noise_seed):
            result = GPTImageClient(settings).generate_concepts(
                args.project_id,
                args.prompt,
                "counting",
                [],
                analysis,
            )[0]
        verification = result["semantic_verification"]
        raw_verification = verification.get("raw")
        seed_match = (
            verification.get("precision_noise_seed") == args.noise_seed
            and (
                raw_verification is None
                or verification.get("raw_noise_seed") == verification.get("precision_noise_seed")
            )
        )
        semantic_pass = (
            result["route"] == "precision"
            and bool(verification["precision"]["passed"])
        ) or (
            result["route"] == "raw"
            and isinstance(raw_verification, dict)
            and bool(raw_verification["passed"])
        )
        fallback_pass = not args.require_raw_fallback or (
            result["route"] == "raw"
            and verification.get("selection_reason") == "precision_failed_raw_verified"
        )
        image_path = Path(result["absolute_path"])
        manifest_path = output_root / "projects" / args.project_id / "concept_generation_manifest.json"
        report.update({
            "finished_at_kst": datetime.now(KST).isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "independent_evaluation": False,
            "evaluator": verification["precision"].get("evaluator"),
            "model_id": verification["precision"].get("model_id"),
            "model_revision": verification["precision"].get("model_revision"),
            "device": verification["precision"].get("device"),
            "runtime_contract_case_count": 1,
            "requested_route": result["requested_route"],
            "selected_route": result["route"],
            "selection_reason": verification.get("selection_reason"),
            "semantic_verification": verification,
            "seed_match": seed_match,
            "semantic_pass": semantic_pass,
            "fallback_pass": fallback_pass,
            "image_path": str(image_path),
            "image_sha256": _sha256(image_path),
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha256(manifest_path),
            "passed": bool(
                result["requested_route"] == "precision"
                and result["quality"]["passed"]
                and seed_match
                and semantic_pass
                and fallback_pass
            ),
        })
    except Exception as exc:  # evidence must survive a failed runtime call
        report.update({
            "finished_at_kst": datetime.now(KST).isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        })

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
