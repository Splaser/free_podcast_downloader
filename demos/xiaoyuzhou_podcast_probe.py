from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_URL = (
    "https://www.xiaoyuzhoufm.com/"
    "podcast/68c436b4de7cd32c37b1c4a8"
)

DEBUG_DIR = Path("debug_xiaoyuzhou_podcast")


def extract_podcast_id(url: str) -> str:
    match = re.search(r"/podcast/([0-9a-fA-F]+)", url)
    if not match:
        raise ValueError(f"无法从 URL 提取 podcast_id: {url}")

    return match.group(1)


def shorten(value: Any, limit: int = 300) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > limit:
        return text[:limit] + "..."

    return text


def walk_json(
    obj: Any,
    path: str = "$",
    *,
    depth: int = 0,
    max_depth: int = 10,
) -> None:
    if depth > max_depth:
        return

    interesting_keys = {
        "title",
        "name",
        "author",
        "description",
        "episodeId",
        "episode_id",
        "podcastId",
        "podcast_id",
        "pubDate",
        "pub_date",
        "datePublished",
        "duration",
        "enclosure",
        "media",
        "source",
        "url",
        "picUrl",
        "cover",
        "image",
        "episodes",
        "episodeList",
        "hasMore",
        "has_more",
        "next",
        "nextCursor",
        "cursor",
        "offset",
        "limit",
        "page",
        "pageSize",
        "loadMoreKey",
    }

    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}"

            if key in interesting_keys:
                if isinstance(value, (dict, list)):
                    print(
                        f"  STRUCT {child_path}: "
                        f"{type(value).__name__} "
                        f"len={len(value)}"
                    )
                else:
                    print(
                        f"  FIELD {child_path}: "
                        f"{shorten(value)}"
                    )

            walk_json(
                value,
                child_path,
                depth=depth + 1,
                max_depth=max_depth,
            )

    elif isinstance(obj, list):
        for index, item in enumerate(obj[:50]):
            walk_json(
                item,
                f"{path}[{index}]",
                depth=depth + 1,
                max_depth=max_depth,
            )


def find_episode_lists(
    obj: Any,
    path: str = "$",
    results: list[tuple[str, list]] | None = None,
) -> list[tuple[str, list]]:
    if results is None:
        results = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}"

            if isinstance(value, list) and value:
                episode_like_count = 0

                for item in value:
                    if not isinstance(item, dict):
                        continue

                    keys = set(item.keys())

                    if (
                        "title" in keys
                        and (
                            "episodeId" in keys
                            or "eid" in keys
                            or "enclosure" in keys
                            or "media" in keys
                            or "podcast" in keys
                        )
                    ):
                        episode_like_count += 1

                if episode_like_count:
                    results.append(
                        (
                            child_path,
                            value,
                        )
                    )

            find_episode_lists(
                value,
                child_path,
                results,
            )

    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            find_episode_lists(
                item,
                f"{path}[{index}]",
                results,
            )

    return results


def get_nested(
    obj: Any,
    *keys: str,
    default=None,
):
    current = obj

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

    return current if current is not None else default


def extract_audio_url(item: dict) -> str:
    enclosure = item.get("enclosure") or {}
    media = item.get("media") or {}

    if not isinstance(enclosure, dict):
        enclosure = {}

    if not isinstance(media, dict):
        media = {}

    source = media.get("source") or {}
    if not isinstance(source, dict):
        source = {}

    return str(
        enclosure.get("url")
        or source.get("url")
        or item.get("audioUrl")
        or item.get("audio_url")
        or ""
    )


