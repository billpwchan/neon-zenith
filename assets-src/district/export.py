# The composed district (compose.py) made ready for the game: hidden faces culled, a lightmap UV laid out over all
# static geometry and Cycles' diffuse light baked into one atlas, the light at street level baked top-down for the
# ground and anything that moves, the props' light read off the surface behind them, then the static geometry
# merged per material into district.glb, the props into props.glb with distance LODs, and the placements,
# colliders and maps into district.json.
# blender -b --python compose.py --python export.py -- cfg.json
#   cfg (on top of compose's): lm_size, bake_samples, ground_ppm, out_public, out_src
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector, Matrix
from mathutils.interpolate import poly_3d_calc

cfg = json.load(open(sys.argv[sys.argv.index('--') + 1]))
ROOT = os.environ.get('NZ_ROOT', os.getcwd())
L = json.load(open(f'{ROOT}/assets-src/district/layout.json'))
OX, OZ = cfg['origin']
PUB = cfg.get('out_public', f'{ROOT}/public/district')
SRC = cfg.get('out_src', f'{ROOT}/src/city/district.json')
BUILD = f'{ROOT}/assets-src/district/build'
os.makedirs(PUB, exist_ok=True); os.makedirs(BUILD, exist_ok=True)
scene = bpy.context.scene
LM_SIZE = cfg.get('lm_size', 4096)
LOG_K, LOG_MAX = 1 / 32, 32.0
LOG_N = math.log2(1 + LOG_MAX / LOG_K)


def game(p):
    return (p.x + OX, p.z, -p.y + OZ)


def tagged(t):
    return [o for o in scene.objects if o.type == 'MESH' and o.get('nz', '').startswith(t)]


def select(objs, active=None):
    bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.object and bpy.context.object.mode != 'OBJECT' else None
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]


LMO = tagged('lm')
print('LM objects', len(LMO))

# ---------------------------------------------------------------- cull faces nothing can see
# a face is hidden when, a hand's breadth out from it, something solid stands at its middle and every corner:
# party walls against the next lot, the undersides sitting on the ground
dg = bpy.context.evaluated_depsgraph_get()
culled = 0
for o in LMO:
    if o.data.users > 1: o.data = o.data.copy()
    mw = o.matrix_world
    nm = mw.to_3x3().inverted().transposed()
    bm = bmesh.new(); bm.from_mesh(o.data)
    dead = []
    for f in bm.faces:
        n = (nm @ f.normal).normalized()
        c = f.calc_center_median()
        pts = [c] + [c.lerp(v.co, 0.9) for v in f.verts]
        hidden = True
        for p in pts:
            q = mw @ p + n * 0.01
            hit, loc, hn, idx, ho, _ = scene.ray_cast(dg, q, n, distance=0.45)
            if not hit or ho == o and (loc - q).length > 0.44:
                hidden = False; break
        if hidden: dead.append(f)
    culled += len(dead)
    bmesh.ops.delete(bm, geom=dead, context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(o.data); bm.free()
print('CULLED', culled)
for o in [o for o in LMO if not o.data.polygons]:
    o['nz'] = 'context'
LMO = [o for o in LMO if o.data.polygons]

# ---------------------------------------------------------------- lightmap: each object unwrapped and baked on its own,
# then shelf-packed into one atlas with its UVs moved to match
PPM = cfg.get('lm_ppm', 10)  # texels per metre
scene.tool_settings.use_uv_select_sync = True
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = cfg.get('bake_samples', 256)
scene.cycles.use_denoising = False
scene.render.bake.margin = 4
scene.render.bake.margin_type = 'EXTEND'
scene.render.bake.use_clear = True

def areas(o):
    s3 = o.matrix_world.to_scale()
    return sum(p.area for p in o.data.polygons) * abs(s3.x * s3.y * s3.z) ** (2 / 3)


def shelf(sizes):
    # tallest first, left to right in rows
    order = sorted(range(len(sizes)), key=lambda i: -sizes[i])
    x = y = h = 0
    at = {}
    for i in order:
        sz = sizes[i]
        if x + sz > LM_SIZE: x, y, h = 0, y + h, 0
        at[i] = (x, y)
        x += sz; h = max(h, sz)
    return at, y + h


def tile_sizes(ppm):
    # the packer fills about two thirds of each square
    return [(int(min(2048, max(32, math.sqrt(areas(o) / 0.66) * ppm))) + 7) // 8 * 8 for o in LMO]


# the densest texel rate whose tiles still fit the atlas
while True:
    SIZES = tile_sizes(PPM)
    PLACE, used = shelf(SIZES)
    if used <= LM_SIZE: break
    PPM *= 0.96
print('LM texels per metre', round(PPM, 2), 'rows', used)
tiles = []
for o, size in zip(LMO, SIZES):
    me = o.data
    uv = me.uv_layers.get('LM') or me.uv_layers.new(name='LM')
    me.uv_layers.active = uv
    select([o])
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    # islands 3 texels apart: bilinear taps and the first mip stay on their own island
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, rotate_method='AXIS_ALIGNED', margin_method='FRACTION', margin=3 / size, shape_method='AABB')
    bpy.ops.object.mode_set(mode='OBJECT')
    im = bpy.data.images.new('LM_' + o.name, size, size, float_buffer=True, alpha=False)
    for m in me.materials:
        nt = m.node_tree
        n = nt.nodes.get('BAKE') or nt.nodes.new('ShaderNodeTexImage')
        n.name = 'BAKE'; n.image = im; nt.nodes.active = n
    uv.active_render = True
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'DIRECT', 'INDIRECT'}, margin=4, use_clear=True, target='IMAGE_TEXTURES')
    me.uv_layers[0].active_render = True
    a_ = np.empty(size * size * 4, dtype=np.float32); im.pixels.foreach_get(a_)
    tiles.append((o, size, a_.reshape(size, size, 4)))
    print('BAKED', o.name, size, 'max', round(float(a_.max()), 3))
