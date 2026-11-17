"""ComfyUI HTTP 客戶端（可指向 mock）。"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

import httpx


class ComfyClientError(RuntimeError):
    pass


class AgentShutdown(Exception):
    """等待 Comfy 期間收到停機訊號。呼叫端應釋放租約並退回佇列。"""


class ComfyClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._owns = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def upload_image(self, path: Path, name: str | None = None) -> dict[str, Any]:
        filename = name or path.name
        with path.open("rb") as fh:
            files = {"image": (filename, fh, "application/octet-stream")}
            resp = self._client.post("/upload/image", files=files)
        if resp.status_code >= 400:
            raise ComfyClientError(f"upload failed: {resp.status_code} {resp.text}")
        return resp.json()

    def submit_prompt(self, workflow: dict[str, Any], client_id: str) -> str:
        resp = self._client.post("/prompt", json={"prompt": workflow, "client_id": client_id})
        if resp.status_code >= 400:
            raise ComfyClientError(f"prompt failed: {resp.status_code} {resp.text}")
        data = resp.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ComfyClientError("prompt 回應缺 prompt_id")
        return str(prompt_id)

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/history/{prompt_id}")
        if resp.status_code >= 400:
            raise ComfyClientError(f"history failed: {resp.status_code} {resp.text}")
        return resp.json()

    def get_queue(self) -> dict[str, Any]:
        resp = self._client.get("/queue")
        if resp.status_code >= 400:
            raise ComfyClientError(f"queue failed: {resp.status_code} {resp.text}")
        data = resp.json()
        if not isinstance(data, dict):
            raise ComfyClientError("queue 回應不是物件")
        return data

    def wait_history(
        self,
        prompt_id: str,
        *,
        poll_interval: float = 0.05,
        timeout_sec: float = 30.0,
        stall_sec: float | None = 300.0,
        on_heartbeat: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """輪詢 history；可選偵測 /queue 停滯，並在等待期間送心跳。"""
        deadline = time.monotonic() + timeout_sec
        last_sig: tuple[str, int, int] | None = None
        stall_since: float | None = None
        missing_since: float | None = None
        while True:
            if on_heartbeat is not None:
                on_heartbeat(f"waiting prompt_id={prompt_id}")
            hist = self.get_history(prompt_id)
            completed = _history_entry(hist, prompt_id)
            if completed is not None:
                return completed
            if should_stop is not None and should_stop():
                raise AgentShutdown(f"shutdown while waiting for {prompt_id}")

            if stall_sec is not None:
                signature = _queue_signature(self.get_queue(), prompt_id)
                now = time.monotonic()
                if signature is None:
                    stall_since = None
                    last_sig = None
                    if missing_since is None:
                        missing_since = now
                    elif now - missing_since >= stall_sec:
                        raise ComfyClientError(
                            f"comfy /queue 停滯：{prompt_id} 不在 queue_running／queue_pending"
                        )
                elif signature == last_sig:
                    missing_since = None
                    if stall_since is None:
                        stall_since = now
                    elif now - stall_since >= stall_sec:
                        raise ComfyClientError(f"comfy /queue 停滯：{prompt_id} 佇列狀態未變化")
                else:
                    missing_since = None
                    stall_since = None
                    last_sig = signature

            now = time.monotonic()
            if now >= deadline:
                raise ComfyClientError(f"history timeout for {prompt_id} after {timeout_sec}s")
            time.sleep(min(poll_interval, max(0.0, deadline - now)))

    def fetch_output_bytes(self, filename: str) -> bytes:
        resp = self._client.get("/view", params={"filename": filename})
        if resp.status_code >= 400:
            raise ComfyClientError(f"view failed: {resp.status_code} {resp.text}")
        return resp.content


def new_client_id() -> str:
    return f"lvs-{uuid4().hex[:12]}"


def _history_entry(hist: dict[str, Any], prompt_id: str) -> dict[str, Any] | None:
    entry = hist.get(prompt_id)
    if isinstance(entry, dict):
        status = entry.get("status") or {}
        if status.get("completed") or entry.get("outputs"):
            return entry
    status_entry = hist.get("status")
    if isinstance(status_entry, dict) and status_entry.get("completed"):
        return status_entry
    return None


def _extract_prompt_id(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("prompt_id", "id"):
            if item.get(key):
                return str(item[key])
        return None
    if isinstance(item, (list, tuple)):
        if len(item) >= 2 and isinstance(item[1], str):
            return item[1]
        if item and isinstance(item[0], str):
            return str(item[0])
    return None


def _queue_signature(queue: dict[str, Any], prompt_id: str) -> tuple[str, int, int] | None:
    for bucket in ("queue_running", "queue_pending"):
        items = queue.get(bucket) or []
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            if _extract_prompt_id(item) != prompt_id:
                continue
            number = idx
            if isinstance(item, (list, tuple)) and item and isinstance(item[0], int):
                number = int(item[0])
            return (bucket, number, idx)
    return None
