from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
import trimesh
from PIL import Image

EVALUATOR_SCHEMA = "xconcep.manufacturing-feedback/1.0"


def _foreground_mask(path: Path, size: int = 128) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    image.thumbnail((768, 768), Image.Resampling.LANCZOS)
    pixels = np.asarray(image, dtype=np.float32)
    border = np.concatenate((pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]), axis=0)
    background = np.median(border, axis=0)
    distance = np.linalg.norm(pixels - background, axis=2)
    threshold = max(18.0, float(np.percentile(distance, 65)) * 0.42)
    mask = distance > threshold
    neighbours = np.zeros(mask.shape, dtype=np.uint8)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
        neighbours += np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    mask = mask & (neighbours >= 2)
    points = np.argwhere(mask)
    if len(points) < 16:
        return np.zeros((size, size), dtype=bool)
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    cropped = mask[y0:y1, x0:x1]
    height, width = cropped.shape
    pad = max(2, int(max(height, width) * 0.08))
    side = max(height, width) + pad * 2
    square = np.zeros((side, side), dtype=np.uint8)
    oy = (side - height) // 2
    ox = (side - width) // 2
    square[oy:oy + height, ox:ox + width] = cropped.astype(np.uint8) * 255
    normalized = Image.fromarray(square).resize((size, size), Image.Resampling.NEAREST)
    return np.asarray(normalized) > 127


def _edge(mask: np.ndarray) -> np.ndarray:
    eroded = mask.copy()
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        eroded &= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return mask ^ eroded


def _iou(left: np.ndarray, right: np.ndarray) -> float:
    union = np.logical_or(left, right).sum()
    return float(np.logical_and(left, right).sum() / union) if union else 0.0


def _profile_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_profile = np.concatenate((left.mean(axis=0), left.mean(axis=1)))
    right_profile = np.concatenate((right.mean(axis=0), right.mean(axis=1)))
    return float(np.clip(1.0 - np.mean(np.abs(left_profile - right_profile)), 0.0, 1.0))


def _aspect(mask: np.ndarray) -> float:
    points = np.argwhere(mask)
    if len(points) < 2:
        return 0.0
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    return float((x1 - x0) / max(y1 - y0, 1))


def compare_appearance(reference_path: Path, candidate_paths: list[Path]) -> dict[str, Any]:
    reference = _foreground_mask(reference_path)
    reference_edge = _edge(reference)
    reference_aspect = _aspect(reference)
    candidates: list[dict[str, Any]] = []
    for path in candidate_paths:
        if not path.exists():
            continue
        candidate = _foreground_mask(path)
        scores: list[dict[str, float]] = []
        for variant in (candidate, np.fliplr(candidate)):
            silhouette = _iou(reference, variant)
            edge = _iou(reference_edge, _edge(variant))
            profile = _profile_similarity(reference, variant)
            candidate_aspect = _aspect(variant)
            aspect = min(reference_aspect, candidate_aspect) / max(reference_aspect, candidate_aspect, 1e-9)
            score = silhouette * 0.48 + profile * 0.27 + aspect * 0.15 + edge * 0.10
            scores.append({"score": score, "silhouette_iou": silhouette, "profile_similarity": profile, "aspect_similarity": aspect, "edge_iou": edge})
        best = max(scores, key=lambda item: item["score"])
        candidates.append({"path": str(path), **{key: round(value, 4) for key, value in best.items()}})
    primary_candidate = candidates[0] if candidates else None
    best_candidate = max(candidates, key=lambda item: item["score"], default=None)
    return {
        "independent": True,
        "method": "background-normalized silhouette, projection profile, aspect, and edge comparison",
        "selection_policy": "primary final render gates quality; best alternate projection is diagnostic only",
        "reference": str(reference_path),
        "score": float(primary_candidate["score"]) if primary_candidate else 0.0,
        "primary_candidate": primary_candidate,
        "best_candidate": best_candidate,
        "diagnostic_best_score": float(best_candidate["score"]) if best_candidate else 0.0,
        "candidates": candidates,
    }


def _load_meshes(glb_path: Path) -> list[trimesh.Trimesh]:
    loaded = trimesh.load(glb_path, force="scene")
    if isinstance(loaded, trimesh.Trimesh):
        return [loaded]
    meshes: list[trimesh.Trimesh] = []
    for node in loaded.graph.nodes_geometry:
        transform, geometry_name = loaded.graph.get(node)
        mesh = loaded.geometry[geometry_name].copy()
        if isinstance(mesh, trimesh.Trimesh):
            mesh.apply_transform(transform)
            meshes.append(mesh)
    return meshes


