"""ComfyUI HTTP 客戶端（可指向 mock）。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


class ComfyClientError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._owns = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def __enter__(self) -> "ComfyClient":
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

    def wait_history(
        self,
        prompt_id: str,
        *,
        poll_interval: float = 0.05,
        timeout_sec: float = 30.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            hist = self.get_history(prompt_id)
            entry = hist.get(prompt_id) or hist.get("status")
            if isinstance(hist.get(prompt_id), dict):
                status = hist[prompt_id].get("status") or {}
                if status.get("completed") or hist[prompt_id].get("outputs"):
                    return hist[prompt_id]
            if isinstance(entry, dict) and entry.get("completed"):
                return entry
            time.sleep(poll_interval)
        raise ComfyClientError(f"history timeout for {prompt_id}")

    def fetch_output_bytes(self, filename: str) -> bytes:
        resp = self._client.get("/view", params={"filename": filename})
        if resp.status_code >= 400:
            raise ComfyClientError(f"view failed: {resp.status_code} {resp.text}")
        return resp.content


def new_client_id() -> str:
    return f"lvs-{uuid4().hex[:12]}"
