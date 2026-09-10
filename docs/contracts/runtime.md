# 運行時契約（Runtime Contracts）

> 由 `TODO.md` 各章「禁止／必須」條款抽出，供 CI 靜態檢查與 pytest 不變式對照。
> 格式寫死（TODO 附錄）：每條契約可映射到具體測試／lint；**P0 契約測試失敗則阻斷合併**，P1／P2 分階段開啟。
>
> 適用範圍：單用戶／單租戶；多租戶隔離策略另文定義。

## CONTRACT-ID: C-AUDIT-001
- **條款**: 禁止在串流 done 事件／聊天完成 webhook／插件回調中自動觸發審計或灌入審計分數
- **來源**: TODO §1.2／§1.4
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_audit_001_no_auto_audit_entrypoint
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-AUDIT-002
- **條款**: 審計前必經「等待 inflight 自然完成 → paused → auditing」，禁止強制 abort／kill 串流
- **來源**: TODO §1.3
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_audit_002_pause_before_audit_sequence
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-AUDIT-003
- **條款**: 審計失敗預設保持 `paused`，由用戶顯式選擇恢復或放棄；禁止靜默寫入假分數
- **來源**: TODO §1.4
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_audit_003_failure_keeps_paused_no_fake_score
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-AUDIT-004
- **條款**: 暫停凍結快照之插件集合雜湊輸入＝插件 ID＋pin 版本＋啟用狀態；僅升版即視為快照變更
- **來源**: TODO §1.5
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_audit_004_plugin_hash_includes_pin_version
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-AUDIT-005
- **條款**: 審計軌跡 append-only；審計流程只讀軌跡；清理為顯式管理動作且本身可審計
- **來源**: TODO §1.6
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_audit_005_trail_is_append_only_and_purge_audited
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-AUDIT-006
- **條款**: 恢復前校驗快照版本；衝突 → `awaiting_confirmation`＋差異摘要，用戶顯式「重綁／放棄」後才可離開
- **來源**: TODO §1.5／§9.1
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_audit_006_resume_conflict_goes_awaiting_confirmation
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-SEAT-001
- **條款**: 席位表帶 `schema_version`；席位表變更時進行中任務凍結或走顯式遷移，禁止靜默改寫 DAG
- **來源**: TODO §2.4
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_seat_001_schema_version_and_freeze_on_change
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-SEAT-002
- **條款**: 部署確認權預設僅 L5 用戶與人類管理員；任何角色席位不得預設持有
- **來源**: TODO §2.2／§8.2
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_seat_002_deploy_confirm_defaults_to_l5_and_human_only
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-SEAT-003
- **條款**: L0 注入席只做注入：無工具、無插件白名單、不執行任務、不直連 MCP
- **來源**: TODO §2.2／§4.1
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_seat_003_l0_has_no_tools_or_plugins
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-SEAT-004
- **條款**: 插件掛載須通過「席位白名單 ∩ 插件最高可掛載層級 ∩ 席位來源層級上限」雙向校驗
- **來源**: TODO §2.4／§6.4
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_seat_004_plugin_mount_level_cap
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-SEAT-005
- **條款**: 工作項只經協調器下發；繞過指揮鏈的直連路徑（含插件捷徑）在 CI／運行時守衛可偵測並拒絕
- **來源**: TODO §2.3／§2.5
- **優先級**: P0
- **驗證**: lint::no_orchestrator_bypass（`backend/scripts/lint_contracts.py`）＋ pytest::backend/tests/test_contracts.py::test_contract_c_seat_005_lint_no_orchestrator_bypass
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-SEAT-006
- **條款**: L1 攔截後執行席不得自行推翻；爭議升級至 L5 或人工干預並留可觀測記錄
- **來源**: TODO §2.4
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_seat_006_l1_dispute_goes_to_l5_not_executor（實作：`backend/company/raho/arbitration.py`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-STATE-001
- **條款**: 狀態矩陣所有 `✗` 路徑必附可觀測錯誤碼，且不改變既有凍結快照
- **來源**: TODO §9.1
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_state_001_every_denial_has_error_code
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-STATE-002
- **條款**: 審計中禁止 L0 刷新與插件集合變更（凍結快照）
- **來源**: TODO §9.1
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_state_002_auditing_freezes_snapshot_and_plugins
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-STATE-003
- **條款**: `l0_refreshing` 下審計請求佇列；刷新完成後自動進入 `paused → auditing`
- **來源**: TODO §9
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_state_003_l0_refreshing_audit_is_queued
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-STATE-004
- **條款**: 編譯／沙盒中一律拒絕審計；編譯結束後可審計含編譯記錄的完整軌跡
- **來源**: TODO §9.1
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_state_004_compiling_denies_audit_and_deploy
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-STATE-005
- **條款**: 所有 `✗`／`Q` 路徑不產生狀態遷移（保護凍結快照）
- **來源**: TODO §9.1
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_state_005_denial_never_transitions
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-STATE-006
- **條款**: `awaiting_deploy` 下 `pause` 僅暫停任務生命週期；部署審批流程獨立
- **來源**: TODO §9.1
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_state_006_awaiting_deploy_pause_semantics
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-COMP-001
- **條款**: 編譯／部署僅能顯式觸發；沙盒通過才進入待部署；編譯成功 ≠ 自動部署
- **來源**: TODO §8.2
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_comp_001_explicit_compile_and_sandbox_gate
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-COMP-002
- **條款**: 編譯／沙盒失敗保留舊版本，禁止自動 `/reload` 或強制熱更新
- **來源**: TODO §8.3
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_comp_002_failure_keeps_old_version_no_reload
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-COMP-003
- **條款**: 產物形態優先級 Datapack＋Resource Pack > Schematic > 預編譯橋接層；禁止運行時生成／編譯 Java
- **來源**: TODO §8.6
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_comp_003_runtime_java_forbidden
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-COMP-004
- **條款**: 部署前須經部署確認權席位確認；確認動作可審計
- **來源**: TODO §8.2
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_comp_004_deploy_requires_confirm_seat
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-COMP-005
- **條款**: 沙盒衝突掃描至少涵蓋命名空間／實體 ID／配方／戰利品表／標籤覆蓋；同名衝突拒絕覆蓋
- **來源**: TODO §8.2／§8.3
- **優先級**: P0
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_comp_005_sandbox_scans_five_conflict_kinds
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-L0-001
- **條款**: 三核管線預設「記憶整理 → 知識圖譜 → 態勢偏置」；可單獨旁路且下游有降級輸入＋路由原因碼
- **來源**: TODO §4.3
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_l0_001_pipeline_bypass_and_reason_codes（實作：`backend/company/raho/l0_pipeline.py`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-L0-002
- **條款**: 注入前脱敏：禁止原始密鑰／憑證／未授權 PII 寫入注入片段
- **來源**: TODO §4.3
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_l0_002_injection_redaction（`l0_pipeline.redact`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-L0-003
- **條款**: 壓力指標預設等權歸一化，且必須實際驅動三核注入強度（禁止死數字）
- **來源**: TODO §4.4
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_l0_003_pressure_drives_injection_strength（`compute_pressure`／`injection_strength`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-L0-004
- **條款**: 敘事核心不得維護第二套可寫世界觀圖譜；臨時工作區帶 `workspace_id` 且關聯 L0 `snapshot_id`；快照變更預設進 `awaiting_confirmation`
- **來源**: TODO §4.7
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_l0_004_narrative_workspace_no_dual_write（實作：`backend/linkin/narrative_workspace.py`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-LLM-001
- **條款**: LLM 一律經 `backend.core.llm.call_llm`；禁止插件直連模型供應商 SDK
- **來源**: TODO §5.5／§6.2（AGENTS.md 關鍵約束 #1）
- **優先級**: P0
- **驗證**: lint::no_direct_provider_sdk（`backend/scripts/lint_contracts.py`）＋ pytest::backend/tests/test_contracts.py::test_contract_c_llm_001_lint_no_direct_provider_sdk
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-LLM-002
- **條款**: 可程式化決策（暫停／審計／扣預算／啟用插件／部署）不得交由 LLM；短路須有路由原因碼
- **來源**: TODO §5.2／§5.6
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_llm_002_route_reason_codes（實作：`backend/core/decision_router.py`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-LLM-003
- **條款**: 快取分類型 TTL；審計／憲兵路徑預設旁路或 TTL=0，不得誤傷新鮮上下文
- **來源**: TODO §5.3
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_llm_003_cache_bypass_audit_paths（實作：`backend/core/typed_llm_cache.py`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-LLM-004
- **條款**: 小模型輸出經啟發式評估；不達標升級大模型且有次數上限與成本觀測
- **來源**: TODO §5.5
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_llm_004_small_model_escalation_cap（實作：`backend/core/small_model_router.py`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-PLUGIN-001
- **條款**: 插件安裝／啟用為顯式動作；禁止串流完成或聊天 webhook 自動安裝／啟用
- **來源**: TODO §6.3
- **優先級**: P2
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_plugin_001_no_auto_plugin_install（實作：`backend/modules/plugin_manager.py`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-PLUGIN-002
- **條款**: 插件降級／停用不得丟失已記錄呼叫日誌；審計讀取持久化軌跡，與插件可用性無關
- **來源**: TODO §6.3
- **優先級**: P2
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_plugin_002_plugin_degrade_keeps_trail（實作：`backend/modules/plugin_manager.py`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-PLUGIN-003
- **條款**: dsh-plugin 預設手動 pin 版本；僅白名單倉庫／已審核版本；禁止執行未審核遠端腳本
- **來源**: TODO §6.2／§6.3
- **優先級**: P2
- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_plugin_003_dsh_plugin_pin_default（實作：`backend/modules/plugin_manager.py`）
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-UI-001
- **條款**: 審計結果不佔常駐狀態列分數槽；側欄預設折疊（主一席＋動作類型＋預算進度條）
- **來源**: TODO §3.3
- **優先級**: P2
- **驗證**: e2e::core-flow.spec.ts（規劃中擴充）
- **狀態**: ❌ 未實現

