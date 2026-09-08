"""Requirement Auditor（L4 需求審計官）：強制前置閘門。

不是普通聊天。五維內部評分皆 > 90 才輸出「戰術指令 JSON」，
交給後續 Dynamic Planner；否則繼續追問或觸發終止協議。

與既有 `/raho/grill/*` 閘門共用會話倉，不另開平行管線。
LLM 一律經 `backend.core.llm.call_llm`。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.company.raho.protocol import (
    LAYER_LABELS,
    GrillQuestion,
    RahoLayer,
    SemanticLock,
    user_grill_enabled,
)
from backend.company.raho.store import STORE, UserGrillSession
from backend.services.auditor_prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

AUDITOR_DIM_THRESHOLD = 90.0
MAX_PHASE_ROUNDS = 3
MAX_AUDITOR_ROUNDS = 10
CONFIDENCE_THRESHOLD = 0.90

DIM_KEYS = ("specificity", "boundary", "constraints", "risk", "success")
DIM_LABELS = {
    "specificity": "目標具體性",
    "boundary": "邊界清晰度",
    "constraints": "約束量化度",
    "risk": "風險感知度",
    "success": "成功定義",
}
PHASE_LABELS = {
    1: "Phase 1 基礎錨定",
    2: "Phase 2 量化絞殺",
    3: "Phase 3 對抗性壓力測試",
    4: "Phase 4 語義鎖定",
}

_VAGUE = re.compile(r"(大概|盡量|尽量|好一點|好一点|隨便|随便|看看|差不多|或許|或许|可能吧)")
_OVER_AUTH_PHRASE = re.compile(
    r"(你看著辦|你看着办|你是 AI 你應該比我懂|你是AI你應該比我懂|你應該比我懂|你应该比我懂)"
)
_QUANT = re.compile(
    r"(\d+(\.\d+)?\s*(%|％|小時|小时|分鐘|分钟|天|週|周|萬|万|元|塊|块|人)|"
    r"\d{4}-\d{2}-\d{2})"
)
_METRIC_WORD = re.compile(
    r"(gmv|kpi|roi|復購|复购|轉化|转化|誤報|误报|準確|准确|預算|预算)",
    re.IGNORECASE,
)
_RATE_PAIR = re.compile(r"(\d+(?:\.\d+)?)\s*%[^%\n]{0,32}(\d+(?:\.\d+)?)\s*%")
_MONEY = re.compile(r"(\d+(?:\.\d+)?)\s*(萬|万|元|塊|块)")
_REVIEW_GATE = re.compile(r"(人工審核|人工审核|停止推播|人工確認|人工确认)")
_QUALITY_BOUND = re.compile(r"(品質不可|质量不可|不可降|不得降|絕對不|绝对不)")
_SUBJECT = re.compile(r"(用戶|用户|客群|受眾|受众|賣家|卖家|粉絲|粉丝|員工|员工|客戶|客户|終端|终端|老闆|老板|發起人|发起人)")
_ACTION = re.compile(
    r"(生成|壓縮|压缩|提升|預警|预警|調價|调价|產出|产出|交付|盯盤|盯盘|審核|审核|追蹤|追踪)"
)
_BEFORE_AFTER = re.compile(r"(目前|現狀|现状|介入前|目標|目标|壓縮至|压缩至|從.{0,12}到|提升到)")
_BOUNDARY = re.compile(
    r"(不做|不包含|不使用|不開發|不开发|排除|絕對不|绝对不|禁止|只做|必須|必须|先做|"
    r"人工審核|人工审核|停止推播)"
)
_BUDGET = re.compile(r"(預算|预算|萬|万|USD|usd|新台幣|新台币|\d+\s*(元|塊|块))")
_TIME = re.compile(r"(時程|时程|期限|deadline|週內|周内|天內|天内|\d{4}-\d{2}-\d{2}|上線|上线)")
_RESOURCE = re.compile(
    r"(人力|幾人|几人|Python|PostgreSQL|API|Excel|Prototype|既有|資料庫|数据库|Line Notify)"
)
_TRADEOFF = re.compile(r"(砍功能|延後|延后|借貸|借贷|犧牲|牺牲|範圍|范围|時程|时程|成本|優先|优先)")
_RISK = re.compile(r"(備案|备案|失敗|失败|風險|风险|斷了|断了|退粉|誤報|误报|停損|停损|降級|降级)")
_FALLBACK = re.compile(r"(人工確認|人工确认|人工審核|人工审核|CSV|手動|手动|停止推播|按下停止)")
_SUCCESS = re.compile(
    r"(準確率|准确率|誤報率|误报率|復購率|复购率|小時|小时|分鐘|分钟|不得低於|不得低于|"
    r"Excel|Prototype|報表|报表|JSON|備忘錄|备忘录|可點擊|可点击)"
)
_CONFIRM = re.compile(r"^(確認|确认|確認無誤|确认无误|確認鎖定|确认锁定|同意|無誤|无误|作為最終|作为最终)")
_UNLIMITED_BUDGET = re.compile(r"(預算無限|预算无限|不限預算|不限预算|多少錢都行|多少钱都行)")
_FREE_OSS = re.compile(r"(開源免費|开源免费|必須免費|必须免费|零成本|不能花錢|不能花钱)")
_COMPLEX = re.compile(
    r"(开发|設計|设计|构建|實現|实现|建立|打造|完整|系統|系统|專案|项目|"
    r"多步|架構|架构|提升|優化|优化|策略|報告|报告|develop|build|implement|"
    r"design|create|project|system|管粉|自動|自动)",
    re.IGNORECASE,
)
_VAGUE_VERB_PRIORITY = (
    "管粉絲",
    "管粉丝",
    "自動管",
    "自动管",
    "幫我管",
    "帮我管",
    "管粉",
    "提升效率",
    "優化一下",
    "优化一下",
    "弄一個",
    "弄一个",
    "搞一個",
    "搞一个",
)
_FAN_KEYS = (
    "管粉絲",
    "管粉丝",
    "管粉",
    "粉絲",
    "粉丝",
    "自動管",
    "自动管",
    "幫我管",
    "帮我管",
)
_SOFT_GOAL = re.compile(
    r"(更黏|黏我|多買|多买|更好|提升效率|優化|优化|改善|智慧|智能|管粉|隨便|随便|看看)"
)
_FAN_METRIC = re.compile(r"(復購|复购|回購|回购)")
_FAN_COST = re.compile(r"(單粉|单粉|每個新粉|每个新粉|行銷成本|营销成本|\d+\s*(元|塊|块))")

# 4 階段 16 題（1–11 一字不改；12–16 補齊攻擊角度）
QUESTION_BANK: list[dict[str, Any]] = [
    {
        "id": 1,
        "phase": 1,
        "dimension": "specificity",
        "question": "我們現在不談解決方案。請用『最終用戶』的視角，描述他完成任務前後那一刻的具體變化。",
        "why": "沒有前後對照，目標只是口號。",
    },
    {
        "id": 2,
        "phase": 1,
        "dimension": "specificity",
        "question": "現狀的痛點是什麼？如果用數字量化這個痛點，目前每個月損失多少錢 / 浪費多少小時？",
        "why": "痛點不能停留在感受，必須可計價。",
    },
    {
        "id": 3,
        "phase": 1,
        "dimension": "specificity",
        "question": "這個需求的發起人是誰？是終端使用者要的，還是你老闆覺得要的？這兩者的差異你怎麼處理？",
        "why": "發起人錯位會讓驗收標準對不上使用者。",
    },
    {
        "id": 12,
        "phase": 1,
        "dimension": "specificity",
        "question": "這個任務不做會怎樣？90 天後現狀會惡化到什麼可量化程度？請給數字。",
        "why": "沒有不做的代價，優先序無法鎖定。",
    },
    {
        "id": 4,
        "phase": 2,
        "dimension": "success",
        "question": "我不接受『提升效率』。請填入數字：『目前需 X 小時，目標壓縮至 Y 小時，且準確率不得低於 Z%』，請現在給出 X、Y、Z。",
        "why": "效率必須是可驗收的三段數字。",
    },
    {
        "id": 5,
        "phase": 2,
        "dimension": "constraints",
        "question": "若預算超支 30%，你是要砍功能（犧牲範圍），還是延後上線（犧牲時間），還是借貸補足（犧牲成本）？請排序。",
        "why": "超支時沒有取捨順序，下層會隨機亂選。",
    },
    {
        "id": 6,
        "phase": 2,
        "dimension": "success",
        "question": "所謂的『完成』，具體會產出什麼格式的交付物？是 Excel 報表、可點擊的 Prototype，還是一份純文字的備忘錄？",
        "why": "交付物格式決定戰役地圖的終態節點。",
    },
    {
        "id": 13,
        "phase": 2,
        "dimension": "constraints",
        "question": "人力投入是幾人、每天幾小時、持續幾週？既有系統／資料庫／帳號有哪些必須沿用的技術？請給數字與名單。",
        "why": "約束不是形容詞，是清單與數字。",
    },
    {
        "id": 7,
        "phase": 3,
        "dimension": "risk",
        "question": "假設這個方案做出來，但關鍵數據源（如 API）突然斷了，你的備案是什麼？如果沒有備案，我將標記此需求為高風險。",
        "why": "沒有備案就等於把失敗外包給運氣。",
    },
    {
        "id": 8,
        "phase": 3,
        "dimension": "risk",
        "question": "你提到希望系統『智慧』一點，但同時又要求『絕對可控』。這兩者是互斥的，當 AI 的判斷與你的直覺衝突時，你聽誰的？具體情境下如何取捨？",
        "why": "智慧與可控衝突時必須先寫死裁決者。",
    },
    {
        "id": 9,
        "phase": 3,
        "dimension": "boundary",
        "question": "如果只能做到現在所提需求的 80%，剩下的 20% 你願意犧牲哪一部分？請具體指出這 20% 的內容。",
        "why": "沒有可犧牲的 20%，範圍就是無限膨脹。",
    },
    {
        "id": 14,
        "phase": 3,
        "dimension": "risk",
        "question": "若上線後第一週指標不升反降，停損條件是什麼？誰有權按下停止？請給觸發數字與角色。",
        "why": "沒有停損條件，失敗會被當成『再觀察一下』。",
    },
    {
        "id": 10,
        "phase": 4,
        "dimension": "success",
        "question": "為了避免誤會，請用你自己的話（不許複製貼上）重新定義一次『成功』，字數不得超過 50 字。",
        "why": "複誦才能暴露殘餘歧義。",
    },
    {
        "id": 11,
        "phase": 4,
        "dimension": "success",
        "question": "如果我現在交付了你說的 A 功能，但你實際想要的是 B 感覺，後果由誰承擔？你現在確定要將剛才的所有回答作為最終合約依據嗎？",
        "why": "合約鎖定前必須把責任歸屬講死。",
    },
    {
        "id": 15,
        "phase": 4,
        "dimension": "boundary",
        "question": "請列出三個『絕對不可以發生』的結果，作為驗收否決項。",
        "why": "否決項是邊界的最後一道鎖。",
    },
    {
        "id": 16,
        "phase": 4,
        "dimension": "success",
        "question": "請確認：以上回答將作為 Planner 唯一依據。若之後改口，以本輪鎖定為準。同意請回覆『確認鎖定』。",
        "why": "沒有明示確認就不能發門票。",
    },
]

OVER_AUTH_REPLY = "我無法為我無法理解的目標負責，請重新填寫 Phase 2 的量化指標。"

FAN_PHASE2_QUESTION = (
    "量化失敗。請填入數字：\n\n"
    "① 目前的「復購率（回購人數 / 總人數）」是 ___ %，目標提升到 ___ %？\n\n"
    "② 你願意為每個新粉絲投入多少新台幣的行銷成本？"
)
FAN_PHASE3_QUESTION = (
    "進行壓力測試：如果系統推薦的內容導致 5 個老粉退粉，"
    "你希望系統自動停止推播，還是改為人工審核？請選擇。"
)


def _opening_hook(query: str) -> str:
    """第一問開場：拒絕模糊動詞，對齊規格中的「被烤」體驗。"""
    text = (query or "").strip()
    for verb in _VAGUE_VERB_PRIORITY:
        if verb in text:
            return f"收到需求。我不接受「{verb}」這個模糊動詞。"
    return "收到需求。"


def _contextual_first_question(query: str) -> GrillQuestion | None:
    """粉絲／管粉類模糊需求：第一問直接用規格範例話術，不先丟題庫 Q1。"""
    text = (query or "").strip()
    if any(verb in text for verb in ("管粉絲", "管粉丝", "管粉", "自動管", "自动管", "幫我管", "帮我管")):
        return GrillQuestion(
            "收到需求。我不接受「管粉絲」這個模糊動詞。請用「最終用戶（粉絲）」的視角描述：在你介入前他們得不到什麼？在你介入後他們獲得了什麼具體好處？",
            why="沒有前後對照，目標只是口號。",
            dimension="specificity",
        )
    return None


def _vague_prefix(phase: int) -> str:
    if int(phase or 1) >= 2:
        return "量化失敗。請填入數字："
    return "量化失敗。我不接受『大概／盡量／好一點』。"


def _with_phase_tag(question: str, phase: int) -> str:
    tag = f"（Phase {int(phase or 1)}）"
    raw = (question or "").rstrip()
    if re.search(r"（Phase [1-4]）|\(Phase [1-4]\)", raw):
        return raw
    return f"{raw}{tag}"


def should_grill_user(query: str, execution_strategy: str = "auto") -> bool:
    """是否應先經審計官閘門。簡單模式與寒暄一律跳過。"""
    if not user_grill_enabled():
        return False
    strategy = (execution_strategy or "auto").strip().lower()
    if strategy == "simple":
        return False
    if strategy == "company":
        return True
    text = query or ""
    return len(text) >= 200 or bool(_COMPLEX.search(text))


def _joined(query: str, answers: list[str] | None) -> str:
    return (query or "").strip() + "\n" + "\n".join(answers or [])


def _clamp(score: float) -> float:
    return max(0.0, min(100.0, score))


def _has_rate_pair(text: str) -> bool:
    raw = text or ""
    if _RATE_PAIR.search(raw):
        return True
    return len(re.findall(r"\d+(?:\.\d+)?\s*%", raw)) >= 2


def _has_money(text: str) -> bool:
    return bool(_MONEY.search(text or "") or _BUDGET.search(text or ""))


def _has_review_gate(text: str) -> bool:
    return bool(_REVIEW_GATE.search(text or "") or _FALLBACK.search(text or ""))


def score_dimensions(query: str, answers: list[str] | None = None) -> dict[str, float]:
    """五維 0–100 評分（規則引擎，測試可重現、不呼叫 LLM）。"""
    text = _joined(query, answers)
    answers = answers or []
    last = answers[-1] if answers else ""
    fan = _is_fan_scenario(query)
    rate_pair = _has_rate_pair(text)
    money = _has_money(text)
    review_gate = _has_review_gate(text)
    metric = bool(_FAN_METRIC.search(text) or (fan and rate_pair))

    spec = 18.0
    if _SUBJECT.search(text):
        spec += 22.0
    if _ACTION.search(text):
        spec += 16.0
    if _QUANT.search(text):
        spec += 28.0
    elif _METRIC_WORD.search(text):
        spec += 8.0
    if _BEFORE_AFTER.search(text):
        spec += 18.0
    if metric and _QUANT.search(text):
        spec += 12.0
    if rate_pair:
        spec += 10.0
    if _VAGUE.search(last) and not _QUANT.search(last):
        spec = min(spec, 38.0)
    if len(text) < 16:
        spec = min(spec, 32.0)

    boundary = 12.0
    if _BOUNDARY.search(text):
        boundary += 42.0
    if re.search(r"(80%|20%|犧牲|牺牲)", text):
        boundary += 24.0
    if review_gate or re.search(r"(絕對可控|绝对可控)", text):
        boundary += 40.0
    if _QUALITY_BOUND.search(text):
        boundary += 24.0
    if len(re.findall(r"(不做|不使用|不開發|不开发|絕對不|绝对不)", text)) >= 2:
        boundary += 18.0
    if _VAGUE.search(last) and not _BOUNDARY.search(last) and not review_gate:
        boundary = min(boundary, 40.0)

    constraints = 10.0
    if _BUDGET.search(text) or money:
        constraints += 28.0
    if _TIME.search(text):
        constraints += 26.0
    if _RESOURCE.search(text):
        constraints += 18.0
    if _TRADEOFF.search(text):
        constraints += 20.0
    if metric and (_FAN_COST.search(text) or money):
        constraints += 40.0
    if fan and rate_pair and money:
        constraints += 16.0
    if _VAGUE.search(last) and not _QUANT.search(last):
        constraints = min(constraints, 35.0)

    risk = 10.0
    if _RISK.search(text):
        risk += 32.0
    if _FALLBACK.search(text) or review_gate:
        risk += 36.0
    if re.search(r"(聽誰|听谁|人工|停損|停损|衝突|冲突)", text):
        risk += 16.0
    if review_gate:
        risk += 28.0
    if _VAGUE.search(last) and not _RISK.search(last) and not review_gate:
        risk = min(risk, 36.0)

    success = 10.0
    if re.search(r"(目前.{0,20}\d+.{0,20}(目標|目标|壓縮|压缩).{0,20}\d+)", text):
        success += 32.0
    elif _BEFORE_AFTER.search(text) and _QUANT.search(text):
        success += 24.0
    if _SUCCESS.search(text) or rate_pair:
        success += 28.0
    if re.search(r"(Excel|Prototype|報表|报表|備忘錄|备忘录|JSON)", text, re.IGNORECASE):
        success += 18.0
    if any(_CONFIRM.search(a.strip()) for a in answers):
        success += 12.0
    if metric and _QUANT.search(text):
        success += 22.0
    if fan and rate_pair and review_gate:
        success += 16.0
    if _VAGUE.search(last) and not _QUANT.search(last):
        success = min(success, 36.0)

    return {
        "specificity": round(_clamp(spec), 1),
        "boundary": round(_clamp(boundary), 1),
        "constraints": round(_clamp(constraints), 1),
        "risk": round(_clamp(risk), 1),
        "success": round(_clamp(success), 1),
    }


def score_requirement(query: str, answers: list[str] | None = None) -> tuple[float, list[str]]:
    """向後相容：回傳 (0–1 綜合置信度, 缺口維度)。鎖定仍看五維皆 > 90。"""
    dims = score_dimensions(query, answers)
    if not dims:
        return 0.05, list(DIM_KEYS)
    overall = sum(float(v) for v in dims.values()) / (100.0 * len(dims))
    gaps = [key for key, val in dims.items() if val <= AUDITOR_DIM_THRESHOLD]
    legacy = []
    if "success" in gaps or "specificity" in gaps:
        legacy.append("metric")
    if "constraints" in gaps:
        legacy.append("tradeoff")
    if "boundary" in gaps:
        legacy.append("scope")
    return max(0.05, min(0.99, overall)), legacy or gaps


def all_dims_locked(scores: dict[str, float]) -> bool:
    return bool(scores) and all(float(scores.get(k, 0)) > AUDITOR_DIM_THRESHOLD for k in DIM_KEYS)


def extract_json(text: str) -> dict[str, Any] | None:
    """從回應中擷取戰術指令 JSON。"""
    raw = text or ""
    if "APPROVED_FOR_PLANNING" not in raw and "```json" not in raw:
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if not fence:
            return None
        raw = fence.group(1)
    try:
        from backend.core.llm import parse_json_response

        data = parse_json_response(raw)
    except Exception:  # noqa: BLE001
        match = re.search(r"\{.*\}", raw, re.DOTALL)
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


def _is_vague(text: str) -> bool:
    return bool(_VAGUE.search(text or "")) and not _QUANT.search(text or "")


def _is_fan_scenario(query: str) -> bool:
    return any(key in (query or "") for key in _FAN_KEYS)


def _fan_contract_ready(sess: UserGrillSession) -> bool:
    """規格第 6 節：復購率 + 單粉成本 + 人工審核備案齊了，才准進語義鎖定放行。"""
    if not _is_fan_scenario(sess.query):
        return False
    text = _joined(sess.query, _user_answers(sess))
    if not _has_rate_pair(text):
        return False
    if not _has_money(text):
        return False
    if not _has_review_gate(text):
        return False
    if int(sess.phase or 1) < 4 and 10 not in sess.asked_ids:
        return False
    return True


def _is_unquantified(text: str, phase: int = 1) -> bool:
    """無數字的軟目標／模糊詞視為無效；Phase 2 起更嚴格要求量化。"""
    raw = (text or "").strip()
    if not raw:
        return True
    if _QUANT.search(raw):
        return False
    if _CONFIRM.search(raw):
        return False
    if _is_vague(raw) or _SOFT_GOAL.search(raw):
        return True
    if int(phase or 1) >= 2 and not (
        _TRADEOFF.search(raw) or _FALLBACK.search(raw) or _BOUNDARY.search(raw)
    ):
        return True
    return False


def _synthesize_fan_lock(sess: UserGrillSession) -> str:
    text = _joined(sess.query, _user_answers(sess))
    rates = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    target = rates[-1] if rates else "目標值"
    cost = re.search(r"(\d+(?:\.\d+)?)\s*(元|塊|块)", text)
    cost_s = f"{cost.group(1)} 元" if cost else "已標示單粉成本"
    review = "且關鍵推播需經人工審核" if re.search(r"人工", text) else "且需有停損備案"
    return (
        f"語義鎖定：請用 50 字總結：「此專案是為提升復購率至 {target}%，"
        f"預算單粉 {cost_s}，{review}」。確認無誤我將產出作戰圖。"
    )


def _scenario_next(sess: UserGrillSession) -> GrillQuestion | None:
    """規格第 6 節粉絲／管粉情境：走範例話術，不先丟通用題庫。"""
    if not _is_fan_scenario(sess.query):
        return None
    answers = _user_answers(sess)
    last = answers[-1] if answers else ""
    if sess.user_rounds >= 1 and 4 not in sess.asked_ids and _is_unquantified(last, 1):
        sess.phase = 2
        sess.phase_rounds = 0
        sess.asked_ids.append(4)
        return GrillQuestion(
            FAN_PHASE2_QUESTION,
            why="效率必須是可驗收的三段數字。",
            dimension="success",
        )
    if 4 in sess.asked_ids and 7 not in sess.asked_ids and _QUANT.search(last):
        sess.phase = 3
        sess.phase_rounds = 0
        sess.asked_ids.append(7)
        return GrillQuestion(
            FAN_PHASE3_QUESTION,
            why="沒有備案就等於把失敗外包給運氣。",
            dimension="risk",
        )
    if (
        7 in sess.asked_ids
        and 10 not in sess.asked_ids
        and answers
        and (_FALLBACK.search(last) or _RISK.search(last) or _REVIEW_GATE.search(last) or _QUANT.search(last))
    ):
        sess.phase = 4
        sess.phase_rounds = 0
        sess.asked_ids.append(10)
        return GrillQuestion(
            _synthesize_fan_lock(sess),
            why="複誦才能暴露殘餘歧義。",
            dimension="success",
        )
    return None


def _is_over_auth(text: str) -> bool:
    stripped = (text or "").strip()
    if stripped in {"直接執行", "直接执行", "結束", "结束", "夠了", "够了", "锁定", "鎖定"}:
        return True
    return bool(_OVER_AUTH_PHRASE.search(stripped))


def _is_contradiction(text: str) -> bool:
    return bool(_UNLIMITED_BUDGET.search(text) and _FREE_OSS.search(text))


def _next_question(sess: UserGrillSession) -> GrillQuestion:
    asked = set(sess.asked_ids)
    phase = int(sess.phase or 1)
    for item in QUESTION_BANK:
        if item["phase"] == phase and item["id"] not in asked:
            sess.asked_ids.append(item["id"])
            return GrillQuestion(item["question"], why=item["why"], dimension=item["dimension"])
    for item in QUESTION_BANK:
        if item["id"] not in asked:
            sess.phase = int(item["phase"])
            sess.phase_rounds = 0
            sess.asked_ids.append(item["id"])
            return GrillQuestion(item["question"], why=item["why"], dimension=item["dimension"])
    item = QUESTION_BANK[9]  # Phase 4 複誦
    return GrillQuestion(item["question"], why=item["why"], dimension=item["dimension"])


def _llm_question(query: str, transcript: str, gaps: list[str], phase: int) -> GrillQuestion | None:
    try:
        from backend.core.llm import call_llm, parse_json_response

        prompt = (
            f"目前階段：{PHASE_LABELS.get(phase, phase)}\n"
            f"【任務】{query}\n"
            f"【未達標維度】{', '.join(gaps) or '語意仍不夠鎖定'}\n"
            f"【對話】\n{transcript or '（尚無）'}\n\n"
            "一次只問一個具體、可證偽的問題。禁止說『明白了』。"
            "若用戶回答含『大概／盡量／好一點』，要求量化。"
            "只輸出 JSON：{\"question\":\"...\",\"why\":\"...\",\"dimension\":\"specificity|boundary|constraints|risk|success\"}"
        )
        raw = call_llm(prompt, system=SYSTEM_PROMPT)
        parsed = extract_json(raw)
        if parsed:
            return None
        data = parse_json_response(raw) or {}
        question = str(data.get("question") or "").strip()
        if not question:
            return None
        return GrillQuestion(
            question,
            why=str(data.get("why") or ""),
            dimension=str(data.get("dimension") or "specificity"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("需求審計官 LLM 降級為題庫：%s", exc)
        return None


def _transcript(sess: UserGrillSession) -> str:
    lines = []
    for turn in sess.turns:
        tag = "用戶" if turn.get("role") == "user" else "審計官"
        lines.append(f"【{tag}】{turn.get('content', '')}")
    return "\n".join(lines)


def _user_answers(sess: UserGrillSession) -> list[str]:
    return [str(t.get("content") or "") for t in sess.turns if t.get("role") == "user"]


def _audit_trail(sess: UserGrillSession) -> list[str]:
    trail: list[str] = []
    last_q = ""
    for turn in sess.turns:
        if turn.get("role") == "assistant":
            last_q = str(turn.get("content") or "")
        elif turn.get("role") == "user" and last_q:
            trail.append(f"Q: {last_q} A: {turn.get('content', '')}")
            last_q = ""
    return trail[:16]


def _extract_field(pattern: str, text: str, default: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return default
    if match.lastindex:
        return match.group(1).strip()[:180]
    return match.group(0).strip()[:180]


def build_ticket(sess: UserGrillSession) -> dict[str, Any]:
    """組裝進入 Planner 的戰術指令 JSON。"""
    text = _joined(sess.query, _user_answers(sess))
    scores = sess.scores or score_dimensions(sess.query, _user_answers(sess))
    confidence = round(min(float(scores[k]) for k in DIM_KEYS), 1)
    hours = re.search(
        r"(?:目前|現需|现需)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(小時|小时|分鐘|分钟).{0,40}?"
        r"(?:目標|目标|壓縮|压缩)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(小時|小时|分鐘|分钟)",
        text,
    )
    acc = re.search(r"(準確率|准确率|誤報率|误报率)[^\d]{0,6}(\d+(?:\.\d+)?)\s*%", text)
    rates = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    unit_cost = re.search(r"(\d+(?:\.\d+)?)\s*(元|塊|块)", text)
    if hours:
        quantified = (
            f"目前每日人工 {hours.group(1)}{hours.group(2)}，"
            f"目標壓縮至 {hours.group(3)}{hours.group(4)}"
        )
        if acc:
            quantified += f"，{acc.group(1)} {acc.group(2)}%"
    elif _is_fan_scenario(sess.query) and len(rates) >= 2:
        quantified = f"目前復購率 {rates[0]}%，目標提升至 {rates[-1]}%"
        if unit_cost:
            quantified += f"，單粉行銷成本 {unit_cost.group(1)} 元"
        if _has_review_gate(text):
            quantified += "，關鍵推播需經人工審核"
    else:
        quantified = _extract_field(
            r"(.{0,40}\d+(?:\.\d+)?\s*(?:小時|小时|%|％).{0,40})",
            text,
            "需以對話中的量化指標作為驗收標準",
        )
    budget = _extract_field(
        r"((?:預算|预算)[^。\n]{0,40}\d+[^。\n]{0,20})",
        text,
        "未明示預算區間",
    )
    if budget == "未明示預算區間" and unit_cost:
        budget = f"單粉行銷成本 {unit_cost.group(1)} 元"
    deadline = _extract_field(r"(\d{4}-\d{2}-\d{2})", text, "未明示截止日期")
    exclusions = [m.group(0) for m in re.finditer(r"(不(?:做|使用|開發|开发|包含)[^，。,\n]{2,30})", text)]
    if _is_fan_scenario(sess.query) and _has_review_gate(text):
        gate = "不自動推播（關鍵內容需人工審核）"
        if gate not in exclusions:
            exclusions.append(gate)
    techs = []
    for name in ("Python", "PostgreSQL", "Line Notify", "Excel", "API"):
        if re.search(name, text, re.IGNORECASE):
            techs.append(name)
    risks = []
    if _is_fan_scenario(sess.query) and _has_review_gate(text):
        risks.append("老粉退粉（備案：關鍵推播改為人工審核）")
    if _RISK.search(text) or _FALLBACK.search(text):
        risks.append(_extract_field(r"(.{0,20}(?:備案|备案|人工確認|人工确认|CSV|人工審核|人工审核)[^。\n]{0,40})", text, "已標示備案"))
    if not risks:
        risks.append("用戶已承認主要失敗模式並提供備案")
    priority = "Cost > Time > Quality (在預算內，稍微延後可接受)"
    if re.search(r"(延後|延后).{0,8}(可接受|其次)", text):
        priority = "Cost > Time > Quality (在預算內，稍微延後可接受)"
    elif re.search(r"(時程|时程|上線|上线).{0,12}(不可|不能|優先|优先)", text):
        priority = "Time > Cost > Quality"
    ticket = {
        "status": "APPROVED_FOR_PLANNING",
        "confidence_score": confidence,
        "clarified_goal": {
            "target_audience": _extract_field(
                r"((?:用戶|用户|客群|賣家|卖家|粉絲|粉丝|終端|终端)[^。\n]{0,40})",
                text,
                "內容創作者的粉絲（終端用戶）" if _is_fan_scenario(sess.query) else sess.query[:80],
            ),
            "core_action": _extract_field(
                r"((?:自動|自动|生成|預警|预警|調價|调价|壓縮|压缩)[^。\n]{0,50})",
                text,
                "以人工審核把關的自動粉絲經營與復購提升"
                if _is_fan_scenario(sess.query)
                else sess.query[:120],
            ),
            "quantified_success": quantified,
        },
        "hard_constraints": {
            "deadline": deadline,
            "budget_range": budget,
            "must_use_tech": techs or ["依現有技術棧"],
            "absolute_exclusions": exclusions[:6],
        },
        "risk_register": {
            "identified_risks": risks[:6],
            "user_priority": priority,
        },
        "audit_trail": _audit_trail(sess),
        "dimension_scores": dict(scores),
    }
    return ticket


def format_locked_brief(sess: UserGrillSession, ticket: dict[str, Any]) -> str:
    goal = ticket.get("clarified_goal") or {}
    constraints = ticket.get("hard_constraints") or {}
    risks = ticket.get("risk_register") or {}
    parts = [
        "【需求審計官戰術指令｜APPROVED_FOR_PLANNING】",
        f"目標受眾：{goal.get('target_audience', '')}",
        f"核心行動：{goal.get('core_action', '')}",
        f"量化成功：{goal.get('quantified_success', '')}",
        f"截止：{constraints.get('deadline', '')}",
        f"預算：{constraints.get('budget_range', '')}",
        f"必須使用：{', '.join(constraints.get('must_use_tech') or [])}",
        f"絕對不做：{', '.join(constraints.get('absolute_exclusions') or [])}",
        f"風險備案：{'; '.join(risks.get('identified_risks') or [])}",
        f"取捨順序：{risks.get('user_priority', '')}",
        f"置信度：{ticket.get('confidence_score')}",
        "【原始需求】" + sess.query,
        "```json\n" + json.dumps(ticket, ensure_ascii=False, indent=2) + "\n```",
    ]
    return "\n".join(parts)


def _phase_gate(phase: int, scores: dict[str, float]) -> bool:
    if phase <= 1:
        return float(scores.get("specificity", 0)) >= 70
    if phase == 2:
        return float(scores.get("constraints", 0)) >= 70 and float(scores.get("success", 0)) >= 70
    if phase == 3:
        return float(scores.get("risk", 0)) >= 70 and float(scores.get("boundary", 0)) >= 60
    return all_dims_locked(scores)


def _infer_phase(scores: dict[str, float]) -> int:
    if float(scores.get("specificity", 0)) < 70:
        return 1
    if float(scores.get("constraints", 0)) < 70 or float(scores.get("success", 0)) < 70:
        return 2
    if float(scores.get("risk", 0)) < 70 or float(scores.get("boundary", 0)) < 60:
        return 3
    return 4


def _append_assistant(sess: UserGrillSession, question: GrillQuestion) -> None:
    sess.turns.append(
        {
            "role": "assistant",
            "content": question.question,
            "dimension": question.dimension,
            "why": question.why,
            "phase": str(sess.phase),
        }
    )


def _trace_l4_question(sess: UserGrillSession, question: GrillQuestion) -> None:
    STORE.record_user_grill(
        sess.session_id,
        sess.query,
        summary=(question.question or "")[:240],
        status="open",
        from_layer=int(RahoLayer.L4_PLANNER),
        to_layer=int(RahoLayer.L5_USER),
        payload={"phase": sess.phase, "dimension": question.dimension},
    )


def _trace_l5_answer(sess: UserGrillSession, text: str) -> None:
    STORE.resolve_user_grill(sess.session_id)
    STORE.record_user_grill(
        sess.session_id,
        sess.query,
        summary=(text or "")[:240],
        status="resolved",
        from_layer=int(RahoLayer.L5_USER),
        to_layer=int(RahoLayer.L4_PLANNER),
    )


def _trace_close(sess: UserGrillSession, summary: str, status: str) -> None:
    STORE.resolve_user_grill(sess.session_id, "resolved" if status == "resolved" else status)
    STORE.record_user_grill(
        sess.session_id,
        sess.query,
        summary=summary[:240],
        status=status,
        from_layer=int(RahoLayer.L4_PLANNER),
        to_layer=int(RahoLayer.L5_USER),
        payload={"locked": sess.locked, "terminated": sess.terminated},
    )


def _failure_report(sess: UserGrillSession, reason: str) -> str:
    scores = sess.scores or {}
    lines = [
        "需求審計失敗報告",
        f"原因：{reason}",
        "禁止進入 Planner 階段。",
        "五維評分：",
    ]
    for key in DIM_KEYS:
        lines.append(f"- {DIM_LABELS[key]}：{scores.get(key, 0)}")
    return "\n".join(lines)


def _pack(
    sess: UserGrillSession,
    question: GrillQuestion | None,
    *,
    closed: bool = False,
    terminated: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    overall = 0.0
    if sess.scores:
        overall = min(float(sess.scores.get(k, 0)) for k in DIM_KEYS) / 100.0
    sess.confidence = overall
    lock = SemanticLock(
        locked=sess.locked,
        confidence=sess.confidence,
        brief=sess.brief,
        session_id=sess.session_id,
        turns=sum(1 for t in sess.turns if t.get("role") == "user"),
        gaps=[k for k, v in (sess.scores or {}).items() if float(v) <= AUDITOR_DIM_THRESHOLD],
    )
    payload = lock.to_dict()
    status = "AUDITING"
    if terminated:
        status = "FAILED"
    elif sess.locked:
        status = "APPROVED_FOR_PLANNING"
    payload.update(
        {
            "should_grill": (not sess.locked) and (not terminated) and user_grill_enabled(),
            "question": question.to_dict() if question else None,
            "closed": closed or terminated or sess.locked,
            "max_turns": MAX_AUDITOR_ROUNDS,
            "phase": sess.phase,
            "phase_label": PHASE_LABELS.get(int(sess.phase or 1), ""),
            "phase_rounds": sess.phase_rounds,
            "scores": dict(sess.scores or {}),
            "ticket": sess.ticket,
            "planner": sess.planner,
            "terminated": terminated,
            "termination_reason": reason,
            "termination_report": _failure_report(sess, reason) if terminated else "",
            "status": status,
            "role": "requirement_auditor",
            "role_label": LAYER_LABELS.get(int(RahoLayer.L4_AUDITOR), "L4 需求審計官"),
            "user_rounds": sess.user_rounds,
        }
    )
    return payload


def _terminate(sess: UserGrillSession, reason: str) -> dict[str, Any]:
    sess.terminated = True
    sess.termination_reason = reason
    report = _failure_report(sess, reason)
    sess.turns.append({"role": "assistant", "content": report, "dimension": "terminate", "why": reason})
    question = GrillQuestion(report, why=reason, dimension="terminate")
    _trace_close(sess, reason or "需求審計失敗", "blocked")
    return _pack(sess, question, closed=True, terminated=True, reason=reason)


def trigger_planner(final_plan: dict[str, Any]) -> dict[str, Any]:
    """五維達標後自動觸發 Dynamic Planner（L4 戰役 DAG + L3 原子拆解）。"""
    ticket = dict(final_plan or {})
    if ticket.get("status") != "APPROVED_FOR_PLANNING":
        return {"status": "REJECTED", "reason": "缺少 status=APPROVED_FOR_PLANNING 的門票"}
    try:
        score = float(ticket.get("confidence_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score < AUDITOR_DIM_THRESHOLD:
        return {"status": "REJECTED", "reason": f"confidence_score {score} < {AUDITOR_DIM_THRESHOLD}"}

    goal = ""
    clarified = ticket.get("clarified_goal") or {}
    if isinstance(clarified, dict):
        goal = str(clarified.get("core_action") or clarified.get("quantified_success") or "").strip()
    if not goal:
        goal = str(ticket.get("clarified_goal") or "")[:240]

    try:
        from backend.company.raho.planner import plan_campaign

        campaign = plan_campaign(goal or "已鎖定需求")
        campaign_data = campaign.to_dict() if hasattr(campaign, "to_dict") else campaign
    except Exception as exc:  # noqa: BLE001
        logger.warning("L4 戰役規劃失敗，仍保留門票：%s", exc)
        campaign_data = {"status": "PLANNER_DEFERRED", "error": str(exc)}

    try:
        from backend.company.raho.commander import command_from_ticket

        commander = command_from_ticket(ticket, use_llm=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("L3 戰術拆解失敗，仍保留門票：%s", exc)
        commander = {"status": "COMMANDER_DEFERRED", "error": str(exc)}

    return {
        "status": "PLANNER_TRIGGERED",
        "ticket": ticket,
        "campaign": campaign_data,
        "commander": commander,
    }


def _approve(sess: UserGrillSession) -> dict[str, Any]:
    ticket = build_ticket(sess)
    sess.ticket = ticket
    sess.locked = True
    sess.brief = format_locked_brief(sess, ticket)
    sess.confidence = min(float(sess.scores.get(k, 0)) for k in DIM_KEYS) / 100.0
    try:
        sess.planner = trigger_planner(ticket)
    except Exception as exc:  # noqa: BLE001
        logger.warning("自動觸發 Planner 失敗：%s", exc)
        sess.planner = {"status": "PLANNER_DEFERRED", "error": str(exc)}
    _trace_close(sess, "五維達標，門票已核發", "resolved")
    return _pack(sess, None, closed=True)


def _ask_next(sess: UserGrillSession, *, prefix: str = "") -> dict[str, Any]:
    gaps = [k for k, v in (sess.scores or {}).items() if float(v) <= AUDITOR_DIM_THRESHOLD]
    phase = int(sess.phase or 1)
    if not sess.user_rounds and not prefix:
        contextual = _contextual_first_question(sess.query)
        if contextual:
            if 1 not in sess.asked_ids:
                sess.asked_ids.append(1)
            text = _with_phase_tag(contextual.question, phase)
            question = GrillQuestion(text, why=contextual.why, dimension=contextual.dimension)
            sess.phase_rounds = int(sess.phase_rounds or 0) + 1
            _append_assistant(sess, question)
            _trace_l4_question(sess, question)
            return _pack(sess, question)
    scenario = _scenario_next(sess)
    if scenario is not None:
        phase = int(sess.phase or 1)
        text = scenario.question
        if prefix and prefix.rstrip("：:") not in text:
            text = f"{prefix}{text}" if not text.startswith("量化失敗") else text
        text = _with_phase_tag(text, phase)
        question = GrillQuestion(text, why=scenario.why, dimension=scenario.dimension)
        sess.phase_rounds = int(sess.phase_rounds or 0) + 1
        _append_assistant(sess, question)
        _trace_l4_question(sess, question)
        return _pack(sess, question)
    question = _llm_question(sess.query, _transcript(sess), gaps, phase)
    if question is None:
        question = _next_question(sess)
    elif not sess.asked_ids:
        sess.asked_ids.append(0)
    text = f"{prefix}{question.question}" if prefix else question.question
    if not sess.asked_ids or (len(sess.asked_ids) == 1 and not sess.user_rounds):
        hook = _opening_hook(sess.query)
        if hook and hook not in text:
            text = f"{hook}{text}"
    text = _with_phase_tag(text, phase)
    question = GrillQuestion(text, why=question.why, dimension=question.dimension)
    sess.phase_rounds = int(sess.phase_rounds or 0) + 1
    _append_assistant(sess, question)
    _trace_l4_question(sess, question)
    return _pack(sess, question)


def auditor_start(query: str) -> dict[str, Any]:
    """開一場需求審計。第一次絕不放行。"""
    text = (query or "").strip()
    if not text:
        raise ValueError("query 不可為空")
    sess = STORE.new_user_session(text)
    sess.phase = 1
    sess.phase_rounds = 0
    sess.scores = score_dimensions(text, [])
    sess.confidence = min(sess.scores.values()) / 100.0
    return _ask_next(sess)


def auditor_turn(session_id: str, answer: str, *, force_lock: bool = False) -> dict[str, Any]:
    sess = STORE.get_user_session(session_id)
    if sess is None:
        raise KeyError(f"審計會話不存在或已過期：{session_id}")
    if sess.terminated:
        return _pack(sess, None, closed=True, terminated=True, reason=sess.termination_reason)
    if sess.locked:
        return _pack(sess, None, closed=True)

    text = (answer or "").strip()
    if not text:
        raise ValueError("answer 不可為空")

    if force_lock or _is_over_auth(text):
        _trace_l5_answer(sess, text)
        return _terminate(sess, OVER_AUTH_REPLY)

    joined_so_far = _joined(sess.query, _user_answers(sess) + [text])
    if _is_contradiction(joined_so_far) or _is_contradiction(text):
        _trace_l5_answer(sess, text)
        return _terminate(sess, "明顯矛盾：預算無限卻要求開源免費方案。需求不可行。")

    if sess.last_user_text and sess.last_user_text == text:
        sess.repeat_count = int(sess.repeat_count or 0) + 1
        if sess.repeat_count >= 1:
            _trace_l5_answer(sess, text)
            return _terminate(sess, "重複跳針：連續 2 輪重複相同句子並拒絕量化。")
    else:
        sess.repeat_count = 0
        sess.last_user_text = text

    sess.turns.append({"role": "user", "content": text})
    sess.user_rounds = int(sess.user_rounds or 0) + 1
    _trace_l5_answer(sess, text)
    answers = _user_answers(sess)
    sess.scores = score_dimensions(sess.query, answers)

    if sess.user_rounds >= MAX_AUDITOR_ROUNDS:
        if all_dims_locked(sess.scores) and (_CONFIRM.search(text) or len(text) <= 50):
            return _approve(sess)
        return _terminate(sess, f"超過 {MAX_AUDITOR_ROUNDS} 輪仍未達五維 > 90，強制終止。")

    if _fan_contract_ready(sess) and (
        _CONFIRM.search(text) or (int(sess.phase or 1) >= 4 and len(text) <= 50)
    ):
        sess.scores = {key: max(float(sess.scores.get(key, 0)), 91.0) for key in DIM_KEYS}
        return _approve(sess)

    if _is_unquantified(text, int(sess.phase or 1)):
        if int(sess.phase_rounds or 0) >= MAX_PHASE_ROUNDS:
            return _terminate(sess, f"{PHASE_LABELS.get(sess.phase)} 連續 {MAX_PHASE_ROUNDS} 輪仍在繞圈子（含無效模糊回答）。")
        return _ask_next(sess, prefix=_vague_prefix(int(sess.phase or 1)))

    target_phase = _infer_phase(sess.scores)
    if all_dims_locked(sess.scores):
        target_phase = 4
        if int(sess.phase or 1) == 4 and (_CONFIRM.search(text) or "合約" in text or "承擔" in text):
            return _approve(sess)
        if int(sess.phase or 1) == 4 and int(sess.phase_rounds or 0) >= 1 and len(text) <= 50:
            return _approve(sess)

    if target_phase > int(sess.phase or 1) and _phase_gate(int(sess.phase or 1), sess.scores):
        sess.phase = target_phase
        sess.phase_rounds = 0
    elif target_phase < int(sess.phase or 1):
        # 不後退；缺的維度用當前階段題庫補
        pass
    else:
        if int(sess.phase_rounds or 0) >= MAX_PHASE_ROUNDS and not _phase_gate(int(sess.phase or 1), sess.scores):
            return _terminate(
                sess,
                f"{PHASE_LABELS.get(sess.phase)} 已追問 {MAX_PHASE_ROUNDS} 輪仍不完整，觸發終止協議。",
            )

    if all_dims_locked(sess.scores) and int(sess.phase or 1) >= 4 and _CONFIRM.search(text):
        return _approve(sess)

    return _ask_next(sess)


def auditor_lock(session_id: str, note: str = "") -> dict[str, Any]:
    """前端『直接執行』視同過度授權，不得繞過五維門檻。"""
    sess = STORE.get_user_session(session_id)
    if sess is None:
        raise KeyError(f"審計會話不存在或已過期：{session_id}")
    text = (note or "").strip() or "你看著辦吧"
    return auditor_turn(session_id, text, force_lock=True)


def auditor_status() -> dict[str, Any]:
    return {
        "enabled": user_grill_enabled(),
        "lock_threshold": CONFIDENCE_THRESHOLD,
        "dim_threshold": AUDITOR_DIM_THRESHOLD,
        "max_rounds": MAX_AUDITOR_ROUNDS,
        "max_phase_rounds": MAX_PHASE_ROUNDS,
        "active_sessions": len(STORE.user_sessions),
        "role": "requirement_auditor",
    }


class RequirementAuditor:
    """強制前置閘門。會話由 RAHO STORE 持有，供 HTTP／SSE／產生器多輪餵入。"""

    def __init__(self) -> None:
        self.system_prompt = SYSTEM_PROMPT
        self.max_rounds = MAX_AUDITOR_ROUNDS
        self.confidence_threshold = CONFIDENCE_THRESHOLD

    def start(self, initial_input: str) -> dict[str, Any]:
        return auditor_start(initial_input)

    def turn(self, session_id: str, user_reply: str) -> dict[str, Any]:
        return auditor_turn(session_id, user_reply)

    def extract_json(self, response: str) -> dict[str, Any] | None:
        return extract_json(response)

    def trigger_planner(self, final_plan: dict[str, Any]) -> dict[str, Any]:
        return trigger_planner(final_plan)

    def force_termination(self, session_id: str, reason: str = "") -> dict[str, Any]:
        sess = STORE.get_user_session(session_id)
        if sess is None:
            raise KeyError(f"審計會話不存在或已過期：{session_id}")
        return _terminate(sess, reason or f"超過 {self.max_rounds} 輪仍未達標")

    def process_user_request(self, initial_input: str):
        """強制前置閘門產生器（規格第 5 節）。

        用法::
            gen = auditor.process_user_request(query)
            payload = next(gen)          # 第一問
            payload = gen.send(reply)    # 後續輪
            # 終態以 return 結束：APPROVED_FOR_PLANNING 或 FAILED
        """
        result = auditor_start(initial_input)
        if result.get("status") in {"APPROVED_FOR_PLANNING", "FAILED"}:
            return result
        user_reply = yield result
        session_id = str(result.get("session_id") or "")
        rounds = 0
        while rounds < self.max_rounds:
            if user_reply is None:
                user_reply = yield result
                continue
            result = auditor_turn(session_id, str(user_reply))
            session_id = str(result.get("session_id") or session_id)
            if result.get("status") in {"APPROVED_FOR_PLANNING", "FAILED"}:
                return result
            user_reply = yield result
            rounds += 1
        if session_id:
            return self.force_termination(session_id)
        return result
