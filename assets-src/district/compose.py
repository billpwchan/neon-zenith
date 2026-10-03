# Temple Street slice: the street the market dash starts on, built by hand from high-detail kits instead of the
# procedural boxes, then lit by its own neon, shop and street lights. The lots come from the game's layout
# (layout.json, dumped from the running city) so the slice drops into the same streets.
# blender -b --python compose.py -- cfg.json
#   cfg: origin [x, z] in game metres, out (.blend), renders [{name, pos, dir, fov}] in game coordinates
# Blender is z-up with y = -game z; G() converts a game point.
import bpy, bmesh, json, math, random, sys, os
from mathutils import Vector, Matrix

# run from the repository root
ROOT = os.environ.get('NZ_ROOT', os.getcwd())
A = f'{ROOT}/assets-src'
cfg = json.load(open(sys.argv[sys.argv.index('--') + 1]))
L = json.load(open(f'{A}/district/layout.json'))
OX, OZ = cfg['origin']
rng = random.Random(cfg.get('seed', 7))


def G(x, y, z):
    return Vector((x - OX, -(z - OZ), y))


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def coll(name, hidden=False):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in scene.collection.children: scene.collection.children.link(c)
    c.hide_render = hidden
    c.hide_viewport = hidden
    return c


LIB = coll('lib', hidden=True)
C_GROUND, C_BLDG, C_PROPS, C_LIGHT = coll('ground'), coll('bldg'), coll('props'), coll('lights')


def link(ob, c):
    for u in list(ob.users_collection): u.objects.unlink(ob)
    c.objects.link(ob)
    return ob


# ---------------------------------------------------------------- collision
# what a vehicle can run into, as the game's axis boxes (layout.js buildCollision); the lots' own boxes are the
# game's already, so only what stands proud of them is recorded here
COLLIDERS = []


def collide(M, lo, hi, kind, solid=False):
    pts = [M @ Vector((x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    gx = [p.x + OX for p in pts]; gz = [-p.y + OZ for p in pts]; gy = [p.z for p in pts]
    c = {'x0': min(gx), 'x1': max(gx), 'y0': min(gy), 'y1': max(gy), 'z0': min(gz), 'z1': max(gz), 'kind': kind}
    if solid: c['solid'] = True
    if kind == 'sign': c['sign'] = 1
    COLLIDERS.append({k: round(v, 3) if isinstance(v, float) else v for k, v in c.items()})


# ---------------------------------------------------------------- materials
_mats = {}


def img(path, noncolor=False):
    im = bpy.data.images.load(path, check_existing=True)
    if noncolor: im.colorspace_settings.name = 'Non-Color'
    return im


def pbr(ph_id, tint=None, rough_mul=1.0):
    """Poly Haven texture set as a glTF-friendly principled material (base colour, ORM, normal)."""
    key = (ph_id, tint, rough_mul)
    if key in _mats: return _mats[key]
    d = f'{A}/ph/{ph_id}/textures'
    files = os.listdir(d)
    f = lambda tag: next((f'{d}/{x}' for x in files if f'_{tag}_' in x), None)
    m = bpy.data.materials.new(ph_id)
    m['nz_tex'] = ph_id
    m['nz_tint'] = list(tint) if tint else [1.0, 1.0, 1.0]
    m.use_nodes = True
    nt = m.node_tree
    bs = nt.nodes['Principled BSDF']
    uv = nt.nodes.new('ShaderNodeUVMap'); uv.uv_map = 'UVMap'
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = img(f('diff'))
    nt.links.new(uv.outputs[0], t.inputs[0])
    if tint:
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'; mix.inputs[0].default_value = 1
        nt.links.new(t.outputs[0], mix.inputs[6]); mix.inputs[7].default_value = (*tint, 1)
        nt.links.new(mix.outputs[2], bs.inputs['Base Color'])
    else:
        nt.links.new(t.outputs[0], bs.inputs['Base Color'])
    if f('arm'):
        a = nt.nodes.new('ShaderNodeTexImage'); a.image = img(f('arm'), True)
        nt.links.new(uv.outputs[0], a.inputs[0])
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(a.outputs[0], sep.inputs[0])
        nt.links.new(sep.outputs[1], bs.inputs['Roughness'])
        nt.links.new(sep.outputs[2], bs.inputs['Metallic'])
    if f('nor_gl'):
        n = nt.nodes.new('ShaderNodeTexImage'); n.image = img(f('nor_gl'), True)
        nt.links.new(uv.outputs[0], n.inputs[0])
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nt.links.new(n.outputs[0], nm.inputs[1])
        nt.links.new(nm.outputs[0], bs.inputs['Normal'])
    _mats[key] = m
    return m


def flat(name, color, rough=0.6, metal=0.0, emit=None, strength=0.0):
    if name in _mats: return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bs = m.node_tree.nodes['Principled BSDF']
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = rough
    bs.inputs['Metallic'].default_value = metal
    if emit:
        bs.inputs['Emission Color'].default_value = (*emit, 1)
        bs.inputs['Emission Strength'].default_value = strength
    _mats[name] = m
    return m


# ---------------------------------------------------------------- meshes
def planar_uv(bm, tile):
    """World-metre UVs by dominant axis, so every tiling texture keeps its real scale."""
    uvl = bm.loops.layers.uv.get('UVMap') or bm.loops.layers.uv.new('UVMap')
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            co = l.vert.co
            u, v = (co.y, co.z) if ax == 0 else (co.x, co.z) if ax == 1 else (co.x, co.y)
            l[uvl].uv = (u / tile, v / tile)


def box(name, lo, hi, mat, c, tile=2.0, faces='all'):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector((lo[i] + (v.co[i] + 0.5) * (hi[i] - lo[i]) for i in range(3)))
    if faces != 'all':
        dead = [f for f in bm.faces if not faces(f.normal)]
        bmesh.ops.delete(bm, geom=dead, context='FACES')
    planar_uv(bm, tile)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    return ob


# ---------------------------------------------------------------- asset library
def load(key, rel):
    """Import a glTF into the hidden library as one joined mesh in its own space."""
    ob = bpy.data.objects.get('LIB_' + key)
    if ob: return ob
    before = set(o.name for o in bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f'{A}/{rel}')
    new = [o.name for o in bpy.data.objects if o.name not in before]
    meshes = [bpy.data.objects[n] for n in new if bpy.data.objects[n].type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes: o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.make_single_user(object=True, obdata=True)
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(meshes) > 1: bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    for n in new:
        o = bpy.data.objects.get(n)
        if o and o != ob: bpy.data.objects.remove(o)
    ob.name = 'LIB_' + key
    link(ob, LIB)
    return ob


def wall_plane(me, axis=1, sign=-1):
    """The main wall of a facade: the most common depth among faces looking out of its front."""
    hist = {}
    for p in me.polygons:
        if p.normal[axis] * sign > 0.9:
            k = round(p.center[axis], 1)
            hist[k] = hist.get(k, 0) + p.area
    return max(hist, key=hist.get)


# per asset: file, uniform scale to metres, the stand or ground plate to cut off its foot (zcut), the span of its
# frontage that is all building (xr), and where its first floor starts above the cut (gf): below that the lot gets
# the shop pack's fronts, which hold up close where a 2K scan of a whole tower does not
ASSETS = {
    'kwc': {'rel': 'sf2/kwc/scene.gltf', 'scale': 20.0, 'zcut': 0.45, 'xr': (1.5, 26.3), 'gf': 3.2},
    'slum2': {'rel': 'sf2/slum2/scene.gltf', 'scale': 15.0, 'zcut': 1.0, 'xr': (0.6, 11.4), 'gf': 3.3},
    'proc': {'rel': 'sketchfab/proc.glb', 'scale': 3.1, 'zcut': 0.95, 'xr': (0.7, 24.1), 'gf': 3.6},
}
GF = 3.6  # every lot's ground floor: shops to 3.0 m, the lightbox fascia above


def facade_asset(key):
    """The asset in metres: front wall on y = 0, left edge on x = 0, its first floor at z = GF; the ground floor
    and whatever stood under it are gone."""
    ob = bpy.data.objects.get('FAC_' + key)
    if ob: return ob
    a = ASSETS[key]
    src = load(key, a['rel'])
    me = src.data.copy()
    me.transform(Matrix.Scale(a['scale'], 4))
    xs = [v.co.x for v in me.vertices]; zs = [v.co.z for v in me.vertices]
    wy = wall_plane(me)
    me.transform(Matrix.Translation((-min(xs), -wy, -min(zs) - a['zcut'] - a['gf'] + GF)))
    crop(me, a['xr'][0], a['xr'][1], z0=GF)
    me.transform(Matrix.Translation((-a['xr'][0], 0, 0)))
    ob = bpy.data.objects.new('FAC_' + key, me)
    LIB.objects.link(ob)
    xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
    ob['w'], ob['d'], ob['h'] = a['xr'][1] - a['xr'][0], max(ys), max(zs)
    print('FACADE', key, 'w', round(ob['w'], 1), 'd', round(ob['d'], 1), 'h', round(ob['h'], 1), 'proud', round(min(ys), 2))
    return ob


def crop(me, x0, x1, z0=None, z1=None):
    bm = bmesh.new(); bm.from_mesh(me)
    cuts = [((x0, 0, 0), (1, 0, 0)), ((x1, 0, 0), (1, 0, 0))]
    if z0 is not None: cuts.append(((0, 0, z0), (0, 0, 1)))
    if z1 is not None: cuts.append(((0, 0, z1), (0, 0, 1)))
    for co, no in cuts:
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=co, plane_no=no)
    def keep(f):
        c = f.calc_center_median()
        return x0 - 1e-3 <= c.x <= x1 + 1e-3 and (z0 is None or c.z >= z0 - 1e-3) and (z1 is None or c.z <= z1 + 1e-3)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(f)], context='FACES')
    bm.to_mesh(me); bm.free()


# ---------------------------------------------------------------- part assembly
def box_me(lo, hi, tile=1.0, faces='all'):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector((lo[i] + (v.co[i] + 0.5) * (hi[i] - lo[i]) for i in range(3)))
    if faces != 'all':
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if not faces(f.normal)], context='FACES')
    planar_uv(bm, tile)
    me = bpy.data.meshes.new('box'); bm.to_mesh(me); bm.free()
    return me


