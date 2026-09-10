"""OPC 决策节点 — 根据诊断结果制定控制策略。

使用 LLM 综合分析诊断结果与统计数据，产出：
- 优先级排序的控制动作列表
- 每个动作的风险评估
- 动作执行顺序建议
- 不执行动作的明确理由（当无异常时）
"""

import json
import logging
from typing import Any

from backend.core.llm import call_llm, parse_json_response
from opc_service.prompts import DECIDE_OPC, DECIDE_OPC_SYSTEM

logger = logging.getLogger(__name__)


async def decide_opc(state: dict) -> dict[str, Any]:
    """节点 D1：根据诊断结果制定控制策略。

    综合分析诊断结果（opc_diagnosis）、分析数据（opc_analysis）、
    品质报告（opc_quality_report），由 LLM 制定优先级排序的
    控制动作列表，含风险评估。

    若无异常检测，则跳过决策（返回空动作列表）。
    """
    diagnosis = state.get("opc_diagnosis") or {}
    analysis = state.get("opc_analysis") or {}
    quality = state.get("opc_quality_report") or {}

    # 无异常 → 无需决策
    if not diagnosis.get("anomaly_detected"):
        return {
            "opc_decisions": [],
            "opc_decision_summary": "无异常，无需控制动作",
        }

    # 构建决策上下文
    context_parts = []

    # 诊断结果
    context_parts.append(
        f"【诊断结果】\n"
        f"异常检测：是\n"
        f"严重程度：{diagnosis.get('severity', 'unknown')}\n"
        f"根因分析：{diagnosis.get('root_cause', '无')}\n"
        f"详细分析：{diagnosis.get('analysis', '无')}"
    )

    # 阈值违规
    violations = analysis.get("violations", [])
    if violations:
        violation_lines = [
            f"  - {v['tag']}: {v['value']} "
            f"（阈值 {v['threshold']}，方向 {v['direction']}，"
            f"严重度 {v['severity']}）"
            for v in violations
        ]
        context_parts.append("【阈值违规】\n" + "\n".join(violation_lines))

    # 品质报告
    if quality:
        context_parts.append(
            f"【数据品质】\n"
            f"总标签数：{quality.get('total', 0)}\n"
            f"品质良好：{quality.get('good', 0)}\n"
            f"品质不良：{quality.get('bad', 0)}"
        )

    # 建议动作（来自诊断）
    suggested = diagnosis.get("suggested_actions", [])
    if suggested:
        action_lines = [
            f"  - {a.get('tag_name', '?')}: → {a.get('value', '?')} "
            f"（{a.get('reason', '无说明')}）"
            for a in suggested
        ]
        context_parts.append("【建议动作（来自诊断）】\n" + "\n".join(action_lines))

    context = "\n\n".join(context_parts)
    prompt = DECIDE_OPC.format(
        context=context,
        query=state.get("query", "请制定控制策略"),
    )

    raw = call_llm(prompt, system=DECIDE_OPC_SYSTEM)
    try:
        result = parse_json_response(raw)
    except json.JSONDecodeError:
        logger.warning("OPC 决策结果解析失败：%s", raw)
        # 降级：直接使用诊断建议的动作
        return {
            "opc_decisions": suggested,
            "opc_decision_summary": "决策解析失败，使用诊断建议",
        }

    decisions = result.get("decisions", [])
    summary = result.get("summary", "")

    if decisions:
        logger.info(
            "OPC 决策：制定 %d 个控制动作，优先级：%s",
            len(decisions),
            ", ".join(
                f"{d.get('tag_name', '?')}={d.get('priority', '?')}"
                for d in decisions
            ),
        )

    return {
        "opc_decisions": decisions,
        "opc_decision_summary": summary,
    }