"""MGW-R7／R8：零依賴 Hub 目錄／circuit；熔斷常數不漂移。"""

from __future__ import annotations

import ast
from pathlib import Path

from backend.hub import circuit as hub_circuit
from backend.hub import probe as hub_probe
from backend.modelgw import circuit as mgw_circuit
from backend.modelgw import probe as mgw_probe

MGW_ROOT = Path(__file__).resolve().parents[1] / "modelgw"


def _python_files() -> list[Path]:
    return sorted(p for p in MGW_ROOT.rglob("*.py") if p.name != "__pycache__")


def test_mgw_r7_no_hub_catalog_or_circuit_import() -> None:
    forbidden_modules = {
        "backend.hub.catalog",
        "backend.hub.circuit",
        "backend.hub.probe",
        "backend.hub.router",
        "backend.hub.service",
    }
    forbidden_names = {"HUB_CATALOG"}
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules or alias.name.startswith("backend.hub."):
                        offenders.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in forbidden_modules or mod.startswith("backend.hub"):
                    offenders.append(f"{path.name}: from {mod}")
                for alias in node.names:
                    if alias.name in forbidden_names:
                        offenders.append(f"{path.name}: from {mod} import {alias.name}")
            elif isinstance(node, ast.Name) and node.id in forbidden_names:
                offenders.append(f"{path.name}: name {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                offenders.append(f"{path.name}: attr {node.attr}")
    assert not offenders, "ModelGW 不得依賴 Hub 目錄／circuit：\n" + "\n".join(offenders)


def test_mgw_r8_circuit_params_match_hub() -> None:
    attrs = [
        "sliding_window_size",
        "minimum_number_of_calls",
        "failure_rate_threshold",
        "slow_call_duration_s",
        "wait_duration_in_open_state_s",
        "permitted_half_open",
        "disable_after_open_cycles",
        "disable_for_s",
    ]
    for name in attrs:
        assert getattr(mgw_circuit.CircuitBreaker, name) == getattr(
            hub_circuit.CircuitBreaker, name
        ), f"熔斷參數漂移：{name}"


def test_mgw_r8_probe_params_match_hub() -> None:
    assert mgw_probe.PROBE_INTERVAL_S == hub_probe.PROBE_INTERVAL_S
    assert mgw_probe.PING_MAX_TOKENS == hub_probe.PING_MAX_TOKENS
    assert mgw_probe.EWMA_ALPHA == hub_probe.EWMA_ALPHA
    assert mgw_probe.FAIL_PENALTY_MS == hub_probe.FAIL_PENALTY_MS