def assemble(name, parts, c, mw=Matrix()):
    """One object from (mesh, matrix, material) parts; the part meshes are consumed."""
    mats, bm = [], bmesh.new()
    for pme, pm, mat in parts:
        if mat not in mats: mats.append(mat)
        pme.transform(pm)
        n0 = len(bm.faces)
        bm.from_mesh(pme)
        bm.faces.ensure_lookup_table()
        for f in bm.faces[n0:]: f.material_index = mats.index(mat)
        bpy.data.meshes.remove(pme)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(m)
    ob = bpy.data.objects.new(name, me); c.objects.link(ob)
    ob.matrix_world = mw
    return ob


def lib_mesh(key, rel, scale=1.0, rot=None):
    """A copy of a library asset's mesh in metres, standing on z = 0, centred on x and y."""
    src = load(key, rel)
    me = src.data.copy()
    if rot: me.transform(rot)
    me.transform(Matrix.Scale(scale, 4))
    xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
    me.transform(Matrix.Translation((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs))))
    return me


# ---------------------------------------------------------------- lettering
# Chiron Hei HK (OFL, Hong Kong glyph forms): medium for raised letters, regular for neon, whose tube runs
# along each outline and wants thinner strokes
FONTS = {
    'hei': bpy.data.fonts.load(f'{A}/fonts/ChironHeiHK-M.ttf'),
    'neon': bpy.data.fonts.load(f'{A}/fonts/ChironHeiHK-R.ttf'),
}
# Blender sizes a font by its whole bounding box, which Chiron's widest glyphs make tall; these bring the CJK glyphs
# back to the height the signs were laid out for (measured on 鐘錶 against STHeiti and Hiragino)
FONT_SCALE = {'hei': 2.66, 'neon': 2.34}


def glyphs(text, size, mode, vertical=False, font='hei'):
    """Lettering as a mesh in font space (x right, y up, facing +z): 'tube' bends neon along every outline,
    'raised' extrudes the letters."""
    cu = bpy.data.curves.new('g', 'FONT')
    cu.font = FONTS[font]; cu.size = size * FONT_SCALE[font]; cu.resolution_u = 3
    cu.body = '\n'.join(text) if vertical else text
    cu.align_x = 'CENTER'; cu.align_y = 'CENTER'
    # line advance is space_line × size, so it takes the font scale back out
    if vertical: cu.space_line = 0.82 / FONT_SCALE[font]
    ob = bpy.data.objects.new('g', cu); scene.collection.objects.link(ob)
    if mode == 'tube':
        bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
        bpy.ops.object.convert(target='CURVE')
        ob.data.dimensions = '3D'; ob.data.bevel_depth = size * 0.02; ob.data.bevel_resolution = 1
        ob.data.resolution_u = 2; ob.data.fill_mode = 'FULL'
    else:
        cu.extrude = size * 0.035
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(ob)
    return me


def tube_path(points, r, closed=False):
    cu = bpy.data.curves.new('t', 'CURVE'); cu.dimensions = '3D'
    sp = cu.splines.new('POLY'); sp.points.add(len(points) - 1)
    for p, q in zip(sp.points, points): p.co = (*q, 1)
    sp.use_cyclic_u = closed
    cu.bevel_depth = r; cu.bevel_resolution = 0; cu.fill_mode = 'FULL'
    ob = bpy.data.objects.new('t', cu); scene.collection.objects.link(ob)
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(ob)
    return me


def face_to(origin, right, up):
    """Font space onto a board face: x along `right`, y along `up`, z out of the face."""
    out = right.cross(up)
    return Matrix(((right.x, up.x, out.x, origin.x), (right.y, up.y, out.y, origin.y), (right.z, up.z, out.z, origin.z), (0, 0, 0, 1)))


# palette: the street keeps to warm reds and ambers with cyan for contrast, as a Night City block keeps to two
NEON = [((1.0, 0.06, 0.2), 5), ((1.0, 0.4, 0.06), 4), ((0.06, 0.75, 1.0), 4), ((1.0, 0.82, 0.62), 1.5), ((1.0, 0.1, 0.55), 1)]


def neon_color():
    return rng.choices([c for c, _ in NEON], [w for _, w in NEON])[0]


def neon_mat(col, strength=45.0):
    return flat(f'neon_{col}_{strength}', (0.05, 0.05, 0.05), rough=0.25, emit=col, strength=strength)


NAMES_V = ['茶餐廳', '大押', '酒家', '麻雀耍樂', '時鐘酒店', '跌打', '涼茶', '金行', '藥房', '按摩', '海鮮', '粥麵', '燒臘',
           '找換', '旅館', '賓館', '雀館', '冰室', '鐘錶', '眼鏡', '夜總會', '卡拉OK', '居酒屋', '拉麵', '五金', '電器', '珠寶']
NAMES_H = ['HOTEL', 'KARAOKE', 'BAR', 'MASSAGE', 'NOODLES', 'OPEN 24H', 'カラオケ', 'ラーメン', '麻雀', '桑拿', 'CLUB', 'LIVE']


