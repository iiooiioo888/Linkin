/** MemoryPanel — 記憶庫管理面板。
 *
 * 列出向量記憶庫中的記憶，支援：
 * - 分頁瀏覽（按建立時間降序）
 * - 刪除單條記憶
 * - 批量清理過期/低品質記憶
 */
import { useCallback, useEffect, useState } from 'react';
import { cleanupMemories, deleteMemory, fetchMemories } from '../api/client';
import type { MemoryItem } from '../api/client';

interface MemoryPanelProps {
  onClose?: () => void;
}

export default function MemoryPanel({ onClose }: MemoryPanelProps) {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMemories(100, 0);
      setMemories(data.memories);
      setTotal(data.total);
      if (data.error) setError(data.error);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await deleteMemory(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      setTotal((prev) => prev - 1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setDeletingId(null);
    }
  };

  const handleCleanup = async () => {
    setCleaning(true);
    setCleanupResult(null);
    try {
      const result = await cleanupMemories(30);
      setCleanupResult(`已清理 ${result.deleted_count} 條過期記憶`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCleaning(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col apple-canvas text-[var(--console-ink)]">
      {/* 標題列 */}
      <div className="flex items-center justify-between border-b border-gray-800 p-3">
        <h3 className="text-sm font-medium text-gray-200">
          🧠 記憶庫 <span className="text-xs text-gray-500">（{total} 條）</span>
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => void handleCleanup()}
            disabled={cleaning || loading}
            className="rounded-md border border-gray-700 px-2 py-1 text-xs text-gray-300 transition-colors hover:bg-gray-800 disabled:opacity-40"
          >
            {cleaning ? '清理中...' : '🧹 清理過期'}
          </button>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="rounded-md border border-gray-700 px-2 py-1 text-xs text-gray-300 transition-colors hover:bg-gray-800 disabled:opacity-40"
          >
            {loading ? '...' : '🔄'}
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="rounded-md px-2 py-1 text-xs text-gray-400 hover:bg-gray-800"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* 錯誤 / 清理結果 */}
      {error && (
        <p className="border-b border-red-800 bg-red-900/30 px-3 py-2 text-xs text-red-300">
          ⚠️ {error}
        </p>
      )}
      {cleanupResult && (
        <p className="border-b border-green-800 bg-green-900/30 px-3 py-2 text-xs text-green-300">
          ✓ {cleanupResult}
        </p>
      )}

      {/* 記憶列表 */}
      <div className="flex-1 overflow-y-auto p-3">
        {loading && memories.length === 0 && (
          <p className="py-8 text-center text-xs text-gray-500">載入中...</p>
        )}
        {!loading && memories.length === 0 && (
          <div className="py-12 text-center">
            <span className="text-3xl">🧠</span>
            <p className="mt-2 text-xs text-gray-500">尚無記憶</p>
            <p className="mt-1 text-[11px] text-gray-600">
              完成反思任務後，成功經驗會自動存入記憶庫
            </p>
          </div>
        )}
        <div className="space-y-2">
          {memories.map((m) => {
            const meta = m.metadata || {};
            return (
              <div
                key={m.id}
                className="rounded-lg border border-gray-800 bg-gray-900/60 p-2.5"
              >
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-300">
                  {m.text.length > 300 ? `${m.text.slice(0, 300)}...` : m.text}
                </p>
                <div className="mt-1.5 flex items-center justify-between">
                  <span className="text-[10px] text-gray-600">
                    {String(meta.created_at ?? '').slice(0, 10)}
                    {meta.score != null && ` · 評分 ${String(meta.score)}`}
                    {meta.iterations != null && ` · 迭代 ${String(meta.iterations)}`}
                  </span>
                  <button
                    onClick={() => void handleDelete(m.id)}
                    disabled={deletingId === m.id}
                    className="rounded px-1.5 py-0.5 text-[10px] text-red-400 transition-colors hover:bg-red-900/30 disabled:opacity-40"
                  >
                    {deletingId === m.id ? '...' : '🗑 刪除'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}