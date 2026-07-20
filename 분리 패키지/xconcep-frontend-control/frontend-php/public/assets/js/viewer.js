import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

let renderer, scene, camera, controls, currentModel, container, animationFrame;

export function initViewer(element) {
  container = element;
  if (renderer) return;
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07131f);
  scene.fog = new THREE.Fog(0x07131f, 9, 24);

  camera = new THREE.PerspectiveCamera(38, 1, 0.05, 100);
  camera.position.set(5.8, 4.5, 7.2);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.innerHTML = '';
  container.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.target.set(0, 0.9, 0);
  controls.minDistance = 3;
  controls.maxDistance = 18;

  scene.add(new THREE.HemisphereLight(0xbfeaff, 0x122331, 2.5));
  const key = new THREE.DirectionalLight(0xffffff, 4.2);
  key.position.set(5, 8, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x2cc8ef, 2.2);
  fill.position.set(-5, 3, -3);
  scene.add(fill);

  const grid = new THREE.GridHelper(18, 36, 0x1f5d78, 0x12364b);
  grid.material.opacity = 0.55;
  grid.material.transparent = true;
  scene.add(grid);

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(22, 22),
    new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.24 })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.01;
  floor.receiveShadow = true;
  scene.add(floor);

  const resize = () => {
    if (!container || !renderer) return;
    const width = container.clientWidth || 640;
    const height = container.clientHeight || 480;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(container);
  resize();

  const render = () => {
    controls.update();
    renderer.render(scene, camera);
    animationFrame = requestAnimationFrame(render);
  };
  render();
}

export async function loadModel(url) {
  if (!renderer) throw new Error('Viewer가 초기화되지 않음');
  if (currentModel) {
    scene.remove(currentModel);
    currentModel.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
        materials.forEach((m) => m.dispose?.());
      }
    });
  }
  const loader = new GLTFLoader();
  const gltf = await loader.loadAsync(`${url}?v=${Date.now()}`);
  currentModel = gltf.scene;
  currentModel.traverse((obj) => {
    if (obj.isMesh) {
      obj.castShadow = true;
      obj.receiveShadow = true;
      if (obj.material) {
        obj.material.metalness = Math.min(obj.material.metalness ?? 0.25, 0.6);
        obj.material.roughness = Math.max(obj.material.roughness ?? 0.55, 0.28);
      }
    }
  });
  scene.add(currentModel);
  frameObject(currentModel);
}

function frameObject(object) {
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxSize = Math.max(size.x, size.y, size.z) || 1;
  object.position.sub(center);
  object.position.y += size.y / 2;
  controls.target.set(0, size.y * 0.42, 0);
  camera.position.set(maxSize * 1.25, maxSize * .95, maxSize * 1.45);
  camera.near = Math.max(maxSize / 100, .01);
  camera.far = maxSize * 100;
  camera.updateProjectionMatrix();
  controls.update();
}

export function setView(view) {
  if (!camera || !controls) return;
  const distance = camera.position.distanceTo(controls.target) || 7;
  const target = controls.target.clone();
  if (view === 'front') camera.position.set(target.x, target.y + distance * .08, target.z + distance);
  else if (view === 'top') camera.position.set(target.x, target.y + distance, target.z + .01);
  else camera.position.set(target.x + distance * .75, target.y + distance * .58, target.z + distance * .88);
  camera.lookAt(target);
  controls.update();
}

export function toggleFullscreen() {
  if (!container) return;
  if (!document.fullscreenElement) container.requestFullscreen?.();
  else document.exitFullscreen?.();
}
