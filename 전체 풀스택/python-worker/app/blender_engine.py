from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
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
    "hmi_blue": {"base_color": [0.01, 0.24, 0.62, 1.0], "metallic": 0.05, "roughness": 0.16},
    "emergency_red": {"base_color": [0.72, 0.015, 0.025, 1.0], "metallic": 0.08, "roughness": 0.24},
}

CAMERA_SEARCH_POSES = [
    {"id": "front_low", "azimuth_deg": -90.0, "elevation": 0.48, "radius": 3.0, "lens_mm": 58.0},
    {"id": "front_high", "azimuth_deg": -90.0, "elevation": 0.70, "radius": 3.0, "lens_mm": 58.0},
    {"id": "front_right_15_low", "azimuth_deg": -75.0, "elevation": 0.48, "radius": 3.0, "lens_mm": 58.0},
    {"id": "front_right_15_high", "azimuth_deg": -75.0, "elevation": 0.70, "radius": 3.0, "lens_mm": 58.0},
    {"id": "front_right_30_low", "azimuth_deg": -60.0, "elevation": 0.48, "radius": 3.0, "lens_mm": 58.0},
    {"id": "front_right_30_high", "azimuth_deg": -60.0, "elevation": 0.70, "radius": 3.0, "lens_mm": 58.0},
    {"id": "front_right_45_low", "azimuth_deg": -45.0, "elevation": 0.48, "radius": 3.0, "lens_mm": 58.0},
    {"id": "front_right_45_high", "azimuth_deg": -45.0, "elevation": 0.70, "radius": 3.0, "lens_mm": 58.0},
    {"id": "front_right_60", "azimuth_deg": -30.0, "elevation": 0.55, "radius": 3.0, "lens_mm": 58.0},
    {"id": "narrow_perspective", "azimuth_deg": -60.0, "elevation": 0.55, "radius": 3.3, "lens_mm": 70.0},
    {"id": "wide_perspective", "azimuth_deg": -60.0, "elevation": 0.55, "radius": 2.8, "lens_mm": 50.0},
    {"id": "legacy_pose", "azimuth_deg": -45.0, "elevation": 0.92, "radius": 3.3234, "lens_mm": 58.0},
]


