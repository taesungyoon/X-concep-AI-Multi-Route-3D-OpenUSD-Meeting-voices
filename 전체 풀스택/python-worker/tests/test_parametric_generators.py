from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.design_state import build_design_state
from app.generation_router import plan_generation
from app.openscad_engine import generate_openscad
from app.parametric_generators import (
    EQUIPMENT_MODE,
    GENERIC_MODE,
    MODULE_MODE,
    PART_MODE,
    build_geometry_contract,
)


EQUIPMENT_PROMPT = (
    "폭 1600mm, 깊이 1000mm, 높이 1800mm 알루미늄 프로파일 프레임 내부에 "
    "컨베이어 1대와 서보모터 2개, 컨베이어 위 비전 카메라 1개를 배치하고 "
    "전면 투명 안전도어와 우측 제어반을 포함함"
)

PART_PROMPT = (
    "폭 240mm 깊이 160mm 높이 120mm L자형 알루미늄 센서 브래킷. "
    "수직판 중앙에 센서 홀 1개, 베이스판에 체결 홀 4개, 양측 삼각 리브 2개"
)


def _state(prompt: str, category: str):
    return build_design_state(
        project_id="PRJ-PARAMETRIC",
        revision=1,
        prompt=prompt,
        category=category,
        selected_2d_id="CONCEPT-1",
        source_analysis={"dimensions": {}},
    )


def test_equipment_design_spec_extracts_counts_and_relationships():
    state = _state(EQUIPMENT_PROMPT, "equipment")
    spec = state["design_spec"]
    quantities = {item["kind"]: item["quantity"] for item in spec["components"]}

    assert quantities["conveyor"] == 1
    assert quantities["servo_motor"] == 2
    assert quantities["vision_camera"] == 1
    assert quantities["safety_door"] == 1
    assert quantities["control_panel"] == 1
    assert {item["relation"] for item in spec["relationships"]} == {"above", "front_of", "right_of"}


def test_specialized_contract_ignores_ungrounded_analysis_boilerplate():
    state = build_design_state(
        project_id="PRJ-PARAMETRIC-ANALYSIS",
        revision=1,
        prompt=EQUIPMENT_PROMPT,
        category="equipment",
        selected_2d_id="CONCEPT-1",
        source_analysis={
            "main_components": ["base frame", "working unit", "drive unit", "control unit"],
            "dimensions": {},
        },
    )

    contract = build_geometry_contract(state, "equipment", EQUIPMENT_MODE)
    required = {item["id"] for item in contract["hard_constraints"]}

    assert "component:base_frame" not in required
    assert "component:working_unit" not in required
    assert "component:drive_unit" not in required
    assert "component:control_unit" not in required
    assert all(item["passed"] for item in contract["requirement_coverage"]["components"])


def test_part_design_spec_extracts_holes_and_ribs():
    state = _state(PART_PROMPT, "part")
    features = {item["kind"]: item["count"] for item in state["features"]}

    assert features == {"mounting_hole": 4, "sensor_hole": 1, "rib": 2}
    assert state["dimensions"]["width_mm"] == 240
    assert state["dimensions"]["depth_mm"] == 160
    assert state["dimensions"]["height_mm"] == 120


def test_router_preserves_legacy_and_resolves_specialized_modes():
    state = _state(EQUIPMENT_PROMPT, "equipment")

    legacy = plan_generation(state, "structural", "standard", "openscad", True)
    automatic = plan_generation(state, "structural", "standard", "openscad_auto", True)
    forced_part = plan_generation(state, "structural", "standard", "openscad_part", True)

    assert legacy["primary_route"] == "openscad"
    assert legacy["generator_mode"] == GENERIC_MODE
    assert automatic["primary_route"] == "openscad"
    assert automatic["requested_generator_mode"] == "openscad_auto"
    assert automatic["generator_mode"] == EQUIPMENT_MODE
    assert forced_part["generator_mode"] == PART_MODE


@pytest.mark.parametrize(
    ("prompt", "category", "mode", "expected_kinds"),
    [
        (PART_PROMPT, "part", PART_MODE, {"main_body", "rib"}),
        ("서보모터 2개와 리니어 가이드가 있는 작업 모듈", "module", MODULE_MODE, {"base_plate", "linear_guide", "servo_motor", "working_jig"}),
        (EQUIPMENT_PROMPT, "equipment", EQUIPMENT_MODE, {"frame", "conveyor", "servo_motor", "vision_camera", "safety_door", "control_panel"}),
    ],
)
def test_specialized_contracts_represent_required_kinds(prompt, category, mode, expected_kinds):
    state = _state(prompt, category)
    contract = build_geometry_contract(state, category, mode)
    represented = {item["requirement_id"] for item in contract["components"]}

    assert expected_kinds <= represented
    assert all(item["passed"] for item in contract["requirement_coverage"]["components"])
    assert contract["generator_mode"] == mode
    assert len(contract["contract_sha256"]) == 64


