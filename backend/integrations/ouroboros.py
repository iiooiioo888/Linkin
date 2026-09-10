"""Ouroboros Agent OS 客戶端（訪談閘門／三階段評估／演化迴圈）。

對接本地 Ouroboros MCP 服務（``ouroboros mcp serve`` 的 HTTP transport，
預設 ``http://localhost:8600``），以 JSON-RPC 呼叫其工具：
- ``ouroboros_interview``：蘇格拉底式訪談，產出 ambiguity 分數
- ``ouroboros_auto``：目標 → Seed → 執行交接
- ``ouroboros_evaluate``：三階段驗證（Mechanical → Semantic → Consensus）

契約對齊：
- **Ambiguity 閘門寫死**：ambiguity > 0.2 時禁止進入 Seed 生成，
  除非顯式 ``force=True``（對齊 Ouroboros 官方 gate 語義）。
- 評估為**顯式動作**；禁止在串流完成時自動觸發（C-AUDIT-001／C-PLUGIN-001 精神）。
- fail-open：服務不可達 → 降級回傳＋原因碼，不阻斷 Linkin 主管線。

環境變數：
- ``LINKIN_OUROBOROS_ENABLED``（預設 false）
- ``LINKIN_OUROBOROS_BASE_URL``（預設 http://localhost:8600）
- ``LINKIN_OUROBOROS_API_KEY``
"""

from __future__ import annotations

import itertools
import os
from dataclasses import dataclass, field
from typing import Any

from backend.integrations.base import IntegrationConfig, IntegrationResponse, ResilientHttpClient

DEFAULT_BASE_URL = "http://localhost:8600"

# ── 閘門常數（對齊官方語義，寫死為契約）──
AMBIGUITY_GATE = 0.2          # ambiguity ≤ 0.2 才准生成 Seed
ONTOLOGY_CONVERGENCE = 0.95   # 連續世代相似度 ≥ 0.95 → 演化收斂

ERR_AMBIGUITY_GATE_BLOCKED = "ERR_AMBIGUITY_GATE_BLOCKED"
ERR_EVALUATE_NOT_PASSED = "ERR_EVALUATE_NOT_PASSED"


def config_from_env(env: dict[str, str] | None = None) -> IntegrationConfig:
    e = env if env is not None else os.environ
    return IntegrationConfig(
        name="ouroboros",
        base_url=e.get("LINKIN_OUROBOROS_BASE_URL", DEFAULT_BASE_URL),
        enabled=e.get("LINKIN_OUROBOROS_ENABLED", "false").lower() == "true",
        api_key=e.get("LINKIN_OUROBOROS_API_KEY", ""),
    )


@dataclass
class OuroborosClient:
    """Ouroboros MCP 工具的 fail-open 封裝（JSON-RPC over HTTP）。"""

    http: ResilientHttpClient = field(init=False)

    def __init__(self, config: IntegrationConfig | None = None, **http_kwargs: Any) -> None:
        self.http = ResilientHttpClient(config or config_from_env(), **http_kwargs)
        self._ids = itertools.count(1)

    # ── MCP JSON-RPC ──

    def call_tool(self, tool: str, arguments: dict[str, Any]) -> IntegrationResponse:
        rpc_id = next(self._ids)
        return self.http.post(
            "mcp",
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            },
        )

    # ── 訪談與 Seed 閘門 ──

    def interview(self, goal: str, *, context: str = "") -> IntegrationResponse:
        args: dict[str, Any] = {"goal": goal}
        if context:
            args["context"] = context
        return self.call_tool("ouroboros_interview", args)

    def gate_seed(self, ambiguity: float, *, force: bool = False) -> dict:
        """Ambiguity 閘門（本地判定，不需服務在線；契約層守衛）。

        Returns:
            dict: ``allowed``、``error_code``（阻擋時）、``ambiguity``、``forced``。
        """
        if ambiguity <= AMBIGUITY_GATE:
            return {"allowed": True, "ambiguity": ambiguity, "forced": False}
        if force:
            return {"allowed": True, "ambiguity": ambiguity, "forced": True}
        return {
            "allowed": False,
            "error_code": ERR_AMBIGUITY_GATE_BLOCKED,
            "ambiguity": ambiguity,
            "forced": False,
        }

    def start_auto(self, goal: str, *, ambiguity: float, force: bool = False) -> dict:
        """顯式啟動 auto 流程；先過本地 ambiguity 閘門，再呼叫遠端工具。"""
        gate = self.gate_seed(ambiguity, force=force)
        if not gate["allowed"]:
            return {"ok": False, **gate}
        resp = self.call_tool("ouroboros_auto", {"goal": goal})
        if not resp.ok:
            return {"ok": False, "error_code": resp.error_code, "reason_code": resp.reason_code, **gate}
        return {"ok": True, "result": resp.data, **gate}

    # ── 三階段評估（顯式觸發）──

    def evaluate(self, execution_id: str, *, stages: tuple[str, ...] = ("mechanical", "semantic", "consensus")) -> dict:
        """依序跑三階段；任一階段失敗即短路（Mechanical 免費 → Semantic → Consensus）。"""
        results: list[dict] = []
        for stage in stages:
            resp = self.call_tool("ouroboros_evaluate", {"execution_id": execution_id, "stage": stage})
            if not resp.ok:
                return {
                    "ok": False,
                    "passed": False,
                    "failed_stage": stage,
                    "error_code": resp.error_code or ERR_EVALUATE_NOT_PASSED,
                    "stages": results,
                }
            results.append({"stage": stage, "result": resp.data})
        return {"ok": True, "passed": True, "stages": results}

    def check_convergence(self, similarities: list[float], *, window: int = 3) -> dict:
        """本地收斂判定（對齊官方：連續 window 代 ≥ 0.95 → 收斂）。"""
        if len(similarities) < window:
            return {"converged": False, "reason": "insufficient_generations"}
        tail = similarities[-window:]
        if all(s >= ONTOLOGY_CONVERGENCE for s in tail):
            return {"converged": True, "reason": "ontology_stabilized", "window": tail}
        return {"converged": False, "reason": "still_evolving", "window": tail}
