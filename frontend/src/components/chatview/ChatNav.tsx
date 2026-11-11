/**
 * ChatView 頂部導覽列（麵包屑、監控／上下文／設定）。
 */
import type { Dispatch, SetStateAction } from 'react';

interface ChatNavProps {
  title: string;
  showMonitor: boolean;
  isMobile: boolean;
  monitorSheetOpen: boolean;
  setMonitorSheetOpen: Dispatch<SetStateAction<boolean>>;
  openContextDetail: () => void;
  onOpenSettings?: () => void;
}

export function ChatNav({
  title,
  showMonitor,
  isMobile,
  monitorSheetOpen,
  setMonitorSheetOpen,
  openContextDetail,
  onOpenSettings,
}: ChatNavProps) {
  return (
    <nav className="ws-nav">
      <div className="ws-crumb">
        {title ? (
          <>
            對話 / <strong>{title}</strong>
          </>
        ) : (
          <strong>對話</strong>
        )}
      </div>
      <div className="ws-nav-acts">
        {showMonitor && isMobile && (
          <button
            type="button"
            className="ws-btn ws-btn-primary md:hidden touch-manipulation"
            onClick={() => setMonitorSheetOpen((v) => !v)}
            data-testid="chat-monitor-sheet-toggle"
            aria-expanded={monitorSheetOpen}
          >
            監控
          </button>
        )}
        <button
          type="button"
          className="ws-btn"
          onClick={() => openContextDetail()}
          data-testid="chat-nav-context"
          title="查看這段對話用到的資料"
        >
          上下文
        </button>
        {onOpenSettings && (
          <button type="button" className="ws-btn ws-btn-icon" onClick={onOpenSettings} aria-label="設定">
            ⚙
          </button>
        )}
      </div>
    </nav>
  );
}
