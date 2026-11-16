"""任務分析器原子規則：pass／fail／unknown、unknown 不當通過、硬 fail 短路。"""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from backend.task_analyzer import rules as rules_mod
from backend.task_analyzer.rules import (
    EVALUATION_ORDER,
    HARD_RULE_IDS,
    RULE_CATALOG,
    RULE_IDS,
    SOFT_RULE_IDS,
    counts_as_pass,
    evaluate_rule,
    evaluate_rules,
)

PASSING: dict[str, Any] = {
    "resources": [
        {"id": "fs", "kind": "mcp_server"},
        {"id": "db", "kind": "dataset"},
    ],
    "authorized_resources": [
        {"id": "fs", "kind": "mcp_server"},
        {"id": "git", "kind": "mcp_server"},
    ],
    "irreversible": False,
    "human_confirmed": False,
    "sensitive": False,
    "egress": False,
    "requested_privileges": ["read"],
    "required_privileges": ["read", "write"],
    "compliance_regimes": ["pii"],
    "budget_ceiling": 10,
    "budget_floor": 10,
    "latency": 100,
    "latency_slo": 200,
    "throughput": 50,
    "throughput_slo": 40,
    "takeover_sec": 30,
    "takeover_slo_sec": 60,
    "high_risk": False,
    "automated_decision": True,
}

FAIL_PATCH: dict[str, dict[str, Any]] = {
    "R-SEC-001": {
        "resources": [{"id": "root", "kind": "mcp_server"}],
        "authorized_resources": [{"id": "fs", "kind": "mcp_server"}],
    },
    "R-SEC-002": {"irreversible": True, "human_confirmed": False},
    "R-PRI-001": {"sensitive": True, "egress": True},
    "R-PRI-002": {"requested_privileges": ["admin"], "required_privileges": ["read"]},
    "R-COM-001": {"compliance_regimes": []},
    "R-ETH-001": {"high_risk": True, "automated_decision": True},
    "R-BUD-001": {"budget_ceiling": 11, "budget_floor": 10},
    "R-PER-001": {"latency": 500, "latency_slo": 200},
    "R-EXP-001": {"takeover_sec": 90, "takeover_slo_sec": 60},
}

UNKNOWN_DROP: dict[str, tuple[str, ...]] = {
    "R-SEC-001": ("resources", "authorized_resources"),
    "R-SEC-002": ("irreversible",),
    "R-PRI-001": ("sensitive", "egress"),
    "R-PRI-002": ("requested_privileges", "required_privileges"),
    "R-COM-001": ("compliance_regimes",),
    "R-BUD-001": ("budget_ceiling", "budget_floor"),
    "R-PER-001": ("latency", "latency_slo", "throughput", "throughput_slo"),
    "R-EXP-001": ("takeover_sec", "takeover_slo_sec"),
    "R-ETH-001": ("high_risk", "automated_decision"),
}


def _facts(**overrides: Any) -> dict[str, Any]:
    data = dict(PASSING)
    data.update(overrides)
    return data


def _drop(rule_id: str) -> dict[str, Any]:
    data = dict(PASSING)
    for key in UNKNOWN_DROP[rule_id]:
        data.pop(key)
    return data


def _status(report: Mapping[str, Any], rule_id: str) -> str:
    for item in report["results"]:
        if item["id"] == rule_id:
            return str(item["status"])
    raise AssertionError(rule_id)


def test_catalog_ids_titles_and_hardness_are_fixed() -> None:
    """規則編號、中文名與硬軟劃分鎖死，不隨呼叫改變。"""

    assert RULE_IDS == (
        "R-SEC-001",
        "R-SEC-002",
        "R-PRI-001",
        "R-PRI-002",
        "R-COM-001",
        "R-BUD-001",
        "R-PER-001",
        "R-EXP-001",
        "R-ETH-001",
    )
    assert [item[1] for item in RULE_CATALOG] == [
        "越權 MCP",
        "不可逆需人工",
        "敏感且出域",
        "最小權限",
        "合規標籤",
        "上限≤底線",
        "延遲吞吐",
        "接管時間",
        "高風險自動決策",
    ]
    assert HARD_RULE_IDS == (
        "R-SEC-001",
        "R-SEC-002",
        "R-PRI-001",
        "R-PRI-002",
        "R-COM-001",
        "R-ETH-001",
    )
    assert SOFT_RULE_IDS == ("R-BUD-001", "R-PER-001", "R-EXP-001")
    assert EVALUATION_ORDER == HARD_RULE_IDS + SOFT_RULE_IDS
    assert set(rules_mod.DISPATCH) == set(RULE_IDS)


