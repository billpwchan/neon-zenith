import bpy, sys
argv = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=argv[0])
for m in bpy.data.materials:
    if not m.use_nodes: continue
    p = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not p: print('MAT', m.name, 'no principled'); continue
    def inp(k):
        i = p.inputs.get(k)
        if i is None: return '?'
        if i.is_linked: return 'tex'
        v = i.default_value
        try: return '(' + ','.join(f'{x:.2f}' for x in v) + ')'
        except TypeError: return f'{v:.2f}'
    users = sum(1 for o in bpy.data.objects if o.type == 'MESH' and any(s.material == m for s in o.material_slots))
    print('MAT', m.name, 'base', inp('Base Color'), 'met', inp('Metallic'), 'rough', inp('Roughness'), 'alpha', inp('Alpha'), 'trans', inp('Transmission Weight'), 'em', inp('Emission Color'), inp('Emission Strength'), 'blend', m.blend_method if hasattr(m, 'blend_method') else '', 'users', users)
