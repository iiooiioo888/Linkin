import { registerModulePages } from '../pageRegistry';

export function registerLocalVideoStudioModule(): void {
  registerModulePages('local-video-studio', {
    projects: () => import('./StudioHub'),
    detail: () => import('./StudioHub'),
    shots: () => import('./StudioHub'),
    jobs: () => import('./StudioHub'),
    review: () => import('./StudioHub'),
    compose: () => import('./StudioHub'),
    resources: () => import('./StudioHub'),
    home: () => import('./StudioHub'),
    '*': () => import('./StudioHub'),
  });
}
