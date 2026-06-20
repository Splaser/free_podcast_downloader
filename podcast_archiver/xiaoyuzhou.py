from __future__ import annotations

import json
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .listen_notes import Episode


XIAOYUZHOU_HOSTS = {
    "xiaoyuzhoufm.com",
    "www.xiaoyuzhoufm.com",
}


def is_xiaoyuzhou_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()

    return (
        host in XIAOYUZHOU_HOSTS
        or host.endswith(".xiaoyuzhoufm.com")
    )


def is_xiaoyuzhou_episode_url(url: str) -> bool:
    if not is_xiaoyuzhou_url(url):
        return False

    path = urlparse(url).path.rstrip("/")
    return path.startswith("/episode/") and len(path.split("/")) >= 3


def _guess_ext(audio_url: str) -> str:
    path = (audio_url or "").lower().split("?", 1)[0]

    for ext in [".m4a", ".mp3", ".aac", ".ogg", ".wav", ".mp4"]:
        if path.endswith(ext):
            return ".m4a" if ext == ".mp4" else ext

    return ".m4a"


def _normalize_podcast_title(title: str) -> str:
    """
    清理小宇宙播客标题末尾多余的中英文冒号。

    例：
    保留意见：
    -> 保留意见
    """
    title = (title or "").strip()

    # 只裁剪标题末尾的冒号，不影响标题中间内容。
    title = title.rstrip("：:")

    return title.strip() or "小宇宙"


def _load_json_script(
    soup: BeautifulSoup,
    *,
    script_id: str = "",
    script_type: str = "",
):
    attrs = {}

    if script_id:
        attrs["id"] = script_id

    if script_type:
        attrs["type"] = script_type

    script = soup.find("script", attrs=attrs)
    if not script:
        return None

    raw = script.string or script.get_text(strip=True)
    if not raw:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_image_url(value) -> str:
    if isinstance(value, str):
        return value.strip()

    if not isinstance(value, dict):
        return ""

    return str(
        value.get("picUrl")
        or value.get("url")
        or value.get("source")
        or value.get("largePicUrl")
        or value.get("smallPicUrl")
        or ""
    ).strip()


def _episode_from_next_data(
    data: dict,
    source_url: str,
) -> Episode | None:
    try:
        raw = data["props"]["pageProps"]["episode"]
    except (KeyError, TypeError):
        return None

    if not isinstance(raw, dict):
        return None

    podcast = raw.get("podcast") or {}
    enclosure = raw.get("enclosure") or {}
    media = raw.get("media") or {}

    if not isinstance(podcast, dict):
        podcast = {}

    if not isinstance(enclosure, dict):
        enclosure = {}

    if not isinstance(media, dict):
        media = {}

    media_source = media.get("source") or {}
    if not isinstance(media_source, dict):
        media_source = {}

    audio_url = str(
        enclosure.get("url")
        or media_source.get("url")
        or raw.get("audioUrl")
        or raw.get("audio_url")
        or ""
    ).strip()

    if not audio_url:
        return None

    title = str(
        raw.get("title")
        or "episode"
    ).strip()

    podcast_title = _normalize_podcast_title(
        str(
            podcast.get("title")
            or "小宇宙"
        )
    )

    author = _normalize_podcast_title(
        str(
            podcast.get("author")
            or podcast_title
        )
    )

    cover_url = (
        _extract_image_url(raw.get("image"))
        or _extract_image_url(raw.get("cover"))
        or _extract_image_url(raw.get("coverUrl"))
        or _extract_image_url(raw.get("cover_url"))
        or _extract_image_url(podcast.get("image"))
        or _extract_image_url(podcast.get("cover"))
        or _extract_image_url(podcast.get("coverUrl"))
    )

    return Episode(
        title=title,
        podcast_title=podcast_title,
        author=author or podcast_title,
        description=str(raw.get("description") or ""),
        audio_url=audio_url,
        cover_url=cover_url,
        source_url=source_url,
        ext=_guess_ext(audio_url),
    )


