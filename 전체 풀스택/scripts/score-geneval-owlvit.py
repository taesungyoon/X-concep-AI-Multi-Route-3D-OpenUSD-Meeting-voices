from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from transformers import (
    AutoImageProcessor,
    AutoModelForObjectDetection,
    AutoModelForZeroShotObjectDetection,
    AutoProcessor,
)


STACK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "google/owlvit-base-patch32"
DEFAULT_REVISION = "cbc355fb364588351c5d51c7f74465e8e7ec6f72"
DETR_MODEL = "facebook/detr-resnet-50"
DETR_REVISION = "1d5f47bd3bdd2c4bbfa585418ffe6da5028b4c0b"
GROUNDING_DINO_MODEL = "IDEA-Research/grounding-dino-base"
GROUNDING_DINO_REVISION = "12bdfa3120f3e7ec7b434d90674b3396eccf88eb"
HUE_CENTERS = {
    "red": 0,
    "orange": 18,
    "yellow": 42,
    "green": 85,
    "blue": 170,
    "purple": 202,
    "pink": 232,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _iou(a: list[float], b: list[float]) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    if intersection <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return intersection / max(area_a + area_b - intersection, 1e-9)


def _nms(items: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda value: value["score"], reverse=True):
        if all(_iou(item["box"], previous["box"]) < threshold for previous in kept):
            kept.append(item)
    return kept


def _color_fraction(image: Image.Image, box: list[float], color: str) -> float:
    width, height = image.size
    left, top, right, bottom = box
    inset_x = max(1.0, (right - left) * 0.08)
    inset_y = max(1.0, (bottom - top) * 0.08)
    crop_box = (
        max(0, int(left + inset_x)),
        max(0, int(top + inset_y)),
        min(width, int(right - inset_x)),
        min(height, int(bottom - inset_y)),
    )
    if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
        return 0.0
    hsv = np.asarray(image.crop(crop_box).convert("HSV"), dtype=np.int16)
    hue = hsv[..., 0]
    saturation = hsv[..., 1]
    value = hsv[..., 2]
    color = color.lower()
    if color == "white":
        mask = (saturation < 45) & (value > 190)
    elif color == "black":
        mask = value < 65
    elif color in {"gray", "grey"}:
        mask = (saturation < 55) & (value >= 65) & (value <= 200)
    elif color == "brown":
        distance = np.minimum(np.abs(hue - 18), 255 - np.abs(hue - 18))
        mask = (distance <= 20) & (saturation > 70) & (value >= 45) & (value <= 190)
    elif color in HUE_CENTERS:
        center = HUE_CENTERS[color]
        distance = np.minimum(np.abs(hue - center), 255 - np.abs(hue - center))
        mask = (distance <= 24) & (saturation > 65) & (value > 45)
    else:
        return 0.0
    return float(mask.mean()) if mask.size else 0.0


def _detect_owlvit(
    image: Image.Image,
    classes: list[str],
    processor: Any,
    model: Any,
    device: torch.device,
    threshold: float,
    nms_threshold: float,
) -> dict[str, list[dict[str, Any]]]:
    queries = [f"a photo of a {name}" for name in classes]
    inputs = processor(text=[queries], images=image, return_tensors="pt")
    inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
    with torch.inference_mode():
        outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]], device=device)
    result = processor.post_process_grounded_object_detection(
        outputs=outputs,
        threshold=threshold,
        target_sizes=target_sizes,
        text_labels=[queries],
    )[0]
    text_labels = result.get("text_labels")
    if text_labels is None:
        text_labels = [queries[int(index)] for index in result["labels"].detach().cpu().tolist()]
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in classes}
    query_to_class = dict(zip(queries, classes))
    for score, label, box in zip(result["scores"], text_labels, result["boxes"]):
        class_name = query_to_class.get(str(label))
        if class_name is None:
            continue
        grouped[class_name].append(
            {
                "score": round(float(score.detach().cpu()), 6),
                "box": [round(float(value), 3) for value in box.detach().cpu().tolist()],
            }
        )
    return {name: _nms(items, nms_threshold) for name, items in grouped.items()}


def _detect_detr(
    image: Image.Image,
    classes: list[str],
    processor: Any,
    model: Any,
    device: torch.device,
    threshold: float,
    nms_threshold: float,
) -> dict[str, list[dict[str, Any]]]:
    inputs = processor(images=image, return_tensors="pt")
    inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
    with torch.inference_mode():
        outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]], device=device)
    result = processor.post_process_object_detection(
        outputs=outputs,
        threshold=threshold,
        target_sizes=target_sizes,
    )[0]
    normalized = {name.replace(" ", "_").lower(): name for name in classes}
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in classes}
    for score, label_id, box in zip(result["scores"], result["labels"], result["boxes"]):
        label = str(model.config.id2label[int(label_id.detach().cpu())]).replace(" ", "_").lower()
        class_name = normalized.get(label)
        if class_name is None:
            continue
        grouped[class_name].append(
            {
                "score": round(float(score.detach().cpu()), 6),
                "box": [round(float(value), 3) for value in box.detach().cpu().tolist()],
            }
        )
    return {name: _nms(items, nms_threshold) for name, items in grouped.items()}


