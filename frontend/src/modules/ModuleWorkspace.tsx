/**
 * 模組宿主：依 GET /modules 目錄 + 前端頁面註冊表渲染。
 * 新模組只要 registerModulePages + 後端 ModuleSpec，不必改控制台。
 */
import { lazy, Suspense, useMemo } from 'react';
import { getWorldModule } from '../lib/worldModules';
import { getModulePageLoader } from './pageRegistry';
import type { ModulePageProps } from './types';

function PanelFallback() {
  return (
    <div className="flex flex-1 items-center justify-center text-[12px] text-[#8E8E93]">
      載入模組…
    </div>
  );
}

function UnknownModulePage({ moduleId, page }: Pick<ModulePageProps, 'moduleId' | 'page'>) {
  const spec = getWorldModule(moduleId);
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
      <p className="text-[13px] font-medium text-[#F5F5F7]">{spec?.title ?? moduleId}</p>
      <p className="max-w-md text-[12px] text-[#8E8E93]">
        頁面「{page}」尚未接上前端畫面。
        {spec?.apiPrefix ? ` 此模組 API 前綴為 ${spec.apiPrefix}，可先用統一目錄 /modules/${moduleId} 對接。` : ''}
      </p>
    </div>
  );
}

export default function ModuleWorkspace({ moduleId, page, focusAgentId, onFocusAgent }: ModulePageProps) {
  const Loader = useMemo(() => {
    const load = getModulePageLoader(moduleId, page);
    return load ? lazy(load) : null;
  }, [moduleId, page]);

  if (!Loader) {
    return <UnknownModulePage moduleId={moduleId} page={page} />;
  }

  return (
    <Suspense fallback={<PanelFallback />}>
      <Loader moduleId={moduleId} page={page} focusAgentId={focusAgentId} onFocusAgent={onFocusAgent} />
    </Suspense>
  );
}