def extract_cover_url(item: dict) -> str:
    candidates = [
        item.get("image"),
        item.get("cover"),
        item.get("coverUrl"),
        item.get("cover_url"),
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate

        if isinstance(candidate, dict):
            value = (
                candidate.get("picUrl")
                or candidate.get("url")
                or candidate.get("largePicUrl")
                or candidate.get("smallPicUrl")
            )

            if value:
                return str(value)

    return ""


def print_episode_list(
    path: str,
    items: list,
) -> None:
    print()
    print(f"=== EPISODE LIST: {path} ===")
    print(f"count: {len(items)}")

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue

        episode_id = (
            item.get("episodeId")
            or item.get("eid")
            or item.get("id")
            or item.get("_id")
            or ""
        )

        title = item.get("title") or item.get("name") or ""
        pub_date = (
            item.get("pubDate")
            or item.get("pub_date")
            or item.get("datePublished")
            or item.get("publishedAt")
            or ""
        )

        audio_url = extract_audio_url(item)
        cover_url = extract_cover_url(item)

        podcast = item.get("podcast") or {}
        podcast_title = ""

        if isinstance(podcast, dict):
            podcast_title = str(
                podcast.get("title")
                or podcast.get("name")
                or ""
            )

        print()
        print(f"[{index}]")
        print("  episode_id:", episode_id)
        print("  title:", shorten(title, 160))
        print("  podcast:", podcast_title)
        print("  pub_date:", pub_date)
        print("  audio:", audio_url)
        print("  cover:", cover_url)

        if episode_id:
            print(
                "  source:",
                f"https://www.xiaoyuzhoufm.com/episode/{episode_id}",
            )


def print_candidate_pagination_fields(
    obj: Any,
    path: str = "$",
) -> None:
    pagination_keys = {
        "hasMore",
        "has_more",
        "next",
        "nextCursor",
        "next_cursor",
        "cursor",
        "offset",
        "limit",
        "page",
        "pageSize",
        "page_size",
        "loadMoreKey",
        "lastId",
        "last_id",
        "endCursor",
        "end_cursor",
    }

    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}"

            if key in pagination_keys:
                print(
                    f"{child_path}: "
                    f"{shorten(value)}"
                )

            print_candidate_pagination_fields(
                value,
                child_path,
            )

    elif isinstance(obj, list):
        for index, item in enumerate(obj[:50]):
            print_candidate_pagination_fields(
                item,
                f"{path}[{index}]",
            )


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    parsed = urlparse(url)

    if "xiaoyuzhoufm.com" not in parsed.netloc.lower():
        print("[ERROR] 不是小宇宙 URL")
        return 1

    podcast_id = extract_podcast_id(url)

    DEBUG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64; rv:152.0) "
                "Gecko/20100101 Firefox/152.0"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,"
                "image/webp,*/*;q=0.8"
            ),
            "Accept-Language": (
                "zh-CN,zh;q=0.9,en-US;q=0.7,en;q=0.5"
            ),
        }
    )

    print("=== REQUEST ===")
    print("url:", url)
    print("podcast_id:", podcast_id)

    response = session.get(
        url,
        timeout=30,
    )
    response.raise_for_status()

    print("status:", response.status_code)
    print("final_url:", response.url)
    print("content_type:", response.headers.get("content-type"))
    print("content_length:", len(response.content))
    print("server:", response.headers.get("server"))

    html_path = (
        DEBUG_DIR
        / f"xiaoyuzhou_podcast_{podcast_id}.html"
    )

    html_path.write_text(
        response.text,
        encoding="utf-8",
    )

    print("saved_html:", html_path)

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    print()
    print("=== HTML META ===")

    title_tag = soup.find("title")
    print(
        "title:",
        title_tag.get_text(strip=True)
        if title_tag
        else "",
    )

    for property_name in [
        "og:title",
        "og:description",
        "og:image",
    ]:
        tag = soup.find(
            "meta",
            attrs={"property": property_name},
        )

        print(
            f"{property_name}:",
            shorten(
                tag.get("content") if tag else "",
                500,
            ),
        )

    next_data_script = soup.find(
        "script",
        id="__NEXT_DATA__",
    )

    if not next_data_script:
        print()
        print("[ERROR] 页面没有 __NEXT_DATA__")
        return 1

    raw_next_data = (
        next_data_script.string
        or next_data_script.get_text()
    )

    next_data = json.loads(raw_next_data)

    json_path = (
        DEBUG_DIR
        / f"xiaoyuzhou_podcast_{podcast_id}_next_data.json"
    )

    json_path.write_text(
        json.dumps(
            next_data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("saved_next_data:", json_path)

    print()
    print("=== PAGE PROPS TOP LEVEL ===")

    page_props = get_nested(
        next_data,
        "props",
        "pageProps",
        default={},
    )

    if isinstance(page_props, dict):
        for key, value in page_props.items():
            if isinstance(value, dict):
                print(
                    f"{key}: dict "
                    f"keys={list(value.keys())[:30]}"
                )

            elif isinstance(value, list):
                print(
                    f"{key}: list len={len(value)}"
                )

            else:
                print(
                    f"{key}: "
                    f"{shorten(value)}"
                )

    print()
    print("=== INTERESTING JSON FIELDS ===")

    walk_json(
        page_props,
        "$.props.pageProps",
        max_depth=8,
    )

    episode_lists = find_episode_lists(
        page_props,
        "$.props.pageProps",
    )

    if not episode_lists:
        print()
        print("[WARN] 没有识别到 episode-like list")
    else:
        seen_paths = set()

        for path, items in episode_lists:
            if path in seen_paths:
                continue

            seen_paths.add(path)
            print_episode_list(
                path,
                items,
            )

    print()
    print("=== PAGINATION CANDIDATES ===")

    print_candidate_pagination_fields(
        page_props,
        "$.props.pageProps",
    )

    print()
    print("=== HTML EPISODE LINKS ===")

    episode_links = []

    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href") or "")

        match = re.search(
            r"/episode/([0-9a-fA-F]+)",
            href,
        )

        if not match:
            continue

        episode_id = match.group(1)

        full_url = (
            href
            if href.startswith("http")
            else f"https://www.xiaoyuzhoufm.com{href}"
        )

        episode_links.append(
            (
                episode_id,
                full_url,
                tag.get_text(" ", strip=True),
            )
        )

    unique_links = []
    seen_episode_ids = set()

    for item in episode_links:
        episode_id = item[0]

        if episode_id in seen_episode_ids:
            continue

        seen_episode_ids.add(episode_id)
        unique_links.append(item)

    print("episode_links:", len(unique_links))

    for index, (
        episode_id,
        episode_url,
        text,
    ) in enumerate(unique_links, start=1):
        print(
            f"{index}. {episode_id} | "
            f"{shorten(text, 100)} | "
            f"{episode_url}"
        )

    print()
    print("=== SCRIPT URL SCAN ===")

    script_urls = []

    for script in soup.find_all("script", src=True):
        src = str(script.get("src") or "")
        script_urls.append(src)

        if (
            "podcast" in src.lower()
            or "[id]" in src.lower()
        ):
            print(src)

    scripts_path = (
        DEBUG_DIR
        / f"xiaoyuzhou_podcast_{podcast_id}_scripts.txt"
    )

    scripts_path.write_text(
        "\n".join(script_urls),
        encoding="utf-8",
    )

    print("saved_scripts:", scripts_path)

    print()
    print("=== DONE ===")
    print(
        "重点把以下内容贴回来："
    )
    print("1. PAGE PROPS TOP LEVEL")
    print("2. EPISODE LIST")
    print("3. PAGINATION CANDIDATES")
    print("4. HTML EPISODE LINKS")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())