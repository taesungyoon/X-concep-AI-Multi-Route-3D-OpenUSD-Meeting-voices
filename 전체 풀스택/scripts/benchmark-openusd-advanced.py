from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade


STACK_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = STACK_ROOT / "python-worker"
sys.path.insert(0, str(WORKER_ROOT))

from app.openusd_exporter import export_openusd  # noqa: E402
from app.settings import get_settings  # noqa: E402


def _write_source_glb(path: Path) -> None:
    scene = trimesh.Scene()
    mesh = trimesh.creation.box(extents=(1.2, 0.8, 0.5))
    mesh.visual.face_colors = np.tile(np.array([48, 112, 190, 255], dtype=np.uint8), (len(mesh.faces), 1))
    scene.add_geometry(mesh, node_name="Body", geom_name="Body")
    path.write_bytes(scene.export(file_type="glb"))


def _write_blender_roundtrip_script(path: Path, usd_path: Path, texture_path: Path, result_path: Path) -> None:
    script = f'''import bpy, json
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=2, location=(0,0,0))
source=bpy.context.object
source.name="TexturedCube"
mat=bpy.data.materials.new("RoundtripMaterial")
mat.use_nodes=True
nodes=mat.node_tree.nodes
links=mat.node_tree.links
bsdf=nodes.get("Principled BSDF")
tex=nodes.new("ShaderNodeTexImage")
tex.image=bpy.data.images.load({str(texture_path)!r})
links.new(tex.outputs["Color"],bsdf.inputs["Base Color"])
source.data.materials.append(mat)
before=[round(v,6) for v in source.dimensions]
try:
    bpy.ops.wm.usd_export(filepath={str(usd_path)!r},export_materials=True,export_textures=True,selected_objects_only=False)
except TypeError:
    bpy.ops.wm.usd_export(filepath={str(usd_path)!r},export_materials=True,selected_objects_only=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.usd_import(filepath={str(usd_path)!r})
meshes=[obj for obj in bpy.context.scene.objects if obj.type=="MESH"]
after=[round(v,6) for v in meshes[0].dimensions] if meshes else []
payload={{"mesh_count":len(meshes),"material_count":len(bpy.data.materials),"image_count":len(bpy.data.images),"before_size":before,"after_size":after}}
open({str(result_path)!r},"w",encoding="utf-8").write(json.dumps(payload,ensure_ascii=False,indent=2))
'''
    path.write_text(script, encoding="utf-8")


def _blender_roundtrip(root: Path, blender_bin: str) -> dict[str, Any]:
    texture = root / "checker.png"
    image = Image.new("RGB", (4, 4), (220, 50, 40))
    for x in range(2):
        for y in range(2):
            image.putpixel((x, y), (40, 130, 220))
    image.save(texture)
    usd_path = root / "blender_roundtrip.usdc"
    result_path = root / "blender_roundtrip.json"
    script_path = root / "blender_roundtrip.py"
    _write_blender_roundtrip_script(script_path, usd_path, texture, result_path)
    completed = subprocess.run(
        [blender_bin, "--background", "--python", str(script_path)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300, check=False,
    )
    if completed.returncode != 0 or not result_path.is_file() or not usd_path.is_file():
        raise RuntimeError((completed.stderr or completed.stdout)[-3000:])
    blender = json.loads(result_path.read_text(encoding="utf-8"))
    stage = Usd.Stage.Open(str(usd_path))
    if not stage:
        raise RuntimeError("Blender USD stage did not reopen with OpenUSD")
    prims = list(stage.Traverse())
    bound_materials = 0
    texture_assets = []
    for prim in prims:
        if prim.IsA(UsdGeom.Mesh):
            material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            bound_materials += int(bool(material))
        for attribute in prim.GetAttributes():
            value = attribute.Get()
            if isinstance(value, Sdf.AssetPath) and value.path:
                texture_assets.append(value.path)
    return {
        "path": str(usd_path),
        "blender": blender,
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "mesh_count": sum(prim.IsA(UsdGeom.Mesh) for prim in prims),
        "bound_material_count": bound_materials,
        "texture_assets": texture_assets,
        "passed": (
            blender["mesh_count"] >= 1 and blender["material_count"] >= 1
            and blender["before_size"] == blender["after_size"]
            and bound_materials >= 1 and bool(texture_assets)
        ),
    }


def _composition_check(glb: Path, root: Path, source_usd: Path, arc: str) -> dict[str, Any]:
    result = export_openusd(
        glb, root / arc, {"project_id": f"usd-{arc}", "category": "benchmark"},
        generate_usdc=True, generate_layers=True, enable_physics=True, enable_variants=True,
        source_usd_path=source_usd, composition_arc=arc,
    )
    stage_path = Path(result["layers"]["root"])
    stage = Usd.Stage.Open(str(stage_path))
    if not stage:
        raise RuntimeError(f"Unable to open {arc} stage")
    asset = stage.GetPrimAtPath("/World/Asset")
    authored = asset.HasAuthoredReferences() if arc == "reference" else asset.HasAuthoredPayloads()
    return {
        "path": str(stage_path),
        "authored_arc": bool(authored),
        "sublayer_count": len(stage.GetRootLayer().subLayerPaths),
        "mesh_count": sum(prim.IsA(UsdGeom.Mesh) for prim in stage.Traverse()),
        "passed": bool(authored) and len(stage.GetRootLayer().subLayerPaths) >= 2 and any(prim.IsA(UsdGeom.Mesh) for prim in stage.Traverse()),
    }


def _variant_check(glb: Path, root: Path) -> dict[str, Any]:
    result = export_openusd(
        glb, root / "direct", {"project_id": "usd-variant", "category": "benchmark"},
        generate_usdc=True, generate_layers=True, enable_physics=True, enable_variants=True,
    )
    stage = Usd.Stage.Open(result["layers"]["root"])
    asset = stage.GetPrimAtPath("/World/Asset")
    variants = asset.GetVariantSets().GetVariantSet("designOption")
    names = variants.GetVariantNames()
    return {
        "path": result["layers"]["root"], "variant_names": names,
        "selection": variants.GetVariantSelection(), "sublayer_count": len(stage.GetRootLayer().subLayerPaths),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)), "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "passed": set(names) == {"MeetingRevision", "Selected"} and variants.GetVariantSelection() == "Selected",
    }


