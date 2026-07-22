from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

GRADE_ORDER = ["concept", "structured", "validated", "engineer_reviewed", "manufacturing_approved"]
GRADE_LABELS = {
    "concept": "컨셉 검토 가능",
    "structured": "구조 검토 가능",
    "validated": "자동 검증 통과",
    "engineer_reviewed": "엔지니어 검토 완료",
    "manufacturing_approved": "제조 승인 완료",
}


def _scene_metrics(glb_path: Path) -> dict[str, Any]:
    loaded = trimesh.load(glb_path, force="scene")
    if isinstance(loaded, trimesh.Trimesh):
        loaded = trimesh.Scene(loaded)
    if not isinstance(loaded, trimesh.Scene):
        raise RuntimeError("GLB를 Scene으로 읽지 못함")
    meshes: list[trimesh.Trimesh] = []
    material_count = 0
    texture_count = 0
    for node in loaded.graph.nodes_geometry:
        transform, geom_name = loaded.graph.get(node)
        mesh = loaded.geometry[geom_name].copy()
        mesh.apply_transform(transform)
        if isinstance(mesh, trimesh.Trimesh):
            meshes.append(mesh)
            material = getattr(mesh.visual, "material", None)
            if material is not None:
                material_count += 1
                if getattr(material, "image", None) is not None or getattr(material, "baseColorTexture", None) is not None:
                    texture_count += 1
    if not meshes:
        raise RuntimeError("GLB에 메시가 없음")
    merged = trimesh.util.concatenate(meshes)
    extents = [float(x) for x in merged.bounding_box.extents]
    return {
        "mesh_count": len(meshes),
        "vertex_count": int(sum(len(mesh.vertices) for mesh in meshes)),
        "face_count": int(sum(len(mesh.faces) for mesh in meshes)),
        "watertight_meshes": int(sum(bool(mesh.is_watertight) for mesh in meshes)),
        "bounding_box": extents,
        "material_count": material_count,
        "texture_count": texture_count,
        "finite_vertices": bool(np.isfinite(merged.vertices).all()),
        "positive_extents": all(value > 1e-8 for value in extents),
    }


def _expected_dimensions_m(design_state: dict[str, Any]) -> list[float] | None:
    dims = design_state.get("dimensions", {})
    values = [dims.get("width_mm") or dims.get("length_mm"), dims.get("depth_mm"), dims.get("height_mm")]
    if not all(isinstance(value, (int, float)) and float(value) > 0 for value in values):
        return None
    return [float(value) / 1000.0 for value in values]