# ---------------------------------------------------------------- ground
def wet(m, dark=0.55, scale=0.08, puddle=0.55):
    """After rain: the surface darkens and its roughness drops to near mirror in the low patches."""
    nt = m.node_tree
    bs = nt.nodes['Principled BSDF']
    co = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = scale; nz.inputs['Detail'].default_value = 6; nz.inputs['Roughness'].default_value = 0.6
    nt.links.new(co.outputs['Object'], nz.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeMapRange'); ramp.inputs['From Min'].default_value = puddle - 0.09; ramp.inputs['From Max'].default_value = puddle + 0.06
    nt.links.new(nz.outputs['Fac'], ramp.inputs['Value'])
    r_src = bs.inputs['Roughness'].links[0].from_socket if bs.inputs['Roughness'].links else None
    mr = nt.nodes.new('ShaderNodeMath'); mr.operation = 'MULTIPLY'; mr.inputs[1].default_value = 0.3
    if r_src: nt.links.new(r_src, mr.inputs[0])
    else: mr.inputs[0].default_value = bs.inputs['Roughness'].default_value
    lerp = nt.nodes.new('ShaderNodeMix'); lerp.data_type = 'FLOAT'
    nt.links.new(ramp.outputs[0], lerp.inputs[0]); nt.links.new(mr.outputs[0], lerp.inputs[2]); lerp.inputs[3].default_value = 0.04
    nt.links.new(lerp.outputs[0], bs.inputs['Roughness'])
    c_src = bs.inputs['Base Color'].links[0].from_socket
    dk = nt.nodes.new('ShaderNodeMix'); dk.data_type = 'RGBA'; dk.blend_type = 'MULTIPLY'
    nt.links.new(ramp.outputs[0], dk.inputs[0]); nt.links.new(c_src, dk.inputs[6]); dk.inputs[7].default_value = (0.55, 0.55, 0.55, 1)
    base = nt.nodes.new('ShaderNodeMix'); base.data_type = 'RGBA'; base.blend_type = 'MULTIPLY'; base.inputs[0].default_value = 1
    nt.links.new(dk.outputs[2], base.inputs[6]); base.inputs[7].default_value = (dark, dark, dark, 1)
    nt.links.new(base.outputs[2], bs.inputs['Base Color'])
    return m


def ground():
    R = L['region']
    road = wet(pbr('asphalt_04').copy(), dark=0.42, scale=0.32, puddle=0.6)
    walk = wet(pbr('square_concrete_pavers').copy(), dark=0.4, scale=0.4, puddle=0.64)
    kerb = pbr('brushed_concrete', tint=(0.5, 0.5, 0.5))
    lo, hi = G(R['x0'], 0, R['z1']), G(R['x1'], 0, R['z0'])
    box('road', (lo.x, lo.y, -0.3), (hi.x, hi.y, 0), road, C_GROUND, tile=4.0, faces=lambda n: n.z > 0.5)
    for b in L['blocks']:
        p0, p1 = G(b['x0'], 0, b['z1']), G(b['x1'], 0, b['z0'])
        box('walk', (p0.x, p0.y, 0), (p1.x, p1.y, 0.18), walk, C_GROUND, tile=1.8, faces=lambda n: n.z > 0.5)
        box('kerb', (p0.x, p0.y, 0), (p1.x, p1.y, 0.18), kerb, C_GROUND, tile=1.0, faces=lambda n: abs(n.z) < 0.5)
    # lane lines: the yellow no-stopping lines along both kerbs and a white dashed centre line
    yel = flat('paint_yellow', (0.75, 0.55, 0.08), rough=0.55)
    wht = flat('paint_white', (0.8, 0.8, 0.78), rough=0.55)
    for x in (-752.47 + 0.35, -738.47 - 0.35):
        for dx in (-0.09, 0.09):
            a, b = G(x + dx - 0.05, 0, -96), G(x + dx + 0.05, 0, -330)
            box('line', (a.x, a.y, 0), (b.x, b.y, 0.004), yel, C_GROUND, faces=lambda n: n.z > 0.5)
    for z in range(-325, -100, 6):
        a, b = G(-745.47 - 0.06, 0, z), G(-745.47 + 0.06, 0, z + 3)
        box('dash', (a.x, b.y, 0), (b.x, a.y, 0.004), wht, C_GROUND, faces=lambda n: n.z > 0.5)


# ---------------------------------------------------------------- lots
def lots():
    """Every building of the slice region; the ones on the hero street get their street line: front centre,
    outward normal (Blender xy) and frontage."""
    out = []
    for b in L['buildings']:
        t = b['tiers'][0]
        x0, x1, z0, z1 = t['x0'], t['x1'], t['z0'], t['z1']
        hero = 1 if abs(x1 + 755.73) < 0.3 else 0 if -737 < x0 < -734 else None
        lot = {**b, 'hero': hero is not None, 'box': (x0, x1, z0, z1, t['y1'])}
        if hero == 1: lot.update(front=G(x1, 0.18, (z0 + z1) / 2), n=Vector((1, 0)), W=z1 - z0, D=x1 - x0)
        if hero == 0: lot.update(front=G(x0, 0.18, (z0 + z1) / 2), n=Vector((-1, 0)), W=z1 - z0, D=x1 - x0)
        if hero is not None:
            th = math.atan2(lot['n'].x, -lot['n'].y)
            right = Vector((math.cos(th), math.sin(th), 0))
            lot['M'] = Matrix.Translation(lot['front'] - right * (lot['W'] / 2)) @ Matrix.Rotation(th, 4, 'Z')
        out.append(lot)
    return out


def building(lot, key):
    """The lot's upper floors from a facade asset, cropped to its frontage, and a plain block behind."""
    fa = facade_asset(key)
    W = lot['W']
    u0 = rng.uniform(0, max(0, fa['w'] - W))
    me = fa.data.copy()
    crop(me, u0, u0 + W)
    me.transform(Matrix.Translation((-u0, 0, 0)))
    if W > fa['w']: me.transform(Matrix.Scale(W / fa['w'], 4, (1, 0, 0)))
    ob = bpy.data.objects.new(f"{key}_{lot['id']}", me); C_BLDG.objects.link(ob)
    ob.matrix_world = lot['M']
    collide(lot['M'], (0, min(v.co.y for v in me.vertices), GF), (W, 0, fa['h']), 'awning')
    shell = pbr('concrete_wall_003', tint=(0.5, 0.48, 0.46))
    if lot['D'] > fa['d'] + 0.5:
        back = assemble(f"back_{lot['id']}", [(box_me((0, fa['d'], 0), (W, lot['D'], fa['h'] * 0.97), 3.0), Matrix(), shell)], C_BLDG, lot['M'])
    # the ground floor's structure behind the shops: a slab over them and party walls
    slab = pbr('dirty_concrete', tint=(0.6, 0.58, 0.55))
    assemble(f"gfbox_{lot['id']}", [(box_me((0, 0.95, 0), (W, lot['D'], GF), 2.0), Matrix(), slab)], C_BLDG, lot['M'])
    return fa['h']


# ---------------------------------------------------------------- tenements
class Builder:
    """One mesh grown from axis boxes, quads and tubes in a lot's frame, with world-metre UVs."""
    FACES = {'x': (0, 4, 6, 2), 'X': (1, 3, 7, 5), 'y': (0, 1, 5, 4), 'Y': (2, 6, 7, 3), 'z': (0, 2, 3, 1), 'Z': (4, 5, 7, 6)}

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        self.mats = []

    def mi(self, m):
        if m not in self.mats: self.mats.append(m)
        return self.mats.index(m)

    def _uv(self, f, tile):
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            co = l.vert.co
            u, v = (co.y, co.z) if ax == 0 else (co.x, co.z) if ax == 1 else (co.x, co.y)
            l[self.uv].uv = (u / tile, v / tile)

    def box(self, lo, hi, mat, tile=1.0, drop=''):
        """An axis box; `drop` names faces to leave out: x X y Y z Z for the -x +x ... sides."""
        if min(hi[i] - lo[i] for i in range(3)) <= 1e-4: return
        v = [self.bm.verts.new((hi[0] if i & 1 else lo[0], hi[1] if i & 2 else lo[1], hi[2] if i & 4 else lo[2])) for i in range(8)]
        k = self.mi(mat)
        for key, idx in self.FACES.items():
            if key in drop: continue
            f = self.bm.faces.new([v[i] for i in idx]); f.material_index = k
            f.normal_update(); self._uv(f, tile)

    def quad(self, pts, mat, tile=1.0):
        f = self.bm.faces.new([self.bm.verts.new(p) for p in pts]); f.material_index = self.mi(mat)
        f.normal_update(); self._uv(f, tile)

    def pipe(self, x, y, z0, z1, r, mat, seg=8):
        ring0 = [self.bm.verts.new((x + r * math.cos(a), y + r * math.sin(a), z0)) for a in [i * 2 * math.pi / seg for i in range(seg)]]
        ring1 = [self.bm.verts.new((v.co.x, v.co.y, z1)) for v in ring0]
        k = self.mi(mat)
        for i in range(seg):
            j = (i + 1) % seg
            f = self.bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i])); f.material_index = k
            uvs = [(i / seg * 2 * math.pi * r, z0), (j / seg * 2 * math.pi * r if j else 2 * math.pi * r, z0), (j / seg * 2 * math.pi * r if j else 2 * math.pi * r, z1), (i / seg * 2 * math.pi * r, z1)]
            for l, uv in zip(f.loops, uvs): l[self.uv].uv = uv

    def finish(self, name, c, mw):
        bmesh.ops.delete(self.bm, geom=[v for v in self.bm.verts if not v.link_faces], context='VERTS')
        me = bpy.data.meshes.new(name); self.bm.to_mesh(me); self.bm.free()
        for m in self.mats: me.materials.append(m)
        ob = bpy.data.objects.new(name, me); c.objects.link(ob)
        ob.matrix_world = mw
        return ob


_grimed = {}


def grime(m, amount=0.5):
    """Rain streaks run down from every ledge and sill: vertical noise darkening the base colour."""
    if m.name in _grimed: return _grimed[m.name]
    m = m.copy(); m.name = m.name + '_grime'
    m['nz_grime'] = amount
    nt = m.node_tree
    bs = nt.nodes['Principled BSDF']
    co = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (5.0, 5.0, 0.22)
    nt.links.new(co.outputs['Object'], mp.inputs['Vector'])
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 1.0; nz.inputs['Detail'].default_value = 5
    nt.links.new(mp.outputs[0], nz.inputs['Vector'])
    rg = nt.nodes.new('ShaderNodeMapRange'); rg.inputs['From Min'].default_value = 0.42; rg.inputs['From Max'].default_value = 0.78
    rg.inputs['To Min'].default_value = 1.0; rg.inputs['To Max'].default_value = 1.0 - amount
    nt.links.new(nz.outputs['Fac'], rg.inputs['Value'])
    src = bs.inputs['Base Color'].links[0].from_socket
    mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.inputs[0].default_value = 1
    nt.links.new(src, mx.inputs[6]); nt.links.new(rg.outputs[0], mx.inputs[7])
    nt.links.new(mx.outputs[2], bs.inputs['Base Color'])
    _grimed[m.name[:-6]] = m
    return m


# the old tenements' skins: mosaic tile in faded pastels, or painted render
WALLS = [('rectangular_facade_tiles', (1.0, 0.82, 0.8), 1.4), ('rectangular_facade_tiles', (0.8, 0.95, 0.88), 1.4),
         ('rectangular_facade_tiles_02', (1.0, 1.0, 1.0), 1.4), ('square_tiled_wall', (0.95, 0.88, 0.75), 1.2),
         ('grey_tiles', (0.85, 0.9, 0.95), 1.2), ('dirty_tiles', (1.0, 0.92, 0.85), 1.2),
         ('painted_plaster_wall', (0.7, 0.82, 0.92), 2.5), ('peeling_painted_wall', (1.0, 0.88, 0.8), 2.5),
         ('worn_plaster_wall', (1.0, 0.93, 0.85), 2.5), ('painted_plaster_wall', (0.95, 0.75, 0.7), 2.5)]
FRAMES = [(0.72, 0.73, 0.7), (0.3, 0.45, 0.4), (0.22, 0.18, 0.15), (0.5, 0.52, 0.55), (0.6, 0.55, 0.4)]
LIT = [((1.0, 0.7, 0.4), 2.6), ((1.0, 0.8, 0.55), 1.8), ((0.75, 0.88, 1.0), 3.2), ((0.7, 0.85, 1.0), 1.8),
       ((1.0, 0.32, 0.38), 1.6), ((0.3, 0.9, 0.8), 1.3)]


def glass_mat(lit=None, k=1.0):
    if not lit: return flat('glass_dark', (0.015, 0.018, 0.022), rough=0.05)
    col, st = lit
    return flat(f'glass_{col}_{st * k:.2f}', tuple(c * 0.15 for c in col), rough=0.12, emit=col, strength=st * k)


def window(b, x0, x1, z0, z1, frame, y=0.12):
    t = 0.045
    y1 = y + 0.05
    b.box((x0, y, z0), (x1, y1, z0 + t), frame, drop='Y')
    b.box((x0, y, z1 - t), (x1, y1, z1), frame, drop='Y')
    b.box((x0, y, z0 + t), (x0 + t, y1, z1 - t), frame, drop='YzZ')
    b.box((x1 - t, y, z0 + t), (x1, y1, z1 - t), frame, drop='YzZ')
    n = 2 if x1 - x0 < 1.4 else 3 if x1 - x0 < 2.1 else 4
    for i in range(1, n):
        xm = x0 + (x1 - x0) * i / n
        b.box((xm - 0.018, y, z0 + t), (xm + 0.018, y1, z1 - t), frame, drop='YzZ')
    zt = z0 + (z1 - z0) * 0.68
    b.box((x0 + t, y, zt - 0.018), (x1 - t, y1, zt + 0.018), frame, drop='Yxz')
    gy = y + 0.035
    if rng.random() < 0.36:
        lit = rng.choice(LIT)
        cut = x0 + (x1 - x0) * rng.choice([0.0, 0.0, 0.35, 0.5, 0.65, 1.0])
        if cut > x0 + 0.05: b.quad([(x0, gy, z0), (cut, gy, z0), (cut, gy, z1), (x0, gy, z1)], glass_mat(lit))
        if cut < x1 - 0.05: b.quad([(cut, gy, z0), (x1, gy, z0), (x1, gy, z1), (cut, gy, z1)], glass_mat(lit, 0.28))
        return lit
    b.quad([(x0, gy, z0), (x1, gy, z0), (x1, gy, z1), (x0, gy, z1)], glass_mat())


