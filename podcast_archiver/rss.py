# podcast_archiver/rss.py
from __future__ import annotations

import re
import time
from typing import Iterable
import requests
import feedparser

from podcast_archiver.listen_notes import Episode
from urllib.parse import urlparse, parse_qs, unquote

AUDIO_MIME_PREFIX = "audio/"

def extract_original_url_from_proxy(audio_url: str) -> str:
    """
    从类似：
    https://cdn.shawnxli.com/afdian/?url=https://afdian.com/p/xxx
    提取原始 url。
    """
    parsed = urlparse(audio_url)
    qs = parse_qs(parsed.query)

    values = qs.get("url")
    if not values:
        return ""

    return unquote(values[0])



def _clean_html_text(text: str) -> str:
    """
    简单清理 RSS description / summary 里的 HTML。
    后续如果想保留富文本，可以改成原样保存。
    """
    if not text:
        return ""

    # 去掉 HTML tag
    text = re.sub(r"<[^>]+>", "", text)

    # 基础 entity
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )

    return re.sub(r"\s+", " ", text).strip()


def _guess_ext_from_url_or_type(url: str, mime_type: str = "") -> str:
    lowered_url = (url or "").lower()
    lowered_type = (mime_type or "").lower()

    for ext in [".mp3", ".m4a", ".aac", ".ogg", ".wav", ".mp4"]:
        if ext in lowered_url:
            return ext

    if "mpeg" in lowered_type or "mp3" in lowered_type:
        return ".mp3"

    if "mp4" in lowered_type or "m4a" in lowered_type or "aac" in lowered_type:
        return ".m4a"

    if "ogg" in lowered_type:
        return ".ogg"

    if "wav" in lowered_type:
        return ".wav"

    return ".mp3"

def _entry_timestamp(entry) -> int:
    parsed_time = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
        or entry.get("created_parsed")
    )

    if not parsed_time:
        return 0

    return int(time.mktime(parsed_time))

def _get_feed_image(feed) -> str:
    """
    从 channel 级别获取播客封面。
    feedparser 里可能是 feed.image.href / feed.image.url / feed.itunes_image.href。
    """
    image = getattr(feed, "image", None)
    if image:
        href = image.get("href") or image.get("url")
        if href:
            return href

    itunes_image = getattr(feed, "itunes_image", None)
    if isinstance(itunes_image, dict):
        href = itunes_image.get("href")
        if href:
            return href

    return ""


def _get_entry_image(entry, fallback: str = "") -> str:
    """
    单集封面，优先 item 自己的 image，没有就用 channel 封面。
    """
    image = getattr(entry, "image", None)
    if image:
        href = image.get("href") or image.get("url")
        if href:
            return href

    itunes_image = getattr(entry, "itunes_image", None)
    if isinstance(itunes_image, dict):
        href = itunes_image.get("href")
        if href:
            return href

    return fallback


def _find_audio_enclosure(entry) -> tuple[str, str]:
    """
    从 RSS item 中找音频 enclosure。
    返回: (audio_url, mime_type)
    """
    links = getattr(entry, "links", []) or []

    # 标准 podcast RSS: <enclosure url="..." type="audio/..." />
    for link in links:
        rel = (link.get("rel") or "").lower()
        mime_type = link.get("type") or ""
        href = link.get("href") or ""

        if not href:
            continue

        if rel == "enclosure" and mime_type.lower().startswith(AUDIO_MIME_PREFIX):
            return href, mime_type

    # fallback：有些 feed enclosure 没有正确 type
    for link in links:
        rel = (link.get("rel") or "").lower()
        href = link.get("href") or ""
        mime_type = link.get("type") or ""

        if not href:
            continue

        lowered = href.lower()
        if rel == "enclosure" and any(ext in lowered for ext in [".mp3", ".m4a", ".aac", ".ogg", ".wav"]):
            return href, mime_type

    # 再 fallback：entry.enclosures
    enclosures = getattr(entry, "enclosures", []) or []
    for enc in enclosures:
        href = enc.get("href") or enc.get("url") or ""
        mime_type = enc.get("type") or ""

        if href and (
            mime_type.lower().startswith(AUDIO_MIME_PREFIX)
            or any(ext in href.lower() for ext in [".mp3", ".m4a", ".aac", ".ogg", ".wav"])
        ):
            return href, mime_type

    return "", ""

def fetch_rss_content(rss_url: str, session=None) -> bytes:
    """
    用 requests 拉 RSS 内容，避免 feedparser 默认请求被站点拦截。
    """
    s = session or requests.Session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",

        # RSS feed 尽量不要 br，避免返回压缩二进制导致 feedparser 解析失败
        "Accept-Encoding": "identity",
    }

    resp = s.get(rss_url, headers=headers, timeout=30, allow_redirects=True)

    print(f"[INFO] RSS GET {rss_url}")
    print(f"[INFO] status={resp.status_code}")
    print(f"[INFO] final_url={resp.url}")
    print(f"[INFO] content-type={resp.headers.get('content-type')}")

    preview = resp.text[:300].replace("\n", "\\n")
    print(f"[INFO] preview={preview}")

    if resp.status_code == 404:
        raise RuntimeError(
            "RSS feed returned 404. This feed URL may be stale, disabled, or no longer public."
        )

    resp.raise_for_status()
    return resp.content


def parse_rss_feed(rss_url: str, session=None) -> list[Episode]:
    """
    解析 podcast RSS feed，返回 Episode 列表。

    注意：
    - RSS 通常按最新到最旧排序；
    - 后续 --latest n 可以直接取 episodes[:n]；
    - 如果需要老到新归档，可在 main 里 reverse。
    """
    rss_content = fetch_rss_content(rss_url, session=session)
    parsed = feedparser.parse(rss_content)

    if parsed.bozo:
        print(f"[WARN] feedparser bozo: {parsed.bozo_exception}")

    feed = parsed.feed
    entries = parsed.entries or []

    podcast_title = (
        feed.get("title")
        or feed.get("itunes_author")
        or feed.get("author")
        or "Podcast"
    )

    author = (
        feed.get("author")
        or feed.get("itunes_author")
        or podcast_title
    )

    feed_cover = _get_feed_image(feed)

    episodes_with_time: list[tuple[int, Episode]] = []

    for entry in entries:
        audio_url, mime_type = _find_audio_enclosure(entry)

        if not audio_url:
            continue

        title = entry.get("title") or "episode"

        description = (
            entry.get("summary")
            or entry.get("description")
            or entry.get("subtitle")
            or ""
        )

        cover_url = _get_entry_image(entry, fallback=feed_cover)

        episode = Episode(
            title=title.strip(),
            podcast_title=podcast_title.strip(),
            author=author.strip(),
            description=_clean_html_text(description),
            audio_url=audio_url,
            cover_url=cover_url,
            source_url=entry.get("link") or rss_url,
            ext=_guess_ext_from_url_or_type(audio_url, mime_type),
        )

        timestamp = _entry_timestamp(entry)
        episodes_with_time.append((timestamp, episode))

    episodes_with_time.sort(key=lambda item: item[0], reverse=True)

    return [episode for _, episode in episodes_with_time]


def print_episodes(episodes: Iterable[Episode], limit: int | None = None):
    """
    简单打印 RSS 解析结果，用于 --list。
    """
    selected = list(episodes)

    if limit is not None:
        selected = selected[:limit]

    for index, episode in enumerate(selected, start=1):
        print(f"{index}. {episode.title}")
        print(f"   podcast: {episode.podcast_title}")
        print(f"   audio: {episode.audio_url}")
        print(f"   ext: {episode.ext}")
        print()