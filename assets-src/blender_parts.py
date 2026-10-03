import bpy, sys, mathutils
argv = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=argv[0])
name = argv[1]; ymin = float(argv[2])
ob = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name.startswith(name)][0]
bpy.context.view_layer.objects.active = ob
for o in bpy.context.scene.objects: o.select_set(o == ob)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.separate(type='LOOSE'); bpy.ops.object.mode_set(mode='OBJECT')
parts = [o for o in bpy.context.selected_objects]
rows = []
for o in parts:
    ws = [o.matrix_world @ v.co for v in o.data.vertices]
    mn = mathutils.Vector((min(v.x for v in ws), min(v.y for v in ws), min(v.z for v in ws)))
    mx = mathutils.Vector((max(v.x for v in ws), max(v.y for v in ws), max(v.z for v in ws)))
    rows.append((o.name, len(o.data.polygons), mn, mx))
print('PARTS', len(rows))
for r in sorted(rows, key=lambda r: -r[3].z):
    if r[3].z > ymin: print('P', r[0], r[1], 'min', tuple(round(v, 2) for v in r[2]), 'max', tuple(round(v, 2) for v in r[3]))
