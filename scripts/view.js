// Lookdev: lines up glTF models in the game's night lighting so assets can be judged before they go in.
// ?f=prep/a.glb,prep/b.glb  &len=4.6,5  (target length per model, metres)  &yaw=deg  &pitch=deg  &dist=m  &studio  &rot=deg,deg (per-model yaw fix)
import * as THREE from 'three/webgpu';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { makeNeonEnv } from '../src/core/env.js';

const q = new URLSearchParams(location.search);
const files = (q.get('f') || '').split(',').filter(Boolean);
const lens = (q.get('len') || '').split(',').map(Number);
const rots = (q.get('rot') || '').split(',').map(Number);
const renderer = new THREE.WebGPURenderer({ antialias: true });
renderer.setPixelRatio(devicePixelRatio);
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
document.body.appendChild(renderer.domElement);
await renderer.init();
const scene = new THREE.Scene();
const studio = q.has('studio');
if (studio) {
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.background = new THREE.Color(0x30343a);
} else {
  scene.environment = makeNeonEnv();
  scene.environmentIntensity = 0.6;
  scene.background = new THREE.Color(0x05040a);
  const a = new THREE.PointLight(0xff3df2, 60, 30, 1.5); a.position.set(-6, 4, 3); scene.add(a);
  const b = new THREE.PointLight(0x3be8ff, 60, 30, 1.5); b.position.set(6, 3, -3); scene.add(b);
  const c = new THREE.PointLight(0xffc890, 25, 30, 1.5); c.position.set(0, 7, 6); scene.add(c);
}
const ground = new THREE.Mesh(new THREE.PlaneGeometry(200, 200).rotateX(-Math.PI / 2), new THREE.MeshStandardNodeMaterial({ color: 0x0b0b0e, roughness: 0.25, metalness: 0 }));
scene.add(ground);

const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
const gap = 1.2;
let x = 0;
const info = [];
const items = [];
for (let i = 0; i < files.length; i++) {
  const g = await loader.loadAsync('/assets-src/' + files[i]);
  const root = g.scene;
  const hide = q.get('hide');
  if (hide) root.traverse((o) => { if (o.name.startsWith(hide)) o.visible = false; });
  if (rots[i]) root.rotation.y = (rots[i] * Math.PI) / 180;
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root, true);
  const size = box.getSize(new THREE.Vector3());
  const len = lens[i] || lens[0] || 4.6;
  const s = q.has('raw') ? 1 : len / Math.max(size.x, size.z);
  const wrap = new THREE.Group();
  wrap.add(root);
  wrap.scale.setScalar(s);
  root.position.set(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2);
  items.push({ wrap, w: size.x * s });
  let tris = 0;
  root.traverse((o) => { if (o.isMesh && o.visible) tris += (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3; });
  info.push(`${files[i]}  raw ${size.x.toFixed(2)}x${size.y.toFixed(2)}x${size.z.toFixed(2)}  scale ${s.toFixed(3)}  tris ${tris}`);
  scene.add(wrap);
}
const total = items.reduce((a, it) => a + it.w, 0) + gap * (items.length - 1);
for (const it of items) { it.wrap.position.x = x - total / 2 + it.w / 2; x += it.w + gap; }
document.getElementById('l').textContent = info.join('\n');

const camera = new THREE.PerspectiveCamera(+(q.get('fov') || 35), innerWidth / innerHeight, 0.05, 500);
const yaw = ((+q.get('yaw') || 35) * Math.PI) / 180, pitch = ((+q.get('pitch') || 14) * Math.PI) / 180;
const dist = +(q.get('dist') || Math.max(8, total * 1.25));
const ty = +(q.get('ty') || 0.8);
camera.position.set(Math.sin(yaw) * Math.cos(pitch) * dist, ty + Math.sin(pitch) * dist, Math.cos(yaw) * Math.cos(pitch) * dist);
camera.lookAt(0, ty, 0);
renderer.setAnimationLoop(() => renderer.render(scene, camera));
window.__nz = { ready: true, scene, info };
