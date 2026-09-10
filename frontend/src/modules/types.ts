/**
 * 世界／整合模組前端契約（與 GET /modules 對齊）。
 */
export type ModulePageProps = {
  moduleId: string;
  page: string;
  focusAgentId: string | null;
  onFocusAgent: (id: string | null) => void;
};
