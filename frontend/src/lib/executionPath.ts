/** 執行路徑的本次選擇與默認。系統建議不在這裡執行。 */

export type ConcretePath = 'simple' | 'company';

export type PathChoice =
  | { source: 'session'; path: ConcretePath }
  | { source: 'default'; path: ConcretePath };

const SESSION_KEY = 'linkin.executionPath.session';

export const PATH_LABEL: Record<ConcretePath, string> = {
  simple: '簡單生成',
  company: '公司分析',
};

export function readSessionPathChoice(): PathChoice | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PathChoice;
    if (parsed?.source !== 'session' && parsed?.source !== 'default') return null;
    if (parsed.path !== 'simple' && parsed.path !== 'company') return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeSessionPathChoice(choice: PathChoice | null): void {
  try {
    if (!choice) {
      sessionStorage.removeItem(SESSION_KEY);
      return;
    }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(choice));
  } catch {
    /* 隱私模式不阻擋送出 */
  }
}

export function strategyForChoice(choice: PathChoice): 'simple' | 'company' | 'user_default' {
  if (choice.source === 'default') return 'user_default';
  return choice.path;
}
