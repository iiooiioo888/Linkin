/**
 * three@0.180 未在 package exports 提供 types；避免安裝龐大的 @types/three。
 * 僅覆蓋 BuildingViewer 實際使用到的 API。
 */
declare module 'three' {
  export const SRGBColorSpace: string;

  export class Color {
    constructor(hex?: number | string);
  }

  export class Fog {
    constructor(color: number, near?: number, far?: number);
  }

  export class Vector3 {
    constructor(x?: number, y?: number, z?: number);
    x: number;
    y: number;
    z: number;
    set(x: number, y: number, z: number): this;
  }

  export class Object3D {
    position: Vector3;
    matrix: object;
    updateMatrix(): void;
  }

  export class Scene {
    background: Color | null;
    fog: Fog | null;
    add(...objects: object[]): this;
  }

  export class PerspectiveCamera {
    constructor(fov: number, aspect: number, near: number, far: number);
    aspect: number;
    position: Vector3;
    updateProjectionMatrix(): void;
  }

  export class WebGLRenderer {
    constructor(params?: { antialias?: boolean; alpha?: boolean });
    domElement: HTMLCanvasElement;
    outputColorSpace: string;
    setPixelRatio(value: number): void;
    setSize(width: number, height: number, updateStyle?: boolean): void;
    render(scene: Scene, camera: PerspectiveCamera): void;
    dispose(): void;
  }

  export class AmbientLight {
    constructor(color?: number, intensity?: number);
  }

  export class DirectionalLight {
    constructor(color?: number, intensity?: number);
    position: Vector3;
  }

  export class HemisphereLight {
    constructor(skyColor?: number, groundColor?: number, intensity?: number);
  }

  export class BoxGeometry {
    constructor(width?: number, height?: number, depth?: number);
    dispose(): void;
  }

  export class MeshLambertMaterial {
    constructor(params?: {
      color?: string | number;
      transparent?: boolean;
      opacity?: number;
      emissive?: string | number;
      depthWrite?: boolean;
    });
    dispose(): void;
  }

  export class InstancedMesh {
    constructor(geometry: BoxGeometry, material: MeshLambertMaterial, count: number);
    geometry: BoxGeometry;
    material: MeshLambertMaterial | MeshLambertMaterial[];
    instanceMatrix: { needsUpdate: boolean };
    setMatrixAt(index: number, matrix: object): void;
  }

  export class GridHelper {
    constructor(size: number, divisions: number, color1?: number, color2?: number);
    position: Vector3;
  }
}

declare module 'three/addons/controls/OrbitControls.js' {
  import type { PerspectiveCamera } from 'three';

  export class OrbitControls {
    constructor(object: PerspectiveCamera, domElement?: HTMLElement);
    enableDamping: boolean;
    dampingFactor: number;
    maxPolarAngle: number;
    target: { set(x: number, y: number, z: number): void };
    update(): boolean;
    dispose(): void;
  }
}
