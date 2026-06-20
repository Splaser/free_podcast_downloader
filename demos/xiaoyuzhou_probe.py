from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_URL = "https://www.xiaoyuzhoufm.com/episode/6a350ac54233e62bc54c5fdb"
DEFAULT_TIMEOUT = 30

MEDIA_EXTENSIONS = (".m4a", ".mp3", ".aac", ".ogg", ".wav", ".mp4", ".m3u8")
MEDIA_HOST_HINTS = (
    "media.xyzcdn.net",
    "audio.xiaoyuzhoufm.com",
    "dts-api.xiaoyuzhoufm.com",
)


def extract_episode_id(url: str) -> str:
    match = re.search(r"/episode/([0-9a-fA-F]{24})(?:[/?#]|$)", url)
    if not match:
        raise ValueError(f"无法从 URL 解析 episode id: {url}")
    return match.group(1)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
    )
    return session


def shorten(value: Any, limit: int = 500) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + " ..."


def iter_json_objects(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, value

    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_json_objects(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_json_objects(child, f"{path}[{index}]")


def looks_like_media_url(value: str) -> bool:
    if not isinstance(value, str):
        return False

    decoded = html.unescape(value).replace("\\/", "/")
    lowered = decoded.lower()

    if not lowered.startswith(("http://", "https://")):
        return False

    return any(host in lowered for host in MEDIA_HOST_HINTS) or any(
        ext in lowered for ext in MEDIA_EXTENSIONS
    )


def collect_media_urls_from_text(text: str) -> list[str]:
    decoded = html.unescape(text).replace("\\u002F", "/").replace("\\/", "/")
    candidates = re.findall(r'https?://[^\s"\'<>]+', decoded)

    result: list[str] = []
    seen: set[str] = set()

    for candidate in candidates:
        candidate = candidate.rstrip("),.;]")
        if not looks_like_media_url(candidate):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)

    return result


def print_meta(soup: BeautifulSoup) -> None:
    print("\n=== HTML META ===")

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    print("title:", title or "(not found)")

    interesting = {
        "description",
        "og:title",
        "og:description",
        "og:image",
        "og:audio",
        "og:audio:url",
        "twitter:title",
        "twitter:description",
        "twitter:image",
        "music:musician",
    }

    found = 0
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name") or tag.get("itemprop")
        content = tag.get("content")
        if not key or content is None:
            continue
        if key.lower() in interesting or "audio" in key.lower():
            print(f"{key}: {shorten(content)}")
            found += 1

    if not found:
        print("(no interesting meta tags found)")

    for audio in soup.find_all(["audio", "source"]):
        src = audio.get("src")
        if src:
            print(f"<{audio.name}> src:", src)


def probe_script_json(soup: BeautifulSoup) -> None:
    print("\n=== EMBEDDED JSON / SCRIPT ===")

    parsed_count = 0
    useful_count = 0

    for index, script in enumerate(soup.find_all("script"), start=1):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue

        script_id = script.get("id") or ""
        script_type = script.get("type") or ""

        should_try_json = (
            script_type in {"application/json", "application/ld+json"}
            or script_id in {"__NEXT_DATA__", "__NUXT_DATA__"}
            or raw.startswith(("{", "["))
        )

        if not should_try_json:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        parsed_count += 1
        print(f"[JSON {parsed_count}] script#{index} id={script_id!r} type={script_type!r}")

        for path, value in iter_json_objects(data):
            key = path.rsplit(".", 1)[-1].lower()

            if isinstance(value, str) and looks_like_media_url(value):
                print(f"  MEDIA {path}: {value.replace('\\/', '/')}")
                useful_count += 1
                continue

            if key in {
                "title",
                "name",
                "description",
                "author",
                "podcast",
                "podcasttitle",
                "podcast_title",
                "audiosrc",
                "audiourl",
                "audio_url",
                "enclosure",
                "image",
                "cover",
                "coverurl",
            }:
                if isinstance(value, (str, int, float, bool)):
                    print(f"  FIELD {path}: {shorten(value, 300)}")
                    useful_count += 1

    if parsed_count == 0:
        print("(no directly parseable JSON scripts found)")
    elif useful_count == 0:
        print("(JSON found, but no obvious episode/media fields matched)")


def probe_api_candidates(
    session: requests.Session,
    episode_id: str,
    referer: str,
    timeout: int,
    save_dir: Path,
) -> None:
    print("\n=== API CANDIDATES ===")

    # 先只做无认证 GET 探测。即使 401/404，也能帮助确认真实入口。
    candidates = [
        f"https://api.xiaoyuzhoufm.com/v1/episodes/{episode_id}",
        f"https://api.xiaoyuzhoufm.com/v1/episode/{episode_id}",
        f"https://api.xiaoyuzhoufm.com/v1/episode/get?eid={episode_id}",
    ]

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
        "Origin": "https://www.xiaoyuzhoufm.com",
    }

    for index, api_url in enumerate(candidates, start=1):
        try:
            resp = session.get(api_url, headers=headers, timeout=timeout)
        except Exception as exc:
            print(f"[{index}] request failed: {api_url}")
            print("    error:", exc)
            continue

        content_type = resp.headers.get("content-type", "")
        print(f"[{index}] {resp.status_code} {content_type} {api_url}")
        print("    preview:", shorten(resp.text, 350))

        output = save_dir / f"xiaoyuzhou_api_{index}_{resp.status_code}.txt"
        output.write_text(resp.text, encoding="utf-8", errors="replace")

        media_urls = collect_media_urls_from_text(resp.text)
        for media_url in media_urls:
            print("    MEDIA:", media_url)


