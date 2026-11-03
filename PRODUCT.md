# 靈境·Linkin

> **Assumptions labeled:** 本次由「依 Impeccable 重構 UI」請求推斷；未跑完整 `/impeccable init` 訪談。事實以倉庫與 AGENTS.md 為準。

## Users

- 主要使用者：操作 AI 公司運行時／工業 OPC／Minecraft 世界模組的工程師與運維（inferred）
- 情境：長時間駐留的控制台——下任務、監看席位／管線、調模型與整合、審批寫入（inferred）

## Job to be done

用同一條 EvoLoop 管線（反思閉環＋公司指揮鏈＋OPC／MineMCP 護欄）完成複雜任務，並在監控中心清楚看見進度、風險與成本。

## Product principles

- 寫世界／OPC 必須經護欄；禁止繞過
- LLM 一律經 `call_llm`；UI 不假裝直連供應商
- 控制台是 Operate 表面：掃描優先於展示，品牌落在精準細節而非裝飾

## Constraints

- 平台：web（React 19 + Vite；本機前端 3001）
- 視覺世界（incumbent）：漆夜靈絲——近黑漆面、素紙墨色、金只作細絲焦點／主動作；見 `frontend/src/index.css` 與 `DESIGN.md`
- 既有 `DESIGN.md` 曾誤標 Linear 紫系；以程式 token 為準，已對齊刷新

## Voice and terminology

- 產品名：靈境·Linkin
- 活動欄用語：工作／觀測／計算／供給／資產／世界／設定
- 介面語言：繁中為主，en 可切換

## Stack

- Frontend: React 19, Vite, Tailwind CSS v4（`@import 'tailwindcss'`）
- Backend: FastAPI + LangGraph（本文件不約束後端 UI）

## Open questions

- 是否要為登入頁另開 Persuade 向視覺世界（目前與控制台共用漆夜）
- 品牌字體是否自架（目前 Google Fonts：Noto Sans TC / Noto Serif TC / JetBrains Mono）
