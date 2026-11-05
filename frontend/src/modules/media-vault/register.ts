import { registerModulePages } from '../pageRegistry';

export function registerMediaVaultModule(): void {
  registerModulePages('media-vault', {
    gallery: () => import('./MediaVaultShell'),
    monitor: () => import('./MediaVaultShell'),
  });
}
