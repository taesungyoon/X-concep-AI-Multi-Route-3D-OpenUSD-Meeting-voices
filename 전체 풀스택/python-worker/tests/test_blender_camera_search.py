from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest
import trimesh

from app.blender_engine import CAMERA_SEARCH_POSES, _normalize_exported_glb_axes, _write_blender_script


def test_camera_search_pose_contract_is_bounded_and_unique():
    ids = [item["id"] for item in CAMERA_SEARCH_POSES]

    assert len(ids) == 12
    assert len(set(ids)) == len(ids)
    assert any(item["azimuth_deg"] == -90.0 for item in CAMERA_SEARCH_POSES)
    assert any(item["id"] == "legacy_pose" for item in CAMERA_SEARCH_POSES)
    assert all(-90.0 <= item["azimuth_deg"] <= -30.0 for item in CAMERA_SEARCH_POSES)
    assert all(0.4 <= item["elevation"] <= 1.0 for item in CAMERA_SEARCH_POSES)
    assert all(45.0 <= item["lens_mm"] <= 75.0 for item in CAMERA_SEARCH_POSES)


def test_generated_blender_script_contains_compilable_local_pose_search(tmp_path: Path):
    source = tmp_path / "source.glb"
    source.write_bytes(b"glTF")
    reference = tmp_path / "reference.png"
    Image.new("RGB", (64, 64), "white").save(reference)
    script_path = tmp_path / "blender_scene.py"
    report_path = tmp_path / "camera_search_report.json"
    output_glb = tmp_path / "model.glb"
    output_png = tmp_path / "render.png"
    output_usd = tmp_path / "model.usdc"

    _write_blender_script(
        script_path,
        [source],
        reference,
        output_glb,
        output_png,
        output_usd,
        report_path,
        "final",
        [1.6, 1.0, 1.8],
    )

    generated = script_path.read_text(encoding="utf-8")
    compile(generated, str(script_path), "exec")
    assert '"schema": "xconcep.camera-pose-search/1.0"' in generated
    assert "'enabled': True" in generated
    # The generated Python embeds paths through repr(), so Windows backslashes
    # are escaped while POSIX paths remain unchanged.
    assert repr(str(report_path))[1:-1] in generated
    assert all(item["id"] in generated for item in CAMERA_SEARCH_POSES)
    assert '"rotation_x_deg":-90.0' in generated
    assert "rotated_error+1e-6<direct_error" in generated


def test_exported_glb_axis_normalization_bakes_expected_z_up_extents(tmp_path: Path):
    output = tmp_path / "swapped.glb"
    scene = trimesh.Scene(trimesh.creation.box(extents=(1.6, 1.8, 1.0)))
    output.write_bytes(scene.export(file_type="glb"))

    report = _normalize_exported_glb_axes(output, [1.6, 1.0, 1.8])

    assert report["applied"] is True
    assert trimesh.load(output, force="scene").extents == pytest.approx([1.6, 1.0, 1.8])
