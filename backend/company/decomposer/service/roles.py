"""TaskDecomposer 的角色比對與最佳角色挑選（自 decomposer/service.py 抽出）。"""

from __future__ import annotations

from .state import _StateMixin


class _RolesMixin(_StateMixin):

    def _find_closest_role(
        self,
        target: str,
        available: set[str],
    ) -> str | None:
        """尋找最接近的可用角色。"""
        # 精確匹配
        if target in available:
            return target

        # 角色替換映射
        fallback_map: dict[str, str] = {
            "ui_designer": "developer",
            "css_dev": "developer",
            "js_dev": "developer",
            "backend_dev": "developer",
            "tester": "developer",
            "devops": "developer",
            "architect": "tech_lead",
            "frontend_lead": "tech_lead",
            "backend_lead": "tech_lead",
            "test_lead": "tech_lead",
            "tech_lead": "manager",
            "analyst": "developer",
            "reviewer": "developer",
            "synthesizer": "developer",
            "coordinator": "manager",
        }

        fallback = fallback_map.get(target)
        if fallback and fallback in available:
            return fallback

        # 最後回退：使用第一個可用角色
        if "developer" in available:
            return "developer"
        if "manager" in available:
            return "manager"
        return next(iter(available), None) if available else None

    def _pick_best_role(
        self,
        goal: str,
        available: set[str],
    ) -> str:
        """根據目標內容選擇最佳執行角色。"""
        goal_lower = goal.lower()

        role_keywords: list[tuple[list[str], str]] = [
            (["ui", "設計", "design", "wireframe", "佈局", "layout", "視覺"], "ui_designer"),
            (["css", "樣式", "style", "動畫", "animation", "rwd", "響應式"], "css_dev"),
            (["js", "javascript", "前端", "frontend", "react", "vue", "互動", "狀態"], "js_dev"),
            (["api", "後端", "backend", "資料庫", "database", "sql", "server"], "backend_dev"),
            (["測試", "test", "qa", "品質", "bug"], "tester"),
            (["架構", "architect", "設計", "系統"], "architect"),
            (["部署", "deploy", "ci/cd", "docker", "k8s", "維運"], "devops"),
            (["分析", "analyst", "研究", "research", "報告", "report"], "analyst"),
            (["審查", "review", "檢查"], "reviewer"),
            (["量化", "估值", "pe", "股票", "行情", "回測", "夏普", "外匯", "加密"], "quant_analyst"),
            (["opc", "工業", "產線", "標籤"], "opc_engineer"),
            (["爬蟲", "crawl", "採集"], "crawler"),
            (["故事", "情節", "對白", "story"], "story_writer"),
            (["rag", "檢索增強", "切片"], "rag_engineer"),
            (["評測", "eval", "基準"], "eval_engineer"),
            (["機器學習", "ml", "訓練"], "ml_engineer"),
            (["負載", "壓測", "吞吐"], "load_tester"),
            (["滲透", "弱點", "攻擊面"], "pen_tester"),
            (["plc", "連鎖"], "plc_engineer"),
            (["路由", "failover", "熔斷"], "router_eng"),
        ]

        for keywords, role in role_keywords:
            if any(kw in goal_lower for kw in keywords):
                if role in available:
                    return role
                # 嘗試回退
                fallback = self._find_closest_role(role, available)
                if fallback:
                    return fallback

        # 預設角色
        if "developer" in available:
            return "developer"
        return next(iter(available), "developer")
