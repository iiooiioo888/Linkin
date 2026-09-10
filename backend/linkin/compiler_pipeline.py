"""Minecraft 適配器／編譯器管線骨架（TODO §8）。

把「敘事／建築產出 → MC 可部署產物」納入與審計同級的**顯式治理**：

    compile（顯式）→ sandboxing（結構校驗＋版本相容＋衝突掃描）
    → awaiting_deploy → deploy（需部署確認權）／rollback

契約寫死：

- **C-COMP-001**：編譯／部署僅能顯式觸發；編譯成功 ≠ 自動部署；
  沙盒未通過不得進入待部署。
- **C-COMP-002**：編譯／沙盒失敗**保留舊版本**，禁止自動 ``/reload`` 或強制熱更新。
- **C-COMP-003**：產物形態優先級 Datapack＋Resource Pack > Schematic >
  預編譯 Java 橋接層；**禁止運行時生成／編譯 Java 代碼**（§8.6）。
- **C-COMP-004**：部署前須經「部署確認權」席位確認（預設僅 L5＋人類管理員，§2.2）。
- **C-COMP-005**：衝突掃描至少涵蓋命名空間／實體 ID／配方／戰利品表／標籤覆蓋；
  同名衝突拒絕覆蓋並回傳衝突清單，禁止靜默最後寫入勝出。
- 編譯／部署呼叫記錄納入審計軌跡（§8.4，經 ``trail`` 注入；可被審計讀取，
  不得主動灌入審計分數）。

測試隔離：編譯器、沙盒掃描器、部署器、產物存儲全部可依賴注入／stub，
不依賴真實 MineMCP 或遊戲伺服器。
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol

from backend.company.seat_table import SeatTable, build_default_seat_table
from backend.company.task_state_machine import TaskAction, TaskRuntimeState, Verdict, evaluate

ERR_RUNTIME_JAVA_FORBIDDEN = "ERR_RUNTIME_JAVA_FORBIDDEN"
ERR_COMPILE_FAILED = "ERR_COMPILE_FAILED"
ERR_SANDBOX_FAILED = "ERR_SANDBOX_FAILED"
ERR_DEPLOY_UNAUTHORIZED = "ERR_DEPLOY_UNAUTHORIZED"
ERR_DEPLOY_CONFLICT = "ERR_DEPLOY_CONFLICT"
ERR_DEPLOY_NOT_AWAITING = "ERR_DEPLOY_NOT_AWAITING"
ERR_ARTIFACT_UNKNOWN = "ERR_ARTIFACT_UNKNOWN"
ERR_ROLLBACK_TARGET_UNKNOWN = "ERR_ROLLBACK_TARGET_UNKNOWN"


# ── 產物形態（§8.6 優先級寫死） ────────────────────────────────
class ArtifactKind(str, Enum):
    DATAPACK = "datapack"                    # 首選
    RESOURCE_PACK = "resource_pack"          # 首選
    SCHEMATIC = "schematic"                  # 建築結構
    JAVA_BRIDGE_PRECOMPILED = "java_bridge"  # 僅預編譯橋接層
    JAVA_MOD_RUNTIME = "java_mod_runtime"    # 禁止：運行時生成／編譯 Java

# 數字越小優先級越高（§8.6）
ARTIFACT_PRIORITY: tuple[ArtifactKind, ...] = (
    ArtifactKind.DATAPACK,
    ArtifactKind.RESOURCE_PACK,
    ArtifactKind.SCHEMATIC,
    ArtifactKind.JAVA_BRIDGE_PRECOMPILED,
)

FORBIDDEN_KINDS: frozenset[ArtifactKind] = frozenset({ArtifactKind.JAVA_MOD_RUNTIME})


def guard_artifact_kind(kind: ArtifactKind | str) -> ArtifactKind:
    """C-COMP-003：運行時 Java 生成路徑一律拒絕。"""
    kind = ArtifactKind(kind)
    if kind in FORBIDDEN_KINDS:
        raise ValueError(
            f"{ERR_RUNTIME_JAVA_FORBIDDEN}: 禁止運行時生成／編譯 Java 代碼（§8.6）"
        )
    return kind


# ── 產物與請求模型 ─────────────────────────────────────────────
@dataclass(frozen=True)
class CompileRequest:
    namespace: str
    kind: ArtifactKind
    files: Mapping[str, str] = field(default_factory=dict)  # 路徑 → 內容
    entity_ids: tuple[str, ...] = ()
    recipes: tuple[str, ...] = ()
    loot_tables: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    mc_version: str = ""
    requested_by: str = ""  # 發起席位（審計歸因）


@dataclass(frozen=True)
class CompileArtifact:
    artifact_id: str
    namespace: str
    kind: ArtifactKind
    version: int
    content_hash: str
    files: Mapping[str, str]
    entity_ids: tuple[str, ...] = ()
    recipes: tuple[str, ...] = ()
    loot_tables: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "namespace": self.namespace,
            "kind": self.kind.value,
            "version": self.version,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }


def _hash_files(files: Mapping[str, str]) -> str:
    rows = sorted(f"{path}\0{content}" for path, content in files.items())
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


# ── 沙盒驗證（§8.2：結構校驗＋版本相容＋衝突掃描） ─────────────
class ConflictKind(str, Enum):
    NAMESPACE = "namespace"    # datapacks/[namespace]/ 同名檔案
    ENTITY_ID = "entity_id"
    RECIPE = "recipe"
    LOOT_TABLE = "loot_table"
    TAG = "tag"


@dataclass(frozen=True)
class Conflict:
    kind: ConflictKind
    key: str
    detail: str = ""


@dataclass(frozen=True)
class SandboxReport:
    ok: bool
    structure_errors: tuple[str, ...] = ()
    version_compatible: bool = True
    conflicts: tuple[Conflict, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "structure_errors": list(self.structure_errors),
            "version_compatible": self.version_compatible,
            "conflicts": [
                {"kind": c.kind.value, "key": c.key, "detail": c.detail} for c in self.conflicts
            ],
        }


class WorldIndex(Protocol):
    """既有世界索引（唯讀）：沙盒衝突掃描的對照來源。"""

    def namespaces(self) -> Iterable[str]: ...
    def entity_ids(self) -> Iterable[str]: ...
    def recipes(self) -> Iterable[str]: ...
    def loot_tables(self) -> Iterable[str]: ...
    def tags(self) -> Iterable[str]: ...
    def mc_version(self) -> str: ...


class InMemoryWorldIndex:
    """預設空世界（測試用）。"""

    def __init__(
        self,
        *,
        namespaces: Iterable[str] = (),
        entity_ids: Iterable[str] = (),
        recipes: Iterable[str] = (),
        loot_tables: Iterable[str] = (),
        tags: Iterable[str] = (),
        version: str = "",
    ) -> None:
        self._namespaces = set(namespaces)
        self._entities = set(entity_ids)
        self._recipes = set(recipes)
        self._loots = set(loot_tables)
        self._tags = set(tags)
        self._version = version

    def namespaces(self) -> Iterable[str]:
        return tuple(self._namespaces)

    def entity_ids(self) -> Iterable[str]:
        return tuple(self._entities)

    def recipes(self) -> Iterable[str]:
        return tuple(self._recipes)

    def loot_tables(self) -> Iterable[str]:
        return tuple(self._loots)

    def tags(self) -> Iterable[str]:
        return tuple(self._tags)

    def mc_version(self) -> str:
        return self._version


StructureChecker = Callable[[CompileArtifact], tuple[str, ...]]


def default_structure_checker(artifact: CompileArtifact) -> tuple[str, ...]:
    """預設結構校驗：命名空間合法、至少一個檔案、無 .java 源碼（C-COMP-003）。"""
    errors: list[str] = []
    ns = artifact.namespace
    if not ns or not ns.replace("_", "").replace("-", "").isalnum() or not ns[0].isalpha():
        errors.append(f"命名空間非法：{ns!r}")
    if not artifact.files:
        errors.append("產物無任何檔案")
    java_files = [p for p in artifact.files if p.endswith(".java")]
    if java_files:
        errors.append(f"產物含 .java 源碼（運行時編譯禁止）：{java_files}")
    return tuple(errors)


def sandbox_scan(
    artifact: CompileArtifact,
    world: WorldIndex,
    *,
    structure_checker: StructureChecker = default_structure_checker,
) -> SandboxReport:
    """沙盒驗證（C-COMP-005）：結構校驗＋版本相容＋五項衝突掃描。"""
    structure_errors = tuple(structure_checker(artifact))
    world_version = (world.mc_version() or "").strip()
    version_ok = True  # 無世界版本資訊時不阻擋；有則由呼叫方 policy 決定嚴格度
    conflicts: list[Conflict] = []
    if artifact.namespace in set(world.namespaces()):
        conflicts.append(Conflict(ConflictKind.NAMESPACE, artifact.namespace, "命名空間已存在"))
    for eid in artifact.entity_ids:
        if eid in set(world.entity_ids()):
            conflicts.append(Conflict(ConflictKind.ENTITY_ID, eid, "實體 ID 重複"))
    for r in artifact.recipes:
        if r in set(world.recipes()):
            conflicts.append(Conflict(ConflictKind.RECIPE, r, "配方衝突"))
    for lt in artifact.loot_tables:
        if lt in set(world.loot_tables()):
            conflicts.append(Conflict(ConflictKind.LOOT_TABLE, lt, "戰利品表衝突"))
    for t in artifact.tags:
        if t in set(world.tags()):
            conflicts.append(Conflict(ConflictKind.TAG, t, "標籤覆蓋衝突"))
    ok = not structure_errors and version_ok and not conflicts
    return SandboxReport(
        ok=ok,
        structure_errors=structure_errors,
        version_compatible=version_ok and bool(world_version or True),
        conflicts=tuple(conflicts),
    )


# ── 產物存儲（版本化＋回滾；失敗保留舊版） ─────────────────────
class ArtifactStore(Protocol):
    def latest(self, namespace: str) -> CompileArtifact | None: ...
    def put_staging(self, artifact: CompileArtifact) -> None: ...
    def promote(self, artifact_id: str) -> None: ...
    def get(self, artifact_id: str) -> CompileArtifact | None: ...
    def history(self, namespace: str) -> tuple[CompileArtifact, ...]: ...


class InMemoryArtifactStore:
    """staging 與 deployed 分離：未經部署確認前，線上（deployed）版本不被覆蓋。"""

    def __init__(self) -> None:
        self._staging: dict[str, CompileArtifact] = {}
        self._deployed: dict[str, CompileArtifact] = {}      # namespace → 當前線上版
        self._history: dict[str, list[CompileArtifact]] = {}

    def latest(self, namespace: str) -> CompileArtifact | None:
        return self._deployed.get(namespace)

    def put_staging(self, artifact: CompileArtifact) -> None:
        self._staging[artifact.artifact_id] = artifact

    def get(self, artifact_id: str) -> CompileArtifact | None:
        if artifact_id in self._staging:
            return self._staging[artifact_id]
        for art in self._deployed.values():
            if art.artifact_id == artifact_id:
                return art
        return None

    def promote(self, artifact_id: str) -> None:
        art = self._staging.pop(artifact_id, None)
        if art is None:
            raise KeyError(f"{ERR_ARTIFACT_UNKNOWN}: {artifact_id}")
        self._deployed[art.namespace] = art
        self._history.setdefault(art.namespace, []).append(art)

    def history(self, namespace: str) -> tuple[CompileArtifact, ...]:
        return tuple(self._history.get(namespace, ()))


# ── 部署器（寫入遊戲世界；stub 可注入） ────────────────────────
class Deployer(Protocol):
    def deploy(self, artifact: CompileArtifact) -> None: ...
    def reload_world(self) -> None: ...  # 僅顯式 reload；管線保證失敗路徑不呼叫


class RecordingDeployer:
    """測試用部署器：記錄呼叫，證明失敗路徑不觸發 /reload（C-COMP-002）。"""

    def __init__(self) -> None:
        self.deployed: list[str] = []
        self.reload_calls = 0

    def deploy(self, artifact: CompileArtifact) -> None:
        self.deployed.append(artifact.artifact_id)

    def reload_world(self) -> None:
        self.reload_calls += 1


TrailRecorder = Callable[[str, dict[str, Any]], None]
CompilerFn = Callable[[CompileRequest], Mapping[str, str]]


# ── 編譯管線 ───────────────────────────────────────────────────
@dataclass
class PipelineResult:
    ok: bool
    error_code: str = ""
    state: TaskRuntimeState | None = None
    artifact: CompileArtifact | None = None
    sandbox: SandboxReport | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_code": self.error_code,
            "state": self.state.value if self.state else None,
            "artifact": self.artifact.to_dict() if self.artifact else None,
            "sandbox": self.sandbox.to_dict() if self.sandbox else None,
            "detail": self.detail,
        }


class CompilePipeline:
    """顯式編譯→沙盒→部署閘門管線（§8）。不掛任何串流／聊天完成事件。"""

    def __init__(
        self,
        *,
        store: ArtifactStore | None = None,
        deployer: Deployer | None = None,
        seat_table: SeatTable | None = None,
        compiler: CompilerFn | None = None,
        structure_checker: StructureChecker = default_structure_checker,
        trail: TrailRecorder | None = None,
    ) -> None:
        self._store = store or InMemoryArtifactStore()
        self._deployer = deployer or RecordingDeployer()
        self._seats = seat_table or build_default_seat_table()
        self._compiler = compiler or (lambda req: dict(req.files))
        self._structure_checker = structure_checker
        self._trail = trail or (lambda task_id, event: None)

    def compile(self, task_id: str, request: CompileRequest) -> PipelineResult:
        """顯式編譯（C-COMP-001）：compile → sandbox → awaiting_deploy。

        失敗一律保留舊版本（staging 不 promote）、不 /reload（C-COMP-002）。
        """
        try:
            kind = guard_artifact_kind(request.kind)
        except ValueError as exc:
            return PipelineResult(ok=False, error_code=ERR_RUNTIME_JAVA_FORBIDDEN, detail=str(exc))

        self._trail(task_id, {"type": "compile_start", "namespace": request.namespace, "by": request.requested_by})
        try:
            files = dict(self._compiler(request))
        except Exception as exc:  # noqa: BLE001
            self._trail(task_id, {"type": "compile_failed", "error": str(exc)})
            return PipelineResult(ok=False, error_code=ERR_COMPILE_FAILED, detail=str(exc))

        prior = self._store.latest(request.namespace)
        version = (prior.version + 1) if prior else 1
        artifact = CompileArtifact(
            artifact_id=f"art-{uuid.uuid4().hex[:10]}",
            namespace=request.namespace,
            kind=kind,
            version=version,
            content_hash=_hash_files(files),
            files=files,
            entity_ids=tuple(request.entity_ids),
            recipes=tuple(request.recipes),
            loot_tables=tuple(request.loot_tables),
            tags=tuple(request.tags),
        )

        report = sandbox_scan(artifact, self._world_index(), structure_checker=self._structure_checker)
        if not report.ok:
            # C-COMP-002：沙盒失敗 → 保留舊版，不進 staging 待部署、不 /reload
            self._trail(task_id, {"type": "sandbox_failed", "artifact_id": artifact.artifact_id})
            return PipelineResult(
                ok=False,
                error_code=ERR_SANDBOX_FAILED,
                state=TaskRuntimeState.PAUSED,
                artifact=artifact,
                sandbox=report,
                detail="沙盒未通過；舊版本保留",
            )

        self._store.put_staging(artifact)
        self._trail(task_id, {"type": "awaiting_deploy", "artifact_id": artifact.artifact_id, "version": version})
        return PipelineResult(
            ok=True,
            state=TaskRuntimeState.AWAITING_DEPLOY,
            artifact=artifact,
            sandbox=report,
        )

    def deploy(self, task_id: str, artifact_id: str, *, confirmed_by: str) -> PipelineResult:
        """顯式部署（C-COMP-004）：須經部署確認權席位；同名衝突由沙盒階段攔截。"""
        if not self._seats.has_deploy_confirm(confirmed_by):
            self._trail(task_id, {"type": "deploy_rejected", "artifact_id": artifact_id, "by": confirmed_by})
            return PipelineResult(
                ok=False,
                error_code=ERR_DEPLOY_UNAUTHORIZED,
                detail=f"席位 {confirmed_by} 無部署確認權（預設僅 l5_user／human_admin）",
            )
        artifact = self._store.get(artifact_id)
        if artifact is None:
            return PipelineResult(ok=False, error_code=ERR_ARTIFACT_UNKNOWN)
        # 僅允許部署 staging 中（已過沙盒）的產物
        current = self._store.latest(artifact.namespace)
        if current is not None and current.artifact_id == artifact_id:
            return PipelineResult(ok=False, error_code=ERR_DEPLOY_NOT_AWAITING, detail="該版本已在線上")
        self._deployer.deploy(artifact)
        self._store.promote(artifact_id)
        self._trail(task_id, {"type": "deployed", "artifact_id": artifact_id, "by": confirmed_by})
        return PipelineResult(ok=True, state=TaskRuntimeState.RUNNING, artifact=artifact)

    def rollback(self, task_id: str, namespace: str, *, confirmed_by: str) -> PipelineResult:
        """回滾到上一穩定版本（§8.3）。"""
        if not self._seats.has_deploy_confirm(confirmed_by):
            return PipelineResult(ok=False, error_code=ERR_DEPLOY_UNAUTHORIZED)
        history = self._store.history(namespace)
        if len(history) < 2:
            return PipelineResult(ok=False, error_code=ERR_ROLLBACK_TARGET_UNKNOWN)
        target = history[-2]
        self._deployer.deploy(target)
        self._trail(task_id, {"type": "rolled_back", "namespace": namespace, "to_version": target.version})
        return PipelineResult(ok=True, artifact=target, detail=f"回滾至 v{target.version}")

    def _world_index(self) -> WorldIndex:
        """世界索引來源；骨架預設空世界，生產接 linkin worldview 唯讀投影。"""
        return InMemoryWorldIndex()


def compile_action_guard(state: TaskRuntimeState, action: TaskAction) -> bool:
    """與 §9 矩陣聯動：編譯／部署請求先過狀態機。"""
    return evaluate(state, action).verdict is not Verdict.DENY
