/**
 * API 路由編輯器：表單草稿、操作狀態與對外 props 型別。
 */
import type { ProviderValue } from './presets';

export interface RouteDraft {
  id: string;
  name: string;
  provider: ProviderValue;
  apiKey: string;
  apiBase: string;
  model: string;
  weight: number;
  enabled: boolean;
  fallback: boolean;
  isDefault: boolean;
  allowedModels: string[];
  modelsLocked: boolean;
  orSort: '' | 'price' | 'latency';
  orOnly: string;
}

/** 儲存／刪除／測試／刷新操作狀態 */
export interface EditorStatus {
  kind: 'idle' | 'busy' | 'ok' | 'fail';
  text: string;
}

export interface ApiRoutesEditorProps {
  /** 儲存／刪除／測連後回呼（控制台同步健康快照、頂欄「未配置」） */
  onChanged?: () => void;
  className?: string;
  /** 設定彈窗用：隱藏「刷新全部目錄」（控制台已有） */
  compact?: boolean;
  /** 控制台側欄已有清單時隱藏重複列表 */
  hideList?: boolean;
}