_parts = {}


def lib_part(rel, name, scale=1.0):
    """One named mesh of a glTF in metres with its transform applied, standing on z = 0, centred on x and y."""
    k = (rel, name, scale)
    if k in _parts: return _parts[k]
    if rel not in _parts:
        before = set(o.name for o in bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=f'{A}/{rel}')
        _parts[rel] = [n for n in set(o.name for o in bpy.data.objects) - before]
        for n in _parts[rel]: link(bpy.data.objects[n], LIB)
    o = bpy.data.objects[name]
    me = o.data.copy(); me.transform(o.matrix_world); me.transform(Matrix.Scale(scale, 4))
    xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
    me.transform(Matrix.Translation((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs))))
    me['size'] = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    _parts[k] = me
    return me


def place(me, lot, at, c=None, rz=0.0):
    o = bpy.data.objects.new(me.name, me); (c or C_PROPS).objects.link(o)
    o.matrix_world = lot['M'] @ Matrix.Translation(at) @ Matrix.Rotation(rz, 4, 'Z')
    return o


def ac_unit(lot, x, z):
    me = lib_part('ph/exterior_aircon_unit/exterior_aircon_unit.gltf', rng.choice(['exterior_aircon_unit', 'exterior_aircon_unit_rusted']), 0.85)
    w, d, h = me['size']
    place(me, lot, (x, -0.14 - d / 2, z))
    collide(lot['M'], (x - w / 2, -0.14 - d, z), (x + w / 2, 0, z + h), 'awning')


def cage(b, x0, x1, z0, z1, rod, roof):
    """An iron window grille standing off the wall, with a corrugated hood."""
    y = -0.42
    b.box((x0, y, z0), (x1, 0, z0 + 0.04), rod, drop='Y')
    for zz in (z0 + (z1 - z0) * 0.5, z1):
        b.box((x0, y, zz - 0.015), (x1, y + 0.03, zz + 0.015), rod, drop='Y')
    n = max(3, int((x1 - x0) / 0.12))
    for i in range(n + 1):
        xx = x0 + (x1 - x0) * i / n
        b.box((xx - 0.007, y, z0), (xx + 0.007, y + 0.014, z1), rod, drop='zZY')
    for xx in (x0, x1 - 0.014):
        for zz in (z0 + (z1 - z0) * 0.5, z1):
            b.box((xx, y, zz - 0.012), (xx + 0.014, 0, zz + 0.012), rod, drop='Y')
        b.box((xx, y, z0), (xx + 0.014, y + 0.014, z1), rod, drop='Y')
    hz = z1 + 0.22
    b.quad([(x0 - 0.05, y - 0.08, z1 + 0.02), (x1 + 0.05, y - 0.08, z1 + 0.02), (x1 + 0.05, 0, hz), (x0 - 0.05, 0, hz)], roof, 1.0)
    b.quad([(x0 - 0.05, 0, hz), (x1 + 0.05, 0, hz), (x1 + 0.05, y - 0.08, z1 + 0.02), (x0 - 0.05, y - 0.08, z1 + 0.02)], roof, 1.0)


def balcony(b, x0, x1, z0, z1, wall, tile, ledge, frame):
    """An enclosed balcony: a tiled parapet and a band of windows standing out from the wall."""
    y = -0.85
    b.box((x0, y, z0), (x1, 0, z0 + 0.12), ledge, 1.5, drop='Y')
    b.box((x0, y, z0 + 0.12), (x1, y + 0.1, z0 + 1.0), wall, tile, drop='zZ')
    for xx in (x0, x1 - 0.1):
        b.box((xx, y + 0.1, z0 + 0.12), (xx + 0.1, 0, z0 + 1.0), wall, tile, drop='zZY')
    b.box((x0, y, z0 + 1.0), (x1, y + 0.12, z0 + 1.06), ledge, 1.5)
    b.box((x0, y, z1 - 0.1), (x1, 0, z1), ledge, 1.5, drop='Y')
    lit = window(b, x0 + 0.04, x1 - 0.04, z0 + 1.06, z1 - 0.1, frame, y=y + 0.02)
    for xx in (x0, x1):
        # the side panes look into the same room as the front; the draws stay so the rest of the street is unchanged
        rng.choice(LIT) if rng.random() < 0.3 else None
        g = glass_mat(lit, 0.6) if lit else glass_mat()
        b.quad([(xx, y + 0.1, z0 + 1.06), (xx, 0, z0 + 1.06), (xx, 0, z1 - 0.1), (xx, y + 0.1, z1 - 0.1)][::1 if xx == x0 else -1], g)


def tenement(lot, h, board_floor=False):
    """A Kowloon tenement above the shops: recessed steel windows in bays, a ledge at every floor, tiled or
    rendered skin streaked by rain, the households' cages, balconies and air conditioners, pipes at the party
    walls, and a roof of tanks and huts."""
    W, D = lot['W'], lot['D']
    b = Builder()
    tex, tint, tile = rng.choice(WALLS)
    wall = grime(pbr(tex, tint=tint), rng.uniform(0.35, 0.6))
    ledge = grime(pbr('dirty_concrete', tint=(0.72, 0.7, 0.68)), 0.4)
    side = grime(pbr('concrete_wall_009', tint=(0.55, 0.55, 0.56)), 0.5)
    fc = rng.choice(FRAMES)
    frame = flat(f'frame_{fc}', fc, rough=0.45, metal=0.35)
    rod = flat('rod', (0.08, 0.08, 0.075), rough=0.5, metal=0.7)
    roof = pbr('worn_corrugated_iron', tint=(0.6, 0.6, 0.6))
    pvc = flat('pvc', (0.45, 0.46, 0.45), rough=0.5)
    fh = rng.uniform(2.85, 3.05)
    nf = max(2, int((h - GF - 1.1) / fh))
    top = GF + nf * fh
    nb = max(1, round(W / rng.uniform(2.7, 3.4)))
    bw = W / nb
    ratio = rng.uniform(0.52, 0.66)
    wh = rng.uniform(1.45, 1.65)
    R = 0.2
    kinds = [rng.choices(['plain', 'ac', 'cage', 'balcony'], [3, 3, 2.5, 1.6])[0] for _ in range(nb)]
    b.box((0, R, GF), (W, D, top), side, 2.0, drop='y')
    for f in range(nf):
        z0 = GF + f * fh; z1 = z0 + fh
        b.box((0, -0.12, z0 - 0.08), (W, R, z0 + 0.1), ledge, 1.5, drop='Y')
        for k in range(nb):
            x0 = k * bw; x1 = x0 + bw
            ww = bw * ratio
            wx0 = x0 + (bw - ww) / 2; wx1 = wx0 + ww
            wz0 = z0 + 0.88; wz1 = min(wz0 + wh, z1 - 0.3)
            zb, zt = z0 + 0.1, z1 - 0.08
            b.box((x0, 0, zb), (wx0, R, zt), wall, tile, drop='xYzZ')
            b.box((wx1, 0, zb), (x1, R, zt), wall, tile, drop='XYzZ')
            b.box((wx0, 0, zb), (wx1, R, wz0), wall, tile, drop='xXYz')
            b.box((wx0, 0, wz1), (wx1, R, zt), wall, tile, drop='xXYZ')
            b.box((wx0 - 0.05, -0.06, wz0 - 0.05), (wx1 + 0.05, 0.0, wz0), ledge, 1.5, drop='Y')
            if f == 0 and board_floor:
                window(b, wx0, wx1, wz0, wz1, frame)
                continue
            kind = kinds[k] if rng.random() > 0.25 else rng.choice(['plain', 'ac', 'cage', 'balcony'])
            if kind == 'balcony':
                balcony(b, wx0 - 0.22, wx1 + 0.22, zb, zt, wall, tile, ledge, frame)
                collide(lot['M'], (wx0 - 0.22, -0.85, zb), (wx1 + 0.22, 0, zt), 'awning')
                continue
            window(b, wx0, wx1, wz0, wz1, frame)
            if kind == 'cage':
                cage(b, wx0 - 0.06, wx1 + 0.06, wz0 - 0.12, wz1 + 0.08, rod, roof)
                collide(lot['M'], (wx0 - 0.11, -0.5, wz0 - 0.12), (wx1 + 0.11, 0, wz1 + 0.3), 'awning')
            if kind == 'ac' or (kind == 'plain' and rng.random() < 0.35):
                ac_unit(lot, (wx0 + wx1) / 2 + rng.uniform(-0.15, 0.15), z0 + 0.12)
    # pipes down the party walls
    for x in (0.16, W - 0.16):
        if rng.random() < 0.7: b.pipe(x, -0.09, GF, top + 0.6, 0.05, pvc)
    # parapet and roof clutter
    b.box((0, -0.12, top - 0.08), (W, R, top + 1.1), wall, tile)
    for xx in (0, W - 0.15):
        b.box((xx, R, top), (xx + 0.15, D, top + 1.1), side, 2.0)
    b.box((0, D - 0.15, top), (W, D, top + 1.1), side, 2.0)
    if W > 5:
        hx = rng.uniform(1.0, W - 4.0)
        b.box((hx, D * 0.4, top), (hx + 3.0, D * 0.4 + 3.2, top + 2.7), side, 2.0, drop='z')
        collide(lot['M'], (hx, D * 0.4, top), (hx + 3.0, D * 0.4 + 3.2, top + 2.7), 'roof', solid=True)
        tx = rng.uniform(0.6, W - 2.6)
        b.box((tx, D * 0.15, top + 0.5), (tx + 2.0, D * 0.15 + 1.4, top + 1.9), pbr('rusty_metal_shutter', tint=(0.7, 0.7, 0.7)), 1.5)
        collide(lot['M'], (tx, D * 0.15, top), (tx + 2.0, D * 0.15 + 1.4, top + 1.9), 'roof', solid=True)
        for i in range(rng.randint(0, 3)):
            ax, ay = rng.uniform(0.5, W - 0.5), rng.uniform(1.0, D - 1.0)
            b.pipe(ax, ay, top, top + rng.uniform(2.5, 5.0), 0.025, rod, seg=6)
    ob = b.finish(f"ten_{lot['id']}", C_BLDG, lot['M'])
    # slab over the shops
    slab = pbr('dirty_concrete', tint=(0.6, 0.58, 0.55))
    assemble(f"gfbox_{lot['id']}", [(box_me((0, 0.95, 0), (W, D, GF), 2.0), Matrix(), slab)], C_BLDG, lot['M'])
    lot['piers'] = [k * bw for k in range(1, nb)]
    lot['fh'] = fh
    return top