def _normalize_topology(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Weld export-format seams before judging manufacturing topology."""
    normalized = mesh.copy()
    normalized.remove_infinite_values()
    normalized.merge_vertices()
    try:
        normalized.update_faces(normalized.nondegenerate_faces())
    except (AttributeError, TypeError):
        normalized.remove_degenerate_faces()
    normalized.remove_unreferenced_vertices()
    try:
        trimesh.repair.fix_normals(normalized, multibody=True)
    except TypeError:
        trimesh.repair.fix_normals(normalized)
    return normalized


def _manufacturing_bodies(meshes: list[trimesh.Trimesh]) -> list[trimesh.Trimesh]:
    bodies: list[trimesh.Trimesh] = []
    for mesh in meshes:
        normalized = _normalize_topology(mesh)
        try:
            separated = list(normalized.split(only_watertight=False))
        except (TypeError, ValueError):
            separated = []
        bodies.extend(_normalize_topology(body) for body in separated if len(body.faces))
        if not separated and len(normalized.faces):
            bodies.append(normalized)
    return bodies


def _coverage_score(contract: dict[str, Any]) -> tuple[float, list[str]]:
    coverage = contract.get("requirement_coverage") or {}
    rows = [item for group in ("components", "features", "relationships") for item in (coverage.get(group) or [])]
    if not rows:
        return 0.0, []
    required = sum(max(1, int(item.get("required") or 1)) for item in rows)
    represented = sum(min(max(0, int(item.get("represented") or int(bool(item.get("passed"))))), max(1, int(item.get("required") or 1))) for item in rows)
    failed = [str(item.get("id")) for item in rows if not item.get("passed") and item.get("id")]
    return represented / max(required, 1), failed


def _assembly_detail_score(contract: dict[str, Any]) -> tuple[float, list[str], int]:
    rows = list((contract.get("requirement_coverage") or {}).get("assembly_details") or [])
    if not rows:
        return 1.0, [], 0
    required = sum(max(1, int(item.get("required") or 1)) for item in rows)
    represented = sum(
        min(max(0, int(item.get("represented") or 0)), max(1, int(item.get("required") or 1)))
        for item in rows
    )
    failed = [str(item.get("id")) for item in rows if not item.get("passed") and item.get("id")]
    return represented / max(required, 1), failed, len(rows)


def inspect_manufacturing(glb_path: Path, contract: dict[str, Any], dimension_tolerance_pct: float = 5.0) -> dict[str, Any]:
    source_meshes = _load_meshes(glb_path)
    if not source_meshes:
        return {"score": 0.0, "passed": False, "checks": [], "failed_requirements": []}
    raw_watertight_ratio = sum(bool(mesh.is_watertight) for mesh in source_meshes) / len(source_meshes)
    meshes = _manufacturing_bodies(source_meshes)
    if not meshes:
        return {"score": 0.0, "passed": False, "checks": [], "failed_requirements": []}
    merged = trimesh.util.concatenate(meshes)
    vertices = np.asarray(merged.vertices)
    face_areas = np.asarray(merged.area_faces)
    finite = bool(np.isfinite(vertices).all())
    nondegenerate_ratio = float(np.mean(face_areas > 1e-12)) if len(face_areas) else 0.0
    watertight_ratio = sum(bool(mesh.is_watertight) for mesh in meshes) / len(meshes)
    positive_volume_ratio = sum(bool(mesh.is_volume) and float(mesh.volume) > 0 for mesh in meshes) / len(meshes)
    target = contract.get("overall_dimensions_mm") or contract.get("overall") or {}
    target_m = [float(target.get(key) or 0.0) / 1000.0 for key in ("width", "depth", "height")]
    actual_m = [float(value) for value in merged.bounding_box.extents]
    if all(value > 0 for value in target_m):
        ordered_target = sorted(target_m, reverse=True)
        ordered_actual = sorted(actual_m, reverse=True)
        errors = [abs(actual - expected) / expected * 100.0 for actual, expected in zip(ordered_actual, ordered_target)]
        dimension_score = max(0.0, 1.0 - sum(min(error, 100.0) for error in errors) / 300.0)
        dimension_passed = all(error <= dimension_tolerance_pct for error in errors)
    else:
        errors, dimension_score, dimension_passed = [], 0.0, False
    coverage_score, failed_requirements = _coverage_score(contract)
    detail_score, failed_details, detail_check_count = _assembly_detail_score(contract)
    failed_requirements.extend(failed_details)
    geometry_score = (float(finite) + nondegenerate_ratio + positive_volume_ratio) / 3.0
    score = geometry_score * 0.23 + watertight_ratio * 0.18 + dimension_score * 0.33 + coverage_score * 0.18 + detail_score * 0.08
    checks = [
        {"id": "finite_vertices", "passed": finite, "value": finite},
        {"id": "nondegenerate_faces", "passed": nondegenerate_ratio >= 0.999, "value": round(nondegenerate_ratio, 4)},
        {"id": "watertight_bodies", "passed": watertight_ratio >= 0.999, "value": round(watertight_ratio, 4)},
        {"id": "positive_volume", "passed": positive_volume_ratio >= 0.999, "value": round(positive_volume_ratio, 4)},
        {"id": "dimension_contract", "passed": dimension_passed, "value": {"actual_m": actual_m, "target_m": target_m, "error_pct": [round(value, 3) for value in errors]}},
        {"id": "requirement_coverage", "passed": coverage_score >= 0.999, "value": round(coverage_score, 4), "independent": False},
    ]
    if detail_check_count:
        checks.append({
            "id": "assembly_detail_contract",
            "passed": detail_score >= 0.999,
            "value": round(detail_score, 4),
            "detail_check_count": detail_check_count,
            "independent": False,
        })
    return {
        "independent_geometry_checks": True,
        "contract_coverage_independent": False,
        "score": round(score, 4),
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "failed_requirements": failed_requirements,
        "metrics": {
            "source_mesh_count": len(source_meshes),
            "manufacturing_body_count": len(meshes),
            "vertex_count": int(sum(len(mesh.vertices) for mesh in meshes)),
            "face_count": int(sum(len(mesh.faces) for mesh in meshes)),
            "raw_watertight_ratio": round(raw_watertight_ratio, 4),
            "watertight_ratio": round(watertight_ratio, 4),
            "positive_volume_ratio": round(positive_volume_ratio, 4),
            "nondegenerate_ratio": round(nondegenerate_ratio, 4),
            "topology_normalization": "weld duplicate format-seam vertices, remove degenerate faces, and fix winding",
        },
    }


def evaluate_candidate(*, reference_path: Path, candidate_paths: list[Path], glb_path: Path, contract: dict[str, Any], target: float = 0.95, dimension_tolerance_pct: float = 5.0) -> dict[str, Any]:
    appearance = compare_appearance(reference_path, candidate_paths)
    manufacturing = inspect_manufacturing(glb_path, contract, dimension_tolerance_pct)
    appearance_score = float(appearance["score"])
    manufacturing_score = float(manufacturing["score"])
    failed_scopes = list(manufacturing.get("failed_requirements") or [])
    if appearance_score < target and not failed_scopes:
        coverage = contract.get("requirement_coverage") or {}
        failed_scopes = [str(item.get("id")) for item in (coverage.get("components") or []) if item.get("id")]
    actions: list[str] = []
    if appearance_score < target:
        actions.append("improve reference silhouette and proportions without changing explicit dimensions")
    if manufacturing_score < target:
        actions.append("repair mesh topology, dimensions, or requirement coverage before promotion")
    passed = appearance_score >= target and manufacturing_score >= target
    return {"schema": EVALUATOR_SCHEMA, "independent_evaluation": True, "target": target, "passed": passed, "score": round(min(appearance_score, manufacturing_score), 4), "silhouette_score": round(appearance_score, 4), "detail_score": round(float((appearance.get("primary_candidate") or {}).get("edge_iou") or 0.0), 4), "appearance": appearance, "manufacturing": manufacturing, "regeneration_plan": {"recommended": not passed, "scopes": sorted(set(failed_scopes)), "strategy": "bounded_self_feedback", "max_attempts": 3, "preserve_best_candidate": True, "actions": actions}, "automatic_grade_ceiling": "validated", "manufacturing_approval": False}


def select_best_candidate(reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(reports, key=lambda item: float(item.get("score") or 0.0), default=None)


def run_bounded_feedback_loop(candidate_factory: Callable[[int, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]], evaluator: Callable[[dict[str, Any]], dict[str, Any]], *, max_attempts: int = 3) -> dict[str, Any]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    attempts: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    feedback: dict[str, Any] | None = None
    for attempt_index in range(1, max_attempts + 1):
        candidate = candidate_factory(attempt_index, feedback, best)
        report = evaluator(candidate)
        attempts.append({"attempt": attempt_index, "candidate": candidate, "report": report, "score": report.get("score", 0.0)})
        best = max(attempts, key=lambda item: float(item.get("score") or 0.0))
        feedback = report.get("regeneration_plan") or {}
        if report.get("passed") is True:
            break
    return {"schema": "xconcep.bounded-self-feedback/1.0", "attempts": attempts, "attempt_count": len(attempts), "best_attempt": best, "target_achieved": bool(best and best["report"].get("passed") is True), "stopped_reason": "target_achieved" if best and best["report"].get("passed") is True else "attempt_budget_exhausted"}


def wilson_lower_bound(successes: int, total: int, z: float = 1.959963984540054) -> float:
    if total <= 0:
        return 0.0
    probability = successes / total
    denominator = 1.0 + z * z / total
    centre = probability + z * z / (2.0 * total)
    margin = z * math.sqrt(probability * (1.0 - probability) / total + z * z / (4.0 * total * total))
    return max(0.0, (centre - margin) / denominator)


def score_holdout(reports: list[dict[str, Any]], *, target: float = 0.95, min_cases_per_category: int = 200) -> dict[str, Any]:
    categories = sorted({str(item.get("category") or "unknown") for item in reports})
    rows: dict[str, Any] = {}
    for category in categories:
        items = [item for item in reports if str(item.get("category") or "unknown") == category]
        successes = sum(bool(item.get("passed")) for item in items)
        total = len(items)
        lower = wilson_lower_bound(successes, total)
        rows[category] = {"successes": successes, "total": total, "observed_rate": round(successes / total, 4) if total else 0.0, "wilson_95_lower": round(lower, 4), "passed": total >= min_cases_per_category and lower >= target}
    return {"target": target, "min_cases_per_category": min_cases_per_category, "categories": rows, "target_achieved": bool(rows) and all(row["passed"] for row in rows.values())}
