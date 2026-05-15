from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CACHE_PATH = Path(".cache/listen_notes_cursor_cache.json")


def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}

    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_best_cursor(channel_uuid: str, offset: int) -> dict | None:
    """
    找一个 collected_count <= offset 的最大 cursor。
    """
    if not channel_uuid or offset <= 0:
        return None

    data = _load_cache()
    items = data.get(channel_uuid) or []

    best = None

    for item in items:
        count = int(item.get("collected_count") or 0)

        if count <= offset and (
            best is None
            or count > int(best.get("collected_count") or 0)
        ):
            best = item

    return best


def save_cursor(
    channel_uuid: str,
    *,
    page_index: int,
    collected_count: int,
    next_pub_date: int | None,
    prev_pub_date: int | None,
    referer_url: str = "",
) -> None:
    if not channel_uuid or not next_pub_date:
        return

    data = _load_cache()
    items = data.setdefault(channel_uuid, [])

    item = {
        "page_index": page_index,
        "collected_count": collected_count,
        "next_pub_date": int(next_pub_date),
        "prev_pub_date": int(prev_pub_date) if prev_pub_date else None,
        "referer_url": referer_url,
    }

    # 同一个 collected_count 覆盖
    items = [
        old for old in items
        if int(old.get("collected_count") or 0) != collected_count
    ]
    items.append(item)
    items.sort(key=lambda x: int(x.get("collected_count") or 0))

    data[channel_uuid] = items
    _save_cache(data)