def _detect_grounding_dino(
    image: Image.Image,
    classes: list[str],
    processor: Any,
    model: Any,
    device: torch.device,
    threshold: float,
    nms_threshold: float,
    text_threshold: float,
) -> dict[str, list[dict[str, Any]]]:
    query = ". ".join(name.lower() for name in classes) + "."
    inputs = processor(images=image, text=query, return_tensors="pt")
    inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
    with torch.inference_mode():
        outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]], device=device)
    result = processor.post_process_grounded_object_detection(
        outputs=outputs,
        input_ids=inputs["input_ids"],
        threshold=threshold,
        text_threshold=text_threshold,
        target_sizes=target_sizes,
    )[0]
    text_labels = result.get("text_labels") or []
    normalized = {name.lower(): name for name in classes}
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in classes}
    for score, label, box in zip(result["scores"], text_labels, result["boxes"]):
        clean_label = str(label).strip().lower().rstrip(".")
        class_name = normalized.get(clean_label)
        if class_name is None:
            class_name = next((name for key, name in normalized.items() if key in clean_label or clean_label in key), None)
        if class_name is None:
            continue
        grouped[class_name].append(
            {
                "score": round(float(score.detach().cpu()), 6),
                "box": [round(float(value), 3) for value in box.detach().cpu().tolist()],
            }
        )
    return {name: _nms(items, nms_threshold) for name, items in grouped.items()}


def _position_ok(relation: str, moving: list[float], reference: list[float]) -> bool:
    moving_x = (moving[0] + moving[2]) / 2
    moving_y = (moving[1] + moving[3]) / 2
    reference_x = (reference[0] + reference[2]) / 2
    reference_y = (reference[1] + reference[3]) / 2
    if relation == "right of":
        return moving_x > reference_x
    if relation == "left of":
        return moving_x < reference_x
    if relation in {"above", "on top of"}:
        return moving_y < reference_y
    if relation in {"below", "under"}:
        return moving_y > reference_y
    return False


