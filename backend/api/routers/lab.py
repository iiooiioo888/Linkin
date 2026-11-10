"""實驗室整合 API：Firecrawl／Prompt Optimizer／Ponytail／Archify／量化策略視覺化。

自 backend.main 抽出；端點行為、模型與回應結構不變。
"""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from backend.billing.context import current_billing_user
from backend.billing.metering import meter_quant_call, require_feature
from backend.billing.plans import PACK_QUANT
from backend.company.archify_compile import render_ir, render_view
from backend.company.quant_capital_flow_maps import strategy_capital_flow
from backend.company.quant_strategy_catalog import market_strategy_catalog
from backend.company.quant_strategy_maps import (
    strategy_catalog_maps,
    strategy_maps,
    strategy_preview,
)
from backend.company.system_flow_maps import resolve_system_flow_ir, system_flow_catalog
from backend.services import lab_tools

router = APIRouter(tags=["lab"])


# ═══════════════════════════════════════════════════════════════
# 實驗室整合 — Firecrawl / Prompt Optimizer / Ponytail / Archify
# ═══════════════════════════════════════════════════════════════


class FirecrawlScrapeRequest(BaseModel):
    url: str
    only_main_content: bool = True


class FirecrawlSearchRequest(BaseModel):
    query: str
    limit: int = 5


class PromptOptimizeRequest(BaseModel):
    prompt: str
    mode: str = "user"
    goal: str = ""


class PonytailReviewRequest(BaseModel):
    content: str
    kind: str = "code"


class ArchifyGenerateRequest(BaseModel):
    description: str


class ArchifyRenderRequest(BaseModel):
    ir: dict[str, Any] = {}
    view: str = ""
    id: str = ""
    kind: str = ""


@router.post("/lab/firecrawl/scrape")
async def lab_firecrawl_scrape(body: FirecrawlScrapeRequest):
    """Firecrawl 單頁抓取（可選 API 金鑰）。"""
    try:
        return lab_tools.firecrawl_scrape(body.url, only_main_content=body.only_main_content)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Firecrawl HTTP {exc.response.status_code}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/lab/firecrawl/search")
async def lab_firecrawl_search(body: FirecrawlSearchRequest):
    """Firecrawl 網頁搜尋（需 FIRECRAWL_API_KEY）。"""
    try:
        return lab_tools.firecrawl_search(body.query, limit=body.limit)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Firecrawl HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/lab/prompt/optimize")