def probe(url: str, *, timeout: int, save_dir: Path, skip_api: bool) -> int:
    episode_id = extract_episode_id(url)
    session = make_session()
    save_dir.mkdir(parents=True, exist_ok=True)

    print("=== REQUEST ===")
    print("url:", url)
    print("episode_id:", episode_id)

    try:
        resp = session.get(url, timeout=timeout)
    except Exception as exc:
        print("[ERROR] page request failed:", exc)
        return 1

    print("status:", resp.status_code)
    print("final_url:", resp.url)
    print("content_type:", resp.headers.get("content-type"))
    print("content_length:", len(resp.content))
    print("server:", resp.headers.get("server"))

    html_path = save_dir / f"xiaoyuzhou_episode_{episode_id}.html"
    html_path.write_text(resp.text, encoding="utf-8", errors="replace")
    print("saved_html:", html_path)

    if resp.status_code >= 400:
        print("[ERROR] page returned HTTP error")
        print("preview:", shorten(resp.text))
        return 1

    soup = BeautifulSoup(resp.text, "html.parser")
    print_meta(soup)
    probe_script_json(soup)

    print("\n=== REGEX MEDIA SCAN ===")
    media_urls = collect_media_urls_from_text(resp.text)
    if media_urls:
        for media_url in media_urls:
            print("MEDIA:", media_url)
    else:
        print("(no obvious media URL found in raw HTML)")

    print("\n=== PAGE STRUCTURE HINTS ===")
    for marker in ["__NEXT_DATA__", "__NUXT_DATA__", "webpack", "_next/static", "application/ld+json"]:
        print(f"{marker}: {resp.text.lower().count(marker.lower())}")

    if not skip_api:
        probe_api_candidates(
            session,
            episode_id,
            referer=url,
            timeout=timeout,
            save_dir=save_dir,
        )

    print("\n=== SUMMARY ===")
    print("page_media_count:", len(media_urls))
    print("saved_dir:", save_dir)
    print("下一步请把完整控制台输出和生成的 HTML/API txt 中命中的结构贴回来。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe Xiaoyuzhou episode page/API structure")
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--save-dir", default="debug_xiaoyuzhou")
    parser.add_argument("--skip-api", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        return probe(
            args.url,
            timeout=max(args.timeout, 1),
            save_dir=Path(args.save_dir),
            skip_api=args.skip_api,
        )
    except ValueError as exc:
        print("[ERROR]", exc)
        return 2
    except KeyboardInterrupt:
        print("\n[WARN] interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
