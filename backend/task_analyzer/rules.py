"""任務分析器原子規則引擎。

只做九條固定規則的判定與短路，不讀 schema／enums，不跑分析流程。
輸入是 dict 或 TypedDict（欄位名即本模組契約）。缺值、型別不對、非有限數字
都是 unknown，unknown 永不計入 pass。

硬規則依出現順序先跑。任一硬規則 fail 即停止，後續規則不執行、不給判決。
軟規則只在沒有硬 fail 時才跑；軟 fail 不短路。

通過條件（``passed``）是九條都已執行且全部為 pass。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from enum import Enum
from typing import Any, Literal, TypedDict, TypeGuard

SCHEMA_VERSION = "v0.1"

RuleStatus = Literal["pass", "fail", "unknown"]
_STATUSES: frozenset[str] = frozenset({"pass", "fail", "unknown"})


class _Probe(Enum):
    """欄位探針：缺值與非法值都不得當成有效事實。"""

    MISSING = "missing"
    INVALID = "invalid"


class RuleFacts(TypedDict, total=False):
    """規則事實。鍵缺席或值為 None 表示未知，不得推斷成否。

    與底層規格 v0.1 同名的欄位：``resources``／``kind``／``id``（ResourceSpec）、
    ``compliance_regimes``（EnvironmentSpec）、``latency``（criterion.metric）、
    ``hard_or_soft``、``status``。``Network.egress`` 在規格是字串且空字串代表未填，
    本引擎的 ``egress`` 只收 bool，字串一律 unknown，避免把自由描述猜成出域。
    ``budget_ceiling``／``budget_floor`` 不是 MoneyBand 的 ``high``／``low``：
    規格要求區間 low 不可大於 high，與此規則「上限≤底線」不是同一條不等式。
    """

    resources: list[dict[str, str]]
    authorized_resources: list[dict[str, str]]
    irreversible: bool
    human_confirmed: bool
    sensitive: bool
    egress: bool
    requested_privileges: list[str]
    required_privileges: list[str]
    compliance_regimes: list[str]
    budget_ceiling: float
    budget_floor: float
    latency: float
    latency_slo: float
    throughput: float
    throughput_slo: float
    takeover_sec: float
    takeover_slo_sec: float
    high_risk: bool
    automated_decision: bool


class RuleVerdict(TypedDict):
    """單條已執行規則。欄位對齊 RedLine：id、category、hard_or_soft、status、evidence。"""

    schema_version: str
    id: str
    title: str
    category: str
    hard_or_soft: Literal["hard", "soft"]
    status: RuleStatus
    evidence: str


class RuleEngineReport(TypedDict):
    """整包結果。skipped_rule_ids 是未執行的規則，不是第四種判決。"""

    schema_version: str
    results: list[RuleVerdict]
    skipped_rule_ids: list[str]
    short_circuited: bool
    hard_failed_rule_id: str | None
    passed: bool


# (id, 中文名, 是否硬規則)。順序即使用者給定的規則序。
RULE_CATALOG: tuple[tuple[str, str, bool], ...] = (
    ("R-SEC-001", "越權 MCP", True),
    ("R-SEC-002", "不可逆需人工", True),
    ("R-PRI-001", "敏感且出域", True),
    ("R-PRI-002", "最小權限", True),
    ("R-COM-001", "合規標籤", True),
    ("R-BUD-001", "上限≤底線", False),
    ("R-PER-001", "延遲吞吐", False),
    ("R-EXP-001", "接管時間", False),
    ("R-ETH-001", "高風險自動決策", True),
)

RULE_IDS: tuple[str, ...] = tuple(item[0] for item in RULE_CATALOG)
RULE_TITLES: dict[str, str] = {item[0]: item[1] for item in RULE_CATALOG}
RULE_CATEGORIES: dict[str, str] = {
    "R-SEC-001": "safety",
    "R-SEC-002": "safety",
    "R-PRI-001": "privacy",
    "R-PRI-002": "privacy",
    "R-COM-001": "compliance",
    "R-BUD-001": "budget",
    "R-PER-001": "performance",
    "R-EXP-001": "experience",
    "R-ETH-001": "ethics",
}
HARD_RULE_IDS: tuple[str, ...] = tuple(item[0] for item in RULE_CATALOG if item[2])
SOFT_RULE_IDS: tuple[str, ...] = tuple(item[0] for item in RULE_CATALOG if not item[2])
EVALUATION_ORDER: tuple[str, ...] = HARD_RULE_IDS + SOFT_RULE_IDS


def counts_as_pass(status: str) -> bool:
    """只有 pass 算通過。unknown、fail、空字串與其他值都不是通過。"""

    return status == "pass"


def _raw(facts: Mapping[str, Any], key: str) -> Any:
    if key not in facts or facts[key] is None:
        return _Probe.MISSING
    return facts[key]


def _flag(facts: Mapping[str, Any], key: str) -> bool | _Probe:
    value = _raw(facts, key)
    if isinstance(value, _Probe):
        return value
    if isinstance(value, bool):
        return value
    return _Probe.INVALID


def _strings(facts: Mapping[str, Any], key: str) -> set[str] | _Probe:
    value = _raw(facts, key)
    if isinstance(value, _Probe):
        return value
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set, frozenset)):
        return _Probe.INVALID
    found: set[str] = set()
    for item in value:
        if not isinstance(item, str) or item == "":
            return _Probe.INVALID
        found.add(item)
    return found


def _number(facts: Mapping[str, Any], key: str) -> float | _Probe:
    value = _raw(facts, key)
    if isinstance(value, _Probe):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _Probe.INVALID
    if not math.isfinite(value):
        return _Probe.INVALID
    return float(value)


def _is_set(value: set[str] | _Probe) -> TypeGuard[set[str]]:
    return isinstance(value, set)


_RESOURCE_KINDS = frozenset({"mcp_server", "api", "dataset", "file", "skill", "opc_node"})


def _mcp_ids(facts: Mapping[str, Any], key: str) -> set[str] | _Probe:
    """取出 kind 為 mcp_server 的資源 id。其他合法 kind 不計入越權。"""

    value = _raw(facts, key)
    if isinstance(value, _Probe):
        return value
    if not isinstance(value, list):
        return _Probe.INVALID
    found: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            return _Probe.INVALID
        kind = item.get("kind")
        resource_id = item.get("id")
        if kind not in _RESOURCE_KINDS or not isinstance(resource_id, str) or resource_id == "":
            return _Probe.INVALID
        if kind == "mcp_server":
            found.add(resource_id)
    return found


def rule_sec_001(facts: Mapping[str, Any]) -> tuple[RuleStatus, str]:
    """越權 MCP：要求的 mcp_server 必須出現在授權資源裡。沒有 MCP 要求視為未呼叫。"""

    requested = _mcp_ids(facts, "resources")
    if _is_set(requested) and not requested:
        return "pass", "mcp_not_requested"
    authorized = _mcp_ids(facts, "authorized_resources")
    if not _is_set(requested) or not _is_set(authorized):
        return "unknown", "mcp_unknown"
    if requested - authorized:
        return "fail", "unauthorized_mcp"
    return "pass", "mcp_authorized"


def rule_sec_002(facts: Mapping[str, Any]) -> tuple[RuleStatus, str]:
    """不可逆需人工：可逆直接過；不可逆必須已有人工確認。"""

    irreversible = _flag(facts, "irreversible")
    if not isinstance(irreversible, bool):
        return "unknown", "irreversible_unknown"
    if not irreversible:
        return "pass", "reversible"
    human = _flag(facts, "human_confirmed")
    if human is True:
        return "pass", "irreversible_confirmed"
    if human is False:
        return "fail", "irreversible_without_human"
    return "unknown", "irreversible_unknown"


def rule_pri_001(facts: Mapping[str, Any]) -> tuple[RuleStatus, str]:
    """敏感且出域：兩項都為真才失敗；任一項明確為假則此違規不成立。"""

    sensitive = _flag(facts, "sensitive")
    egress = _flag(facts, "egress")
    if sensitive is False or egress is False:
        return "pass", "not_sensitive_egress"
    if sensitive is True and egress is True:
        return "fail", "sensitive_egress"
    return "unknown", "privacy_unknown"


def rule_pri_002(facts: Mapping[str, Any]) -> tuple[RuleStatus, str]:
    """最小權限：要求的權限不得超出必要集合。空要求視為未越權。"""

    requested = _strings(facts, "requested_privileges")
    if _is_set(requested) and not requested:
        return "pass", "least_privilege"
    required = _strings(facts, "required_privileges")
    if not _is_set(requested) or not _is_set(required):
        return "unknown", "privilege_unknown"
    if requested - required:
        return "fail", "excess_privilege"
    return "pass", "least_privilege"


def rule_com_001(facts: Mapping[str, Any]) -> tuple[RuleStatus, str]:
    """合規標籤：``compliance_regimes`` 至少要有一個標籤。空清單是已知缺失。"""

    regimes = _strings(facts, "compliance_regimes")
    if not _is_set(regimes):
        return "unknown", "compliance_unknown"
    if not regimes:
        return "fail", "missing_compliance_label"
    return "pass", "compliance_labels_ok"


def rule_bud_001(facts: Mapping[str, Any]) -> tuple[RuleStatus, str]:
    """上限≤底線：預算上限不得高於底線。負數或非有限值視為未知。"""

    ceiling = _number(facts, "budget_ceiling")
    floor = _number(facts, "budget_floor")
    if not isinstance(ceiling, float) or not isinstance(floor, float):
        return "unknown", "budget_unknown"
    if ceiling < 0 or floor < 0:
        return "unknown", "budget_unknown"
    if ceiling <= floor:
        return "pass", "ceiling_within_floor"
    return "fail", "ceiling_above_floor"


def _finite(facts: Mapping[str, Any], key: str) -> float | None:
    """合法非負有限數；缺值、型別錯、負數、NaN、無限都回 None。"""

    value = _number(facts, key)
    if not isinstance(value, float) or value < 0:
        return None
    return value


def rule_per_001(facts: Mapping[str, Any]) -> tuple[RuleStatus, str]:
    """延遲吞吐：延遲不高於 SLO，且吞吐不低於 SLO。"""

    latency = _finite(facts, "latency")
    latency_slo = _finite(facts, "latency_slo")
    throughput = _finite(facts, "throughput")
    throughput_slo = _finite(facts, "throughput_slo")
    if None in (latency, latency_slo, throughput, throughput_slo):
        return "unknown", "performance_unknown"
    assert latency is not None and latency_slo is not None
    assert throughput is not None and throughput_slo is not None
    if latency <= latency_slo and throughput >= throughput_slo:
        return "pass", "performance_met"
    return "fail", "latency_or_throughput_miss"


def rule_exp_001(facts: Mapping[str, Any]) -> tuple[RuleStatus, str]:
    """接管時間：接管秒數不得超過 SLO。"""

    takeover = _number(facts, "takeover_sec")
    slo = _number(facts, "takeover_slo_sec")
    if not isinstance(takeover, float) or not isinstance(slo, float):
        return "unknown", "takeover_unknown"
    if takeover < 0 or slo < 0:
        return "unknown", "takeover_unknown"
    if takeover <= slo:
        return "pass", "takeover_within_slo"
    return "fail", "takeover_too_slow"


def rule_eth_001(facts: Mapping[str, Any]) -> tuple[RuleStatus, str]:
    """高風險自動決策：兩項都為真才失敗；任一項明確為假則此違規不成立。"""

    high_risk = _flag(facts, "high_risk")
    automated = _flag(facts, "automated_decision")
    if high_risk is False or automated is False:
        return "pass", "not_high_risk_automated"
    if high_risk is True and automated is True:
        return "fail", "high_risk_automated"
    return "unknown", "ethics_unknown"


DISPATCH: dict[str, Any] = {
    "R-SEC-001": rule_sec_001,
    "R-SEC-002": rule_sec_002,
    "R-PRI-001": rule_pri_001,
    "R-PRI-002": rule_pri_002,
    "R-COM-001": rule_com_001,
    "R-BUD-001": rule_bud_001,
    "R-PER-001": rule_per_001,
    "R-EXP-001": rule_exp_001,
    "R-ETH-001": rule_eth_001,
}


def _coerce(outcome: object) -> tuple[RuleStatus, str]:
    if (
        isinstance(outcome, tuple)
        and len(outcome) == 2
        and outcome[0] in _STATUSES
        and isinstance(outcome[1], str)
    ):
        status: RuleStatus = outcome[0]
        return status, outcome[1]
    return "unknown", "invalid_status"


def evaluate_rule(rule_id: str, facts: Mapping[str, Any]) -> RuleVerdict:
    """執行單條規則。規則表在呼叫當下讀取，方便測試替換。"""

    if rule_id not in DISPATCH:
        raise KeyError(rule_id)
    if not isinstance(facts, Mapping) or isinstance(facts, (str, bytes)):
        raise TypeError("facts 必須是對應欄位的 dict")
    status, evidence = _coerce(DISPATCH[rule_id](facts))
    return {
        "schema_version": SCHEMA_VERSION,
        "id": rule_id,
        "title": RULE_TITLES[rule_id],
        "category": RULE_CATEGORIES[rule_id],
        "hard_or_soft": "hard" if rule_id in HARD_RULE_IDS else "soft",
        "status": status,
        "evidence": evidence,
    }


def evaluate_rules(facts: Mapping[str, Any]) -> RuleEngineReport:
    """先硬後軟。硬 fail 後不再呼叫後續規則。"""

    if not isinstance(facts, Mapping) or isinstance(facts, (str, bytes)):
        raise TypeError("facts 必須是對應欄位的 dict")

    results: list[RuleVerdict] = []
    short_circuited = False
    hard_failed_rule_id: str | None = None

    for index, rule_id in enumerate(EVALUATION_ORDER):
        verdict = evaluate_rule(rule_id, facts)
        results.append(verdict)
        if verdict["hard_or_soft"] == "hard" and verdict["status"] == "fail":
            short_circuited = True
            hard_failed_rule_id = rule_id
            skipped = list(EVALUATION_ORDER[index + 1 :])
            break
    else:
        skipped = []

    passed = (
        not short_circuited
        and not skipped
        and len(results) == len(RULE_IDS)
        and all(counts_as_pass(item["status"]) for item in results)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "results": results,
        "skipped_rule_ids": skipped,
        "short_circuited": short_circuited,
        "hard_failed_rule_id": hard_failed_rule_id,
        "passed": passed,
    }
