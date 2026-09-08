"""RAHO 會話與質詢樹儲存（記憶體，重啟即清空）。"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.company.raho.protocol import (
    KIND_LABELS,
    RahoLayer,
    annotate_edge,
    kind_label,
    layer_label,
    raho_directory,
    raho_identity,
)

_MAX_SESSIONS = 80
_MAX_TREES = 40
_MAX_PENDING = 40


@dataclass
class GrillNode:
    node_id: str
    from_layer: int
    to_layer: int
    kind: str  # user_grill | mgp | escalate | resolve | timeout | user_decide | inspect | campaign
    status: str  # open | resolved | escalated | timeout | blocked
    summary: str
    created_at: float
    resolved_at: float | None = None
    parent_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    from_role: str = ""
    to_role: str = ""
    from_label: str = ""
    to_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        edge = annotate_edge(
            self.from_layer,
            self.to_layer,
            from_role=self.from_role,
            to_role=self.to_role,
        )
        return {
            "node_id": self.node_id,
            "from_layer": self.from_layer,
            "to_layer": self.to_layer,
            "from_role": edge["from_role"],
            "to_role": edge["to_role"],
            "from_label": self.from_label or edge["from_label"],
            "to_label": self.to_label or edge["to_label"],
            "from_short": edge["from_short"],
            "to_short": edge["to_short"],
            "kind": self.kind,
            "kind_label": kind_label(self.kind),
            "status": self.status,
            "summary": self.summary,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "parent_id": self.parent_id,
            "payload": self.payload,
            "blocked": self.status in {"open", "blocked"},
        }


@dataclass
class GrillTree:
    tree_id: str
    run_id: str
    goal: str
    nodes: list[GrillNode] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    campaign: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        open_nodes = [n for n in self.nodes if n.status in {"open", "blocked"}]
        return {
            "tree_id": self.tree_id,
            "run_id": self.run_id,
            "goal": self.goal,
            "created_at": self.created_at,
            "nodes": [n.to_dict() for n in self.nodes],
            "open_count": len(open_nodes),
            "blocked": [n.to_dict() for n in open_nodes],
            "campaign": self.campaign,
        }


@dataclass
class UserGrillSession:
    session_id: str
    query: str
    turns: list[dict[str, str]] = field(default_factory=list)
    confidence: float = 0.0
    locked: bool = False
    brief: str = ""
    created_at: float = field(default_factory=time.time)
    phase: int = 1
    phase_rounds: int = 0
    scores: dict[str, float] = field(default_factory=dict)
    last_user_text: str = ""
    repeat_count: int = 0
    terminated: bool = False
    termination_reason: str = ""
    ticket: dict[str, Any] | None = None
    asked_ids: list[int] = field(default_factory=list)
    user_rounds: int = 0
    planner: dict[str, Any] | None = None


@dataclass
class PendingDecision:
    decision_id: str
    run_id: str
    item_id: str
    layer: int
    question: str
    choices: list[dict[str, Any]]
    created_at: float
    ttl: float
    resolution: dict[str, Any] | None = None
    event: asyncio.Event = field(default_factory=asyncio.Event)

    def expired(self) -> bool:
        return time.time() - self.created_at >= self.ttl

    def to_dict(self) -> dict[str, Any]:
        remaining = max(0.0, self.ttl - (time.time() - self.created_at))
        return {
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "item_id": self.item_id,
            "layer": self.layer,
            "layer_label": layer_label(self.layer),
            "role_id": raho_identity(layer=self.layer)["role_id"],
            "role_label": layer_label(self.layer),
            "question": self.question,
            "choices": self.choices,
            "created_at": self.created_at,
            "ttl": self.ttl,
            "remaining_sec": round(remaining, 1),
            "resolved": self.resolution is not None,
            "resolution": self.resolution,
            "blocked": self.resolution is None and not self.expired(),
        }


class RahoStore:
    """執行緒安全的 RAHO 狀態倉。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.user_sessions: dict[str, UserGrillSession] = {}
        self.trees: dict[str, GrillTree] = {}
        self.pending: dict[str, PendingDecision] = {}
        self.battle_plans: dict[str, dict[str, Any]] = {}
        self.grill_rounds: dict[str, int] = {}
        self.shared_memory: dict[str, dict[str, Any]] = {}
        self.l0_traces: list[dict[str, Any]] = []
        self.l0_prefs: dict[str, str] = {}
        self.l0_entities: dict[str, dict[str, Any]] = {}

    def _trim(self, mapping: dict, limit: int) -> None:
        while len(mapping) > limit:
            mapping.pop(next(iter(mapping)), None)

    def new_user_session(self, query: str) -> UserGrillSession:
        sid = uuid.uuid4().hex[:12]
        sess = UserGrillSession(session_id=sid, query=query, brief=query)
        with self._lock:
            self.user_sessions[sid] = sess
            self._trim(self.user_sessions, _MAX_SESSIONS)
        return sess

    def get_user_session(self, session_id: str) -> UserGrillSession | None:
        return self.user_sessions.get((session_id or "").strip())

    def drop_user_session(self, session_id: str) -> None:
        with self._lock:
            self.user_sessions.pop(session_id, None)

    def ensure_tree(self, run_id: str, goal: str = "") -> GrillTree:
        with self._lock:
            tree = self.trees.get(run_id)
            if tree is None:
                tree = GrillTree(tree_id=run_id, run_id=run_id, goal=goal)
                self.trees[run_id] = tree
                self._trim(self.trees, _MAX_TREES)
            elif goal and not tree.goal:
                tree.goal = goal
            return tree

    def set_campaign(self, run_id: str, campaign: dict[str, Any], goal: str = "") -> None:
        tree = self.ensure_tree(run_id, goal)
        with self._lock:
            tree.campaign = campaign or {}

    def add_node(
        self,
        run_id: str,
        *,
        from_layer: int,
        to_layer: int,
        kind: str,
        summary: str,
        status: str = "open",
        parent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        goal: str = "",
        from_role: str = "",
        to_role: str = "",
    ) -> GrillNode:
        edge = annotate_edge(from_layer, to_layer, from_role=from_role, to_role=to_role)
        node = GrillNode(
            node_id=uuid.uuid4().hex[:10],
            from_layer=from_layer,
            to_layer=to_layer,
            kind=kind,
            status=status,
            summary=summary,
            created_at=time.time(),
            parent_id=parent_id,
            payload=payload or {},
            from_role=edge["from_role"],
            to_role=edge["to_role"],
            from_label=edge["from_label"],
            to_label=edge["to_label"],
        )
        tree = self.ensure_tree(run_id, goal)
        with self._lock:
            tree.nodes.append(node)
        return node

    def resolve_node(self, run_id: str, node_id: str, status: str = "resolved") -> GrillNode | None:
        tree = self.trees.get(run_id)
        if not tree:
            return None
        for node in tree.nodes:
            if node.node_id == node_id:
                node.status = status
                node.resolved_at = time.time()
                return node
        return None

    def get_tree(self, run_id: str) -> GrillTree | None:
        return self.trees.get(run_id)

    def list_trees(self) -> list[GrillTree]:
        return list(self.trees.values())

    def add_pending(self, pending: PendingDecision) -> PendingDecision:
        with self._lock:
            self.pending[pending.decision_id] = pending
            self._trim(self.pending, _MAX_PENDING)
        return pending

    def get_pending(self, decision_id: str) -> PendingDecision | None:
        return self.pending.get(decision_id)

    def list_pending(self, run_id: str | None = None) -> list[PendingDecision]:
        items = list(self.pending.values())
        if run_id:
            items = [p for p in items if p.run_id == run_id]
        return items

    def decide(self, decision_id: str, resolution: dict[str, Any]) -> PendingDecision | None:
        pending = self.pending.get(decision_id)
        if pending is None:
            return None
        pending.resolution = resolution
        pending.event.set()
        return pending

    def put_battle_plan(self, plan_id: str, plan: dict[str, Any]) -> None:
        with self._lock:
            self.battle_plans[plan_id] = plan
            self._trim(self.battle_plans, _MAX_TREES)

    def get_battle_plan(self, plan_id: str) -> dict[str, Any] | None:
        return self.battle_plans.get(plan_id)

    def user_grill_run_id(self, session_id: str) -> str:
        return f"grill:{(session_id or '').strip()}"

    def record_user_grill(
        self,
        session_id: str,
        query: str,
        *,
        summary: str,
        status: str,
        from_layer: int,
        to_layer: int,
        payload: dict[str, Any] | None = None,
    ) -> GrillNode:
        """把 L5↔L4 用戶審計寫進質詢樹，讓監控中心看得到烤問鏈。"""
        return self.add_node(
            self.user_grill_run_id(session_id),
            from_layer=from_layer,
            to_layer=to_layer,
            kind="user_grill",
            summary=summary,
            status=status,
            payload=payload or {},
            goal=query,
        )

    def resolve_user_grill(self, session_id: str, status: str = "resolved") -> None:
        tree = self.trees.get(self.user_grill_run_id(session_id))
        if not tree:
            return
        now = time.time()
        with self._lock:
            for node in tree.nodes:
                if node.kind == "user_grill" and node.status in {"open", "blocked"}:
                    node.status = status
                    node.resolved_at = now

    def bump_grill_round(self, item_id: str) -> int:
        key = (item_id or "").strip() or "_"
        with self._lock:
            self.grill_rounds[key] = int(self.grill_rounds.get(key) or 0) + 1
            self._trim(self.grill_rounds, _MAX_PENDING * 4)
            return self.grill_rounds[key]

    def grill_round(self, item_id: str) -> int:
        return int(self.grill_rounds.get((item_id or "").strip() or "_") or 0)

    def write_signed(self, node_id: str, record: dict[str, Any]) -> dict[str, Any]:
        key = (node_id or "").strip()
        if not key:
            return record
        with self._lock:
            self.shared_memory[key] = record
            self._trim(self.shared_memory, _MAX_TREES * 4)
        return record

    def read_signed(self, node_id: str) -> dict[str, Any] | None:
        key = (node_id or "").strip()
        if not key:
            return None
        record = self.shared_memory.get(key)
        if not record or not record.get("signed"):
            return None
        return record

    def revoke_signed(self, node_id: str) -> None:
        key = (node_id or "").strip()
        with self._lock:
            record = self.shared_memory.get(key)
            if record:
                record["signed"] = False

    def snapshot(self) -> dict[str, Any]:
        trees = [t.to_dict() for t in self.list_trees()]
        pending = [p.to_dict() for p in self.list_pending() if p.resolution is None]
        blocked = []
        for tree in trees:
            blocked.extend(tree.get("blocked") or [])
        for p in pending:
            if p.get("blocked"):
                blocked.append(
                    {
                        "kind": "user_decide",
                        "status": "blocked",
                        "summary": p.get("question", ""),
                        "from_layer": RahoLayer.L2_EXECUTOR,
                        "to_layer": RahoLayer.L5_USER,
                        **p,
                    }
                )
        payload = {
            "trees": trees,
            "pending_decisions": pending,
            "blocked": blocked,
            "user_sessions": len(self.user_sessions),
            "battle_plans": len(self.battle_plans),
            "signed_memory": sum(1 for r in self.shared_memory.values() if r.get("signed")),
            "directory": raho_directory(),
            "kind_labels": dict(KIND_LABELS),
        }
        try:
            from backend.company.raho.l0 import kernel_snapshot

            payload["l0"] = kernel_snapshot()
        except Exception:  # noqa: BLE001
            payload["l0"] = {"layer": 0, "enabled": False, "traces": [], "knowledge": []}
        return payload


STORE = RahoStore()
