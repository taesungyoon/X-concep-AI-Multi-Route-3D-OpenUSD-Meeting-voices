from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from PIL import Image


DATASET_SCHEMA = "xconcep.cad-vlm-sample/1.0"
CATEGORIES = {"part", "module", "equipment"}
SPLITS = {"train", "eval", "test"}
MODE_FOR_CATEGORY = {
    "part": "openscad_part",
    "module": "openscad_module",
    "equipment": "openscad_equipment",
}


class DatasetValidationError(ValueError):
    """Raised when records cannot safely be used for training."""


def load_records(dataset_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(dataset_dir).expanduser().resolve()
    manifest = root / "records.jsonl"
    if not manifest.is_file():
        raise DatasetValidationError(f"dataset manifest not found: {manifest}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetValidationError(f"invalid JSON at records.jsonl:{line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise DatasetValidationError(f"record at line {line_number} must be an object")
        record["_line_number"] = line_number
        records.append(record)
    if not records:
        raise DatasetValidationError("dataset contains no records")
    return records


def _safe_image_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DatasetValidationError(f"image path escapes dataset root: {relative}") from exc
    return path


def _canonical_contract_hash(contract: dict[str, Any]) -> str:
    value = dict(contract)
    value.pop("contract_sha256", None)
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_allowlist(root: Path) -> set[str]:
    candidates = [root / "license_allowlist.json", root.parent.parent / "schema" / "license_allowlist.json"]
    for path in candidates:
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            return {str(item) for item in value.get("allowed_training_licenses", [])}
    raise DatasetValidationError("license_allowlist.json not found")


def validate_dataset(dataset_dir: str | Path, *, open_images: bool = True) -> dict[str, Any]:
    root = Path(dataset_dir).expanduser().resolve()
    records = load_records(root)
    allowlist = _load_allowlist(root)
    errors: list[str] = []
    ids: set[str] = set()
    prompt_splits: dict[str, set[str]] = defaultdict(set)
    image_splits: dict[str, set[str]] = defaultdict(set)
    split_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    image_count = 0
    for record in records:
        line = record.pop("_line_number", "?")
        prefix = f"line {line}"
        record_id = str(record.get("id") or "")
        category = str(record.get("category") or "")
        split = str(record.get("split") or "")
        if record.get("schema_version") != DATASET_SCHEMA:
            errors.append(f"{prefix}: unsupported schema_version")
        if not record_id:
            errors.append(f"{prefix}: id is required")
        elif record_id in ids:
            errors.append(f"{prefix}: duplicate id {record_id}")
        ids.add(record_id)
        if category not in CATEGORIES:
            errors.append(f"{prefix}: invalid category {category}")
        if split not in SPLITS:
            errors.append(f"{prefix}: invalid split {split}")
        split_counts[split] += 1
        category_counts[category] += 1
        if not str(record.get("prompt") or "").strip():
            errors.append(f"{prefix}: prompt is required")
        prompt = str(record.get("prompt") or "")
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        images = record.get("images")
        image_hashes = record.get("image_sha256")
        if not isinstance(images, list) or not images:
            errors.append(f"{prefix}: images must be a non-empty list")
        else:
            for relative in images:
                try:
                    image_path = _safe_image_path(root, str(relative))
                    if not image_path.is_file():
                        errors.append(f"{prefix}: missing image {relative}")
                        continue
                    image_count += 1
                    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
                    image_splits[digest].add(split)
                    view = image_path.stem.rsplit("_", 1)[-1]
                    expected_digest = image_hashes.get(view) if isinstance(image_hashes, dict) else None
                    if expected_digest != digest:
                        errors.append(f"{prefix}: image_sha256 mismatch for {relative}")
                    if open_images:
                        with Image.open(image_path) as image:
                            image.verify()
                except (DatasetValidationError, OSError) as exc:
                    errors.append(f"{prefix}: invalid image {relative}: {exc}")
        spec = record.get("design_spec")
        if not isinstance(spec, dict):
            errors.append(f"{prefix}: design_spec must be an object")
        else:
            if spec.get("category") != category:
                errors.append(f"{prefix}: design_spec category mismatch")
            if spec.get("units") != "mm":
                errors.append(f"{prefix}: design_spec units must be mm")
            prompt_hash = str(spec.get("source_prompt_hash") or "")
            if prompt_hash != prompt_sha256:
                errors.append(f"{prefix}: design_spec source_prompt_hash mismatch")
            if prompt_hash:
                prompt_splits[prompt_hash].add(split)
        contract = record.get("geometry_contract")
        if not isinstance(contract, dict):
            errors.append(f"{prefix}: geometry_contract must be an object")
        else:
            expected_mode = MODE_FOR_CATEGORY.get(category)
            if contract.get("generator_mode") != expected_mode:
                errors.append(f"{prefix}: generator_mode must be {expected_mode}")
            if contract.get("contract_sha256") != _canonical_contract_hash(contract):
                errors.append(f"{prefix}: contract_sha256 mismatch")
            coverage = contract.get("requirement_coverage") or {}
            failed_coverage = [
                str(item.get("id") or item.get("relation") or "unknown")
                for group in ("components", "features", "relationships")
                for item in (coverage.get(group) or [])
                if item.get("passed") is not True
            ]
            if failed_coverage:
                errors.append(f"{prefix}: contract requirement coverage failed: {failed_coverage}")
        provenance = record.get("provenance")
        if not isinstance(provenance, dict):
            errors.append(f"{prefix}: provenance must be an object")
        else:
            license_id = str(provenance.get("license") or "")
            if license_id not in allowlist:
                errors.append(f"{prefix}: license is not allowlisted: {license_id}")
            if provenance.get("training_allowed") is not True:
                errors.append(f"{prefix}: provenance.training_allowed must be true")
            for key in ("source_kind", "source_id", "generator_version"):
                if not str(provenance.get(key) or "").strip():
                    errors.append(f"{prefix}: provenance.{key} is required")
        cad_context = record.get("cad_context")
        if cad_context is not None:
            if not isinstance(cad_context, dict):
                errors.append(f"{prefix}: cad_context must be an object")
            elif cad_context.get("schema") != "xconcep.php-cad-context/1.0":
                errors.append(f"{prefix}: unsupported cad_context schema")
            else:
                for key in ("sample_id", "source_format", "parser_mode", "manifest_sha256", "geometry_sha256"):
                    if not str(cad_context.get(key) or "").strip():
                        errors.append(f"{prefix}: cad_context.{key} is required")
                if not isinstance(cad_context.get("entity_counts"), dict):
                    errors.append(f"{prefix}: cad_context.entity_counts must be an object")
                score = cad_context.get("quality_score")
                if not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
                    errors.append(f"{prefix}: cad_context.quality_score must be 0..1")
    for prompt_hash, seen_splits in prompt_splits.items():
        if len(seen_splits) > 1:
            errors.append(f"prompt hash {prompt_hash[:12]} appears across splits: {sorted(seen_splits)}")
    for image_hash, seen_splits in image_splits.items():
        if len(seen_splits) > 1:
            errors.append(f"image hash {image_hash[:12]} appears across splits: {sorted(seen_splits)}")
    if errors:
        raise DatasetValidationError("dataset validation failed:\n- " + "\n- ".join(errors))
    return {
        "schema": "xconcep.cad-vlm-validation/1.0",
        "valid": True,
        "record_count": len(records),
        "image_count": image_count,
        "split_counts": dict(sorted(split_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "allowed_training_licenses": sorted(allowlist),
    }


def _instruction(record: dict[str, Any], target_type: str) -> str:
    target_label = "DesignSpec" if target_type == "design_spec" else "GeometryContract"
    cad_context = record.get("cad_context")
    context_text = ""
    if isinstance(cad_context, dict):
        observed = {key: cad_context.get(key) for key in ("source_format", "parser_mode", "entity_counts", "bbox", "topology", "surfaces")}
        context_text = "\nCAD preprocessing observations (not inferred design intent): " + json.dumps(observed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (
        "여러 시점의 동일한 산업용 대상 이미지를 분석하세요. "
        f"사용자 요구를 만족하는 {target_label} JSON을 생성하세요. "
        "이미지에 보이지 않거나 프롬프트에 없는 부품은 임의로 추가하지 마세요. "
        "치수 단위는 mm, 좌표계는 Z-up/right-handed를 사용하고 JSON 외의 설명은 출력하지 마세요.\n"
        f"요구사항: {record['prompt']}" + context_text
    )


def make_training_example(
    record: dict[str, Any],
    dataset_root: str | Path,
    *,
    target_type: str = "design_spec",
    max_images: int = 3,
) -> dict[str, Any]:
    if target_type not in {"design_spec", "geometry_contract"}:
        raise DatasetValidationError(f"unsupported target_type: {target_type}")
    root = Path(dataset_root).expanduser().resolve()
    images = []
    for relative in [str(value) for value in record["images"][:max_images]]:
        with Image.open(_safe_image_path(root, relative)) as source:
            images.append(source.convert("RGB").copy())
    content = [{"type": "image"} for _ in images]
    content.append({"type": "text", "text": _instruction(record, target_type)})
    target = json.dumps(record[target_type], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "id": record["id"],
        "category": record["category"],
        "images": images,
        "messages": [
            {"role": "user", "content": content},
            {"role": "assistant", "content": [{"type": "text", "text": target}]},
        ],
    }


def to_training_dataset(
    dataset_dir: str | Path,
    *,
    split: str,
    target_type: str,
    max_images: int = 3,
    limit: int | None = None,
):
    from datasets import Dataset
    root = Path(dataset_dir).expanduser().resolve()
    records = [record for record in load_records(root) if record.get("split") == split]
    if limit is not None:
        records = records[: max(0, limit)]
    if not records:
        raise DatasetValidationError(f"no records found for split={split}")
    rows = []
    for record in records:
        rows.append({
            "id": record["id"],
            "category": record["category"],
            "image_paths": [str(_safe_image_path(root, str(value))) for value in record["images"][:max_images]],
            "instruction": _instruction(record, target_type),
            "target_json": json.dumps(
                record[target_type], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        })
    dataset = Dataset.from_list(rows)

    def materialize(batch: dict[str, list[Any]]) -> dict[str, list[Any]]:
        images_batch: list[list[Image.Image]] = []
        messages_batch: list[list[dict[str, Any]]] = []
        for paths, instruction, target in zip(
            batch["image_paths"], batch["instruction"], batch["target_json"], strict=True
        ):
            images: list[Image.Image] = []
            for path in paths:
                with Image.open(path) as source:
                    images.append(source.convert("RGB").copy())
            content = [{"type": "image"} for _ in images]
            content.append({"type": "text", "text": instruction})
            images_batch.append(images)
            messages_batch.append([
                {"role": "user", "content": content},
                {"role": "assistant", "content": [{"type": "text", "text": target}]},
            ])
        return {
            "id": batch["id"],
            "category": batch["category"],
            "images": images_batch,
            "messages": messages_batch,
        }

    dataset.set_transform(materialize)
    return dataset
