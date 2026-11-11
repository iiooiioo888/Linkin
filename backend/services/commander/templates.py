"""L2 角色模板目錄（自 backend.services.commander 抽出）。

TEMPLATE_HINTS／TEMPLATE_META 與爬蟲相關模板集合。
"""

from __future__ import annotations

TEMPLATE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("核准來源", "備援", "上傳清單"), "file_ingest"),
    (("價格", "官網", "爬取", "url", "訂價"), "web_scraper"),
    (("社群", "提及", "社交", "社群媒體"), "social_listener"),
    (("pdf", "表格", "第三頁"), "pdf_extractor"),
    (("威脅", "融合", "合成", "彙整"), "data_synthesizer"),
    (("swot",), "swot"),
    (("文案", "landing", "cta"), "copy"),
    (("程式", "實作", "code", "api"), "code"),
    (("審查", "review"), "review"),
]


CRAWL_TOOLS = frozenset({"web_fetch", "web_search"})


CRAWL_TEMPLATES = frozenset({"web_scraper", "social_listener"})


TEMPLATE_META: dict[str, dict[str, str]] = {
    "web_scraper": {
        "name": "價格偵查員",
        "trait": "只信頁面原文，禁止臆測",
        "tools": "web_fetch,json_formatter",
        "schema": "List[Dict[str, str]]",
        "example": '[{"product": "A", "price": 100}]',
        "fallback": "若頁面載入失敗，請重試一次，若仍失敗，輸出空陣列 []，不要編造數據。",
        "success": "產出 JSON 中至少包含 5 筆有效產品",
        "input_hint": "url_list.csv",
    },
    "social_listener": {
        "name": "社群監聽員",
        "trait": "只計可核對的公開提及，禁止灌水",
        "tools": "web_search,json_formatter",
        "schema": "List[Dict[str, str]]",
        "example": '[{"source": "X", "mentions": "12"}]',
        "fallback": "來源不可用則輸出空陣列，禁止臆測提及數。",
        "success": "每列含來源與可核對的提及數",
        "input_hint": "social_targets.csv",
    },
    "pdf_extractor": {
        "name": "表格提取員",
        "trait": "只抽指定頁表格，禁止補值",
        "tools": "read_file,python_exec",
        "schema": "List[Dict[str, str]]",
        "example": '[{"col": "值"}]',
        "fallback": "頁面或表格不存在則輸出 []，禁止補值。",
        "success": "表格列完整且不編造",
        "input_hint": "source.pdf",
    },
    "data_synthesizer": {
        "name": "商業威脅分析師",
        "trait": "只融合 input_ref，禁止外推",
        "tools": "read_memory,text_analyzer",
        "schema": "Plain Text (Max 200 chars)",
        "example": "威脅等級：中。應對：守住底線價並準備對照表。",
        "fallback": "嚴禁提及任何未在輸入 JSON 中的數據。輸入缺失則暫停並 [GRILL]。",
        "success": "明確包含『高/中/低』判定",
        "input_hint": "",
    },
    "swot": {
        "name": "SWOT 分析員",
        "trait": "缺證據必須標『證據不足』",
        "tools": "read_memory,text_analyzer",
        "schema": "四象限表格",
        "example": "S/W/O/T 各 ≤ 5 條",
        "fallback": "缺證據的象限留空並標註「證據不足」。",
        "success": "四象限皆標註證據或『證據不足』",
        "input_hint": "",
    },
    "copy": {
        "name": "文案員",
        "trait": "只寫可上線三件套，禁止空話",
        "tools": "text_analyzer",
        "schema": "標題 + 正文 + CTA",
        "example": "標題／正文／CTA 三行",
        "fallback": "素材不足則只交標題草案並標註缺口。",
        "success": "含標題與 CTA",
        "input_hint": "",
    },
    "code": {
        "name": "實作員",
        "trait": "只交可運行最小交付",
        "tools": "read_file,python_exec",
        "schema": "完整程式碼或 diff",
        "example": "",
        "fallback": "規格不足則輸出 [GRILL] 而非猜測實作。",
        "success": "可運行的最小交付",
        "input_hint": "",
    },
    "review": {
        "name": "審查員",
        "trait": "只打可執行缺陷，禁止滿分敷衍",
        "tools": "read_memory",
        "schema": "分數 + 缺陷清單",
        "example": "分數: 0-100；缺陷: []",
        "fallback": "交付物缺失則退回，不給滿分。",
        "success": "含分數與可執行缺陷",
        "input_hint": "",
    },
    "file_ingest": {
        "name": "核准來源擷取員",
        "trait": "只讀核准來源，禁止爬蟲與編造",
        "tools": "read_file,json_formatter",
        "schema": "List[Dict[str, str]]",
        "example": '[{"product": "A", "price": "100"}]',
        "fallback": "檔案不存在或欄位缺失則輸出 []，禁止編造，並以 [GRILL] 回報缺口。",
        "success": "產出 JSON 至少含有效列，且未使用爬蟲",
        "input_hint": "price_source.csv",
    },
    "generic": {
        "name": "原子執行員",
        "trait": "只做一件事，規格不足則 [GRILL]",
        "tools": "read_memory",
        "schema": "依任務指定",
        "example": "",
        "fallback": "規格不足則 [GRILL]，禁止擴寫範圍。",
        "success": "單一交付物符合 output_schema",
    },
}
