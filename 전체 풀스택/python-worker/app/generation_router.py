from __future__ import annotations

import re
from typing import Any

from .parametric_generators import GENERIC_MODE, is_openscad_mode, resolve_generator_mode

FREEFORM_TERMS = {
    "곡면", "유기적", "인체공학", "손잡이", "그립", "외장", "커버", "하우징", "shell", "ergonomic", "freeform", "organic"
}
STRUCTURAL_TERMS = {
    "프레임", "플레이트", "브래킷", "홀", "슬롯", "축", "롤러", "컨베이어", "지그", "각도", "치수", "mm",
    "frame", "plate", "bracket", "hole", "slot", "shaft", "roller", "conveyor", "jig", "dimension"
}
VISUAL_TERMS = {
    "고품질", "리얼리즘", "재질", "조명", "렌더링", "pbr", "material", "lighting", "realistic", "photorealistic"
}
MOTION_TERMS = {
    "동작", "회전", "이동", "시뮬레이션", "애니메이션", "joint", "motion", "simulation", "animation", "openusd", "omniverse"
}


def _has_any(text: str, terms: set[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def _dimension_count(design_state: dict[str, Any]) -> int:
    return sum(value is not None and float(value) > 0 for value in design_state.get("dimensions", {}).values())


def _component_policy(component: dict[str, Any]) -> str:
    text = f"{component.get('id','')} {component.get('name','')}".lower()
    if _has_any(text, FREEFORM_TERMS):
        return "generative_mesh"
    if any(term in text for term in ["motor", "모터", "sensor", "센서", "bearing", "베어링", "bolt", "볼트"]):
        return "catalog_asset"
    return "parametric"


def plan_generation(
    design_state: dict[str, Any],
    output_goal: str,
    quality_profile: str,
    engine_override: str | None,
    has_reference_image: bool,
    low_threshold: float = 0.60,
    high_threshold: float = 0.80,
) -> dict[str, Any]:
    prompt = str(design_state.get("source_prompt") or "")
    dim_count = _dimension_count(design_state)
    structural = _has_any(prompt, STRUCTURAL_TERMS) or dim_count >= 1
    freeform = _has_any(prompt, FREEFORM_TERMS) or (has_reference_image and not structural)
    visual = _has_any(prompt, VISUAL_TERMS) or quality_profile in {"standard", "final"}
    motion = _has_any(prompt, MOTION_TERMS) or output_goal == "motion_openusd"

    reasons: list[str] = []
    if structural:
        reasons.append("치수·프레임·기계 요소가 있어 구조 생성 경로가 필요함")
    if freeform:
        reasons.append("곡면·외관·참고 이미지 특성이 있어 생성 Mesh 경로가 유리함")
    if visual:
        reasons.append("재질·렌더링 품질을 위해 Blender 후처리가 필요함")
    if motion:
        reasons.append("동작·OpenUSD·Omniverse 출력이 필요함")

    force_blender = engine_override == "blender"
    requested_generator_mode = engine_override if is_openscad_mode(engine_override) else None
    generator_mode: str | None = None
    if engine_override:
        # Blender is a post-processor, not a source geometry generator. Build a
        # deterministic source mesh first so the UI's direct Blender option is runnable.
        if requested_generator_mode:
            route = "openscad"
            generator_mode = resolve_generator_mode(requested_generator_mode, str(design_state.get("category") or "equipment"))
        else:
            route = ("openscad" if structural else "hunyuan3d") if force_blender else engine_override
        confidence = 1.0
        if requested_generator_mode:
            reasons.insert(0, f"고급 설정에서 {generator_mode} 파라메트릭 생성기를 직접 지정함")
        else:
            reasons.insert(0, "Blender용 기초 형상을 먼저 생성한 뒤 후처리함" if force_blender else "고급 설정에서 생성 엔진을 직접 지정함")
    elif output_goal == "fast":
        route = "hunyuan3d"
        confidence = 0.95
        reasons.insert(0, "빠른 3D 결과를 우선함")
    elif output_goal == "structural":
        route = "openscad"
        confidence = 0.95
        reasons.insert(0, "구조·치수 중심 결과를 우선함")
    elif output_goal == "high_quality":
        route = "hybrid" if structural and freeform else ("openscad" if structural else "hunyuan3d")
        confidence = 0.85
        reasons.insert(0, "고품질 시각화를 위해 Blender Final 경로를 사용함")
    elif output_goal == "motion_openusd":
        route = "hybrid" if structural and freeform else ("openscad" if structural else "hunyuan3d")
        confidence = 0.88
        reasons.insert(0, "동작·OpenUSD 결과를 위해 Blender와 USD 패키징을 사용함")
    else:
        if structural and freeform:
            route = "hybrid"
            confidence = 0.72
        elif structural:
            route = "openscad"
            confidence = 0.87 if dim_count >= 2 else 0.78
        elif freeform:
            route = "hunyuan3d"
            confidence = 0.84 if has_reference_image else 0.70
        else:
            route = "hunyuan3d"
            confidence = 0.62
            reasons.append("명확한 구조 단서가 적어 빠른 Mesh Preview를 우선함")

    if route in {"openscad", "hybrid"} and generator_mode is None:
        generator_mode = GENERIC_MODE

    postprocess: list[str] = []
    if force_blender or output_goal in {"high_quality", "motion_openusd"} or quality_profile == "final" or route == "hybrid":
        postprocess.append("blender")
    if output_goal == "motion_openusd":
        postprocess.append("openusd")
    elif quality_profile == "final":
        postprocess.append("openusd")

    if route == "hybrid":
        primary_route = "openscad"
        secondary_routes = ["hunyuan3d"]
    else:
        primary_route = route
        secondary_routes = []

    if confidence >= high_threshold:
        execution_policy = "single_primary"
    elif confidence >= low_threshold:
        execution_policy = "primary_with_fallback_preview"
    else:
        execution_policy = "parallel_low_cost_preview"

    component_routes = []
    for component in design_state.get("components", []):
        policy = _component_policy(component)
        engine = {"parametric": "openscad", "generative_mesh": "hunyuan3d", "catalog_asset": "catalog"}[policy]
        component_routes.append({
            "component_id": component.get("id"),
            "representation_policy": policy,
            "engine": engine,
            "generator_mode": generator_mode if engine == "openscad" else None,
        })

    fallback_chain = {
        "hunyuan3d": ["hunyuan3d_retry_background_removed", "openscad_blockout", "blender_blockout"],
        "openscad": ["openscad_simplified_features", "trimesh_parametric_fallback", "blender_blockout"],
        "blender": ["return_source_glb", "queue_final_render_retry"],
        "openusd": ["blender_usd_export", "omniverse_asset_converter", "usda_metadata_package"],
    }

    return {
        "plan_version": "2.0",
        "output_goal": output_goal,
        "quality_profile": quality_profile,
        "primary_route": primary_route,
        "generator_mode": generator_mode,
        "requested_generator_mode": requested_generator_mode,
        "secondary_routes": secondary_routes,
        "postprocess": postprocess,
        "confidence": round(confidence, 3),
        "execution_policy": execution_policy,
        "reasons": reasons or ["기본 자동 추천 경로를 적용함"],
        "component_routes": component_routes,
        "fallback_chain": fallback_chain,
        "user_actions": [
            {"goal": "fast", "label": "더 빠르게 생성"},
            {"goal": "structural", "label": "구조를 정확하게 재생성"},
            {"goal": "high_quality", "label": "더 사실적으로 재생성"},
            {"goal": "motion_openusd", "label": "동작·OpenUSD로 확장"},
        ],
    }
