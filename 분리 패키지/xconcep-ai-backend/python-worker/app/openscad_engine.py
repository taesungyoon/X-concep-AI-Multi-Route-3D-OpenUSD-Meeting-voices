from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .generator import Part, _render_isometric


@dataclass
class OpenSCADResult:
    glb_path: Path
    stl_path: Path
    scad_path: Path
    preview_path: Path
    manifest_path: Path
    geometry_json_path: Path
    provider: dict[str, Any]


def _safe_dim(value: Any, default: float) -> float:
    try:
        number = float(value)
        return number if number > 0 else default
    except (TypeError, ValueError):
        return default


def _dimensions(design_state: dict[str, Any], category: str) -> tuple[float, float, float]:
    dims = design_state.get("dimensions", {})
    if category == "equipment":
        defaults = (1600.0, 1000.0, 1800.0)
    elif category == "module":
        defaults = (800.0, 600.0, 900.0)
    else:
        defaults = (240.0, 160.0, 120.0)
    width = _safe_dim(dims.get("width_mm") or dims.get("length_mm"), defaults[0])
    depth = _safe_dim(dims.get("depth_mm"), defaults[1])
    height = _safe_dim(dims.get("height_mm"), defaults[2])
    return width, depth, height


def _geometry_contract(design_state: dict[str, Any], category: str) -> dict[str, Any]:
    width, depth, height = _dimensions(design_state, category)
    thickness = max(8.0, min(width, depth) * 0.025)
    components = design_state.get("components", [])
    return {
        "schema_version": "1.0",
        "units": "mm",
        "overall": {"width": width, "depth": depth, "height": height},
        "parameters": {
            "plate_thickness": thickness,
            "frame_profile": max(20.0, min(width, depth) * 0.035),
            "hole_diameter": max(4.0, min(width, depth) * 0.012),
        },
        "components": components,
        "features": ["base", "supports", "work_unit", "mounting_holes"],
    }


def _write_scad(path: Path, contract: dict[str, Any], category: str) -> None:
    overall = contract["overall"]
    params = contract["parameters"]
    width, depth, height = overall["width"], overall["depth"], overall["height"]
    t, profile, hole = params["plate_thickness"], params["frame_profile"], params["hole_diameter"]
    if category == "part":
        body = f"""
$fn=64;
W={width}; D={depth}; H={height}; T={t}; HD={hole};
difference() {{
  union() {{
    cube([W,D,T], center=true);
    translate([0,0,H/2]) cube([T,D,H], center=true);
    translate([-W*0.25,0,H*0.25]) rotate([0,35,0]) cube([T,D*0.75,H*0.6], center=true);
    translate([ W*0.25,0,H*0.25]) rotate([0,-35,0]) cube([T,D*0.75,H*0.6], center=true);
  }}
  for (x=[-W*0.35,W*0.35], y=[-D*0.3,D*0.3]) translate([x,y,-T]) cylinder(h=T*3,d=HD);
}}
"""
    else:
        base_z = t / 2
        post_z = t + height / 2
        x = width / 2 - profile / 2
        y = depth / 2 - profile / 2
        work_w, work_d, work_h = width * 0.36, depth * 0.42, height * 0.28
        body = f"""
$fn=48;
W={width}; D={depth}; H={height}; T={t}; P={profile}; HD={hole};
module base_plate() {{
  difference() {{
    translate([0,0,T/2]) cube([W,D,T], center=true);
    for (x=[-W*0.42,W*0.42], y=[-D*0.42,D*0.42]) translate([x,y,-T]) cylinder(h=T*3,d=HD);
  }}
}}
module post(x,y) {{ translate([x,y,{post_z}]) cube([P,P,H], center=true); }}
module frame() {{
  base_plate();
  post(-{x},-{y}); post({x},-{y}); post(-{x},{y}); post({x},{y});
  translate([0,-{y},H+T]) cube([W,P,P], center=true);
  translate([0,{y},H+T]) cube([W,P,P], center=true);
  translate([-{x},0,H+T]) cube([P,D,P], center=true);
  translate([{x},0,H+T]) cube([P,D,P], center=true);
}}
module work_unit() {{ translate([0,0,T+H*0.42]) cube([{work_w},{work_d},{work_h}], center=true); }}
module control_box() {{ translate([W*0.42,0,T+H*0.35]) cube([W*0.16,D*0.28,H*0.45], center=true); }}
union() {{ frame(); work_unit(); control_box(); }}
"""
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _parts_from_contract(contract: dict[str, Any], category: str) -> list[Part]:
    w, d, h = contract["overall"]["width"], contract["overall"]["depth"], contract["overall"]["height"]
    scale = 1.0 / 1000.0
    width, depth, height = w * scale, d * scale, h * scale
    profile = contract["parameters"]["frame_profile"] * scale
    plate = contract["parameters"]["plate_thickness"] * scale
    steel = (78, 102, 117, 255)
    blue = (27, 112, 178, 255)
    dark = (20, 42, 55, 255)
    if category == "part":
        return [
            Part("base", (width, depth, plate), (0, 0, plate / 2), steel),
            Part("upright", (plate, depth, height), (0, 0, height / 2 + plate), blue),
            Part("rib_left", (plate, depth * .72, height * .62), (-width * .25, 0, height * .32), dark),
            Part("rib_right", (plate, depth * .72, height * .62), (width * .25, 0, height * .32), dark),
        ]
    x, y = width / 2 - profile / 2, depth / 2 - profile / 2
    parts = [Part("base", (width, depth, plate), (0, 0, plate / 2), steel)]
    for px in (-x, x):
        for py in (-y, y):
            parts.append(Part("post", (profile, profile, height), (px, py, height / 2 + plate), blue))
    parts.extend([
        Part("top_front", (width, profile, profile), (0, -y, height + plate), steel),
        Part("top_back", (width, profile, profile), (0, y, height + plate), steel),
        Part("work_unit", (width * .36, depth * .42, height * .28), (0, 0, height * .42), blue),
        Part("control_box", (width * .16, depth * .28, height * .45), (width * .42, 0, height * .35), steel),
    ])
    return parts


