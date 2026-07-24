from __future__ import annotations

"""Import CAD AI Dataset Studio PHP packages into raw CAD-VLM JSONL safely."""

import hashlib
import json
import math
import shutil
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .dataset import DatasetValidationError


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(f"invalid PHP artifact JSON: {path}") from exc
    if not isinstance(value, dict):
        raise DatasetValidationError(f"PHP artifact must be an object: {path}")
    return value


def _category(value: str, mapping: dict[str, str]) -> str:
    key = value.strip().lower()
    if key in mapping:
        return mapping[key]
    if any(token in key for token in ("equipment", "enclosure", "cabinet", "machine", "cell")):
        return "equipment"
    if any(token in key for token in ("module", "unit", "assembly", "system")):
        return "module"
    return "part"


def _finite(point: Any) -> tuple[float, float, float] | None:
    if not isinstance(point, list) or len(point) < 2:
        return None
    try:
        result = (float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0)
    except (TypeError, ValueError):
        return None
    return result if all(math.isfinite(value) for value in result) else None


def render_geometry_preview(geometry: dict[str, Any], destination: Path) -> None:
    """Render observed primitives/points into a deterministic RGB PNG."""
    width, height, padding = 900, 600, 45
    image = Image.new("RGB", (width, height), "#071626")
    draw = ImageDraw.Draw(image)
    bbox = geometry.get("bbox") if isinstance(geometry.get("bbox"), dict) else {}
    minimum = _finite(bbox.get("min")) or (0.0, 0.0, 0.0)
    extent = _finite(bbox.get("extent")) or (1.0, 1.0, 0.0)
    scale = min((width - padding * 2) / max(abs(extent[0]), 1.0), (height - padding * 2) / max(abs(extent[1]), 1.0))

    def project(point: Any) -> tuple[float, float] | None:
        value = _finite(point)
        return None if value is None else (padding + (value[0] - minimum[0]) * scale, height - padding - (value[1] - minimum[1]) * scale)

    rendered = 0
    primitives = geometry.get("primitives") if isinstance(geometry.get("primitives"), list) else []
    for primitive in primitives:
        if not isinstance(primitive, dict):
            continue
        if primitive.get("type") == "line":
            start, end = project(primitive.get("start")), project(primitive.get("end"))
            if start and end:
                draw.line((start, end), fill="#38d4ff", width=3)
                rendered += 1
        elif primitive.get("type") == "circle":
            center = project(primitive.get("center"))
            try:
                radius = abs(float(primitive.get("radius"))) * scale
            except (TypeError, ValueError):
                radius = 0.0
            if center and radius > 0:
                draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline="#38d4ff", width=3)
                rendered += 1
    points = [point for point in (project(value) for value in geometry.get("points", [])) if point]
    if rendered == 0 and len(points) > 1:
        draw.line(points, fill="#38d4ff", width=2)
    elif rendered == 0:
        for point in points:
            draw.ellipse((point[0] - 2, point[1] - 2, point[0] + 2, point[1] + 2), fill="#38d4ff")
    draw.text((28, 22), "CAD AI PHP observed geometry preview", fill="#a8bacb")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)


def _package_dirs(source: Path, staging: Path) -> list[Path]:
    def extract(package: Path) -> Path:
        target = staging / package.stem
        with zipfile.ZipFile(package) as archive:
            for name in archive.namelist():
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    raise DatasetValidationError(f"unsafe ZIP member: {name}")
            archive.extractall(target)
        return target

    if source.is_file() and source.suffix.lower() == ".zip":
        return [extract(source)]
    if not source.is_dir():
        raise DatasetValidationError(f"PHP package input not found: {source}")
    packages = [path.parent for path in sorted(source.rglob("manifest.json"))]
    packages.extend(extract(path) for path in sorted(source.glob("*.zip")))
    return packages


