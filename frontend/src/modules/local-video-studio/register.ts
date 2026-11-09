import { registerModulePages } from '../pageRegistry';

export function registerLocalVideoStudioModule(): void {
  registerModulePages('local-video-studio', {
    home: () => import('./LocalVideoStudioShell'),
    '*': () => import('./LocalVideoStudioShell'),
  });
}