def floor_board(lot, fh):
    """The big signboard over a tenement's first floor: a dark board, a neon name and a lit frame."""
    W = lot['W']
    col = neon_color()
    name = rng.choice([t for t in NAMES_V if len(t) <= max(2, int((W - 1.5) / 1.4))])
    size = min(fh * 0.55, (W - 1.5) / len(name))
    board = pbr('painted_metal_shutter', tint=(0.09, 0.08, 0.09))
    z0, z1 = GF + 0.25, GF + fh - 0.15
    parts = [(box_me((0.3, -0.5, z0), (W - 0.3, -0.16, z1), 1.0), Matrix(), board)]
    parts.append((glyphs(name, size, 'tube', font='neon'), Matrix.Translation((W / 2, -0.53, (z0 + z1) / 2)) @ Matrix.Rotation(math.radians(90), 4, 'X'), neon_mat(col, 50.0)))
    m = 0.12
    rect = [(0.3 + m, -0.53, z0 + m), (W - 0.3 - m, -0.53, z0 + m), (W - 0.3 - m, -0.53, z1 - m), (0.3 + m, -0.53, z1 - m)]
    parts.append((tube_path(rect, 0.02, closed=True), Matrix(), neon_mat(neon_color(), 40.0)))
    for zz in (z0 + 0.2, z1 - 0.2):
        for xx in (0.8, W - 0.8):
            parts.append((box_me((xx - 0.04, -0.16, zz - 0.04), (xx + 0.04, 0, zz + 0.04)), Matrix(), board))
    assemble(f"board_{lot['id']}", parts, C_PROPS, lot['M'])
    collide(lot['M'], (0.3, -0.56, z0), (W - 0.3, 0, z1), 'sign')
    l = bpy.data.lights.new('neon', 'AREA'); l.size = W * 0.8; l.size_y = 0.6; l.energy = 22 * W; l.color = col
    o = bpy.data.objects.new('boardlight', l); C_LIGHT.objects.link(o)
    o.matrix_world = lot['M'] @ Matrix.Translation((W / 2, -0.7, z0 - 0.1)) @ Matrix.Rotation(math.radians(-50), 4, 'X')


def tower_mat():
    """Far blocks: a concrete skin with a grid of windows, a share of them lit."""
    m = bpy.data.materials.get('tower')
    if m: return m
    m = pbr('concrete_wall_009', tint=(0.22, 0.22, 0.23)).copy(); m.name = 'tower'
    nt = m.node_tree
    bs = nt.nodes['Principled BSDF']
    uv = nt.nodes.new('ShaderNodeUVMap'); uv.uv_map = 'UVMap'
    br = nt.nodes.new('ShaderNodeTexBrick'); br.offset = 0.0; br.squash = 1.0
    br.inputs['Scale'].default_value = 1.0; br.inputs['Brick Width'].default_value = 3.1; br.inputs['Row Height'].default_value = 3.0
    br.inputs['Mortar Size'].default_value = 0.75; br.inputs['Mortar Smooth'].default_value = 0.0; br.inputs['Bias'].default_value = 0.0
    br.inputs['Color1'].default_value = (0, 0, 0, 1); br.inputs['Color2'].default_value = (1, 1, 1, 1)
    nt.links.new(uv.outputs[0], br.inputs['Vector'])
    win = nt.nodes.new('ShaderNodeMath'); win.operation = 'SUBTRACT'; win.inputs[0].default_value = 1.0
    nt.links.new(br.outputs['Fac'], win.inputs[1])
    sep = nt.nodes.new('ShaderNodeSeparateColor'); nt.links.new(br.outputs['Color'], sep.inputs[0])
    on = nt.nodes.new('ShaderNodeMath'); on.operation = 'GREATER_THAN'; on.inputs[1].default_value = 0.7
    nt.links.new(sep.outputs[0], on.inputs[0])
    lit = nt.nodes.new('ShaderNodeMath'); lit.operation = 'MULTIPLY'
    nt.links.new(win.outputs[0], lit.inputs[0]); nt.links.new(on.outputs[0], lit.inputs[1])
    warm = nt.nodes.new('ShaderNodeMix'); warm.data_type = 'RGBA'
    nt.links.new(sep.outputs[1], warm.inputs[0]); warm.inputs[6].default_value = (1.0, 0.72, 0.45, 1); warm.inputs[7].default_value = (0.7, 0.85, 1.0, 1)
    nt.links.new(warm.outputs[2], bs.inputs['Emission Color'])
    st = nt.nodes.new('ShaderNodeMath'); st.operation = 'MULTIPLY'; st.inputs[1].default_value = 2.2
    nt.links.new(lit.outputs[0], st.inputs[0]); nt.links.new(st.outputs[0], bs.inputs['Emission Strength'])
    base_src = bs.inputs['Base Color'].links[0].from_socket
    mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'
    nt.links.new(win.outputs[0], mx.inputs[0]); nt.links.new(base_src, mx.inputs[6]); mx.inputs[7].default_value = (0.01, 0.012, 0.015, 1)
    nt.links.new(mx.outputs[2], bs.inputs['Base Color'])
    rr = nt.nodes.new('ShaderNodeMix'); rr.data_type = 'FLOAT'
    r_src = bs.inputs['Roughness'].links[0].from_socket
    nt.links.new(win.outputs[0], rr.inputs[0]); nt.links.new(r_src, rr.inputs[2]); rr.inputs[3].default_value = 0.08
    nt.links.new(rr.outputs[0], bs.inputs['Roughness'])
    return m


# ---------------------------------------------------------------- shops
SHOPKIT = json.load(open(f'{ROOT}/src/city/shopkit.json'))['modules']
SHOPCFG = json.load(open(f'{A}/facade/cfg/shop_bot.json'))
_shop_lit = {}


def shop_module(name):
    """A shop front from the pack, its interiors and signs made to glow like the street strip's."""
    ob = bpy.data.objects.get('SHOP_' + name)
    if ob: return ob
    if not bpy.data.objects.get('LIB_shops'):
        before = set(o.name for o in bpy.data.objects)
        mats_before = set(m.name for m in bpy.data.materials)
        bpy.ops.import_scene.gltf(filepath=f'{A}/shopkit/raw.glb')
        for n in [o.name for o in bpy.data.objects if o.name not in before]:
            o = bpy.data.objects[n]
            if o.type == 'MESH' and o.name.startswith('S_'):
                o.name = 'SHOP_' + o.name[2:]; link(o, LIB)
        import re
        g, f = re.compile(SHOPCFG['glass']), re.compile(SHOPCFG['frame'])
        for m in [m for m in bpy.data.materials if m.name not in mats_before]:
            if not m.use_nodes: continue
            bs = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if not bs: continue
            kind = 1 if g.search(m.name) else 2 if f.search(m.name) else 0
            if kind == 0: continue
            src = bs.inputs['Base Color'].links[0].from_socket if bs.inputs['Base Color'].links else None
            if src: m.node_tree.links.new(src, bs.inputs['Emission Color'])
            bs.inputs['Emission Strength'].default_value = 3.0 if kind == 1 else 1.6
        bpy.data.objects.new('LIB_shops', None)
    return bpy.data.objects['SHOP_' + name]


def shop_variant(name, open_):
    """The module as the game shows it: interiors lit only while the shop is open, its signs dimmer once shut."""
    src = shop_module(name)
    if open_: return src.data
    key = 'SHOPX_' + name
    me = bpy.data.meshes.get(key)
    if me: return me
    me = src.data.copy(); me.name = key
    for i, m in enumerate(me.materials):
        bs = m.node_tree.nodes.get('Principled BSDF') if m.use_nodes else None
        if not bs or bs.inputs['Emission Strength'].default_value <= 0: continue
        m2 = m.copy(); m2.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value *= (0.0 if bs.inputs['Emission Strength'].default_value > 2 else 0.45)
        me.materials[i] = m2
    return me


KITW = [m['w'] for m in SHOPKIT]
KITSTART = [sum(KITW[:k]) for k in range(len(KITW))]
KITSTRIP = KITSTART[-1] + KITW[-1]


def shop_fit(seed, w):
    """shopkit.js shopFit, to the bit: the modules a shop of width w wears from its seed."""
    o = ((seed * 5.13) % 1) * KITSTRIP
    k0 = 0
    for k in range(1, len(KITW)):
        if abs(KITSTART[k] - o) < abs(KITSTART[k0] - o): k0 = k
    lst, tot = [], 0.0
    while True:
        nxt = tot + KITW[(k0 + len(lst)) % len(KITW)]
        if lst and abs(nxt - w) >= abs(tot - w): break
        lst.append((k0 + len(lst)) % len(KITW)); tot = nxt
    return lst, tot


