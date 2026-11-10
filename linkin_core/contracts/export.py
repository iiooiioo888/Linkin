"""把 OpenAPI、AsyncAPI 與 K8s 骨架寫進倉庫。"""

from __future__ import annotations

import json
from pathlib import Path

from linkin_core.contracts.asyncapi_doc import build_asyncapi
from linkin_core.contracts.k8s_skeleton import render_files
from linkin_core.contracts.openapi_doc import build_openapi

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = Path(__file__).resolve().parent
K8S_DIR = ROOT / "deploy" / "k8s" / "linkin"


def _dump_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def artifacts() -> dict[Path, str]:
    files = {
        CONTRACT_DIR / "openapi.json": _dump_json(build_openapi()),
        CONTRACT_DIR / "asyncapi.json": _dump_json(build_asyncapi()),
    }
    for name, text in render_files().items():
        files[K8S_DIR / name] = text
    return files


def write() -> list[Path]:
    written: list[Path] = []
    for path, text in artifacts().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    for path in write():
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
