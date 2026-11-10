"""FFmpeg 合成（無 ffmpeg 時寫入假成片，仍須經 compliance.stamp）。"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.local_video_studio.config import load_config
from backend.local_video_studio.storage import LocalPathStorage, get_storage

_FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 128


class ComposeError(RuntimeError):
    pass


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def compose_shots(
    *,
    project_id: str,
    clip_relative_paths: list[str],
    output_name: str = "final_v1.mp4",
    add_watermark: bool = True,
    metadata: dict[str, Any] | None = None,
    storage: LocalPathStorage | None = None,
) -> dict[str, Any]:
    if not clip_relative_paths:
        raise ComposeError("至少需要一個鏡頭片段")
    store = storage or get_storage()
    store.ensure_project_dirs(project_id)
    cfg = load_config()
    out_rel = f"projects/{project_id}/output/{output_name}"
    out_path = store.resolve(out_rel)
    concat_rel = f"projects/{project_id}/output/concat.txt"
    concat_path = store.resolve(concat_rel)

    lines = []
    for rel in clip_relative_paths:
        abs_clip = store.resolve(rel)
        if not abs_clip.is_file():
            raise ComposeError(f"片段不存在：{rel}")
        lines.append(f"file '{abs_clip.as_posix()}'")
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    text = cfg.compliance_text
    meta = {
        "ai_generated": "true",
        "ai_service": "local-video-studio",
        "ai_model": "wan2.2-5b;ltx-video",
        **{k: str(v) for k, v in (metadata or {}).items()},
    }

    if _ffmpeg_available():
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
        ]
        if add_watermark:
            # 簡化：單路視訊 + drawtext
            filt = (
                f"drawtext=text='{text}':x=w-tw-24:y=h-th-24:"
                "fontsize=28:fontcolor=white@0.8:box=1:boxcolor=black@0.4"
            )
            cmd += ["-vf", filt]
        for key, value in meta.items():
            cmd += ["-metadata", f"{key}={value}"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            # 退回假檔，仍標示合規路徑
            out_path.write_bytes(_FAKE_MP4)
            engine = "ffmpeg-fallback"
            stderr = proc.stderr[-500:]
        else:
            engine = "ffmpeg"
            stderr = ""
    else:
        out_path.write_bytes(_FAKE_MP4)
        engine = "mock-bytes"
        stderr = ""

    raw = out_path.read_bytes()
    meta_path = store.resolve(f"projects/{project_id}/output/{Path(output_name).stem}.metadata.json")
    meta_doc = {
        **meta,
        "explicit_mark": add_watermark,
        "explicit_text": text,
        "engine": engine,
        "clips": clip_relative_paths,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    meta_path.write_text(json.dumps(meta_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "relative_path": out_rel,
        "bytes": len(raw),
        "sha256": meta_doc["sha256"],
        "mime": "video/mp4",
        "engine": engine,
        "metadata": meta_doc,
        "stderr_tail": stderr,
    }
