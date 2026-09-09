"""預算控制系統。

提供：
- BudgetManager: 追蹤任務/會話/月度花費，強制執行上限與降級
- TierRouter: 根據任務重要性與預算壓力選擇模型層級
- CostTracker: 估算 LLM 呼叫成本（token 計價）

所有金額以 USD 為單位。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.company.rate_card import (
    estimate_usage_cost,
    get_model_costs,
    get_model_rate_cards,
    public_rate_cards,
    rate_card_for,
    reload_model_costs,
)
from backend.company.state import BudgetConfig, BudgetTier

logger = logging.getLogger(__name__)

# ── 預算預測配置 ──
DEFAULT_HISTORY_WINDOW_DAYS = 7
DEFAULT_FORECAST_WINDOW_DAYS = 30
MIN_DATA_POINTS_FOR_FORECAST = 3


class CostTracker:
    """估算 LLM 呼叫成本（含快取／推理／多模態收費項）。"""

    @staticmethod
    def estimate_cost(
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        *,
        cached_input_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        image_tokens: int = 0,
        audio_tokens: int = 0,
        embedding_tokens: int = 0,
        **extra: float,
    ) -> float:
        """根據各收費項用量估算成本（USD）。"""
        return estimate_usage_cost(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            image_tokens=image_tokens,
            audio_tokens=audio_tokens,
            embedding_tokens=embedding_tokens,
            **extra,
        )

    @staticmethod
    def estimate_cost_rough(model: str, complexity: str = "medium") -> float:
        """粗略估算（無 token 計數時使用）。"""
        base_tokens = {"low": 500, "medium": 2000, "high": 8000}
        tokens = base_tokens.get(complexity, 2000)
        return CostTracker.estimate_cost(model, input_tokens=tokens, output_tokens=tokens)


class TierRouter:
    """根據任務重要性與預算壓力選擇模型層級。"""

    def __init__(self, config: BudgetConfig):
        self.config = config

    def resolve_model(
        self,
        tier: BudgetTier,
        budget_pressure: float = 0.0,  # 0.0 ~ 1.0，越高壓力越大
    ) -> str:
        """根據層級與預算壓力解析實際使用的模型名稱。

        budget_pressure >= degrade_threshold 時，使用降級鏈中的便宜模型。
        """
        if budget_pressure >= self.config.degrade_threshold:
            degraded = self.config.degrade_chain.get(tier)
            if degraded:
                logger.info(
                    "預算壓力 %.0f%%，tier %s 降級為 %s",
                    budget_pressure * 100,
                    tier.value,
                    degraded,
                )
                return degraded
        return self.config.tier_models.get(tier, "gpt-4o-mini")

    def select_tier(
        self,
        task_complexity: str,
        is_critical: bool = False,
    ) -> BudgetTier:
        """根據任務特徵選擇層級。"""
        if is_critical:
            return BudgetTier.CRITICAL
        mapping = {
            "high": BudgetTier.REASONING,
            "medium": BudgetTier.ROUTINE,
            "low": BudgetTier.SUMMARY,
        }
        return mapping.get(task_complexity, BudgetTier.ROUTINE)


class BudgetManager:
    """預算管理器：追蹤花費、強制執行上限。

    總預算 = API（LLM）用量 + 雲資源用量（本地 Docker + 阿里雲 BSS）。
    """

    def __init__(self, config: BudgetConfig):
        self.config = config
        self._task_spent: float = 0.0
        self._session_spent: float = 0.0
        self._monthly_spent: float = 0.0  # 僅 API（LLM）月累計
        self._docker_cost: float = 0.0
        self._aliyun_cost: float = 0.0
        self._task_aliyun_delta: float = 0.0  # 本任務內阿里雲增量（勿用月累計倒扣）
        self._month: int = datetime.now(timezone.utc).month
        self._year: int = datetime.now(timezone.utc).year
        self._router = TierRouter(config)
        self._tokens_in: int = 0
        self._tokens_out: int = 0
        # 預算預測所需數據
        self._spending_history: list[dict[str, Any]] = []  # [{date, api_cost, cloud_cost, total}]

    # ── 屬性 ──

    @property
    def task_spent(self) -> float:
        return self._task_spent

    @property
    def session_spent(self) -> float:
        return self._session_spent

    @property
    def docker_cost(self) -> float:
        return self._docker_cost

    @property
    def aliyun_cost(self) -> float:
        return self._aliyun_cost

    @property
    def cloud_cost(self) -> float:
        """雲資源合計（Docker + 阿里雲）。"""
        return self._docker_cost + self._aliyun_cost

    @property
    def api_cost(self) -> float:
        """API（LLM）月累計。"""
        return self._monthly_spent

    @property
    def task_api_spent(self) -> float:
        """本任務 API（LLM）花費 = 任務總額 − Docker − 本任務阿里雲增量。"""
        return round(
            max(0.0, self._task_spent - self._docker_cost - self._task_aliyun_delta),
            6,
        )

    @property
    def monthly_spent(self) -> float:
        """月度總花費（API + 雲資源），供上限檢查。"""
        return self._monthly_spent + self.cloud_cost

    @property
    def budget_pressure(self) -> float:
        """計算當前預算壓力（0.0 ~ 1.0）。

        API + Docker + 阿里雲一併納入壓力計算。
        """
        pressures: list[float] = []
        for spent, limit in [
            (self._task_spent, self.config.task_limit_usd),
            (self._session_spent, self.config.session_limit_usd),
            (self.monthly_spent, self.config.monthly_limit_usd),
        ]:
            if limit > 0:
                pressures.append(spent / limit)
        return max(pressures) if pressures else 0.0

    @property
    def total_spent(self) -> float:
        """總花費（API + Docker + 阿里雲）。"""
        return self.monthly_spent

    # ── 月度重置 ──

    def _check_month_rollover(self) -> None:
        """檢查是否需要月度重置。"""
        now = datetime.now(timezone.utc)
        if now.month != self._month or now.year != self._year:
            logger.info("月度預算重置：%d-%02d → %d-%02d",
                        self._year, self._month, now.year, now.month)
            self._monthly_spent = 0.0
            self._aliyun_cost = 0.0
            self._month = now.month
            self._year = now.year

    # ── 花費記錄 ──

    def record_cost(
        self,
        amount: float,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        complexity: str | None = None,
    ) -> None:
        """記錄一筆 API（LLM）花費到所有追蹤層級。"""
        self._check_month_rollover()
        self._task_spent += amount
        self._session_spent += amount
        self._monthly_spent += amount
        tin, tout = int(input_tokens or 0), int(output_tokens or 0)
        if complexity and tin <= 0 and tout <= 0:
            n = {"low": 500, "medium": 2000, "high": 8000}.get(complexity, 2000)
            tin = tout = n
        if tin > 0:
            self._tokens_in += tin
        if tout > 0:
            self._tokens_out += tout
        pressure = self.budget_pressure
        if pressure >= self.config.warn_threshold:
            logger.warning(
                "預算警告：已達 %.0f%%（任務 $%.4f/$%.2f，會話 $%.4f/$%.2f，月 $%.4f/$%.2f）"
                "｜API $%.4f + 雲 $%.4f",
                pressure * 100,
                self._task_spent, self.config.task_limit_usd,
                self._session_spent, self.config.session_limit_usd,
                self.monthly_spent, self.config.monthly_limit_usd,
                self._monthly_spent, self.cloud_cost,
            )

    def record_docker_cost(self, service: str, hours: float) -> float:
        """記錄容器服務按時費用（USD），計入雲資源預算（不與 API 雙重累加）。

        類似阿里雲 ECS 按量付費：費用 = 小時費率 × 運行時長。

        Args:
            service: 服務名稱
            hours: 運行時長（小時）

        Returns:
            該時段的費用（USD）
        """
        from backend.company.docker_tools import get_service_hourly_rate
        rate = get_service_hourly_rate(service)
        cost = rate * hours
        if cost > 0:
            self._docker_cost += cost
            self._session_spent += cost
            self._task_spent += cost
            logger.debug(
                "Docker %s 運行 %.2fh，費率 $%.3f/h，費用 $%.4f（累計 Docker $%.4f）",
                service, hours, rate, cost, self._docker_cost,
            )
            pressure = self.budget_pressure
            if pressure >= self.config.warn_threshold:
                logger.warning(
                    "雲資源成本警告：預算壓力 %.0f%%（API $%.4f + Docker $%.4f + 阿里雲 $%.4f = $%.4f）",
                    pressure * 100,
                    self._monthly_spent,
                    self._docker_cost,
                    self._aliyun_cost,
                    self.total_spent,
                )
        return cost

    def record_aliyun_cost(self, amount_usd: float) -> float:
        """同步阿里雲 BSS 帳目（USD）到公司預算。

        採「設值」語意：以最新查詢結果覆寫本月阿里雲累計，避免輪詢重複加總。
        """
        self._check_month_rollover()
        amount = max(0.0, float(amount_usd or 0))
        delta = amount - self._aliyun_cost
        self._aliyun_cost = amount
        if delta > 0:
            self._session_spent += delta
            self._task_spent += delta
            self._task_aliyun_delta += delta
            logger.info("阿里雲費用同步：$%.4f（Δ $%.4f）", amount, delta)
        return amount

    def sync_cloud_from_billing(self) -> dict[str, float]:
        """從 CloudBilling 拉取 Docker + 阿里雲並寫入預算計數器。"""
        from backend.services.cloud_console import get_cloud_billing

        summary = get_cloud_billing().get_billing_summary()
        docker_usd = float((summary.get("breakdown") or {}).get("docker_usd") or 0)
        aliyun_usd = float((summary.get("breakdown") or {}).get("aliyun_usd") or 0)
        # Docker 採快照覆寫（與 record_docker_runtime 一致）
        if docker_usd > self._docker_cost:
            delta = docker_usd - self._docker_cost
            self._docker_cost = docker_usd
            self._session_spent += delta
            self._task_spent += delta
        self.record_aliyun_cost(aliyun_usd)
        return {
            "api_usd": round(self._monthly_spent, 4),
            "docker_usd": round(self._docker_cost, 4),
            "aliyun_usd": round(self._aliyun_cost, 4),
            "cloud_usd": round(self.cloud_cost, 4),
            "total_usd": round(self.total_spent, 4),
        }

    def record_docker_runtime(self) -> dict[str, Any]:
        """記錄當前所有容器的運行成本（用於任務開始/結束快照）。

        從 DockerManager 獲取所有容器 uptime，計算各服務費用並記錄。

        Returns:
            {services: {svc: {rate, hours, cost}}, total_cost: float}
        """
        from backend.services.docker_manager import get_docker_manager
        from backend.company.docker_tools import get_service_hourly_rate

        dm = get_docker_manager()
        if not dm.available:
            return {"services": {}, "total_cost": 0.0}

        containers = dm.list_containers()
        services: dict[str, dict[str, Any]] = {}
        total = 0.0

        for c in containers:
            svc = c.get("service", c["name"])
            if svc == "_docker_unavailable":
                continue
            rate = get_service_hourly_rate(svc)
            uptime_s = float(c.get("uptime_seconds", 0))
            hours = uptime_s / 3600.0
            cost = rate * hours
            services[svc] = {"rate": rate, "hours": round(hours, 2), "cost": round(cost, 4)}
            total += cost

        # 記錄總 Docker 成本到預算
        if total > 0:
            delta = total - self._docker_cost
            if delta > 0.001:  # 只記錄顯著變化
                self._docker_cost = total
                logger.info(
                    "Docker 運行成本快照：總計 $%.4f（%d 個服務）",
                    total, len(services),
                )

        return {"services": services, "total_cost": round(total, 4)}

    # ── Docker 預算控制 ──

    def get_docker_optimization_suggestions(self) -> list[dict[str, Any]]:
        """根據預算壓力提供容器優化建議。

        當預算壓力超過閾值時，建議停止非核心容器以節省成本。

        Returns:
            建議列表，每項包含 service, action, reason, estimated_saving
        """
        from backend.services.docker_manager import get_docker_manager
        from backend.company.docker_tools import get_service_hourly_rate

        pressure = self.budget_pressure
        suggestions: list[dict[str, Any]] = []

        # 只有壓力超過警告閾值才建議優化
        if pressure < self.config.warn_threshold:
            return suggestions

        dm = get_docker_manager()
        if not dm.available:
            return suggestions

        containers = dm.list_containers()

        # 核心服務不可停
        CORE_SERVICES = {"backend"}
        # 可停止的服務（按優先級排序）
        STOPPABLE_PRIORITY = ["chroma", "frontend", "opc", "redis"]

        for svc in STOPPABLE_PRIORITY:
            container = next((c for c in containers if c.get("service") == svc), None)
            if not container:
                continue

            status = container.get("status", "")
            if not status.startswith("Up"):
                continue

            rate = get_service_hourly_rate(svc)
            # 估算停止後每小時節省
            hourly_saving = rate

            if pressure >= 0.9:  # 90%+ 壓力 → 停止所有非核心
                suggestions.append({
                    "service": svc,
                    "action": "stop",
                    "reason": f"預算壓力 {pressure:.0%}，建議停止 {svc} 節省 ${rate:.3f}/h",
                    "estimated_saving_per_hour": round(hourly_saving, 4),
                    "priority": "high",
                })
            elif pressure >= 0.7 and svc in ("chroma", "frontend"):  # 70%+ → 停止低優先級
                suggestions.append({
                    "service": svc,
                    "action": "stop",
                    "reason": f"預算壓力 {pressure:.0%}，建議停止 {svc} 節省 ${rate:.3f}/h",
                    "estimated_saving_per_hour": round(hourly_saving, 4),
                    "priority": "medium",
                })

        return suggestions

    def can_afford_docker_runtime(self, estimated_hours: float = 1.0) -> tuple[bool, str]:
        """檢查是否可負擔 Docker 容器繼續運行。

        Args:
            estimated_hours: 預估繼續運行時長

        Returns:
            (can_continue, reason)
        """
        from backend.company.docker_tools import get_service_hourly_rate
        from backend.services.docker_manager import get_docker_manager

        dm = get_docker_manager()
        if not dm.available:
            return True, "Docker 不可用，無需檢查"

        containers = dm.list_containers()
        total_hourly = 0.0
        for c in containers:
            svc = c.get("service", c["name"])
            if svc == "_docker_unavailable":
                continue
            if c.get("status", "").startswith("Up"):
                total_hourly += get_service_hourly_rate(svc)

        estimated_cost = total_hourly * estimated_hours
        return self.can_afford(estimated_cost, BudgetTier.ROUTINE)

    # ── 預算檢查 ──

    def can_afford(self, estimated_cost: float, tier: BudgetTier) -> tuple[bool, str]:
        """檢查是否可負擔預估成本。

        Returns:
            (can_proceed, reason): 是否可繼續，以及原因說明
        """
        self._check_month_rollover()

        # 檢查月度上限（API + 雲資源）
        if (self.config.monthly_limit_usd > 0
                and self.monthly_spent + estimated_cost > self.config.monthly_limit_usd):
            if self.config.hard_stop:
                return False, (
                    f"月度預算已達上限 ($ {self.config.monthly_limit_usd})，"
                    f"已花費 $ {self.monthly_spent:.4f}"
                    f"（API ${self._monthly_spent:.4f} + 雲 ${self.cloud_cost:.4f}）"
                )
            return True, "月度預算接近上限，已降級到便宜模型"

        # 檢查會話上限
        if (self.config.session_limit_usd > 0
                and self._session_spent + estimated_cost > self.config.session_limit_usd):
            if self.config.hard_stop:
                return False, (
                    f"會話預算已達上限 ($ {self.config.session_limit_usd})，"
                    f"已花費 $ {self._session_spent:.4f}"
                )
            return True, "會話預算接近上限，已降級到便宜模型"

        # 檢查任務上限
        if (self.config.task_limit_usd > 0
                and self._task_spent + estimated_cost > self.config.task_limit_usd):
            if self.config.hard_stop:
                return False, (
                    f"任務預算已達上限 ($ {self.config.task_limit_usd})，"
                    f"已花費 $ {self._task_spent:.4f}"
                )
            return True, "任務預算接近上限，已降級到便宜模型"

        return True, "預算充足"

    def resolve_model_for_tier(self, tier: BudgetTier) -> str:
        """根據當前預算壓力與層級選擇模型。

        用戶顯式配置過 LLM 模型時（如 Qwen 端點），所有層級
        動態跟隨該模型，避免使用端點不存在的預設模型
        （如 gpt-4o-mini）。此檢查在每次調用時動態執行，
        確保配置變更即時生效。
        """
        from backend.core.llm_config import get_explicit_model
        from backend.core.provider_pool import clamp_model

        configured = get_explicit_model()
        if configured:
            return clamp_model(configured)
        return clamp_model(self._router.resolve_model(tier, self.budget_pressure))

    # ── 重置 ──

    def reset_task(self) -> None:
        """重置任務級別花費（新任務開始時）。"""
        self._task_spent = 0.0
        self._docker_cost = 0.0
        self._task_aliyun_delta = 0.0
        self._tokens_in = 0
        self._tokens_out = 0

    def reset_session(self) -> None:
        """重置會話級別花費。"""
        self._session_spent = 0.0
        self._task_spent = 0.0
        self._task_aliyun_delta = 0.0

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """序列化為字典。"""
        return {
            "task_spent": round(self._task_spent, 4),
            "task_api_spent": round(self.task_api_spent, 4),
            "task_limit": self.config.task_limit_usd,
            "session_spent": round(self._session_spent, 4),
            "session_limit": self.config.session_limit_usd,
            "monthly_spent": round(self.monthly_spent, 4),
            "monthly_limit": self.config.monthly_limit_usd,
            "api_cost": round(self._monthly_spent, 4),
            "docker_cost": round(self._docker_cost, 4),
            "aliyun_cost": round(self._aliyun_cost, 4),
            "cloud_cost": round(self.cloud_cost, 4),
            "total_spent": round(self.total_spent, 4),
            "budget_pressure": round(self.budget_pressure, 2),
            "tokens_in": int(self._tokens_in),
            "tokens_out": int(self._tokens_out),
            "tokens_total": int(self._tokens_in + self._tokens_out),
            "active_tier": self._router.resolve_model(
                BudgetTier.ROUTINE, self.budget_pressure
            ),
        }