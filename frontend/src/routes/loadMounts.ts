/**
 * 讀取 frontend/src/routes/mounts/*.ts。
 * chat 由本分支提供；其餘掛載由別的分支加入。glob 不到時該入口維持未接上。
 */
import { listSurfaces, type SurfaceEntry, type SurfaceMountModule } from './catalog';

const modules = import.meta.glob('./mounts/*.ts', { eager: true }) as Record<
  string,
  Partial<SurfaceMountModule>
>;

export function loadSurfaces(): SurfaceEntry[] {
  return listSurfaces(modules);
}