def _score_case(
    image: Image.Image,
    metadata: dict[str, Any],
    detections: dict[str, list[dict[str, Any]]],
    color_threshold: float,
) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    includes = list(metadata.get("include") or [])
    color_details = []
    for item_index, requirement in enumerate(includes):
        class_name = str(requirement["class"])
        expected_count = int(requirement.get("count", 1))
        found = detections.get(class_name, [])
        if len(found) != expected_count:
            reasons.append(f"{class_name}: expected {expected_count}, detected {len(found)}")
        if requirement.get("color") and found:
            fraction = _color_fraction(image, found[0]["box"], str(requirement["color"]))
            color_details.append({"class": class_name, "color": requirement["color"], "fraction": round(fraction, 6)})
            if fraction < color_threshold:
                reasons.append(f"{class_name}: {requirement['color']} fraction {fraction:.4f} < {color_threshold:.4f}")
        if requirement.get("position") and found:
            relation, reference_index = requirement["position"]
            reference_requirement = includes[int(reference_index)]
            reference_found = detections.get(str(reference_requirement["class"]), [])
            if not reference_found or not _position_ok(str(relation), found[0]["box"], reference_found[0]["box"]):
                reasons.append(f"{class_name}: position '{relation}' failed")
    detail = {
        "detections": detections,
        "colors": color_details,
    }
    return not reasons, reasons, detail


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a local GenEval subset with a pinned open-source detector")
    parser.add_argument("--dataset-root", type=Path, default=STACK_ROOT / "storage" / "quality-datasets")
    parser.add_argument("--image-manifest", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "images" / "manifest.jsonl")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "images" / "geneval-semantic.json")
    parser.add_argument("--backend", choices=("detr", "owlvit", "grounding-dino"), default="grounding-dino")
    parser.add_argument("--model")
    parser.add_argument("--revision")
    parser.add_argument("--det-threshold", type=float)
    parser.add_argument("--nms-threshold", type=float, default=0.30)
    parser.add_argument("--text-threshold", type=float, default=0.30)
    parser.add_argument("--color-threshold", type=float, default=0.08)
    parser.add_argument("--minimum-score", type=float, default=0.8)
    parser.add_argument("--prompt-mode", choices=("raw", "rewritten", "precision"))
    parser.add_argument("--split", choices=("calibration", "holdout"))
    args = parser.parse_args()

    dataset_root = args.dataset_root.resolve()
    image_manifest = args.image_manifest.resolve()
    lock = json.loads((dataset_root / "quality-datasets.lock.json").read_text(encoding="utf-8"))
    lock_map = {item["id"]: item for item in lock["datasets"]}
    geneval_entry = lock_map["geneval"]
    source_path = dataset_root / geneval_entry["artifacts"][0]["path"]
    metadata_rows = _read_jsonl(source_path)
    metadata = {index: row for index, row in enumerate(metadata_rows)}
    image_rows = [row for row in _read_jsonl(image_manifest) if row.get("dataset") == "geneval"]
    if args.prompt_mode:
        image_rows = [row for row in image_rows if row.get("prompt_mode", "raw") == args.prompt_mode]
    if args.split:
        image_rows = [row for row in image_rows if row.get("split") == args.split]
    if not image_rows:
        raise SystemExit("No GenEval rows were found in the image manifest")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    default_models = {
        "detr": (DETR_MODEL, DETR_REVISION, 0.7),
        "owlvit": (DEFAULT_MODEL, DEFAULT_REVISION, 0.08),
        "grounding-dino": (GROUNDING_DINO_MODEL, GROUNDING_DINO_REVISION, 0.30),
    }
    default_model, default_revision, default_detection_threshold = default_models[args.backend]
    model_id = args.model or default_model
    model_revision = args.revision or default_revision
    detection_threshold = args.det_threshold if args.det_threshold is not None else default_detection_threshold
    if args.backend == "detr":
        processor = AutoImageProcessor.from_pretrained(model_id, revision=model_revision)
        model = AutoModelForObjectDetection.from_pretrained(
            model_id,
            revision=model_revision,
            use_safetensors=True,
        ).to(device)
        detector = _detect_detr
    elif args.backend == "owlvit":
        processor = AutoProcessor.from_pretrained(model_id, revision=model_revision)
        model = AutoModelForZeroShotObjectDetection.from_pretrained(
            model_id,
            revision=model_revision,
            use_safetensors=True,
        ).to(device)
        detector = _detect_owlvit
    else:
        processor = AutoProcessor.from_pretrained(model_id, revision=model_revision)
        model = AutoModelForZeroShotObjectDetection.from_pretrained(
            model_id,
            revision=model_revision,
            use_safetensors=True,
        ).to(device)
        detector = lambda image, classes, processor, model, device, threshold, nms_threshold: _detect_grounding_dino(
            image,
            classes,
            processor,
            model,
            device,
            threshold,
            nms_threshold,
            args.text_threshold,
        )
    model.eval()
    case_results = []
    started_all = time.perf_counter()
    for position, image_row in enumerate(image_rows, start=1):
        row_index = int(image_row["row_index"])
        row_metadata = metadata[row_index]
        image_path = Path(image_row["path"])
        if not image_path.is_absolute():
            image_path = image_manifest.parent / image_path
        classes = sorted({str(item["class"]) for item in row_metadata.get("include", [])})
        started = time.perf_counter()
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            detections = detector(
                image,
                classes,
                processor,
                model,
                device,
                detection_threshold,
                args.nms_threshold,
            )
            correct, reasons, detail = _score_case(image, row_metadata, detections, args.color_threshold)
        result = {
            "dataset": "geneval",
            "row_index": row_index,
            "tag": row_metadata.get("tag"),
            "prompt_sha256": hashlib.sha256(str(row_metadata.get("prompt", "")).encode("utf-8")).hexdigest(),
            "image_sha256": sha256_file(image_path),
            "benchmark_seed": image_row.get("benchmark_seed"),
            "seed": image_row.get("seed"),
            "prompt_mode": image_row.get("prompt_mode", "raw"),
            "split": image_row.get("split"),
            "correct": correct,
            "reasons": reasons,
            "detail": detail,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
        case_results.append(result)
        print(f"[{position:02d}/{len(image_rows):02d}] {row_metadata.get('tag')}:{row_index} -> {'PASS' if correct else 'FAIL'}", flush=True)

    correct_count = sum(item["correct"] for item in case_results)
    overall = correct_count / len(case_results) if case_results else 0.0
    task_scores = {}
    for tag in sorted({str(item["tag"]) for item in case_results}):
        tagged = [item for item in case_results if item["tag"] == tag]
        task_scores[tag] = {
            "correct": sum(item["correct"] for item in tagged),
            "count": len(tagged),
            "score_pct": round(sum(item["correct"] for item in tagged) / len(tagged) * 100, 4),
        }
    report = {
        "schema_version": 1,
        "evaluator": f"{args.backend}-geneval-compatible-v1",
        "official_geneval_score": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "model_revision": model_revision,
        "model_license": "Apache-2.0",
        "device": str(device),
        "dataset_revision": geneval_entry["revision"],
        "dataset_source_sha256": geneval_entry["artifacts"][0]["sha256"],
        "image_manifest_sha256": sha256_file(image_manifest),
        "prompt_mode": args.prompt_mode,
        "split": args.split,
        "thresholds": {
            "detection": detection_threshold,
            "nms_iou": args.nms_threshold,
            "text": args.text_threshold if args.backend == "grounding-dino" else None,
            "color_fraction": args.color_threshold,
            "minimum_score": args.minimum_score,
        },
        "case_count": len(case_results),
        "correct_count": correct_count,
        "overall_score_pct": round(overall * 100, 4),
        "task_scores": task_scores,
        "passed": overall >= args.minimum_score,
        "duration_seconds": round(time.perf_counter() - started_all, 3),
        "cases": case_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "case_count", "correct_count", "overall_score_pct", "task_scores")}, ensure_ascii=False))
    print(f"Report: {args.output.resolve()}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
