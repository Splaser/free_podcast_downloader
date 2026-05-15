from __future__ import annotations

import html
import json
import re
import time
from random import random
from typing import Any, Literal
from urllib.parse import urlparse

from .downloader import download_episode
from .listen_notes import Episode

AFDIAN_DOMAIN = "ifdian.net"
AFDIAN_HOSTS = {"ifdian.net", "www.ifdian.net", "afdian.com", "www.afdian.com"}
DEFAULT_SLEEP_TIME = 8
POST_OUTPUT_TITLE = "single_posts"

UrlKind = Literal["album", "post"]


def is_afdian_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return (
        host in AFDIAN_HOSTS
        or host.endswith(".ifdian.net")
        or host.endswith(".afdian.com")
    )


def parse_album_id(album_url: str) -> str:
    m = re.search(r"/album/([0-9a-fA-F]+)", album_url)
    if m:
        return m.group(1)
    raise ValueError(f"无法从 URL 解析 album_id: {album_url}")


def parse_post_id(post_url: str) -> str:
    m = re.search(r"/p/([0-9a-fA-F]+)", post_url)
    if m:
        return m.group(1)
    raise ValueError(f"无法从 URL 解析 post_id: {post_url}")


def parse_input_url(url: str) -> tuple[UrlKind, str]:
    if re.search(r"/album/[0-9a-fA-F]+", url):
        return "album", parse_album_id(url)

    if re.search(r"/p/[0-9a-fA-F]+", url):
        return "post", parse_post_id(url)

    raise ValueError(f"不支持的爱发电 URL 格式: {url}")


def _api_url(path: str, domain: str = AFDIAN_DOMAIN) -> str:
    return f"https://{domain}{path}"


