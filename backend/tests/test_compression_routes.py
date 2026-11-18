"""上下文／提示詞壓縮路由：只轉呼叫既有規則函式。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.routers import compression as compression_routes
from backend.main import app
from backend.memory.context_compressor import compress, extract_decisions, summarize_trace
from backend.prompts.templates import truncate

client = TestClient(app)
ROUTER_SOURCE = Path(compression_routes.__file__).read_text(encoding="utf-8")


def test_routes_only_delegate_existing_helpers():
    assert "call_llm" not in ROUTER_SOURCE
    assert "optimize_prompt" not in ROUTER_SOURCE
    assert "/lab/prompt/optimize" not in ROUTER_SOURCE
    assert "context_bus" not in ROUTER_SOURCE


def test_compress_context_matches_helper():
    raw = "夜班交接。" * 40
    direct = compress(raw, 80)
    response = client.post("/context/compress", json={"text": raw, "limit": 80})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == direct
    assert "已壓縮" in body["text"]
    assert body["original_chars"] == len(raw)
    assert body["result_chars"] == len(direct)
    assert body["helper"] == "backend.memory.context_compressor.compress"


def test_compress_context_delegates(monkeypatch):
    def fake(text: str, limit: int = 720) -> str:
        return f"compressed:{limit}:{text}"

    monkeypatch.setattr(compression_routes, "compress", fake)
    response = client.post("/context/compress", json={"text": "鍋爐", "limit": 32})
    assert response.status_code == 200
    assert response.json()["text"] == "compressed:32:鍋爐"


def test_extract_decisions_matches_helper():
    raw = "決定改用代理池。其他閒聊。"
    response = client.post("/context/decisions", json={"text": raw, "limit": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["decisions"] == extract_decisions(raw, limit=3)
    assert body["helper"] == "backend.memory.context_compressor.extract_decisions"


def test_summarize_trace_matches_helper():
    payload = {
        "title": "爬蟲",
        "body": "因未加 Header 被封鎖，決定改用代理池。",
        "failure_reason": "IP 被封",
        "limit": 280,
    }
    response = client.post("/context/trace-summary", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == summarize_trace(
        title=payload["title"],
        body=payload["body"],
        failure_reason=payload["failure_reason"],
        limit=payload["limit"],
    )
    assert body["helper"] == "backend.memory.context_compressor.summarize_trace"


def test_truncate_prompt_matches_helper_and_keeps_both_ends():
    raw = f"開頭{'中' * 80}結尾"
    direct = truncate(raw, 20)
    response = client.post("/prompts/truncate", json={"text": raw, "max_chars": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == direct
    assert body["text"].startswith("開頭")
    assert body["text"].endswith("結尾")
    assert "省略" in body["text"]
    assert body["helper"] == "backend.prompts.templates.truncate"


def test_truncate_prompt_omitted_limit_uses_helper_default():
    raw = "短提示"
    response = client.post("/prompts/truncate", json={"text": raw})
    assert response.status_code == 200
    assert response.json()["text"] == truncate(raw, None)


def test_rejects_limit_below_helper_slice():
    response = client.post("/context/compress", json={"text": "甲", "limit": 16})
    assert response.status_code == 422


def test_rejects_oversized_text():
    response = client.post("/context/compress", json={"text": "甲" * 200_001})
    assert response.status_code == 422
