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
  onNewSession?: () => void;
}

export function ChatNav({
  title,
  showMonitor,
  isMobile,
  monitorSheetOpen,
  setMonitorSheetOpen,
  openContextDetail,
  onOpenSettings,
  onNewSession,
}: ChatNavProps) {
  return (
    <nav className="ws-nav">
      <div className="ws-crumb">
        {title ? <strong>{title}</strong> : null}
      </div>
      <div className="ws-nav-acts">
        {onNewSession && (
          <button type="button" className="ws-btn" onClick={onNewSession}>
            新對話
          </button>
        )}
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
            <svg className="ws-ico" viewBox="0 0 24 24" aria-hidden>
              <circle cx="12" cy="12" r="3" />
              <path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6" />
            </svg>
          </button>
        )}
      </div>
    </nav>
  );
}
