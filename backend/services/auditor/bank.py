"""Requirement Auditor 的題庫、選項表與制式問題資料（自 backend.services.auditor 抽出）。"""

from __future__ import annotations

from typing import Any

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

_CHOICE_VAGUE = {"key": "vague", "label": "大概／盡量做好一點就好"}

_CHOICES_BY_DIMENSION: dict[str, list[dict[str, str]]] = {
    "specificity": [
        {
            "key": "before_after",
            "label": "終端用戶是月營收 >50 萬賣家；介入前每天人工盯盤 4 小時、月損 8 萬，介入後自動競品預警",
        },
        {
            "key": "pain_quant",
            "label": "現狀每月浪費 120 小時、損失約 8 萬；不做此任務 90 天后損失升到 12 萬",
        },
        {
            "key": "stakeholder",
            "label": "發起人是終端賣家本人（非老闆拍腦袋）；驗收以日省 3 小時盯盤為準",
        },
        _CHOICE_VAGUE,
    ],
    "success": [
        {
            "key": "xyz",
            "label": "目前需 4 小時，目標壓縮至 0.5 小時，準確率不得低於 95%，誤報率 <5%",
        },
        {
            "key": "deliverable",
            "label": "交付可點擊 Prototype + 每日 Excel 預警報表",
        },
        {
            "key": "lock_confirm",
            "label": "成功是把盯盤從 4 小時壓到 30 分鐘、誤報 <5%；我承擔後果",
        },
        _CHOICE_VAGUE,
    ],
    "constraints": [
        {
            "key": "scope_first",
            "label": "超支 30% 優先砍功能，其次延後上線，不借貸",
        },
        {
            "key": "team_stack",
            "label": "2 人 × 每天 4 小時 × 6 週；沿用 Python 3.10、PostgreSQL、Line Notify",
        },
        {
            "key": "budget_deadline",
            "label": "預算 15~20 萬新台幣，截止 2026-10-15，不可超支借貸",
        },
        _CHOICE_VAGUE,
    ],
    "risk": [
        {
            "key": "api_fallback",
            "label": "API 斷線時改用手動 CSV 上傳；誤報率 >5% 自動停用推播",
        },
        {
            "key": "human_gate",
            "label": "AI 與直覺衝突時以人工確認按鈕為準，系統不可自動調價",
        },
        {
            "key": "stop_loss",
            "label": "上線第一週 KPI 不升反降 >10% 時，產品負責人可按下停止",
        },
        _CHOICE_VAGUE,
    ],
    "boundary": [
        {
            "key": "sacrifice_20",
            "label": "80% 先做預警與建議，犧牲自動調價這 20%",
        },
        {
            "key": "veto_list",
            "label": "否決項：誤報導致錯殺價格、未經人工確認自動調價、資料外洩",
        },
        {
            "key": "exclusions",
            "label": "不做手機 APP、不使用爬蟲，只用官方 API",
        },
        _CHOICE_VAGUE,
    ],
}

_CHOICES_BY_QUESTION_ID: dict[int, list[dict[str, str]]] = {
    5: [
        {"key": "scope", "label": "超支 30% 優先砍功能，其次延後，不借貸"},
        {"key": "time", "label": "超支 30% 優先延後上線，其次砍功能"},
        {"key": "cost", "label": "超支 30% 允許借貸補足（最後手段）"},
        _CHOICE_VAGUE,
    ],
    6: [
        {"key": "prototype", "label": "可點擊 Prototype + 操作說明"},
        {"key": "excel", "label": "每日 Excel 預警報表（可下載）"},
        {"key": "memo", "label": "純文字備忘錄（僅在無法做互動原型時）"},
        _CHOICE_VAGUE,
    ],
    7: [
        {"key": "csv", "label": "API 斷線改用手動 CSV 上傳，24 小內恢復"},
        {"key": "cache", "label": "使用昨日快取 + 人工補數，標記高風險"},
        {"key": "pause", "label": "暫停自動推播，全轉人工審核"},
        _CHOICE_VAGUE,
    ],
    8: [
        {"key": "human", "label": "AI 與直覺衝突時以人工確認為準"},
        {"key": "ai", "label": "AI 建議為主，人工僅事後抽查"},
        {"key": "hybrid", "label": "低風險自動、高風險（調價）必須人工"},
        _CHOICE_VAGUE,
    ],
    10: [
        {"key": "succinct", "label": "把盯盤從 4 小時壓到 30 分鐘、誤報 <5%，預算 15 萬且調價需人工"},
        {"key": "fan", "label": "復購率從 12% 提升到 18%，單粉成本 ≤3 元，關鍵推播人工審核"},
        _CHOICE_VAGUE,
    ],
    11: [
        {"key": "confirm", "label": "確認。後果由我承擔，以上作為最終合約依據"},
        {"key": "revise", "label": "需再修訂一項：成功定義仍以數字驗收為準"},
        _CHOICE_VAGUE,
    ],
    16: [
        {"key": "lock", "label": "確認鎖定"},
        {"key": "hold", "label": "暫不鎖定，需補一項量化指標"},
    ],
}

_FAN_PHASE3_CHOICES = [
    {"key": "manual", "label": "改為人工審核後再推播"},
    {"key": "auto_stop", "label": "5 個老粉退粉即自動停止推播"},
    {"key": "threshold", "label": "退粉率 >2% 當日停止，次日人工復核"},
    _CHOICE_VAGUE,
]


FAN_PHASE2_QUESTION = (
    "量化失敗。請填入數字：\n\n"
    "① 目前的「復購率（回購人數 / 總人數）」是 ___ %，目標提升到 ___ %？\n\n"
    "② 你願意為每個新粉絲投入多少新台幣的行銷成本？"
)
FAN_PHASE3_QUESTION = (
    "進行壓力測試：如果系統推薦的內容導致 5 個老粉退粉，"
    "你希望系統自動停止推播，還是改為人工審核？請選擇。"
)
