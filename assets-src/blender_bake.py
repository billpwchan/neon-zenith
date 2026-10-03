# Bake a multi-material model into one instancing-friendly mesh: joined, oriented (nose to glTF -Z), scaled,
# decimated, unwrapped to a single atlas, and every material baked into three maps:
#   albedo.png  RGB albedo (sRGB),  A = glass mask
#   mr.png      R = paint mask,     G = roughness,  B = metalness  (glTF metallicRoughness layout)
#   emit.png    RGB emission (sRGB, normalised), A = opacity (decal cut-outs)
# Writes <out>/lod.glb (nodes lod0, lod1; placeholder material) and the three PNGs.
# usage: blender -b --python blender_bake.py -- config.json
import bpy, bmesh, sys, json, re, math, os
import numpy as np
from mathutils import Vector, Matrix

cfg = json.load(open(sys.argv[sys.argv.index('--') + 1:][0]))
out = cfg['out']
os.makedirs(out, exist_ok=True)
S = cfg.get('tex', 1024)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=cfg['src'])

# --- keep only the wanted part of the scene ---
objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if 'keep_root' in cfg:
    # keep the meshes under the named node (used for picking one car out of a pack)
    root = bpy.data.objects[cfg['keep_root']]
    def under(o):
        while o:
            if o == root: return True
            o = o.parent
        return False
    objs = [o for o in objs if under(o)]
if 'keep_radius' in cfg:
    cx, cy, r = cfg['keep_radius']
    def near(o):
        c = sum((o.matrix_world @ Vector(b) for b in o.bound_box), Vector()) / 8
        return math.hypot(c.x - cx, c.y - cy) < r
    objs = [o for o in objs if near(o)]
if 'keep_box' in cfg:
    lo, hi = Vector(cfg['keep_box'][0]), Vector(cfg['keep_box'][1])
    def inside(o):
        c = sum((o.matrix_world @ Vector(b) for b in o.bound_box), Vector()) / 8
        return all(lo[i] <= c[i] <= hi[i] for i in range(3))
    objs = [o for o in objs if inside(o)]
# make single-user, unparent keeping the world transform (before the empties go), apply, then join
for o in objs:
    o.data = o.data.copy()
bpy.ops.object.select_all(action='DESELECT')
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
for o in list(bpy.context.scene.objects):
    if o not in objs: bpy.data.objects.remove(o, do_unlink=True)
print('KEEP', len(objs))
bpy.ops.object.select_all(action='DESELECT')
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
ob.name = 'lod0'

# drop faces of unwanted materials (interiors that dark glass will hide anyway)
drop = re.compile(cfg['drop']) if cfg.get('drop') else None
if drop:
    bm = bmesh.new(); bm.from_mesh(ob.data)
    names = [s.material.name if s.material else '' for s in ob.material_slots]
    dead = [f for f in bm.faces if drop.search(names[f.material_index])]
    bmesh.ops.delete(bm, geom=dead, context='FACES')
    bm.to_mesh(ob.data); bm.free()
    print('DROPPED faces', len(dead))

# --- orient, scale, sit on the ground ---
rz = math.radians(cfg.get('rotZ', 180))
if cfg.get('pca'):
    # align the body's long axis with Y first (cars in a pack sit at arbitrary angles)
    xy = np.array([(v.co.x, v.co.y) for v in ob.data.vertices])
    xy -= xy.mean(0)
    w, V = np.linalg.eigh(np.cov(xy.T))
    a = math.atan2(V[1, -1], V[0, -1])
    rz += math.pi / 2 - a
ob.data.transform(Matrix.Rotation(rz, 4, 'Z'))
print('ROT', round(math.degrees(rz), 1))
vs = [v.co for v in ob.data.vertices]
mn = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
mx = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
s = cfg['length'] / (mx.y - mn.y)
ob.data.transform(Matrix.Translation(Vector((-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z))))
ob.data.transform(Matrix.Scale(s, 4))
print('SIZE', [round((mx[i] - mn[i]) * s, 3) for i in range(3)])

