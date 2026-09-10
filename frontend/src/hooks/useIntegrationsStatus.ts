/**
 * 外部整合狀態輪詢（fail-open：失敗時保留上次資料，不阻斷 UI）。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchIntegrations, type IntegrationStatus } from '../api/integrations';

export function useIntegrationsStatus(pollMs = 12000): {
  items: IntegrationStatus[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
} {
  const [items, setItems] = useState<IntegrationStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const next = await fetchIntegrations();
      setItems(next);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // pollMs < 0：完全不請求（由父層注入 items）
    if (pollMs < 0) {
      setLoading(false);
      return;
    }
    void reload();
    if (pollMs === 0) return;
    const t = setInterval(() => void reload(), pollMs);
    return () => clearInterval(t);
  }, [reload, pollMs]);

  return { items, loading, error, reload };
}
