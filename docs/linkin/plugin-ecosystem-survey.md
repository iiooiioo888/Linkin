# 上游插件生態盤點（TODO §6.1／§6.2）

> 盤點日期：2026-09-29　資料來源：`https://deepseek.club/plugins`、`https://github.com/topics/dsh-plugin`
> 對照契約：本專案「模組／插件」契約＝`backend/modules/`（registry + plugin_manager）
> ＋席位表白名單（`backend/company/seat_table.py` 的 `plugin_whitelist`／`PluginMountPolicy`）
> ＋審計軌跡（§6.3 降級不丟日誌）。

## 一、deepseek.club 插件市集（§6.1）

平台為「Plugin Hub／Harness Capability Center」，規模：

| 指標 | 數量 |
|---|---|
| DSH Plugins | 1068 |
| 生態工具（Eco Tools） | 12 |
| 分類 | 15 |
| 貢獻者 | 737 |

**15 個分類**：UI 增強、主題外觀、聊天與消息、記憶、工具與能力、技能包、工作流、通知、模型接入、開發與運行時、娛樂（另有 All／Community Verified／Community 篩選與 Downloads 排序）。

### 與本專案模組契約的適配判斷

| 市集分類 | 對應本專案契約面 | 適配價值 | 建議 |
|---|---|---|---|
| 🧠 記憶 | §4 L0 三核＋記憶注入 | **高** | 已由 MemOS／OpenViking 覆蓋；新插件走 `integrations` 召回層接入，不另開指揮鏈 |
| 🛠️ 工具與能力 | `backend/company/tools.py` ToolRegistry | **高** | 以 `<serverId>__<tool>` 前綴掛入（見 `mcp_clients.py`） |
| 🔁 工作流 | 協調器工作項 DAG | 中 | 須經協調器下發，禁止繞過（§2.3）；僅接受可表達為席位工具者 |
| 🧩 技能包 | `backend/company/skills.py`（注入角色 system_prompt） | **高** | 天然契合——技能庫即為「可重用知識注入」，可直接收編 |
| 🔌 模型接入 | `backend/core/api_router.py`／provider_pool | 低 | 本專案已鎖單一 token-plan key（`models_locked`），引入多廠商違反現行鎖定策略 |
| 🎨 UI 增強／🎭 主題 | 前端 `frontend/src` | 低 | 前端為自建 React SPA，外部 UI 插件無掛載點 |
| 💬 聊天與消息 | 對話殼 | 低 | 同上，自建實作 |
| 🔔 通知 | cron `hermes send` 推播 | 低 | 已由 Hermes 網關覆蓋 |
| 🧑‍💻 開發與運行時 | `opc_service`／編譯器 | 低 | 與 §8 MC 編譯器契約重疊，優先自建 |
| 🎮 娛樂 | 世界模組（Minecraft） | 中 | 可作為世界模組來源，須聲明最高可掛載層級（§2.4） |

**結論**：**記憶／工具／技能包**三類是高價值且契約已就緒的接入面；其餘分類或價值低、或與既有自建實作重疊。建議採「白名單顯式接入」，不啟用自動發現。

## 二、github.com/topics/dsh-plugin（§6.2）

該 topic 描述：DeepSeek Harness（DSH）是「agentic, plugin-based software development harness」，第三方插件以 host bundle ＋ 可選 client section 形式，**經 Cordis 註冊進 harness**。

### 主要倉庫與適配評估

| 倉庫 | 能力類型 | 授權／依賴 | 與本專案契約的關係 |
|---|---|---|---|
| `deepseek-ai/deepseek-harness` | harness 本體 | — | 上游框架；本專案為獨立 FastAPI+LangGraph，**非** harness 插件，無直接安裝關係 |
| `awesome-dsh-plugin/awesome-dsh-plugin` | 精選清單 | 清單 | **適合作為插件來源索引**，供白名單審核 |
| `MemTensor/MemOS` | 記憶 OS | 開源 | **已整合**（`linkin-memos` systemd + neo4j/qdrant/ollama） |
| `volcengine/OpenViking` | Context Database | 開源 | **已整合**（`openviking` systemd，127.0.0.1:1933） |
| `nexu-io/open-design` | 設計插件 | 開源 | 低相關；設計產出不由本專案管線承接 |
| `esengine/DeepSeek-Reasonix` | 終端 coding agent | 開源 | 低相關；與 Hermes 自身 agent 能力重疊 |
| `anywhere-labs/dsh-desktop`、`dataelement/dsh-desktop` | 桌面端 | 開源 | 無關（本專案為 Web） |
| `zhu1090093659/dsh-web` | Web 插件聚合生態 | 開源 | 無關 |
| `Molunerfinn/PicGo` | 圖片上傳 | 開源 | 無關 |
| `voyager-crew/voyager` | 瀏覽器增強套件 | 開源 | 無關（提示詞管理器與 Hermes skill 重疊） |

### 適配缺口

1. **註冊機制不同**：DSH 插件經 **Cordis** 註冊；本專案走 `backend/modules/registry.py` 的 `modules/<name>.py` 載入。二者無共同 ABI，**不存在直接安裝路徑**——只能語意對接（把插件能力包成席位工具）。
2. **依賴形態**：DSH 插件多為 npm/host bundle；本專案 `requirements-integrations.txt` 為獨立的可選依賴檔，正常部署不安裝。
3. **優先適配清單**（依契約就緒度排序）：
   1. `awesome-dsh-plugin` — 作為白名單來源索引，人工審核後納入
   2. 記憶類插件（MemOS 同族）— 走既有 `integrations/context_assembler.py` 召回面
   3. 技能包類 — 直接轉為 `backend/data/skills.json` 條目
   4. 工具類 — 經 `mcp_clients.py` 以 `<serverId>__<tool>` 掛入 ToolRegistry

## 三、接入護欄（不得鬆綁）

依 §2.4／§6.2／§6.4，任何插件接入必須：

- 在席位表 `plugin_whitelist` 中顯式列出（`plugin_id ∈ whitelist`）
- 通過 `SeatTable.check_plugin_mount()` 的**雙向校驗**：席位白名單 ∩ 插件聲明 `max_mount_layer` ∩ 席位 `max_plugin_source_level`
- 聲明**來源標籤**（`deepseek-club` / `dsh-plugin` / `world-module`）與 **pin 版本**
- 非白名單倉庫／未審核版本一律拒絕（C-PLUGIN-003）
- 降級／停用**不丟失**已記錄呼叫日誌（C-PLUGIN-002）
- 禁止自動安裝／啟用（C-PLUGIN-001）；僅顯式動作

## 四、未完成項

本盤點為**初步適配表**。以下需另行確認（非本文件可結案）：

- 1068 個插件的**逐項清單**未拉取（市集為動態載入，需逐一枚舉分類頁）
- 各倉庫的**授權條款**未逐一核實（表中僅記「開源」）
- `awesome-dsh-plugin` 的條目數與更新頻率未查
- 是否需為 DSH 插件寫 **shim**（類比 Yao／OpenPencil 的處置）待評估——目前判定為「不寫」，因兩者註冊機制無共同 ABI
