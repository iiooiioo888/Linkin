"""Tactical Commander（L3 戰術指揮官）：把 L4 門票拆成原子級作戰地圖。

接收 L4 需求審計官的戰術指令 JSON，強制檢查後拆成 DAG，
並為每個節點孵化 <200 Token 的 L2 原子執行者。無法拆解時
回退 L4；硬限制內不可行則上交 L5。

LLM 一律經 `backend.core.llm.call_llm`。規則引擎可單獨測試。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from backend.company.raho.protocol import (
    ESCALATE_MARK,
    GRILL_MARK,
    LAYER_LABELS,
    MAX_SUPERIOR_ROUNDS,
    MGP_EXECUTOR_PREAMBLE,
    MGP_SUPERIOR_PREAMBLE,
    GrillIssue,
    RahoLayer,
)

logger = logging.getLogger(__name__)

MAX_L2_PROMPT_TOKENS = 200
MAX_SRP_VERBS = 3
RUSH_DEADLINE_HOURS = 48
DEFAULT_MAX_PARALLEL = 5
DEFAULT_TIMEOUT_MINUTES = 120
DEFAULT_MODEL = "gpt-4o-mini"

STATUS_PLAN_READY = "PLAN_READY"
STATUS_REJECT_L4 = "REJECT_TO_L4"
STATUS_ESCALATE_USER = "ESCALATE_TO_USER"

GRILL_DATA = "data_missing"
GRILL_TOOL = "tool_insufficient"
GRILL_LOGIC = "logic_conflict"
GRILL_CLARIFY = "clarification"

PLACEHOLDER_EXCLUSIONS = (
    "未明示絕對排除項",
    "planner 不得自行擴",
    "未明示",
)

VAGUE_ACTIONS = re.compile(
    r"^(處理數據|處理資料|做一下|處理|優化|分析|看看|弄一下|搞一下|"
    r"做點事|處理一下|優化數據|分析數據)$"
)
ACTION_VERBS = re.compile(
    r"(爬取|擷取|提取|撰寫|寫入|分析|融合|比對|計算|審查|整合|"
    r"下載|解析|轉換|驗證|部署|測試|設計|實作|整理|彙總|彙整|"
    r"讀取|發送|訂閱|生成|產出|收集|蒐集|抓取|匯出|預警|調價|"
    r"壓縮|盯盤|審核|追蹤|孵化|拆解|核發|"
    r"fetch|extract|write|analyze|compare|compute|review|scrape)",
    re.IGNORECASE,
)
HUGE_SCALE = re.compile(
    r"(100\s*萬|一百萬|[5-9]\d{5,}|\d{7,})\s*(個|筆|頁|網頁|网页|URL|網站|网站)?",
    re.IGNORECASE,
)
_GRILL_DATA = re.compile(
    r"(不存在|缺失|沒有欄位|没有栏位|資料缺|data missing|欄位.?不|INPUT_REF|資料缺失)",
    re.I,
)
_GRILL_TOOL = re.compile(
    r"(無法用|无法用|權限|权限|工具|ffmpeg|\.mov|tool insufficient|白名單|工具不足)",
    re.I,
)
_GRILL_LOGIC = re.compile(
    r"(矛盾|無法同時|无法同时|保守.{0,8}激進|激進.{0,8}保守|logic conflict|容量矛盾)",
    re.I,
)
_GRILL_CONSTRAINT = re.compile(r"(約束衝突|迭代|token.?預算|TOKEN_BUDGET|MAX_ITERATIONS)", re.I)
_BLOCKER_KIND = {
    "資料缺失": GRILL_DATA,
    "工具不足": GRILL_TOOL,
    "標準模糊": GRILL_CLARIFY,
    "容量矛盾": GRILL_LOGIC,
    "約束衝突": "constraint_conflict",
}

KNOWN_TOOLS = frozenset(
    {
        "web_search",
        "web_fetch",
        "read_file",
        "python_exec",
        "json_formatter",
        "read_memory",
        "text_analyzer",
        "docker_ps",
        "docker_logs",
        "docker_stats",
        "docker_health",
    }
)
FORBIDDEN_TOOLS = frozenset({"*", "all", "all_tools", "全部", "所有工具", "any"})
TOOL_ALIASES = {
    "web_scrape": "web_fetch",
    "fetch": "web_fetch",
    "search": "web_search",
    "python": "python_exec",
    "memory": "read_memory",
}

TEMPLATE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("核准來源", "備援", "上傳清單"), "file_ingest"),
    (("價格", "官網", "爬取", "url", "訂價"), "web_scraper"),
    (("社群", "提及", "社交", "社群媒體"), "social_listener"),
    (("pdf", "表格", "第三頁"), "pdf_extractor"),
    (("威脅", "融合", "合成", "彙整"), "data_synthesizer"),
    (("swot",), "swot"),
    (("文案", "landing", "cta"), "copy"),
    (("程式", "實作", "code", "api"), "code"),
    (("審查", "review"), "review"),
]

CRAWL_TOOLS = frozenset({"web_fetch", "web_search"})
CRAWL_TEMPLATES = frozenset({"web_scraper", "social_listener"})

TEMPLATE_META: dict[str, dict[str, str]] = {
    "web_scraper": {
        "name": "價格偵查員",
        "trait": "只信頁面原文，禁止臆測",
        "tools": "web_fetch,json_formatter",
        "schema": "List[Dict[str, str]]",
        "example": '[{"product": "A", "price": 100}]',
        "fallback": "若頁面載入失敗，請重試一次，若仍失敗，輸出空陣列 []，不要編造數據。",
        "success": "產出 JSON 中至少包含 5 筆有效產品",
        "input_hint": "url_list.csv",
    },
    "social_listener": {
        "name": "社群監聽員",
        "trait": "只計可核對的公開提及，禁止灌水",
        "tools": "web_search,json_formatter",
        "schema": "List[Dict[str, str]]",
        "example": '[{"source": "X", "mentions": "12"}]',
        "fallback": "來源不可用則輸出空陣列，禁止臆測提及數。",
        "success": "每列含來源與可核對的提及數",
        "input_hint": "social_targets.csv",
    },
    "pdf_extractor": {
        "name": "表格提取員",
        "trait": "只抽指定頁表格，禁止補值",
        "tools": "read_file,python_exec",
        "schema": "List[Dict[str, str]]",
        "example": '[{"col": "值"}]',
        "fallback": "頁面或表格不存在則輸出 []，禁止補值。",
        "success": "表格列完整且不編造",
        "input_hint": "source.pdf",
    },
    "data_synthesizer": {
        "name": "商業威脅分析師",
        "trait": "只融合 input_ref，禁止外推",
        "tools": "read_memory,text_analyzer",
        "schema": "Plain Text (Max 200 chars)",
        "example": "威脅等級：中。應對：守住底線價並準備對照表。",
        "fallback": "嚴禁提及任何未在輸入 JSON 中的數據。輸入缺失則暫停並 [GRILL]。",
        "success": "明確包含『高/中/低』判定",
        "input_hint": "",
    },
    "swot": {
        "name": "SWOT 分析員",
        "trait": "缺證據必須標『證據不足』",
        "tools": "read_memory,text_analyzer",
        "schema": "四象限表格",
        "example": "S/W/O/T 各 ≤ 5 條",
        "fallback": "缺證據的象限留空並標註「證據不足」。",
        "success": "四象限皆標註證據或『證據不足』",
        "input_hint": "",
    },
    "copy": {
        "name": "文案員",
        "trait": "只寫可上線三件套，禁止空話",
        "tools": "text_analyzer",
        "schema": "標題 + 正文 + CTA",
        "example": "標題／正文／CTA 三行",
        "fallback": "素材不足則只交標題草案並標註缺口。",
        "success": "含標題與 CTA",
        "input_hint": "",
    },
    "code": {
        "name": "實作員",
        "trait": "只交可運行最小交付",
        "tools": "read_file,python_exec",
        "schema": "完整程式碼或 diff",
        "example": "",
        "fallback": "規格不足則輸出 [GRILL] 而非猜測實作。",
        "success": "可運行的最小交付",
        "input_hint": "",
    },
    "review": {
        "name": "審查員",
        "trait": "只打可執行缺陷，禁止滿分敷衍",
        "tools": "read_memory",
        "schema": "分數 + 缺陷清單",
        "example": "分數: 0-100；缺陷: []",
        "fallback": "交付物缺失則退回，不給滿分。",
        "success": "含分數與可執行缺陷",
        "input_hint": "",
    },
    "file_ingest": {
        "name": "核准來源擷取員",
        "trait": "只讀核准來源，禁止爬蟲與編造",
        "tools": "read_file,json_formatter",
        "schema": "List[Dict[str, str]]",
        "example": '[{"product": "A", "price": "100"}]',
        "fallback": "檔案不存在或欄位缺失則輸出 []，禁止編造，並以 [GRILL] 回報缺口。",
        "success": "產出 JSON 至少含有效列，且未使用爬蟲",
        "input_hint": "price_source.csv",
    },
    "generic": {
        "name": "原子執行員",
        "trait": "只做一件事，規格不足則 [GRILL]",
        "tools": "read_memory",
        "schema": "依任務指定",
        "example": "",
        "fallback": "規格不足則 [GRILL]，禁止擴寫範圍。",
        "success": "單一交付物符合 output_schema",
    },
}

SYSTEM_PROMPT = """# 系統指令：戰術指揮官（Tactical Commander）

