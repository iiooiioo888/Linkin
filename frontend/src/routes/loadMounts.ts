/**
 * 讀取 frontend/src/routes/mounts/*.ts。
 * 四個入口都由掛載檔提供；glob 不到時該入口維持未接上。
 */
import { listSurfaces, type SurfaceEntry, type SurfaceMountModule } from './catalog';

const modules = import.meta.glob('./mounts/*.ts', { eager: true }) as Record<
  string,
  Partial<SurfaceMountModule>
>;

export function loadSurfaces(): SurfaceEntry[] {
  return listSurfaces(modules);
}
