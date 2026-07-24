from pathlib import Path

import pytest
import trimesh

from app.design_state import build_design_state
from app.generation_router import plan_generation
from app.openscad_engine import _stl_to_glb, generate_openscad


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("폭 900mm, 깊이 60cm, 높이 1.2m 검사 프레임", (900, 600, 1200)),
        ("width 900mm, depth 600mm, height 1200mm inspection frame", (900, 600, 1200)),
        ("1600mm width, 100cm depth, 1.8m height inspection frame", (1600, 1000, 1800)),
    ],
)
def test_design_state_recovers_labelled_dimensions_from_prompt(prompt, expected):
    state = build_design_state(
        project_id="PRJ-TEST",
        revision=1,
        prompt=prompt,
        category="equipment",
        selected_2d_id="concept-1",
        source_analysis={"dimensions": {"width_mm": None, "depth_mm": None, "height_mm": None}},
    )

    assert tuple(state["dimensions"][key] for key in ("width_mm", "depth_mm", "height_mm")) == expected


def test_structured_dimensions_take_precedence_over_prompt_values():
    state = build_design_state(
        project_id="PRJ-TEST",
        revision=1,
        prompt="width 900mm, depth 600mm, height 1200mm",
        category="equipment",
        selected_2d_id="concept-1",
        source_analysis={"dimensions": {"width_mm": 1000, "depth_mm": 700, "height_mm": 1300}},
    )

    assert state["dimensions"] == {"width_mm": 1000.0, "depth_mm": 700.0, "height_mm": 1300.0, "length_mm": None}


def test_saved_design_spec_components_override_generic_analysis_summary():
    state = build_design_state(
        project_id="PRJ-TEST",
        revision=2,
        prompt="1600mm width inspection equipment with 2 servo motors",
        category="equipment",
        selected_2d_id="CONCEPT-1",
        source_analysis={
            "main_components": ["base frame", "working unit"],
            "design_spec": {
                "components": [
                    {
                        "id": "servo_motor",
                        "kind": "servo_motor",
                        "name": "servo motor",
                        "quantity": 2,
                        "required": True,
                        "source": "prompt",
                    }
                ]
            },
        },
    )

    assert state["components"] == [
        {
            "id": "servo_motor",
            "kind": "servo_motor",
            "name": "servo motor",
            "quantity": 2,
            "required": True,
            "source": "prompt",
        }
    ]


def test_openscad_stl_millimetres_are_exported_as_glb_metres(tmp_path):
    stl_path = tmp_path / "source.stl"
    glb_path = tmp_path / "result.glb"
    trimesh.creation.box(extents=(900, 600, 1200)).export(stl_path)

    _stl_to_glb(stl_path, glb_path)

    scene = trimesh.load(glb_path, force="scene")
    assert sorted(scene.extents, reverse=True) == pytest.approx([1.2, 0.9, 0.6], abs=1e-5)


def test_native_openscad_does_not_hide_missing_binary_with_fallback(tmp_path):
    with pytest.raises(RuntimeError, match="native binary not found"):
        generate_openscad(
            design_state={"dimensions": {"width_mm": 300, "depth_mm": 200, "height_mm": 120}},
            category="part",
            output_dir=tmp_path,
            openscad_bin=str(tmp_path / "missing-openscad.exe"),
            timeout_seconds=5,
            mode="native",
        )


def test_direct_blender_override_creates_source_geometry_then_postprocesses():
    state = {
        "source_prompt": "폭 900mm 깊이 600mm 높이 1200mm 프레임 장비",
        "dimensions": {"width_mm": 900, "depth_mm": 600, "height_mm": 1200},
        "components": [],
    }

    plan = plan_generation(state, "auto", "standard", "blender", True)

    assert plan["primary_route"] == "openscad"
    assert "blender" in plan["postprocess"]
    assert plan["confidence"] == 1.0