def import_php_cad_packages(source: str | Path, output_dir: str | Path, *, license_id: str, training_allowed: bool, category_map: dict[str, str] | None = None, minimum_quality: float = 0.9) -> dict[str, Any]:
    """Create raw JSONL and PNGs from PHP package directories or package ZIPs."""
    if not training_allowed:
        raise DatasetValidationError("--training-allowed is required; package provenance alone is not a training license")
    if not 0.0 <= minimum_quality <= 1.0:
        raise DatasetValidationError("minimum_quality must be between 0 and 1")
    source_path, output = Path(source).expanduser().resolve(), Path(output_dir).expanduser().resolve()
    if output.exists():
        raise DatasetValidationError(f"output directory already exists: {output}")
    mapping = {str(key).lower(): str(value) for key, value in (category_map or {}).items()}
    if any(value not in {"part", "module", "equipment"} for value in mapping.values()):
        raise DatasetValidationError("category map values must be part, module, or equipment")
    staging = output.with_name(output.name + ".staging")
    try:
        packages = _package_dirs(source_path, staging / "unzipped")
        if not packages:
            raise DatasetValidationError("no PHP manifest.json package found")
        rows, skipped, seen_ids = [], [], set()
        for package in packages:
            manifest_path, geometry_path = package / "manifest.json", package / "geometry" / "geometry.json"
            quality_path, label_path = package / "quality" / "report.json", package / "metadata" / "label.json"
            manifest, geometry, quality, label = (_read_json(path) for path in (manifest_path, geometry_path, quality_path, label_path))
            sample_id = str(manifest.get("sample_id") or "")
            if not sample_id or sample_id in seen_ids:
                raise DatasetValidationError(f"missing or duplicate PHP sample_id: {package}")
            seen_ids.add(sample_id)
            score = float(quality.get("score") if isinstance(quality.get("score"), (int, float)) else -1)
            if score < minimum_quality:
                skipped.append({"sample_id": sample_id, "reason": "quality_below_threshold", "quality_score": score})
                continue
            original_category = str(label.get("category") or manifest.get("label", {}).get("category") or "unlabeled")
            source_info = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
            source_format = str(source_info.get("format") or geometry.get("source", {}).get("format") or "cad")
            entity_counts = geometry.get("entity_counts") if isinstance(geometry.get("entity_counts"), dict) else {}
            prompt = str(label.get("training_prompt") or label.get("description") or "").strip() or f"PHP CAD {source_format.upper()} {sample_id}; entities={json.dumps(entity_counts, sort_keys=True)}"
            php_split = str(manifest.get("split") or "").lower()
            split = {"validation": "eval", "valid": "eval"}.get(php_split, php_split)
            preview = staging / "images" / f"{sample_id}.png"
            render_geometry_preview(geometry, preview)
            rows.append({"id": sample_id.lower(), "category": _category(original_category, mapping), "prompt": prompt, **({"split": split} if split in {"train", "eval", "test"} else {}), "images": [{"path": (Path("images") / preview.name).as_posix(), "view": "observed"}], "source_analysis": {"cad_observed": {"bbox": geometry.get("bbox"), "entity_counts": entity_counts, "topology": geometry.get("topology", {}), "surfaces": geometry.get("surfaces", {})}}, "cad_context": {"schema": "xconcep.php-cad-context/1.0", "sample_id": sample_id, "source_format": source_format, "parser_mode": str(geometry.get("parser_mode") or "unknown"), "entity_counts": entity_counts, "bbox": geometry.get("bbox"), "topology": geometry.get("topology", {}), "surfaces": geometry.get("surfaces", {}), "quality_score": score, "manifest_sha256": _sha256(manifest_path), "geometry_sha256": _sha256(geometry_path), "php_split": manifest.get("split"), "category_original": original_category}, "provenance": {"license": license_id, "training_allowed": True, "source_kind": "php_cad_dataset_studio", "source_id": sample_id, "generator_version": str(manifest.get("provenance", {}).get("version") or "1.0.0"), "source_sha256": str(source_info.get("sha256") or ""), "php_manifest_sha256": _sha256(manifest_path)}})
        if not rows:
            raise DatasetValidationError("no PHP samples met the quality threshold")
        (staging / "records.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        report = {"schema": "xconcep.php-cad-import-report/1.0", "source": str(source_path), "imported_count": len(rows), "skipped": skipped, "minimum_quality": minimum_quality}
        (staging / "import_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staging.replace(output)
        return report
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