def game_shops():
    """Every shopfront the game draws in the district, placed as shopkit.js places it, so the bake sees the same
    fronts and the same light falling out of them."""
    for i, sf in enumerate(L['district']['shopfronts']):
        lst, tot = shop_fit(sf['seed'], sf['w'])
        c, sn = math.cos(sf['rotY']), math.sin(sf['rotY'])
        nx, nz, rx, rz = sn, c, c, -sn
        lx, lz = sf['x'] - nx * 0.02 - rx * sf['w'] / 2, sf['z'] - nz * 0.02 - rz * sf['w'] / 2
        sx = sf['w'] / tot
        R = Vector((rx, -rz, 0)); N = Vector((nx, -nz, 0))
        at = 0.0
        for k in lst:
            o = G(lx + rx * at * sx, 0.2, lz + rz * at * sx)
            ob = bpy.data.objects.new(f"gshop_{i}_{k}", shop_variant(SHOPKIT[k]['name'], sf['open'])); C_BLDG.objects.link(ob)
            ob.matrix_world = Matrix(((R.x * sx, -N.x, 0, o.x), (R.y * sx, -N.y, 0, o.y), (0, 0, 1, o.z), (0, 0, 0, 1)))
            at += KITW[k]
        if sf['open']:
            l = bpy.data.lights.new('shop', 'AREA'); l.shape = 'RECTANGLE'; l.size = sf['w'] * 0.9; l.size_y = 0.5
            l.energy = 22 * sf['w']; l.color = (1.0, 0.86, 0.66) if (sf['seed'] * 7.31) % 1 < 0.45 else (0.86, 0.95, 1.0)
            o = bpy.data.objects.new('shoplight', l); C_LIGHT.objects.link(o)
            cx, cz = sf['x'] + nx * 0.7, sf['z'] + nz * 0.7
            M = Matrix(((R.x, -N.x, 0, 0), (R.y, -N.y, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
            o.matrix_world = Matrix.Translation(G(cx, 3.1, cz)) @ M @ Matrix.Rotation(math.radians(-25), 4, 'X')


def game_lamps():
    """The game's street lamps (props.js): pole, arm reaching 2.8 m over the road, sodium or LED head."""
    steel = flat('lamp_steel', (0.06, 0.065, 0.07), rough=0.45, metal=0.85)
    for i, lp in enumerate(L['district']['lamps']):
        ex, ez = lp['x'] + lp['ox'] * 2.8, lp['z'] + lp['oz'] * 2.8
        a, b = G(lp['x'] - 0.09, 0, lp['z'] + 0.09), G(lp['x'] + 0.09, 0, lp['z'] - 0.09)
        box(f'gpole_{i}', (a.x, a.y, 0.18), (b.x, b.y, 8.9), steel, C_PROPS)
        l = bpy.data.lights.new('lamp', 'SPOT'); l.energy = 300; l.spot_size = math.radians(120); l.spot_blend = 0.6; l.shadow_soft_size = 0.25
        l.color = (1.0, 0.62, 0.28) if lp['warm'] else (0.75, 0.86, 1.0)
        o = bpy.data.objects.new('lamplight', l); C_LIGHT.objects.link(o)
        o.location = G(ex, 8.5, ez)


def fascia(lot):
    W = lot['W']
    # the signboard band above the shops: a dark steel case the full width, and on it a few lightboxes of
    # different sizes and colours with the shops' names raised on them; some stay dark
    case = pbr('painted_metal_shutter', tint=(0.16, 0.15, 0.15))
    parts = [(box_me((0.05, -0.45, 3.02), (W - 0.05, -0.05, GF - 0.02), 1.0), Matrix(), case)]
    at = rng.uniform(0.2, 1.2)
    while at < W - 1.6:
        bw = min(rng.uniform(1.6, 4.2), W - 0.2 - at)
        if rng.random() < 0.72:
            panel_col, letter_col = rng.choice([((1.0, 0.92, 0.78), (0.75, 0.04, 0.03)), ((1.0, 0.82, 0.3), (0.6, 0.05, 0.02)),
                                                ((0.85, 0.08, 0.06), (1.0, 0.95, 0.75)), ((0.08, 0.5, 0.75), (1.0, 1.0, 0.95)),
                                                ((0.06, 0.06, 0.07), (1.0, 0.3, 0.08))])
            st = rng.uniform(1.2, 2.4)
            z0, z1 = 3.06 + rng.uniform(0, 0.06), GF - 0.06 - rng.uniform(0, 0.06)
            parts.append((box_me((at, -0.52, z0), (at + bw, -0.44, z1), 1.0), Matrix(), flat(f'panel_{panel_col}_{st:.1f}', panel_col, rough=0.3, emit=panel_col, strength=st)))
            name = rng.choice(NAMES_V)
            gm = glyphs(name, min((z1 - z0) * 0.8, (bw - 0.3) / max(1, len(name)) * 0.92), 'raised', font='hei')
            parts.append((gm, Matrix.Translation((at + bw / 2, -0.54, (z0 + z1) / 2)) @ Matrix.Rotation(math.radians(90), 4, 'X'),
                          flat(f'letters_{letter_col}', letter_col, rough=0.4, emit=letter_col, strength=4.0)))
        at += bw + rng.uniform(0.15, 0.9)
    assemble(f"fascia_{lot['id']}", parts, C_PROPS, lot['M'])
    collide(lot['M'], (0.05, -0.56, 3.02), (W - 0.05, 0, GF), 'sign')


# ---------------------------------------------------------------- signs
def blade(lot, at, z0, text, col, big=False):
    """A blade sign standing out from the wall: a dark board with neon lettering and a neon border on both faces."""
    s = rng.uniform(1.05, 1.35) if big else rng.uniform(0.75, 1.0)
    H = len(text) * s * 0.84 + s * 0.45
    P = s * 1.1 + 0.22
    t = 0.22
    y0, y1 = -0.35 - P, -0.35
    board = pbr('painted_metal_shutter', tint=(0.12, 0.11, 0.12))
    nm = neon_mat(col, 55.0 if big else 45.0)
    parts = [(box_me((at - t / 2, y0, z0), (at + t / 2, y1, z0 + H), 1.0), Matrix(), board)]
    for side in (1, -1):
        fx = at + side * (t / 2 + 0.035)
        right = Vector((0, side, 0))
        gm = glyphs(text, s * 0.95, 'tube', vertical=True, font='neon')
        parts.append((gm, face_to(Vector((fx, (y0 + y1) / 2, z0 + H / 2)), right, Vector((0, 0, 1))), nm))
        m = 0.09
        rect = [(fx, y0 + m, z0 + m), (fx, y1 - m, z0 + m), (fx, y1 - m, z0 + H - m), (fx, y0 + m, z0 + H - m)]
        parts.append((tube_path(rect, 0.018, closed=True), Matrix(), neon_mat(neon_color(), 40.0)))
    for zz in (z0 + 0.3, z0 + H - 0.3):
        parts.append((box_me((at - 0.04, -0.4, zz - 0.04), (at + 0.04, 0, zz + 0.04)), Matrix(), board))
    assemble(f"blade_{lot['id']}_{at:.1f}", parts, C_PROPS, lot['M'])
    collide(lot['M'], (at - t / 2 - 0.06, y0, z0), (at + t / 2 + 0.06, 0, z0 + H), 'sign')
    # what the sign throws on the wall and the street
    l = bpy.data.lights.new('neon', 'POINT'); l.energy = 110 if big else 55; l.color = col; l.shadow_soft_size = 0.5
    o = bpy.data.objects.new('neonlight', l); C_LIGHT.objects.link(o)
    o.matrix_world = lot['M'] @ Matrix.Translation((at, (y0 + y1) / 2, z0 + H / 2))


def wall_neon(lot, z, text, col):
    """Neon lettering on rails just off the wall."""
    s = rng.uniform(0.7, 1.1)
    gm = glyphs(text, s, 'tube', font='neon')
    w = max(v.co.x for v in gm.vertices) - min(v.co.x for v in gm.vertices)
    if w > lot['W'] - 1: bpy.data.meshes.remove(gm); return
    at = rng.uniform(w / 2 + 0.4, lot['W'] - w / 2 - 0.4)
    rail = pbr('rusty_metal_02', tint=(0.14, 0.14, 0.14))
    parts = [(gm, Matrix.Translation((at, -0.32, z)) @ Matrix.Rotation(math.radians(90), 4, 'X'), neon_mat(col, 45.0))]
    for zz in (z - s * 0.45, z + s * 0.45):
        parts.append((box_me((at - w / 2 - 0.1, -0.3, zz - 0.02), (at + w / 2 + 0.1, -0.02, zz + 0.02)), Matrix(), rail))
    assemble(f"wneon_{lot['id']}", parts, C_PROPS, lot['M'])
    collide(lot['M'], (at - w / 2 - 0.1, -0.4, z - s * 0.55), (at + w / 2 + 0.1, 0, z + s * 0.55), 'sign')
    l = bpy.data.lights.new('neon', 'POINT'); l.energy = 60; l.color = col; l.shadow_soft_size = 0.6
    o = bpy.data.objects.new('neonlight', l); C_LIGHT.objects.link(o)
    o.matrix_world = lot['M'] @ Matrix.Translation((at, -0.8, z))


def proj_sign(lot, at, z0, text, col, L, tall):
    """The Kowloon signboard: a lit box cantilevered far over the street on a steel truss, tied back to the wall,
    neon lettering and border on both faces."""
    t = 0.32
    y0 = -0.3 - L
    if tall:
        s = min(1.15, (L - 0.5) * 0.8)
        H = len(text) * s * 0.86 + s * 0.6
    else:
        s = rng.uniform(1.0, 1.6)
        H = s * 1.5
    board = pbr('painted_metal_shutter', tint=(0.1, 0.09, 0.1))
    steel = pbr('rusty_metal_02', tint=(0.16, 0.16, 0.16))
    face = flat(f'signface_{col}', tuple(c * 0.05 for c in col), rough=0.35, emit=col, strength=0.1) if rng.random() < 0.7 else flat(f'signbox_{col}', tuple(c * 0.2 for c in col), rough=0.35, emit=col, strength=0.9)
    parts = [(box_me((at - t / 2, y0, z0), (at + t / 2, -0.3, z0 + H), 1.0), Matrix(), board)]
    nm = neon_mat(col, 60.0)
    for side in (1, -1):
        fx = at + side * (t / 2 + 0.004)
        parts.append((box_me((min(fx, fx + side * 0.002), y0 + 0.08, z0 + 0.08), (max(fx, fx + side * 0.002), -0.38, z0 + H - 0.08)), Matrix(), face))
        fx = at + side * (t / 2 + 0.04)
        gm = glyphs(text, s * (0.95 if tall else 0.9), 'tube', vertical=tall, font='neon')
        gw = max(v.co.x for v in gm.vertices) - min(v.co.x for v in gm.vertices)
        if not tall and gw > L - 0.6:
            k = (L - 0.6) / gw; gm.transform(Matrix.Scale(k, 4))
        parts.append((gm, face_to(Vector((fx, (y0 - 0.3) / 2, z0 + H / 2)), Vector((0, side, 0)), Vector((0, 0, 1))), nm))
        m = 0.1
        rect = [(fx, y0 + m, z0 + m), (fx, -0.3 - m, z0 + m), (fx, -0.3 - m, z0 + H - m), (fx, y0 + m, z0 + H - m)]
        parts.append((tube_path(rect, 0.022, closed=True), Matrix(), neon_mat(neon_color(), 45.0)))
    # truss along the top and the tie rods back to the wall
    zt = z0 + H
    for dx in (-0.12, 0.12):
        parts.append((box_me((at + dx - 0.03, y0, zt), (at + dx + 0.03, 0, zt + 0.06)), Matrix(), steel))
        parts.append((box_me((at + dx - 0.03, y0, zt + 0.45), (at + dx + 0.03, 0, zt + 0.51)), Matrix(), steel))
    n = max(2, int(L / 0.6))
    for i in range(n + 1):
        yy = y0 + (0 - y0) * i / n
        parts.append((box_me((at - 0.15, yy - 0.02, zt), (at + 0.15, yy + 0.02, zt + 0.51)), Matrix(), steel))
    for frac in (0.55, 0.95):
        parts.append((tube_path([(at, y0 * frac, zt + 0.48), (at, 0, zt + 0.48 + L * 0.7)], 0.015), Matrix(), steel))
    assemble(f"proj_{lot['id']}_{at:.1f}_{z0:.1f}", parts, C_PROPS, lot['M'])
    collide(lot['M'], (at - t / 2 - 0.06, y0, z0), (at + t / 2 + 0.06, 0, zt + 0.51), 'sign')
    for yy in [y0 * 0.25, y0 * 0.75]:
        for side in (1, -1):
            l = bpy.data.lights.new('neon', 'POINT'); l.energy = 40 * H; l.color = col; l.shadow_soft_size = 0.6
            o = bpy.data.objects.new('neonlight', l); C_LIGHT.objects.link(o)
            o.matrix_world = lot['M'] @ Matrix.Translation((at + side * 0.7, yy, z0 + H / 2))


def signs(lot, h):
    W = lot['W']
    if 'piers' in lot:
        spots = list(lot['piers'])
        rng.shuffle(spots)
        spots = spots[:1 + (rng.random() < 0.55) + (len(spots) > 3)]
    else:
        n = 1 + (rng.random() < 0.6) + (W > 12)
        spots = [(i + 0.5) * W / n + rng.uniform(-W / (4 * n), W / (4 * n)) for i in range(n)]
    for at in spots:
        r = rng.random()
        if r < 0.32:
            big = rng.random() < 0.25
            text = rng.choice([t for t in NAMES_V if len(t) <= (5 if big else 3)])
            z0 = GF + 0.4 + rng.uniform(0, 3.5 if big else 7.5)
            if z0 + len(text) * 1.4 < h - 1: blade(lot, at, z0, text, neon_color(), big)
            continue
        tall = r < 0.62
        L = rng.uniform(2.6, 4.2) if tall else rng.uniform(3.5, 6.0)
        text = rng.choice([t for t in NAMES_V if len(t) <= 4]) if tall else rng.choice([t for t in NAMES_V + NAMES_H if len(t) <= 6])
        z0 = GF + 0.6 + rng.uniform(0, 6.0)
        if z0 + (len(text) * 1.1 if tall else 2.5) < h - 1: proj_sign(lot, at, z0, text, neon_color(), L, tall)
    if 'piers' not in lot and rng.random() < 0.4:
        wall_neon(lot, GF + 3.0 * rng.randint(1, 3) + 1.5, rng.choice(NAMES_H), neon_color())


# ---------------------------------------------------------------- street furniture
def lamps():
    me = lib_mesh('lamp', 'sketchfab/lamp.glb', 0.01)
    steel = flat('lamp_steel', (0.06, 0.065, 0.07), rough=0.45, metal=0.85)
    for i, m in enumerate(me.materials):
        if 'Glass' not in m.name: me.materials[i] = steel
    # which way the arm reaches: the lamp head sits where most of the mesh is above 7.5 m
    head = [v.co for v in me.vertices if v.co.z > 7.5]
    hx = sum(c.x for c in head) / len(head); hy = sum(c.y for c in head) / len(head)
    arm = math.atan2(hy, hx)
    for i, z in enumerate(range(-318, -100, 28)):
        x, out = (-752.47 + 0.45, 1) if i % 2 == 0 else (-738.47 - 0.45, -1)
        ob = bpy.data.objects.new('lamp', me); C_PROPS.objects.link(ob)
        ob.location = G(x, 0.18, z)
        ob.rotation_euler = (0, 0, -arm + (0 if out > 0 else math.pi))
        l = bpy.data.lights.new('lamp', 'SPOT'); l.energy = 300; l.color = (0.82, 0.9, 1.0); l.spot_size = math.radians(130); l.spot_blend = 0.6; l.shadow_soft_size = 0.2
        o = bpy.data.objects.new('lamplight', l); C_LIGHT.objects.link(o)
        o.location = G(x + out * 2.4, 8.0, z)


def cables():
    rub = flat('cable', (0.02, 0.02, 0.022), rough=0.45)
    parts = []
    for i in range(34):
        za = rng.uniform(-325, -100); zb = za + rng.uniform(-6, 6)
        ya, yb = rng.uniform(5.5, 16), rng.uniform(5.5, 16)
        a, b = G(-755.6, ya, za), G(-735.4, yb, zb)
        sag = rng.uniform(0.4, 1.6)
        n = 14
        pts = [tuple(a.lerp(b, k / n) - Vector((0, 0, sag * 4 * (k / n) * (1 - k / n)))) for k in range(n + 1)]
        for j in range(1 + (rng.random() < 0.35) * rng.randint(1, 3)):
            off = Vector((0, 0, -0.06 * j))
            parts.append((tube_path([tuple(Vector(p) + off) for p in pts], rng.uniform(0.008, 0.016)), Matrix(), rub))
    assemble('cables', parts, C_PROPS)


def bridge(z=-158.0):
    """A footbridge across the street between the second floors, ribbed underneath, lit along its edges, with the
    street's name in neon on both faces: the gateway the run starts through."""
    con = pbr('precast_concrete_wall', tint=(0.42, 0.42, 0.43))
    a, b = G(-755.7, 0, z + 1.8), G(-735.3, 0, z - 1.8)
    x0, x1, y0, y1 = a.x, b.x, a.y, b.y
    cx = (x0 + x1) / 2
    led = flat('led_strip', (0.1, 0.1, 0.1), emit=(0.55, 0.85, 1.0), strength=30.0)
    amb = flat('led_amber', (0.1, 0.1, 0.1), emit=(1.0, 0.55, 0.15), strength=25.0)
    rail = pbr('rusty_metal_02', tint=(0.14, 0.14, 0.14))
    board = pbr('painted_metal_shutter', tint=(0.1, 0.09, 0.1))
    parts = [(box_me((x0, y0, 6.55), (x1, y1, 7.0), 2.0), Matrix(), con)]
    # the deck's ribs and two edge beams underneath
    for xx in [x0 + 0.6 + i * 1.6 for i in range(int((x1 - x0 - 1.2) / 1.6) + 1)]:
        parts.append((box_me((xx - 0.1, y0 + 0.25, 6.25), (xx + 0.1, y1 - 0.25, 6.55), 1.0), Matrix(), con))
    for yy in (y0, y1 - 0.45):
        parts.append((box_me((x0, yy, 6.1), (x1, yy + 0.45, 6.55), 2.0), Matrix(), con))
    for yy in (y0, y1 - 0.25):
        parts.append((box_me((x0, yy, 7.0), (x1, yy + 0.25, 8.0), 2.0), Matrix(), con))
        parts.append((box_me((x0, yy + 0.05, 8.0), (x1, yy + 0.2, 8.06)), Matrix(), rail))
    for yy in (y0 + 0.5, y1 - 0.54):
        parts.append((box_me((x0 + 0.3, yy, 6.07), (x1 - 0.3, yy + 0.04, 6.1)), Matrix(), led))
    for yy in (y0 - 0.005, y1):
        parts.append((box_me((x0 + 0.3, yy, 6.3), (x1 - 0.3, yy + 0.005, 6.36)), Matrix(), amb))
    # the name board standing on each parapet
    red = neon_mat((1.0, 0.05, 0.12), 70.0)
    gold = neon_mat((1.0, 0.55, 0.12), 50.0)
    for side, yy in ((-1, y0), (1, y1)):
        face = yy + side * 0.32
        parts.append((box_me((cx - 4.6, min(yy, face), 7.6), (cx + 4.6, max(yy, face), 10.6), 1.0), Matrix(), board))
        rot = Matrix.Rotation(math.radians(90), 4, 'X') if side < 0 else Matrix.Rotation(math.pi, 4, 'Z') @ Matrix.Rotation(math.radians(90), 4, 'X')
        fy = face + side * 0.04
        parts.append((glyphs('廟街', 1.75, 'tube', font='neon'), Matrix.Translation((cx, fy, 9.55)) @ rot, red))
        parts.append((glyphs('TEMPLE  STREET', 0.5, 'tube', font='neon'), Matrix.Translation((cx, fy, 8.2)) @ rot, gold))
        m = 0.14
        rect = [(cx - 4.6 + m, fy, 7.6 + m), (cx + 4.6 - m, fy, 7.6 + m), (cx + 4.6 - m, fy, 10.6 - m), (cx - 4.6 + m, fy, 10.6 - m)]
        parts.append((tube_path(rect, 0.025, closed=True), Matrix(), gold))
        for xx in (cx - 2.2, cx + 2.2):
            l = bpy.data.lights.new('gate', 'POINT'); l.energy = 260; l.color = (1.0, 0.12, 0.15); l.shadow_soft_size = 1.0
            o = bpy.data.objects.new('gatelight', l); C_LIGHT.objects.link(o); o.location = (xx, fy + side * 0.8, 9.4)
    assemble('bridge', parts, C_PROPS)
    I = Matrix()
    collide(I, (x0, y0, 6.1), (x1, y1, 7.0), 'roof', solid=True)
    for yy in (y0, y1 - 0.25):
        collide(I, (x0, yy, 7.0), (x1, yy + 0.25, 8.06), 'awning')
    collide(I, (cx - 4.6, y0 - 0.4, 7.6), (cx + 4.6, y0, 10.6), 'sign')
    collide(I, (cx - 4.6, y1, 7.6), (cx + 4.6, y1 + 0.4, 10.6), 'sign')
    for xx in (x0 + 4, cx, x1 - 4):
        l = bpy.data.lights.new('bridge', 'AREA'); l.size = 3; l.energy = 80; l.color = (0.55, 0.85, 1.0)
        o = bpy.data.objects.new('bridgelight', l); C_LIGHT.objects.link(o); o.location = (xx, (y0 + y1) / 2, 6.0)


def clutter(lot):
    """Rubbish at the kerb, crates and boxes by the shops."""
    W = lot['W']
    bag = lib_mesh('trashbag', 'ph/trashbag/trashbag.gltf')
    crate = lib_mesh('crate', 'ph/plastic_crate_01/plastic_crate_01.gltf')
    card = lib_mesh('card', 'ph/cardboard_box_01/cardboard_box_01.gltf')
    for i in range(rng.randint(0, 4)):
        o = bpy.data.objects.new('bag', bag); C_PROPS.objects.link(o)
        o.matrix_world = lot['M'] @ Matrix.Translation((rng.uniform(0.5, W - 0.5), -rng.uniform(2.4, 3.0), 0)) @ Matrix.Rotation(rng.uniform(0, 6.3), 4, 'Z')
    for i in range(rng.randint(0, 3)):
        at = rng.uniform(0.5, W - 0.5)
        for k in range(rng.randint(1, 4)):
            is_crate = rng.random() < 0.6
            o = bpy.data.objects.new('crate' if is_crate else 'card', crate if is_crate else card); C_PROPS.objects.link(o)
            o.matrix_world = lot['M'] @ Matrix.Translation((at + rng.uniform(-0.1, 0.1), -rng.uniform(1.05, 1.4), k * 0.27)) @ Matrix.Rotation(rng.uniform(-0.3, 0.3), 4, 'Z')


def vending(lot):
    me = lib_mesh('vending', 'sf2/vending/scene.gltf')
    o = bpy.data.objects.new('vending', me); C_PROPS.objects.link(o)
    # the machine's front is its -y in the pack
    # clear of the shopfronts, which stand 0.67 m proud
    o.matrix_world = lot['M'] @ Matrix.Translation((rng.uniform(0.8, lot['W'] - 0.8), -1.12, 0))
    at = o.matrix_world.translation
    collide(Matrix.Translation(at), (-0.6, -0.45, 0), (0.6, 0.45, 2.0), 'shop')
    l = bpy.data.lights.new('vend', 'AREA'); l.size = 0.9; l.size_y = 1.6; l.energy = 40; l.color = (0.85, 0.95, 1.0)
    lo = bpy.data.objects.new('vendlight', l); C_LIGHT.objects.link(lo)
    lo.matrix_world = o.matrix_world @ Matrix.Translation((0, -0.6, 1.0)) @ Matrix.Rotation(math.radians(-90), 4, 'X')


# ---------------------------------------------------------------- the street
def street():
    ground()
    for i, lot in enumerate(lots()):
        x0, x1, z0, z1, h = lot['box']
        if not lot['hero']:
            p0, p1 = G(x0, 0, z1), G(x1, 0, z0)
            box(f"bg_{lot['id']}", (p0.x, p0.y, 0), (p1.x, p1.y, h), tower_mat(), C_BLDG, tile=1.0)
            continue
        # every hero lot is a generated tenement: real geometry at street level, and a mesh the lightmap can unwrap
        board = rng.random() < 0.4
        hh = tenement(lot, h, board)
        if board: floor_board(lot, lot['fh'])
        fascia(lot)
        signs(lot, hh)
        clutter(lot)
        if rng.random() < 0.18: vending(lot)
    taken = [(b['tiers'][0]['x0'] + b['tiers'][0]['x1']) / 2 for b in L['buildings']], [(b['tiers'][0]['z0'] + b['tiers'][0]['z1']) / 2 for b in L['buildings']]
    for k, bl in enumerate(L['blocks']):
        if any(bl['x0'] < x < bl['x1'] and bl['z0'] < z < bl['z1'] for x, z in zip(*taken)): continue
        n = max(1, round((bl['z1'] - bl['z0']) / 22))
        for i in range(n):
            z0 = bl['z0'] + (bl['z1'] - bl['z0']) * i / n + 0.3; z1 = bl['z0'] + (bl['z1'] - bl['z0']) * (i + 1) / n - 0.3
            p0, p1 = G(bl['x0'] + 0.5, 0, z1), G(bl['x1'] - 0.5, 0, z0)
            box(f"fill_{k}_{i}", (p0.x, p0.y, 0), (p1.x, p1.y, rng.uniform(28, 95)), tower_mat(), C_BLDG, tile=1.0)
    game_shops()
    game_lamps()
    cables()
    bridge()
    tag()


# what each object becomes in the game: lightmapped static geometry, self-lit signs, instanced props, or context
# that only shapes the bake
def tag():
    for o in bpy.data.objects:
        if o.type != 'MESH' or not o.users_collection or o.users_collection[0] == LIB: continue
        n = o.name
        hero = n.split('_')[1] if '_' in n else ''
        if n.startswith(('ten_', 'gfbox_', 'back_', 'proc_', 'bridge')): o['nz'] = 'lm'
        elif n.startswith(('fascia_', 'board_', 'blade_', 'proj_', 'wneon_', 'cables')): o['nz'] = 'self'
        elif o.data.name.startswith('exterior_aircon_unit'): o['nz'] = 'prop:' + o.data.name.split('.')[0]
        elif n.startswith('vending'): o['nz'] = 'prop:vending'
        elif n.startswith('bag'): o['nz'] = 'prop:trashbag'
        elif n.startswith('crate'): o['nz'] = 'prop:crate'
        elif n.startswith('card'): o['nz'] = 'prop:carton'
        else: o['nz'] = 'context'



def lighting():
    w = bpy.data.worlds.new('night'); scene.world = w; w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs[1].default_value = 1.0
    sky = w.node_tree.nodes.new('ShaderNodeTexGradient'); sky.gradient_type = 'EASING'
    sep = w.node_tree.nodes.new('ShaderNodeTexCoord')
    mp = w.node_tree.nodes.new('ShaderNodeMapping'); mp.inputs['Rotation'].default_value = (0, math.radians(-90), 0)
    w.node_tree.links.new(sep.outputs['Generated'], mp.inputs['Vector']); w.node_tree.links.new(mp.outputs[0], sky.inputs[0])
    ramp = w.node_tree.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.5; ramp.color_ramp.elements[0].color = (0.05, 0.035, 0.06, 1)
    ramp.color_ramp.elements[1].position = 0.75; ramp.color_ramp.elements[1].color = (0.006, 0.01, 0.022, 1)
    w.node_tree.links.new(sky.outputs[0], ramp.inputs[0]); w.node_tree.links.new(ramp.outputs[0], bg.inputs[0])
    if cfg.get('haze', True):
        vol = w.node_tree.nodes.new('ShaderNodeVolumeScatter'); vol.inputs['Density'].default_value = cfg.get('haze_density', 0.0009); vol.inputs['Anisotropy'].default_value = 0.35
        w.node_tree.links.new(vol.outputs[0], w.node_tree.nodes['World Output'].inputs['Volume'])


def camera(r):
    cam = bpy.data.objects.get('cam')
    if not cam:
        cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); scene.collection.objects.link(cam)
    scene.camera = cam
    d = Vector((r['dir'][0], -r['dir'][2], r['dir'][1]))
    cam.location = G(*r['pos'])
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.data.sensor_fit = 'VERTICAL'
    cam.data.angle_y = math.radians(r.get('fov', 60))
    cam.data.clip_start = 0.1; cam.data.clip_end = 3000


street()
bpy.app.driver_namespace['nz_colliders'] = COLLIDERS
if cfg.get('day'):
    w = bpy.data.worlds.new('day'); scene.world = w; w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.55, 0.62, 0.75, 1)
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); C_LIGHT.objects.link(sun)
    sun.data.energy = 3.5; sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(60))
else:
    lighting()

scene.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'METAL'
prefs.get_devices()
for d in prefs.devices: d.use = True
scene.cycles.device = 'GPU'
scene.cycles.samples = cfg.get('samples', 96)
scene.cycles.use_denoising = True
scene.cycles.volume_step_rate = 4.0
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = cfg.get('exposure', -0.8)
scene.render.resolution_x, scene.render.resolution_y = cfg.get('res', [960, 540])
if cfg.get('out'):
    os.makedirs(os.path.dirname(os.path.abspath(cfg['out'])), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(cfg['out']))
for r in cfg.get('renders', []):
    camera(r)
    scene.render.filepath = r['file']
    bpy.ops.render.render(write_still=True)
    print('RENDERED', r['file'])
