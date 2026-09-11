"""OPC 路由 — 标签写入（含安全护栏检查）。"""

import logging
from typing import Any

from fastapi import APIRouter

from opc_service.audit import audit_logger
from opc_service.client import opc_client
from opc_service.guard import write_guard
from opc_service.models import (
    WriteRequest,
    WriteResponse,
    WriteResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OPC 写入"])


@router.post("/write", response_model=WriteResponse)
async def write_tags(req: WriteRequest):
    """写入标签值，写入前通过安全护栏检查。

    安全检查流程：
    1. 白名单检查 → 2. 边界检查 → 3. 并发执行写入 → 4. 审计记录
    
    性能优化：使用并发批量写入，显著提升多标签写入性能。
    """
    results: list[WriteResult] = []
    valid_entries: list[dict[str, Any]] = []

    # 第一阶段：安全检查与过滤
    for entry in req.entries:
        # 安全护栏检查
        passed, guard_msg = write_guard.validate_write(
            entry.tag_name, entry.value
        )
        if not passed:
            results.append(
                WriteResult(
                    tag_name=entry.tag_name,
                    success=False,
                    message=guard_msg,
                )
            )
            audit_logger.log_write(
                entry.tag_name,
                entry.value,
                reason=req.reason,
                result="blocked",
                detail=guard_msg,
            )
        else:
            valid_entries.append({"tag_name": entry.tag_name, "value": entry.value})

    # 第二阶段：并发执行所有有效写入
    if valid_entries:
        try:
            write_results = await opc_client.write_nodes(valid_entries)
            for result in write_results:
                results.append(WriteResult(**result))
                audit_logger.log_write(
                    result["tag_name"],
                    float(result.get("written_value") or 0.0),
                    reason=req.reason,
                    result="success" if result["success"] else "failed",
                    detail=result.get("message", ""),
                )
                if result.get("success"):
                    try:
                        from backend.billing.metering import meter_opc_write

                        meter_opc_write(reference=result["tag_name"], meta={"reason": req.reason or ""})
                    except Exception:
                        pass
        except Exception as exc:
            logger.exception("批量写入失败")
            # 降级处理：为每个未处理的条目添加失败结果
            for pending in valid_entries:
                results.append(
                    WriteResult(
                        tag_name=pending["tag_name"],
                        success=False,
                        message=str(exc),
                    )
                )
                audit_logger.log_write(
                    pending["tag_name"],
                    float(pending["value"]),
                    reason=req.reason,
                    result="failed",
                    detail=str(exc),
                )

    return WriteResponse(results=results)