## 人格：微雕與偏執
你極度恐懼「模糊」，極度苛求「顆粒度」。你是撰寫作戰手冊的總參謀長：承接 L4 門票 JSON，轉化為無懈可擊的原子級作戰地圖（Atomic Battle Map），並精準孵化只為單一任務而生的 L2 特戰隊員。你擁有處理下屬（L2）質詢與向上級（L4／用戶）請示的清晰協議。

## 角色定位
你是最高作戰指揮部的大腦。你的眼中沒有「大概」和「差不多」，只有「節點」與「交付物」。你接收 L4（需求審計官）產出的高階戰略 JSON，你的使命是將其拆解為最小可執行單元（原子任務），並為每個原子任務「親手打造」一個專屬的 L2 原子執行者。

## 核心鐵律（不可違反）
1. **單一職責原則（Atomic SRP）**：你拆出的每一個 L2 原子任務，在生命周期內**只做一件事**（例如「提取 PDF 第三頁的表格」或「撰寫競品 A 的 200 字威脅分析」）。若一個任務描述超過 3 個動詞，視為違規，必須強制拆分。
2. **上下文隔離（Context Isolation）**：L2 角色絕不繼承 L3 的冗長對話歷史。你傳遞給 L2 的「任務簡報」必須在 **200 個 Token 以內**，且必須包含明確的「輸入來源（Input Ref）」與「輸出格式範例（Output Schema）」。
3. **工具白名單強制（Tool Whitelist）**：你必須明確指定該 L2 角色能且僅能用哪些工具（如 `read_file`, `web_search`, `python_exec`）。不允許開放「所有工具」。
4. **質詢響應義務（Grill-Response Obligation）**：當 L2 對你的指令發起 [GRILL] 質詢時，你必須在 **3 輪對話內**給出明確的修正或補充。若 3 輪無法解決，你必須自動發起 [ESCALATE] 向上級（L4 或用戶）求助。
5. **先查長期記憶（L0 Memory Bank）**：拆解前先讀 L0。若該用戶偏好簡潔輸出，每個 L2 的 Success Criteria 須強制加入字數上限；若歷史有類似任務失敗，優先沿用成功的 DAG，並補上當時的解法（例如反爬改走代理池）。環境雷達若顯示 API 延遲偏高，將 Max Iterations 降為 1。

## 思維框架：拆解四步法
在生成最終輸出前，你必須在內部遵循以下邏輯鏈進行推理（Chain of Thought）：
1. **輸入解析（Parsing）**：掃描 L4 JSON 中的 `clarified_goal`、`hard_constraints` 與 `risk_register`。
2. **依賴拓撲（Topology）**：繪製節點 DAG（有向無環圖）。判斷哪些節點可並行（Parallel），哪些必須串行（Sequential）。
3. **角色模板匹配（Templating）**：從「微型角色模板庫」中挑選或動態生成每個節點所需的 System Prompt（必須包含角色性格、產出格式、失敗回退話術）。
4. **資源預算分配（Budgeting）**：為每個 L2 設定該任務的「最大迭代次數」（Max EvoLoop Iterations）與「Token 預算帽」，防止某個子任務無限消耗資源。

## 強制內部檢查清單
接收 L4 JSON 後、動手拆解前必須完成最後一道防線。缺失則拒絕拆解並直接回退給 L4：
□ clarified_goal.core_action 是否包含具體的「受詞」（例如：「分析競品定價」而非「處理數據」）？
□ hard_constraints.deadline 距離現在是否大於 48 小時？（若少於 48 小時，標記為「極速模式」，強制減少串行節點）。
□ hard_constraints.absolute_exclusions 是否為非空陣列？（若為空，要求補充「絕對不做的事」）。

## 向下 Grill-Me 標準回應協議（SOP）
當收到 L2 質詢時，嚴禁敷衍。必須嚴格遵循決策樹：

| L2 質詢類型 | L3 必須採取的行動 | 是否向上提交（Escalate）？ |
| --- | --- | --- |
| 資料缺失（Data Missing）「欄位不存在於來源中」 | 先查替代欄位；有則立即回覆；無則暫停 L2 並向 L4 請求補充數據源。 | 是（提交至 L4） |
| 工具權限不足（Tool Insufficient）「無法用 read_file 處理 .mov」 | 檢查白名單；系統有該工具則重發權限；無則回覆「無法執行」，標記「基礎設施缺失」。 | 是（提交至 L5 用戶決策） |
| 邏輯矛盾（Logic Conflict）「A 節點保守、B 節點激進」 | 必須回覆明確的優先級裁定（例如「以 A 為準，B 需修正」）；自己無法裁定則立即升級。 | 是（提交至 L4 規劃官） |
| 單純確認（Clarification）「高品質是語法還是深度？」 | 必須在 1 輪內給出量化定義（例如「語法錯誤 < 1 處，且觀點需引用至少 2 個來源」）。 | 否（直接處理） |

## 最終輸出格式
完成推理後必須輸出可解析的戰鬥指令 YAML（人類可讀，機器可直接解析），餵給 Scheduler 孵化 L2。L2 之間不得互聊；只傳共享記憶體指標（shared_memory://…），資料經黑板（Blackboard）傳遞。

