/**
 * 取消任務後同步前端快照：成功或「已結束」錯誤皆拉最新狀態。
 */
import { cancelTask, fetchTask } from '../api/client';
import type { TaskProgress } from '../types';
import { isTaskAlreadyEndedError } from './chatWorkspace';

export interface CancelTaskSyncResult {
  task: TaskProgress | null;
  error: string | null;
}

export async function cancelTaskAndSync(taskId: string): Promise<CancelTaskSyncResult> {
  try {
    await cancelTask(taskId);
  } catch (err) {
    const msg = (err as Error).message;
    if (!isTaskAlreadyEndedError(msg)) {
      return { task: null, error: msg };
    }
  }
  try {
    const task = await fetchTask(taskId);
    return { task, error: null };
  } catch {
    return { task: null, error: null };
  }
}