def validate_asset(
    *,
    glb_path: Path,
    route: str,
    design_state: dict[str, Any],
    manifest_path: Path | None = None,
    dimension_tolerance_pct: float = 5.0,
    blender_processed: bool = False,
) -> dict[str, Any]:
    metrics = _scene_metrics(glb_path)
    checks: list[dict[str, Any]] = []
    checks.append({"id": "mesh_exists", "label": "Mesh 생성", "passed": metrics["mesh_count"] > 0, "value": metrics["mesh_count"]})
    checks.append({"id": "geometry_finite", "label": "비정상 좌표 없음", "passed": metrics["finite_vertices"], "value": metrics["finite_vertices"]})
    checks.append({"id": "bounding_box", "label": "Bounding Box 정상", "passed": metrics["positive_extents"], "value": metrics["bounding_box"]})
    checks.append({"id": "faces", "label": "Face 존재", "passed": metrics["face_count"] > 0, "value": metrics["face_count"]})

    expected = _expected_dimensions_m(design_state)
    dimension_score = None
    if expected and route in {"openscad", "hybrid"}:
        actual = sorted(metrics["bounding_box"], reverse=True)
        target = sorted(expected, reverse=True)
        errors = [abs(a - t) / max(t, 1e-9) * 100 for a, t in zip(actual, target)]
        dimension_score = max(0.0, 1.0 - sum(min(error, 100) for error in errors) / 300.0)
        checks.append({
            "id": "dimension_contract",
            "label": "주요 치수 계약",
            "passed": all(error <= dimension_tolerance_pct for error in errors),
            "value": {"expected_m": target, "actual_m": actual, "error_pct": [round(x, 2) for x in errors]},
        })

    manifest_components = 0
    manifest: dict[str, Any] = {}
    if manifest_path and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_components = len(manifest.get("parts", []))
        except Exception:
            manifest = {}
            manifest_components = 0
    required_components = len([item for item in design_state.get("components", []) if item.get("required", True)])
    coverage = manifest.get("requirement_coverage") or {}
    component_rows = list(coverage.get("components") or [])
    feature_rows = list(coverage.get("features") or [])
    relationship_rows = list(coverage.get("relationships") or [])

    if component_rows:
        required_total = sum(max(1, int(item.get("required") or 1)) for item in component_rows)
        represented_total = sum(min(max(0, int(item.get("represented") or 0)), max(1, int(item.get("required") or 1))) for item in component_rows)
        component_score = represented_total / max(required_total, 1)
        component_passed = all(bool(item.get("passed")) for item in component_rows)
        component_value: Any = component_rows
    else:
        component_score = min(1.0, manifest_components / max(required_components, 1)) if manifest_components else (0.65 if route == "hunyuan3d" else 0.8)
        component_passed = component_score >= 0.7
        component_value = {"required": required_components, "represented": manifest_components or "mesh_estimate", "score": round(component_score, 3)}
    checks.append({
        "id": "component_contract",
        "label": "필수 구성요소 계약",
        "passed": component_passed,
        "value": component_value,
    })

    feature_score: float | None = None
    if feature_rows:
        required_total = sum(max(1, int(item.get("required") or 1)) for item in feature_rows)
        represented_total = sum(min(max(0, int(item.get("represented") or 0)), max(1, int(item.get("required") or 1))) for item in feature_rows)
        feature_score = represented_total / max(required_total, 1)
        checks.append({
            "id": "feature_contract",
            "label": "필수 형상 특징 계약",
            "passed": all(bool(item.get("passed")) for item in feature_rows),
            "value": feature_rows,
        })

    relationship_score: float | None = None
    if relationship_rows:
        relationship_score = sum(bool(item.get("passed")) for item in relationship_rows) / len(relationship_rows)
        checks.append({
            "id": "relationship_contract",
            "label": "구성요소 배치 관계 계약",
            "passed": all(bool(item.get("passed")) for item in relationship_rows),
            "value": relationship_rows,
        })

    multiview_validation = manifest.get("multiview_validation") or {}
    multiview_score: float | None = None
    if multiview_validation:
        multiview_score = float(multiview_validation.get("score") or 0.0)
        checks.append({
            "id": "multiview_contract",
            "label": "정면·상면·측면 계약 검증",
            "passed": multiview_validation.get("passed") is True,
            "value": multiview_validation.get("checks") or [],
        })

    semantic_validation = manifest.get("semantic_validation") or {}
    semantic_passed = semantic_validation.get("passed") is True
    if semantic_validation:
        checks.append({
            "id": "independent_semantic_validation",
            "label": "독립 의미·형상 검증",
            "passed": semantic_passed,
            "value": semantic_validation,
        })

    if route == "hunyuan3d":
        grade = "concept"
    elif route in {"openscad", "hybrid"}:
        grade = "structured"
    else:
        grade = "concept"

    all_core_passed = all(check["passed"] for check in checks[:4])
    contract_passed = all(check["passed"] for check in checks[4:] if check["id"] != "independent_semantic_validation") if len(checks) > 4 else True
    if all_core_passed and contract_passed and semantic_passed and (route in {"openscad", "hybrid"} or blender_processed):
        grade = "validated"

    available_requirement_scores = [component_score]
    if feature_score is not None:
        available_requirement_scores.append(feature_score)
    if relationship_score is not None:
        available_requirement_scores.append(relationship_score)
    functional_score = min(available_requirement_scores) if coverage else 0.5
    silhouette_score = float(semantic_validation.get("silhouette_score") or 0.0)
    detail_score = float(semantic_validation.get("detail_score") or (0.25 if blender_processed else 0.0))
    dimension_layout_score = (
        multiview_score
        if multiview_score is not None
        else dimension_score if dimension_score is not None
        else relationship_score or 0.0
    )
    scores = {
        "functional_match": round(functional_score, 3),
        "component_match": round(component_score, 3),
        "dimension_and_layout_match": round(dimension_layout_score, 3),
        "silhouette_match": round(silhouette_score, 3),
        "detail_appearance_match": round(detail_score, 3),
    }
    weighted = (
        scores["functional_match"] * 0.30
        + scores["component_match"] * 0.25
        + scores["dimension_and_layout_match"] * 0.22
        + scores["silhouette_match"] * 0.15
        + scores["detail_appearance_match"] * 0.08
    )

    usage = {
        "concept": ["외관·아이디어 검토", "고객 커뮤니케이션", "제안 자료"],
        "structured": ["구조·배치 검토", "초기 엔지니어링", "후속 CAD 입력"],
        "validated": ["자동 검증 완료 구조 검토", "후속 CAD 설계 입력", "시뮬레이션 자산 준비"],
        "engineer_reviewed": ["상세설계 진행", "제조성 검토 입력"],
        "manufacturing_approved": ["승인 범위 내 제작 기준 데이터"],
    }[grade]
    return {
        "grade": grade,
        "grade_label": GRADE_LABELS[grade],
        "automatic_grade_ceiling": "validated" if semantic_validation else "structured",
        "score": round(weighted, 3),
        "scores": scores,
        "checks": checks,
        "metrics": metrics,
        "multiview": multiview_validation,
        "regeneration_plan": multiview_validation.get("regeneration_plan") or {
            "recommended": False,
            "scopes": [],
            "strategy": "none",
        },
        "usage_scope": usage,
        "next_required_review": "엔지니어 검토" if grade in {"concept", "structured", "validated"} else "제조 승인",
        "manufacturing_note": (
            "생성 결과는 검증 수준에 따라 컨셉 검토, 구조 검토, 상세설계 입력, 시뮬레이션 자산으로 활용함. "
            "공차·재료 강도·체결·가공·조립·안전 조건은 자동 검증과 엔지니어 검토 후 확정해야 함."
        ),
        "consistency_priority": [
            "기능 및 동작 원리", "필수 구성요소", "주요 치수와 배치", "전체 비례와 실루엣", "재질·곡면·세부 외관"
        ],
    }


def apply_manual_grade(validation: dict[str, Any], requested_grade: str, reviewer: str, note: str) -> dict[str, Any]:
    current = validation.get("grade", "concept")
    if GRADE_ORDER.index(requested_grade) <= GRADE_ORDER.index(current):
        raise ValueError("현재 등급보다 높은 수동 검토 등급만 적용할 수 있음")
    validation = dict(validation)
    validation["grade"] = requested_grade
    validation["grade_label"] = GRADE_LABELS[requested_grade]
    validation["manual_review"] = {"reviewer": reviewer, "note": note}
    validation["usage_scope"] = {
        "engineer_reviewed": ["상세설계 진행", "제조성 검토 입력"],
        "manufacturing_approved": ["승인 범위 내 제작 기준 데이터"],
    }[requested_grade]
    return validation
