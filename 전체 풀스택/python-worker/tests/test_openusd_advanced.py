from __future__ import annotations

import numpy as np
import pytest
import trimesh
from pxr import Usd, UsdGeom

from app.openusd_exporter import OpenUSDExportError, export_openusd


def _source_glb(path):
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(extents=(1, 1, 1)), node_name="Box")
    path.write_bytes(scene.export(file_type="glb"))


def _source_usd(path):
    stage = Usd.Stage.CreateNew(str(path))
    root = UsdGeom.Xform.Define(stage, "/Asset")
    stage.SetDefaultPrim(root.GetPrim())
    UsdGeom.Cube.Define(stage, "/Asset/Cube")
    stage.GetRootLayer().Save()


@pytest.mark.parametrize("arc,token", [("reference", "prepend references"), ("payload", "prepend payload")])
def test_layered_export_supports_reference_and_payload(tmp_path, arc, token):
    glb = tmp_path / "source.glb"
    source = tmp_path / "source.usda"
    _source_glb(glb)
    _source_usd(source)
    result = export_openusd(
        glb, tmp_path / arc, {"project_id": arc}, generate_layers=True,
        source_usd_path=source, composition_arc=arc,
    )
    root_path = result["layers"]["root"]
    assert token in open(root_path, encoding="utf-8").read()
    stage = Usd.Stage.Open(root_path)
    assert stage
    assert any(prim.IsA(UsdGeom.Cube) for prim in stage.Traverse())


def test_layered_export_rejects_unknown_composition_arc(tmp_path):
    glb = tmp_path / "source.glb"
    _source_glb(glb)
    with pytest.raises(OpenUSDExportError, match="composition_arc"):
        export_openusd(glb, tmp_path / "bad", {}, composition_arc="inherit")


def test_layered_export_preserves_parametric_assembly_hierarchy(tmp_path):
    glb = tmp_path / "source.glb"
    _source_glb(glb)
    contract = {
        "generator_mode": "openscad_equipment",
        "generator_version": "1.0.0",
        "contract_sha256": "abc123",
        "relationships": [{"subject": "camera", "relation": "above", "object": "conveyor"}],
        "components": [
            {
                "id": "conveyor_1",
                "kind": "conveyor",
                "requirement_id": "conveyor",
                "center_mm": [0, 0, 700],
                "size_mm": [1000, 500, 200],
            },
            {
                "id": "camera_1",
                "kind": "vision_camera",
                "requirement_id": "vision_camera",
                "center_mm": [0, 0, 1300],
                "size_mm": [160, 120, 100],
            },
        ],
    }
    result = export_openusd(
        glb,
        tmp_path / "assembly",
        {"project_id": "assembly", "geometry_contract": contract},
        generate_layers=True,
    )

    assert "assembly" in result["layers"]
    assembly_text = open(result["layers"]["assembly"], encoding="utf-8").read()
    assert 'def Xform "Assembly"' in assembly_text
    assert assembly_text.count("xconcep:requirementId") == 2
    stage = Usd.Stage.Open(result["layers"]["root"])
    assert stage.GetPrimAtPath("/World/Asset/Assembly/conveyor_1").IsValid()
    camera = stage.GetPrimAtPath("/World/Asset/Assembly/camera_1")
    assert camera.GetAttribute("xconcep:bboxCenterM").Get() == pytest.approx((0.0, 0.0, 1.3))
