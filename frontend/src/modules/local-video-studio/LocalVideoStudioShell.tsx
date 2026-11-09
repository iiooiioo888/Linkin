import type { ModulePageProps } from '../types';

/** M0 空殼：僅展示模組標題與 health 提示，不做 CRUD／渲染。 */
export default function LocalVideoStudioShell({ moduleId, page }: ModulePageProps) {
  return (
    <div
      className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 px-6 text-center"
      data-testid="local-video-studio-shell"
    >
      <p className="text-[18px] font-semibold text-[var(--console-ink)]">Local Video Studio</p>
      <p className="max-w-md text-[13px] text-[var(--console-sub)]">
        本機優先 AI 影片工作室骨架（里程碑 M0）。後續將提供專案／鏡頭板／任務與審核；目前僅 health
        探針可用。
      </p>
      <p className="font-mono text-[11px] text-[var(--console-sub)]">
        {moduleId}/{page || 'home'} · GET /local-video-studio/health → {'{ok:true}'}
      </p>
      <p className="max-w-lg text-[11px] text-[var(--console-sub)]">
        規格：倉庫根目錄 PROJECT_SPEC.md · 媒資庫可參考{' '}
        <a className="text-[var(--console-accent)] hover:underline" href="#/modules/media-vault">
          Media Vault
        </a>
      </p>
    </div>
  );
}
