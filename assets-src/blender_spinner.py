# Close the spinner's scissor door (baked open in the Sketchfab mesh) and export a clean GLB.
import bpy, sys, mathutils, math
argv = sys.argv[sys.argv.index('--') + 1:]
src, out, ang = argv[0], argv[1], float(argv[2])
piv = mathutils.Vector((0.8, float(argv[3]), float(argv[4])))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
R = mathutils.Matrix.Translation(piv) @ mathutils.Matrix.Rotation(math.radians(ang), 4, 'X') @ mathutils.Matrix.Translation(-piv)
import bmesh
door = 0
for ob in [o for o in bpy.context.scene.objects if o.type == 'MESH']:
  mw = ob.matrix_world.copy(); mwi = mw.inverted()
  bm = bmesh.new(); bm.from_mesh(ob.data)
  bm.verts.ensure_lookup_table()
  seen = set()
  for v in bm.verts:
    if v.index in seen: continue
    isl = []; st = [v]; seen.add(v.index)
    while st:
        a = st.pop(); isl.append(a)
        for e in a.link_edges:
            b = e.other_vert(a)
            if b.index not in seen: seen.add(b.index); st.append(b)
    ws = [mw @ a.co for a in isl]
    if min(p.x for p in ws) > 0.68 and max(p.z for p in ws) > 1.35 and max(p.y for p in ws) < 0 and min(p.z for p in ws) > 0.5:
        door += 1
        for a in isl: a.co = mwi @ (R @ (mw @ a.co))
  bm.to_mesh(ob.data); bm.free()
print('DOOR islands', door)
if len(argv) > 5:
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.render.resolution_x, sc.render.resolution_y = 1400, 800
    cam = bpy.data.cameras.new('c'); cam.type = 'ORTHO'; cam.ortho_scale = 5
    co = bpy.data.objects.new('c', cam); sc.collection.objects.link(co); sc.camera = co
    co.location = (6, 0, 1.1); co.rotation_euler = (math.pi / 2, 0, math.pi / 2)
    sc.render.filepath = argv[5]; bpy.ops.render.render(write_still=True)
    co.location = (6, 0, 1.1); co.rotation_euler = (math.pi / 2, 0, math.pi / 2); cam.ortho_scale = 2.4; co.location = (6, -0.2, 1.0)
    sc.render.filepath = argv[6]; bpy.ops.render.render(write_still=True)
else:
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_yup=True)
