"""從後端狀態矩陣生成前端 ``frontend/src/lib/taskStateMatrix.ts`` 的 MATRIX 區塊。

來源（單一真相）：``backend/company/task_state_machine.py::export_matrix``
（TODO §9／C-UI-002）。

為什麼要生成而非手抄：前端原本手抄一份矩陣，缺了 15 個 ``*|l0_refresh``
格子；``evaluate()`` 對查不到的鍵**兜底回 ``allow``**，導致 UI 放行後端必然
拒絕的組合——違反 §3.4／C-UI-002「禁止前端自行放行後端會拒絕的組合」。

用法::

    cd /opt/linkin && PYTHONPATH=/opt/linkin .venv/bin/python -m backend.scripts.export_task_state_matrix

生成的區塊由 ``/* GENERATED:START */`` 與 ``/* GENERATED:END */`` 包夾，
區塊外的內容（型別、``inferRuntimeState`` 等手寫邏輯）原樣保留。
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from backend.company.task_state_machine import TaskAction, TaskRuntimeState, export_matrix

TARGET = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "taskStateMatrix.ts"

START = "/* GENERATED:START — 由 backend/scripts/export_task_state_matrix.py 產生，請勿手改 */"
END = "/* GENERATED:END */"


def _ts_str(value: str | None, *, omit_empty: bool = True) -> str:
    if value is None or (omit_empty and value == ""):
        return "null" if value is None else "''"
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _render_matrix_block(schema: str) -> str:
    matrix = export_matrix()
    lines: list[str] = []
    lines.append(START)
    lines.append(f"export const TASK_STATE_MATRIX_SCHEMA = {_ts_str(schema)} as const;")
    lines.append("")
    lines.append("export const TASK_RUNTIME_STATES = [")
    for s in TaskRuntimeState:
        lines.append(f"  {_ts_str(s.value)},")
    lines.append("] as const;")
    lines.append("")
    lines.append("export const TASK_ACTIONS = [")
    for a in TaskAction:
        lines.append(f"  {_ts_str(a.value)},")
    lines.append("] as const;")
    lines.append("")
    lines.append("export type TaskRuntimeState = (typeof TASK_RUNTIME_STATES)[number];")
    lines.append("export type TaskAction = (typeof TASK_ACTIONS)[number];")
    lines.append("")
    lines.append("export type Verdict = 'allow' | 'deny' | 'queue' | 'sequence';")
    lines.append("")
    lines.append("export type MatrixDecision = {")
    lines.append("  verdict: Verdict;")
    lines.append("  nextState?: TaskRuntimeState | null;")
    lines.append("  errorCode?: string;")
    lines.append("  note?: string;")
    lines.append("  buttonEnabled: boolean;")
    lines.append("};")
    lines.append("")
    lines.append("/** 後端 §9 矩陣完整匯出（鍵＝`state|action`）。 */")
    lines.append("export const MATRIX: Record<string, MatrixDecision> = {")
    for cell in sorted(matrix["cells"], key=lambda c: (c["state"], c["action"])):
        parts = [f"verdict: {_ts_str(cell['verdict'])}"]
        parts.append(
            f"nextState: {_ts_str(cell['next_state'])}"
            if cell["next_state"]
            else "nextState: null"
        )
        parts.append(f"errorCode: {_ts_str(cell['error_code'])}")
        if cell["note"]:
            parts.append(f"note: {_ts_str(cell['note'])}")
        parts.append(f"buttonEnabled: {'true' if cell['button_enabled'] else 'false'}")
        lines.append(f"  {_ts_str(cell['state'] + '|' + cell['action'])}: {{ {', '.join(parts)} }},")
    lines.append("};")
    lines.append(END)
    return "\n".join(lines)


def render(full_source: str) -> str:
    """把 ``full_source`` 中的生成區塊替換為最新內容，回傳新全文。"""
    schema = export_matrix()["schema"]
    block = _render_matrix_block(schema)
    if START in full_source and END in full_source:
        head, rest = full_source.split(START, 1)
        _, tail = rest.split(END, 1)
        return head + block + tail
    raise SystemExit(
        f"找不到生成區塊標記（{START[:40]}…）；請先確認 {TARGET} 結構。"
    )


def main() -> int:
    if not TARGET.exists():
        print(f"目標檔不存在：{TARGET}", file=sys.stderr)
        return 1
    src = io.open(TARGET, encoding="utf-8").read()
    new = render(src)
    if new == src:
        print(f"已是最新：{TARGET}")
        return 0
    io.open(TARGET, "w", encoding="utf-8").write(new)
    n = len(export_matrix()["cells"])
    print(f"已更新：{TARGET}（{n} 格）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
