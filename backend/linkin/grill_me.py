"""grill-me：嚴刑拷打模式（本地定制模組，上游無此檔案）。

魔鬼代言人 + 嚴格審查員：對使用者的計畫/決策/策略參數進行壓力測試。
單發提問、追打模糊回答、維度輪替、最終輸出 GO / GO-WITH-CONDITIONS / NO-GO 裁決。

經 backend.core.llm.call_llm 呼叫（AGENTS.md #1）；無金鑰/失敗時拋錯由 API 層轉 HTTP。
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from backend.core.llm import call_llm

logger = logging.getLogger(__name__)

GRILL_SYSTEM = (
    "你是「嚴刑拷打審查員」（grill-me）：魔鬼代言人，目標不是否定使用者，"
    "而是在他付出代價之前把計畫逼想清楚。"
    "規則：一次只問一個問題；問題必須具體、可證偽、有殺傷力（附一行『為什麼重要』）；"
    "追打模糊回答（『應該沒問題』→ 要數字或事實）；"
    "拷問維度輪替：假設、失敗模式、數字、機會成本、執行、反方；"
    "使用者說『結束/夠了/總結』時輸出總結："
    "🟢已想清楚 / 🟡回答薄弱（附原問題）/ 🔴未回答或迴避，"
    "最終裁決 GO / GO-WITH-CONDITIONS（列條件）/ NO-GO（列原因）。"
    "語氣直接犀利、對事不對人；計畫經得起打就明說『這個回答過關』再打下一面；"
    "以使用者的語言（繁體中文為主）回應。"
)

# 記憶體中的拷問會話（重啟即清空；刻意不落盤，避免敏感計畫殘留）
_SESSIONS: dict[str, list[dict[str, str]]] = {}
_MAX_SESSIONS = 50
_MAX_TURNS = 40  # 每會話保留的訊息數上限


def _resolve_model(question: str) -> str:
    model = os.getenv("EVOL_GRILL_MODEL", "").strip()
    if not model:
        from backend.core.stage_router import resolve_stage_model

        model = resolve_stage_model("generate", query=question)
    return model


def grill_start(topic: str) -> dict[str, Any]:
    """開一場新的拷問會話，回傳 session_id 與第一發問題。"""
    text = (topic or "").strip()
    if not text:
        raise ValueError("topic 不可為空：請提供要拷問的計畫/決策/想法")
    if len(_SESSIONS) >= _MAX_SESSIONS:
        # 淘汰最舊會話
        oldest = next(iter(_SESSIONS))
        _SESSIONS.pop(oldest, None)
    session_id = uuid.uuid4().hex[:12]
    prompt = f"【要拷問的對象】\n{text}\n\n請開始第一發拷問（單一問題 + 一行為什麼重要）。"
    reply = call_llm(prompt, system=GRILL_SYSTEM, model=_resolve_model(text))
    _SESSIONS[session_id] = [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": reply},
    ]
    return {"session_id": session_id, "reply": reply, "turns": 1}


def grill_turn(session_id: str, answer: str) -> dict[str, Any]:
    """繼續拷問：使用者回答上一發問題，LLM 追打或換維度。"""
    sid = (session_id or "").strip()
    text = (answer or "").strip()
    if sid not in _SESSIONS:
        raise KeyError(f"會話不存在或已過期：{sid}（請重新 grill_start）")
    if not text:
        raise ValueError("answer 不可為空")
    history = _SESSIONS[sid]
    # 組裝對話上下文（call_llm 單 prompt 介面 → 拼接對話紀錄）
    transcript = "\n\n".join(
        f"{'【使用者】' if m['role'] == 'user' else '【審查員】'}{m['content']}" for m in history
    )
    prompt = f"{transcript}\n\n【使用者】{text}\n\n【審查員】請繼續（追打模糊處，或輪替到下一個拷問維度；若使用者要求總結則輸出總結與裁決）。"
    reply = call_llm(prompt, system=GRILL_SYSTEM, model=_resolve_model(text))
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    if len(history) > _MAX_TURNS:
        del history[: len(history) - _MAX_TURNS]
    return {"session_id": sid, "reply": reply, "turns": len(history) // 2}


def grill_summary(session_id: str) -> dict[str, Any]:
    """強制收尾：輸出 🟢🟡🔴 總結與 GO/NO-GO 裁決。"""
    sid = (session_id or "").strip()
    if sid not in _SESSIONS:
        raise KeyError(f"會話不存在或已過期：{sid}")
    history = _SESSIONS[sid]
    transcript = "\n\n".join(
        f"{'【使用者】' if m['role'] == 'user' else '【審查員】'}{m['content']}" for m in history
    )
    prompt = f"{transcript}\n\n【使用者】結束，請總結。\n\n【審查員】"
    reply = call_llm(prompt, system=GRILL_SYSTEM, model=_resolve_model("總結"))
    _SESSIONS.pop(sid, None)
    return {"session_id": sid, "reply": reply, "closed": True}


def grill_status() -> dict[str, Any]:
    return {"active_sessions": len(_SESSIONS), "max_sessions": _MAX_SESSIONS}
