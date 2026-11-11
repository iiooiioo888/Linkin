/**
 * ChatView 右側任務監控（含行動版 backdrop 與快照讀取中 placeholder）。
 */
import type { Dispatch, SetStateAction } from 'react';
import ChatTaskMonitor from '../ChatTaskMonitor';
import type { ChatMessage, RahoPendingDecision, TaskProgress } from '../../types';

interface ChatMonitorSideProps {
  isMobile: boolean;
  monitorSheetOpen: boolean;
  setMonitorSheetOpen: Dispatch<SetStateAction<boolean>>;
  showMonitor: boolean;
  live: ChatMessage | null;
  task: TaskProgress | null | undefined;
  pending: RahoPendingDecision[];
  running: boolean;
  now: number;
  onOpenTask: (messageId: string) => void;
  onOpenTrace?: (taskId: string) => void;
  openContextDetail: (preferTaskId?: string | null) => void;
  handlePause: () => Promise<void>;
  handleResume: () => Promise<void>;
}

export function ChatMonitorSide({
  isMobile,
  monitorSheetOpen,
  setMonitorSheetOpen,
  showMonitor,
  live,
  task,
  pending,
  running,
  now,
  onOpenTask,
  onOpenTrace,
  openContextDetail,
  handlePause,
  handleResume,
}: ChatMonitorSideProps) {
  return (
    <>
    {isMobile && monitorSheetOpen && showMonitor && (
      <button
        type="button"
        className="ws-monitor-backdrop md:hidden"
        aria-label="關閉任務監控"
        onClick={() => setMonitorSheetOpen(false)}
      />
    )}
    {showMonitor && live && task && (
      <ChatTaskMonitor
        task={task}
        pending={pending}
        running={running}
        now={now}
        onOpenTask={() => onOpenTask(live.id)}
        onOpenTrace={onOpenTrace}
        onOpenContext={() => openContextDetail(task.task_id)}
        onPause={() => void handlePause()}
        onResume={() => void handleResume()}
      />
    )}
    {showMonitor && live && !task && (
      <aside className="ws-side" aria-label="任務監控" data-testid="chat-task-monitor">
        <div className="ws-side-h">
          <div>
            <p className="ws-side-k">任務監控</p>
            <p className="ws-side-t">讀取任務快照</p>
          </div>
        </div>
        <div className="ws-side-scroll">
          <p className="ws-empty">正在讀取這次任務</p>
        </div>
      </aside>
    )}
    </>
  );
}
