import bpy, sys, mathutils, math
argv = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=argv[0])
ob = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name.startswith('spinner_0')][0]
bpy.context.view_layer.objects.active = ob
for o in bpy.context.scene.objects: o.select_set(o == ob)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.separate(type='LOOSE'); bpy.ops.object.mode_set(mode='OBJECT')
red = bpy.data.materials.new('red'); red.diffuse_color = (1, 0, 0, 1)
door = []
for o in bpy.context.scene.objects:
    if o.type != 'MESH' or not o.name.startswith('spinner_0'): continue
    ws = [o.matrix_world @ v.co for v in o.data.vertices]
    if min(v.x for v in ws) > 0.7 and max(v.z for v in ws) > 1.35 and max(v.y for v in ws) < 0:
        door.append(o)
for o in door:
    o.data.materials.clear(); o.data.materials.append(red)
print('DOOR', len(door))
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.color_type = 'MATERIAL'
sc.render.resolution_x, sc.render.resolution_y = 1400, 800
cam = bpy.data.cameras.new('c'); cam.type = 'ORTHO'; cam.ortho_scale = 5
co = bpy.data.objects.new('c', cam); sc.collection.objects.link(co); sc.camera = co
co.location = (6, 0, 1.1); co.rotation_euler = (math.pi / 2, 0, math.pi / 2)
sc.render.filepath = argv[1]; bpy.ops.render.render(write_still=True)
co.location = (0, -6, 1.1); co.rotation_euler = (math.pi / 2, 0, 0)
sc.render.filepath = argv[2]; bpy.ops.render.render(write_still=True)