def _episode_from_json_ld(
    data: dict,
    source_url: str,
) -> Episode | None:
    if not isinstance(data, dict):
        return None

    # 某些页面可能返回 JSON-LD 数组。
    if isinstance(data.get("@graph"), list):
        for item in data["@graph"]:
            episode = _episode_from_json_ld(item, source_url)
            if episode:
                return episode

    if data.get("@type") != "PodcastEpisode":
        return None

    media = data.get("associatedMedia") or {}
    series = data.get("partOfSeries") or {}

    if not isinstance(media, dict):
        media = {}

    if not isinstance(series, dict):
        series = {}

    audio_url = str(
        media.get("contentUrl")
        or media.get("url")
        or ""
    ).strip()

    if not audio_url:
        return None

    podcast_title = _normalize_podcast_title(
        str(
            series.get("name")
            or "小宇宙"
        )
    )

    return Episode(
        title=str(data.get("name") or "episode").strip(),
        podcast_title=podcast_title,
        author=podcast_title,
        description=str(data.get("description") or ""),
        audio_url=audio_url,
        cover_url=_extract_image_url(data.get("image")),
        source_url=source_url,
        ext=_guess_ext(audio_url),
    )


def _meta_content(
    soup: BeautifulSoup,
    *,
    property_name: str = "",
    name: str = "",
) -> str:
    if property_name:
        tag = soup.find(
            "meta",
            attrs={"property": property_name},
        )
    elif name:
        tag = soup.find(
            "meta",
            attrs={"name": name},
        )
    else:
        return ""

    if not tag:
        return ""

    return str(tag.get("content") or "").strip()


def _fill_episode_fallbacks(
    episode: Episode,
    soup: BeautifulSoup,
) -> Episode:
    if not episode.cover_url:
        episode.cover_url = (
            _meta_content(
                soup,
                property_name="og:image",
            )
            or _meta_content(
                soup,
                name="twitter:image",
            )
        )

    if not episode.audio_url:
        episode.audio_url = _meta_content(
            soup,
            property_name="og:audio",
        )
        episode.ext = _guess_ext(episode.audio_url)

    return episode


def parse_xiaoyuzhou_episode(
    url: str,
    session,
) -> Episode:
    if not is_xiaoyuzhou_episode_url(url):
        raise ValueError(f"不支持的小宇宙 URL: {url}")

    if session is None:
        raise ValueError(
            "parse_xiaoyuzhou_episode() 需要传入 session"
        )

    resp = session.get(
        url,
        timeout=30,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(
        resp.text,
        "html.parser",
    )

    # 1. 首选 __NEXT_DATA__，字段最完整。
    next_data = _load_json_script(
        soup,
        script_id="__NEXT_DATA__",
    )

    if isinstance(next_data, dict):
        episode = _episode_from_next_data(
            next_data,
            resp.url,
        )

        if episode:
            print("[INFO] Xiaoyuzhou parsed from __NEXT_DATA__")
            return _fill_episode_fallbacks(
                episode,
                soup,
            )

    # 2. JSON-LD 兜底。
    json_ld_scripts = soup.find_all(
        "script",
        attrs={"type": "application/ld+json"},
    )

    for script in json_ld_scripts:
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue

        try:
            json_ld = json.loads(raw)
        except json.JSONDecodeError:
            continue

        candidates = (
            json_ld
            if isinstance(json_ld, list)
            else [json_ld]
        )

        for candidate in candidates:
            episode = _episode_from_json_ld(
                candidate,
                resp.url,
            )

            if episode:
                print("[INFO] Xiaoyuzhou parsed from JSON-LD")
                return _fill_episode_fallbacks(
                    episode,
                    soup,
                )

    # 3. 最后使用 OpenGraph。
    title = _meta_content(
        soup,
        property_name="og:title",
    )

    audio_url = _meta_content(
        soup,
        property_name="og:audio",
    )

    cover_url = _meta_content(
        soup,
        property_name="og:image",
    )

    description = (
        _meta_content(
            soup,
            property_name="og:description",
        )
        or _meta_content(
            soup,
            name="description",
        )
    )

    if not title or not audio_url:
        raise ValueError(
            "小宇宙页面未解析到完整的标题或音频地址"
        )

    print("[INFO] Xiaoyuzhou parsed from OpenGraph fallback")

    return Episode(
        title=title,
        podcast_title="小宇宙",
        author="小宇宙",
        description=description,
        audio_url=audio_url,
        cover_url=cover_url,
        source_url=resp.url,
        ext=_guess_ext(audio_url),
    )