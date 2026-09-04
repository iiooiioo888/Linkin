/**
 * BuildingViewer — Three.js 體素預覽（Sponge Schematic v3）。
 */
import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { BuildingPreview } from '../../api/linkin';

type Props = {
  preview: BuildingPreview | null;
  loading?: boolean;
};

export default function BuildingViewer({ preview, loading = false }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !preview || preview.voxels.length === 0) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0d0d0f);
    scene.fog = new THREE.Fog(0x0d0d0f, 28, 90);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 500);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.replaceChildren(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI * 0.48;

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xfff4e0, 0.95);
    key.position.set(40, 80, 30);
    scene.add(key);
    scene.add(new THREE.HemisphereLight(0x87b7ff, 0x2a2a2e, 0.35));

    const groups = new Map<string, { color: string; opacity: number; emissive: string; positions: THREE.Vector3[] }>();
    for (const voxel of preview.voxels) {
      const swatch = preview.palette[voxel.i] ?? { name: 'stone', color: '#8e8e93' };
      const color = swatch.color || '#8e8e93';
      const opacity = swatch.opacity ?? 1;
      const emissive = swatch.emissive || '#000000';
      const keyName = `${color}:${opacity}:${emissive}`;
      let group = groups.get(keyName);
      if (!group) {
        group = { color, opacity, emissive, positions: [] };
        groups.set(keyName, group);
      }
      group.positions.push(new THREE.Vector3(voxel.x, voxel.y, voxel.z));
    }

    const ox = (preview.width - 1) / 2;
    const oz = (preview.length - 1) / 2;
    const geometry = new THREE.BoxGeometry(0.96, 0.96, 0.96);
    const meshes: THREE.InstancedMesh[] = [];
    const dummy = new THREE.Object3D();

    for (const group of groups.values()) {
      const material = new THREE.MeshLambertMaterial({
        color: group.color,
        transparent: group.opacity < 0.999,
        opacity: group.opacity,
        emissive: group.emissive,
        depthWrite: group.opacity >= 0.999,
      });
      const mesh = new THREE.InstancedMesh(geometry, material, group.positions.length);
      group.positions.forEach((pos, index) => {
        dummy.position.set(pos.x - ox, pos.y, pos.z - oz);
        dummy.updateMatrix();
        mesh.setMatrixAt(index, dummy.matrix);
      });
      mesh.instanceMatrix.needsUpdate = true;
      scene.add(mesh);
      meshes.push(mesh);
    }

    const grid = new THREE.GridHelper(
      Math.max(preview.width, preview.length) + 4,
      Math.max(preview.width, preview.length) + 4,
      0x3a3a40,
      0x222226,
    );
    grid.position.y = -0.5;
    scene.add(grid);

    const span = Math.max(preview.width, preview.height, preview.length, 4);
    camera.position.set(span * 1.15, span * 0.85, span * 1.35);
    controls.target.set(0, Math.max(1, preview.height / 2), 0);
    controls.update();

    const resize = () => {
      const width = host.clientWidth || 1;
      const height = host.clientHeight || 1;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(host);
    resize();

    let frame = 0;
    const tick = () => {
      frame = requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera);
    };
    tick();

    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      controls.dispose();
      geometry.dispose();
      for (const mesh of meshes) {
        const material = mesh.material;
        if (Array.isArray(material)) material.forEach((item) => item.dispose());
        else material.dispose();
      }
      renderer.dispose();
      host.replaceChildren();
    };
  }, [preview]);

  if (loading) {
    return <div className="flex h-full items-center justify-center text-[12px] text-[#8a8f98]">載入 3D 模型…</div>;
  }
  if (!preview || preview.voxels.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
        <p className="text-[12px] text-[#AEAEB2]">生成或選取建築方案後，以 Three.js 預覽方塊模型</p>
        <p className="text-[10px] text-[#636366]">Sponge Schematic v3 · .schem</p>
      </div>
    );
  }

  return (
    <div className="relative h-full min-h-[280px] w-full">
      <div ref={hostRef} className="h-full w-full overflow-hidden rounded-xl" />
      <div className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-black/45 px-2 py-1 text-[10px] text-[#AEAEB2]">
        {preview.width}×{preview.height}×{preview.length} · {preview.voxel_count} 方塊 · v{preview.version}
        {preview.biome ? ` · ${preview.biome.replace('minecraft:', '')}` : ''}
      </div>
    </div>
  );
}
