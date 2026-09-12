/**
 * 布局預覽 — 原生 2D 俯視圖（map_plan、build brief、世界意圖），無需 Dynmap／MineMCP。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchMinecraftLayoutPreview,
  type LayoutPreviewData,
  type LayoutPreviewFeature,
} from '../../api/linkin';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  PanelAlert,
  PanelShell,
  SectionHeader,
} from '../../components/ui/ConsoleLayout';

type ViewTransform = { scale: number; tx: number; ty: number };

function featureAtPoint(
  features: LayoutPreviewFeature[],
  wx: number,
  wz: number,
): LayoutPreviewFeature | null {
  for (let i = features.length - 1; i >= 0; i -= 1) {
    const f = features[i];
    if (f.type === 'point') {
      const p = f.point!;
      const dx = wx - p.x;
      const dz = wz - p.z;
      if (dx * dx + dz * dz <= 9) return f;
    } else if (f.type === 'rect') {
      const r = f.rect!;
      if (wx >= r.x1 && wx <= r.x2 && wz >= r.z1 && wz <= r.z2) return f;
    } else if (f.type === 'polyline') {
      for (const p of f.polyline?.points ?? []) {
        const dx = wx - p.x;
        const dz = wz - p.z;
        if (dx * dx + dz * dz <= 16) return f;
      }
    }
  }
  return null;
}

function LayoutCanvas({
  data,
  selectedId,
  onSelect,
}: {
  data: LayoutPreviewData;
  selectedId: string | null;
  onSelect: (f: LayoutPreviewFeature | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 640, h: 420 });
  const [transform, setTransform] = useState<ViewTransform>({ scale: 1, tx: 0, ty: 0 });
  const dragRef = useRef<{ x: number; y: number; active: boolean }>({ x: 0, y: 0, active: false });
  const pinchRef = useRef<{ dist: number; scale: number } | null>(null);

  const bounds = data.bounds;
  const worldW = Math.max(1, bounds.x2 - bounds.x1);
  const worldD = Math.max(1, bounds.z2 - bounds.z1);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setSize({ w: rect.width, h: rect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const baseScale = useMemo(() => {
    const pad = 24;
    return Math.min((size.w - pad) / worldW, (size.h - pad) / worldD);
  }, [size, worldW, worldD]);

  const toScreen = useCallback(
    (wx: number, wz: number) => {
      const s = baseScale * transform.scale;
      const cx = size.w / 2 + transform.tx;
      const cy = size.h / 2 + transform.ty;
      const ox = (bounds.x1 + bounds.x2) / 2;
      const oz = (bounds.z1 + bounds.z2) / 2;
      return {
        x: cx + (wx - ox) * s,
        y: cy + (wz - oz) * s,
      };
    },
    [baseScale, bounds, size, transform],
  );

  const toWorld = useCallback(
    (sx: number, sy: number) => {
      const s = baseScale * transform.scale;
      const cx = size.w / 2 + transform.tx;
      const cy = size.h / 2 + transform.ty;
      const ox = (bounds.x1 + bounds.x2) / 2;
      const oz = (bounds.z1 + bounds.z2) / 2;
      return {
        x: ox + (sx - cx) / s,
        z: oz + (sy - cy) / s,
      };
    },
    [baseScale, bounds, size, transform],
  );

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    setTransform((t) => ({ ...t, scale: Math.min(8, Math.max(0.25, t.scale * factor)) }));
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    dragRef.current = { x: e.clientX, y: e.clientY, active: true };
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    dragRef.current = { x: e.clientX, y: e.clientY, active: true };
    setTransform((t) => ({ ...t, tx: t.tx + dx, ty: t.ty + dy }));
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (dragRef.current.active) {
      const moved =
        Math.abs(e.clientX - dragRef.current.x) + Math.abs(e.clientY - dragRef.current.y);
      if (moved < 6) {
        const rect = containerRef.current?.getBoundingClientRect();
        if (rect) {
          const sx = e.clientX - rect.left;
          const sy = e.clientY - rect.top;
          const w = toWorld(sx, sy);
          onSelect(featureAtPoint(data.features, w.x, w.z));
        }
      }
    }
    dragRef.current.active = false;
  };

  const onTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const [a, b] = [e.touches[0], e.touches[1]];
      const dist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      pinchRef.current = { dist, scale: transform.scale };
    }
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (e.touches.length === 2 && pinchRef.current) {
      const [a, b] = [e.touches[0], e.touches[1]];
      const dist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      const ratio = dist / pinchRef.current.dist;
      setTransform((t) => ({
        ...t,
        scale: Math.min(8, Math.max(0.25, pinchRef.current!.scale * ratio)),
      }));
    }
  };

  const onTouchEnd = () => {
    pinchRef.current = null;
  };

  const resetView = () => setTransform({ scale: 1, tx: 0, ty: 0 });

  const renderFeature = (f: LayoutPreviewFeature) => {
    const selected = f.id === selectedId;
    const stroke = selected ? '#f7f8f8' : f.color;
    const strokeW = selected ? 2.5 : 1.2;
    const opacity = f.label === 'planned' ? 0.85 : 1;

    if (f.type === 'rect' && f.rect) {
      const tl = toScreen(f.rect.x1, f.rect.z1);
      const br = toScreen(f.rect.x2, f.rect.z2);
      const w = br.x - tl.x;
      const h = br.y - tl.y;
      return (
        <g key={f.id} opacity={opacity}>
          <rect
            x={tl.x}
            y={tl.y}
            width={w}
            height={h}
            fill={`${f.color}33`}
            stroke={stroke}
            strokeWidth={strokeW}
            strokeDasharray={f.label === 'planned' ? '4 3' : undefined}
          />
          <title>{f.title}</title>
        </g>
      );
    }
    if (f.type === 'point' && f.point) {
      const p = toScreen(f.point.x, f.point.z);
      return (
        <g key={f.id} opacity={opacity}>
          <circle cx={p.x} cy={p.y} r={selected ? 7 : 5} fill={f.color} stroke={stroke} strokeWidth={strokeW} />
          <title>{f.title}</title>
        </g>
      );
    }
    if (f.type === 'polyline' && f.polyline) {
      const pts = f.polyline.points
        .map((pt) => {
          const s = toScreen(pt.x, pt.z);
          return `${s.x},${s.y}`;
        })
        .join(' ');
      const width = Math.max(1, (f.polyline.width ?? 1) * baseScale * transform.scale * 0.5);
      return (
        <g key={f.id} opacity={opacity}>
          <polyline
            points={pts}
            fill="none"
            stroke={stroke}
            strokeWidth={width}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={f.label === 'planned' ? '6 4' : undefined}
          />
          <title>{f.title}</title>
        </g>
      );
    }
    return null;
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] text-[var(--console-faint)]">
        <span>拖曳平移 · 滾輪／雙指縮放 · 點選要素</span>
        <button type="button" className="console-btn-ghost px-2 py-0.5" onClick={resetView}>
          重置視圖
        </button>
        <span className="text-[var(--console-muted)]">
          縮放 {Math.round(transform.scale * 100)}%
        </span>
      </div>
      <div
        ref={containerRef}
        className="relative min-h-[280px] flex-1 touch-none overflow-hidden rounded-xl border border-[#c9a961]/25 bg-[#0a0a0c]"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        <svg width={size.w} height={size.h} className="block">
          <defs>
            <pattern id="grid" width={32} height={32} patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#ffffff08" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
          {data.features.map(renderFeature)}
        </svg>
        <div className="pointer-events-none absolute bottom-2 left-2 rounded bg-black/50 px-2 py-1 text-[9px] text-[#8a8f98]">
          XZ 俯視 · {data.region || '—'} · {data.note}
        </div>
      </div>
    </div>
  );
}

function FeatureDetail({ feature }: { feature: LayoutPreviewFeature }) {
  return (
    <div className="space-y-1 text-xs text-[var(--console-muted)]">
      <div className="font-medium text-[var(--console-text)]">{feature.title}</div>
      <div>類型：{feature.kind}</div>
      <div>狀態：{feature.label}（{feature.status}）</div>
      <div>來源：{feature.source}</div>
      {feature.type === 'rect' && feature.rect ? (
        <div>
          範圍：X {feature.rect.x1}–{feature.rect.x2} · Z {feature.rect.z1}–{feature.rect.z2}
        </div>
      ) : null}
      {feature.type === 'point' && feature.point ? (
        <div>座標：X {feature.point.x} · Z {feature.point.z}</div>
      ) : null}
      {feature.meta?.block_count != null ? <div>預估方塊：{String(feature.meta.block_count)}</div> : null}
      {feature.meta?.estimated_blocks != null ? (
        <div>預估方塊：{String(feature.meta.estimated_blocks)}</div>
      ) : null}
      {feature.meta?.material ? <div>材質：{String(feature.meta.material)}</div> : null}
      {feature.meta?.layout_mode ? (
        <div className="text-[var(--console-faint)]">
          布局：{feature.meta.layout_mode === 'synthetic' ? '種子推算（無絕對座標）' : '絕對座標'}
        </div>
      ) : null}
      {feature.meta?.footprint_estimate ? (
        <div className="text-amber-300/90">建築 footprint 為估算，非遊戲內已建造</div>
      ) : null}
    </div>
  );
}

export default function LayoutPreviewPanel() {
  const [data, setData] = useState<LayoutPreviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<LayoutPreviewFeature | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchMinecraftLayoutPreview();
      setData(res);
      setSelected(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedFeature = selected ?? (data?.features[0] ?? null);

  return (
    <PanelShell scroll={false}>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll className="flex min-h-0 flex-1 flex-col">
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}

          <SectionHeader
            title="布局預覽"
            description="Linkin 原生 2D 俯視 — map_plan、建築意圖、NPC 待落地（不需 Dynmap／橋接）"
          />

          {data?.empty ? (
            <ConsoleCard className="mt-2">
              <ConsoleCardHeader>尚無可預覽的布局</ConsoleCardHeader>
              <div className="space-y-3 px-3 pb-4 text-xs text-[var(--console-muted)]">
                <p>請先從敘事工作區生成 map_plan，或提交建築／世界意圖。</p>
                <div className="flex flex-wrap gap-2">
                  <a href="#/modules/minecraft/narrative" className="console-btn">
                    敘事工作區
                  </a>
                  <a href="#/modules/minecraft/map_plan" className="console-btn-ghost">
                    地圖計畫
                  </a>
                  <a href="#/modules/minecraft/plugin-hub" className="console-btn-ghost">
                    插件中心（Dynmap）
                  </a>
                  <a href="#/modules/minecraft/server-map" className="console-btn-ghost">
                    伺服器地圖
                  </a>
                </div>
              </div>
            </ConsoleCard>
          ) : data ? (
            <div className="mt-2 grid min-h-0 flex-1 gap-3 lg:grid-cols-[1fr_220px]">
              <ConsoleCard className="flex min-h-[320px] flex-col p-3">
                {data.map_plan ? (
                  <p className="mb-2 text-[10px] text-[var(--console-faint)]">
                    {data.map_plan.title} · {data.map_plan.region} · {data.map_plan.status ?? 'planned'}
                    {data.map_plan.estimated_blocks != null ? ` · ~${data.map_plan.estimated_blocks} 方塊` : ''}
                  </p>
                ) : null}
                <LayoutCanvas data={data} selectedId={selected?.id ?? null} onSelect={setSelected} />
              </ConsoleCard>

              <div className="space-y-3">
                <ConsoleCard>
                  <ConsoleCardHeader>圖例</ConsoleCardHeader>
                  <ul className="space-y-1 px-3 pb-3 text-[10px]">
                    {data.legend.map((item) => (
                      <li key={item.kind} className="flex items-center gap-2 text-[var(--console-muted)]">
                        <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: item.color }} />
                        {item.label}
                      </li>
                    ))}
                  </ul>
                </ConsoleCard>

                <ConsoleCard>
                  <ConsoleCardHeader>要素詳情</ConsoleCardHeader>
                  <div className="px-3 pb-3">
                    {selectedFeature ? (
                      <FeatureDetail feature={selectedFeature} />
                    ) : (
                      <p className="text-xs text-[var(--console-faint)]">點選地圖上的要素</p>
                    )}
                  </div>
                </ConsoleCard>

                <ConsoleCard>
                  <ConsoleCardHeader>統計</ConsoleCardHeader>
                  <div className="px-3 pb-3 text-[10px] text-[var(--console-muted)]">
                    <div>要素：{data.counts.total}</div>
                    <div>plots：{data.counts.plots}</div>
                    <div>建築意圖：{data.counts.build_briefs}</div>
                    <div>NPC 待落地：{data.counts.npc_intents}</div>
                  </div>
                </ConsoleCard>
              </div>
            </div>
          ) : null}

          {loading ? <p className="mt-2 text-xs text-[var(--console-faint)]">載入中…</p> : null}
          <button type="button" className="console-btn-ghost mt-2 text-xs" onClick={() => void load()}>
            重新載入
          </button>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
