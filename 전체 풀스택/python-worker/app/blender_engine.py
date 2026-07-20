from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .renderer import create_preview


MATERIAL_PRESETS = {
    "painted_steel": {"base_color": [0.23, 0.30, 0.34, 1.0], "metallic": 0.65, "roughness": 0.28},
    "industrial_blue": {"base_color": [0.03, 0.28, 0.72, 1.0], "metallic": 0.18, "roughness": 0.32},
    "black_abs": {"base_color": [0.015, 0.02, 0.025, 1.0], "metallic": 0.0, "roughness": 0.38},
    "transparent_polycarbonate": {"base_color": [0.2, 0.65, 0.8, 0.24], "metallic": 0.0, "roughness": 0.1},
    "brushed_aluminum": {"base_color": [0.55, 0.58, 0.6, 1.0], "metallic": 0.95, "roughness": 0.22},
}


def _merge_glbs(source_glbs: list[Path], output_path: Path) -> None:
    scene_out = trimesh.Scene()
    node_count = 0
    for source in source_glbs:
        loaded = trimesh.load(source, force="scene")
        if isinstance(loaded, trimesh.Trimesh):
            loaded = trimesh.Scene(loaded)
        if not isinstance(loaded, trimesh.Scene):
            continue
        for node in loaded.graph.nodes_geometry:
            transform, geom_name = loaded.graph.get(node)
            mesh = loaded.geometry[geom_name].copy()
            mesh.apply_transform(transform)
            if not isinstance(mesh, trimesh.Trimesh):
                continue
            if not hasattr(mesh.visual, "face_colors") or len(mesh.visual.face_colors) == 0:
                mesh.visual.face_colors = np.array((82, 118, 137, 255), dtype=np.uint8)
            scene_out.add_geometry(mesh, node_name=f"asset_{node_count}_{node}", geom_name=f"asset_{node_count}_{geom_name}")
            node_count += 1
    if node_count == 0:
        raise RuntimeError("Blender 후처리에 사용할 GLB 메시가 없음")
    output_path.write_bytes(scene_out.export(file_type="glb"))