def _camera_search_code(config: dict[str, Any]) -> str:
    return r'''
camera_search_config = __CONFIG__
camera_search_report = {
    "schema": "xconcep.camera-pose-search/1.0",
    "enabled": bool(camera_search_config.get("enabled")),
    "method": "local Blender Workbench pose sweep with background-normalized silhouette scoring",
    "coordinate_normalization": coordinate_normalization,
    "candidates": [],
    "selected": None,
}

def set_camera_pose(pose):
    angle=math.radians(float(pose["azimuth_deg"]))
    radius=float(pose["radius"])*size
    cam.location=(
        center.x+math.cos(angle)*radius,
        center.y+math.sin(angle)*radius,
        center.z+float(pose["elevation"])*size,
    )
    cam.data.lens=float(pose["lens_mm"])
    look_at(cam,(center.x,center.y,center.z+float(pose.get("target_z",0.0))*size))

def normalized_foreground_mask(pixels, output_size=128):
    rgb=np.asarray(pixels,dtype=np.float32)[...,:3]
    border=np.concatenate((rgb[0],rgb[-1],rgb[:,0],rgb[:,-1]),axis=0)
    background=np.median(border,axis=0)
    distance=np.linalg.norm(rgb-background,axis=2)
    threshold=max(18.0/255.0,float(np.percentile(distance,65))*0.42)
    mask=distance>threshold
    neighbours=np.zeros(mask.shape,dtype=np.uint8)
    for dy,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
        neighbours+=np.roll(np.roll(mask,dy,axis=0),dx,axis=1)
    mask=mask & (neighbours>=2)
    points=np.argwhere(mask)
    if len(points)<16:
        return np.zeros((output_size,output_size),dtype=bool)
    y0,x0=points.min(axis=0); y1,x1=points.max(axis=0)+1
    cropped=mask[y0:y1,x0:x1]
    height,width=cropped.shape
    pad=max(2,int(max(height,width)*0.08))
    side=max(height,width)+pad*2
    square=np.zeros((side,side),dtype=bool)
    oy=(side-height)//2; ox=(side-width)//2
    square[oy:oy+height,ox:ox+width]=cropped
    indices=np.linspace(0,side-1,output_size).astype(np.int32)
    return square[indices][:,indices]

def mask_edge(mask):
    eroded=mask.copy()
    for dy,dx in ((-1,0),(1,0),(0,-1),(0,1)):
        eroded &= np.roll(np.roll(mask,dy,axis=0),dx,axis=1)
    return mask ^ eroded

def mask_iou(left,right):
    union=np.logical_or(left,right).sum()
    return float(np.logical_and(left,right).sum()/union) if union else 0.0

def mask_aspect(mask):
    points=np.argwhere(mask)
    if len(points)<2: return 0.0
    y0,x0=points.min(axis=0); y1,x1=points.max(axis=0)+1
    return float((x1-x0)/max(y1-y0,1))

def score_masks(reference,candidate):
    reference_edge=mask_edge(reference)
    candidates=[]
    for variant in (candidate,np.fliplr(candidate)):
        silhouette=mask_iou(reference,variant)
        edge=mask_iou(reference_edge,mask_edge(variant))
        left_profile=np.concatenate((reference.mean(axis=0),reference.mean(axis=1)))
        right_profile=np.concatenate((variant.mean(axis=0),variant.mean(axis=1)))
        profile=float(np.clip(1.0-np.mean(np.abs(left_profile-right_profile)),0.0,1.0))
        reference_aspect=mask_aspect(reference); candidate_aspect=mask_aspect(variant)
        aspect=min(reference_aspect,candidate_aspect)/max(reference_aspect,candidate_aspect,1e-9)
        score=silhouette*0.48+profile*0.27+aspect*0.15+edge*0.10
        candidates.append({
            "score":round(float(score),4),
            "silhouette_iou":round(float(silhouette),4),
            "profile_similarity":round(float(profile),4),
            "aspect_similarity":round(float(aspect),4),
            "edge_iou":round(float(edge),4),
        })
    return max(candidates,key=lambda item:item["score"])

original_render_engine=scene.render.engine
if camera_search_report["enabled"]:
    try:
        scene.render.engine='BLENDER_WORKBENCH'
        scene.display.shading.light='STUDIO'
        scene.display.shading.color_type='MATERIAL'
        scene.display.shading.show_shadows=True
        scene.display.shading.show_cavity=True
        scene.display.shading.cavity_type='BOTH'
        plane.hide_render=True
        reference_image=bpy.data.images.load(camera_search_config["reference"],check_existing=False)
        reference_image.scale(384,384)
        rw,rh=reference_image.size
        reference_pixels=np.array(reference_image.pixels[:],dtype=np.float32).reshape(rh,rw,4)
        reference_mask=normalized_foreground_mask(reference_pixels)
        candidate_dir=camera_search_config["candidate_dir"]
        import os
        os.makedirs(candidate_dir,exist_ok=True)
        scene.render.resolution_x=480
        scene.render.resolution_y=323
        scene.render.resolution_percentage=100
        try: scene.eevee.taa_render_samples=8
        except Exception: pass
        for pose in camera_search_config["poses"]:
            set_camera_pose(pose)
            candidate_path=os.path.join(candidate_dir,pose["id"]+".png")
            scene.render.filepath=candidate_path
            bpy.ops.render.render(write_still=True)
            rendered=bpy.data.images.load(candidate_path,check_existing=False)
            width,height=rendered.size
            pixels=np.array(rendered.pixels[:],dtype=np.float32).reshape(height,width,4)
            metrics=score_masks(reference_mask,normalized_foreground_mask(pixels))
            bpy.data.images.remove(rendered)
            camera_search_report["candidates"].append({
                "id":pose["id"],
                "path":candidate_path,
                "pose":pose,
                **metrics,
            })
        selected=max(camera_search_report["candidates"],key=lambda item:item["score"])
        camera_search_report["selected"]=selected
        set_camera_pose(selected["pose"])
    except Exception as exc:
        camera_search_report["error"]=str(exc)
        camera_search_report["enabled"]=False
        fallback=next(
            (pose for pose in camera_search_config["poses"] if pose["id"]=="legacy_pose"),
            camera_search_config["poses"][0],
        )
        camera_search_report["fallback_pose"]=fallback
        set_camera_pose(fallback)

scene.render.engine=original_render_engine
plane.hide_render=False
scene.render.resolution_x=1280
scene.render.resolution_y=860
scene.render.resolution_percentage=100
scene.render.filepath=camera_search_config["final_output"]
try: scene.eevee.taa_render_samples=64
except Exception: pass
with open(camera_search_config["report"],"w",encoding="utf-8") as report_file:
    json.dump(camera_search_report,report_file,ensure_ascii=False,indent=2)
'''.replace("__CONFIG__", repr(config))


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