def test_equipment_contract_contains_catalog_level_assembly_details():
    contract = build_geometry_contract(_state(EQUIPMENT_PROMPT, "equipment"), "equipment", EQUIPMENT_MODE)
    kind_counts: dict[str, int] = {}
    for item in contract["components"]:
        kind = item["kind"]
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    assert kind_counts["conveyor_side_rail"] == 2
    assert kind_counts["conveyor_support_leg"] == 4
    assert kind_counts["camera_lens"] == 2
    assert kind_counts["camera_optic"] == 1
    assert kind_counts["safety_door_frame"] == 4
    assert kind_counts["safety_door_handle"] == 1
    assert kind_counts["safety_door_hinge"] == 2
    assert kind_counts["control_panel_door"] == 1
    assert kind_counts["hmi_screen"] == 1
    assert kind_counts["panel_handle"] == 1
    assert kind_counts["emergency_stop"] == 1
    assert kind_counts["status_button"] == 2
    assert all(item["passed"] for item in contract["requirement_coverage"]["assembly_details"])

    camera_coverage = next(
        item for item in contract["requirement_coverage"]["components"]
        if item["id"] == "vision_camera"
    )
    assert camera_coverage["required"] == 1
    assert camera_coverage["passed"] is True


def test_vision_inspection_cell_uses_externalized_layout_without_removing_standard_mode():
    inspection = build_geometry_contract(_state(EQUIPMENT_PROMPT, "equipment"), "equipment", EQUIPMENT_MODE)
    standard = build_geometry_contract(
        _state("폭 1600mm 깊이 1000mm 높이 1800mm 일반 포장 설비와 컨베이어", "equipment"),
        "equipment",
        EQUIPMENT_MODE,
    )

    assert inspection["parameters"]["layout_variant"] == "vision_inspection_cell"
    assert standard["parameters"]["layout_variant"] == "standard_cell"

    inspection_by_id = {item["id"]: item for item in inspection["components"]}
    conveyor = inspection_by_id["conveyor_1"]
    control_panel = inspection_by_id["control_panel_1"]
    camera = inspection_by_id["vision_camera_1"]
    cell = inspection["parameters"]["cell_envelope"]

    assert conveyor["size_mm"][1] > conveyor["size_mm"][0]
    assert control_panel["center_mm"][0] > cell["right"]
    assert camera["center_mm"][2] > cell["top"]


def test_part_contract_contains_exact_requested_feature_counts():
    contract = build_geometry_contract(_state(PART_PROMPT, "part"), "part", PART_MODE)
    counts: dict[str, int] = {}
    for item in contract["features"]:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1

    assert counts == {"mounting_hole": 4, "sensor_hole": 1}
    coverage = {item["id"]: item for item in contract["requirement_coverage"]["features"]}
    assert coverage["mounting_hole"] == {"id": "mounting_hole", "required": 4, "represented": 4, "passed": True}
    assert coverage["sensor_hole"]["passed"] is True
    assert coverage["rib"]["passed"] is True


def test_contract_and_mock_exports_are_deterministic(tmp_path: Path):
    state = _state(EQUIPMENT_PROMPT, "equipment")
    first_contract = build_geometry_contract(state, "equipment", EQUIPMENT_MODE)
    second_contract = build_geometry_contract(state, "equipment", EQUIPMENT_MODE)

    assert first_contract["contract_sha256"] == second_contract["contract_sha256"]
    assert first_contract["deterministic_seed"] == second_contract["deterministic_seed"]

    first = generate_openscad(
        design_state=state,
        category="equipment",
        output_dir=tmp_path / "first",
        openscad_bin="missing-openscad",
        timeout_seconds=5,
        mode="mock",
        generator_mode=EQUIPMENT_MODE,
    )
    second = generate_openscad(
        design_state=state,
        category="equipment",
        output_dir=tmp_path / "second",
        openscad_bin="missing-openscad",
        timeout_seconds=5,
        mode="mock",
        generator_mode=EQUIPMENT_MODE,
    )

    assert first.scad_path.read_bytes() == second.scad_path.read_bytes()
    assert first.geometry_json_path.read_bytes() == second.geometry_json_path.read_bytes()
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["generator_mode"] == EQUIPMENT_MODE
    assert manifest["requirement_coverage"]["relationships"]


def test_legacy_openscad_template_remains_available(tmp_path: Path):
    generated = generate_openscad(
        design_state=_state(PART_PROMPT, "part"),
        category="part",
        output_dir=tmp_path,
        openscad_bin="missing-openscad",
        timeout_seconds=5,
        mode="mock",
        generator_mode=GENERIC_MODE,
    )
    geometry = json.loads(generated.geometry_json_path.read_text(encoding="utf-8"))
    manifest = json.loads(generated.manifest_path.read_text(encoding="utf-8"))

    assert geometry["features"] == ["base", "supports", "work_unit", "mounting_holes"]
    assert manifest["generator_mode"] == GENERIC_MODE
    assert generated.provider["generator_version"] == "legacy-1.0"
