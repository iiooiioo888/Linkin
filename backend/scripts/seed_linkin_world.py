"""寫入靈境世界觀種子、示範 NPC，以及 Linkin 子角色。

不呼叫真實嵌入 API。Chroma 失敗時降級 JSON（比照 seed_demo_content.py）。
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.linkin.constitution import load_constitution, worldview_seed_documents
from backend.linkin.knowledge import (
    COL_EVENTS,
    COL_NPCS,
    COL_WORLDVIEW,
    get_store,
    list_entities,
    reset_store,
    save_entities,
    upsert_entity,
)
from backend.linkin.roles import seed_linkin_roles
from backend.linkin.tools import format_npc_text

SEED_NPCS = [
    {
        "id": "npc-loom-scribe",
        "name": "司契·白绫",
        "faction": "织庭盟",
        "occupation": "典章司仪",
        "personality": "严谨、温和、把契约视为对世界的承诺",
        "backstory": (
            "白绫自幼在织庭都契约广场抄录织梦者残章。她相信每一座建筑都是记忆的锚点，"
            "也曾在裂隙港目睹即兴改建撕裂金线纹样，从此坚持任何改建必须留下可追溯的契约副本。"
        ),
        "location": "织庭都",
        "speech_style": "文言夹白，短句收束",
        "relationships": {"宁渊守望者": "互相尊重但不赞同对方的「少动」"},
    },
    {
        "id": "npc-ark-captain",
        "name": "岚舟·铜钉",
        "faction": "自由舟",
        "occupation": "裂隙港船长兼工坊主",
        "personality": "豪爽、好奇、厌恶空谈秩序",
        "backstory": (
            "铜钉少年时随自由舟穿过世界缝隙，靠黄铜市集的修理摊起家。他认定灵境应随旅人的梦生长，"
            "但在宁渊谷差点让灵泉枯竭后，开始愿意在扩建前先问一句「灵脉还撑得住吗」。"
        ),
        "location": "裂隙港",
        "speech_style": "市井口语，喜欢用航海比喻",
        "relationships": {"司契·白绫": "经常吵架的生意伙伴"},
    },
    {
        "id": "npc-still-warden",
        "name": "雾衡",
        "faction": "宁渊庭",
        "occupation": "灵脉守望者",
        "personality": "寡言、慈悲、对过度塑形极为敏感",
        "backstory": (
            "雾衡在宁渊谷灵脉神殿守了三十年。她能听见灵丝过紧时的颤音，因此对织庭都的宏伟工程保持警惕，"
            "却也承认若没有自由舟的航路，隐士们将无法把过剩的灵泉分给精灵森林。"
        ),
        "location": "宁渊谷",
        "speech_style": "低声、留白多",
        "relationships": {"岚舟·铜钉": "有条件的合作"},
    },
]


def seed_worldview() -> tuple[int, str]:
    store = get_store()
    count = 0
    for doc in worldview_seed_documents():
        store.upsert(
            COL_WORLDVIEW,
            doc["text"],
            dict(doc.get("metadata") or {}),
            record_id=str(doc["id"]),
            skip_quality=True,
        )
        count += 1
    backend = "chroma" if store.backend_status().get("chroma") else "json"
    return count, backend


def seed_npcs() -> int:
    store = get_store()
    for card in SEED_NPCS:
        store.upsert(
            COL_NPCS,
            format_npc_text(card),
            dict(card),
            record_id=card["id"],
            skip_quality=True,
        )
    store.upsert(
        COL_EVENTS,
        "种子事件：三大阵营在织庭都召开第一次「灵丝议会」，约定改建必须留下契约副本。",
        {"kind": "history", "title": "第一次灵丝议会"},
        record_id="event-first-council",
        skip_quality=True,
    )
    return len(SEED_NPCS)


SEED_ITEM = {
    "id": "item-aether-shard",
    "name": "灵丝碎片",
    "type": "消耗品",
    "rarity": "uncommon",
    "attributes": {"power": 10},
    "description": "织梦者残章剥落的纤维，可短暂稳定区域和谐度。",
}


def seed_catalog() -> tuple[int, int]:
    """示範道具；任務列表由生成 API 寫入，此處保證 JSON 檔存在。"""
    upsert_entity("items", dict(SEED_ITEM))
    if not list_entities("quests"):
        save_entities("quests", [])
    return 1, len(list_entities("quests"))


def main() -> None:
    reset_store()
    const = load_constitution()
    n_world, backend = seed_worldview()
    n_npc = seed_npcs()
    n_item, n_quest = seed_catalog()
    roles = seed_linkin_roles()
    world = const.get("world_name") or "Linkin"
    print(f"constitution: {world} factions={len(const.get('factions') or [])}")
    print(f"worldview docs: {n_world} ({backend})")
    print(f"npcs: {n_npc}")
    print(f"items: {n_item}")
    print(f"quests: {n_quest}")
    print(f"roles: {len(roles)}")
    status = get_store().backend_status()
    if not status.get("chroma"):
        err = status.get("error") or "json"
        print(f"chroma fallback: {err}")


if __name__ == "__main__":
    main()
