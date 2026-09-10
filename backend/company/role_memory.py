"""角色記憶系統 — 讓 Agent 從歷史任務學習。

每個角色擁有獨立的記憶命名空間，支援：

- 執行前檢索：查詢該角色的相關歷史經驗
- 執行後保存：將成功案例存入角色記憶
- 審查回饋記憶：Reviewer 的回饋也存入記憶，避免重複錯誤

記憶格式：
    問題：{task_title}
    經驗：{experience}
    結果：{outcome}

使用範例：
    >>> from backend.company.role_memory import RoleMemory
    >>> memory = RoleMemory("developer")
    >>> experiences = memory.retrieve("開發登入頁面", k=3)
    >>> memory.save("開發登入頁面", "使用 JWT 認證", "成功通過審查")
"""

from __future__ import annotations

import logging
from typing import Any

from backend.memory.vector_store import VectorMemoryStore

logger = logging.getLogger(__name__)

# 角色記憶集合名稱前綴
ROLE_MEMORY_PREFIX = "role_memory_"


class RoleMemory:
    """角色記憶管理器。

    每個角色一個獨立的 ChromaDB collection，
    避免不同角色的經驗互相干擾。
    """

    def __init__(self, role: str, store: VectorMemoryStore | None = None):
        """初始化角色記憶。

        Args:
            role: 角色名稱（如 "developer"、"reviewer"）
            store: 向量記憶庫實例（可注入，方便測試）
        """
        self.role = role.lower()
        self.collection_name = f"{ROLE_MEMORY_PREFIX}{self.role}"
        self._store = store or VectorMemoryStore(collection_name=self.collection_name)

    def retrieve(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        """檢索與任務相關的歷史經驗。

        Args:
            query: 任務描述
            k: 回傳筆數

        Returns:
            [{"text": ..., "metadata": ..., "distance": ...}, ...]
        """
        try:
            results = self._store.search_similar(query, k=k)
            if results:
                logger.debug(
                    "角色 %s 檢索到 %d 筆相關經驗", self.role, len(results)
                )
            return results
        except Exception as exc:
            logger.warning("角色記憶檢索失敗（%s）：%s", self.role, exc)
            return []

    def retrieve_formatted(self, query: str, k: int = 3) -> str:
        """檢索並格式化為 Prompt 區塊。

        Args:
            query: 任務描述
            k: 回傳筆數

        Returns:
            格式化的經驗文字，若無相關經驗則回傳空字串
        """
        results = self.retrieve(query, k=k)
        if not results:
            return ""

        lines = [f"【{self.role} 的歷史經驗】"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['text'][:800]}")
        lines.append("")
        lines.append("請參考以上歷史經驗，避免重複犯錯。")
        return "\n".join(lines)

    def save(
        self,
        task_title: str,
        experience: str,
        outcome: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """保存經驗到角色記憶。

        Args:
            task_title: 任務標題
            experience: 經驗描述（做了什麼、學到什麼）
            outcome: 結果（成功/失敗、審查分數等）
            metadata: 額外元數據

        Returns:
            記憶 ID，失敗時回傳 None
        """
        text = f"任務：{task_title}\n經驗：{experience}\n結果：{outcome}"
        meta = {
            "role": self.role,
            "task_title": task_title[:200],
            **(metadata or {}),
        }
        try:
            record_id = self._store.add_memory(text, metadata=meta)
            logger.debug("角色 %s 保存經驗：%s", self.role, task_title[:50])
            return record_id
        except Exception as exc:
            logger.warning("角色記憶保存失敗（%s）：%s", self.role, exc)
            return None

    def save_from_work_item(
        self,
        title: str,
        output: str,
        review_result: dict[str, Any] | None = None,
        success: bool = True,
    ) -> str | None:
        """從工作項結果保存經驗。

        Args:
            title: 工作項標題
            output: 交付物（截斷保存）
            review_result: 審查結果
            success: 是否成功

        Returns:
            記憶 ID，失敗時回傳 None
        """
        # 只保存有學習價值的經驗
        # 1. 失敗的經驗（避免重複犯錯）
        # 2. 審查分數 < 8 的經驗（有改進空間）
        # 3. 成功的複雜任務
        score = (review_result or {}).get("score")
        should_save = (
            not success
            or (score is not None and isinstance(score, (int, float)) and score < 8)
            or len(output) > 500  # 較長的交付物通常是複雜任務
        )

        if not should_save:
            return None

        experience = output[:1000] if output else "（無交付物）"
        if review_result:
            feedback = review_result.get("feedback", "")
            if feedback:
                experience += f"\n審查回饋：{feedback[:300]}"

        outcome = "成功" if success else "失敗"
        if score is not None:
            outcome += f"（評分 {score}）"

        return self.save(
            task_title=title,
            experience=experience,
            outcome=outcome,
            metadata={"score": score, "success": success},
        )

    def count(self) -> int:
        """回傳角色記憶總數。"""
        try:
            return self._store.count()
        except Exception:
            return 0

    def cleanup(self, max_age_days: int = 60, min_score: float | None = None) -> int:
        """清理過期或低品質記憶。"""
        try:
            return self._store.cleanup(max_age_days, min_score)
        except Exception as exc:
            logger.warning("角色記憶清理失敗（%s）：%s", self.role, exc)
            return 0


# ═══════════════════════════════════════════════════════════════
# 全域角色記憶管理器快取
# ═══════════════════════════════════════════════════════════════

_role_memories: dict[str, RoleMemory] = {}


def get_role_memory(role: str) -> RoleMemory:
    """獲取角色的記憶管理器（快取單例）。

    Args:
        role: 角色名稱

    Returns:
        RoleMemory 實例
    """
    role_key = role.lower()
    if role_key not in _role_memories:
        _role_memories[role_key] = RoleMemory(role_key)
    return _role_memories[role_key]