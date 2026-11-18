"""上下文與提示詞的規則壓縮。

每條路由只轉呼叫一個既有函式，不組新的模型管線。

- ``POST /context/compress`` → ``backend.memory.context_compressor.compress``
- ``POST /context/decisions`` → ``backend.memory.context_compressor.extract_decisions``
- ``POST /context/trace-summary`` → ``backend.memory.context_compressor.summarize_trace``
- ``POST /prompts/truncate`` → ``backend.prompts.templates.truncate``
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from backend.memory.context_compressor import compress, extract_decisions, summarize_trace
from backend.prompts.templates import truncate

router = APIRouter(tags=["compression"])

_MAX_TEXT = 200_000
_COMPRESS_HELPER = "backend.memory.context_compressor.compress"
_DECISIONS_HELPER = "backend.memory.context_compressor.extract_decisions"
_SUMMARY_HELPER = "backend.memory.context_compressor.summarize_trace"
_TRUNCATE_HELPER = "backend.prompts.templates.truncate"


def _bound_text(value: str) -> str:
    if len(value) > _MAX_TEXT:
        raise ValueError(f"文字超過 {_MAX_TEXT} 字")
    return value


class CompressContextRequest(BaseModel):
    text: str = ""
    limit: int = Field(default=720, ge=17, le=20_000)

    @field_validator("text")
    @classmethod
    def text_within_cap(cls, value: str) -> str:
        return _bound_text(value)


class ExtractDecisionsRequest(BaseModel):
    text: str = ""
    limit: int = Field(default=5, ge=1, le=50)

    @field_validator("text")
    @classmethod
    def text_within_cap(cls, value: str) -> str:
        return _bound_text(value)


class SummarizeTraceRequest(BaseModel):
    title: str = ""
    body: str = ""
    failure_reason: str = ""
    limit: int = Field(default=280, ge=17, le=20_000)

    @field_validator("title", "body", "failure_reason")
    @classmethod
    def text_within_cap(cls, value: str) -> str:
        return _bound_text(value)


class TruncatePromptRequest(BaseModel):
    text: str = ""
    max_chars: int | None = Field(default=None, ge=1, le=100_000)

    @field_validator("text")
    @classmethod
    def text_within_cap(cls, value: str) -> str:
        return _bound_text(value)


@router.post("/context/compress")
async def compress_context(body: CompressContextRequest):
    """規則截斷上下文。對應 ``context_compressor.compress``。"""
    text = compress(body.text, body.limit)
    return {
        "text": text,
        "original_chars": len(body.text),
        "result_chars": len(text),
        "helper": _COMPRESS_HELPER,
    }


@router.post("/context/decisions")
async def extract_context_decisions(body: ExtractDecisionsRequest):
    """抽出帶決策語意的句子。對應 ``context_compressor.extract_decisions``。"""
    decisions = extract_decisions(body.text, limit=body.limit)
    return {"decisions": decisions, "helper": _DECISIONS_HELPER}


@router.post("/context/trace-summary")
async def summarize_context_trace(body: SummarizeTraceRequest):
    """一筆記憶軌跡的壓縮摘要。對應 ``context_compressor.summarize_trace``。"""
    summary = summarize_trace(
        title=body.title,
        body=body.body,
        failure_reason=body.failure_reason,
        limit=body.limit,
    )
    return {"summary": summary, "helper": _SUMMARY_HELPER}


@router.post("/prompts/truncate")
async def truncate_prompt(body: TruncatePromptRequest):
    """提示詞頭尾截斷。對應 ``prompts.templates.truncate``，不改寫用詞。"""
    text = truncate(body.text, body.max_chars)
    return {
        "text": text,
        "original_chars": len(body.text),
        "result_chars": len(text),
        "helper": _TRUNCATE_HELPER,
    }
