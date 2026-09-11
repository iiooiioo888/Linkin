/**
 * BillingPanel — 雲端費用儀表盤。
 *
 * 顯示 Docker 按時計費 + 阿里雲 BSS 帳目、各服務費用佔比。
 * 卡片分組：總覽 / 組成 / 接入狀態 / 產品明細。
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { fetchCloudBilling } from '../api/client';
import type { CloudBilling, CloudServiceCost } from '../types';
import { useFixedPages, usePagination } from '../lib/pagination';
import { ConsolePageFrame, ConsolePagination } from './ui/ConsolePagination';
import { PanelSection, PanelShell, consoleLayout } from './ui/ConsoleLayout';

function formatCost(amount: number): string {
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  if (amount < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(2)}`;
}

function StatCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: 'green' | 'amber' | 'blue' | 'orange' | 'violet';
}) {
  const valueCls =
    accent === 'green'
      ? 'text-[#34C759]'
      : accent === 'amber'
        ? 'text-[#FF9500]'
        : accent === 'blue'
          ? 'text-[#007AFF]'
          : accent === 'orange'
            ? 'text-[#FF9500]'
            : accent === 'violet'
              ? 'text-[#64D2FF]'
              : 'text-[#F5F5F7]';
  return (
    <div className="apple-card apple-card--pad">
      <p className="apple-title">{label}</p>
      <p className={`apple-data mt-2 text-[26px] ${valueCls}`}>{value}</p>
      {hint && <p className="mt-2 text-[11px] font-normal text-[#8E8E93]">{hint}</p>}
    </div>
  );
}

function SectionCard({
  title,
  hint,
  children,
  action,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className={consoleLayout.card}>
      <div className={`flex flex-wrap items-center justify-between gap-2 ${consoleLayout.cardHeader} normal-case tracking-normal`}>
        <div>
          <h3 className="apple-heading text-[14px]">{title}</h3>
          {hint && <p className="mt-1 text-[11px] font-normal text-[#8E8E93]">{hint}</p>}
        </div>
        {action}
      </div>
      <div className={consoleLayout.cardBody}>{children}</div>
    </section>
  );
}

function ServiceCostCard({ svc, maxCost }: { svc: CloudServiceCost; maxCost: number }) {
  const pct = maxCost > 0 ? (svc.cost / maxCost) * 100 : 0;
  const isAliyun = svc.source === 'aliyun';
  return (
    <div className="apple-inset p-3">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-gray-200">
            {svc.product_name || svc.service}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] ${
                isAliyun
                  ? 'bg-orange-500/15 text-orange-300'
                  : 'bg-blue-500/15 text-blue-300'
              }`}
            >
              {isAliyun ? '阿里雲' : 'Docker'}
            </span>
            {!isAliyun && (
              <span className="text-[11px] text-gray-500">
                ${svc.rate.toFixed(3)}/h · {svc.uptime_hours}h
              </span>
            )}
            {isAliyun && svc.pretax_amount_cny != null && (
              <span className="text-[11px] text-gray-500">
                ¥{Number(svc.pretax_amount_cny).toFixed(2)}
              </span>
            )}
          </div>
        </div>
        <span className="shrink-0 font-mono text-sm font-semibold text-amber-300">
          {formatCost(svc.cost)}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-gray-800">
        <div
          className={`h-full rounded-full transition-all ${
            isAliyun
              ? 'bg-gradient-to-r from-orange-500 to-orange-300'
              : 'bg-gradient-to-r from-blue-500 to-sky-300'
          }`}
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
    </div>
  );
}

export default function BillingPanel({ embedded = false }: { embedded?: boolean }) {
  const [billing, setBilling] = useState<CloudBilling | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<'all' | 'docker' | 'aliyun'>('all');

  const refresh = useCallback(async () => {
    try {
      const data = await fetchCloudBilling();
      setBilling(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => clearInterval(timer);
  }, [refresh]);

  const aliyun = billing?.aliyun;
  const breakdown = billing?.breakdown;

  const filteredServices = useMemo(() => {
    const list = billing?.per_service ?? [];
    if (sourceFilter === 'all') return list;
    return list.filter((s) => (s.source || 'docker') === sourceFilter);
  }, [billing?.per_service, sourceFilter]);

  const dockerCount = billing?.per_service.filter((s) => (s.source || 'docker') !== 'aliyun').length ?? 0;
  const aliyunCount = billing?.per_service.filter((s) => s.source === 'aliyun').length ?? 0;

  const embeddedPager = useFixedPages(4);
  const servicePager = usePagination(filteredServices, 4);

  if (loading && !billing) {
    return (
      <div className={embedded ? 'py-8 text-center' : 'flex flex-1 items-center justify-center'}>
        <span className="text-sm text-gray-500">加載費用數據...</span>
      </div>
    );
  }

  const show = (page: number) => !embedded || embeddedPager.page === page;

  const body = (
      <PanelSection>
      {show(1) && (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="今日費用"
          value={billing ? formatCost(billing.today_total) : '--'}
          hint="Docker＋阿里雲"
          accent="green"
        />
        <StatCard
          label="本月費用"
          value={billing ? formatCost(billing.month_total) : '--'}
          hint="雲資源合計 USD"
          accent="amber"
        />
        <StatCard
          label="即時合計"
          value={billing ? formatCost(billing.total_now) : '--'}
          hint="目前累計雲資源"
          accent="violet"
        />
        <StatCard
          label="月度預估"
          value={billing ? formatCost(billing.month_projected) : '--'}
          hint="依 Docker 小時費率推估"
          accent="blue"
        />
      </div>
      )}

      {show(2) && (
      <SectionCard title="費用組成" hint="雲服務預算只計下列資源；AI 使用預算另計 LLM API">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatCard
            label="Docker"
            value={breakdown ? formatCost(breakdown.docker_usd) : '--'}
            hint="本地容器按時計費"
            accent="blue"
          />
          <StatCard
            label="阿里雲"
            value={breakdown ? formatCost(breakdown.aliyun_usd) : '--'}
            hint={
              aliyun?.configured
                ? aliyun.ok
                  ? `帳期 ${aliyun.billing_cycle} · ¥${aliyun.month_total_cny.toFixed(2)}`
                  : '查詢失敗'
                : '未配置 AccessKey'
            }
            accent="orange"
          />
          <StatCard
            label="雲資源小計"
            value={breakdown ? formatCost(breakdown.cloud_total_usd) : '--'}
            hint="Docker＋阿里雲"
            accent="green"
          />
        </div>
      </SectionCard>
      )}

      {show(2) && error && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/15 px-4 py-2 text-sm text-red-300">
          ⚠ {error}
          <button onClick={() => void refresh()} className="ml-3 underline">
            重試
          </button>
        </div>
      )}

      {show(3) && aliyun && (
        <SectionCard
          title="阿里雲 BSS 接入"
          hint={`環境變數 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET · CNY→USD 匯率 ${aliyun.cny_usd_rate}`}
          action={
            <span
              className={`rounded px-2 py-0.5 text-[11px] ${
                aliyun.configured && aliyun.ok
                  ? 'bg-green-500/15 text-green-300'
                  : aliyun.configured
                    ? 'bg-amber-500/15 text-amber-300'
                    : 'bg-gray-700/50 text-gray-400'
              }`}
            >
              {aliyun.configured && aliyun.ok
                ? '已連線'
                : aliyun.configured
                  ? '已配置但查詢失敗'
                  : '未接入'}
            </span>
          }
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              label="本月 CNY"
              value={`¥${aliyun.month_total_cny.toFixed(2)}`}
              hint={`帳期 ${aliyun.billing_cycle || '—'}`}
              accent="orange"
            />
            <StatCard
              label="本月 USD"
              value={formatCost(aliyun.month_total_usd)}
              hint={`匯率 ${aliyun.cny_usd_rate}`}
              accent="amber"
            />
            <StatCard
              label="今日 CNY"
              value={`¥${aliyun.today_total_cny.toFixed(2)}`}
              hint="粗估分攤"
            />
            <StatCard
              label="今日 USD"
              value={formatCost(aliyun.today_total_usd)}
              hint="計入 Agent 雲資源"
              accent="green"
            />
          </div>
          {aliyun.error && (
            <p className="mt-3 text-[11px] text-amber-200/90">{aliyun.error}</p>
          )}
          {(aliyun.products?.length ?? 0) > 0 && (
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {aliyun.products.map((p) => (
                <div
                  key={`${p.product_code}-${p.product_name}`}
                  className="rounded-lg border border-orange-500/15 bg-orange-500/5 px-3 py-2"
                >
                  <p className="truncate text-[12px] font-medium text-gray-200">{p.product_name}</p>
                  <p className="mt-0.5 text-[10px] text-gray-500">{p.product_code}</p>
                  <div className="mt-1.5 flex items-baseline justify-between">
                    <span className="text-[11px] text-gray-500">¥{p.pretax_amount_cny.toFixed(2)}</span>
                    <span className="font-mono text-[12px] text-orange-300">{formatCost(p.cost_usd)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      )}

      {show(4) && billing && billing.per_service.length > 0 && (
        <SectionCard
          title="各服務／產品費用明細"
          hint={`${dockerCount} Docker · ${aliyunCount} 阿里雲產品`}
          action={
            <div className="flex gap-1 rounded-md border border-gray-800 bg-gray-950/50 p-0.5">
              {([
                ['all', '全部'],
                ['docker', 'Docker'],
                ['aliyun', '阿里雲'],
              ] as const).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSourceFilter(key)}
                  className={`rounded px-2 py-0.5 text-[11px] ${
                    sourceFilter === key
                      ? 'bg-gray-700 text-gray-100'
                      : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          }
        >
          {filteredServices.length === 0 ? (
            <p className="text-sm text-gray-500">此篩選下暫無明細</p>
          ) : (
            <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
              {(embedded ? servicePager.slice : filteredServices).map((svc) => (
                <ServiceCostCard
                  key={`${svc.source || 'docker'}-${svc.service}`}
                  svc={svc}
                  maxCost={billing.per_service[0]?.cost ?? 1}
                />
              ))}
            </div>
          )}
          {embedded ? (
            <ConsolePagination
              page={servicePager.page}
              totalPages={servicePager.pages}
              onPageChange={servicePager.setPage}
              className="!border-0"
            />
          ) : null}
          <div className="mt-3 flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2.5">
            <span className="text-sm font-medium text-gray-300">雲資源總計</span>
            <span className="text-sm font-bold text-amber-300">{formatCost(billing.total_now)}</span>
          </div>
        </SectionCard>
      )}

      {show(4) && billing && billing.per_service.length === 0 && (
        <SectionCard title="暫無雲資源費用">
          <p className="text-sm text-gray-300">尚無 Docker 或阿里雲帳單資料</p>
          <p className="mt-1 text-xs text-gray-500">
            啟動 Compose 容器後開始 Docker 按時計費；配置阿里雲 AccessKey 後拉取 BSS 帳單。
          </p>
        </SectionCard>
      )}
      </PanelSection>
  );

  if (embedded) {
    return (
      <ConsolePageFrame
        page={embeddedPager.page}
        totalPages={embeddedPager.pages}
        onPageChange={(p) => {
          embeddedPager.setPage(p);
          if (p === 4) servicePager.reset();
        }}
      >
        {body}
      </ConsolePageFrame>
    );
  }
  return <PanelShell>{body}</PanelShell>;
}
