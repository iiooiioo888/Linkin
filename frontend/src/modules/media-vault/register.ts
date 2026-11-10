import { registerModulePages } from '../pageRegistry';

export function registerMediaVaultModule(): void {
  registerModulePages('media-vault', {
    control: () => import('./MediaVaultHub'),
    gallery: () => import('./MediaVaultHub'),
    monitor: () => import('./MediaVaultHub'),
    '*': () => import('./MediaVaultHub'),
  });
}
