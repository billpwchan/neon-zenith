# Shopfront slicer: cuts the Asian Shop Pack into the shop modules the street strip is made of (shops.mjs CUTS,
# in the same order), each moved to its own origin (left edge, pavement, wall) in metres. The pack's fronts share
# one street line; 'wall' (Blender y) is just behind its deepest shutter, so everything in front stands proud.
# blender -b --python shop_slice.py -- cfg.json
#   cfg: src, out, drop (regex), wall, modules [{name, x0, x1, z0, z1}] in Blender coordinates (z up, front -y)
import bpy, bmesh, sys, json, re
from mathutils import Vector, Matrix

cfg = json.load(open(sys.argv[sys.argv.index('--') + 1]))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=cfg['src'])
drop = re.compile(cfg['drop'])
src = [o for o in bpy.data.objects if o.type == 'MESH' and not any(drop.search(s.material.name) for s in o.material_slots if s.material)]


def bbox(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)])


made = []
for md in cfg['modules']:
    x0, x1, z0, z1 = md['x0'], md['x1'], md['z0'], md['z1']
    parts = []
    for ob in src:
        lo, hi = bbox(ob)
        if hi.x <= x0 or lo.x >= x1 or hi.z <= z0 + 0.01 or lo.z >= z1 - 0.01: continue
        me = ob.data.copy(); me.transform(ob.matrix_world)
        bm = bmesh.new(); bm.from_mesh(me)
        for x in (x0, x1):
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(x, 0, 0), plane_no=(1, 0, 0))
        dead = [f for f in bm.faces if not (x0 <= f.calc_center_median().x <= x1 and z0 <= f.calc_center_median().z <= z1)]
        bmesh.ops.delete(bm, geom=dead, context='FACES')
        if not bm.faces: bm.free(); continue
        bm.to_mesh(me); bm.free()
        o = bpy.data.objects.new(md['name'], me); bpy.context.scene.collection.objects.link(o); parts.append(o)
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts: o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1: bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = 'S_' + md['name']
    o.data.transform(Matrix.Translation((-x0, -cfg['wall'], -z0)))
    ys = [v.co.y for v in o.data.vertices]
    print('MOD', md['name'], 'w', round(x1 - x0, 3), 'depth', round(min(ys), 2), round(max(ys), 2), 'tris', sum(len(p.vertices) - 2 for p in o.data.polygons))
    made.append(o)
for ob in list(bpy.data.objects):
    if ob not in made: bpy.data.objects.remove(ob)
bpy.ops.export_scene.gltf(filepath=cfg['out'], export_format='GLB', export_apply=True, export_yup=True)
