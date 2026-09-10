"""模拟 OPC UA 服务器 — 核心服务器类。

建立具有工业制程标签的本地 OPC UA 服务器，
标签值随时间动态变化以模拟真实环境。
"""

import asyncio
import logging
import random
from datetime import timezone

from asyncua import Server, ua

from opc_service.config import settings
from opc_service.simulator.tags import SIM_TAGS

logger = logging.getLogger(__name__)


class SimulatedOPCServer:
    """模拟 OPC UA 服务器。

    建立一个具有工业制程标签的本地 OPC UA 服务器，
    标签值会随时间动态变化以模拟真实环境。
    """

    def __init__(self):
        self._server: Server | None = None
        self._nodes: dict[str, ua.Node] = {}
        self._values: dict[str, float] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动模拟服务器并注册所有标签。"""
        self._server = Server()
        await self._server.init()
        url = (
            f"opc.tcp://0.0.0.0:{settings.sim_port}/freeopcua/server/"
        )
        self._server.set_endpoint(url)
        self._server.set_server_name("EvoLoop Simulated OPC Server")

        # 注册命名空间
        idx = await self._server.register_namespace(
            "http://evoloop.local/sim"
        )

        # 建立 Objects 节点
        objects = self._server.get_objects_node()

        # 为每个模拟标签建立变量节点（ns=2;s=TagName，与 client 读取路径一致）
        for tag in SIM_TAGS:
            name = tag["name"]
            self._values[name] = tag["init"]
            node_id = ua.NodeId(name, ua.Int16(idx))

            var = await objects.add_variable(
                nodeid=node_id,
                bname=name,
                val=tag["init"],
                varianttype=ua.VariantType.Double,
            )
            await var.set_writable(True)
            # 设置描述与单位
            desc_attr = ua.LocalizedText(f"{tag['desc']} ({tag['unit']})")
            await var.write_attribute(
                ua.AttributeIds.Description,
                ua.DataValue(
                    ua.Variant(desc_attr, ua.VariantType.LocalizedText)
                ),
            )
            self._nodes[name] = var

        # 启动服务器
        await self._server.start()
        logger.info(
            "模拟 OPC UA 服务器已启动：%s（%d 个标签）",
            url,
            len(SIM_TAGS),
        )

        # 启动数值更新后台任务
        self._task = asyncio.create_task(self._update_loop())

    async def stop(self) -> None:
        """停止模拟服务器。"""
        if self._task:
            self._task.cancel()
            self._task = None
        if self._server:
            await self._server.stop()
            self._server = None
            logger.info("模拟 OPC UA 服务器已停止")

    async def _update_loop(self) -> None:
        """后台循环：每秒更新标签值以模拟动态变化。"""
        while True:
            try:
                for tag in SIM_TAGS:
                    name = tag["name"]
                    current = self._values[name]
                    drift = tag["drift"]

                    if drift > 0:
                        # 随机漫步：在 drift 范围内随机变动
                        delta = random.uniform(-drift, drift)
                        new_val = current + delta
                        # 钳制在范围内
                        lo, hi = tag["range"]
                        new_val = max(lo, min(hi, new_val))
                        self._values[name] = round(new_val, 2)

                    # 更新 OPC 节点
                    node = self._nodes[name]
                    dv = ua.DataValue(
                        ua.Variant(
                            self._values[name], ua.VariantType.Double
                        )
                    )
                    dv.SourceTimestamp = ua.DateTime.now(timezone.utc)
                    await node.write_value(dv)

                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("模拟服务器更新循环异常")
                await asyncio.sleep(1.0)

    # ---- 内部访问器（供 anomaly 模块使用） ----

    @property
    def values(self) -> dict[str, float]:
        return self._values