import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1 :]
input_path, output_path = args
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=input_path)
objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if not objects:
    raise RuntimeError("GLB에 렌더링할 메시가 없음")
mins = Vector((1e9, 1e9, 1e9)); maxs = Vector((-1e9, -1e9, -1e9))
for obj in objects:
    for corner in obj.bound_box:
        point = obj.matrix_world @ Vector(corner)
        mins.x = min(mins.x, point.x); mins.y = min(mins.y, point.y); mins.z = min(mins.z, point.z)
        maxs.x = max(maxs.x, point.x); maxs.y = max(maxs.y, point.y); maxs.z = max(maxs.z, point.z)
center = (mins + maxs) / 2
size = max((maxs - mins))

bpy.ops.object.camera_add(location=(center.x + size * 2.2, center.y - size * 2.2, center.z + size * 1.7))
camera = bpy.context.object
bpy.context.scene.camera = camera
def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
look_at(camera, center)
for loc, energy, radius in [((4, -4, 7), 1500, 4), ((-4, -2, 4), 900, 3), ((0, 5, 6), 1200, 3)]:
    bpy.ops.object.light_add(type='AREA', location=(center.x + loc[0] * size/4, center.y + loc[1] * size/4, center.z + loc[2] * size/4))
    light = bpy.context.object
    light.data.energy = energy
    light.data.shape = 'DISK'; light.data.size = radius * size/4
    look_at(light, center)

bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
bpy.context.scene.render.resolution_x = 1280
bpy.context.scene.render.resolution_y = 860
bpy.context.scene.render.resolution_percentage = 100
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.filepath = output_path
bpy.context.scene.world.color = (0.015, 0.025, 0.04)
bpy.ops.render.render(write_still=True)
