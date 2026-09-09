"""EvoLoop 參數化 Prompt 模板（Task 1.2）。

四組核心模板：生成初始回答、自動評估、反思與建議、優化回答。
皆以 str.format 參數化，占位符以 {欄位名} 表示。
"""
import os

# 上下文截斷上限（字符數），可透過環境變數調整（優化 #14）
_MAX_CONTEXT_CHARS = int(os.getenv("EVOL_MAX_CONTEXT_CHARS", "6000"))
_MAX_ANSWER_CHARS = int(os.getenv("EVOL_MAX_ANSWER_CHARS", "4000"))


def truncate(text: str, max_chars: int | None = None) -> str:
    """截斷長文本，超過上限時保留頭尾並插入省略標記（優化 #14）。

    用於 prompt 注入前壓縮上下文，節省 token。
    """
    limit = max_chars or _MAX_CONTEXT_CHARS
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n...（省略 {len(text) - limit} 字）...\n" + text[-half:]

GENERATE_INITIAL_ANSWER_SYSTEM = (
    "你是一位專業、有同理心的客服與領域專家助手，"
    "回答務必準確、具體且可執行。"
)

GENERATE_INITIAL_ANSWER = """請根據以下資訊回答使用者問題。
{memory_context}
{history_context}
【使用者問題】
{query}

要求：
1. 回答需準確、具體、可執行
2. 若有參考經驗可借鑑，但不要照抄
3. 以使用者的語言回答

請直接給出你的回答："""

EVALUATE_ANSWER = """你是一位嚴格的回答品質審查員，請評估以下回答的品質。

【使用者問題】
{query}

【待評估回答】
{answer}

請從以下維度綜合評估（總分 0-10，10 為完美）：
- 準確性：是否正確回答問題
- 完整性：是否涵蓋關鍵要點
- 清晰度：表達是否清楚易懂
- 專業性與同理心

只輸出 JSON，不要輸出任何其他文字：
{{"score": <0到10的數字>, "strengths": "<優點>", "weaknesses": "<不足之處>"}}"""

REFLECT = """你是一位擅長反思與改進的專家。以下回答未達品質標準，請深入反思。

【使用者問題】
{query}

【目前的回答】（評分 {score}/10）
{answer}

【審查員評估】
{evaluation}

請：
1. 深入分析回答問題的根本原因
2. 給出具體、可執行的改進建議

只輸出 JSON，不要輸出任何其他文字：
{{"critique": "<根本原因分析>", "suggestion": "<具體改進建議>"}}"""

IMPROVE_ANSWER = """請根據反思結果，重寫出一份更好的回答。

【使用者問題】
{query}

【原始回答】
{answer}

【根本原因分析】
{critique}

【改進建議】
{suggestion}

要求：完整解決上述指出的所有問題，給出一份高品質的最終回答。

請直接給出改進後的回答："""

LENGTH_DIRECTIVE = """【輸出長度硬性要求】
上限 {max_chars} 字元，目前已有 {actual_chars} 字元，超出 {excess_chars} 字元。
必須在保留關鍵結論與可執行步驟的前提下精簡到上限以內：刪除鋪陳、合併列點、去掉重複範例。"""