def _layer_conflict(root: Path) -> dict[str, Any]:
    weak = Sdf.Layer.CreateNew(str(root / "weak.usda"))
    weak_stage = Usd.Stage.Open(weak)
    weak_prim = weak_stage.DefinePrim("/World", "Xform")
    weak_prim.CreateAttribute("xconcep:decision", Sdf.ValueTypeNames.String).Set("weak")
    weak.Save()
    strong = Sdf.Layer.CreateNew(str(root / "strong.usda"))
    strong_stage = Usd.Stage.Open(strong)
    strong_prim = strong_stage.DefinePrim("/World", "Xform")
    strong_prim.CreateAttribute("xconcep:decision", Sdf.ValueTypeNames.String).Set("strong")
    strong.Save()
    composed = Sdf.Layer.CreateNew(str(root / "conflict_root.usda"))
    composed.subLayerPaths = ["./strong.usda", "./weak.usda"]
    composed.Save()
    stage = Usd.Stage.Open(composed)
    resolved = stage.GetPrimAtPath("/World").GetAttribute("xconcep:decision").Get()
    return {"path": str(composed.realPath), "resolved": resolved, "passed": resolved == "strong"}


def _instancing(root: Path) -> dict[str, Any]:
    path = root / "instances.usda"
    stage = Usd.Stage.CreateNew(str(path))
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    prototype = UsdGeom.Cube.Define(stage, "/World/Prototypes/Cube").GetPrim()
    for index, x in enumerate((-1.5, 1.5)):
        instance = UsdGeom.Xform.Define(stage, f"/World/Instance_{index}").GetPrim()
        instance.GetReferences().AddInternalReference(prototype.GetPath())
        instance.SetInstanceable(True)
        UsdGeom.Xformable(instance).AddTranslateOp().Set(Gf.Vec3d(x, 0, 0))
    stage.GetRootLayer().Save()
    reopened = Usd.Stage.Open(str(path))
    instances = [prim for prim in reopened.Traverse() if prim.IsInstance()]
    return {"path": str(path), "instance_count": len(instances), "passed": len(instances) == 2}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate advanced OpenUSD composition and Blender round-trip contracts")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "benchmarks" / "openusd-advanced")
    parser.add_argument("--blender-bin", default=get_settings().blender_bin)
    args = parser.parse_args()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = args.output.resolve() / run_id
    root.mkdir(parents=True, exist_ok=False)
    glb = root / "source.glb"
    _write_source_glb(glb)
    started = time.perf_counter()
    checks: dict[str, Any] = {}
    for name, action in (
        ("blender_roundtrip", lambda: _blender_roundtrip(root, args.blender_bin)),
        ("variant_sublayer_units", lambda: _variant_check(glb, root)),
        ("layer_conflict", lambda: _layer_conflict(root)),
        ("instancing", lambda: _instancing(root)),
    ):
        try:
            checks[name] = action()
        except Exception as exc:
            checks[name] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
    source_usd = Path(checks.get("blender_roundtrip", {}).get("path", root / "missing.usdc"))
    for arc in ("reference", "payload"):
        try:
            checks[arc] = _composition_check(glb, root, source_usd, arc)
        except Exception as exc:
            checks[arc] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "blender_bin": str(Path(args.blender_bin).resolve()), "passed": all(check["passed"] for check in checks.values()),
        "duration_seconds": round(time.perf_counter() - started, 3), "checks": checks,
    }
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Advanced OpenUSD Benchmark", "", f"- Result: **{'PASS' if report['passed'] else 'FAIL'}**", "", "| Check | Result |", "|---|---:|"]
    lines.extend(f"| {name} | {'PASS' if check['passed'] else 'FAIL'} |" for name, check in checks.items())
    (root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": {name: check["passed"] for name, check in checks.items()}}, ensure_ascii=False))
    print(f"Report: {root / 'report.md'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