def get_album_name(album_id: str, session, domain: str = AFDIAN_DOMAIN) -> str:
    if session is None:
        raise ValueError("get_album_name() 需要传入已认证的 session")

    try:
        resp = session.get(
            _api_url("/api/user/get-album-info", domain),
            params={"album_id": album_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        album_title = data.get("data", {}).get("album", {}).get("title")
        if album_title:
            return album_title

    except Exception as e:
        print("[WARN] 获取专辑信息失败:", e)

    return album_id


def extract_album_list(resp_data: Any) -> tuple[list[dict], int]:
    """
    兼容爱发电接口返回结构变化：
    data 可能直接是 list，也可能包在 list/items/posts 等字段中。
    """
    albums: list[dict] = []
    has_more = 0

    if isinstance(resp_data, list):
        return resp_data, 0

    if isinstance(resp_data, dict):
        for key in ["list", "items", "posts"]:
            value = resp_data.get(key)
            if isinstance(value, list):
                albums = value
                has_more = resp_data.get("has_more", 0)
                return albums, has_more

        for value in resp_data.values():
            if isinstance(value, list):
                albums = value
                has_more = resp_data.get("has_more", 0)
                return albums, has_more

    print("[WARN] 当前 cookie 可能失效，或请求过快导致空返回。")
    return albums, has_more


def _decode_json_string(raw: str) -> str:
    if raw is None:
        return ""

    raw = html.unescape(raw)

    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw.replace("\\/", "/")


def _regex_json_field(text: str, key: str) -> str:
    pattern = rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"'
    m = re.search(pattern, text)
    if not m:
        return ""
    return _decode_json_string(m.group(1))


def _extract_user_name(text: str) -> str:
    m = re.search(
        r'"user"\s*:\s*\{.*?"name"\s*:\s*"((?:\\.|[^"\\])*)"',
        text,
        re.S,
    )
    if m:
        return _decode_json_string(m.group(1))

    return _regex_json_field(text, "name") or "unknown"


def _find_first_post_dict(obj: Any) -> dict | None:
    if isinstance(obj, dict):
        keys = set(obj.keys())
        if (
            "title" in keys
            or "content" in keys
            or "audio" in keys
            or "audio_thumb" in keys
            or "medias" in keys
            or "media" in keys
        ):
            return obj

        for value in obj.values():
            found = _find_first_post_dict(value)
            if found:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = _find_first_post_dict(item)
            if found:
                return found

    return None


def _looks_like_audio_url(value: str) -> bool:
    lowered = value.lower()

    if not value.startswith("http"):
        return False

    if any(x in lowered for x in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
        return False

    return True


def _find_audio_url(obj: Any) -> str:
    audio_keys = {
        "audio",
        "audio_url",
        "audioUrl",
        "media_url",
        "mediaUrl",
        "file_url",
        "fileUrl",
        "download_url",
        "downloadUrl",
        "url",
    }

    if isinstance(obj, dict):
        for key in audio_keys:
            value = obj.get(key)
            if isinstance(value, str) and _looks_like_audio_url(value):
                return value

        type_value = str(
            obj.get("type")
            or obj.get("media_type")
            or obj.get("mediaType")
            or obj.get("file_type")
            or ""
        ).lower()

        if "audio" in type_value or "mp3" in type_value or "sound" in type_value:
            for key in [
                "url",
                "src",
                "file_url",
                "fileUrl",
                "media_url",
                "mediaUrl",
                "download_url",
            ]:
                value = obj.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value

        for value in obj.values():
            found = _find_audio_url(value)
            if found:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = _find_audio_url(item)
            if found:
                return found

    return ""


def _find_thumb_url(obj: Any) -> str:
    thumb_keys = {
        "audio_thumb",
        "audioThumb",
        "cover",
        "cover_url",
        "coverUrl",
        "thumb",
        "thumbnail",
        "pic",
        "image",
        "image_url",
        "imageUrl",
    }

    if isinstance(obj, dict):
        for key in thumb_keys:
            value = obj.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value

        for value in obj.values():
            found = _find_thumb_url(value)
            if found:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = _find_thumb_url(item)
            if found:
                return found

    return ""


def _guess_ext(audio_url: str) -> str:
    lowered = (audio_url or "").lower()

    for ext in [".mp3", ".m4a", ".aac", ".ogg", ".wav", ".mp4"]:
        if ext in lowered:
            return ".m4a" if ext == ".mp4" else ext

    return ".mp3"


def _normalize_post_detail(raw: dict, post_id: str) -> dict:
    title = raw.get("title") or raw.get("name") or post_id
    content = raw.get("content") or raw.get("desc") or raw.get("description") or ""

    user = raw.get("user") or raw.get("author") or {}
    if isinstance(user, dict):
        author = (
            user.get("name")
            or user.get("user_name")
            or user.get("userName")
            or "unknown"
        )
    else:
        author = "unknown"

    audio = (
        raw.get("audio")
        or raw.get("audio_url")
        or raw.get("audioUrl")
        or _find_audio_url(raw)
    )

    audio_thumb = (
        raw.get("audio_thumb")
        or raw.get("audioThumb")
        or raw.get("cover")
        or raw.get("cover_url")
        or raw.get("coverUrl")
        or raw.get("thumb")
        or _find_thumb_url(raw)
    )

    return {
        "title": str(title or post_id),
        "user": {"name": str(author or "unknown")},
        "content": str(content or ""),
        "audio_thumb": str(audio_thumb or ""),
        "audio": str(audio or ""),
    }


def get_post_from_page(post_id: str, session, domain: str = AFDIAN_DOMAIN) -> dict:
    if session is None:
        raise ValueError("get_post_from_page() 需要传入已认证的 session")

    api_url = _api_url("/api/post/get-detail", domain)
    params = {"post_id": post_id, "album_id": ""}

    try:
        resp = session.get(api_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        post_like = _find_first_post_dict(data)
        if post_like:
            item = _normalize_post_detail(post_like, post_id)

            if item.get("audio"):
                print("[INFO] /p/ 资源通过 /api/post/get-detail 解析成功")
                return item

            print("[WARN] /api/post/get-detail 返回成功，但未解析到 audio")
            return item

        print("[WARN] /api/post/get-detail 没找到 post-like 结构")

    except Exception as e:
        print("[WARN] /api/post/get-detail 请求失败:", e)

    url = f"https://{domain}/p/{post_id}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    text = resp.text

    title = _regex_json_field(text, "title") or post_id
    content = _regex_json_field(text, "content")
    audio = _regex_json_field(text, "audio")
    audio_thumb = (
        _regex_json_field(text, "audio_thumb")
        or _regex_json_field(text, "thumb")
        or _regex_json_field(text, "cover")
    )
    author = _extract_user_name(text)

    if not audio:
        print("[WARN] 当前 /p/ 页面没有解析到 audio 字段，可能是页面结构变化。")

    return {
        "title": title,
        "user": {"name": author},
        "content": content,
        "audio_thumb": audio_thumb,
        "audio": audio,
    }


def _episode_from_item(
    item: dict, podcast_title: str, source_url: str = ""
) -> Episode | None:
    title = str(item.get("title") or "episode").strip()

    user = item.get("user") or {}
    author = user.get("name") if isinstance(user, dict) else ""

    audio_url = str(item.get("audio") or "").strip()
    if not audio_url:
        print(f"[WARN] 本条动态没有音频文件，跳过: {title}")
        return None

    return Episode(
        title=title,
        podcast_title=podcast_title,
        author=author or podcast_title,
        description=str(item.get("content") or ""),
        audio_url=audio_url,
        cover_url=str(item.get("audio_thumb") or ""),
        source_url=source_url,
        ext=_guess_ext(audio_url),
    )


def print_afdian_episode(episode: Episode, index: int | None = None) -> None:
    prefix = f"{index}. " if index is not None else ""

    print(f"{prefix}{episode.title}")
    print(f"   album: {episode.podcast_title}")
    print(f"   author: {episode.author}")
    print(f"   audio: {episode.audio_url}")
    print(f"   ext: {episode.ext}")
    print()


def iter_album_items(
    album_id: str,
    session,
    *,
    latest: int | None = None,
    offset: int = 0,
    domain: str = AFDIAN_DOMAIN,
) -> list[dict]:
    """
    latest=None: asc 全量归档；
    latest=n: desc 取最新 n 条。
    offset 会在最终列表上应用，保持和现有 CLI 习惯一致。
    """
    items: list[dict] = []
    seen = set()

    if latest is None:
        params = {
            "album_id": album_id,
            "lastRank": 0,
            "rankOrder": "asc",
            "rankField": "rank",
        }
        wanted_total = None

    else:
        params = {
            "album_id": album_id,
            "lastRank": 0,
            "rankOrder": "desc",
            "rankField": "publish_sn",
        }
        wanted_total = max(offset, 0) + max(latest, 0)

    while True:
        resp = session.get(
            _api_url("/api/user/get-album-post", domain),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()

        data = resp.json().get("data", {})
        page_items, has_more = extract_album_list(data)

        if not page_items:
            print("[WARN] 当前返回数据为空，跳过本次循环")
            break

        for item in page_items:
            key = (
                item.get("post_id")
                or item.get("id")
                or item.get("title")
                or json.dumps(item, sort_keys=True, ensure_ascii=False)
            )

            if key in seen:
                continue

            seen.add(key)
            items.append(item)

        if wanted_total is not None and len(items) >= wanted_total:
            break

        if page_items:
            params["lastRank"] = page_items[-1].get(
                "rank",
                params.get("lastRank", 0) + 10,
            )

        if not has_more:
            break

    offset = max(offset or 0, 0)

    if latest is None:
        return items[offset:]

    return items[offset : offset + latest]


def get_album_episodes(
    album_id: str,
    session,
    *,
    latest: int | None = None,
    offset: int = 0,
    domain: str = AFDIAN_DOMAIN,
) -> list[Episode]:
    album_name = get_album_name(album_id, session=session, domain=domain)
    items = iter_album_items(
        album_id,
        session,
        latest=latest,
        offset=offset,
        domain=domain,
    )

    episodes: list[Episode] = []

    for item in items:
        ep = _episode_from_item(item, podcast_title=album_name)
        if ep:
            episodes.append(ep)

    return episodes


def get_single_post_episode(
    post_id: str,
    session,
    *,
    domain: str = AFDIAN_DOMAIN,
) -> Episode | None:
    item = get_post_from_page(post_id, session=session, domain=domain)
    return _episode_from_item(
        item,
        podcast_title=POST_OUTPUT_TITLE,
        source_url=f"https://{domain}/p/{post_id}",
    )


def download_afdian_episodes(
    episodes: list[Episode],
    *,
    output_dir: str = "downloads",
    session=None,
    write_tag: bool = True,
    retag_existing: bool = False,
    sleep_time: int = DEFAULT_SLEEP_TIME,
) -> None:
    total = len(episodes)

    for index, episode in enumerate(episodes, start=1):
        print(f"[INFO] downloading {index}/{total}")
        print("title:", episode.title)
        print("album:", episode.podcast_title)
        print("audio:", episode.audio_url)

        try:
            output_path = download_episode(
                episode,
                output_dir=output_dir,
                session=session,
                write_tag=write_tag,
                retag_existing=retag_existing,
            )
            print("done:", output_path)

        except Exception as e:
            print(f"[ERROR] download failed: {episode.title}")
            print(f"[ERROR] {e}")

        if index < total and sleep_time > 0:
            time.sleep(sleep_time + random() * 3)
