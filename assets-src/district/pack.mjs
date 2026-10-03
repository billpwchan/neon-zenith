// Export (export.py) → what the game loads from public/district:
//   district.glb  static geometry, meshopt; textures as KTX2
//   props.glb     instanced props with LODs, meshopt; textures as KTX2
//   lightmap.ktx2 / lightmap_2k.ktx2   the baked atlas, UASTC HDR (BC6H on desktop)
//   ground.ktx2   the light at street level, UASTC HDR
//   ph/<id>_{diff,nor,arm}.ktx2        the Poly Haven sets the district's materials name in their extras, with
//                                      _1k copies of diff and nor for phones (arm is 1K already)
// node assets-src/district/pack.mjs
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS, KHRTextureBasisu } from '@gltf-transform/extensions';
import { dedup, prune, meshopt } from '@gltf-transform/functions';
import { MeshoptEncoder, MeshoptDecoder } from 'meshoptimizer';
import sharp from 'sharp';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync, readdirSync, existsSync, rmSync, statSync } from 'node:fs';
import { join } from 'node:path';
import os from 'node:os';

const ROOT = new URL('../..', import.meta.url).pathname;
const BUILD = join(ROOT, 'assets-src/district/build');
const PH = join(ROOT, 'assets-src/ph');
const OUT = join(ROOT, 'public/district');
const TMP = join(os.tmpdir(), 'nz-pack');
mkdirSync(join(OUT, 'ph'), { recursive: true });
mkdirSync(TMP, { recursive: true });

// colour: ETC1S (small, colour detail survives at street distance); data and normals: UASTC, which keeps channels apart
const ROLE = {
  color: { max: 2048, args: ['-q', '255', '-comp_level', '2', '-srgb', '-mip_srgb'] },
  normal: { max: 2048, args: ['-uastc', '-uastc_level', '2', '-uastc_rdo_l', '2', '-normal_map'] },
  data: { max: 1024, args: ['-uastc', '-uastc_level', '2', '-uastc_rdo_l', '3', '-linear'] },
};

let n = 0;
async function ktx2(input, role, cap = Infinity) {
  const { args } = ROLE[role], max = Math.min(ROLE[role].max, cap);
  const meta = await sharp(input).metadata();
  const s = Math.min(1, max / Math.max(meta.width, meta.height));
  // block-compressed mips want sizes divisible by four
  const w = Math.max(4, Math.round((meta.width * s) / 4) * 4), h = Math.max(4, Math.round((meta.height * s) / 4) * 4);
  const png = join(TMP, `t${n}.png`), out = join(TMP, `t${n++}.ktx2`);
  await sharp(input).resize(w, h, { kernel: 'lanczos3', fit: 'fill' }).png().toFile(png);
  execFileSync('basisu', [...args, '-mipmap', '-file', png, '-output_file', out], { stdio: 'pipe' });
  const buf = readFileSync(out);
  rmSync(png); rmSync(out);
  return buf;
}

function roleOf(doc, tex) {
  for (const m of doc.getRoot().listMaterials()) {
    if (m.getNormalTexture() === tex) return 'normal';
    if (m.getBaseColorTexture() === tex || m.getEmissiveTexture() === tex) return 'color';
  }
  return 'data';
}

async function pack(name, keepAttributes, cap) {
  const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder });
  const doc = await io.read(join(BUILD, name));
  const textures = doc.getRoot().listTextures();
  for (const t of textures) {
    t.setImage(await ktx2(Buffer.from(t.getImage()), roleOf(doc, t), cap)).setMimeType('image/ktx2');
    t.setURI(t.getURI().replace(/\.(png|jpe?g|webp)$/i, '.ktx2'));
  }
  if (textures.length) doc.createExtension(KHRTextureBasisu).setRequired(true);
  await MeshoptEncoder.ready;
  await doc.transform(dedup(), prune({ keepAttributes, keepExtras: true }),
    meshopt({ encoder: MeshoptEncoder, level: 'medium', quantizePosition: 16, quantizeTexcoord: 16, quantizeNormal: 10 }));
  await io.write(join(OUT, name), doc);
  console.log(name, textures.length, 'textures', (statSync(join(OUT, name)).size / 1e6).toFixed(1), 'MB');
  return doc;
}

// the district's materials name no textures, but the runtime reads all four of its UV sets; the props carry stray
// UV layers from their source scenes that nothing reads. Props are under a metre across, where 1K is already finer
// than the screen at arm's length.
const district = await pack('district.glb', true);
await pack('props.glb', false, 1024);

// the Poly Haven sets the district's materials ask for
const ids = new Set(district.getRoot().listMaterials().map((m) => m.getExtras().nz_tex).filter(Boolean));
for (const id of ids) {
  const dir = join(PH, id, 'textures');
  const files = readdirSync(dir);
  const pick = (tag) => files.find((f) => f.includes(`_${tag}_`));
  for (const [tag, role, out] of [['diff', 'color', 'diff'], ['nor_gl', 'normal', 'nor'], ['arm', 'data', 'arm']]) {
    const dst = join(OUT, 'ph', `${id}_${out}.ktx2`);
    let src = pick(tag) && join(dir, pick(tag));
    if (!src) {
      // sets without a packed map ship roughness alone: no occlusion, no metal
      src = join(dir, pick('rough'));
      const { data, info } = await sharp(src).extractChannel(0).raw().toBuffer({ resolveWithObject: true });
      const arm = Buffer.alloc(info.width * info.height * 3);
      for (let i = 0; i < data.length; i++) { arm[i * 3] = 255; arm[i * 3 + 1] = data[i]; }
      const tmp = join(TMP, `${id}_arm.png`);
      await sharp(arm, { raw: { width: info.width, height: info.height, channels: 3 } }).png().toFile(tmp);
      src = tmp;
    }
    const small = role === 'data' ? null : dst.replace('.ktx2', '_1k.ktx2');
    if (existsSync(dst) && statSync(dst).mtimeMs > statSync(src).mtimeMs && (!small || existsSync(small))) continue;
    writeFileSync(dst, await ktx2(src, role));
    if (small) writeFileSync(small, await ktx2(src, role, 1024));
  }
  console.log('ph', id);
}

// the baked light: HDR straight from the denoised EXRs
const hdr = (src, dst, extra = []) => {
  execFileSync('basisu', ['-hdr_4x4', '-mipmap', ...extra, '-file', join(BUILD, src), '-output_file', join(OUT, dst)], { stdio: 'pipe' });
  console.log(dst, (statSync(join(OUT, dst)).size / 1e6).toFixed(1), 'MB');
};
hdr('lm_dn.exr', 'lightmap.ktx2');
hdr('lm_dn.exr', 'lightmap_2k.ktx2', ['-resample', '2048', '2048']);
hdr('ground_dn.exr', 'ground.ktx2');
writeFileSync(join(OUT, 'ph.json'), JSON.stringify([...ids].sort()));
