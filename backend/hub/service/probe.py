"""Hub 上游探針與熔斷記錄（call_llm 經 _compat 延遲解析，保留套件層 patch）（自 backend.hub.service 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.hub.runtime import runtime

from ._compat import call_llm


def _record_circuit(model: str, failed: bool, duration_s: float) -> None:
    runtime.circuits.get(model).record(failed, duration_s=duration_s)


def _llm_probe(prompt: str, system: str | None, model: str, **kwargs: Any) -> str:
    """Hub 上游唯一入口：經 call_llm（ModelGW precheck）；entry=hub 觀測。

    G-GATE1（雙閘時序；P4-S2）：
    - Hub ``validate_model_id``／目錄＝**B 層產品濾鏡**（可長期保留）
    - ModelGW ``precheck_model``（WIRE=enforce）＝**唯一「能不能叫」準入權威**
    - 二者**不得**合併成單一電路狀態；Hub 目錄綠**不得**繞過 ModelGW admit
    """
    runtime.upstream_calls.append({"model": model, "prompt": prompt[:80]})
    try:
        from backend.modelgw.runtime import entry_scope

        with entry_scope("hub"):
            return call_llm(prompt, system=system, model=model, **kwargs)
    except ImportError:
        return call_llm(prompt, system=system, model=model, **kwargs)
