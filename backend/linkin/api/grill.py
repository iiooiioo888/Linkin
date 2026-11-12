"""靈境 REST：grill-me 嚴刑拷打模式端點。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .router import linkin_router
from .shared import logger

# ── grill-me 嚴刑拷打模式（本地定制，上游無此區塊）──


@linkin_router.post("/grill/start")
def grill_start(body: dict[str, Any]) -> dict[str, Any]:
    """開一場拷問會話：body={"topic": "<計畫/決策/想法>"}。"""
    from backend.linkin import grill_me

    topic = str((body or {}).get("topic") or (body or {}).get("question") or "").strip()
    try:
        return {"status": "ok", **grill_me.grill_start(topic)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    except Exception as exc:
        logger.warning("grill_me 啟動失敗：%s", exc)
        raise HTTPException(
            status_code=503, detail={"message": f"grill-me 不可用（LLM 未配置或呼叫失敗）：{exc}"}
        ) from exc


@linkin_router.post("/grill/turn")
def grill_turn(body: dict[str, Any]) -> dict[str, Any]:
    """繼續拷問：body={"session_id": "...", "answer": "<使用者回答>"}。"""
    from backend.linkin import grill_me

    session_id = str((body or {}).get("session_id") or "").strip()
    answer = str((body or {}).get("answer") or "").strip()
    try:
        return {"status": "ok", **grill_me.grill_turn(session_id, answer)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    except Exception as exc:
        logger.warning("grill_me 回合失敗：%s", exc)
        raise HTTPException(status_code=503, detail={"message": f"grill-me 不可用：{exc}"}) from exc


@linkin_router.post("/grill/summary")
def grill_summary(body: dict[str, Any]) -> dict[str, Any]:
    """強制收尾：body={"session_id": "..."} → 🟢🟡🔴 總結 + GO/NO-GO 裁決。"""
    from backend.linkin import grill_me

    session_id = str((body or {}).get("session_id") or "").strip()
    try:
        return {"status": "ok", **grill_me.grill_summary(session_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except Exception as exc:
        logger.warning("grill_me 總結失敗：%s", exc)
        raise HTTPException(status_code=503, detail={"message": f"grill-me 不可用：{exc}"}) from exc


@linkin_router.get("/grill/status")
def grill_status() -> dict[str, Any]:
    from backend.linkin import grill_me

    return grill_me.grill_status()