for m in bpy.data.materials:
    if m.node_tree and m.node_tree.nodes.get('BAKE'): m.node_tree.nodes.remove(m.node_tree.nodes['BAKE'])

place = PLACE
atlas_px = np.zeros((LM_SIZE, LM_SIZE, 4), dtype=np.float32); atlas_px[..., 3] = 1
for i, (o, sz, px) in enumerate(tiles):
    ox, oy = place[i]
    atlas_px[oy:oy + sz, ox:ox + sz] = px
    uv = o.data.uv_layers['LM']
    a_ = np.empty(len(uv.data) * 2, dtype=np.float32); uv.data.foreach_get('uv', a_); a_ = a_.reshape(-1, 2)
    a_ = (np.array([ox, oy]) + a_ * sz) / LM_SIZE
    uv.data.foreach_set('uv', a_.astype(np.float32).ravel())
print('ATLAS used rows', used, 'of', LM_SIZE)
atlas = bpy.data.images.new('LMATLAS', LM_SIZE, LM_SIZE, float_buffer=True, alpha=False)
atlas.pixels.foreach_set(atlas_px.ravel())
atlas.filepath_raw = f'{BUILD}/lm_raw.exr'; atlas.file_format = 'OPEN_EXR'; atlas.save()


def denoise(src, name):
    """OIDN through the compositor of an empty scene; the bake comes back without its sampling noise."""
    sc = bpy.data.scenes.new('dn_' + name)
    sc.render.resolution_x, sc.render.resolution_y = src.size
    sc.render.resolution_percentage = 100
    sc.render.engine = 'BLENDER_WORKBENCH'
    cam = bpy.data.objects.new('dncam', bpy.data.cameras.new('dncam')); sc.collection.objects.link(cam); sc.camera = cam
    tree = bpy.data.node_groups.new('dn_' + name, 'CompositorNodeTree')
    tree.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    im = tree.nodes.new('CompositorNodeImage'); im.image = src
    dn = tree.nodes.new('CompositorNodeDenoise')
    for k in ('use_hdr',):
        if hasattr(dn, k): setattr(dn, k, True)
    if 'HDR' in dn.inputs: dn.inputs['HDR'].default_value = True
    out = tree.nodes.new('NodeGroupOutput')
    tree.links.new(im.outputs['Image'], dn.inputs['Image'])
    tree.links.new(dn.outputs['Image'], out.inputs[0])
    sc.compositing_node_group = tree
    sc.render.use_compositing = True
    sc.render.image_settings.file_format = 'OPEN_EXR'
    sc.render.image_settings.color_depth = '32'
    sc.render.filepath = f'{BUILD}/{name}_dn.exr'
    bpy.ops.render.render(scene=sc.name, write_still=True)
    out_img = bpy.data.images.load(f'{BUILD}/{name}_dn.exr')
    return out_img


def pixels(im):
    a = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    return a.reshape(im.size[1], im.size[0], 4)


def log_png(arr, path):
    """Light as 8-bit RGB with no alpha (a browser premultiplies an alpha channel and would crush RGBM's darks):
    e = log2(1 + v / LOG_K) / LOG_N per channel, read back as LOG_K * (exp2(e * LOG_N) - 1)."""
    rgb = np.clip(arr[..., :3], 0, LOG_MAX)
    enc = np.log2(1 + rgb / LOG_K) / LOG_N
    h, w = arr.shape[:2]
    out = np.concatenate([enc, np.ones((h, w, 1), dtype=np.float32)], axis=2)
    im = bpy.data.images.new(os.path.basename(path), w, h, alpha=False, float_buffer=False)
    im.colorspace_settings.name = 'Non-Color'
    im.pixels.foreach_set(out.astype(np.float32).ravel())
    im.filepath_raw = path; im.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    im.save()


