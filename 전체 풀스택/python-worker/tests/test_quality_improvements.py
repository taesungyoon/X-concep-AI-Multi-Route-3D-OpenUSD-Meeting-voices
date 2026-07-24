from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw

from app.design_state import build_design_state
from app.manufacturing_feedback import evaluate_candidate
from app.parametric_generators import EQUIPMENT_MODE, build_geometry_contract


def _reference(path: Path) -> None:
    image = Image.new("RGB", (256, 256), "white")
    ImageDraw.Draw(image).rectangle((32, 64, 224, 192), fill=(60, 80, 100))
    image.save(path)


def test_export_format_seams_are_welded_before_topology_scoring(tmp_path):
    reference = tmp_path / "reference.png"
    _reference(reference)
    source = trimesh.creation.box(extents=(0.24, 0.16, 0.12))
    vertices = source.vertices[source.faces].reshape((-1, 3))
    faces = np.arange(len(vertices)).reshape((-1, 3))
    seamed = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    assert seamed.is_watertight is False
    glb = tmp_path / "seamed.glb"
    seamed.export(glb)
    contract = {
        "overall": {"width": 240, "depth": 160, "height": 120},
        "requirement_coverage": {
            "components": [{"id": "main_body", "required": 1, "represented": 1, "passed": True}],
            "features": [],
            "relationships": [],
        },
    }

    report = evaluate_candidate(
        reference_path=reference,
        candidate_paths=[reference],
        glb_path=glb,
        contract=contract,
        target=0.95,
    )

    metrics = report["manufacturing"]["metrics"]
    assert metrics["raw_watertight_ratio"] == 0.0
    assert metrics["watertight_ratio"] == 1.0
    assert metrics["positive_volume_ratio"] == 1.0
    assert report["passed"] is True


def test_safety_cover_and_door_have_independent_geometry_coverage():
    prompt = "폭 1400mm 깊이 900mm 높이 1700mm 조립 설비. 안전커버와 전면 안전도어 포함."
    state = build_design_state(
        project_id="QUALITY-COVER",
        revision=1,
        prompt=prompt,
        category="equipment",
        selected_2d_id="CONCEPT-1",
        source_analysis={"dimensions": {}},
    )
    contract = build_geometry_contract(state, "equipment", EQUIPMENT_MODE)
    represented = {item["requirement_id"] for item in contract["components"]}
    coverage = {item["id"]: item for item in contract["requirement_coverage"]["components"]}

    assert {"safety_cover", "safety_door"} <= represented
    assert coverage["safety_cover"]["passed"] is True
    assert coverage["safety_door"]["passed"] is True
