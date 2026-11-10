/** 這一輪控制台給使用者看的狀態。編譯相關狀態不顯示。 */

const RUNTIME_LABEL: Record<string, string> = {
  running: '進行中',
  paused: '暫停',
  auditing: '審計',
  l0_refreshing: '世界更新',
  plugin_degraded: '外掛降級',
  awaiting_confirmation: '待確認',
};

export function runtimeStateLabel(state: string | undefined | null): string {
  if (!state) return '';
  return RUNTIME_LABEL[state] || '';
}