def _write_blender_script(
    script_path: Path,
    source_glbs: list[Path],
    output_glb: Path,
    output_png: Path,
    output_usd: Path,
    profile: str,
) -> None:
    sources = json.dumps([str(path) for path in source_glbs])
    samples = {"preview": 16, "standard": 64, "final": 256}[profile]
    engine = "BLENDER_EEVEE_NEXT" if profile != "final" else "BLENDER_EEVEE_NEXT"
    script = f'''import bpy, math
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
sources={sources}
for source in sources:
    bpy.ops.import_scene.gltf(filepath=source)
objects=[o for o in bpy.context.scene.objects if o.type=="MESH"]
if not objects: raise RuntimeError("GLB 메시 없음")
for idx,obj in enumerate(objects):
    for poly in obj.data.polygons: poly.use_smooth=True
    if not obj.data.materials:
        mat=bpy.data.materials.new(name=f"XconcepMaterial_{{idx}}")
        mat.use_nodes=True
        bsdf=mat.node_tree.nodes.get("Principled BSDF")
        palette=[(0.04,0.24,0.68,1),(0.025,0.03,0.04,1),(0.42,0.45,0.47,1)]
        bsdf.inputs["Base Color"].default_value=palette[idx%len(palette)]
        bsdf.inputs["Metallic"].default_value=0.35 if idx%3==2 else 0.12
        bsdf.inputs["Roughness"].default_value=0.28 if idx%3==0 else 0.38
        obj.data.materials.append(mat)
mins=Vector((1e9,1e9,1e9)); maxs=Vector((-1e9,-1e9,-1e9))
for obj in objects:
    for corner in obj.bound_box:
        p=obj.matrix_world@Vector(corner)
        mins.x=min(mins.x,p.x); mins.y=min(mins.y,p.y); mins.z=min(mins.z,p.z)
        maxs.x=max(maxs.x,p.x); maxs.y=max(maxs.y,p.y); maxs.z=max(maxs.z,p.z)
center=(mins+maxs)/2; size=max(maxs-mins)
def look_at(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=max(size*5,10), location=(center.x,center.y,mins.z-0.01))
plane=bpy.context.object
mat=bpy.data.materials.new(name="Ground"); mat.use_nodes=True
bsdf=mat.node_tree.nodes.get("Principled BSDF"); bsdf.inputs["Base Color"].default_value=(0.025,0.03,0.035,1); bsdf.inputs["Roughness"].default_value=.42
plane.data.materials.append(mat)
bpy.ops.object.camera_add(location=(center.x+size*2.2,center.y-size*2.2,center.z+size*1.45))
cam=bpy.context.object; bpy.context.scene.camera=cam; look_at(cam,center)
for loc,energy,area,temp in [((3,-4,5),1700,3.5,0),((-3,-1,2.5),900,2.8,0),((0,4,4),1200,2.4,0)]:
    bpy.ops.object.light_add(type='AREA',location=(center.x+loc[0]*size/4,center.y+loc[1]*size/4,center.z+loc[2]*size/4))
    light=bpy.context.object; light.data.energy=energy; light.data.shape='DISK'; light.data.size=max(area*size/4,.2); look_at(light,center)
scene=bpy.context.scene
scene.render.engine='{engine}'
scene.render.resolution_x=1280; scene.render.resolution_y=860; scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'; scene.render.filepath={str(output_png)!r}
scene.world.color=(0.01,0.015,0.025)
scene.render.film_transparent=False
scene.render.image_settings.color_mode='RGBA'
scene.render.engine='{engine}'
bpy.ops.wm.save_as_mainfile(filepath={str(output_glb.with_suffix('.blend'))!r})
bpy.ops.export_scene.gltf(filepath={str(output_glb)!r},export_format='GLB',export_apply=True)
try:
    bpy.ops.wm.usd_export(filepath={str(output_usd)!r},export_materials=True,export_textures=True)
except Exception as exc:
    print("USD_EXPORT_WARNING",exc)
bpy.ops.render.render(write_still=True)
'''
    script_path.write_text(script, encoding="utf-8")


def generate_blender_asset(
    *,
    source_glbs: list[Path],
    selected_image_path: Path,
    output_dir: Path,
    blender_bin: str,
    timeout_seconds: int,
    mode: str,
    profile: str,
    design_state: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_glb = output_dir / "model_high_quality.glb"
    output_png = output_dir / "render_high_quality.png"
    output_usd = output_dir / "model_blender.usdc"
    script_path = output_dir / "blender_scene.py"
    materials_path = output_dir / "material_manifest.json"
    binary = shutil.which(blender_bin)
    provider: dict[str, Any]
    if mode != "mock" and binary:
        _write_blender_script(script_path, source_glbs, output_glb, output_png, output_usd, profile)
        completed = subprocess.run(
            [binary, "--background", "--python", str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0 or not output_glb.exists():
            _merge_glbs(source_glbs, output_glb)
            create_preview(output_glb, selected_image_path, output_png, "")
            provider = {"mode": "fallback", "engine": "blender", "error": completed.stderr[-1600:]}
        else:
            provider = {"mode": "native", "engine": "blender", "binary": binary, "profile": profile}
    else:
        _merge_glbs(source_glbs, output_glb)
        create_preview(output_glb, selected_image_path, output_png, "")
        _write_blender_script(script_path, source_glbs, output_glb, output_png, output_usd, profile)
        provider = {"mode": "mock" if mode == "mock" else "fallback", "engine": "blender", "binary_found": bool(binary), "profile": profile}

    materials_path.write_text(json.dumps({
        "design_id": design_state.get("design_id"),
        "revision": design_state.get("revision"),
        "profile": profile,
        "presets": MATERIAL_PRESETS,
        "visual_direction": design_state.get("visual", {}),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "glb_path": output_glb,
        "preview_path": output_png,
        "usd_path": output_usd if output_usd.exists() else None,
        "blend_path": output_glb.with_suffix(".blend") if output_glb.with_suffix(".blend").exists() else None,
        "script_path": script_path,
        "materials_path": materials_path,
        "provider": provider,
    }
