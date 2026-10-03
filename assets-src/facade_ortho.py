# Orthographic facade capture: looks at a model's front (glTF +Z) over a rectangle and writes
#   albedo.png  flat texture colour (sRGB)
#   glass.png   white where a glass material is the front-most surface
#   frame.png   white where a modelled frame material is front-most
#   normal.png  tangent-space normal of the front-most surface (x right, y up, z toward the viewer), raw
# blender -b --python facade_ortho.py -- cfg.json
import bpy, sys, json, math, re, os
from mathutils import Vector

cfg = json.load(open(sys.argv[sys.argv.index('--') + 1]))
out = cfg['out']
os.makedirs(out, exist_ok=True)
x0, x1, y0, y1 = cfg['rect']
W, H = cfg['px']

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=cfg['src'])
hide = re.compile(cfg['hide']) if cfg.get('hide') else None
for ob in list(bpy.data.objects):
    if ob.type != 'MESH': continue
    names = [ob.name] + [s.material.name for s in ob.material_slots if s.material]
    if hide and any(hide.search(n) for n in names): bpy.data.objects.remove(ob); continue
    # street furniture standing clear of the wall (poles, signs) is not part of the facade
    if 'front' in cfg and max((ob.matrix_world @ Vector(c)).y for c in ob.bound_box) < -(cfg.get('zfront', 0) + cfg['front']):
        bpy.data.objects.remove(ob)
for img in bpy.data.images: img.alpha_mode = 'CHANNEL_PACKED'

sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.film_transparent = True
cam = bpy.data.cameras.new('c'); cam.type = 'ORTHO'; cam.clip_end = 2000
cam.ortho_scale = max(x1 - x0, (y1 - y0))
cam.sensor_fit = 'AUTO'
co = bpy.data.objects.new('c', cam); sc.collection.objects.link(co); sc.camera = co
# glTF (x, y, z) -> Blender (x, -z, y): the front (+z) faces Blender -y
co.location = ((x0 + x1) / 2, -(cfg.get('zfront', 0) + 100), (y0 + y1) / 2)
co.rotation_euler = (math.pi / 2, 0, 0)


def render(path):
    sc.render.filepath = os.path.join(out, path)
    bpy.ops.render.render(write_still=True)


# albedo: workbench, unlit texture colour
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'FLAT'
sc.display.shading.color_type = 'TEXTURE'
sc.display.render_aa = '16'
sc.view_settings.view_transform = 'Standard'
render('albedo.png')

# material masks: flat material colours
sc.display.shading.color_type = 'MATERIAL'
glass = re.compile(cfg['glass'])
frame = re.compile(cfg['frame']) if cfg.get('frame') else None
for m in bpy.data.materials:
    m.diffuse_color = (1, 1, 1, 1) if glass.search(m.name) else (0, 0, 0, 1)
render('glass.png')
for m in bpy.data.materials:
    m.diffuse_color = (1, 1, 1, 1) if frame and frame.search(m.name) else (0, 0, 0, 1)
render('frame.png')

# normals: cycles, every surface emits its own normal remapped to the facade's tangent frame
sc.render.engine = 'CYCLES'
sc.cycles.samples = 16
sc.cycles.use_denoising = False
sc.view_settings.view_transform = 'Raw'
nm = bpy.data.materials.new('nrm'); nm.use_nodes = True
nt = nm.node_tree; nt.nodes.clear()
geo = nt.nodes.new('ShaderNodeNewGeometry')
sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(geo.outputs['Normal'], sep.inputs[0])
neg = nt.nodes.new('ShaderNodeMath'); neg.operation = 'MULTIPLY'; neg.inputs[1].default_value = -1
nt.links.new(sep.outputs['Y'], neg.inputs[0])
comb = nt.nodes.new('ShaderNodeCombineXYZ')
nt.links.new(sep.outputs['X'], comb.inputs['X']); nt.links.new(sep.outputs['Z'], comb.inputs['Y']); nt.links.new(neg.outputs[0], comb.inputs['Z'])
rem = nt.nodes.new('ShaderNodeVectorMath'); rem.operation = 'MULTIPLY_ADD'
rem.inputs[1].default_value = (0.5, 0.5, 0.5); rem.inputs[2].default_value = (0.5, 0.5, 0.5)
nt.links.new(comb.outputs[0], rem.inputs[0])
em = nt.nodes.new('ShaderNodeEmission'); nt.links.new(rem.outputs[0], em.inputs['Color'])
o = nt.nodes.new('ShaderNodeOutputMaterial'); nt.links.new(em.outputs[0], o.inputs['Surface'])
sc.view_layers[0].material_override = nm
if sc.world is None: sc.world = bpy.data.worlds.new('w')
sc.world.use_nodes = True
sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0
render('normal.png')
# glass by depth, for models whose panes are painted into one atlas with the wall: whatever sits more than
# glassDepth behind the wall plane is inside a window opening
if 'glassDepth' in cfg:
    nm2 = bpy.data.materials.new('dep'); nm2.use_nodes = True
    nt = nm2.node_tree; nt.nodes.clear()
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(geo.outputs['Position'], sep.inputs[0])
    gt = nt.nodes.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'
    gt.inputs[1].default_value = -cfg.get('zfront', 0) + cfg['glassDepth']
    nt.links.new(sep.outputs['Y'], gt.inputs[0])
    em = nt.nodes.new('ShaderNodeEmission'); nt.links.new(gt.outputs[0], em.inputs['Color'])
    o = nt.nodes.new('ShaderNodeOutputMaterial'); nt.links.new(em.outputs[0], o.inputs['Surface'])
    sc.view_layers[0].material_override = nm2
    render('glass.png')
print('FACADE OK', out)
