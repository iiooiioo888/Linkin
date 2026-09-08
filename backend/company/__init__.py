"""EvoLoop 多代理人公司運行時（Phase 6+ 擴展）。

受 OpenOPC 啟發，提供：
- 任務拆分器（TaskDecomposer）—— 核心主功能模組
- 可自定義提示詞配置（PromptConfig）—— 所有 LLM 提示詞皆可覆蓋
- 組織架構與角色分工（Manager / Developer / Reviewer / Synthesizer）
- 預算感知模型路由（critical / reasoning / routine / summary 四級）
- 工作項狀態機（Planning → Execution → Review → Done）
- 依賴 DAG 平行執行與審查閘
- 組織記憶（per-role 經驗設定檔、共享 playbook）
- RAHO 遞歸對抗分層（L5→L4→L3→L2 下達，L1 獨立驗收，L0 滲透；強制質詢與熱馬桶圈上交）
"""