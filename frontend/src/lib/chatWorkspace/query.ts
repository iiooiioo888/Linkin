/**
 * 公司查詢偵測（與後端 execution_path.resolve_execution_path 對齊的規則式判斷）。
 */
/**
 * 與後端 `execution_path.resolve_execution_path` 對齊（不含 OPC／cost_speed 配置）。
 * 自動模式下這類查詢才建任務、才分裂左右監控，避免靈境複雜查詢誤走 SSE 簡單路徑。
 */
const COMPANY_QUERY_RE =
  /开发|設計|设计|构建|實現|实现|建立|打造|完整|系統|系统|專案|项目|多步|架構|架构|重构|遷移|迁移|deploy|develop|build|implement|design|create|refactor|migrate|project|system|application|故事|小說|小说|撰寫|撰写|長文|长文|\d+\s*字/i;

const COMPANY_QUERY_LENGTH = 200;

const LINKIN_WORLD_RE =
  /灵境|靈境|linkin|织庭|織庭|自由舟|宁渊|寧淵|灵丝|靈絲|织梦者|織夢者|精灵森林|精靈森林|裂隙港|织庭都|織庭都|宁渊谷|寧淵谷|aetherthread|will of linkin/i;

const LINKIN_WORK_RE =
  /NPC|角色卡|任务|任務|主线|主線|支线|支線|道具|附魔|世界观|世界觀|宪法|憲法|叙事|敘事|故事|世界设定|世界設定/i;

function isLinkinComplexTask(query: string): boolean {
  return LINKIN_WORLD_RE.test(query) && LINKIN_WORK_RE.test(query);
}

export function looksLikeCompanyQuery(query: string): boolean {
  const q = (query || '').trim();
  if (!q) return false;
  if (isLinkinComplexTask(q)) return true;
  if (q.length >= COMPANY_QUERY_LENGTH) return true;
  return COMPANY_QUERY_RE.test(q);
}
