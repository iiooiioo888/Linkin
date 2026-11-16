"""任務分析器授權矩陣。

權限是 role × resource × action，預設拒絕。角色只有
requester、analyst、approver、admin。

跨租戶一律拒絕，admin 也不例外。admin 的特權只存在於自己的 tenant_id：
同租戶內每個 resource × action 都允許。

本模組只回答「這格能不能做」，不載入 Schema、不執行規則、不轉移狀態。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_ID_RE = re.compile(r"[A-Za-z0-9._@-]{1,96}")

REASON_ALLOW = "allow"
REASON_CROSS_TENANT = "cross_tenant"
REASON_FORBIDDEN = "forbidden"
REASON_INVALID_TENANT = "invalid_tenant"
REASON_UNKNOWN_RESOURCE = "unknown_resource"
REASON_UNKNOWN_ACTION = "unknown_action"


class Role(str, Enum):
    REQUESTER = "requester"
    ANALYST = "analyst"
    APPROVER = "approver"
    ADMIN = "admin"


class Resource(str, Enum):
    CONFIG = "config"
    ANALYSIS = "analysis"
    QUESTION = "question"
    REPORT = "report"
    AUDIT = "audit"


class Action(str, Enum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    ANSWER = "answer"
    APPROVE = "approve"
    APPEND = "append"


# 非 admin 的允許格。未列出的組合一律拒絕。
# requester 提出分析並回答提問；analyst 分析、發問、撰寫報告；
# approver 核准報告並讀取審計。三者都可讀同租戶設定，只有 admin 可改。
_ROLE_GRANTS: frozenset[tuple[Role, Resource, Action]] = frozenset(
    {
        (Role.REQUESTER, Resource.CONFIG, Action.READ),
        (Role.REQUESTER, Resource.ANALYSIS, Action.CREATE),
        (Role.REQUESTER, Resource.ANALYSIS, Action.READ),
        (Role.REQUESTER, Resource.QUESTION, Action.READ),
        (Role.REQUESTER, Resource.QUESTION, Action.ANSWER),
        (Role.REQUESTER, Resource.REPORT, Action.READ),
        (Role.ANALYST, Resource.CONFIG, Action.READ),
        (Role.ANALYST, Resource.ANALYSIS, Action.READ),
        (Role.ANALYST, Resource.ANALYSIS, Action.UPDATE),
        (Role.ANALYST, Resource.QUESTION, Action.CREATE),
        (Role.ANALYST, Resource.QUESTION, Action.READ),
        (Role.ANALYST, Resource.REPORT, Action.CREATE),
        (Role.ANALYST, Resource.REPORT, Action.READ),
        (Role.APPROVER, Resource.CONFIG, Action.READ),
        (Role.APPROVER, Resource.ANALYSIS, Action.READ),
        (Role.APPROVER, Resource.QUESTION, Action.READ),
        (Role.APPROVER, Resource.REPORT, Action.READ),
        (Role.APPROVER, Resource.REPORT, Action.APPROVE),
        (Role.APPROVER, Resource.AUDIT, Action.READ),
    }
)

_ADMIN_GRANTS: frozenset[tuple[Role, Resource, Action]] = frozenset(
    (Role.ADMIN, resource, action) for resource in Resource for action in Action
)

GRANTS: frozenset[tuple[Role, Resource, Action]] = _ROLE_GRANTS | _ADMIN_GRANTS


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} 必須是字串")
    text = value.strip()
    if _ID_RE.fullmatch(text) is None:
        raise ValueError(f"{field} 無效")
    return text


def _parse_role(value: object) -> Role:
    if isinstance(value, Role):
        return value
    if isinstance(value, str):
        try:
            return Role(value.strip())
        except ValueError:
            pass
    raise ValueError("角色必須是 requester、analyst、approver 或 admin")


@dataclass(frozen=True, slots=True)
class Actor:
    """已驗證的租戶內行動者。"""

    actor_id: str
    tenant_id: str
    role: Role | str

    def __post_init__(self) -> None:
        actor_id = _identifier(self.actor_id, "actor_id")
        tenant_id = _identifier(self.tenant_id, "tenant_id")
        role = _parse_role(self.role)
        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "role", role)


@dataclass(frozen=True, slots=True)
class AuthzDecision:
    """一次矩陣查詢的結果。allowed 為真時 reason 一定是 allow。"""

    allowed: bool
    reason: str
    role: str
    resource: str
    action: str
    tenant_id: str


def _decision(
    *,
    allowed: bool,
    reason: str,
    role: str,
    resource: str,
    action: str,
    tenant_id: str,
) -> AuthzDecision:
    return AuthzDecision(
        allowed=allowed,
        reason=reason,
        role=role,
        resource=resource,
        action=action,
        tenant_id=tenant_id,
    )


def _label(value: Resource | Action | str) -> str:
    if isinstance(value, (Resource, Action)):
        return value.value
    if isinstance(value, str):
        return value.strip()
    raise TypeError("resource 與 action 必須是列舉或字串")


def _parse_resource(value: Resource | str) -> Resource | None:
    if isinstance(value, Resource):
        return value
    try:
        return Resource(value.strip())
    except ValueError:
        return None


def _parse_action(value: Action | str) -> Action | None:
    if isinstance(value, Action):
        return value
    try:
        return Action(value.strip())
    except ValueError:
        return None


def authorize(
    actor: Actor,
    *,
    tenant_id: str,
    resource: Resource | str,
    action: Action | str,
) -> AuthzDecision:
    """先看租戶，再看矩陣。跨租戶在資源名稱是否存在之前就拒絕。"""
    if not isinstance(actor, Actor):
        raise TypeError("actor 必須是 Actor")
    role = actor.role
    if not isinstance(role, Role):
        raise TypeError("actor.role 必須是 Role")
    if not isinstance(tenant_id, str):
        raise TypeError("tenant_id 必須是字串")
    resource_label = _label(resource)
    action_label = _label(action)
    target = tenant_id.strip()
    if not target:
        return _decision(
            allowed=False,
            reason=REASON_INVALID_TENANT,
            role=role.value,
            resource=resource_label,
            action=action_label,
            tenant_id=target,
        )
    if actor.tenant_id != target:
        return _decision(
            allowed=False,
            reason=REASON_CROSS_TENANT,
            role=role.value,
            resource=resource_label,
            action=action_label,
            tenant_id=target,
        )
    parsed_resource = _parse_resource(resource)
    if parsed_resource is None:
        return _decision(
            allowed=False,
            reason=REASON_UNKNOWN_RESOURCE,
            role=role.value,
            resource=resource_label,
            action=action_label,
            tenant_id=target,
        )
    parsed_action = _parse_action(action)
    if parsed_action is None:
        return _decision(
            allowed=False,
            reason=REASON_UNKNOWN_ACTION,
            role=role.value,
            resource=parsed_resource.value,
            action=action_label,
            tenant_id=target,
        )
    allowed = (role, parsed_resource, parsed_action) in GRANTS
    return _decision(
        allowed=allowed,
        reason=REASON_ALLOW if allowed else REASON_FORBIDDEN,
        role=role.value,
        resource=parsed_resource.value,
        action=parsed_action.value,
        tenant_id=target,
    )


def grants() -> frozenset[tuple[str, str, str]]:
    """回傳全部允許格：(role, resource, action)。"""
    return frozenset(
        (role.value, resource.value, action.value) for role, resource, action in GRANTS
    )


def permission_message(decision: AuthzDecision) -> str:
    if decision.reason == REASON_CROSS_TENANT:
        return "跨租戶拒絕"
    if decision.reason == REASON_INVALID_TENANT:
        return "租戶無效"
    if decision.reason == REASON_UNKNOWN_RESOURCE:
        return "未知資源"
    if decision.reason == REASON_UNKNOWN_ACTION:
        return "未知動作"
    if decision.reason == REASON_ALLOW:
        return "允許"
    return "角色無權限"
