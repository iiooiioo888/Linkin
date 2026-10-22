import { useEffect, useState } from 'react';
import { fetchHostResources, type HostResourceSample } from '../api/client';

/** 輪詢主機資源。失敗時保留上一筆，避免環突然變回估算值。 */
export function useHostResources(intervalMs = 8000): HostResourceSample | null {
  const [host, setHost] = useState<HostResourceSample | null>(null);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const next = await fetchHostResources();
        if (!stop) setHost(next);
      } catch {
        if (!stop) setHost((prev) => prev ?? { available: false });
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), intervalMs);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [intervalMs]);

  return host;
}