def _normalize_exported_glb_axes(output_path: Path, expected_dimensions: list[float] | None) -> dict[str, Any]:
    """Bake a Z-up transform when the exported GLB has height in its Y extent."""
    report: dict[str, Any] = {
        "expected_dimensions_m": expected_dimensions,
        "applied": False,
        "rotation_x_deg": 0.0,
    }
    if not expected_dimensions or not output_path.is_file():
        return report
    loaded = trimesh.load(output_path, force="scene")
    if isinstance(loaded, trimesh.Trimesh):
        loaded = trimesh.Scene(loaded)
    if not isinstance(loaded, trimesh.Scene) or loaded.extents is None:
        report["error"] = "scene_extents_unavailable"
        return report
    current = [float(value) for value in loaded.extents]
    expected = [float(value) for value in expected_dimensions]
    rotated = [current[0], current[2], current[1]]
    direct_error = sum(abs(actual - target) / max(target, 1e-9) for actual, target in zip(current, expected))
    rotated_error = sum(abs(actual - target) / max(target, 1e-9) for actual, target in zip(rotated, expected))
    report.update({
        "exported_dimensions_before_m": current,
        "direct_error": direct_error,
        "rotated_error": rotated_error,
    })
    if rotated_error + 1e-6 >= direct_error:
        report["exported_dimensions_after_m"] = current
        return report
    loaded.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, (1, 0, 0)))
    temporary = output_path.with_name(f"{output_path.stem}.axis-normalized{output_path.suffix}")
    temporary.write_bytes(loaded.export(file_type="glb"))
    temporary.replace(output_path)
    verified = trimesh.load(output_path, force="scene")
    report.update({
        "applied": True,
        "rotation_x_deg": -90.0,
        "exported_dimensions_after_m": [float(value) for value in verified.extents],
    })
    return report