lm = pixels(denoise(atlas, 'lm'))
print('LM stats p50/p99/max', [round(float(np.percentile(lm[..., :3].max(axis=2), q)), 3) for q in (50, 99, 99.9)], float(lm[..., :3].max()))
log_png(lm, f'{BUILD}/lightmap.png')

# ---------------------------------------------------------------- the light at street level, top down
R = L['district']['region']
PPM = cfg.get('ground_ppm', 4)
gw, gh = int((R['x1'] - R['x0']) * PPM), int((R['z1'] - R['z0']) * PPM)
bm = bmesh.new()
# game (x0, z0) at uv (0, 0); rows run with +z like the game's own lightmap canvas
corners = [(R['x0'], R['z0']), (R['x1'], R['z0']), (R['x1'], R['z1']), (R['x0'], R['z1'])]
vs = [bm.verts.new((x - OX, -(z - OZ), 0.3)) for x, z in corners]
f = bm.faces.new(vs)
uvl = bm.loops.layers.uv.new('UVMap')
for l, uv in zip(f.loops, [(0, 0), (1, 0), (1, 1), (0, 1)]): l[uvl].uv = uv
bm.normal_update()
if f.normal.z < 0: f.normal_flip()
probe_me = bpy.data.meshes.new('probe'); bm.to_mesh(probe_me); bm.free()
probe = bpy.data.objects.new('probe', probe_me); scene.collection.objects.link(probe)
gimg = bpy.data.images.new('GROUND', gw, gh, float_buffer=True, alpha=False)
pm = bpy.data.materials.new('probe'); pm.use_nodes = True
pn = pm.node_tree.nodes.new('ShaderNodeTexImage'); pn.image = gimg; pm.node_tree.nodes.active = pn
probe_me.materials.append(pm)
select([probe])
bpy.ops.object.bake(type='DIFFUSE', pass_filter={'DIRECT', 'INDIRECT'}, margin=2, use_clear=True, target='IMAGE_TEXTURES')
ground = pixels(denoise(gimg, 'ground'))
log_png(ground, f'{BUILD}/ground.png')
bpy.data.objects.remove(probe)
print('GROUND', gw, gh, 'p50/p99', [round(float(np.percentile(ground[..., :3].max(axis=2), q)), 3) for q in (50, 99)])


def sample(arr, u, v):
    h, w = arr.shape[:2]
    x = min(max(u * w - 0.5, 0), w - 1.001); y = min(max(v * h - 0.5, 0), h - 1.001)
    x0, y0 = int(x), int(y); fx, fy = x - x0, y - y0
    c = arr[y0, x0, :3] * (1 - fx) * (1 - fy) + arr[y0, x0 + 1, :3] * fx * (1 - fy) + arr[y0 + 1, x0, :3] * (1 - fx) * fy + arr[y0 + 1, x0 + 1, :3] * fx * fy
    return [round(float(v), 4) for v in c]


def ground_at(gx, gz):
    return sample(ground, (gx - R['x0']) / (R['x1'] - R['x0']), (gz - R['z0']) / (R['z1'] - R['z0']))


# ---------------------------------------------------------------- props: placements and the light on them
dg = bpy.context.evaluated_depsgraph_get()
props = {}
for o in tagged('prop:'):
    kind = o['nz'][5:]
    mw = o.matrix_world
    p = mw.translation
    g = game(p)
    th = math.atan2(mw[1][0], mw[0][0])
    irr = None
    if kind.startswith('exterior_aircon_unit'):
        # read the wall behind it
        d = o.data['size'][1] if 'size' in o.data else 0.4
        h = o.data['size'][2] if 'size' in o.data else 0.8
        inward = (mw.to_3x3() @ Vector((0, 1, 0))).normalized()
        q = mw @ Vector((0, d / 2 + 0.01, h / 2))
        hit, loc, hn, idx, ho, hm = scene.ray_cast(dg, q, inward, distance=1.0)
        if hit and ho.get('nz') == 'lm':
            me = ho.data
            poly = me.polygons[idx]
            co = [ho.matrix_world @ me.vertices[v].co for v in poly.vertices]
            w = poly_3d_calc(co, loc)
            uvs = [me.uv_layers['LM'].data[li].uv for li in poly.loop_indices]
            u = sum(wi * uv.x for wi, uv in zip(w, uvs)); v = sum(wi * uv.y for wi, uv in zip(w, uvs))
            irr = sample(lm, u, v)
    if irr is None: irr = ground_at(g[0], g[2])
    props.setdefault(kind, []).append([round(g[0], 3), round(g[1], 3), round(g[2], 3), round(th, 4), *irr])
print('PROPS', {k: len(v) for k, v in props.items()})

