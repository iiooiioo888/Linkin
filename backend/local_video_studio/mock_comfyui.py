"""Mock ComfyUI：/prompt、/history、/upload/image、/view（測試／CI 用）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response

# 假 PNG／MP4 位元組（足夠寫入與 sha256）
_FAKE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
_FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64


def create_mock_comfy_app(*, output_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="mock-comfyui")
    state: dict[str, Any] = {"history": {}, "uploads": {}, "outputs": {}}
    out_root = output_dir or Path("/tmp/lvs-mock-comfy")
    out_root.mkdir(parents=True, exist_ok=True)

    @app.post("/upload/image")
    async def upload_image(image: UploadFile = File(...)) -> dict[str, Any]:
        raw = await image.read()
        name = image.filename or f"upload-{uuid4().hex[:8]}.png"
        path = out_root / name
        path.write_bytes(raw or _FAKE_PNG)
        state["uploads"][name] = str(path)
        return {"name": name, "subfolder": "", "type": "input"}

    @app.post("/prompt")
    async def prompt(body: dict[str, Any]) -> dict[str, Any]:
        prompt_id = uuid4().hex
        # 依 workflow 粗略判斷輸出類型
        workflow = body.get("prompt") or {}
        is_video = False
        for node in workflow.values() if isinstance(workflow, dict) else []:
            class_type = (node or {}).get("class_type", "")
            if "Video" in class_type or "SaveVideo" in class_type or "VHS" in class_type:
                is_video = True
                break
        filename = f"mock_{prompt_id[:8]}.{'mp4' if is_video else 'png'}"
        payload = _FAKE_MP4 if is_video else _FAKE_PNG
        (out_root / filename).write_bytes(payload)
        state["outputs"][filename] = payload
        state["history"][prompt_id] = {
            "status": {"completed": True, "status_str": "success"},
            "outputs": {
                "9": {
                    "images" if not is_video else "gifs": [
                        {"filename": filename, "subfolder": "", "type": "output"}
                    ]
                }
            },
        }
        return {"prompt_id": prompt_id, "number": 1}

    @app.get("/history/{prompt_id}")
    async def history(prompt_id: str) -> dict[str, Any]:
        entry = state["history"].get(prompt_id)
        if entry is None:
            return {}
        return {prompt_id: entry}

    @app.get("/queue")
    async def queue() -> dict[str, Any]:
        return {"queue_running": [], "queue_pending": []}

    @app.get("/view")
    async def view(filename: str) -> Response:
        data = state["outputs"].get(filename)
        if data is None:
            path = out_root / filename
            if path.is_file():
                data = path.read_bytes()
        if data is None:
            return Response(status_code=404)
        media = "video/mp4" if filename.endswith(".mp4") else "image/png"
        return Response(content=data, media_type=media)

    app.state.mock = state  # type: ignore[attr-defined]
    return app
