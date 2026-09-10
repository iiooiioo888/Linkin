"""寫入示範資料：60 任務、60 推理軌跡、60 知識庫條目。

不呼叫 LLM／嵌入 API。知識庫以固定維度假向量寫入 Chroma；
失敗時降級寫入 JSON 記憶檔。
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RUN_DIR = DATA / "company_runs"
TRACE_DIR = DATA / "traces"
JSON_MEMORY = DATA / "memory_store.json"

N = 60

ROLES = [
    "manager",
    "ai_lead",
    "architect",
    "creative_lead",
    "finance_lead",
    "growth_lead",
    "industrial_lead",
    "developer",
    "reviewer",
    "synthesizer",
    "js_dev",
    "backend_dev",
    "tester",
    "devops",
    "knowledge_mgr",
    "memory_curator",
    "hub_operator",
    "github_ops",
    "quant_analyst",
    "opc_engineer",
]

STATUSES_CYCLE = [
    "executing",
    "ready",
    "in_review",
    "done",
    "blocked",
    "rework",
    "planning",
    "done",
    "done",
    "executing",
]

TASK_TITLES = [
    "角色總覽卡片對齊與溢出修正",
    "左側導覽加入角色層級跳轉",
    "監控偏好：活躍／告警篩選改為分段控制",
    "DeepSeek 健康探針失敗後關閉模型",
    "Hub 目錄代碼一致性檢查",
    "公司任務看板即時推播",
    "審查回饋寫入角色記憶",
    "知識庫 runbook 去重與過期清理",
    "OPC 感知鏈路延遲告警",
    "StocksX 回測報告整合",
    "StoryForge 章節節奏校稿",
    "GitHub Release 變更紀錄產生",
    "Hub 路由權重與熔斷演練",
    "前端 3001 熱重載與快取失效",
    "任務列表虛擬捲動效能",
    "無障礙鍵盤焦點順序",
    "繁中文案與狀態徽章對照",
    "Docker 沙箱成本分攤",
    "阿里雲用量日結",
    "API 契約 OpenAPI 對齊",
]

TASK_GOALS = [
    "把角色工作台操作邏輯整理成可跳轉、可篩選的 consule 流程",
    "補齊監控降級與目錄完整性，避免匯入即崩潰",
    "讓示範資料足以撐滿卡片、列表與軌跡頁",
    "把成本拆成 API／Docker／雲，卡片不再只顯示一個 $0",
    "推理軌跡要能對應到具體工作項與角色",
]


def _now(i: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=3 * i)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def seed_tasks() -> Path:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    run_id = "demo60"
    path = RUN_DIR / f"run_{run_id}.jsonl"
    lines: list[str] = []
    for i in range(N):
        ts = _now(i)
        role = ROLES[i % len(ROLES)]
        title = f"{TASK_TITLES[i % len(TASK_TITLES)]} #{i + 1:02d}"
        status_event = "work_item_done" if STATUSES_CYCLE[i % len(STATUSES_CYCLE)] == "done" else (
            "work_item_error" if STATUSES_CYCLE[i % len(STATUSES_CYCLE)] == "blocked" else "work_item_start"
        )
        rec = {
            "ts": _iso(ts),
            "run_id": run_id,
            "event": status_event,
            "item_id": f"demo-item-{i + 1:02d}",
            "title": title,
            "assignee": role,
            "goal": TASK_GOALS[i % len(TASK_GOALS)],
            "cost": round(0.002 + (i % 17) * 0.0013, 4),
            "phase": "execute_review",
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
        if status_event == "work_item_start" and i % 4 == 0:
            lines.append(
                json.dumps(
                    {
                        "ts": _iso(ts + timedelta(seconds=8)),
                        "run_id": run_id,
                        "event": "review_pass" if i % 3 else "review_rework",
                        "item_id": rec["item_id"],
                        "title": title,
                        "assignee": "reviewer",
                        "score": 7.5 + (i % 5) * 0.4,
                    },
                    ensure_ascii=False,
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _thought(i: int, title: str) -> str:
    return (
        f"步驟 1：釐清「{title}」的成功條件與現況差距。\n"
        f"步驟 2：對照角色層級與依賴，避免一次改太多表面。\n"
        f"步驟 3：假設 #{i + 1} 的瓶頸在資訊架構而非樣式。\n"
        f"步驟 4：先給可操作的跳轉／篩選，再補示範資料撐滿列表。\n"
        f"步驟 5：檢查降級路徑：目錄不一致、探針失敗、空看板。"
    )


def seed_reasoning() -> int:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    for i in range(N):
        task_id = f"demo-reason-{i + 1:02d}"
        title = f"{TASK_TITLES[i % len(TASK_TITLES)]} #{i + 1:02d}"
        ts0 = _now(i)
        events = [
            {
                "seq": 1,
                "ts": _iso(ts0),
                "task_id": task_id,
                "event": "phase",
                "data": {"phase": "retrieve", "query": title},
            },
            {
                "seq": 2,
                "ts": _iso(ts0 + timedelta(seconds=2)),
                "task_id": task_id,
                "event": "context_injection",
                "data": {
                    "source": "memory",
                    "items": [f"歷史：類似任務曾在 {ROLES[i % len(ROLES)]} 完成"],
                },
            },
            {
                "seq": 3,
                "ts": _iso(ts0 + timedelta(seconds=5)),
                "task_id": task_id,
                "event": "llm_call",
                "data": {
                    "model": "deepseek-reasoner",
                    "prompt": f"請規劃：{title}",
                    "thoughts": _thought(i, title),
                    "response": f"建議先完成 {title} 的資訊架構，再補視覺。交付：跳轉錨點、篩選、示範 60 筆。",
                    "cost": round(0.004 + (i % 9) * 0.0007, 4),
                    "duration_ms": 800 + i * 17,
                    "prompt_tokens": 420 + i,
                    "completion_tokens": 180 + i % 40,
                },
            },
            {
                "seq": 4,
                "ts": _iso(ts0 + timedelta(seconds=12)),
                "task_id": task_id,
                "event": "evaluation",
                "data": {"score": 7.2 + (i % 6) * 0.3, "feedback": "推理鏈完整，缺實際截圖驗證。"},
            },
        ]
        path = TRACE_DIR / f"trace_{task_id}.jsonl"
        path.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
            encoding="utf-8",
        )
    return N


KB_TOPICS = [
    "角色總覽卡片：標題與成本列不得互相擠壓",
    "左側目錄用層級錨點跳到 L0／L1／L2",
    "活躍與告警是篩選，不是第二套計數",
    "卡片右上角金額是該角色合計成本",
    "探針失敗應關閉對應 pool 模型",
    "Hub catalog 代碼必須與 PROVIDER_OF 對齊",
    "知識庫條目保留來源、過期日與責任角色",
    "推理軌跡以 task_id 對應工作項",
    "Docker 與阿里雲成本分開累計",
    "待命角色仍可出現在跳轉清單",
]


def _kb_text(i: int) -> str:
    topic = KB_TOPICS[i % len(KB_TOPICS)]
    return (
        f"【知識庫 #{i + 1:02d}】{topic}\n"
        f"適用角色：{ROLES[i % len(ROLES)]}\n"
        f"摘要：操作時先跳轉到目標層級，再用活躍／告警縮小範圍，"
        f"最後才進單角色工作台看任務與推理。\n"
        f"步驟：1) 確認層級 2) 看合計成本 3) 展開任務列表 4) 對照軌跡。\n"
        f"反例：把 $0 當成徽章、把 80/80 當成完成度。\n"
        f"更新：示範資料第 {i + 1} 條。"
    )


def _unit_vec(i: int, dim: int = 1536) -> list[float]:
    vec = [math.sin((i + 1) * (j + 1) * 0.017) for j in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def seed_knowledge() -> tuple[int, str]:
    records = []
    ids = []
    docs = []
    metas = []
    embs = []
    for i in range(N):
        text = _kb_text(i)
        rec_id = f"kb-demo-{i + 1:02d}"
        meta = {
            "kind": "knowledge",
            "source": "seed_demo_content",
            "role": ROLES[i % len(ROLES)],
            "topic": KB_TOPICS[i % len(KB_TOPICS)],
            "created_at": _iso(_now(i)),
            "_id": rec_id,
        }
        records.append({"id": rec_id, "text": text, "metadata": meta, "created_at": meta["created_at"]})
        ids.append(rec_id)
        docs.append(text)
        metas.append(meta)
        embs.append(_unit_vec(i))

    JSON_MEMORY.parent.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if JSON_MEMORY.exists():
        try:
            existing = json.loads(JSON_MEMORY.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, OSError):
            existing = []
    keep = [m for m in existing if (m.get("metadata") or {}).get("source") != "seed_demo_content"]
    JSON_MEMORY.write_text(json.dumps(keep + records, ensure_ascii=False, indent=2), encoding="utf-8")

    chroma_note = "chroma skipped"
    try:
        import chromadb

        from backend.memory.chroma_compat import apply_chromadb_sql_txt_compat

        apply_chromadb_sql_txt_compat()
        persist = DATA / "chroma"
        persist.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(persist))
        col = client.get_or_create_collection(name="evo_memory")
        try:
            col.delete(ids=ids)
        except Exception:
            pass
        col.add(  # chromadb stubs: metadatas/embeddings typed loosely at runtime
            ids=ids,
            documents=docs,
            metadatas=metas,  # type: ignore[arg-type]
            embeddings=embs,  # type: ignore[arg-type]
        )
        chroma_note = f"chroma evo_memory +{N}"
    except Exception as exc:
        chroma_note = f"chroma failed: {exc}"

    return N, chroma_note


def main() -> None:
    tasks_path = seed_tasks()
    n_reason = seed_reasoning()
    n_kb, chroma_note = seed_knowledge()
    print(f"tasks: {N} -> {tasks_path}")
    print(f"reasoning traces: {n_reason} -> {TRACE_DIR}")
    print(f"knowledge: {n_kb} json + {chroma_note}")


if __name__ == "__main__":
    main()
