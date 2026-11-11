/**
 * 任務面板型別：TaskPanelProps、角色狀態與看板分組。
 */

import type { KanbanItem, TaskProgress } from '../../types';

export interface TaskPanelProps {
  task: TaskProgress;
  /** 設定後顯示「開啟任務頁面」按鈕 */
  onOpenFull?: () => void;
  /** 取消任務回調 */
  onCancel?: (taskId: string) => void;
  /** 斷點續跑回調 */
  onResume?: (taskId: string) => void;
  /** 查看執行軌跡回調 */
  onOpenTrace?: (taskId: string) => void;
  /** 開啟對話底部詳細區 Context（組成／趨勢／瀏覽器） */
  onOpenContext?: (taskId: string) => void;
  /** 對話流已由 ChatView portal 決策列接管時隱藏，避免重複 */
  hideDecision?: boolean;
}

// ── 角色狀態（對應 PysdnOPC 芯片圖標） ──

export type RoleStatus = 'pending' | 'active' | 'waiting' | 'done' | 'failed';

export type RoleWorkGroup = {
  role: string;
  status: RoleStatus;
  entries: Array<{ status: string; item: KanbanItem }>;
};
