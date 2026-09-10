import type { ComponentType } from 'react';
import type { ModulePageLoader } from './pageRegistry';
import type { ModulePageProps } from './types';

/** 既有面板不吃 module props；包一層以免 extra props 影響型別。 */
export function wrapPanel(loader: () => Promise<{ default: ComponentType }>): ModulePageLoader {
  return async () => {
    const mod = await loader();
    const Inner = mod.default;
    function Wrapped(_props: ModulePageProps) {
      return <Inner />;
    }
    return { default: Wrapped };
  };
}
