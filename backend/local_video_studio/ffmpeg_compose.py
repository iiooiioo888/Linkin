"""FFmpeg 合成。正式環境缺少 ffmpeg 或非 0 退出必須失敗，不寫假成片。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.local_video_studio.config import load_config
from backend.local_video_studio.storage import LocalPathStorage, get_storage

_FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 128
_SHA_CHUNK = 8 * 1024 * 1024
_META_PATH_KEYS = {
    "audio_relative_path",
    "audio_relative_paths",
    "subtitle_relative_path",
    "subtitles_relative_path",
    "fontfile",
}
_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
)


class ComposeError(RuntimeError):
    pass


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_SHA_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _escape_filter(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
        .replace(";", r"\;")
    )


def resolve_drawtext_font(explicit: str | None = None) -> Path:
    """顯式標識用字型。缺檔即失敗，不可略過 drawtext。"""
    chosen = (explicit or os.getenv("LVS_DRAWTEXT_FONT") or os.getenv("LVS_COMPLIANCE_FONT") or "")
    chosen = chosen.strip()
    if chosen:
        path = Path(chosen)
        if path.is_file():
            return path
        raise ComposeError(f"drawtext 字型不存在，拒絕略過顯式標識：{path}")
    for cand in _FONT_CANDIDATES:
        if cand.is_file():
            return cand
    joined = "、".join(str(item) for item in _FONT_CANDIDATES)
    raise ComposeError(f"drawtext 字型不存在，拒絕略過顯式標識：{joined}")


def build_ffmpeg_command(
    *,
    concat_path: Path,
    output_path: Path,
    audio_paths: list[Path],
    subtitle_path: Path | None,
    font_path: Path | None,
    watermark_text: str | None,
    metadata: dict[str, str],
) -> list[str]:
    """組出 SPEC §11 命令：字幕濾鏡、amix、音訊 -map、drawtext fontfile。"""
    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
    ]
    for audio in audio_paths:
        cmd += ["-i", str(audio)]

    filters: list[str] = []
    video_in = "0:v"
    if subtitle_path is not None:
        escaped = _escape_filter(subtitle_path.as_posix())
        filters.append(f"[{video_in}]subtitles=filename='{escaped}'[vsub]")
        video_in = "vsub"
    if watermark_text is not None:
        if font_path is None:
            raise ComposeError("drawtext 字型不存在，拒絕略過顯式標識")
        font = _escape_filter(font_path.as_posix())
        text = _escape_filter(watermark_text)
        filters.append(
            f"[{video_in}]drawtext=fontfile='{font}':text='{text}':"
            "x=w-tw-24:y=h-th-24:fontsize=28:fontcolor=white@0.8:box=1:boxcolor=black@0.4[v]"
        )
    elif video_in != "0:v":
        filters.append(f"[{video_in}]null[v]")

    if audio_paths:
        pads = "".join(f"[{idx}:a]" for idx in range(1, len(audio_paths) + 1))
        filters.append(
            f"{pads}amix=inputs={len(audio_paths)}:duration=longest:dropout_transition=0[a]"
        )

    if filters:
        cmd += ["-filter_complex", ";".join(filters)]
    if watermark_text is not None or subtitle_path is not None:
        cmd += ["-map", "[v]"]
    else:
        cmd += ["-map", "0:v"]
    if audio_paths:
        cmd += ["-map", "[a]"]

    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium"]
    if audio_paths:
        cmd += ["-c:a", "aac"]
    for key, value in metadata.items():
        cmd += ["-metadata", f"{key}={value}"]
    cmd.append(str(output_path))
    return cmd


def _as_path_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    return []


def _resolve_inputs(
    store: LocalPathStorage,
    *,
    audio_relative_paths: list[str] | None,
    subtitle_relative_path: str | None,
    metadata: dict[str, Any],
) -> tuple[list[Path], Path | None]:
    audios = list(audio_relative_paths or [])
    if not audios:
        audios = _as_path_list(metadata.get("audio_relative_paths"))
    if not audios:
        audios = _as_path_list(metadata.get("audio_relative_path"))
    subtitle = (subtitle_relative_path or "").strip()
    if not subtitle:
        raw_sub = metadata.get("subtitle_relative_path") or metadata.get("subtitles_relative_path")
        subtitle = str(raw_sub).strip() if raw_sub else ""

    audio_files: list[Path] = []
    for rel in audios:
        path = store.resolve(rel)
        if not path.is_file():
            raise ComposeError(f"音訊不存在：{rel}")
        audio_files.append(path)
    subtitle_file: Path | None = None
    if subtitle:
        subtitle_file = store.resolve(subtitle)
        if not subtitle_file.is_file():
            raise ComposeError(f"字幕不存在：{subtitle}")
    return audio_files, subtitle_file


def _container_metadata(metadata: dict[str, Any] | None, base: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    for key, value in (metadata or {}).items():
        if key in _META_PATH_KEYS or isinstance(value, (dict, list)):
            continue
        merged[str(key)] = str(value)
    return merged


def compose_shots(
    *,
    project_id: str,
    clip_relative_paths: list[str],
    output_name: str = "final_v1.mp4",
    add_watermark: bool = True,
    metadata: dict[str, Any] | None = None,
    storage: LocalPathStorage | None = None,
    audio_relative_paths: list[str] | None = None,
    subtitle_relative_path: str | None = None,
    fontfile: str | None = None,
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

    meta_in = dict(metadata or {})
    audio_files, subtitle_file = _resolve_inputs(
        store,
        audio_relative_paths=audio_relative_paths,
        subtitle_relative_path=subtitle_relative_path,
        metadata=meta_in,
    )
    text = cfg.compliance_text
    meta = _container_metadata(
        meta_in,
        {
            "ai_generated": "true",
            "ai_service": "local-video-studio",
            "ai_model": "wan2.2-5b;ltx-video",
        },
    )

    allow_fake = cfg.allow_fake_media
    ffmpeg_ok = _ffmpeg_available()
    if not ffmpeg_ok and not allow_fake:
        raise ComposeError("ffmpeg 不存在，拒絕寫入假成片")

    font_path: Path | None = None
    if ffmpeg_ok and add_watermark:
        # 有 ffmpeg 就必須燒上顯式標識；缺字型不得改走假成片。
        font_path = resolve_drawtext_font(fontfile or cfg.drawtext_font or None)

    if ffmpeg_ok:
        cmd = build_ffmpeg_command(
            concat_path=concat_path,
            output_path=out_path,
            audio_paths=audio_files,
            subtitle_path=subtitle_file,
            font_path=font_path,
            watermark_text=text if add_watermark else None,
            metadata=meta,
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            if out_path.exists():
                out_path.unlink()
            stderr = (proc.stderr or "")[-500:]
            if not allow_fake:
                raise ComposeError(f"ffmpeg 失敗（exit {proc.returncode}）：{stderr}")
            out_path.write_bytes(_FAKE_MP4)
            engine = "ffmpeg-fallback"
        else:
            engine = "ffmpeg"
            stderr = ""
    else:
        out_path.write_bytes(_FAKE_MP4)
        engine = "mock-bytes"
        stderr = ""

    raw_size = out_path.stat().st_size
    digest = _sha256_file(out_path)
    meta_path = store.resolve(f"projects/{project_id}/output/{Path(output_name).stem}.metadata.json")
    meta_doc = {
        **meta,
        "explicit_mark": add_watermark,
        "explicit_text": text,
        "engine": engine,
        "clips": clip_relative_paths,
        "sha256": digest,
        "bytes": raw_size,
    }
    meta_path.write_text(json.dumps(meta_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "relative_path": out_rel,
        "bytes": raw_size,
        "sha256": digest,
        "mime": "video/mp4",
        "engine": engine,
        "metadata": meta_doc,
        "stderr_tail": stderr,
    }
