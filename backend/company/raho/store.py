"""RAHO 會話與質詢樹儲存（記憶體，重啟即清空）。"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.company.raho.protocol import RahoLayer

_MAX_SESSIONS = 80
_MAX_TREES = 40
_MAX_PENDING = 40


@dataclass
class GrillNode:
    node_id: str
    from_layer: int
    to_layer: int
    kind: str  # user_grill | mgp | escalate | resolve | timeout | user_decide
    status: str  # open | resolved | escalated | timeout | blocked
    summary: str
    created_at: float
    resolved_at: float | None = None
    parent_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "from_layer": self.from_layer,
            "to_layer": self.to_layer,
            "kind": self.kind,
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
            "layer_label": f"L{self.layer}",
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
    ) -> GrillNode:
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
        return {
            "trees": trees,
            "pending_decisions": pending,
            "blocked": blocked,
            "user_sessions": len(self.user_sessions),
        }


STORE = RahoStore()