# ---------------------------------------------------------------- props.glb: one mesh per kind at the origin, with LODs
# full detail up close; the decimated levels only ever stand in at distance
LODS = [1.0, 0.18, 0.04]
pc = bpy.data.collections.new('propsx'); scene.collection.children.link(pc)
pobs = []
for kind in props:
    src = next(o for o in tagged('prop:') if o['nz'] == 'prop:' + kind).data
    for i, r in enumerate(LODS):
        ob = bpy.data.objects.new(f'{kind}_lod{i}', src.copy()); pc.objects.link(ob)
        ob['nz'] = ''
        if r < 1:
            md = ob.modifiers.new('dec', 'DECIMATE'); md.ratio = r; md.use_collapse_triangulate = True
        pobs.append(ob)
select(pobs)
bpy.ops.export_scene.gltf(filepath=f'{BUILD}/props.glb', export_format='GLB', use_selection=True, export_extras=True,
                          export_yup=True, export_apply=True, export_image_format='AUTO')
print('EXPORTED props', [(o.name, len(o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.polygons)) for o in pobs])
for o in pobs: bpy.data.objects.remove(o)


# ---------------------------------------------------------------- district.glb: static geometry merged per material
def strip_ph(objs):
    """Materials built from Poly Haven sets go out as plain factors with their recipe in extras; the game rebuilds
    them from its own texture copies."""
    for o in objs:
        for m in o.data.materials:
            if not m or 'nz_tex' not in m or m.get('nz_done'): continue
            nt = m.node_tree
            for n in [n for n in nt.nodes if n.type not in ('BSDF_PRINCIPLED', 'OUTPUT_MATERIAL')]: nt.nodes.remove(n)
            bs = nt.nodes['Principled BSDF']
            bs.inputs['Base Color'].default_value = (*m['nz_tint'], 1)
            bs.inputs['Roughness'].default_value = 0.8
            m['nz_done'] = 1


def merged(objs, name):
    copies = []
    for o in objs:
        c = o.copy(); c.data = o.data.copy(); scene.collection.objects.link(c)
        copies.append(c)
    select(copies)
    bpy.ops.object.make_single_user(object=True, obdata=True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    return ob


# windows: each pane gets its own frame, metres across and up from its lower left corner (WIN) and its size (WSZ),
# for the room the game draws behind the glass
for o in LMO:
    me = o.data
    win = me.uv_layers.new(name='WIN'); wsz = me.uv_layers.new(name='WSZ')
    mw = o.matrix_world
    nm = mw.to_3x3().inverted().transposed()
    glass = {i for i, m in enumerate(me.materials) if m and m.name.startswith('glass_')}
    for poly in me.polygons:
        if poly.material_index not in glass: continue
        n = (nm @ poly.normal).normalized()
        t = Vector((0, 0, 1)).cross(n).normalized()
        pts = [mw @ me.vertices[v].co for v in poly.vertices]
        us = [p.dot(t) for p in pts]; vs = [p.z for p in pts]
        u0, v0, w, h = min(us), min(vs), max(us) - min(us), max(vs) - min(vs)
        for li, u, v in zip(poly.loop_indices, us, vs):
            win.data[li].uv = (u - u0, v - v0)
            wsz.data[li].uv = (w, h)

SELF = tagged('self')
strip_ph(LMO + SELF)
lm_all = merged(LMO, 'district_lm')
self_all = merged(SELF, 'district_self')
for ob in (lm_all, self_all):
    ob.data.uv_layers.active = ob.data.uv_layers[0]
select([lm_all, self_all])
bpy.ops.export_scene.gltf(filepath=f'{BUILD}/district.glb', export_format='GLB', use_selection=True, export_extras=True,
                          export_yup=True, export_texcoords=True, export_normals=True, export_tangents=False,
                          export_image_format='AUTO', export_apply=True)
print('TRIS lm', sum(len(p.vertices) - 2 for p in lm_all.data.polygons), 'self', sum(len(p.vertices) - 2 for p in self_all.data.polygons))

# ---------------------------------------------------------------- district.json
hero = sorted({int(o.name.split('_')[1]) for o in LMO if o.name.split('_')[0] in ('ten', 'gfbox', 'proc', 'back')})
COLL = bpy.app.driver_namespace.get('nz_colliders', [])
json.dump({
    'origin': [OX, OZ],
    'region': R,
    'hero': hero,
    'corridor': {'x0': -756.0, 'x1': -734.9, 'z0': R['z0'], 'z1': R['z1']},
    'lightmap': {'size': LM_SIZE, 'k': LOG_K, 'n': LOG_N},
    'ground': {'w': gw, 'h': gh, 'k': LOG_K, 'n': LOG_N},
    'colliders': COLL,
    'props': props,
}, open(SRC, 'w'), separators=(',', ':'))
print('WROTE', SRC, 'colliders', len(COLL))