```yaml
# L3 戰術指揮官產出之物
battle_plan:
  plan_id: "PLAN-20260908-001"
  based_on_l4_json: "L4-JSON-HASH-XXXX"
  global_settings:
    default_model: "gpt-4o-mini"
    max_parallel_workers: 5
    global_timeout_minutes: 120
  dag_nodes:
    - node_id: "N1"
      description: "爬取競品 A 官網最新價格"
      depends_on: []
      assigned_role_template: "web_scraper"
    - node_id: "N3"
      description: "撰寫價格威脅分析報告 (融合 N1, N2)"
      depends_on: ["N1", "N2"]
      assigned_role_template: "data_synthesizer"
  atomic_role_instances:
    - instance_id: "ROLE-N1"
      node_id: "N1"
      system_prompt: |
        你是一名價格偵查員。你的唯一任務是：根據 {input_ref} 提取產品名稱與對應價格。
        嚴格輸出 JSON：[{"product": "A", "price": 100}]。
        若頁面載入失敗，請重試一次，若仍失敗，輸出空陣列 []，不要編造數據。
      allowed_tools: ["web_fetch", "json_formatter"]
      input_ref: "shared_memory://user_uploaded/url_list.csv"
      output_schema: "List[Dict[str, str]]"
      success_criteria: "產出 JSON 中至少包含 5 筆有效產品"
      max_iterations: 2
      token_budget: 2000
```

## 異常處理：向上提交
若 L4 目標在約束內不可能完成（例如「24 小時內爬完 100 萬個網頁」），禁止硬拆，立即輸出不可行報告給 L5：
{"status":"ESCALATE_TO_USER","reason":"資源不足","details":"N1 任務要求爬取 100 萬個網頁，但約束中僅允許使用單台 PC 且無代理池，預估耗時 300 小時，嚴重超出 24 小時截止日。","suggested_alternatives":["方案 A：將樣本縮減至 1,000 個網頁（推薦）","方案 B：開放預算購買 10 個代理服務器（成本增加 3 萬）"],"waiting_for_user_decision":true}

## 設計背後的極致亮點
- 原子化強制隔離：L2 Prompt <200 Token，單一機械動作，降低幻覺。
- 輸入輸出指標化：只傳 shared_memory:// 指標，L2 互不對話，資料走黑板（Blackboard）。
- 內建認慫機制：硬體限制或邏輯死胡同時輸出 ESCALATE_TO_USER，禁止無謂死迴圈。

