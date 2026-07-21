from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image


STACK_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = STACK_ROOT / "python-worker"
sys.path.insert(0, str(WORKER_ROOT))

from app.image_quality import validate_generated_image  # noqa: E402
from app.openai_image_client import GPTImageClient  # noqa: E402
from app.settings import get_settings  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _stratified(rows: list[dict[str, Any]], key: str, count: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        groups.setdefault(value, []).append(row)
    selected: list[dict[str, Any]] = []
    depth = 0
    keys = sorted(groups)
    while len(selected) < count and any(depth < len(groups[value]) for value in keys):
        for value in keys:
            if depth < len(groups[value]):
                selected.append(groups[value][depth])
                if len(selected) == count:
                    break
        depth += 1
    return selected


def select_cases(dataset_root: Path, count: int) -> list[dict[str, Any]]:
    lock = json.loads((dataset_root / "quality-datasets.lock.json").read_text(encoding="utf-8"))
    if lock.get("tier") not in {"standard", "full"}:
        raise RuntimeError("Image benchmark requires a standard or full dataset lock")
    lock_map = {item["id"]: item for item in lock["datasets"]}
    parti = _read_jsonl(dataset_root / lock_map["parti-prompts"]["sample"]["path"])
    geneval = _read_jsonl(dataset_root / lock_map["geneval"]["sample"]["path"])
    parti_count = count // 2
    geneval_count = count - parti_count
    cases = []
    for row in _stratified(parti, "category", parti_count):
        cases.append({"dataset": "parti-prompts", **row})
    for row in _stratified(geneval, "tag", geneval_count):
        cases.append({"dataset": "geneval", **row})
    return cases


def _seed(case: dict[str, Any], base_seed: int) -> int:
    identity = f"{base_seed}:{case['dataset']}:{case['row_index']}"
    return int.from_bytes(hashlib.sha256(identity.encode("utf-8")).digest()[:8], "big") & ((1 << 63) - 1)


def _generate(client: GPTImageClient, prompt: str, seed: int, prefix: str) -> bytes:
    workflow = client._comfyui_flux_workflow(prompt, None, prefix)
    workflow["7"]["inputs"]["noise_seed"] = seed
    client_id = str(uuid.uuid4())
    timeout = httpx.Timeout(float(client.settings.comfyui_timeout_seconds), connect=15.0)
    with httpx.Client(timeout=timeout) as http:
        response = http.post(
            f"{client.settings.comfyui_base_url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        response.raise_for_status()
        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI returned no prompt id: {response.text[:500]}")
        deadline = time.monotonic() + client.settings.comfyui_timeout_seconds
        while time.monotonic() < deadline:
            history_response = http.get(f"{client.settings.comfyui_base_url}/history/{prompt_id}")
            history_response.raise_for_status()
            history = history_response.json().get(prompt_id)
            if history:
                status = history.get("status") or {}
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI generation failed: {status.get('messages') or status}")
                images = (history.get("outputs") or {}).get("13", {}).get("images") or []
                if images:
                    image = images[0]
                    result = http.get(
                        f"{client.settings.comfyui_base_url}/view",
                        params={
                            "filename": image["filename"],
                            "subfolder": image.get("subfolder", ""),
                            "type": image.get("type", "output"),
                        },
                    )
                    result.raise_for_status()
                    return result.content
            time.sleep(0.75)
    raise TimeoutError(f"ComfyUI timed out after {client.settings.comfyui_timeout_seconds}s")


def _gate_quality(image_bytes: bytes, thresholds: dict[str, Any]) -> dict[str, Any]:
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            width, height = source.size
            entropy = float(source.convert("L").entropy())
    except OSError as exc:
        return {"passed": False, "metrics": {}, "error": f"{type(exc).__name__}: {exc}"}
    metrics = {
        "width": width,
        "height": height,
        "bytes": len(image_bytes),
        "entropy": round(entropy, 4),
    }
    return {
        "passed": (
            width >= int(thresholds["image_min_width"])
            and height >= int(thresholds["image_min_height"])
            and len(image_bytes) >= int(thresholds["image_min_bytes"])
            and entropy >= float(thresholds["image_min_entropy"])
        ),
        "metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a deterministic local ComfyUI/FLUX quality sample")
    parser.add_argument("--dataset-root", type=Path, default=STACK_ROOT / "storage" / "quality-datasets")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "images")
    parser.add_argument("--base-url", default="http://127.0.0.1:8188")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    if args.count < 12:
        raise SystemExit("Standard quality contract requires at least 12 images")
    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be at least 1")

    settings = replace(
        get_settings(),
        openai_image_mode="comfyui",
        comfyui_base_url=args.base_url,
        storage_path=STACK_ROOT / "storage",
    )
    client = GPTImageClient(settings)
    with httpx.Client(timeout=10.0) as http:
        stats = http.get(f"{args.base_url}/system_stats")
        stats.raise_for_status()

    cases = select_cases(args.dataset_root.resolve(), args.count)
    thresholds = json.loads((STACK_ROOT / "quality" / "gates.json").read_text(encoding="utf-8"))["thresholds"]
    output_root = args.output.resolve()
    files_root = output_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    existing_manifest = output_root / "manifest.jsonl"
    previous_rows = _read_jsonl(existing_manifest) if existing_manifest.is_file() else []
    previous_by_case = {(row.get("dataset"), int(row.get("row_index", -1))): row for row in previous_rows}
    manifest_rows = []
    reused_count = 0
    generated_count = 0
    started_all = time.monotonic()
    for position, case in enumerate(cases, start=1):
        prompt = str(case.get("prompt") or "").strip()
        if not prompt:
            raise RuntimeError(f"Empty prompt: {case['dataset']}:{case['row_index']}")
        base_seed = _seed(case, args.seed)
        chosen_seed = base_seed
        generation_attempt = 1
        filename = f"{case['dataset']}-{case['row_index']}.png"
        image_path = files_root / filename
        started = time.monotonic()
        previous = previous_by_case.get((case["dataset"], int(case["row_index"])), {})
        reuse_ok = False
        gate_quality: dict[str, Any] = {}
        if args.reuse_existing and image_path.is_file():
            image_bytes = image_path.read_bytes()
            runtime_quality = validate_generated_image(
                image_bytes,
                settings,
                expected_size=(settings.comfyui_width, settings.comfyui_height),
            )
            gate_quality = _gate_quality(image_bytes, thresholds)
            reuse_ok = bool(runtime_quality["passed"] and gate_quality["passed"])
            if reuse_ok:
                chosen_seed = int(previous.get("seed", base_seed))
                generation_attempt = int(previous.get("generation_attempt", 1))
                reused_count += 1
        if not reuse_ok:
            failures = []
            for generation_attempt in range(1, args.max_attempts + 1):
                chosen_seed = (base_seed + (generation_attempt - 1) * 104729) & ((1 << 63) - 1)
                image_bytes = _generate(
                    client,
                    prompt,
                    chosen_seed,
                    f"quality/{case['dataset']}-{case['row_index']}-attempt-{generation_attempt}",
                )
                runtime_quality = validate_generated_image(
                    image_bytes,
                    settings,
                    expected_size=(settings.comfyui_width, settings.comfyui_height),
                )
                gate_quality = _gate_quality(image_bytes, thresholds)
                if runtime_quality["passed"] and gate_quality["passed"]:
                    image_path.write_bytes(image_bytes)
                    generated_count += 1
                    break
                failures.append({"attempt": generation_attempt, "runtime": runtime_quality, "gate": gate_quality})
            else:
                raise RuntimeError(f"Image quality failed after {args.max_attempts} attempts for {filename}: {failures}")
        manifest_rows.append(
            {
                "dataset": case["dataset"],
                "row_index": case["row_index"],
                "stratum": case.get("category") or case.get("tag") or "unknown",
                "path": f"files/{filename}",
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "seed": chosen_seed,
                "generation_attempt": generation_attempt,
                "basic_quality": gate_quality["metrics"],
                "provider": "comfyui",
                "model": settings.comfyui_unet_model,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        )
        print(f"[{position:02d}/{len(cases):02d}] {case['dataset']}:{case['row_index']} -> {filename}", flush=True)

    partial = output_root / "manifest.jsonl.partial"
    with partial.open("w", encoding="utf-8", newline="\n") as target:
        for row in manifest_rows:
            target.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    partial.replace(output_root / "manifest.jsonl")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "comfyui",
        "model": settings.comfyui_unet_model,
        "count": len(manifest_rows),
        "reused_count": reused_count,
        "generated_count": generated_count,
        "seed": args.seed,
        "duration_seconds": round(time.monotonic() - started_all, 3),
    }
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
