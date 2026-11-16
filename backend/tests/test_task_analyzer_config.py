"""任務分析器設定、權限矩陣與只追加審計。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread

import pytest

from backend.task_analyzer import audit as audit_mod
from backend.task_analyzer import authz as authz_mod
from backend.task_analyzer import config as config_mod
from backend.task_analyzer.audit import AuditEvent, AuditLog, AuditLogError
from backend.task_analyzer.authz import (
    REASON_ALLOW,
    REASON_CROSS_TENANT,
    REASON_FORBIDDEN,
    REASON_INVALID_TENANT,
    REASON_UNKNOWN_ACTION,
    REASON_UNKNOWN_RESOURCE,
    Action,
    Actor,
    Resource,
    Role,
    authorize,
    grants,
)
from backend.task_analyzer.config import (
    CONFIG_FIELDS,
    CONFIG_UPDATE_ACTION,
    ConfigError,
    ConfigStore,
    Priority,
    RedlineUnknownPolicy,
    default_config,
)

_STAMP = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
_NON_ADMIN_GRANTS = {
    ("requester", "config", "read"),
    ("requester", "analysis", "create"),
    ("requester", "analysis", "read"),
    ("requester", "question", "read"),
    ("requester", "question", "answer"),
    ("requester", "report", "read"),
    ("analyst", "config", "read"),
    ("analyst", "analysis", "read"),
    ("analyst", "analysis", "update"),
    ("analyst", "question", "create"),
    ("analyst", "question", "read"),
    ("analyst", "report", "create"),
    ("analyst", "report", "read"),
    ("approver", "config", "read"),
    ("approver", "analysis", "read"),
    ("approver", "question", "read"),
    ("approver", "report", "read"),
    ("approver", "report", "approve"),
    ("approver", "audit", "read"),
}
_IMPORT_ROOTS = {
    "__future__", "backend", "collections", "dataclasses", "datetime",
    "enum", "math", "re", "threading", "types",
}


def _actor(role: Role | str, tenant: str = "acme", actor_id: str = "ada") -> Actor:
    return Actor(actor_id, tenant, role)


def _event(
    *,
    tenant_id: str = "acme",
    actor_id: str = "ada",
    action: str = "config.update",
    from_state: str = "3",
    to_state: str = "4",
    rule_id: str = "max_question_rounds",
    at: datetime = _STAMP,
) -> AuditEvent:
    return AuditEvent(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        from_state=from_state,
        to_state=to_state,
        rule_id=rule_id,
        at=at,
    )


@pytest.fixture
def audit() -> AuditLog:
    return AuditLog()


@pytest.fixture
def store(audit: AuditLog) -> ConfigStore:
    return ConfigStore(audit, clock=lambda: _STAMP)


def test_defaults_match_product_contract():
    cfg = default_config()
    assert cfg.to_dict() == {
        "max_question_rounds": 3,
        "max_questions_per_round": 5,
        "question_timeout_hours": 24,
        "discovery_timeout_sec": 60,
        "budget_sensitivity_threshold": 0.2,
        "redline_unknown_policy": "ask_user",
        "default_priority": "P2",
        "report_schema_version": "v0.1",
    }
    assert cfg.redline_unknown_policy is RedlineUnknownPolicy.ASK_USER
    assert cfg.default_priority is Priority.P2
    assert CONFIG_FIELDS == tuple(cfg.to_dict())
    assert default_config() == cfg
    assert default_config() is not cfg


def test_direct_config_rejects_invalid_values():
    with pytest.raises(ConfigError, match="max_question_rounds"):
        config_mod.TaskAnalyzerConfig(max_question_rounds=True)  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="report_schema_version"):
        config_mod.TaskAnalyzerConfig(report_schema_version="schema-master")


def test_tenant_override_is_isolated(store: ConfigStore, audit: AuditLog):
    admin_a = _actor(Role.ADMIN, "tenant-a", "ann")
    admin_b = _actor(Role.ADMIN, "tenant-b", "ben")
    updated = store.update(admin_a, {"max_question_rounds": 4, "default_priority": "P0"})
    assert updated.max_question_rounds == 4
    assert updated.default_priority is Priority.P0
    assert store.get(admin_b) == default_config()
    assert store.overrides(admin_a) == {"max_question_rounds": 4, "default_priority": "P0"}
    assert store.overrides(admin_b) == {}
    assert audit.read("tenant-b") == ()
    assert [event.rule_id for event in audit.read("tenant-a")] == [
        "max_question_rounds",
        "default_priority",
    ]


def test_change_writes_audit_fields_in_field_order(store: ConfigStore, audit: AuditLog):
    admin = _actor(Role.ADMIN)
    store.update(
        admin,
        {
            "report_schema_version": "v0.2",
            "max_questions_per_round": 6,
            "max_question_rounds": 4,
            "budget_sensitivity_threshold": 0.5,
            "discovery_timeout_sec": 90,
            "question_timeout_hours": 48,
            "redline_unknown_policy": "deny",
            "default_priority": Priority.P0,
        },
    )
    events = audit.read("acme")
    assert [event.rule_id for event in events] == list(CONFIG_FIELDS)
    expected = {
        "max_question_rounds": ("3", "4"),
        "max_questions_per_round": ("5", "6"),
        "question_timeout_hours": ("24", "48"),
        "discovery_timeout_sec": ("60", "90"),
        "budget_sensitivity_threshold": ("0.2", "0.5"),
        "redline_unknown_policy": ("ask_user", "deny"),
        "default_priority": ("P2", "P0"),
        "report_schema_version": ("v0.1", "v0.2"),
    }
    for event in events:
        assert event.to_dict() == {
            "tenant_id": "acme",
            "actor_id": "ada",
            "action": CONFIG_UPDATE_ACTION,
            "from_state": expected[event.rule_id][0],
            "to_state": expected[event.rule_id][1],
            "rule_id": event.rule_id,
            "at": _STAMP.isoformat(),
        }
        assert isinstance(event.from_state, str)
        assert isinstance(event.to_state, str)
        assert event.at == _STAMP


def test_unchanged_value_does_not_emit_audit(store: ConfigStore, audit: AuditLog):
    admin = _actor(Role.ADMIN)
    store.update(admin, {"max_question_rounds": 3, "redline_unknown_policy": "ask_user"})
    assert audit.read("acme") == ()
    assert store.overrides(admin) == {}
    store.update(admin, {"budget_sensitivity_threshold": 0.5})
    store.update(admin, {"budget_sensitivity_threshold": 0.50})
    assert len(audit.read("acme")) == 1


def test_invalid_change_is_atomic(store: ConfigStore, audit: AuditLog):
    admin = _actor(Role.ADMIN)
    with pytest.raises(ConfigError):
        store.update(admin, {"max_question_rounds": 4, "question_timeout_hours": 0})
    assert store.get(admin) == default_config()
    assert audit.read("acme") == ()
    payload = {"max_question_rounds": 6}
    store.update(admin, payload)
    payload["max_question_rounds"] = 1
    assert store.get(admin).max_question_rounds == 6


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_question_rounds", True), ("max_question_rounds", -1),
        ("max_question_rounds", 3.0), ("max_question_rounds", "3"),
        ("max_question_rounds", 10_001), ("max_questions_per_round", -1),
        ("question_timeout_hours", 0), ("question_timeout_hours", 366 * 24 + 1),
        ("discovery_timeout_sec", 0), ("discovery_timeout_sec", 86_401),
        ("budget_sensitivity_threshold", True), ("budget_sensitivity_threshold", -0.01),
        ("budget_sensitivity_threshold", 1.01), ("budget_sensitivity_threshold", float("nan")),
        ("redline_unknown_policy", "ASK_USER"), ("redline_unknown_policy", "ask-user"),
        ("default_priority", "p2"), ("default_priority", "P4"),
        ("report_schema_version", "0.1"), ("report_schema_version", "V0.1"),
        ("report_schema_version", "v0.1.0"), ("report_schema_version", "v01.1"),
        ("state", "running"), ("rule", "always"), ("schema", "master"),
    ],
)
def test_invalid_override_rejected(store: ConfigStore, audit: AuditLog, field: str, value: object):
    admin = _actor(Role.ADMIN)
    with pytest.raises(ConfigError):
        store.update(admin, {field: value})
    assert store.get(admin) == default_config()
    assert audit.read("acme") == ()


def test_boundary_values_round_trip(store: ConfigStore):
    admin = _actor(Role.ADMIN)
    store.update(
        admin,
        {
            "max_question_rounds": 0,
            "max_questions_per_round": 10_000,
            "question_timeout_hours": 1,
            "discovery_timeout_sec": 86_400,
            "budget_sensitivity_threshold": 0,
        },
    )
    cfg = store.get(admin)
    assert cfg.max_question_rounds == 0
    assert cfg.max_questions_per_round == 10_000
    assert cfg.question_timeout_hours == 1
    assert cfg.discovery_timeout_sec == 86_400
    assert cfg.budget_sensitivity_threshold == 0.0
    store.update(admin, {"budget_sensitivity_threshold": 1, "question_timeout_hours": 366 * 24})
    again = store.get(admin)
    assert again.budget_sensitivity_threshold == 1.0
    assert again.question_timeout_hours == 366 * 24


def test_reset_returns_to_default_and_audits(store: ConfigStore, audit: AuditLog):
    admin = _actor(Role.ADMIN)
    store.update(admin, {"max_question_rounds": 8, "default_priority": "P1"})
    store.reset(admin, ["max_question_rounds"])
    cfg = store.get(admin)
    assert cfg.max_question_rounds == 3
    assert cfg.default_priority is Priority.P1
    assert store.overrides(admin) == {"default_priority": "P1"}
    reset_event = audit.read("acme")[-1]
    assert reset_event.rule_id == "max_question_rounds"
    assert reset_event.from_state == "8"
    assert reset_event.to_state == "3"
    store.reset(admin, ["max_question_rounds"])
    assert len(audit.read("acme")) == 3


def test_callers_without_update_do_not_change_or_audit(store: ConfigStore, audit: AuditLog):
    admin = _actor(Role.ADMIN)
    analyst = _actor(Role.ANALYST, actor_id="lee")
    approver = _actor(Role.APPROVER, actor_id="pat")
    requester = _actor(Role.REQUESTER, actor_id="rae")
    assert store.get(requester) == default_config()
    for actor in (analyst, approver, requester):
        with pytest.raises(PermissionError, match="角色無權限"):
            store.update(actor, {"max_question_rounds": 9})
    assert store.get(admin) == default_config()
    assert audit.read("acme") == ()
    with pytest.raises(PermissionError, match="角色無權限"):
        store.read_audit(analyst)
    store.update(admin, {"discovery_timeout_sec": 30})
    visible = store.read_audit(approver)
    assert len(visible) == 1
    assert visible[0].actor_id == "ada"
    with pytest.raises(PermissionError, match="角色無權限"):
        store.read_audit(requester)


def test_cross_tenant_config_access_is_denied(store: ConfigStore, audit: AuditLog):
    admin_a = _actor(Role.ADMIN, "tenant-a", "ann")
    admin_b = _actor(Role.ADMIN, "tenant-b", "ben")
    store.update(admin_a, {"max_question_rounds": 7})
    for call in (
        lambda: store.get(admin_a, tenant_id="tenant-b"),
        lambda: store.update(admin_a, {"max_question_rounds": 2}, tenant_id="tenant-b"),
        lambda: store.reset(admin_a, ["schema"], tenant_id="tenant-b"),
        lambda: store.overrides(admin_b, tenant_id="tenant-a"),
        lambda: store.read_audit(admin_b, tenant_id="tenant-a"),
    ):
        with pytest.raises(PermissionError, match="跨租戶拒絕"):
            call()
    assert store.get(admin_b) == default_config()
    assert store.get(admin_a).max_question_rounds == 7
    assert audit.read("tenant-b") == ()
    assert len(audit.read("tenant-a")) == 1


def test_blank_tenant_and_empty_change_are_rejected(store: ConfigStore):
    admin = _actor(Role.ADMIN)
    with pytest.raises(PermissionError, match="租戶無效"):
        store.update(admin, {"max_question_rounds": 4}, tenant_id="  ")
    with pytest.raises(ConfigError, match="變更不可為空"):
        store.update(admin, {})
    with pytest.raises(TypeError):
        store.update(admin, "max_question_rounds")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        store.reset(admin, "max_question_rounds")  # type: ignore[arg-type]
    with pytest.raises(PermissionError, match="跨租戶拒絕"):
        store.reset(admin, [], tenant_id="other")


def test_naive_clock_does_not_commit(audit: AuditLog):
    admin = _actor(Role.ADMIN)
    store = ConfigStore(audit, clock=lambda: datetime(2026, 11, 16, 0, 0))
    with pytest.raises(ValueError, match="at 必須是有時區的 datetime"):
        store.update(admin, {"max_question_rounds": 4})
    assert audit.read("acme") == ()
    assert store.get(admin) == default_config()


def test_concurrent_updates_keep_both_fields(store: ConfigStore, audit: AuditLog):
    admin = _actor(Role.ADMIN)
    errors: list[BaseException] = []

    def set_rounds() -> None:
        try:
            store.update(admin, {"max_question_rounds": 8})
        except Exception as exc:
            errors.append(exc)

    def set_questions() -> None:
        try:
            store.update(admin, {"max_questions_per_round": 9})
        except Exception as exc:
            errors.append(exc)

    first = Thread(target=set_rounds)
    second = Thread(target=set_questions)
    first.start()
    second.start()
    first.join()
    second.join()
    assert errors == []
    cfg = store.get(admin)
    assert cfg.max_question_rounds == 8
    assert cfg.max_questions_per_round == 9
    assert {event.rule_id for event in audit.read("acme")} == {
        "max_question_rounds",
        "max_questions_per_round",
    }


def test_config_object_and_store_reject_tampering(store: ConfigStore):
    admin = _actor(Role.ADMIN)
    cfg = store.get(admin)
    with pytest.raises(FrozenInstanceError):
        cfg.max_question_rounds = 1  # type: ignore[misc]
    with pytest.raises(ConfigError, match="update 或 reset"):
        store._overrides = {}  # type: ignore[misc]
    with pytest.raises(ConfigError, match="update 或 reset"):
        del store._lock  # type: ignore[misc]


def test_audit_fields_and_append_only():
    names = [field.name for field in fields(AuditEvent)]
    assert names == [
        "tenant_id",
        "actor_id",
        "action",
        "from_state",
        "to_state",
        "rule_id",
        "at",
    ]
    shifted = datetime(2026, 11, 16, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    event = _event(at=shifted, tenant_id="  acme  ")
    assert event.at == _STAMP
    assert event.tenant_id == "acme"
    with pytest.raises(FrozenInstanceError):
        event.action = "tamper"  # type: ignore[misc]
    with pytest.raises(ValueError, match="at 必須是有時區的 datetime"):
        _event(at=datetime(2026, 11, 16))
    log = AuditLog()
    assert not hasattr(log, "update")
    assert not hasattr(log, "delete")
    assert not hasattr(log, "clear")
    stored = log.append(event)
    assert stored is event
    snapshot = log.read("acme")
    assert isinstance(snapshot, tuple)
    assert snapshot[0] is event
    extra = _event(rule_id="default_priority", from_state="P2", to_state="P1")
    with pytest.raises(TypeError):
        log.append_many((extra, "nope"))  # type: ignore[arg-type]
    assert log.read("acme") == snapshot
    log.append(extra)
    again = log.read("acme")
    assert again[0] is snapshot[0]
    assert again[0].action == "config.update"
    assert len(again) == 2
    assert log.read("other-tenant") == ()
    with pytest.raises(AuditLogError, match="只允許追加"):
        log._events = ()  # type: ignore[misc]
    with pytest.raises(AuditLogError, match="只允許追加"):
        del log._lock  # type: ignore[misc]
    with pytest.raises(AttributeError):
        snapshot.append(extra)  # type: ignore[attr-defined]
    assert log.read("acme") == again


def test_append_many_is_all_or_nothing_and_rejects_a_single_event():
    log = AuditLog()
    first = _event()
    second = _event(rule_id="default_priority", from_state="P2", to_state="P0")
    log.append_many(())
    assert log.read("acme") == ()
    log.append_many((first, second))
    assert [event.rule_id for event in log.read("acme")] == [
        "max_question_rounds",
        "default_priority",
    ]
    with pytest.raises(TypeError):
        log.append_many(first)  # type: ignore[arg-type]
    assert len(log.read("acme")) == 2


def test_permission_vocabulary_and_matrix():
    assert {role.value for role in Role} == {"requester", "analyst", "approver", "admin"}
    assert {item.value for item in Resource} == {
        "config", "analysis", "question", "report", "audit",
    }
    assert {item.value for item in Action} == {
        "read", "create", "update", "answer", "approve", "append",
    }
    expected = set(_NON_ADMIN_GRANTS)
    for resource in Resource:
        for action in Action:
            expected.add(("admin", resource.value, action.value))
    assert grants() == expected
    for role in (Role.REQUESTER, Role.ANALYST, Role.APPROVER):
        actor = _actor(role, actor_id=role.value)
        for resource in Resource:
            for action in Action:
                decision = authorize(
                    actor,
                    tenant_id=actor.tenant_id,
                    resource=resource,
                    action=action,
                )
                cell = (role.value, resource.value, action.value)
                assert decision.allowed is (cell in _NON_ADMIN_GRANTS)
                assert decision.reason == (REASON_ALLOW if decision.allowed else REASON_FORBIDDEN)
                assert decision.tenant_id == "acme"


def test_admin_cells_allow_only_inside_tenant():
    admin = _actor(Role.ADMIN)
    for resource in Resource:
        for action in Action:
            allowed = authorize(admin, tenant_id="acme", resource=resource, action=action)
            denied = authorize(admin, tenant_id="other", resource=resource, action=action)
            assert allowed.allowed is True
            assert allowed.reason == REASON_ALLOW
            assert denied.allowed is False
            assert denied.reason == REASON_CROSS_TENANT


def test_cross_tenant_beats_unknown_names_and_blank_tenant_is_invalid():
    admin = _actor(" admin ", " acme ")
    assert admin.role is Role.ADMIN
    assert admin.tenant_id == "acme"
    cross = authorize(admin, tenant_id="other", resource="schema", action="execute")
    assert cross.allowed is False
    assert cross.reason == REASON_CROSS_TENANT
    unknown_resource = authorize(admin, tenant_id=" acme ", resource="schema", action=Action.READ)
    assert unknown_resource.reason == REASON_UNKNOWN_RESOURCE
    unknown_action = authorize(admin, tenant_id="acme", resource=" config ", action="execute")
    assert unknown_action.reason == REASON_UNKNOWN_ACTION
    blank = authorize(admin, tenant_id="  ", resource=Resource.CONFIG, action=Action.UPDATE)
    assert blank.reason == REASON_INVALID_TENANT
    assert blank.allowed is False
    for role in Role:
        decision = authorize(
            _actor(role, "tenant-a", role.value),
            tenant_id="tenant-b",
            resource=Resource.CONFIG,
            action=Action.READ,
        )
        assert decision.reason == REASON_CROSS_TENANT
    with pytest.raises(ValueError, match="角色"):
        _actor("wizard")
    with pytest.raises(ValueError, match="tenant_id"):
        _actor(Role.ADMIN, tenant=" ")
    with pytest.raises(TypeError):
        authorize(
            "ada",  # type: ignore[arg-type]
            tenant_id="acme",
            resource=Resource.CONFIG,
            action=Action.READ,
        )


def test_package_files_stay_within_the_three_models():
    root = Path(config_mod.__file__).resolve().parent
    names = sorted(path.name for path in root.glob("*.py"))
    # #179–#181 的 schema、規則與狀態機與此三模型同套件，清單必須含它們，不得刪檔。
    assert names == [
        "__init__.py",
        "audit.py",
        "authz.py",
        "config.py",
        "enums.py",
        "errors.py",
        "rules.py",
        "schema.py",
        "state_machine.py",
        "validate.py",
    ]
    banned = ("task_state_machine", "schema_registry", "rule_engine")
    for path in (root / name for name in ("audit.py", "authz.py", "config.py")):
        text = path.read_text(encoding="utf-8")
        for needle in banned:
            assert needle not in text
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                root_name = stripped.split()[1].split(".")[0]
            else:
                continue
            assert root_name in _IMPORT_ROOTS
    for module in (audit_mod, authz_mod, config_mod):
        assert not hasattr(module, "RuleEngine")
        assert not hasattr(module, "SchemaRegistry")
        assert not hasattr(module, "TaskRuntimeState")
        assert not hasattr(module, "transition")
