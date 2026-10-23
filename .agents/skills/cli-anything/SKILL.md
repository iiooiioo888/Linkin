---
name: cli-anything
description: 當使用者要找、查或列出 CLI-Anything 的軟體命令列時使用。透過 Linkin 工具 cli_hub 做 list、search、info、installed。安裝、更新、解除或啟動個別軟體必須先等使用者明確確認。
compatibility: 需要 cli-anything-hub（命令 cli-hub）。Linkin 只開放查目錄。
license: MIT
---

# CLI-Anything

上游 [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything)。套件是 `cli-anything-hub`（授權 MIT），命令是 `cli-hub`。

## Linkin 裡怎麼用

先說「使用 CLI-Anything 查目錄」，再呼叫工具。不要自己組 shell，也不要呼叫 `cli-hub install`。

```tool_call
{"tool": "cli_hub", "args": {"action": "search", "query": "gimp"}}
```

| action | 參數 | 做什麼 |
| --- | --- | --- |
| `list` | 無 | 依分類列出目錄裡的名稱 |
| `search` | `query` | 用名稱、說明或分類搜尋 |
| `info` | `name` | 看單一 CLI 的說明、版本與是否已裝 |
| `installed` | 無 | 只看本機已經裝好的 harness 名稱 |

## 停在確認

`install`、`update`、`uninstall`、`launch` 會改本機或啟動外部程式。Linkin 不執行這些動作。使用者點名要裝某一個時，先講名稱與用途，等使用者確認後，由使用者在本機執行 `cli-hub install <name>`。

目錄來自上游公開 registry。查詢失敗就回報原因。不要改權限、安全策略或核心目標。