## CONTRACT-ID: C-UI-002
- **條款**: UI 按鈕可用性以後端 §9 矩陣為準；禁止前端自行放行後端會拒絕的組合
- **來源**: TODO §9.2
- **優先級**: P2
- **驗證**: e2e::state-matrix-buttons（規劃中）
- **狀態**: ❌ 未實現

## CONTRACT-ID: C-INTEG-001
- **條款**: 外部整合（MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil）一律 fail-open；每次呼叫寫審計軌跡並附原因碼
- **來源**: 整合層設計（`backend/integrations/base.py`）
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_integrations.py::test_base_unreachable_fails_open_with_reason_code 等
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-INTEG-002
- **條款**: 整合啟用為顯式動作（環境變數或 `POST /integrations/{name}/toggle`）；未啟用時禁止發出任何網路請求
- **來源**: C-PLUGIN-001 精神延伸
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_integrations.py::test_base_disabled_is_fail_closed_without_network
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-INTEG-003
- **條款**: 召回片段注入 prompt 前必經脱敏（C-L0-002）；審計路徑召回快取一律旁路（C-LLM-003）
- **來源**: TODO §4.3／§5.3
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_integrations.py::test_assembler_redacts_secrets_before_injection、test_assembler_audit_path_bypasses_recall_cache
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-INTEG-004
- **條款**: Ouroboros ambiguity > 0.2 時本地閘門阻擋 Seed 生成（僅顯式 force 可過）；三階段評估任一失敗即短路
- **來源**: Ouroboros 官方 gate 語義
- **優先級**: P1
- **驗證**: pytest::backend/tests/test_integrations.py::test_ouroboros_ambiguity_gate_blocks_above_threshold、test_ouroboros_start_auto_blocked_locally_without_remote_call、test_ouroboros_evaluate_short_circuits_on_stage_failure
- **狀態**: ✅ 已實現

## CONTRACT-ID: C-PERF-001
- **條款**: P95 預設上限（可配置）：L0 `/refresh` 3s、插件啟停 2s、編譯管線（stub）5s、審計（無 LLM）1s
- **來源**: TODO §7.2
- **優先級**: P2
- **驗證**: pytest::test_perf_budget_stubbed_clock（規劃中）
- **狀態**: ❌ 未實現
