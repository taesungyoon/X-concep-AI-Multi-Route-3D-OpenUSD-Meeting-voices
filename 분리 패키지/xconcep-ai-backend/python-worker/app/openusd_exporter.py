from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import trimesh


class OpenUSDExportError(RuntimeError):
    pass


def export_openusd(
    glb_path: Path,
    output_dir: Path,
    metadata: dict[str, Any],
    generate_usdc: bool = True,
    meeting_analysis: dict[str, Any] | None = None,
    revision: int = 1,
    enable_physics: bool = True,
    enable_variants: bool = True,
    generate_layers: bool = True,
    source_usd_path: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scene = trimesh.load(glb_path, force="scene")
    if isinstance(scene, trimesh.Trimesh):
        wrapper = trimesh.Scene()
        wrapper.add_geometry(scene, node_name="Mesh_0", geom_name="Mesh_0")
        scene = wrapper

    usda_path = output_dir / "model.usda"
    _write_usda(scene, usda_path, metadata, meeting_analysis, revision, enable_physics, enable_variants)

    usdc_path: Path | None = None
    if generate_usdc:
        try:
            usdc_path = output_dir / "model.usdc"
            _write_usdc(scene, usdc_path, metadata, meeting_analysis, revision, enable_physics, enable_variants)
        except Exception:
            usdc_path = None

    layers: dict[str, str] = {}
    manifest_path: Path | None = None
    if generate_layers:
        layers, manifest_path = _write_layered_package(
            scene=scene,
            output_dir=output_dir / "openusd",
            metadata=metadata,
            meeting_analysis=meeting_analysis,
            revision=revision,
            enable_physics=enable_physics,
            enable_variants=enable_variants,
            source_usd_path=source_usd_path,
        )
    return {
        "usda": str(usda_path),
        "usdc": str(usdc_path) if usdc_path else None,
        "layers": layers,
        "manifest": str(manifest_path) if manifest_path else None,
    }


def validate_usda(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    result: dict[str, Any] = {
        "valid_header": text.startswith("#usda 1.0"),
        "default_prim": 'defaultPrim = "World"' in text,
        "up_axis_z": 'upAxis = "Z"' in text,
        "meters_per_unit": "metersPerUnit = 1" in text,
        "mesh_count": text.count('def Mesh "'),
        "physics_enabled": "PhysicsCollisionAPI" in text or "PhysicsScene" in text,
        "variant_enabled": "variantSet" in text or "variantSets" in text,
        "meeting_metadata": "xconcep_meetingSummary" in text,
        "size_bytes": path.stat().st_size,
        "parser_available": False,
        "parser_valid": None,
        "parser_error": None,
    }
    try:
        from pxr import Usd  # type: ignore
        result["parser_available"] = True
        stage = Usd.Stage.Open(str(path))
        result["parser_valid"] = bool(stage)
        if stage:
            result["default_prim_path"] = str(stage.GetDefaultPrim().GetPath())
            prims = list(stage.Traverse())
            result["traversed_prim_count"] = len(prims)
            result["stage_mesh_count"] = sum(1 for prim in prims if prim.GetTypeName() == "Mesh")
    except ImportError:
        pass
    except Exception as exc:
        result["parser_valid"] = False
        result["parser_error"] = str(exc)
    result["valid"] = all([
        result["valid_header"], result["default_prim"], result["up_axis_z"],
        result["meters_per_unit"],
        (result.get("stage_mesh_count", 0) > 0 if result["parser_available"] else result["mesh_count"] > 0),
        result["parser_valid"] is not False,
    ])
    return result


def _write_layered_package(
    scene: trimesh.Scene,
    output_dir: Path,
    metadata: dict[str, Any],
    meeting_analysis: dict[str, Any] | None,
    revision: int,
    enable_physics: bool,
    enable_variants: bool,
    source_usd_path: Path | None = None,
) -> tuple[dict[str, str], Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    revisions_dir = output_dir / "revisions"
    revisions_dir.mkdir(parents=True, exist_ok=True)

    geometry = output_dir / "geometry.usda"
    looks = output_dir / "looks.usda"
    render_asset = output_dir / "render_asset.usdc"
    meeting = output_dir / "meeting.usda"
    revision_layer = revisions_dir / f"rev_{revision:03d}.usda"
    root = output_dir / "root.usda"

    use_render_asset = bool(source_usd_path and source_usd_path.exists())
    if use_render_asset:
        import shutil
        shutil.copy2(source_usd_path, render_asset)
    else:
        _write_geometry_layer(scene, geometry, enable_physics)
        _write_looks_layer(scene, looks)
    _write_meeting_layer(meeting, metadata, meeting_analysis, revision)
    _write_revision_layer(revision_layer, meeting_analysis, revision)

    asset_decl = ['    def Xform "Asset"']
    if use_render_asset:
        asset_decl.extend([
            "    (",
            "        prepend references = @./render_asset.usdc@",
            "    )",
        ])
    elif enable_variants:
        asset_decl.extend([
            "    (",
            '        prepend variantSets = "designOption"',
            "        variants = {",
            '            string designOption = "Selected"',
            "        }",
            "    )",
        ])
    asset_decl.append("    {")
    if enable_variants and not use_render_asset:
        asset_decl.extend([
            '        variantSet "designOption" = {',
            '            "Selected" { }',
            '            "MeetingRevision" { }',
            "        }",
        ])
    asset_decl.append("    }")
    sublayers = []
    if not use_render_asset:
        sublayers.extend(["        @./geometry.usda@,", "        @./looks.usda@,"])
    sublayers.extend(["        @./meeting.usda@,", f"        @./revisions/rev_{revision:03d}.usda@"] )
    root.write_text(
        "\n".join([
            "#usda 1.0",
            "(",
            '    defaultPrim = "World"',
            "    metersPerUnit = 1",
            '    upAxis = "Z"',
            "    subLayers = [",
            *sublayers,
            "    ]",
            ")",
            "",
            'def Xform "World"',
            "{",
            *asset_decl,
            "}",
            "",
        ]),
        encoding="utf-8",
    )

    manifest = {
        "schema": "xconcep.openusd.package/1.0",
        "project_id": metadata.get("project_id"),
        "revision": revision,
        "default_stage": "root.usda",
        "layers": {
            **({"render_asset": "render_asset.usdc"} if use_render_asset else {"geometry": "geometry.usda", "looks": "looks.usda"}),
            "meeting": "meeting.usda",
            "revision": f"revisions/rev_{revision:03d}.usda",
        },
        "capabilities": {
            "nucleus_publish": True,
            "live_collaboration": True,
            "kit_webrtc_streaming": True,
            "asset_validation": True,
            "physx_ready": enable_physics,
            "variants": enable_variants,
        },
        "metadata": metadata,
        "meeting_analysis": meeting_analysis or {},
        "render_asset_source": "blender_usd" if use_render_asset else "direct_mesh_fallback",
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    layer_paths = {
        "root": str(root),
        "meeting": str(meeting),
        "revision": str(revision_layer),
    }
    if use_render_asset:
        layer_paths["render_asset"] = str(render_asset)
    else:
        layer_paths["geometry"] = str(geometry)
        layer_paths["looks"] = str(looks)
    return layer_paths, manifest_path


def _write_geometry_layer(scene: trimesh.Scene, path: Path, enable_physics: bool) -> None:
    lines = [
        "#usda 1.0",
        "(",
        '    defaultPrim = "World"',
        "    metersPerUnit = 1",
        '    upAxis = "Z"',
        ")",
        "",
        'def Xform "World"',
        "{",
    ]
    if enable_physics:
        lines.extend([
            '    def PhysicsScene "PhysicsScene"',
            "    {",
            "        vector3f physics:gravityDirection = (0, 0, -1)",
            "        float physics:gravityMagnitude = 9.81",
            "    }",
        ])
    lines.extend(['    def Xform "Asset"', "    {"])
    used: set[str] = set()
    for mesh_index, (node_name, mesh) in enumerate(_flatten_scene(scene), start=1):
        name = _identifier(str(node_name or f"Mesh_{mesh_index}"), used)
        points = ",\n                    ".join(_vec3(v) for v in np.asarray(mesh.vertices, dtype=float))
        counts = ", ".join("3" for _ in mesh.faces)
        indices = ", ".join(str(int(index)) for index in np.asarray(mesh.faces).reshape(-1))
        extent = np.asarray(mesh.bounds, dtype=float)
        api = ' (\n            prepend apiSchemas = ["PhysicsCollisionAPI"]\n        )' if enable_physics else ""
        lines.extend([
            f'        def Mesh "{name}"{api}',
            "        {",
            f"            point3f[] points = [{points}]",
            f"            int[] faceVertexCounts = [{counts}]",
            f"            int[] faceVertexIndices = [{indices}]",
            f"            float3[] extent = [{_vec3(extent[0])}, {_vec3(extent[1])}]",
            '            uniform token subdivisionScheme = "none"',
            f'            custom string xconcep:semanticLabel = "{_escape(name)}"',
            "        }",
        ])
    lines.extend(["    }", "}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_looks_layer(scene: trimesh.Scene, path: Path) -> None:
    lines = ["#usda 1.0", "", 'over Xform "World"', "{", '    over Xform "Asset"', "    {"]
    used: set[str] = set()
    for mesh_index, (node_name, mesh) in enumerate(_flatten_scene(scene), start=1):
        name = _identifier(str(node_name or f"Mesh_{mesh_index}"), used)
        color = _display_color(mesh)
        lines.extend([
            f'        over "{name}"',
            "        {",
            f"            color3f[] primvars:displayColor = [{_vec3(color)}] (",
            '                interpolation = "constant"',
            "            )",
            "        }",
        ])
    lines.extend(["    }", "}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_meeting_layer(path: Path, metadata: dict[str, Any], meeting_analysis: dict[str, Any] | None, revision: int) -> None:
    analysis = meeting_analysis or {}
    lines = [
        "#usda 1.0",
        "",
        'over Xform "World"',
        "{",
        f'    custom string xconcep_projectId = "{_escape(str(metadata.get("project_id", "")))}"',
        f'    custom string xconcep_category = "{_escape(str(metadata.get("category", "")))}"',
        f'    custom string xconcep_selectedConcept = "{_escape(str(metadata.get("selected_concept_id", "")))}"',
        f"    custom int xconcep_revision = {revision}",
        f'    custom string xconcep_meetingSummary = "{_escape(str(analysis.get("summary", "")))}"',
        f'    custom string xconcep_revisionNote = "{_escape(str(analysis.get("revision_note", "")))}"',
        f'    custom string xconcep_pipeline = "ComfyUI/OpenAI Images + Gemma local vLLM/Ray + TripoSR/OpenSCAD/Blender + Omniverse OpenUSD"',
        "}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_revision_layer(path: Path, meeting_analysis: dict[str, Any] | None, revision: int) -> None:
    analysis = meeting_analysis or {}
    changes = analysis.get("requested_changes") or []
    lines = [
        "#usda 1.0",
        "",
        'over Xform "World"',
        "{",
        f"    custom int xconcep_activeRevision = {revision}",
        f'    custom string xconcep_revisionJson = "{_escape(json.dumps(changes, ensure_ascii=False))}"',
        "}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_usda(
    scene: trimesh.Scene,
    path: Path,
    metadata: dict[str, Any],
    meeting_analysis: dict[str, Any] | None,
    revision: int,
    enable_physics: bool,
    enable_variants: bool,
) -> None:
    analysis = meeting_analysis or {}
    lines = [
        "#usda 1.0",
        "(",
        '    defaultPrim = "World"',
        "    metersPerUnit = 1",
        '    upAxis = "Z"',
        ")",
        "",
        'def Xform "World"',
        "{",
        '    custom string xconcep_projectId = "' + _escape(str(metadata.get("project_id", ""))) + '"',
        '    custom string xconcep_category = "' + _escape(str(metadata.get("category", ""))) + '"',
        '    custom string xconcep_selectedConcept = "' + _escape(str(metadata.get("selected_concept_id", ""))) + '"',
        f"    custom int xconcep_revision = {revision}",
        '    custom string xconcep_meetingSummary = "' + _escape(str(analysis.get("summary", ""))) + '"',
        '    custom string xconcep_pipeline = "ComfyUI/OpenAI Images + Gemma local + TripoSR/OpenSCAD/Blender + Omniverse"',
    ]
    if enable_physics:
        lines.extend([
            '    def PhysicsScene "PhysicsScene"',
            "    {",
            "        vector3f physics:gravityDirection = (0, 0, -1)",
            "        float physics:gravityMagnitude = 9.81",
            "    }",
        ])
    lines.append('    def Xform "Asset"')
    if enable_variants:
        lines.extend([
            "    (",
            '        prepend variantSets = "designOption"',
            "        variants = {",
            '            string designOption = "Selected"',
            "        }",
            "    )",
        ])
    lines.append("    {")
    if enable_variants:
        lines.extend([
            '        variantSet "designOption" = {',
            '            "Selected" { }',
            '            "MeetingRevision" { }',
            "        }",
        ])
    used: set[str] = set()
    for mesh_index, (node_name, mesh) in enumerate(_flatten_scene(scene), start=1):
        name = _identifier(str(node_name or f"Mesh_{mesh_index}"), used)
        points = ",\n                    ".join(_vec3(v) for v in np.asarray(mesh.vertices, dtype=float))
        counts = ", ".join("3" for _ in mesh.faces)
        indices = ", ".join(str(int(index)) for index in np.asarray(mesh.faces).reshape(-1))
        extent = np.asarray(mesh.bounds, dtype=float)
        display = _display_color(mesh)
        api = ' (\n            prepend apiSchemas = ["PhysicsCollisionAPI"]\n        )' if enable_physics else ""
        lines.extend([
            f'        def Mesh "{name}"{api}',
            "        {",
            f"            point3f[] points = [{points}]",
            f"            int[] faceVertexCounts = [{counts}]",
            f"            int[] faceVertexIndices = [{indices}]",
            f"            float3[] extent = [{_vec3(extent[0])}, {_vec3(extent[1])}]",
            f"            color3f[] primvars:displayColor = [{_vec3(display)}] (",
            '                interpolation = "constant"',
            "            )",
            '            uniform token subdivisionScheme = "none"',
            f'            custom string xconcep:semanticLabel = "{_escape(name)}"',
            "        }",
        ])
    lines.extend(["    }", "}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_usdc(
    scene: trimesh.Scene,
    path: Path,
    metadata: dict[str, Any],
    meeting_analysis: dict[str, Any] | None,
    revision: int,
    enable_physics: bool,
    enable_variants: bool,
) -> None:
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics  # type: ignore

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    asset = UsdGeom.Xform.Define(stage, "/World/Asset")
    world_prim = world.GetPrim()
    analysis = meeting_analysis or {}
    attrs = {
        "xconcep:projectId": metadata.get("project_id", ""),
        "xconcep:category": metadata.get("category", ""),
        "xconcep:selectedConcept": metadata.get("selected_concept_id", ""),
        "xconcep:meetingSummary": analysis.get("summary", ""),
        "xconcep:pipeline": "ComfyUI/OpenAI Images + Gemma local + TripoSR/OpenSCAD/Blender + Omniverse",
    }
    for key, value in attrs.items():
        world_prim.CreateAttribute(key, Sdf.ValueTypeNames.String, custom=True).Set(str(value))
    world_prim.CreateAttribute("xconcep:revision", Sdf.ValueTypeNames.Int, custom=True).Set(int(revision))
    if enable_physics:
        physics = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
        physics.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
        physics.CreateGravityMagnitudeAttr(9.81)
    if enable_variants:
        variants = asset.GetPrim().GetVariantSets().AddVariantSet("designOption")
        for name in ("Selected", "MeetingRevision"):
            variants.AddVariant(name)
        variants.SetVariantSelection("Selected")

    used: set[str] = set()
    for mesh_index, (node_name, mesh) in enumerate(_flatten_scene(scene), start=1):
        name = _identifier(str(node_name or f"Mesh_{mesh_index}"), used)
        usd_mesh = UsdGeom.Mesh.Define(stage, f"/World/Asset/{name}")
        usd_mesh.CreatePointsAttr([Gf.Vec3f(*map(float, v)) for v in mesh.vertices])
        usd_mesh.CreateFaceVertexCountsAttr([3] * len(mesh.faces))
        usd_mesh.CreateFaceVertexIndicesAttr([int(i) for i in np.asarray(mesh.faces).reshape(-1)])
        usd_mesh.CreateSubdivisionSchemeAttr("none")
        color = _display_color(mesh)
        usd_mesh.CreateDisplayColorAttr([Gf.Vec3f(*map(float, color))])
        usd_mesh.GetPrim().CreateAttribute("xconcep:semanticLabel", Sdf.ValueTypeNames.String, custom=True).Set(name)
        if enable_physics:
            UsdPhysics.CollisionAPI.Apply(usd_mesh.GetPrim())
    stage.GetRootLayer().Save()


def _flatten_scene(scene: trimesh.Scene):
    if isinstance(scene, trimesh.Trimesh):
        yield "Mesh_0", scene
        return
    for node_name in scene.graph.nodes_geometry:
        transform, geometry_name = scene.graph.get(node_name)
        source = scene.geometry[geometry_name]
        mesh = source.copy()
        mesh.apply_transform(transform)
        if isinstance(mesh, trimesh.Trimesh) and len(mesh.vertices) and len(mesh.faces):
            yield node_name or geometry_name, mesh


def _display_color(mesh: trimesh.Trimesh) -> tuple[float, float, float]:
    try:
        colors = np.asarray(mesh.visual.face_colors, dtype=float)
        if colors.size:
            rgb = colors[:, :3].mean(axis=0) / 255.0
            return float(rgb[0]), float(rgb[1]), float(rgb[2])
    except Exception:
        pass
    return 0.55, 0.65, 0.72


def _identifier(value: str, used: set[str]) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not value or value[0].isdigit():
        value = "Mesh_" + value
    base = value
    suffix = 2
    while value in used:
        value = f"{base}_{suffix}"
        suffix += 1
    used.add(value)
    return value


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _vec3(value: Any) -> str:
    x, y, z = [float(v) for v in value]
    return f"({x:.7g}, {y:.7g}, {z:.7g})"
