/**
 * AlertsPanel — 告警規則管理面板。
 *
 * 支援創建/刪除/啟停 CPU 與記憶體閾值告警規則，
 * 以及查看最近的告警觸發歷史。
 */
import { useCallback, useEffect, useState } from 'react';
import { createAlertRule, deleteAlertRule, fetchCloudAlerts, toggleAlertRule } from '../api/client';
import type { CloudAlertRecord, CloudAlertRule } from '../types';

export default function AlertsPanel({ embedded = false }: { embedded?: boolean }) {
  const [rules, setRules] = useState<CloudAlertRule[]>([]);
  const [history, setHistory] = useState<CloudAlertRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // 新建表單
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState('');
  const [formMetric, setFormMetric] = useState('cpu');
  const [formThreshold, setFormThreshold] = useState('80');
  const [formService, setFormService] = useState('*');

  const refresh = useCallback(async () => {
    try {
      const data = await fetchCloudAlerts();
      setRules(data.rules);
      setHistory(data.history);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleCreate = useCallback(async () => {
    if (!formName.trim()) return;
    setSaving(true);
    try {
      await createAlertRule({
        name: formName.trim(),
        metric: formMetric,
        threshold: Number(formThreshold),
        service: formService,
      });
      setShowForm(false);
      setFormName('');
      setFormThreshold('80');
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }, [formName, formMetric, formThreshold, formService, refresh]);

  const handleToggle = useCallback(
    async (ruleId: string) => {
      try {
        await toggleAlertRule(ruleId);
        await refresh();
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [refresh],
  );

  const handleDelete = useCallback(
    async (ruleId: string) => {
      try {
        await deleteAlertRule(ruleId);
        await refresh();
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [refresh],
  );

  return (
    <div className={embedded ? 'space-y-3' : 'flex-1 space-y-4 overflow-auto p-4'}>
      {/* 標題欄 */}
      <div className="flex items-center justify-between">
        {!embedded ? <h3 className="text-sm font-medium text-gray-200">告警規則</h3> : <span />}
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-lg bg-blue-500/20 px-3 py-1.5 text-xs text-blue-300 transition-colors hover:bg-blue-500/30"
        >
          {showForm ? '取消' : '+ 新增規則'}
        </button>
      </div>

      {/* 錯誤提示 */}
      {error && (
        <div className="rounded-lg bg-red-500/15 px-4 py-2 text-sm text-red-300">
          ⚠ {error}
          <button onClick={() => void refresh()} className="ml-3 underline">重試</button>
        </div>
      )}

      {/* 新建規則表單 */}
      {showForm && (
        <div className="rounded-lg border border-gray-800 bg-gray-900/80 p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <div>
              <label className="mb-1 block text-[11px] text-gray-500">名稱</label>
              <input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="CPU 過高告警"
                className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-200 placeholder-gray-600"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-gray-500">指標</label>
              <select
                value={formMetric}
                onChange={(e) => setFormMetric(e.target.value)}
                className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-200"
              >
                <option value="cpu">CPU (%)</option>
                <option value="memory">記憶體 (MB)</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-gray-500">閾值</label>
              <input
                value={formThreshold}
                onChange={(e) => setFormThreshold(e.target.value)}
                type="number"
                className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-200"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-gray-500">服務</label>
              <input
                value={formService}
                onChange={(e) => setFormService(e.target.value)}
                placeholder="* = 全部"
                className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-200"
              />
            </div>
          </div>
          <button
            onClick={() => void handleCreate()}
            disabled={saving || !formName.trim()}
            className="mt-3 rounded-lg bg-green-500/20 px-4 py-1.5 text-xs text-green-300 transition-colors hover:bg-green-500/30 disabled:opacity-40"
          >
            {saving ? '創建中...' : '✓ 創建'}
          </button>
        </div>
      )}

      {/* 規則列表 */}
      {loading ? (
        <div className="flex justify-center py-8">
          <span className="text-sm text-gray-500">加載中...</span>
        </div>
      ) : rules.length === 0 ? (
        <div className="flex flex-col items-center py-12 text-center">
          <span className="mb-2 text-4xl">⚠️</span>
          <p className="text-sm text-gray-500">暫無告警規則</p>
          <p className="text-xs text-gray-600">點擊上方按鈕創建第一條規則</p>
        </div>
      ) : (
        <div className="space-y-2">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className={`flex items-center justify-between rounded-lg border p-3 ${
                rule.enabled
                  ? 'border-gray-800 bg-gray-900/80'
                  : 'border-gray-800/50 bg-gray-900/40'
              }`}
            >
              <div className="flex items-center gap-3">
                {/* 啟用指示燈 */}
                <span
                  className={`inline-block h-2.5 w-2.5 rounded-full ${
                    rule.enabled ? 'bg-green-400' : 'bg-gray-600'
                  }`}
                />
                <div>
                  <p className={`text-sm font-medium ${rule.enabled ? 'text-gray-200' : 'text-gray-500'}`}>
                    {rule.name}
                  </p>
                  <p className="text-[11px] text-gray-500">
                    {rule.metric === 'cpu' ? 'CPU' : '記憶體'} &gt; {rule.threshold}
                    {rule.metric === 'cpu' ? '%' : ' MB'}
                    {' · '}
                    服務: {rule.service}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => void handleToggle(rule.id)}
                  className={`rounded-md px-2.5 py-1 text-[11px] transition-colors ${
                    rule.enabled
                      ? 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                      : 'bg-green-500/10 text-green-400 hover:bg-green-500/20'
                  }`}
                >
                  {rule.enabled ? '停用' : '啟用'}
                </button>
                <button
                  onClick={() => void handleDelete(rule.id)}
                  className="rounded-md bg-red-500/10 px-2.5 py-1 text-[11px] text-red-400 transition-colors hover:bg-red-500/20"
                >
                  刪除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 告警歷史（無資料也保留區塊） */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-gray-200">觸發歷史</h3>
        {history.length === 0 ? (
          <div className="rounded-lg border border-gray-800 bg-gray-900/80 px-4 py-8 text-center">
            <p className="text-sm text-gray-500">尚無觸發紀錄</p>
            <p className="mt-1 text-xs text-gray-600">規則啟用後，超過閾值會寫入此時間線</p>
          </div>
        ) : (
          <div className="max-h-64 space-y-1.5 overflow-auto rounded-lg border border-gray-800 bg-gray-900/80 p-2">
            {history.map((h, i) => (
              <div
                key={`${h.rule_id}-${h.ts}-${i}`}
                className="flex items-center justify-between rounded-md bg-gray-950/60 px-3 py-1.5"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium text-red-300">{h.rule_name}</span>
                  <span className="text-[11px] text-gray-500">
                    {h.service} · {h.metric}={h.value}
                    {h.metric === 'cpu' ? '%' : 'MB'} &gt; {h.threshold}
                  </span>
                </div>
                <span className="text-[10px] text-gray-600">
                  {new Date(h.ts).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}