# --- weld and decimate to the LOD0 budget ---
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0005)
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.object.mode_set(mode='OBJECT')
def tris(o): return sum(len(p.vertices) - 2 for p in o.data.polygons)
def decimate(o, target):
    t = tris(o)
    if t <= target: return
    m = o.modifiers.new('dec', 'DECIMATE'); m.ratio = target / t; m.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=m.name)
decimate(ob, cfg.get('lod0', 8000))
print('LOD0 tris', tris(ob))

# --- atlas UV: a new map that the bake writes through; the old map keeps feeding the source materials ---
src_uv = ob.data.uv_layers[0].name if ob.data.uv_layers else None
uv = ob.data.uv_layers.new(name='bake')
ob.data.uv_layers.active = uv
if src_uv: ob.data.uv_layers[src_uv].active_render = True
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004, area_weight=0.6, scale_to_bounds=True)
bpy.ops.object.mode_set(mode='OBJECT')

# --- bake helpers ---
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = 4
sc.render.bake.margin = 6
sc.render.bake.use_clear = True
img = bpy.data.images.new('bake', S, S, alpha=True, float_buffer=True)
img.colorspace_settings.name = 'Non-Color'

def principled(m):
    return next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if m and m.use_nodes else None

mats = [s.material for s in ob.material_slots if s.material]
for m in mats:
    if not m.use_nodes: m.use_nodes = True
    nt = m.node_tree
    tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = img; tn.name = '_bake'
    for n in nt.nodes: n.select = False
    tn.select = True; nt.nodes.active = tn

def read():
    a = np.empty(S * S * 4, dtype=np.float32); img.pixels.foreach_get(a)
    return a.reshape(S, S, 4)

def bake(kind, **kw):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.bake(type=kind, **kw)
    return read()

def bake_value(fn):
    # bake a per-material scalar or colour by routing it through an emission shader
    saved = []
    for m in mats:
        nt = m.node_tree
        outn = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output) if any(n.type == 'OUTPUT_MATERIAL' for n in nt.nodes) else None
        if not outn: continue
        old = [l.from_socket for l in outn.inputs['Surface'].links]
        em = nt.nodes.new('ShaderNodeEmission'); em.name = '_tmp'
        fn(m, nt, em)
        nt.links.new(em.outputs[0], outn.inputs['Surface'])
        saved.append((m, outn, old, em))
    r = bake('EMIT')
    for m, outn, old, em in saved:
        nt = m.node_tree
        nt.nodes.remove(em)
        for s in old: nt.links.new(s, outn.inputs['Surface'])
    return r

def route(inp_name, scalar=True):
    def fn(m, nt, em):
        p = principled(m)
        if not p:
            em.inputs['Color'].default_value = (0, 0, 0, 1); return
        i = p.inputs[inp_name]
        if i.is_linked:
            nt.links.new(i.links[0].from_socket, em.inputs['Color'])
        else:
            v = i.default_value
            em.inputs['Color'].default_value = (v, v, v, 1) if scalar else tuple(v)
    return fn

def flag(rx, extra=None):
    r = re.compile(rx) if rx else None
    def fn(m, nt, em):
        on = bool(r and r.search(m.name))
        if extra and not on: on = extra(m)
        em.inputs['Color'].default_value = (1, 1, 1, 1) if on else (0, 0, 0, 1)
    return fn

def is_glass(m):
    p = principled(m)
    if not p: return False
    a = p.inputs['Alpha']; t = p.inputs.get('Transmission Weight')
    return (not a.is_linked and a.default_value < 0.9) or (t is not None and not t.is_linked and t.default_value > 0.5)