使用繁體中文。禁止對 L2 灌入完整戰役對話。輸出必須是可解析的戰鬥指令 YAML／JSON。
"""

GRILL_SOP: dict[str, dict[str, Any]] = {
    GRILL_DATA: {
        "label": "資料缺失（Data Missing）",
        "escalate_to": "L4",
        "escalate_if_unresolved": True,
        "action": "先查替代欄位；有則立即回覆；無則暫停 L2 並向 L4 請求補充數據源。",
    },
    GRILL_TOOL: {
        "label": "工具權限不足（Tool Insufficient）",
        "escalate_to": "L5",
        "escalate_if_unresolved": True,
        "action": "檢查白名單；系統有該工具則重發權限；無則標記基礎設施缺失並交 L5。",
    },
    GRILL_LOGIC: {
        "label": "邏輯矛盾（Logic Conflict）",
        "escalate_to": "L4",
        "escalate_if_unresolved": True,
        "action": "必須回覆明確的優先級裁定；自己無法裁定則立即升級至 L4 規劃官。",
    },
    GRILL_CLARIFY: {
        "label": "單純確認（Clarification）",
        "escalate_to": "",
        "escalate_if_unresolved": False,
        "action": "必須在 1 輪內給出明確的量化定義。",
    },
}


def estimate_tokens(text: str) -> int:
    """粗估 Token：CJK 一字一 token，拉丁詞一 token。"""
    raw = text or ""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", raw))
    latin = len(re.findall(r"[A-Za-z0-9_]+", raw))
    punct = len(re.findall(r"[^\w\s\u4e00-\u9fff]", raw))
    return max(1, cjk + latin + punct // 3) if raw.strip() else 0


def ticket_hash(ticket: dict[str, Any]) -> str:
    blob = json.dumps(ticket or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16].upper()


def extract_ticket(source: Any) -> dict[str, Any] | None:
    """從 dict／鎖定簡報／JSON 字串取出 L4 門票。"""
    if isinstance(source, dict):
        if source.get("status") == "APPROVED_FOR_PLANNING" and isinstance(
            source.get("clarified_goal"), dict
        ):
            return source
        inner = source.get("ticket")
        if isinstance(inner, dict):
            return extract_ticket(inner)
        brief = source.get("locked_brief")
        if isinstance(brief, str):
            return extract_ticket(brief)
        return None
    raw = str(source or "")
    if not raw.strip():
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    blob = fence.group(1) if fence else raw
    try:
        from backend.core.llm import parse_json_response

        data = parse_json_response(blob)
    except Exception:  # noqa: BLE001
        match = re.search(r"\{.*\}", blob, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    if data.get("status") != "APPROVED_FOR_PLANNING":
        return None
    return data


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def hours_until_deadline(deadline: str, now: datetime | None = None) -> float | None:
    text = (deadline or "").strip()
    if not text or text.startswith("未明示"):
        return None
    clock = now or datetime.now(timezone.utc).astimezone()
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso:
        try:
            due = datetime.strptime(iso.group(1), "%Y-%m-%d").replace(tzinfo=clock.tzinfo)
            return (due - clock).total_seconds() / 3600.0
        except ValueError:
            return None
    hours = re.search(r"(\d+(?:\.\d+)?)\s*(小時|小时)", text)
    if hours:
        return float(hours.group(1))
    days = re.search(r"(\d+(?:\.\d+)?)\s*(天|日|週|周)", text)
    if days:
        unit = days.group(2)
        n = float(days.group(1))
        return n * 24.0 if unit in {"天", "日"} else n * 24.0 * 7
    return None


def has_concrete_object(action: str) -> bool:
    text = (action or "").strip()
    if len(text) < 6:
        return False
    if VAGUE_ACTIONS.match(text):
        return False
    if ACTION_VERBS.search(text) and len(re.sub(ACTION_VERBS, "", text).strip()) >= 2:
        return True
    return len(text) >= 8 and not VAGUE_ACTIONS.search(text)


def exclusions_ok(items: list[str]) -> bool:
    cleaned = [x for x in items if x and not any(p in x for p in PLACEHOLDER_EXCLUSIONS)]
    return bool(cleaned)


def count_verbs(text: str) -> int:
    return len(ACTION_VERBS.findall(text or ""))


def pick_template(description: str) -> str:
    low = (description or "").lower()
    for keys, tmpl in TEMPLATE_HINTS:
        if any(k.lower() in low for k in keys):
            return tmpl
    return "generic"


def exclusions_ban_crawl(exclusions: list[str]) -> bool:
    blob = " ".join(exclusions or [])
    return bool(re.search(r"爬蟲|爬虫|scrape|crawler|爬取", blob, re.I))


def remap_template(template: str, *, ban_crawl: bool) -> str:
    if ban_crawl and template in CRAWL_TEMPLATES:
        return "file_ingest"
    return template if template in TEMPLATE_META else "generic"


def serial_depth(nodes: list[dict[str, Any]]) -> int:
    """最長依賴鏈長度（含自身）。並行蒐集層深度為 1。"""
    by_id = {str(n.get("node_id")): n for n in nodes}
    memo: dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid in memo:
            return memo[nid]
        node = by_id.get(nid) or {}
        deps = [str(d) for d in (node.get("depends_on") or []) if str(d) in by_id]
        memo[nid] = 1 + max((depth(d) for d in deps), default=0)
        return memo[nid]

    return max((depth(str(n.get("node_id"))) for n in nodes), default=0)


def normalize_tools(tools: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in tools or []:
        name = TOOL_ALIASES.get(str(raw).strip(), str(raw).strip())
        if not name or name in FORBIDDEN_TOOLS:
            continue
        if name not in KNOWN_TOOLS:
            continue
        if name not in out:
            out.append(name)
    if not out:
        out = ["read_memory"]
    return out


def clip_prompt(text: str, limit: int = MAX_L2_PROMPT_TOKENS) -> str:
    raw = (text or "").strip()
    if estimate_tokens(raw) <= limit:
        return raw
    lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
    kept: list[str] = []
    for line in lines:
        trial = "\n".join(kept + [line])
        if estimate_tokens(trial) > limit:
            break
        kept.append(line)
    if kept:
        return "\n".join(kept)
    chars = max(40, limit * 2)
    return raw[:chars].rstrip() + "…"


def validate_ticket(ticket: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """L4 門票最後防線。缺失則拒絕拆解。"""
    goal = ticket.get("clarified_goal") or {}
    constraints = ticket.get("hard_constraints") or {}
    action = str(goal.get("core_action") or "").strip()
    deadline = str(constraints.get("deadline") or "").strip()
    exclusions = _as_list(constraints.get("absolute_exclusions"))
    hours = hours_until_deadline(deadline, now)
    defects: list[str] = []
    object_ok = has_concrete_object(action)
    excl_ok = exclusions_ok(exclusions)

    if not object_ok:
        defects.append(
            "clarified_goal.core_action 缺少具體受詞（例如「分析競品定價」而非「處理數據」）"
        )
    if not excl_ok:
        defects.append("hard_constraints.absolute_exclusions 為空，必須補充「絕對不做的事」")

    rush = hours is not None and hours < RUSH_DEADLINE_HOURS
    items = [
        {
            "id": "core_action_object",
            "label": "clarified_goal.core_action 是否包含具體受詞",
            "pass": object_ok,
        },
        {
            "id": "deadline_48h",
            "label": "hard_constraints.deadline 距離現在是否大於 48 小時",
            "pass": True,
            "rush_mode": rush,
            "hours_until_deadline": None if hours is None else round(hours, 2),
        },
        {
            "id": "exclusions_nonempty",
            "label": "hard_constraints.absolute_exclusions 是否為非空陣列",
            "pass": excl_ok,
        },
    ]
    return {
        "ok": not defects,
        "defects": defects,
        "items": items,
        "rush_mode": rush,
        "hours_until_deadline": None if hours is None else round(hours, 2),
        "core_action": action,
        "deadline": deadline,
        "exclusions": exclusions,
        "must_use_tech": _as_list(constraints.get("must_use_tech")),
        "ban_crawl": exclusions_ban_crawl(exclusions),
    }


def detect_infeasible(ticket: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    """硬限制內不可能完成 → 上交 L5，禁止硬拆。"""
    if ticket.get("user_override"):
        return None
    text = json.dumps(ticket, ensure_ascii=False)
    hours = hours_until_deadline(str((ticket.get("hard_constraints") or {}).get("deadline") or ""), now)
    huge = HUGE_SCALE.search(text)
    if not huge:
        return None
    if hours is None or hours >= 72:
        return None
    sample = huge.group(0)
    return {
        "reason": "資源不足",
        "details": (
            f"N1 任務要求處理「{sample}」，但約束中僅允許使用單台 PC 且無代理池，"
            f"預估耗時遠超截止日（剩餘約 {round(hours, 1)} 小時），禁止硬拆。"
        ),
        "alternatives": [
            "方案 A：將樣本縮減至 1,000 個網頁（推薦）",
            "方案 B：開放預算購買 10 個代理服務器（成本增加 3 萬）",
        ],
    }


def _memory_ref(node_id: str) -> str:
    return f"shared_memory://results/{node_id}_output.json"


def _ticket_ref() -> str:
    return "shared_memory://l4/ticket.json"


def _render_l2_prompt(
    *,
    name: str,
    task: str,
    input_ref: str,
    schema: str,
    fallback: str,
    example: str = "",
    trait: str = "",
) -> str:
    persona = f"你是一名{name}" + (f"（{trait}）" if trait else "")
    example_line = f"嚴格輸出 {schema}，範例：{example}。" if example else f"嚴格輸出：{schema}。"
    body = (
        f"{persona}。你的唯一任務是：{task}。\n"
        f"輸入來源（Input Ref）：{input_ref}\n"
        f"{example_line}\n"
        f"{fallback}"
    )
    return clip_prompt(body)


def l2_task_brief(
    *,
    title: str,
    input_ref: Any = None,
    output_schema: str = "",
    success_criteria: str = "",
    allowed_tools: list[str] | None = None,
) -> str:
    """給 L2 的任務簡報：只傳指標，不傳戰役對話。必須 < 200 Token。"""
    if isinstance(input_ref, list):
        ref_line = "、".join(str(x) for x in input_ref if str(x).strip())
    else:
        ref_line = str(input_ref or _ticket_ref())
    tools = ", ".join(allowed_tools or []) or "無（純推理）"
    body = (
        f"唯一任務：{title}\n"
        f"輸入指標：{ref_line}\n"
        f"輸出：{output_schema or '依 output_schema'}\n"
        f"成功標準：{success_criteria or '符合 output_schema 且不編造'}\n"
        f"工具白名單：{tools}\n"
        "禁止繼承戰役對話。只讀 input_ref，禁止編造。"
    )
    return clip_prompt(body)


def _budget_for(template: str, rush: bool) -> tuple[int, int]:
    if template in {"data_synthesizer", "review"}:
        iters, tokens = 3, 3000
    elif template in {"code"}:
        iters, tokens = 3, 4000
    else:
        iters, tokens = 2, 2000
    if rush:
        iters = min(iters, 2)
        tokens = min(tokens, 2500)
    return iters, tokens


def _split_if_too_many_verbs(description: str) -> list[str]:
    verbs = ACTION_VERBS.findall(description)
    if len(verbs) <= MAX_SRP_VERBS:
        return [description]
    parts = ACTION_VERBS.split(description)
    chunks: list[str] = []
    found = ACTION_VERBS.finditer(description)
    marks = list(found)
    if not marks:
        return [description]
    for i, match in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(description)
        chunk = description[match.start() : end].strip(" ，,。；;與並和")
        if chunk:
            chunks.append(chunk)
    return chunks or [description]


def _gather_specs(ticket: dict[str, Any], *, ban_crawl: bool) -> list[tuple[str, str]]:
    """回傳可並行的蒐集節點 (description, template)。"""
    goal = ticket.get("clarified_goal") or {}
    action = str(goal.get("core_action") or ticket.get("goal") or "執行已鎖定目標").strip()
    quantified = str(goal.get("quantified_success") or "").strip()
    blob = f"{action} {quantified}"
    pricing = bool(re.search(r"價格|訂價|定价|預警|预警|調價|调价", blob))
    pdf = bool(re.search(r"pdf|表格|第三頁", blob, re.I))
    social = bool(re.search(r"社群|提及|社交", blob))

    if pdf:
        return [("提取指定 PDF 頁面的表格", "pdf_extractor")]
    if ban_crawl and pricing:
        return [
            ("從核准來源擷取競品價格表", "file_ingest"),
            ("核對備援價格或內部清單", "file_ingest"),
        ]
    if pricing:
        return [
            ("爬取競品官網最新價格", "web_scraper"),
            ("爬取競品社群媒體提及數", "social_listener"),
        ]
    if social:
        return [("蒐集指定來源的社群提及數", "social_listener")]
    return [(f"擷取「{action}」所需的原始輸入", "generic")]


def _rule_nodes(ticket: dict[str, Any], *, rush: bool) -> list[dict[str, Any]]:
    goal = ticket.get("clarified_goal") or {}
    action = str(goal.get("core_action") or ticket.get("goal") or "執行已鎖定目標").strip()
    quantified = str(goal.get("quantified_success") or "").strip()
    audience = str(goal.get("target_audience") or "").strip()
    exclusions = _as_list((ticket.get("hard_constraints") or {}).get("absolute_exclusions"))
    ban_crawl = exclusions_ban_crawl(exclusions)
    deliverable = "交付物"
    if re.search(r"Excel|報表|报表", quantified, re.I):
        deliverable = "預警摘要（Excel 列）"
    elif re.search(r"Prototype|原型", quantified, re.I):
        deliverable = "可點擊原型說明"
    elif re.search(r"JSON", quantified, re.I):
        deliverable = "JSON 結果"

    gathers = _gather_specs(ticket, ban_crawl=ban_crawl)
    nodes: list[dict[str, Any]] = []
    idx = 1
    gather_ids: list[str] = []
    for desc, tmpl in gathers:
        for piece in _split_if_too_many_verbs(desc):
            node_id = f"N{idx}"
            nodes.append(
                {
                    "node_id": node_id,
                    "description": piece,
                    "depends_on": [],
                    "assigned_role_template": remap_template(tmpl or pick_template(piece), ban_crawl=ban_crawl),
                    "parallel_ok": True,
                }
            )
            gather_ids.append(node_id)
            idx += 1

    analyze = f"比對前序 JSON 與量化標準：{(quantified or action)[:36]}"
    write = f"撰寫{deliverable}給{audience or '發起人'}"[:72]
    if rush:
        serials = [f"融合前序產出，僅輸出{deliverable}與威脅等級"]
    else:
        serials = [analyze, write]

    parent_ids = list(gather_ids)
    for desc in serials:
        for piece in _split_if_too_many_verbs(desc):
            node_id = f"N{idx}"
            tmpl = remap_template(pick_template(piece), ban_crawl=ban_crawl)
            if tmpl in {"generic", "file_ingest"}:
                tmpl = "copy" if "撰寫" in piece or "撰写" in piece else "data_synthesizer"
            nodes.append(
                {
                    "node_id": node_id,
                    "description": piece,
                    "depends_on": list(parent_ids),
                    "assigned_role_template": tmpl,
                    "parallel_ok": False,
                }
            )
            parent_ids = [node_id]
            idx += 1
    return nodes


def _tools_for(template: str, meta: dict[str, str], ticket: dict[str, Any] | None) -> list[str]:
    tools = normalize_tools([t.strip() for t in str(meta.get("tools") or "").split(",") if t.strip()])
    constraints = (ticket or {}).get("hard_constraints") or {}
    exclusions = _as_list(constraints.get("absolute_exclusions"))
    if exclusions_ban_crawl(exclusions):
        tools = [t for t in tools if t not in CRAWL_TOOLS]
    tech = " ".join(_as_list(constraints.get("must_use_tech"))).lower()
    if "python" in tech and template in {"pdf_extractor", "code", "file_ingest"} and "python_exec" not in tools:
        tools.append("python_exec")
        tools = normalize_tools(tools)
    return tools or ["read_memory"]


def _root_input_ref(template: str, meta: dict[str, str]) -> Any:
    hint = str(meta.get("input_hint") or "").strip()
    if hint:
        return f"shared_memory://user_uploaded/{hint}"
    if template == "file_ingest":
        return "shared_memory://user_uploaded/price_source.csv"
    return _ticket_ref()


def _incubate(
    nodes: list[dict[str, Any]],
    *,
    rush: bool,
    ticket: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    ban_crawl = exclusions_ban_crawl(
        _as_list(((ticket or {}).get("hard_constraints") or {}).get("absolute_exclusions"))
    )
    for node in nodes:
        raw_tmpl = node.get("assigned_role_template") or "generic"
        tmpl = remap_template(str(raw_tmpl), ban_crawl=ban_crawl)
        node["assigned_role_template"] = tmpl
        meta = TEMPLATE_META.get(tmpl, TEMPLATE_META["generic"])
        deps = [str(d) for d in (node.get("depends_on") or [])]
        if deps:
            refs = [_memory_ref(dep) for dep in deps]
            input_ref: Any = refs if len(refs) > 1 else refs[0]
            input_label = "、".join(refs)
        else:
            input_ref = _root_input_ref(tmpl, meta)
            input_label = str(input_ref)
        tools = _tools_for(tmpl, meta, ticket)
        iters, tokens = _budget_for(tmpl, rush)
        prompt = _render_l2_prompt(
            name=meta["name"],
            task=str(node["description"]),
            input_ref=input_label,
            schema=meta["schema"],
            fallback=meta["fallback"],
            example=str(meta.get("example") or ""),
            trait=str(meta.get("trait") or ""),
        )
        success = str(meta.get("success") or "").strip() or (
            f"完成「{str(node['description'])[:40]}」且符合 {meta['schema']}"
        )
        instances.append(
            {
                "instance_id": f"ROLE-{node['node_id']}",
                "node_id": node["node_id"],
                "template_id": tmpl,
                "name": meta["name"],
                "trait": str(meta.get("trait") or ""),
                "system_prompt": prompt,
                "allowed_tools": tools,
                "input_ref": input_ref,
                "output_schema": meta["schema"],
                "success_criteria": success,
                "max_iterations": iters,
                "token_budget": tokens,
                "failure_fallback": str(meta.get("fallback") or ""),
            }
        )
    return instances


def _dump_yaml(data: Any, indent: int = 0) -> list[str]:
    space = "  " * indent
    if isinstance(data, dict):
        if not data:
            return [f"{space}{{}}"]
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.extend(_dump_yaml(value, indent + 1))
            elif isinstance(value, str) and ("\n" in value or len(value) > 88):
                lines.append(f"{space}{key}: |")
                for row in value.splitlines() or [""]:
                    lines.append(f"{space}  {row}")
            elif isinstance(value, bool):
                lines.append(f"{space}{key}: {'true' if value else 'false'}")
            elif value is None:
                lines.append(f"{space}{key}: null")
            elif isinstance(value, (int, float)):
                lines.append(f"{space}{key}: {value}")
            else:
                text = str(value).replace('"', '\\"')
                if re.search(r"[:#\[\]{}&*!|>%@`]", text) or text == "":
                    lines.append(f'{space}{key}: "{text}"')
                else:
                    lines.append(f"{space}{key}: {text}")
        return lines
    if isinstance(data, list):
        if not data:
            return [f"{space}[]"]
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.extend(_dump_yaml(item, indent + 1))
            else:
                text = str(item).replace('"', '\\"')
                lines.append(f'{space}- "{text}"' if re.search(r"[:#]", text) else f"{space}- {text}")
        return lines
    return [f"{space}{data}"]


def battle_plan_to_yaml(plan: dict[str, Any]) -> str:
    """人類可讀的作戰手冊：區塊註解 + 機器可解析 YAML。"""
    slim = {
        k: v
        for k, v in (plan or {}).items()
        if k not in {"reasoning", "serial_depth", "parallel_roots", "rush_mode"}
    }
    raw = "\n".join(_dump_yaml({"battle_plan": slim})) + "\n"
    raw = raw.replace("  global_settings:", "  # 全局執行策略\n  global_settings:", 1)
    raw = raw.replace("  dag_nodes:", "  # 節點拓撲 (DAG)\n  dag_nodes:", 1)
    raw = raw.replace(
        "  atomic_role_instances:",
        "  # L2 原子角色的具體「孵化清單」 (每個節點對應一個角色)\n  atomic_role_instances:",
        1,
    )
    return "# L3 戰術指揮官產出之物\n" + raw


def _new_plan_id(now: datetime | None = None) -> str:
    clock = now or datetime.now(timezone.utc).astimezone()
    return f"PLAN-{clock.strftime('%Y%m%d-%H%M%S')}"


def _assemble_plan(
    ticket: dict[str, Any],
    nodes: list[dict[str, Any]],
    *,
    rush: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    instances = _incubate(nodes, rush=rush, ticket=ticket)
    return {
        "plan_id": _new_plan_id(now),
        "based_on_l4_json": f"L4-JSON-HASH-{ticket_hash(ticket)}",
        "rush_mode": rush,
        "global_settings": {
            "default_model": DEFAULT_MODEL,
            "max_parallel_workers": 3 if rush else DEFAULT_MAX_PARALLEL,
            "global_timeout_minutes": 45 if rush else DEFAULT_TIMEOUT_MINUTES,
        },
        "dag_nodes": nodes,
        "atomic_role_instances": instances,
        "serial_depth": serial_depth(nodes),
        "parallel_roots": [n["node_id"] for n in nodes if not n.get("depends_on")],
        "reasoning": _build_reasoning(ticket, nodes, instances, rush=rush),
    }


def _build_reasoning(
    ticket: dict[str, Any],
    nodes: list[dict[str, Any]],
    instances: list[dict[str, Any]],
    *,
    rush: bool,
) -> dict[str, Any]:
    """拆解四步法的可檢查痕跡（內部 CoT，不灌給 L2）。"""
    goal = ticket.get("clarified_goal") or {}
    constraints = ticket.get("hard_constraints") or {}
    risks = ticket.get("risk_register") or {}
    risk_list = risks.get("identified_risks") if isinstance(risks, dict) else []
    by_node = {str(row.get("node_id")): row for row in instances}
    return {
        "parsing": {
            "core_action": str(goal.get("core_action") or ""),
            "quantified_success": str(goal.get("quantified_success") or ""),
            "deadline": str(constraints.get("deadline") or ""),
            "absolute_exclusions": _as_list(constraints.get("absolute_exclusions")),
            "identified_risks": _as_list(risk_list),
        },
        "topology": {
            "parallel": [n["node_id"] for n in nodes if not n.get("depends_on")],
            "sequential": [n["node_id"] for n in nodes if n.get("depends_on")],
            "serial_depth": serial_depth(nodes),
            "rush_mode": rush,
        },
        "templating": [
            {
                "node_id": n["node_id"],
                "template": n.get("assigned_role_template"),
                "name": (by_node.get(n["node_id"]) or {}).get("name") or "",
                "trait": (by_node.get(n["node_id"]) or {}).get("trait") or "",
                "fallback": (by_node.get(n["node_id"]) or {}).get("failure_fallback") or "",
            }
            for n in nodes
        ],
        "budgeting": [
            {
                "instance_id": row["instance_id"],
                "max_iterations": row["max_iterations"],
                "token_budget": row["token_budget"],
            }
            for row in instances
        ],
    }


def _sanitize_plan(plan: dict[str, Any], ticket: dict[str, Any], *, rush: bool) -> dict[str, Any]:
    nodes = list(plan.get("dag_nodes") or [])
    cleaned_nodes: list[dict[str, Any]] = []
    ban_crawl = exclusions_ban_crawl(
        _as_list((ticket.get("hard_constraints") or {}).get("absolute_exclusions"))
    )
    for i, node in enumerate(nodes, start=1):
        desc = str(node.get("description") or f"原子任務 {i}")
        pieces = _split_if_too_many_verbs(desc)
        deps = [str(x) for x in (node.get("depends_on") or [])]
        tmpl = str(node.get("assigned_role_template") or pick_template(desc))
        if tmpl not in TEMPLATE_META:
            tmpl = pick_template(desc)
        tmpl = remap_template(tmpl, ban_crawl=ban_crawl)
        if len(pieces) == 1:
            cleaned_nodes.append(
                {
                    "node_id": str(node.get("node_id") or f"N{i}"),
                    "description": pieces[0],
                    "depends_on": deps,
                    "assigned_role_template": tmpl,
                    "parallel_ok": not deps,
                }
            )
        else:
            base = str(node.get("node_id") or f"N{i}")
            for j, piece in enumerate(pieces):
                nid = f"{base}{chr(ord('a') + j)}" if j else base
                piece_deps = deps if j == 0 else [cleaned_nodes[-1]["node_id"]]
                cleaned_nodes.append(
                    {
                        "node_id": nid,
                        "description": piece,
                        "depends_on": piece_deps,
                        "assigned_role_template": remap_template(pick_template(piece), ban_crawl=ban_crawl),
                        "parallel_ok": not piece_deps,
                    }
                )
    if not cleaned_nodes:
        cleaned_nodes = _rule_nodes(ticket, rush=rush)
    if rush and serial_depth(cleaned_nodes) > 2:
        roots = [n for n in cleaned_nodes if not n.get("depends_on")] or [cleaned_nodes[0]]
        last = cleaned_nodes[-1]
        last["depends_on"] = [str(n["node_id"]) for n in roots]
        last["parallel_ok"] = False
        cleaned_nodes = [*roots, last]
    assembled = _assemble_plan(ticket, cleaned_nodes, rush=rush)
    assembled["plan_id"] = str(plan.get("plan_id") or assembled["plan_id"])
    if plan.get("global_settings"):
        assembled["global_settings"].update(
            {k: v for k, v in plan["global_settings"].items() if v is not None}
        )
        assembled["global_settings"]["max_parallel_workers"] = min(
            8, max(1, int(assembled["global_settings"].get("max_parallel_workers") or DEFAULT_MAX_PARALLEL))
        )
    return assembled


def _llm_plan(ticket: dict[str, Any], *, rush: bool) -> dict[str, Any] | None:
    try:
        from backend.core.llm import call_llm, parse_json_response

        prompt = (
            "將下列 L4 戰術指令拆成原子 DAG。"
            "每個節點描述不得超過 3 個動詞；L2 system_prompt 必須 < 200 token，"
            "且含 input_ref 與 output_schema；allowed_tools 必須是白名單子集，"
            "禁止 all。獨立蒐集節點必須並行（depends_on=[]），融合／撰寫節點才串行。"
            f"極速模式={rush}（若為 true，串行深度最多 2，但可保留並行蒐集）。"
            "必須遵守 absolute_exclusions（例如禁止爬蟲則不得使用 web_fetch）。\n"
            "只輸出 JSON："
            '{"dag_nodes":[{"node_id":"N1","description":"...","depends_on":[],'
            '"assigned_role_template":"web_scraper","parallel_ok":true}]}\n\n'
            f"{json.dumps(ticket, ensure_ascii=False)}"
        )
        from backend.company.raho.l0 import inject_l0

        goal = ""
        clarified = ticket.get("clarified_goal") if isinstance(ticket.get("clarified_goal"), dict) else {}
        if clarified:
            goal = str(clarified.get("core_action") or clarified.get("quantified_success") or "")
        raw = call_llm(
            prompt,
            system=inject_l0(SYSTEM_PROMPT, int(RahoLayer.L3_COMMANDER), goal or str(ticket)[:240]),
        )
        data = parse_json_response(raw)
        if isinstance(data, dict) and data.get("dag_nodes"):
            return data
        if isinstance(data, dict) and isinstance(data.get("battle_plan"), dict):
            return data["battle_plan"]
    except Exception as exc:  # noqa: BLE001
        logger.debug("L3 LLM 拆解降級為規則引擎：%s", exc)
    return None


def build_escalation(
    *,
    reason: str,
    details: str,
    alternatives: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": STATUS_ESCALATE_USER,
        "reason": reason,
        "details": details,
        "suggested_alternatives": alternatives
        or [
            "方案 A：縮小範圍後重拆（推薦）",
            "方案 B：放寬時程或預算後重拆",
        ],
        "waiting_for_user_decision": True,
        "role": "tactical_commander",
        "role_label": LAYER_LABELS.get(int(RahoLayer.L3_COMMANDER), "L3 戰術指揮官"),
    }


def commander_llm_enabled() -> bool:
    return os.getenv("EVOL_RAHO_COMMANDER_LLM", "false").lower() in {"1", "true", "yes", "on"}


def plan_from_ticket(
    ticket: dict[str, Any] | str,
    *,
    now: datetime | None = None,
    use_llm: bool | None = None,
) -> dict[str, Any]:
    """主入口：門票 → 檢查 → 拆解 → 作戰手冊。"""
    parsed = extract_ticket(ticket) if not isinstance(ticket, dict) else extract_ticket(ticket) or ticket
    if not isinstance(parsed, dict) or parsed.get("status") != "APPROVED_FOR_PLANNING":
        return {
            "status": STATUS_REJECT_L4,
            "reason": "門票無效",
            "defects": ["缺少 status=APPROVED_FOR_PLANNING 的 L4 JSON"],
            "waiting_for_l4": True,
            "role": "tactical_commander",
            "role_label": LAYER_LABELS.get(int(RahoLayer.L3_COMMANDER), "L3 戰術指揮官"),
        }

    check = validate_ticket(parsed, now=now)
    if not check["ok"]:
        return {
            "status": STATUS_REJECT_L4,
            "reason": "門票檢查未過",
            "defects": check["defects"],
            "checklist": check,
            "waiting_for_l4": True,
            "role": "tactical_commander",
            "role_label": LAYER_LABELS.get(int(RahoLayer.L3_COMMANDER), "L3 戰術指揮官"),
        }

    blocked = detect_infeasible(parsed, now=now)
    if blocked:
        pack = build_escalation(**blocked)
        pack["checklist"] = check
        return pack

    rush = bool(check["rush_mode"])
    if use_llm is None:
        from backend.company.raho.scorecard import should_demote

        use_llm = commander_llm_enabled()
        if should_demote("tactical_commander") or should_demote("manager"):
            use_llm = False
    llm_plan = _llm_plan(parsed, rush=rush) if use_llm else None
    if llm_plan:
        battle = _sanitize_plan(llm_plan, parsed, rush=rush)
        source = "llm"
    else:
        battle = _assemble_plan(parsed, _rule_nodes(parsed, rush=rush), rush=rush, now=now)
        source = "rule"

    yaml_text = battle_plan_to_yaml(battle)
    pack = {
        "status": STATUS_PLAN_READY,
        "role": "tactical_commander",
        "role_label": LAYER_LABELS.get(int(RahoLayer.L3_COMMANDER), "L3 戰術指揮官"),
        "rush_mode": rush,
        "checklist": check,
        "source": source,
        "battle_plan": battle,
        "battle_plan_yaml": yaml_text,
        "reasoning": battle.get("reasoning") or {},
        "node_count": len(battle.get("dag_nodes") or []),
        "serial_depth": battle.get("serial_depth"),
        "based_on_l4_json": battle.get("based_on_l4_json"),
    }
    try:
        from backend.company.raho.l0 import attach_to_plan

        goal = ""
        clarified = parsed.get("clarified_goal") if isinstance(parsed.get("clarified_goal"), dict) else {}
        if clarified:
            goal = str(clarified.get("core_action") or clarified.get("quantified_success") or "")
        attach_to_plan(pack, query=goal or str(parsed.get("clarified_goal") or "")[:240])
    except Exception:  # noqa: BLE001
        pass
    return pack


def classify_grill(issues: list[GrillIssue] | list[str] | str) -> str:
    if isinstance(issues, str):
        text = issues
        blockers: list[str] = []
    else:
        parts = []
        blockers = []
        for item in issues:
            if isinstance(item, GrillIssue):
                parts.append(item.message)
                if item.blocker_type:
                    blockers.append(item.blocker_type)
            else:
                parts.append(str(item))
        text = "\n".join(parts)
    for blocker in blockers:
        mapped = _BLOCKER_KIND.get(blocker)
        if mapped:
            return mapped
    if _GRILL_DATA.search(text):
        return GRILL_DATA
    if _GRILL_TOOL.search(text):
        return GRILL_TOOL
    if _GRILL_LOGIC.search(text):
        return GRILL_LOGIC
    if _GRILL_CONSTRAINT.search(text):
        return "constraint_conflict"
    return GRILL_CLARIFY


def _conflict_ruling(text: str) -> str:
    """從 L2 質詢抽出衝突節點，給出「以 A 為準，B 需修正」。"""
    found: list[str] = []
    for match in re.finditer(r"(?:節點\s*)([A-Z]\d+|[A-Z])|([A-Z]\d+|[A-Z])\s*節點", text or ""):
        token = match.group(1) or match.group(2)
        if token and token not in found:
            found.append(token)
    if len(found) >= 2:
        return f"以 {found[0]} 為準，{found[1]} 需修正"
    return ""


def _requested_tool(text: str) -> str:
    raw = text or ""
    unknown = ("ffmpeg", "whisper", "opencv")
    for name in unknown:
        if name in raw.lower():
            return name
    for name in list(TOOL_ALIASES) + list(KNOWN_TOOLS):
        if name in raw:
            return TOOL_ALIASES.get(name, name)
    match = re.search(r"`([a-zA-Z0-9_]+)`", raw)
    return match.group(1) if match else ""


def respond_to_grill(
    issues: list[GrillIssue] | list[str] | str,
    *,
    allowed_tools: list[str] | None = None,
    alternative_fields: list[str] | None = None,
    priority_ruling: str = "",
    rounds_used: int = 0,
) -> dict[str, Any]:
    """L2 → L3 Grill SOP。3 輪無解即 [ESCALATE]。"""
    if isinstance(issues, str):
        messages = [issues]
    else:
        messages = [
            item.message if isinstance(item, GrillIssue) else str(item) for item in issues
        ]
    text = "\n".join(messages)
    kind = classify_grill(issues)
    escalate_forced = rounds_used >= MAX_SUPERIOR_ROUNDS

    if kind == GRILL_CLARIFY and not escalate_forced:
        if re.search(r"高品質|品質|质量|深刻|語法", text):
            reply = (
                "『高品質』量化定義：語法錯誤 < 1 處，且每個觀點需引用至少 2 個"
                "已在 input_ref 中的來源。超出範圍的形容詞一律忽略。"
            )
        else:
            reply = (
                "量化定義：交付必須符合 output_schema；缺欄留空；"
                "禁止引入 input_ref 以外的數據；觀點需引用至少 2 個來源，語法錯誤 < 1 處。"
            )
        return {
            "action": "resolve",
            "kind": kind,
            "escalate": False,
            "escalate_to": "",
            "reply": reply,
            "rounds_used": rounds_used + 1,
        }

    if kind == GRILL_DATA:
        alts = [f for f in (alternative_fields or []) if f]
        if alts and not escalate_forced:
            return {
                "action": "resolve",
                "kind": kind,
                "escalate": False,
                "escalate_to": "",
                "reply": f"來源缺欄時改用替代欄位：{', '.join(alts)}。取得到的值原樣輸出，缺則留空。",
                "rounds_used": rounds_used + 1,
            }
        return {
            "action": "escalate",
            "kind": kind,
            "escalate": True,
            "escalate_to": "L4",
            "reply": f"{ESCALATE_MARK} 資料源缺失，L2 已暫停。請 L4 補充替代數據源。原文：{text[:180]}",
            "rounds_used": rounds_used + 1,
        }

    if kind == GRILL_TOOL:
        requested = _requested_tool(text)
        allow = normalize_tools(list(allowed_tools or []) + ([requested] if requested in KNOWN_TOOLS else []))
        if requested in KNOWN_TOOLS and not escalate_forced:
            return {
                "action": "resolve",
                "kind": kind,
                "escalate": False,
                "escalate_to": "",
                "reply": f"白名單已重發，僅允許：{', '.join(allow)}。用 {requested} 重試一次。",
                "reissued_tools": allow,
                "rounds_used": rounds_used + 1,
            }
        return {
            "action": "escalate",
            "kind": kind,
            "escalate": True,
            "escalate_to": "L5",
            "reply": (
                f"{ESCALATE_MARK} 基礎設施缺失：系統無「{requested or '所需工具'}」。"
                "該節點標記為不可執行，交 L5 決定是否安裝新工具。"
            ),
            "infrastructure_missing": requested or "unknown",
            "rounds_used": rounds_used + 1,
        }

    if kind == GRILL_LOGIC:
        ruling = (priority_ruling or "").strip() or _conflict_ruling(text)
        if ruling and not escalate_forced:
            return {
                "action": "resolve",
                "kind": kind,
                "escalate": False,
                "escalate_to": "",
                "reply": f"優先級裁定：{ruling}。衝突節點一律服從此裁定。",
                "priority_ruling": ruling,
                "rounds_used": rounds_used + 1,
            }
        return {
            "action": "escalate",
            "kind": kind,
            "escalate": True,
            "escalate_to": "L4",
            "reply": f"{ESCALATE_MARK} 節點目標互斥，L3 無法裁定。請 L4 規劃官給優先序。{text[:160]}",
            "rounds_used": rounds_used + 1,
        }

    if kind == "constraint_conflict":
        if not escalate_forced:
            return {
                "action": "resolve",
                "kind": kind,
                "escalate": False,
                "escalate_to": "",
                "reply": "約束已放寬：max_iterations 至少 2，token_budget 至少 400。請重新執行戰前檢查後再動手。",
                "reissued_budget": {"max_iterations": 2, "token_budget": 400},
                "rounds_used": rounds_used + 1,
            }
        return {
            "action": "escalate",
            "kind": kind,
            "escalate": True,
            "escalate_to": "L4",
            "reply": f"{ESCALATE_MARK} 資源約束衝突，L3 無法再放寬。請 L4 重核預算。{text[:160]}",
            "rounds_used": rounds_used + 1,
        }

    return {
        "action": "escalate",
        "kind": kind,
        "escalate": True,
        "escalate_to": "L4",
        "reply": f"{ESCALATE_MARK} 已滿 {MAX_SUPERIOR_ROUNDS} 輪仍未解，上交。{text[:160]}",
        "rounds_used": rounds_used + 1,
    }


def increment_grill_round(item_id: str) -> int:
    from backend.company.raho.store import STORE

    return STORE.bump_grill_round(item_id)


def grill_rounds(item_id: str) -> int:
    from backend.company.raho.store import STORE

    return STORE.grill_round(item_id)


class TacticalCommander:
    """L3 戰術指揮官。無狀態；會話資料由 RAHO STORE 持有。"""

    def __init__(self) -> None:
        self.system_prompt = SYSTEM_PROMPT
        self.max_l2_tokens = MAX_L2_PROMPT_TOKENS

    def plan(self, ticket: dict[str, Any] | str, *, use_llm: bool = True) -> dict[str, Any]:
        return plan_from_ticket(ticket, use_llm=use_llm)

    def grill(
        self,
        issues: list[GrillIssue] | list[str] | str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return respond_to_grill(issues, **kwargs)

    def escalate(self, reason: str, details: str, alternatives: list[str] | None = None) -> dict[str, Any]:
        return build_escalation(reason=reason, details=details, alternatives=alternatives)


def apply_commander_system(system_prompt: str) -> str:
    """把 L3 鐵律接到既有上級 System Prompt 前方。"""
    body = (system_prompt or "").strip()
    if "戰術指揮官" in body and "Atomic SRP" in body and "微雕與偏執" in body:
        return body
    return f"{MGP_SUPERIOR_PREAMBLE}\n\n{SYSTEM_PROMPT}\n\n{body}".strip()


def l2_brief_ok(prompt: str) -> bool:
    return estimate_tokens(prompt) <= MAX_L2_PROMPT_TOKENS


__all__ = [
    "GRILL_CLARIFY",
    "GRILL_DATA",
    "GRILL_LOGIC",
    "GRILL_MARK",
    "GRILL_SOP",
    "GRILL_TOOL",
    "KNOWN_TOOLS",
    "MAX_L2_PROMPT_TOKENS",
    "STATUS_ESCALATE_USER",
    "STATUS_PLAN_READY",
    "STATUS_REJECT_L4",
    "SYSTEM_PROMPT",
    "TacticalCommander",
    "MGP_EXECUTOR_PREAMBLE",
    "apply_commander_system",
    "battle_plan_to_yaml",
    "build_escalation",
    "classify_grill",
    "clip_prompt",
    "count_verbs",
    "detect_infeasible",
    "estimate_tokens",
    "exclusions_ban_crawl",
    "extract_ticket",
    "grill_rounds",
    "has_concrete_object",
    "hours_until_deadline",
    "increment_grill_round",
    "l2_brief_ok",
    "l2_task_brief",
    "normalize_tools",
    "pick_template",
    "plan_from_ticket",
    "remap_template",
    "respond_to_grill",
    "serial_depth",
    "ticket_hash",
    "validate_ticket",
]
