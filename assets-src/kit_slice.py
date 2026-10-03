# Facade kit slicer: cuts a modelled facade into bay x floor cells for instancing on the city's buildings.
# Wall and cable meshes are bisected on the grid; small props (AC units, railings, awnings) stay whole and
# go to the cell holding their centre. Cells are moved to their own origin (left edge, floor line, wall
# plane) and scaled to metres. Writes one glb with objects L0_c_r (full detail) and L1_c_r (far).
# blender -b --python kit_slice.py -- cfg.json
#   cfg: src, out, scale, grid {x0, bay, nb, y0, pitch, nf}, lod0 {x0, x1, ymax, zmin}, lod1 {x0, x1, nb} (optional),
#        whole (max raw size for a prop to stay whole), decimate [[regex, ratio], ...], drop (regex, props left out),
#        wall (Blender y of the wall plane, default 0), zcut (faces whose front depth -y is below it are left out:
#        for whole buildings whose back and floor slabs share meshes with the front), lod1.simplify (no authored far
#        panel: the far cells are the near ones decimated to this ratio)
import bpy, bmesh, sys, json, re, math
from mathutils import Vector, Matrix

cfg = json.load(open(sys.argv[sys.argv.index('--') + 1]))
G = cfg['grid']
S = cfg['scale']

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=cfg['src'])
drop = re.compile(cfg['drop']) if cfg.get('drop') else None


def names(ob):
    return [ob.name] + [s.material.name for s in ob.material_slots if s.material]


# glTF (x, y, z) -> Blender (x, -z, y): height is Blender z, the facade front is Blender -y
def bbox(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def pick(x0, x1, ymax, zmin):
    out = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH': continue
        lo, hi = bbox(ob)
        c = (lo + hi) / 2
        # glTF z (front) = -Blender y
        big = max(hi.x - lo.x, hi.z - lo.z) > cfg['whole']
        front = -c.y >= zmin or (big and 'zcut' in cfg and -lo.y >= cfg['zcut'])
        if (x0 - 0.05 <= c.x <= x1 + 0.05 or big) and c.z <= ymax and front and hi.z > G['y0']:
            if drop and any(drop.search(n) for n in names(ob)): continue
            out.append(ob)
    return out


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


# uneven bays (grid.xs, the pier centres): cut on the piers and stretch every cell to the mean bay, as
# facades.mjs stretches the photo
XS = G.get('xs')


def cell_of(x, z, x0):
    c = (sum(1 for v in XS[1:-1] if x >= v) if XS[0] <= x <= XS[-1] else -1) if XS and x0 == XS[0] else math.floor((x - x0) / G['bay'])
    r = math.floor((z - G['y0']) / G['pitch'])
    return c, r


def build(objs, x0, nb, prefix, decim):
    whole, cut = [], []
    for ob in objs:
        lo, hi = bbox(ob)
        size = max(hi.x - lo.x, hi.z - lo.z)
        (whole if size <= cfg['whole'] else cut).append(ob)
    # heavy little props lose triangles nobody will see
    for ob in whole + cut:
        for rx, ratio in decim:
            if any(re.search(rx, n) for n in names(ob)) and tris(ob) > 600:
                if ob.data.users > 1: ob.data = ob.data.copy()
                mod = ob.modifiers.new('d', 'DECIMATE'); mod.ratio = ratio
                bpy.context.view_layer.objects.active = ob
                with bpy.context.temp_override(object=ob, active_object=ob):
                    bpy.ops.object.modifier_apply(modifier='d')
                break
    cells = {}
    def add(c, r, me):
        cells.setdefault((c, r), []).append(me)
    # bisected meshes: cut on every grid line, faces sorted by centroid
    xs = XS[1:-1] if XS and x0 == XS[0] else [x0 + k * G['bay'] for k in range(1, nb)]
    zs = [G['y0'] + k * G['pitch'] for k in range(0, G['nf'] + 1)]
    for ob in cut:
        me = ob.data.copy()
        me.transform(ob.matrix_world)
        bm = bmesh.new(); bm.from_mesh(me)
        for x in xs:
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(x, 0, 0), plane_no=(1, 0, 0))
        for z in zs:
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, z), plane_no=(0, 0, 1))
        bm.faces.ensure_lookup_table()
        zc = cfg.get('zcut')
        keys = [(-1, -1) if zc is not None and -f.calc_center_median().y < zc else cell_of(f.calc_center_median().x, f.calc_center_median().z, x0) for f in bm.faces]
        for key in set(keys):
            c, r = key
            if not (0 <= c < nb and 0 <= r < G['nf']): continue
            b2 = bm.copy()
            b2.faces.ensure_lookup_table()
            dead = [f for f, k in zip(b2.faces, keys) if k != key]
            bmesh.ops.delete(b2, geom=dead, context='FACES')
            m2 = bpy.data.meshes.new(f'{ob.name}_{c}_{r}')
            b2.to_mesh(m2); b2.free()
            for mat in me.materials: m2.materials.append(mat)
            add(c, r, m2)
        bm.free()
    for ob in whole:
        lo, hi = bbox(ob)
        cx, cz = (lo.x + hi.x) / 2, (lo.z + hi.z) / 2
        c, r = cell_of(cx, cz, x0)
        if not (0 <= c < nb and 0 <= r < G['nf']): continue
        me = ob.data.copy(); me.transform(ob.matrix_world)
        add(c, r, me)
    made = []
    for (c, r), meshes in cells.items():
        parts = []
        for me in meshes:
            o = bpy.data.objects.new(me.name, me); bpy.context.scene.collection.objects.link(o); parts.append(o)
        bpy.ops.object.select_all(action='DESELECT')
        for o in parts: o.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        if len(parts) > 1: bpy.ops.object.join()
        o = bpy.context.view_layer.objects.active
        o.name = f'{prefix}_{c}_{r}'
        # cell origin: left edge, floor line, wall plane; then metres
        left = XS[c] if XS and x0 == XS[0] else x0 + c * G['bay']
        o.data.transform(Matrix.Translation((-left, -cfg.get('wall', 0), -(G['y0'] + r * G['pitch']))))
        if XS and x0 == XS[0]: o.data.transform(Matrix.Diagonal((G['bay'] / (XS[c + 1] - XS[c]), 1, 1, 1)))
        o.data.transform(Matrix.Scale(S, 4))
        made.append(o)
    return made


L0 = cfg['lod0']
src0 = pick(L0['x0'], L0['x1'], L0['ymax'], L0['zmin'])
L1 = cfg.get('lod1', {})
keep = build(src0, L0['x0'], G['nb'], 'L0', cfg.get('decimate', []))
if 'simplify' in L1:
    keep += build(src0, L0['x0'], G['nb'], 'L1', [['.', L1['simplify']]])
elif L1:
    keep += build(pick(L1['x0'], L1['x1'], L0['ymax'], L0['zmin']), L1['x0'], L1['nb'], 'L1', [])
for ob in list(bpy.data.objects):
    if ob not in keep: bpy.data.objects.remove(ob)
print('cells', len(keep), 'tris', {o.name: tris(o) for o in keep})
bpy.ops.export_scene.gltf(filepath=cfg['out'], export_format='GLB', export_apply=True, export_yup=True)