emit_cfg = {re.compile(k): v for k, v in cfg.get('emit', {}).items()}
emit_base = re.compile(cfg['emit_base']) if cfg.get('emit_base') else None
def emission(m, nt, em):
    if emit_base and emit_base.search(m.name):
        route('Base Color', scalar=False)(m, nt, em); return
    for r, (cr, cg, cb, k) in emit_cfg.items():
        if r.search(m.name):
            em.inputs['Color'].default_value = (cr * k, cg * k, cb * k, 1); return
    p = principled(m)
    if not p: em.inputs['Color'].default_value = (0, 0, 0, 1); return
    st = p.inputs['Emission Strength'].default_value
    c = p.inputs['Emission Color']
    if st <= 0: em.inputs['Color'].default_value = (0, 0, 0, 1); return
    if c.is_linked: nt.links.new(c.links[0].from_socket, em.inputs['Color']); em.inputs['Strength'].default_value = st
    else: v = c.default_value; em.inputs['Color'].default_value = (v[0] * st, v[1] * st, v[2] * st, 1)

def override_color(m, nt, em):
    # colour overrides for materials whose authored colour is wrong for us (e.g. white glass)
    for k, v in cfg.get('color', {}).items():
        if re.search(k, m.name): em.inputs['Color'].default_value = (*v, 1); return True
    return False

def base(m, nt, em):
    if override_color(m, nt, em): return
    route('Base Color', scalar=False)(m, nt, em)

albedo = bake_value(base)
rough = bake_value(route('Roughness'))
metal = bake_value(route('Metallic'))
glass_rx = cfg.get('glass')
glass = bake_value(flag(glass_rx, None if cfg.get('glass_only_rx') else is_glass))
paint = bake_value(flag(cfg.get('paint')))
emit = bake_value(emission)
def cutout(m, nt, em):
    # only authored alpha textures (decals, logos) cut holes; flat alpha belongs to glass, handled by the glass mask
    p = principled(m)
    a = p.inputs['Alpha'] if p else None
    if a is not None and a.is_linked: nt.links.new(a.links[0].from_socket, em.inputs['Color'])
    else: em.inputs['Color'].default_value = (1, 1, 1, 1)
alpha = bake_value(cutout)
# lamps read as glass too if they are transparent; they keep their own colour
lampmask = (emit[..., :3].max(-1) > 0.02)

def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)

def save(name, rgba):
    im = bpy.data.images.new(name, S, S, alpha=True, float_buffer=False)
    im.colorspace_settings.name = 'Non-Color'
    im.pixels.foreach_set(np.clip(rgba, 0, 1).astype(np.float32).ravel())
    im.filepath_raw = os.path.join(out, name)
    im.file_format = 'PNG'
    im.save()

g = np.where(lampmask, 0, glass[..., 0])
save('albedo.png', np.dstack([srgb(albedo[..., 0]), srgb(albedo[..., 1]), srgb(albedo[..., 2]), g]))
save('mr.png', np.dstack([paint[..., 0], rough[..., 0], metal[..., 0], np.ones((S, S))]))
emax = max(1e-3, float(emit[..., :3].max()))
save('emit.png', np.dstack([srgb(emit[..., 0] / emax), srgb(emit[..., 1] / emax), srgb(emit[..., 2] / emax), alpha[..., 0]]))
print('EMAX', emax)

# --- LOD1 from LOD0, sharing the atlas ---
for m in mats:
    nt = m.node_tree
    n = nt.nodes.get('_bake')
    if n: nt.nodes.remove(n)
ob.data.uv_layers.remove(ob.data.uv_layers[src_uv]) if src_uv else None
ob.data.materials.clear()
pm = bpy.data.materials.new('atlas'); ob.data.materials.append(pm)
lod1 = ob.copy(); lod1.data = ob.data.copy(); lod1.name = 'lod1'
sc.collection.objects.link(lod1)
decimate(lod1, cfg.get('lod1', 900))
print('LOD1 tris', tris(lod1))
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=os.path.join(out, 'lod.glb'), export_format='GLB', use_selection=True, export_yup=True, export_materials='PLACEHOLDER', export_normals=True, export_texcoords=True)
json.dump({'emax': emax, 'size': [round((mx[i] - mn[i]) * s, 3) for i in (0, 2, 1)], 'lod0': tris(ob), 'lod1': tris(lod1)}, open(os.path.join(out, 'info.json'), 'w'))
print('DONE')
