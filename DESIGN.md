---
version: alpha
name: Linkin-lacquer-silk
description: "漆夜靈絲：近黑漆面控制台，素紙墨色字，金只作細絲（焦點、主動作、作用中導航）。Operate 模式優先掃描；禁止紫漸層、奶油底、側欄色條、漸層字。"

colors:
  canvas: "#0a0908"
  sidebar: "#12100e"
  surface: "#1b1815"
  surface-elevated: "#242019"
  hairline: "#322c26"
  hairline-strong: "#463f36"
  ink: "#f6f1e6"
  ink-muted: "#c8bfb0"
  ink-faint: "#9b9183"
  dim: "#2c2721"
  accent: "#e8c98a"
  accent-soft: "#9a7844"
  accent-ink: "#1c160e"
  success: "#6fa87f"
  info: "#7a92b8"
  warning: "#c9a961"
  danger: "#b88080"
  purple: "#9184b5"
  cyan: "#7aa8b8"

typography:
  brand:
    fontFamily: "Noto Serif TC, Songti TC, serif"
    fontSize: 15px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  display:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, sans-serif"
    fontSize: 22px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, sans-serif"
    fontSize: 15px
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.011em"
  body:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "-0.011em"
  caption:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, SF Mono, Consolas, monospace"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "0"

rounded:
  sm: 6px
  md: 10px
  lg: 14px

spacing:
  u: 8px
  u2: 16px
  u3: 24px
  u4: 32px
  u6: 48px

components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.md}"
    padding: 8px 14px
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: 6px 10px
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: 16px
---

## Overview

靈境·Linkin 控制台的視覺世界是**漆夜靈絲**：表面用實色漆（`#0a0908` 系），文字用素紙墨（`#f6f1e6`），金色（`#e8c98a`）只出現在焦點環、主 CTA、作用中導航細絲。這是 Operate 表面——資訊密度與掃描優先於裝飾。

權威來源：`frontend/src/index.css` 的 `--console-*` token。本檔取代舊的 Linear 紫系抄本。

## Colors

| Token | Hex | 用途 |
|-------|-----|------|
| canvas | `#0a0908` | 頁面底 |
| surface / elevated | `#1b1815` / `#242019` | 面板 |
| hairline | `#322c26` | 分隔 |
| ink / muted / faint | `#f6f1e6` / `#c8bfb0` / `#9b9183` | 字階 |
| accent | `#e8c98a` | 主動作與焦點 |

語意色（綠／藍／琥珀／危）只標狀態，不作背景洗色。禁止紫／青霓虹漸層當品牌。

## Typography

- UI：Noto Sans TC；品牌字偶用 Noto Serif TC
- 等寬：JetBrains Mono（僅代碼、計數、狀態碼）
- 正文 ≥13px；標題以字重／尺寸階拉開，勿用漸層字或全大寫 eyebrow

## Layout

- 8pt 網格（`--u`…`--u6`）
- 殼層：TopBar → ActivityBar | SidePanel | Main | RightPanel → StatusBar
- 相關緊、區塊鬆；不要卡片套卡片

## Elevation & Depth

- 靠邊線與實色面差分層，不用彩色零偏移光暈
- 焦點：`outline` 金色細環，非 glow shadow

## Shapes

- 半徑：控件 ~10px、大面板 ~14px；避免一切圓角 pill 當預設

## Components

- 主按鈕：金底深墨字
- 活動列作用中：左側 **2px** 實色細絲（非 3px 色條、無 glow）
- 任務卡／指標：用邊框色或背景差表示優先級，不用側欄色條

## Do's and Don'ts

**Do**

- 用 token，勿硬編 Tailwind gray／藍鏈結色
- 空狀態說清楚下一步
- 鍵盤焦點可見

**Don't**

- 漸層字、側欄 3px+ 色條、radial spotlight、彩色 glow
- 全大寫追蹤字 eyebrow 當區段標題
- emoji 當圖示系統
- 把 Linear／Inter／紫漸層帶回殼層
