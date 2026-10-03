// one-off: Sketchfab exports -> glTF that three's loader reads natively (metal/rough), deduped and welded
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { metalRough, dedup, weld, prune } from '@gltf-transform/functions';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
for (const n of process.argv.slice(2)) {
  const doc = await io.read(`assets-src/sketchfab/${n}.glb`);
  await doc.transform(metalRough(), dedup(), weld(), prune());
  await io.write(`assets-src/prep/${n}.glb`, doc);
  console.log(n, 'ok');
}
