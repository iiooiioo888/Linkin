import { useEffect, useState } from 'react';
import MediaCrawlerPanel from '../../components/MediaCrawlerPanel';
import { fetchMediaVaultControlOverview, type MediaVaultControlOverview } from '../../lib/mediaVaultApi';
import { consoleLayout } from '../../lib/consoleLayout';

type Props = {
  onOpenGallery: (batchId: string) => void;
  onOpenMonitor: (batchId: string) => void;
};

export default function ControlPanel({ onOpenGallery, onOpenMonitor }: Props) {
  const [overview, setOverview] = useState<MediaVaultControlOverview | null>(null);

  useEffect(() => {
    fetchMediaVaultControlOverview()
      .then(setOverview)
      .catch(() => setOverview(null));
  }, []);

  const vault = overview?.vault;
  const mc = overview?.mediacrawler;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4" data-testid="media-vault-control">
      <header>
        <h1 className="text-[15px] font-semibold text-[var(--console-ink)]">採集控制</h1>
        <p className="text-[11px] text-[var(--console-sub)]">MediaCrawler 任務 → 媒資庫入庫</p>
      </header>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="今日入庫" value={vault ? String(vault.today_ingested) : '—'} />
        <Kpi label="媒資總數" value={vault ? String(vault.total_posts) : '—'} />
        <Kpi
          label="任務成功率"
          value={
            vault?.success_rate != null ? `${Math.round(vault.success_rate * 100)}%` : mc ? '—' : '…'
          }
        />
        <Kpi label="運行中任務" value={mc ? String(mc.running_jobs ?? 0) : '—'} />
      </div>

      <MediaCrawlerPanel embedded onOpenGallery={onOpenGallery} onOpenMonitor={onOpenMonitor} />
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className={`${consoleLayout.insetCard} p-3`}>
      <p className="text-[10px] uppercase tracking-wide text-[var(--console-sub)]">{label}</p>
      <p className="text-[18px] font-semibold text-[var(--console-ink)]" data-testid="media-vault-stat">
        {value}
      </p>
    </div>
  );
}