async def lab_prompt_optimize(body: PromptOptimizeRequest):
    """Prompt Optimizer — LLM 提示詞優化。"""
    try:
        return lab_tools.optimize_prompt(body.prompt, mode=body.mode, goal=body.goal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/lab/ponytail/review")
async def lab_ponytail_review(body: PonytailReviewRequest):
    """Ponytail — 過度工程審查。"""
    try:
        return lab_tools.ponytail_review(body.content, kind=body.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/lab/archify/evoloop")
async def lab_archify_evoloop():
    """Archify — EvoLoop 內建架構 IR。"""
    return lab_tools.get_evoloop_architecture()


@router.get("/lab/archify/system-flows")
async def lab_archify_system_flows():
    """Archify — 系統架構／運作流程圖目錄（Lab 流程選擇器）。"""
    return system_flow_catalog()


@router.get("/lab/archify/system-flows/{flow_id}")
async def lab_archify_system_flow(flow_id: str):
    """Archify — 單一系統流程簡化 IR。"""
    try:
        return resolve_system_flow_ir(flow_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/lab/archify/generate")
async def lab_archify_generate(body: ArchifyGenerateRequest):
    """Archify — 由描述生成架構 IR。"""
    try:
        return lab_tools.generate_architecture(body.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _archify_public(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "html": payload["html"],
        "diagram_type": payload.get("diagram_type"),
        "title": payload.get("title"),
        "engine": payload.get("engine") or "archify",
        "source": payload.get("source"),
    }


@router.get("/lab/archify/html")
async def lab_archify_html(view: str = "overview", id: str = "", kind: str = ""):
    """用官方 archify CLI 把策略庫／系統圖編成獨立 HTML。"""
    try:
        return _archify_public(render_view(view=view, id=id, kind=kind))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/lab/archify/artifact")
async def lab_archify_artifact(view: str = "overview", id: str = "", kind: str = ""):
    """同一張策略圖，直接回 Archify HTML（iframe / 另開分頁）。"""
    try:
        payload = render_view(view=view, id=id, kind=kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as orig:
        raise HTTPException(status_code=503, detail=str(orig)) from orig
    except Exception as orig:
        raise HTTPException(status_code=502, detail=str(orig)) from orig
    return HTMLResponse(payload["html"], media_type="text/html; charset=utf-8")


@router.post("/lab/archify/render")
async def lab_archify_render(body: ArchifyRenderRequest):
    """把簡化 IR（或正式 Archify JSON）交給 archify CLI 渲染。"""
    try:
        if body.ir:
            return _archify_public(render_ir(body.ir))
        return _archify_public(render_view(view=body.view, id=body.id, kind=body.kind))
    except ValueError as orig:
        raise HTTPException(status_code=400, detail=str(orig)) from orig
    except FileNotFoundError as orig:
        raise HTTPException(status_code=503, detail=str(orig)) from orig
    except Exception as orig:
        raise HTTPException(status_code=502, detail=str(orig)) from orig


def _require_quant_pack() -> None:
    require_feature(PACK_QUANT, current_billing_user())
    meter_quant_call(reference="lab_quant")


@router.get("/lab/archify/strategies")
async def lab_archify_strategies():
    """Archify — 策略庫總覽／分類拓撲 IR（全部策略可視化）。"""
    _require_quant_pack()
    return strategy_catalog_maps()


@router.get("/lab/archify/strategies/{strategy_id}")
async def lab_archify_strategy(strategy_id: str):
    """Archify — 單策略工作流／生命週期 IR。"""
    _require_quant_pack()
    payload = strategy_maps(strategy_id)
    if not payload.get("ok"):
        raise HTTPException(status_code=404, detail=payload.get("error") or "未知策略")
    return payload


@router.get("/lab/quant/strategies")
async def lab_quant_strategies(category: str = "", query: str = "", status: str = ""):
    """stock-quant 策略庫分類樹（實驗室瀏覽；角色仍用 market_strategy_catalog）。"""
    _require_quant_pack()
    return market_strategy_catalog(
        category=category,
        query=query,
        status=status,
        listing=True,
    )


@router.get("/lab/quant/preview")
async def lab_quant_preview(strategy: str, symbol: str = "600519"):
    """策略工作流 IR + 回測權益／收盤曲線（實驗室圖表）。"""
    _require_quant_pack()
    payload = strategy_preview(strategy, symbol=symbol)
    if not payload.get("ok"):
        raise HTTPException(status_code=404, detail=payload.get("error") or "未知策略")
    return payload


@router.get("/lab/quant/capital-flow")
async def lab_quant_capital_flow(
    strategy: str,
    symbol: str = "600519",
    initial_capital: float = 1_000_000.0,
    stop_loss_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    position_pct: float | None = None,
    enable_t1: bool = False,
):
    """策略資金流三視圖：瀑布 Mermaid、狀態機 Mermaid、時間軸表。"""
    _require_quant_pack()
    payload = strategy_capital_flow(
        strategy,
        symbol=symbol,
        initial_capital=initial_capital,
        stop_loss_pct=stop_loss_pct,
        trailing_stop_pct=trailing_stop_pct,
        position_pct=position_pct,
        enable_t1=enable_t1,
    )
    if not payload.get("ok"):
        raise HTTPException(status_code=404, detail=payload.get("error") or "未知策略")
    return payload