def test_counts_as_pass_rejects_unknown_and_anything_else() -> None:
    assert counts_as_pass("pass") is True
    assert counts_as_pass("unknown") is False
    assert counts_as_pass("fail") is False
    assert counts_as_pass("skipped") is False
    assert counts_as_pass("") is False


def test_all_pass_keeps_hard_rules_before_soft_rules() -> None:
    report = evaluate_rules(PASSING)
    assert report["schema_version"] == "v0.1"
    assert report["passed"] is True
    assert report["short_circuited"] is False
    assert report["hard_failed_rule_id"] is None
    assert report["skipped_rule_ids"] == []
    assert [item["id"] for item in report["results"]] == list(EVALUATION_ORDER)
    assert {item["status"] for item in report["results"]} == {"pass"}
    assert [item["hard_or_soft"] for item in report["results"]] == ["hard"] * 6 + ["soft"] * 3
    assert [item["category"] for item in report["results"]] == [
        "safety",
        "safety",
        "privacy",
        "privacy",
        "compliance",
        "ethics",
        "budget",
        "performance",
        "experience",
    ]


def test_empty_facts_are_unknown_and_not_pass() -> None:
    report = evaluate_rules({})
    assert report["passed"] is False
    assert report["short_circuited"] is False
    assert [item["status"] for item in report["results"]] == ["unknown"] * 9
    assert all(item["evidence"].endswith("_unknown") for item in report["results"])


def test_none_values_match_missing_keys() -> None:
    blank = {key: None for key in PASSING}
    assert evaluate_rules(blank)["results"] == evaluate_rules({})["results"]


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_each_rule_fail_is_not_pass(rule_id: str) -> None:
    report = evaluate_rules(_facts(**FAIL_PATCH[rule_id]))
    assert _status(report, rule_id) == "fail"
    assert report["passed"] is False
    if rule_id in HARD_RULE_IDS:
        assert report["short_circuited"] is True
        assert report["hard_failed_rule_id"] == rule_id
    else:
        assert report["short_circuited"] is False
        assert report["skipped_rule_ids"] == []


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_each_rule_unknown_is_not_pass_and_does_not_short_circuit(rule_id: str) -> None:
    report = evaluate_rules(_drop(rule_id))
    assert _status(report, rule_id) == "unknown"
    assert report["passed"] is False
    assert report["short_circuited"] is False
    assert report["skipped_rule_ids"] == []
    assert len(report["results"]) == 9


