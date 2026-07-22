from __future__ import annotations

import copy
import json

from app.contract_validation import validate_contract_multiview
from app.design_state import build_design_state
from app.parametric_generators import (
    EQUIPMENT_MODE,
    apply_partial_regeneration,
    build_geometry_contract,
)


PROMPT = (
    "폭 1600mm 깊이 1000mm 높이 1800mm 알루미늄 프로파일 프레임 내부에 "
    "컨베이어 1대와 서보모터 2개, 컨베이어 위 비전 카메라 1개를 배치하고 "
    "전면 투명 안전도어와 우측 제어반을 포함함"
)


def _contract():
    state = build_design_state(
        project_id="PRJ-MULTIVIEW",
        revision=1,
        prompt=PROMPT,
        category="equipment",
        selected_2d_id="CONCEPT-1",
        source_analysis={"dimensions": {}},
    )
    return build_geometry_contract(state, "equipment", EQUIPMENT_MODE)


def test_multiview_validation_writes_three_views_and_passes(tmp_path):
    report = validate_contract_multiview(_contract(), tmp_path / "views")

    assert report["passed"] is True
    assert report["regeneration_plan"]["scopes"] == []
    assert set(report["views"]) == {"front", "top", "right"}
    assert all((tmp_path / item["file"]).is_file() for item in report["views"].values())
    assert (tmp_path / "multiview_validation.json").is_file()
    assert all(check["passed"] for check in report["checks"])


def test_multiview_failure_targets_relationship_subject(tmp_path):
    contract = _contract()
    for component in contract["components"]:
        if component.get("requirement_id") == "vision_camera":
            component["center_mm"][2] = 100.0

    report = validate_contract_multiview(contract, tmp_path / "views")
    relationship_check = next(
        check for check in report["checks"] if check["id"] == "geometric_relationships"
    )

    assert report["passed"] is False
    assert relationship_check["passed"] is False
    assert "vision_camera" in report["regeneration_plan"]["scopes"]


def test_partial_regeneration_replaces_only_requested_requirement_group():
    previous = _contract()
    candidate = copy.deepcopy(previous)
    previous["components"][0]["preserved_marker"] = "keep"
    for component in candidate["components"]:
        if component.get("requirement_id") == "servo_motor":
            component["center_mm"][0] += 25.0

    merged = apply_partial_regeneration(
        previous,
        candidate,
        ["component:servo_motor"],
    )

    frame = next(item for item in merged["components"] if item["id"] == "frame_post_1")
    previous_servo = next(item for item in previous["components"] if item["id"] == "servo_motor_1")
    merged_servo = next(item for item in merged["components"] if item["id"] == "servo_motor_1")

    assert frame["preserved_marker"] == "keep"
    assert merged_servo["center_mm"][0] == previous_servo["center_mm"][0] + 25.0
    assert merged["partial_regeneration"]["applied"] is True
    assert "frame_post_1" in merged["partial_regeneration"]["preserved_component_ids"]
    assert "servo_motor_1" in merged["partial_regeneration"]["regenerated_component_ids"]
    assert all(item["passed"] for item in merged["requirement_coverage"]["components"])
    assert len(merged["contract_sha256"]) == 64


def test_partial_regeneration_falls_back_when_outer_dimensions_change():
    previous = _contract()
    candidate = copy.deepcopy(previous)
    candidate["overall"]["width"] += 100.0

    merged = apply_partial_regeneration(previous, candidate, ["servo_motor"])

    assert merged["partial_regeneration"]["applied"] is False
    assert merged["partial_regeneration"]["fallback"] == "full_regeneration"
    assert merged["partial_regeneration"]["reason"] == "overall_dimensions_changed"


def test_multiview_report_is_valid_json(tmp_path):
    validate_contract_multiview(_contract(), tmp_path / "views")
    report = json.loads((tmp_path / "multiview_validation.json").read_text(encoding="utf-8"))

    assert report["schema"] == "xconcep.contract-multiview/1.0"
    assert report["independent"] is False
