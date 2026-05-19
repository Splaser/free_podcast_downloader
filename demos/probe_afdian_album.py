# probe_afdian_album.py
from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

from podcast_archiver.session_utils import create_session
from podcast_archiver.afdian import (
    parse_album_id,
    extract_album_list,
    _api_url,
)


def shorten(value: Any, limit: int = 240) -> str:
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)

    text = text.replace("\n", "\\n").replace("\r", "\\r")

    if len(text) > limit:
        return text[:limit] + "..."

    return text


def print_item_probe(item: dict, index: int) -> None:
    print()
    print("=" * 80)
    print(f"[ITEM #{index}]")
    print("=" * 80)

    print("[KEYS]")
    print(", ".join(sorted(item.keys())))

    interesting_keys = [
        "post_id",
        "id",
        "title",
        "rank",
        "publish_sn",
        "publish_time",
        "published_at",
        "create_time",
        "created_at",
        "ctime",
        "utime",
        "date",
        "show_time",
        "type",
        "audio",
        "audio_url",
        "audioUrl",
        "audio_thumb",
        "cover",
        "preview_text",
        "content",
    ]

    print()
    print("[INTERESTING FIELDS]")
    for key in interesting_keys:
        if key in item:
            print(f"{key}: {shorten(item.get(key))}")

    print()
    print("[RAW JSON PREVIEW]")
    print(shorten(item, limit=1200))


def probe_album(
    album_url_or_id: str,
    *,
    browser: str = "firefox",
    max_pages: int = 1,
    per_page_probe: int = 5,
) -> None:
    album_id = (
        parse_album_id(album_url_or_id)
        if "/album/" in album_url_or_id
        else album_url_or_id
    )

    session = create_session(
        browser=browser,
        domain="ifdian.net",
    )

    params = {
        "album_id": album_id,
        "lastRank": 0,
        "rankOrder": "asc",
        "rankField": "rank",
    }

    all_keys = Counter()
    total_items = 0

    for page_index in range(1, max_pages + 1):
        print()
        print("#" * 80)
        print(f"[PAGE {page_index}] params={params}")
        print("#" * 80)

        resp = session.get(
            _api_url("/api/user/get-album-post"),
            params=params,
            timeout=30,
        )

        print("[HTTP]", resp.status_code)
        print("[URL]", resp.url)
        print("[PREVIEW]", resp.text[:500])

        resp.raise_for_status()
        raw = resp.json()

        print("[API ec]", raw.get("ec"))
        print("[API em]", raw.get("em") or raw.get("msg"))

        if raw.get("ec") != 200:
            print("[ERROR] API returned non-200 ec, stop.")
            break

        data = raw.get("data", {})
        page_items, has_more = extract_album_list(data)

        print("[PAGE ITEMS]", len(page_items))
        print("[HAS MORE]", has_more)

        if not page_items:
            break

        for item in page_items:
            all_keys.update(item.keys())

        for idx, item in enumerate(page_items[:per_page_probe], start=1):
            print_item_probe(item, total_items + idx)

        total_items += len(page_items)

        last_item = page_items[-1]
        params["lastRank"] = last_item.get(
            "rank",
            params.get("lastRank", 0) + 10,
        )

        if not has_more:
            break

    print()
    print("#" * 80)
    print("[SUMMARY]")
    print("#" * 80)
    print("total_items_seen:", total_items)
    print("all_keys:")
    for key, count in sorted(all_keys.items()):
        print(f"  {key}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("album", help="Afdian album URL or album_id")
    parser.add_argument("--browser", default="firefox", choices=["firefox", "chrome"])
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--per-page-probe", type=int, default=5)

    args = parser.parse_args()

    probe_album(
        args.album,
        browser=args.browser,
        max_pages=args.max_pages,
        per_page_probe=args.per_page_probe,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())