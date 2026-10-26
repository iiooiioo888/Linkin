"""預設 12 個服務與同步呼叫深度。"""

from __future__ import annotations

from linkin_core.contracts.slo import MAX_SYNC_HOPS

# 另加 frontend 映像。團隊小於 5 人時見 SMALL_TEAM_MERGED。
DEFAULT_SERVICES: tuple[str, ...] = (
    "api-gateway",
    "route-service",
    "context-service",
    "reflection-service",
    "company-orchestrator",
    "seat-executor",
    "tool-gateway",
    "guardrail-service",
    "opc-service",
    "minecraft-gateway",
    "memory-service",
    "observability-collector",
)

FRONTEND_SERVICE = "frontend"

# 小於 5 人時併回去，功能清單仍按模組保留。
SMALL_TEAM_MERGED: dict[str, str] = {
    "context-service": "route-service",
    "reflection-service": "company-orchestrator",
}

# 同步鏈。長度含起點。context 對 memory / opc 讀是平行扇出，不計入第四跳。
SYNC_CHAINS: dict[str, tuple[str, ...]] = {
    "route_preview": ("api-gateway", "route-service", "context-service"),
    "chat_simple": ("api-gateway", "route-service", "reflection-service"),
    "task_accept": ("api-gateway", "company-orchestrator"),
    "tool_invoke": ("seat-executor", "tool-gateway", "guardrail-service"),
    "opc_write_accept": ("guardrail-service", "opc-service"),
}

# (來源, 目的, 埠)。ingress-nginx 是命名空間，不是工作負載。
ALLOW: tuple[tuple[str, str, int], ...] = (
    ("ingress-nginx", "api-gateway", 8080),
    ("api-gateway", "route-service", 8080),
    ("api-gateway", "reflection-service", 8080),
    ("api-gateway", "company-orchestrator", 8080),
    ("api-gateway", "tool-gateway", 8080),
    ("api-gateway", "guardrail-service", 8080),
    ("api-gateway", "frontend", 8080),
    ("api-gateway", "redis", 6379),
    ("route-service", "context-service", 8080),
    ("context-service", "memory-service", 8080),
    ("context-service", "opc-service", 8080),
    ("memory-service", "chroma", 8000),
    ("company-orchestrator", "postgres", 5432),
    ("company-orchestrator", "nats", 4222),
    ("guardrail-service", "postgres", 5432),
    ("observability-collector", "postgres", 5432),
    ("seat-executor", "tool-gateway", 8080),
    ("seat-executor", "nats", 4222),
    ("tool-gateway", "guardrail-service", 8080),
    ("guardrail-service", "opc-service", 8081),
    ("guardrail-service", "minecraft-gateway", 8080),
)

OTLP_PORT = 4317
DNS_PORTS = (53,)


def assert_sync_budget() -> None:
    for name, chain in SYNC_CHAINS.items():
        if len(chain) > MAX_SYNC_HOPS:
            raise ValueError(f"{name} 同步鏈 {len(chain)} 跳，上限 {MAX_SYNC_HOPS}")


def seat_executor_targets() -> set[str]:
    return {dst for src, dst, _port in ALLOW if src == "seat-executor"}
