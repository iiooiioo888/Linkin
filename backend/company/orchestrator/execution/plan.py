"""作戰計畫建構 mixin：把 L3 作戰地圖孵化成工作項。"""

from __future__ import annotations

from typing import Any

from backend.company.roles import RoleType

from .._base import OrchestratorBase


class _ExecutionPlanMixin(OrchestratorBase):
    """作戰計畫 → 工作項（含依賴與原子角色卡）。"""

    def _build_from_battle_plan(self, plan: dict[str, Any]) -> list:
        """把 L3 作戰地圖孵化成工作項（含依賴與原子角色卡）。"""
        from backend.company.raho.atomic_pool import incubate_instance
        from backend.company.state import BudgetTier, WorkItemStatus

        template_role = {
            "web_scraper": RoleType.CRAWLER,
            "social_listener": RoleType.RESEARCHER,
            "pdf_extractor": RoleType.ANALYST,
            "data_synthesizer": RoleType.ANALYST,
            "swot": RoleType.ANALYST,
            "copy": RoleType.CONTENT_WRITER,
            "code": RoleType.DEVELOPER,
            "review": RoleType.REVIEWER,
            "plan": RoleType.COORDINATOR,
            "generic": RoleType.DEVELOPER,
            "research": RoleType.RESEARCHER,
            "file_ingest": RoleType.ANALYST,
        }
        available = {rt.value: rt for rt in self.config.roles}
        nodes = list(plan.get("dag_nodes") or [])
        instances = {
            str(row.get("node_id")): row
            for row in (plan.get("atomic_role_instances") or [])
            if isinstance(row, dict)
        }
        created: list[Any] = []
        id_map: dict[str, str] = {}
        for node in nodes:
            node_id = str(node.get("node_id") or f"N{len(created) + 1}")
            tmpl = str(node.get("assigned_role_template") or "generic")
            role = template_role.get(tmpl, RoleType.DEVELOPER)
            if role.value not in available:
                role = available.get("developer") or available.get("analyst") or next(iter(self.config.roles), RoleType.DEVELOPER)
            instance = instances.get(node_id) or {}
            desc = str(node.get("description") or "")
            item = self.work_items.create(
                title=desc[:80] or node_id,
                description=desc,
                assignee=role,
                created_by=RoleType.TACTICAL_COMMANDER,
                depends_on=[],
                tier=BudgetTier.SUMMARY if instance.get("token_budget", 3000) <= 2000 else BudgetTier.ROUTINE,
            )
            item.artifacts["node_id"] = node_id
            item.artifacts["battle_plan_id"] = plan.get("plan_id")
            incubate_instance(item, {**instance, "template_id": tmpl})
            item.transition_to(WorkItemStatus.READY)
            created.append(item)
            id_map[node_id] = item.id
        for node, item in zip(nodes, created):
            deps = [id_map[str(d)] for d in (node.get("depends_on") or []) if str(d) in id_map]
            item.depends_on = deps
        return created