@pytest.mark.parametrize("rule_id", HARD_RULE_IDS)
def test_hard_fail_skips_later_rules(rule_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """硬 fail 之後的規則函式不得被呼叫。"""

    later = list(EVALUATION_ORDER[EVALUATION_ORDER.index(rule_id) + 1 :])
    called: list[str] = []

    def _spy(rule: str):
        def _run(_facts: Mapping[str, Any]) -> tuple[str, str]:
            called.append(rule)
            return "pass", "should-not-run"

        return _run

    for later_id in later:
        monkeypatch.setitem(rules_mod.DISPATCH, later_id, _spy(later_id))

    report = evaluate_rules(_facts(**FAIL_PATCH[rule_id]))
    assert called == []
    assert report["skipped_rule_ids"] == later
    assert [item["id"] for item in report["results"]] == list(
        EVALUATION_ORDER[: EVALUATION_ORDER.index(rule_id) + 1]
    )
    assert report["results"][-1]["status"] == "fail"
    assert "skipped" not in {item["status"] for item in report["results"]}


def test_soft_fail_still_runs_remaining_soft_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def _wrap(rule_id: str, original: Any) -> Any:
        def _run(facts: Mapping[str, Any]) -> tuple[str, str]:
            called.append(rule_id)
            return original(facts)

        return _run

    for rule_id in ("R-PER-001", "R-EXP-001"):
        monkeypatch.setitem(
            rules_mod.DISPATCH,
            rule_id,
            _wrap(rule_id, rules_mod.DISPATCH[rule_id]),
        )

    report = evaluate_rules(_facts(**FAIL_PATCH["R-BUD-001"]))
    assert called == ["R-PER-001", "R-EXP-001"]
    assert _status(report, "R-BUD-001") == "fail"
    assert _status(report, "R-PER-001") == "pass"
    assert _status(report, "R-EXP-001") == "pass"
    assert report["short_circuited"] is False
    assert report["passed"] is False


def test_monkeypatched_unknown_cannot_become_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unknown(_facts: Mapping[str, Any]) -> tuple[str, str]:
        return "unknown", "forced"

    monkeypatch.setitem(rules_mod.DISPATCH, "R-COM-001", _unknown)
    report = evaluate_rules(PASSING)
    assert _status(report, "R-COM-001") == "unknown"
    assert evaluate_rule("R-COM-001", PASSING)["evidence"] == "forced"
    assert report["passed"] is False
    assert report["short_circuited"] is False


def test_monkeypatched_invalid_status_becomes_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def _bogus(_facts: Mapping[str, Any]) -> tuple[str, str]:
        return "skipped", "nope"

    monkeypatch.setitem(rules_mod.DISPATCH, "R-EXP-001", _bogus)
    verdict = evaluate_rule("R-EXP-001", PASSING)
    assert verdict["status"] == "unknown"
    assert verdict["evidence"] == "invalid_status"
    assert counts_as_pass(verdict["status"]) is False
    assert evaluate_rules(PASSING)["passed"] is False


def test_first_hard_fail_stops_before_later_hard_fail() -> None:
    facts = _facts(**FAIL_PATCH["R-SEC-001"], **FAIL_PATCH["R-ETH-001"])
    report = evaluate_rules(facts)
    assert report["hard_failed_rule_id"] == "R-SEC-001"
    assert "R-ETH-001" in report["skipped_rule_ids"]
    assert all(item["id"] != "R-ETH-001" for item in report["results"])


def _mcp(resource_id: str, kind: str = "mcp_server") -> dict[str, str]:
    return {"id": resource_id, "kind": kind}


@pytest.mark.parametrize(
    ("overrides", "evidence"),
    [
        ({"resources": []}, "mcp_not_requested"),
        ({"resources": [_mcp("db", "dataset")]}, "mcp_not_requested"),
        ({"resources": [_mcp("git"), _mcp("fs")]}, "mcp_authorized"),
        ({"resources": [_mcp("git"), _mcp("fs"), _mcp("root")]}, "unauthorized_mcp"),
        ({"resources": [_mcp("fs")], "authorized_resources": None}, "mcp_unknown"),
        ({"resources": "fs"}, "mcp_unknown"),
        ({"resources": [1]}, "mcp_unknown"),
        ({"resources": [{"kind": "mcp_server"}]}, "mcp_unknown"),
        ({"resources": [_mcp("x", "widget")]}, "mcp_unknown"),
        ({"resources": [{"kind": "dataset"}]}, "mcp_unknown"),
    ],
)
def test_sec_001_mcp(overrides: dict[str, Any], evidence: str) -> None:
    verdict = evaluate_rule("R-SEC-001", _facts(**overrides))
    assert verdict["title"] == "越權 MCP"
    assert verdict["category"] == "safety"
    assert verdict["hard_or_soft"] == "hard"
    assert verdict["schema_version"] == "v0.1"
    assert verdict["evidence"] == evidence


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"irreversible": False, "human_confirmed": None}, "reversible"),
        ({"irreversible": True, "human_confirmed": True}, "irreversible_confirmed"),
        ({"irreversible": True, "human_confirmed": False}, "irreversible_without_human"),
        ({"irreversible": True, "human_confirmed": None}, "irreversible_unknown"),
        ({"irreversible": "yes"}, "irreversible_unknown"),
    ],
)
def test_sec_002_irreversible(overrides: dict[str, Any], reason: str) -> None:
    assert evaluate_rule("R-SEC-002", _facts(**overrides))["evidence"] == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"sensitive": False, "egress": True}, "not_sensitive_egress"),
        ({"sensitive": True, "egress": False}, "not_sensitive_egress"),
        ({"sensitive": True, "egress": True}, "sensitive_egress"),
        ({"sensitive": True, "egress": None}, "privacy_unknown"),
        ({"sensitive": None, "egress": True}, "privacy_unknown"),
        ({"sensitive": "yes", "egress": True}, "privacy_unknown"),
        ({"sensitive": True, "egress": ""}, "privacy_unknown"),
        ({"sensitive": True, "egress": "public"}, "privacy_unknown"),
    ],
)
def test_pri_001_sensitive_egress(overrides: dict[str, Any], reason: str) -> None:
    verdict = evaluate_rule("R-PRI-001", _facts(**overrides))
    assert verdict["category"] == "privacy"
    assert verdict["evidence"] == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"requested_privileges": []}, "least_privilege"),
        ({"requested_privileges": ["read"]}, "least_privilege"),
        ({"requested_privileges": ["read", "write"]}, "least_privilege"),
        ({"requested_privileges": ["read", "admin"]}, "excess_privilege"),
        ({"requested_privileges": ["read"], "required_privileges": None}, "privilege_unknown"),
    ],
)
def test_pri_002_least_privilege(overrides: dict[str, Any], reason: str) -> None:
    verdict = evaluate_rule("R-PRI-002", _facts(**overrides))
    assert verdict["title"] == "最小權限"
    assert verdict["category"] == "privacy"
    assert verdict["evidence"] == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"compliance_regimes": ["gdpr"]}, "compliance_labels_ok"),
        ({"compliance_regimes": []}, "missing_compliance_label"),
        ({"compliance_regimes": None}, "compliance_unknown"),
        ({"compliance_regimes": "gdpr"}, "compliance_unknown"),
        ({"compliance_regimes": [""]}, "compliance_unknown"),
    ],
)
def test_com_001_labels(overrides: dict[str, Any], reason: str) -> None:
    verdict = evaluate_rule("R-COM-001", _facts(**overrides))
    assert verdict["category"] == "compliance"
    assert verdict["evidence"] == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"budget_ceiling": 9, "budget_floor": 10}, "ceiling_within_floor"),
        ({"budget_ceiling": 10, "budget_floor": 10}, "ceiling_within_floor"),
        ({"budget_ceiling": 10.5, "budget_floor": 10}, "ceiling_above_floor"),
        ({"budget_ceiling": True, "budget_floor": 10}, "budget_unknown"),
        ({"budget_ceiling": -1, "budget_floor": 10}, "budget_unknown"),
        ({"budget_ceiling": math.nan, "budget_floor": 10}, "budget_unknown"),
        ({"budget_ceiling": math.inf, "budget_floor": 10}, "budget_unknown"),
    ],
)
def test_bud_001_ceiling_versus_floor(overrides: dict[str, Any], reason: str) -> None:
    verdict = evaluate_rule("R-BUD-001", _facts(**overrides))
    assert verdict["title"] == "上限≤底線"
    assert verdict["category"] == "budget"
    assert verdict["hard_or_soft"] == "soft"
    assert verdict["evidence"] == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"latency": 200, "throughput": 40}, "performance_met"),
        ({"latency": 201}, "latency_or_throughput_miss"),
        ({"throughput": 39}, "latency_or_throughput_miss"),
        ({"latency": -1}, "performance_unknown"),
        ({"throughput": None}, "performance_unknown"),
    ],
)
def test_per_001_latency_and_throughput(overrides: dict[str, Any], reason: str) -> None:
    verdict = evaluate_rule("R-PER-001", _facts(**overrides))
    assert verdict["category"] == "performance"
    assert verdict["evidence"] == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"takeover_sec": 60, "takeover_slo_sec": 60}, "takeover_within_slo"),
        ({"takeover_sec": 61}, "takeover_too_slow"),
        ({"takeover_sec": -0.1}, "takeover_unknown"),
        ({"takeover_slo_sec": "fast"}, "takeover_unknown"),
    ],
)
def test_exp_001_takeover(overrides: dict[str, Any], reason: str) -> None:
    verdict = evaluate_rule("R-EXP-001", _facts(**overrides))
    assert verdict["category"] == "experience"
    assert verdict["evidence"] == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"high_risk": False, "automated_decision": True}, "not_high_risk_automated"),
        ({"high_risk": True, "automated_decision": False}, "not_high_risk_automated"),
        ({"high_risk": True, "automated_decision": True}, "high_risk_automated"),
        ({"high_risk": True, "automated_decision": None}, "ethics_unknown"),
        ({"high_risk": 1, "automated_decision": True}, "ethics_unknown"),
    ],
)
def test_eth_001_high_risk_automation(overrides: dict[str, Any], reason: str) -> None:
    verdict = evaluate_rule("R-ETH-001", _facts(**overrides))
    assert verdict["title"] == "高風險自動決策"
    assert verdict["category"] == "ethics"
    assert verdict["evidence"] == reason


def test_evaluate_rules_does_not_mutate_facts() -> None:
    facts = _facts()
    snapshot = dict(facts)
    evaluate_rules(facts)
    assert facts == snapshot


def test_non_mapping_is_rejected() -> None:
    with pytest.raises(TypeError):
        evaluate_rules(["not", "a", "dict"])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        evaluate_rule("R-SEC-001", "mcp")  # type: ignore[arg-type]


def test_unknown_rule_id_is_rejected() -> None:
    with pytest.raises(KeyError):
        evaluate_rule("R-SEC-999", PASSING)


def test_module_does_not_import_schema_enums_or_llm() -> None:
    """本檔只許規則引擎，不牽 schema、enums、流程或模型 SDK。"""

    path = Path(rules_mod.__file__ or "")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    banned = ("schema", "enums", "litellm", "openai", "langgraph")
    assert all(not any(word in name for word in banned) for name in imported)
    assert path.name == "rules.py"


def test_repeated_evaluation_is_stable() -> None:
    assert evaluate_rules(PASSING) == evaluate_rules(dict(PASSING))
