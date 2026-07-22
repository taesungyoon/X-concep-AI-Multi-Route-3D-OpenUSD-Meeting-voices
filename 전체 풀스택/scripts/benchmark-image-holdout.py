from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from quality_metrics import binary_summary, deterministic_split, score_distribution


STACK_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = STACK_ROOT / "python-worker"
sys.path.insert(0, str(WORKER_ROOT))

from app.image_quality import validate_generated_image  # noqa: E402
from app.image_precision import route_prompt  # noqa: E402
from app.openai_image_client import GPTImageClient  # noqa: E402
from app.settings import get_settings  # noqa: E402


def _load_baseline_module():
    spec = importlib.util.spec_from_file_location("xconcep_baseline_images", Path(__file__).with_name("benchmark-local-images.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASELINE = _load_baseline_module()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    partial.replace(path)


def _round_robin(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = f"{row['dataset']}:{row.get('category') or row.get('tag') or 'unknown'}"
        groups.setdefault(key, []).append(row)
    selected = []
    depth = 0
    keys = sorted(groups)
    while len(selected) < count and any(depth < len(groups[key]) for key in keys):
        for key in keys:
            if depth < len(groups[key]):
                selected.append(groups[key][depth])
                if len(selected) == count:
                    break
        depth += 1
    return selected


def select_reliability_cases(dataset_root: Path, holdout_count: int, calibration_count: int) -> list[dict[str, Any]]:
    candidates = BASELINE.select_cases(dataset_root, 512)
    decorated = []
    for case in candidates:
        logical_id = f"{case['dataset']}:{int(case['row_index'])}"
        decorated.append({**case, "logical_id": logical_id, "split": deterministic_split(logical_id)})
    holdout = _round_robin([case for case in decorated if case["split"] == "holdout"], holdout_count)
    calibration = _round_robin([case for case in decorated if case["split"] == "calibration"], calibration_count)
    if len(holdout) != holdout_count or len(calibration) != calibration_count:
        raise RuntimeError(
            f"canonical pool cannot satisfy split contract: holdout={len(holdout)}/{holdout_count}, "
            f"calibration={len(calibration)}/{calibration_count}"
        )
    return calibration + holdout


def rewrite_prompt(prompt: str, dataset: str, stratum: str) -> str:
    focus = {
        "single_object": "Show exactly the named object once.",
        "two_object": "Show exactly the two named objects, both fully visible.",
        "counting": "Preserve the exact requested count with clearly separated objects.",
        "colors": "Preserve every requested object color exactly.",
        "position": "Preserve the requested spatial relationship and leave clear separation.",
        "color_attr": "Bind each requested color to the correct object.",
    }.get(stratum, "Preserve every named subject, attribute, count, and relationship exactly.")
    if dataset == "parti-prompts":
        focus = "Preserve the original subject and composition while making all important elements clearly visible."
    return f"{prompt.strip()} {focus} Use a clean, uncluttered composition with no extra objects or text."


def generation_seed(case: dict[str, Any], benchmark_seed: int) -> int:
    identity = f"{benchmark_seed}:{case['dataset']}:{int(case['row_index'])}"
    return int.from_bytes(hashlib.sha256(identity.encode("utf-8")).digest()[:8], "big") & ((1 << 63) - 1)


def _key(row: dict[str, Any]) -> tuple[str, int, str, int]:
    return row["dataset"], int(row["row_index"]), str(row["prompt_mode"]), int(row["benchmark_seed"])


def _evaluate_quality(
    image_bytes: bytes,
    thresholds: dict[str, Any],
    settings: Any,
) -> dict[str, Any]:
    """Reject broken/blank images without misclassifying intentional low-entropy scenes."""
    gate = BASELINE._gate_quality(image_bytes, thresholds)
    runtime = validate_generated_image(
        image_bytes,
        settings,
        expected_size=(settings.comfyui_width, settings.comfyui_height),
    )
    metrics = {**gate.get("metrics", {}), **runtime.get("metrics", {})}
    structural_passed = bool(metrics) and (
        int(metrics.get("width", 0)) >= int(thresholds["image_min_width"])
        and int(metrics.get("height", 0)) >= int(thresholds["image_min_height"])
        and int(metrics.get("bytes", 0)) >= int(thresholds["image_min_bytes"])
    )
    entropy_passed = float(metrics.get("entropy", 0.0)) >= float(thresholds["image_min_entropy"])
    return {
        "passed": bool(structural_passed and runtime.get("passed")),
        "metrics": {**metrics, "entropy_passed": entropy_passed},
        "checks": runtime.get("checks", []),
        "policy": "structural-integrity-plus-nonblank-v2",
    }


def _is_reusable(
    row: dict[str, Any],
    output_root: Path,
    thresholds: dict[str, Any],
    settings: Any,
) -> bool:
    path = output_root / row.get("path", "")
    if not path.is_file():
        return False
    image_bytes = path.read_bytes()
    if row.get("image_sha256") != hashlib.sha256(image_bytes).hexdigest():
        return False
    quality = _evaluate_quality(image_bytes, thresholds, settings)
    row["basic_quality_passed"] = quality["passed"]
    row["basic_quality"] = quality["metrics"]
    row["basic_quality_checks"] = quality["checks"]
    row["basic_quality_policy"] = quality["policy"]
    # A deterministic low-quality result is still reusable evidence. Regenerating
    # it with the same prompt and noise seed would only hide or duplicate failure.
    return True


def _duplicate_rate(rows: list[dict[str, Any]]) -> float:
    hashes = [row.get("image_sha256") for row in rows if row.get("image_sha256")]
    return (len(hashes) - len(set(hashes))) / len(hashes) * 100.0 if hashes else 0.0


def summarize(rows: list[dict[str, Any]], thresholds: dict[str, Any], evaluation_split: str = "holdout") -> dict[str, Any]:
    groups = {}
    seed_scores: dict[str, list[float]] = {}
    for mode in sorted({row["prompt_mode"] for row in rows}):
        seed_scores[mode] = []
        for benchmark_seed in sorted({int(row["benchmark_seed"]) for row in rows if row["prompt_mode"] == mode}):
            subset = [row for row in rows if row["prompt_mode"] == mode and int(row["benchmark_seed"]) == benchmark_seed and row["split"] == evaluation_split]
            quality = binary_summary(bool(row.get("basic_quality_passed")) for row in subset)
            quality["exact_duplicate_rate_pct"] = round(_duplicate_rate(subset), 4)
            quality["passed_contract"] = (
                quality["score_pct"] >= float(thresholds["image_basic_pass_rate_pct"])
                and quality["exact_duplicate_rate_pct"] <= float(thresholds["image_max_exact_duplicate_rate_pct"])
            )
            groups[f"{mode}:{benchmark_seed}"] = quality
            seed_scores[mode].append(quality["score_pct"])
    distributions = {mode: score_distribution(scores) for mode, scores in seed_scores.items()}
    return {
        "groups": groups,
        "prompt_mode_seed_distributions": distributions,
        "passed": bool(groups) and all(group["passed_contract"] for group in groups.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate resumable calibration/holdout ComfyUI images over repeated seeds")
    parser.add_argument("--dataset-root", type=Path, default=STACK_ROOT / "storage" / "quality-datasets")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "image-holdout")
    parser.add_argument("--baseline-manifest", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "images" / "manifest.jsonl")
    parser.add_argument("--route-reference-manifest", type=Path, help="raw manifest used to reuse unchanged fast-route images")
    parser.add_argument("--base-url", default="http://127.0.0.1:8188")
    parser.add_argument("--holdout-count", type=int, default=120)
    parser.add_argument("--calibration-count", type=int, default=30)
    parser.add_argument("--seeds", default="20260721,20260722,20260723")
    parser.add_argument("--rewritten-seeds", default="", help="optional subset for rewritten A/B; empty uses every seed")
    parser.add_argument("--prompt-modes", default="raw,rewritten")
    parser.add_argument("--only-split", choices=("calibration", "holdout"))
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--offline-rescore", action="store_true", help="reuse existing evidence only; never contact ComfyUI")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    rewritten_seeds = [int(value.strip()) for value in args.rewritten_seeds.split(",") if value.strip()] or list(seeds)
    prompt_modes = [value.strip() for value in args.prompt_modes.split(",") if value.strip()]
    if len(set(seeds)) < 3:
        raise SystemExit("reliability contract requires at least three distinct benchmark seeds")
    if not prompt_modes or any(mode not in {"raw", "rewritten", "precision"} for mode in prompt_modes):
        raise SystemExit("--prompt-modes accepts raw, rewritten, and/or precision")
    if any(seed not in seeds for seed in rewritten_seeds):
        raise SystemExit("--rewritten-seeds must be a subset of --seeds")
    if args.holdout_count < 120:
        raise SystemExit("reliability contract requires at least 120 holdout cases")

    dataset_root = args.dataset_root.resolve()
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    cases = select_reliability_cases(dataset_root, args.holdout_count, args.calibration_count)
    if args.only_split:
        cases = [case for case in cases if case["split"] == args.only_split]
    plan = {
        "holdout_cases": sum(case["split"] == "holdout" for case in cases),
        "calibration_cases": sum(case["split"] == "calibration" for case in cases),
        "seeds": seeds,
        "prompt_modes": prompt_modes,
        "rewritten_seeds": rewritten_seeds if any(mode in {"rewritten", "precision"} for mode in prompt_modes) else [],
        "only_split": args.only_split,
        "total_images": len(cases) * sum(len(rewritten_seeds) if mode in {"rewritten", "precision"} else len(seeds) for mode in prompt_modes),
    }
    if "precision" in prompt_modes:
        route_case_counts: dict[str, int] = {}
        for case in cases:
            route_name, _ = route_prompt(
                str(case.get("prompt") or ""),
                stratum=str(case.get("category") or case.get("tag") or "unknown"),
                requirements=case.get("include") or [],
            )
            route_case_counts[route_name] = route_case_counts.get(route_name, 0) + 1
        plan["precision_route_cases"] = route_case_counts
        plan["precision_route_images"] = {
            route: count * len(rewritten_seeds) for route, count in route_case_counts.items()
        }
    (output_root / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.plan_only:
        print(json.dumps(plan, ensure_ascii=False))
        return 0

    thresholds = json.loads((STACK_ROOT / "quality" / "gates.json").read_text(encoding="utf-8"))["thresholds"]
    settings = replace(
        get_settings(), openai_image_mode="comfyui", comfyui_base_url=args.base_url, storage_path=STACK_ROOT / "storage"
    )
    client = GPTImageClient(settings)
    if not args.offline_rescore:
        with httpx.Client(timeout=10.0) as http:
            response = http.get(f"{args.base_url}/system_stats")
            response.raise_for_status()

    manifest_path = output_root / "manifest.jsonl"
    existing_rows = _read_jsonl(manifest_path) if args.resume else []
    reusable = {
        _key(row): row
        for row in existing_rows
        if _is_reusable(row, output_root, thresholds, settings)
    }
    baseline_manifest = args.baseline_manifest.resolve()
    baseline_rows = _read_jsonl(baseline_manifest)
    baseline_by_case = {(row.get("dataset"), int(row.get("row_index", -1))): row for row in baseline_rows}
    route_reference_manifest = args.route_reference_manifest.resolve() if args.route_reference_manifest else None
    route_reference_rows = _read_jsonl(route_reference_manifest) if route_reference_manifest else []
    route_reference_by_case = {
        (row.get("dataset"), int(row.get("row_index", -1)), int(row.get("benchmark_seed", -1))): row
        for row in route_reference_rows
        if row.get("prompt_mode") == "raw"
    }
    rows: list[dict[str, Any]] = []
    generated = 0
    reused = 0
    total = plan["total_images"]
    started_all = time.monotonic()
    for case in cases:
        raw_prompt = str(case.get("prompt") or "").strip()
        stratum = str(case.get("category") or case.get("tag") or "unknown")
        for benchmark_seed in seeds:
            noise_seed = generation_seed(case, benchmark_seed)
            for prompt_mode in prompt_modes:
                if prompt_mode in {"rewritten", "precision"} and benchmark_seed not in rewritten_seeds:
                    continue
                key = (case["dataset"], int(case["row_index"]), prompt_mode, benchmark_seed)
                previous = reusable.get(key)
                if previous:
                    rows.append(previous)
                    reused += 1
                    continue
                route_name = "fast"
                if prompt_mode == "raw":
                    prompt = raw_prompt
                elif prompt_mode == "rewritten":
                    prompt = rewrite_prompt(raw_prompt, case["dataset"], stratum)
                    route_name = "rewritten"
                else:
                    route_name, prompt = route_prompt(
                        raw_prompt,
                        stratum=stratum,
                        requirements=case.get("include") or [],
                    )
                relative = Path("files") / prompt_mode / f"seed-{benchmark_seed}" / f"{case['dataset']}-{case['row_index']}.png"
                image_path = output_root / relative
                image_path.parent.mkdir(parents=True, exist_ok=True)
                started = time.monotonic()
                route_reference = route_reference_by_case.get((case["dataset"], int(case["row_index"]), benchmark_seed))
                if prompt_mode == "precision" and route_name == "fast" and route_reference and route_reference_manifest:
                    reference_path = Path(str(route_reference.get("path", "")))
                    if not reference_path.is_absolute():
                        reference_path = route_reference_manifest.parent / reference_path
                    expected_prompt_sha = hashlib.sha256(raw_prompt.encode("utf-8")).hexdigest()
                    if (
                        reference_path.is_file()
                        and int(route_reference.get("seed", -1)) == noise_seed
                        and route_reference.get("prompt_sha256") == expected_prompt_sha
                    ):
                        reference_bytes = reference_path.read_bytes()
                        if route_reference.get("image_sha256") == hashlib.sha256(reference_bytes).hexdigest():
                            quality = _evaluate_quality(reference_bytes, thresholds, settings)
                            image_path.write_bytes(reference_bytes)
                            row = {
                                "dataset": case["dataset"], "row_index": case["row_index"], "stratum": stratum,
                                "logical_id": case["logical_id"], "split": case["split"], "prompt_mode": prompt_mode,
                                "route": route_name, "benchmark_seed": benchmark_seed, "seed": noise_seed, "path": relative.as_posix(),
                                "prompt_sha256": expected_prompt_sha, "raw_prompt_sha256": expected_prompt_sha,
                                "image_sha256": hashlib.sha256(reference_bytes).hexdigest(),
                                "basic_quality_passed": quality["passed"], "basic_quality": quality["metrics"],
                                "basic_quality_checks": quality["checks"], "basic_quality_policy": quality["policy"],
                                "provider": "comfyui", "model": settings.comfyui_unet_model,
                                "duration_seconds": round(time.monotonic() - started, 3), "reused_from_route_reference": True,
                            }
                            rows.append(row)
                            reused += 1
                            _write_jsonl_atomic(manifest_path, rows)
                            continue
                baseline_row = baseline_by_case.get((case["dataset"], int(case["row_index"])))
                if prompt_mode == "raw" and benchmark_seed == seeds[0] and baseline_row and int(baseline_row.get("seed", -1)) == noise_seed:
                    baseline_path = Path(str(baseline_row.get("path", "")))
                    if not baseline_path.is_absolute():
                        baseline_path = baseline_manifest.parent / baseline_path
                    if baseline_path.is_file():
                        baseline_bytes = baseline_path.read_bytes()
                        quality = _evaluate_quality(baseline_bytes, thresholds, settings)
                        if quality["passed"]:
                            image_path.write_bytes(baseline_bytes)
                            row = {
                                "dataset": case["dataset"], "row_index": case["row_index"], "stratum": stratum,
                                "logical_id": case["logical_id"], "split": case["split"], "prompt_mode": prompt_mode, "route": route_name,
                                "benchmark_seed": benchmark_seed, "seed": noise_seed, "path": relative.as_posix(),
                                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                                "raw_prompt_sha256": hashlib.sha256(raw_prompt.encode("utf-8")).hexdigest(),
                                "image_sha256": hashlib.sha256(baseline_bytes).hexdigest(), "basic_quality_passed": True,
                                "basic_quality": quality["metrics"], "basic_quality_checks": quality["checks"],
                                "basic_quality_policy": quality["policy"], "provider": "comfyui", "model": settings.comfyui_unet_model,
                                "duration_seconds": round(time.monotonic() - started, 3), "reused_from_baseline": True,
                            }
                            rows.append(row)
                            reused += 1
                            _write_jsonl_atomic(manifest_path, rows)
                            continue
                image_bytes = None
                error = None
                if args.offline_rescore:
                    raise RuntimeError(
                        "offline rescore evidence missing for "
                        f"{case['dataset']}:{case['row_index']}:{prompt_mode}:{benchmark_seed}"
                    )
                for attempt in range(1, args.max_attempts + 1):
                    try:
                        image_bytes = BASELINE._generate(
                            client, prompt, noise_seed,
                            f"quality-holdout/{prompt_mode}/seed-{benchmark_seed}/{case['dataset']}-{case['row_index']}",
                        )
                        break
                    except (httpx.HTTPError, TimeoutError) as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        if attempt < args.max_attempts:
                            time.sleep(min(2**attempt, 8))
                if image_bytes is None:
                    row = {
                        "dataset": case["dataset"], "row_index": case["row_index"], "stratum": stratum,
                        "logical_id": case["logical_id"], "split": case["split"], "prompt_mode": prompt_mode, "route": route_name,
                        "benchmark_seed": benchmark_seed, "seed": noise_seed, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                        "raw_prompt_sha256": hashlib.sha256(raw_prompt.encode("utf-8")).hexdigest(), "basic_quality_passed": False,
                        "error": error or "generation_failed", "provider": "comfyui", "model": settings.comfyui_unet_model,
                        "duration_seconds": round(time.monotonic() - started, 3),
                    }
                else:
                    image_path.write_bytes(image_bytes)
                    quality = _evaluate_quality(image_bytes, thresholds, settings)
                    row = {
                        "dataset": case["dataset"], "row_index": case["row_index"], "stratum": stratum,
                        "logical_id": case["logical_id"], "split": case["split"], "prompt_mode": prompt_mode, "route": route_name,
                        "benchmark_seed": benchmark_seed, "seed": noise_seed, "path": relative.as_posix(),
                        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                        "raw_prompt_sha256": hashlib.sha256(raw_prompt.encode("utf-8")).hexdigest(),
                        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                        "basic_quality_passed": quality["passed"], "basic_quality": quality["metrics"],
                        "basic_quality_checks": quality["checks"], "basic_quality_policy": quality["policy"],
                        "provider": "comfyui", "model": settings.comfyui_unet_model,
                        "duration_seconds": round(time.monotonic() - started, 3),
                    }
                    generated += 1
                rows.append(row)
                _write_jsonl_atomic(manifest_path, rows)
                print(
                    f"[{len(rows):04d}/{total:04d}] {case['split']} {prompt_mode} seed={benchmark_seed} "
                    f"{case['dataset']}:{case['row_index']} -> {'PASS' if row['basic_quality_passed'] else 'FAIL'}",
                    flush=True,
                )

    _write_jsonl_atomic(manifest_path, rows)
    summary = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), **plan,
        "provider": "comfyui", "model": settings.comfyui_unet_model, "generated_count": generated,
        "reused_count": reused, "duration_seconds": round(time.monotonic() - started_all, 3),
        **summarize(rows, thresholds, args.only_split or "holdout"),
    }
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("passed", "generated_count", "reused_count", "total_images")}, ensure_ascii=False))
    print(f"Manifest: {manifest_path}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