def _write_blender_script(
    script_path: Path,
    source_glbs: list[Path],
    selected_image_path: Path,
    output_glb: Path,
    output_png: Path,
    output_usd: Path,
    camera_search_report: Path,
    profile: str,
    expected_dimensions: list[float] | None = None,
) -> None:
    sources = json.dumps([str(path) for path in source_glbs])
    search_code = _camera_search_code({
        "enabled": profile == "final" and selected_image_path.is_file(),
        "reference": str(selected_image_path),
        "candidate_dir": str(output_png.parent / "camera_candidates"),
        "report": str(camera_search_report),
        "final_output": str(output_png),
        "poses": CAMERA_SEARCH_POSES,
    })
    script = f'''import bpy, math, json, numpy as np
from mathutils import Vector, Matrix
bpy.ops.wm.read_factory_settings(use_empty=True)
sources={sources}
for source in sources:
    bpy.ops.import_scene.gltf(filepath=source)
objects=[o for o in bpy.context.scene.objects if o.type=="MESH"]
if not objects: raise RuntimeError("GLB 메시 없음")
expected_dimensions={expected_dimensions!r}
coordinate_normalization={{"expected_dimensions_m":expected_dimensions,"applied":False,"rotation_x_deg":0.0}}
def object_bounds(targets):
    lower=Vector((1e9,1e9,1e9)); upper=Vector((-1e9,-1e9,-1e9))
    for target in targets:
        for corner in target.bound_box:
            point=target.matrix_world@Vector(corner)
            lower.x=min(lower.x,point.x); lower.y=min(lower.y,point.y); lower.z=min(lower.z,point.z)
            upper.x=max(upper.x,point.x); upper.y=max(upper.y,point.y); upper.z=max(upper.z,point.z)
    return lower,upper
if expected_dimensions and all(float(value)>0 for value in expected_dimensions):
    imported_min,imported_max=object_bounds(objects)
    imported_size=imported_max-imported_min
    current=[float(imported_size.x),float(imported_size.y),float(imported_size.z)]
    rotated=[current[0],current[2],current[1]]
    expected=[float(value) for value in expected_dimensions]
    direct_error=sum(abs(actual-target)/max(target,1e-9) for actual,target in zip(current,expected))
    rotated_error=sum(abs(actual-target)/max(target,1e-9) for actual,target in zip(rotated,expected))
    coordinate_normalization.update({{"imported_dimensions_m":current,"direct_error":direct_error,"rotated_error":rotated_error}})
    if rotated_error+1e-6<direct_error:
        correction=Matrix.Rotation(math.radians(-90.0),4,'X')
        for obj in objects:
            obj.matrix_world=correction@obj.matrix_world
        bpy.context.view_layer.update()
        coordinate_normalization.update({{"applied":True,"rotation_x_deg":-90.0}})
for idx,obj in enumerate(objects):
    for poly in obj.data.polygons: poly.use_smooth=False
    mat=bpy.data.materials.new(name=f"XconcepMaterial_{{idx}}")
    mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    name=obj.name.lower()
    if "hmi_screen" in name:
        color,metallic,roughness=(0.01,0.22,0.68,1.0),0.05,0.14
        if bsdf.inputs.get("Emission Color") is not None:
            bsdf.inputs["Emission Color"].default_value=(0.01,0.12,0.55,1.0)
            bsdf.inputs["Emission Strength"].default_value=0.35
        elif bsdf.inputs.get("Emission") is not None:
            bsdf.inputs["Emission"].default_value=(0.01,0.12,0.55,1.0)
    elif "emergency_stop" in name:
        color,metallic,roughness=(0.76,0.012,0.02,1.0),0.08,0.22
    elif "camera_lens" in name or "inspection_optic" in name:
        color,metallic,roughness=(0.008,0.035,0.075,1.0),0.28,0.08
    elif "status_button_green" in name:
        color,metallic,roughness=(0.02,0.48,0.10,1.0),0.06,0.20
    elif "status_button_amber" in name:
        color,metallic,roughness=(0.95,0.42,0.015,1.0),0.06,0.20
    elif "door_handle" in name or "panel_handle" in name:
        color,metallic,roughness=(0.015,0.02,0.025,1.0),0.40,0.24
    elif "safety_door" in name or "safety_cover" in name:
        color,metallic,roughness=(0.46,0.72,0.82,0.10),0.0,0.08
    elif "frame" in name or "gantry" in name or "conveyor_support" in name:
        color,metallic,roughness=(0.58,0.62,0.65,1.0),0.90,0.22
    elif "servo" in name or "camera" in name or "sensor" in name:
        color,metallic,roughness=(0.018,0.025,0.035,1.0),0.15,0.30
    elif "conveyor" in name or "guide" in name:
        color,metallic,roughness=(0.24,0.29,0.32,1.0),0.72,0.25
    elif "control_panel" in name:
        color,metallic,roughness=(0.22,0.25,0.28,1.0),0.58,0.31
    else:
        color,metallic,roughness=(0.08,0.30,0.58,1.0),0.30,0.32
    bsdf.inputs["Base Color"].default_value=color
    bsdf.inputs["Metallic"].default_value=metallic
    bsdf.inputs["Roughness"].default_value=roughness
    if color[3] < 1.0:
        bsdf.inputs["Alpha"].default_value=color[3]
        for socket_name in ("Transmission Weight","Transmission"):
            if bsdf.inputs.get(socket_name) is not None:
                bsdf.inputs[socket_name].default_value=0.18
        mat.diffuse_color=color
        try: mat.use_transparency_overlap=False
        except Exception: pass
        try: mat.surface_render_method='BLENDED'
        except Exception:
            try: mat.blend_method='BLEND'
            except Exception: pass
    obj.data.materials.clear(); obj.data.materials.append(mat)
    bevel=obj.modifiers.new(name="Manufacturing Edge",type='BEVEL')
    bevel.width=max(min(obj.dimensions)*0.008,0.00025); bevel.segments=3; bevel.limit_method='ANGLE'
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
bpy.ops.object.camera_add(location=(center.x+size*2.35,center.y-size*2.35,center.z+size*0.92))
cam=bpy.context.object; bpy.context.scene.camera=cam; look_at(cam,center)
cam.data.lens=58
for loc,energy,area,temp in [((3,-4,5),850,3.5,0),((-3,-1,2.5),420,2.8,0),((0,4,4),560,2.4,0)]:
    bpy.ops.object.light_add(type='AREA',location=(center.x+loc[0]*size/4,center.y+loc[1]*size/4,center.z+loc[2]*size/4))
    light=bpy.context.object; light.data.energy=energy; light.data.shape='DISK'; light.data.size=max(area*size/4,.2); look_at(light,center)
scene=bpy.context.scene
try:
    scene.render.engine='BLENDER_EEVEE_NEXT'
except TypeError:
    scene.render.engine='BLENDER_EEVEE'
try:
    scene.eevee.taa_render_samples=64
    scene.eevee.use_gtao=True
    scene.eevee.gtao_quality=1.0
    scene.eevee.gtao_distance=max(size*0.08,0.08)
    scene.eevee.shadow_ray_count=4
    scene.eevee.shadow_step_count=8
    scene.eevee.shadow_pool_size='1024'
except Exception: pass
scene.render.resolution_x=1280; scene.render.resolution_y=860; scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'; scene.render.filepath={str(output_png)!r}
scene.view_settings.exposure=-0.35
try: scene.view_settings.look='AgX - Medium High Contrast'
except Exception: pass
if scene.world is None: scene.world=bpy.data.worlds.new("Xconcep World")
scene.world.color=(0.01,0.015,0.025)
scene.render.film_transparent=False
scene.render.image_settings.color_mode='RGBA'
{search_code}
bpy.ops.wm.save_as_mainfile(filepath={str(output_glb.with_suffix('.blend'))!r})
bpy.ops.object.select_all(action='DESELECT')
for obj in objects: obj.select_set(True)
bpy.context.view_layer.objects.active=objects[0]
bpy.ops.export_scene.gltf(filepath={str(output_glb)!r},export_format='GLB',export_apply=True,use_selection=True)
try:
    try:
        bpy.ops.wm.usd_export(filepath={str(output_usd)!r},export_materials=True,export_textures=True,selected_objects_only=True)
    except TypeError:
        bpy.ops.wm.usd_export(filepath={str(output_usd)!r},export_materials=True,selected_objects_only=True)
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
    camera_search_path = output_dir / "camera_search_report.json"
    binary = shutil.which(blender_bin) or (str(Path(blender_bin).resolve()) if Path(blender_bin).is_file() else None)
    provider: dict[str, Any]
    dimensions = design_state.get("dimensions", {})
    expected_dimensions = (
        [
            float(dimensions.get("width_mm") or dimensions.get("length_mm")) / 1000.0,
            float(dimensions.get("depth_mm")) / 1000.0,
            float(dimensions.get("height_mm")) / 1000.0,
        ]
        if all(dimensions.get(key) for key in ("width_mm", "depth_mm", "height_mm"))
        else None
    )
    if mode == "native" and not binary:
        raise RuntimeError(f"Blender native binary not found: {blender_bin}")
    if mode != "mock" and binary:
        _write_blender_script(
            script_path, source_glbs, selected_image_path, output_glb, output_png,
            output_usd, camera_search_path, profile,
            expected_dimensions,
        )
        started = time.perf_counter()
        completed = subprocess.run(
            [binary, "--background", "--python", str(script_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = round(time.perf_counter() - started, 3)
        if completed.returncode != 0 or not output_glb.exists() or not output_png.exists():
            if mode == "native":
                details = (completed.stderr or completed.stdout)[-2400:]
                raise RuntimeError(f"Blender native generation failed: {details}")
            _merge_glbs(source_glbs, output_glb)
            create_preview(output_glb, selected_image_path, output_png, "")
            provider = {"mode": "fallback", "engine": "blender", "error": completed.stderr[-1600:]}
        else:
            provider = {
                "mode": "native", "engine": "blender", "binary": binary, "profile": profile,
                "returncode": completed.returncode, "duration_seconds": elapsed,
            }
            if camera_search_path.is_file():
                try:
                    camera_search = json.loads(camera_search_path.read_text(encoding="utf-8"))
                    provider["camera_search"] = {
                        "enabled": camera_search.get("enabled"),
                        "selected": camera_search.get("selected"),
                        "candidate_count": len(camera_search.get("candidates") or []),
                    }
                except (OSError, ValueError, TypeError):
                    provider["camera_search"] = {"enabled": False, "error": "report_parse_failed"}
    else:
        _merge_glbs(source_glbs, output_glb)
        create_preview(output_glb, selected_image_path, output_png, "")
        _write_blender_script(
            script_path, source_glbs, selected_image_path, output_glb, output_png,
            output_usd, camera_search_path, profile,
        )
        provider = {"mode": "mock" if mode == "mock" else "fallback", "engine": "blender", "binary_found": bool(binary), "profile": profile}

    if output_glb.is_file():
        provider["glb_axis_normalization"] = _normalize_exported_glb_axes(output_glb, expected_dimensions)
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
        "camera_search_path": camera_search_path if camera_search_path.exists() else None,
        "provider": provider,
    }