def _export_fallback_mesh(parts: list[Part], glb_path: Path, stl_path: Path) -> None:
    scene = trimesh.Scene()
    meshes: list[trimesh.Trimesh] = []
    for index, part in enumerate(parts):
        mesh = trimesh.creation.box(extents=part.size)
        mesh.apply_translation(part.center)
        mesh.visual.face_colors = np.array(part.color, dtype=np.uint8)
        scene.add_geometry(mesh, node_name=f"{part.name}_{index}", geom_name=f"{part.name}_{index}")
        meshes.append(mesh.copy())
    glb_path.write_bytes(scene.export(file_type="glb"))
    trimesh.util.concatenate(meshes).export(stl_path, file_type="stl")


def _stl_to_glb(stl_path: Path, glb_path: Path) -> None:
    mesh = trimesh.load(stl_path, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        raise RuntimeError("OpenSCAD STL을 메시로 읽지 못함")
    mesh.visual.face_colors = np.array((74, 116, 142, 255), dtype=np.uint8)
    scene = trimesh.Scene(mesh)
    glb_path.write_bytes(scene.export(file_type="glb"))


def generate_openscad(
    *,
    design_state: dict[str, Any],
    category: str,
    output_dir: Path,
    openscad_bin: str,
    timeout_seconds: int,
    mode: str,
) -> OpenSCADResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = _geometry_contract(design_state, category)
    geometry_json_path = output_dir / "geometry.json"
    geometry_json_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    scad_path = output_dir / "model.scad"
    stl_path = output_dir / "model_structural.stl"
    glb_path = output_dir / "model_structural.glb"
    preview_path = output_dir / "render_structural.png"
    manifest_path = output_dir / "assembly_manifest.json"
    _write_scad(scad_path, contract, category)

    binary = shutil.which(openscad_bin)
    provider: dict[str, Any]
    if mode != "mock" and binary:
        command = [binary, "--export-format", "stl", "-o", str(stl_path), str(scad_path)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
        if completed.returncode != 0 or not stl_path.exists():
            provider = {"mode": "fallback", "engine": "openscad", "error": completed.stderr[-1200:]}
            parts = _parts_from_contract(contract, category)
            _export_fallback_mesh(parts, glb_path, stl_path)
        else:
            _stl_to_glb(stl_path, glb_path)
            provider = {"mode": "native", "engine": "openscad", "binary": binary, "command": command}
    else:
        parts = _parts_from_contract(contract, category)
        _export_fallback_mesh(parts, glb_path, stl_path)
        provider = {"mode": "mock" if mode == "mock" else "fallback", "engine": "openscad", "binary_found": bool(binary)}

    parts = _parts_from_contract(contract, category)
    _render_isometric(preview_path, parts, str(design_state.get("purpose") or design_state.get("source_prompt") or ""))
    manifest = {
        "manifest_version": "1.0",
        "engine": "openscad",
        "units": "mm",
        "coordinate_system": design_state.get("coordinate_system"),
        "design_id": design_state.get("design_id"),
        "revision": design_state.get("revision"),
        "overall_dimensions_mm": contract["overall"],
        "parts": [
            {
                "id": f"{part.name}_{index}",
                "name": part.name,
                "size_m": list(part.size),
                "center_m": list(part.center),
                "material_preset": "painted_steel" if part.name != "work_unit" else "industrial_blue",
            }
            for index, part in enumerate(parts)
        ],
        "files": {
            "scad": scad_path.name,
            "stl": stl_path.name,
            "glb": glb_path.name,
            "preview": preview_path.name,
            "geometry_json": geometry_json_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return OpenSCADResult(glb_path, stl_path, scad_path, preview_path, manifest_path, geometry_json_path, provider)
