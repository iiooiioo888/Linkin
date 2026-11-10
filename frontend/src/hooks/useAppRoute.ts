/**
 * Hash 路由狀態：初始正規化、狀態同步、瀏覽器前進／後退，以及 navigateRoute。
 *
 * 由 App.tsx 抽出，行為與原本的 route useState／useEffect 完全一致。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  appRouteFromState,
  applyAppRoute,
  getDefaultRoute,
  parseAppRoute,
  routesEqual,
  syncAppRouteHash,
} from '../lib/appRoute';
import type { MonitorTab, ViewKey } from '../components/AppShell';
import type { LabSubTab } from '../lib/labTabs';

export interface UseAppRouteResult {
  routeReady: boolean;
  activeView: ViewKey;
  monitorTab: MonitorTab;
  focusAgentId: string | null;
  focusTaskId: string | null;
  traceTaskId: string | null;
  rahoFocus: string | null;
  labSubTab: LabSubTab;
  navigateRoute: (patch: Partial<ReturnType<typeof getDefaultRoute>>) => void;
}

export function useAppRoute(): UseAppRouteResult {
  // ── IDE 布局状态（由 Hash 路由初始化） ──
  const initialRoute = applyAppRoute(parseAppRoute(window.location.hash));
  const [routeReady, setRouteReady] = useState(false);
  const [activeView, setActiveView] = useState<ViewKey>(initialRoute.activeView);
  const [monitorTab, setMonitorTab] = useState<MonitorTab>(initialRoute.monitorTab);
  /** 進入監控「角色 Agent」時預選一位，主區開工作台；名冊在左側外圍 */
  const [focusAgentId, setFocusAgentId] = useState<string | null>(initialRoute.focusAgentId);
  const [focusTaskId, setFocusTaskId] = useState<string | null>(initialRoute.focusTaskId);
  const [traceTaskId, setTraceTaskId] = useState<string | null>(initialRoute.traceTaskId);
  /** 公司運行時席位 I/O 監察整頁的聚焦對象（raho run_id 或 task_id） */
  const [rahoFocus, setRahoFocus] = useState<string | null>(initialRoute.rahoFocus);
  const [labSubTab, setLabSubTab] = useState<LabSubTab>(initialRoute.labSubTab);

  // Hash 路由：初始化正規化 + 狀態同步 + 瀏覽器前進/後退
  useEffect(() => {
    const boot = parseAppRoute(window.location.hash);
    syncAppRouteHash(boot);
    setRouteReady(true);
  }, []);

  useEffect(() => {
    if (!routeReady) return;
    syncAppRouteHash(
      appRouteFromState({
        activeView,
        monitorTab,
        focusAgentId,
        focusTaskId,
        traceTaskId,
        rahoFocus,
        labSubTab,
      }),
    );
  }, [routeReady, activeView, monitorTab, focusAgentId, focusTaskId, traceTaskId, rahoFocus, labSubTab]);

  useEffect(() => {
    const onHashChange = () => {
      const parsed = parseAppRoute(window.location.hash);
      const current = appRouteFromState({
        activeView,
        monitorTab,
        focusAgentId,
        focusTaskId,
        traceTaskId,
        rahoFocus,
        labSubTab,
      });
      if (routesEqual(current, parsed)) return;
      const next = applyAppRoute(parsed);
      setActiveView(next.activeView);
      setMonitorTab(next.monitorTab);
      setFocusAgentId(next.focusAgentId);
      setFocusTaskId(next.focusTaskId);
      setTraceTaskId(next.traceTaskId);
      setRahoFocus(next.rahoFocus);
      setLabSubTab(next.labSubTab);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [activeView, monitorTab, focusAgentId, focusTaskId, traceTaskId, rahoFocus, labSubTab]);

  const navigateRoute = useCallback(
    (patch: Partial<ReturnType<typeof getDefaultRoute>>) => {
      const route = appRouteFromState({
        activeView: patch.view ?? activeView,
        monitorTab: patch.monitorTab ?? monitorTab,
        focusAgentId: patch.focusAgentId !== undefined ? patch.focusAgentId : focusAgentId,
        focusTaskId: patch.focusTaskId !== undefined ? patch.focusTaskId : focusTaskId,
        traceTaskId: patch.traceTaskId !== undefined ? patch.traceTaskId : traceTaskId,
        rahoFocus: patch.rahoFocus !== undefined ? patch.rahoFocus : rahoFocus,
        labSubTab: patch.labSubTab ?? labSubTab,
      });
      const applied = applyAppRoute(route);
      setActiveView(applied.activeView);
      setMonitorTab(applied.monitorTab);
      setFocusAgentId(applied.focusAgentId);
      setFocusTaskId(applied.focusTaskId);
      setTraceTaskId(applied.traceTaskId);
      setRahoFocus(applied.rahoFocus);
      setLabSubTab(applied.labSubTab);
    },
    [activeView, monitorTab, focusAgentId, focusTaskId, traceTaskId, rahoFocus, labSubTab],
  );

  return {
    routeReady,
    activeView,
    monitorTab,
    focusAgentId,
    focusTaskId,
    traceTaskId,
    rahoFocus,
    labSubTab,
    navigateRoute,
  };
}
