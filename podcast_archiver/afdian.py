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


def _extract_publish_time(ep: Episode) -> int | None:
    item = getattr(ep, "afdian_item", None)
    if not isinstance(item, dict):
        return None

    value = item.get("publish_time")
    if value is None:
        return None

    try:
        return int(value)
    except Exception:
        return None


def _has_publish_time_sort(episodes: list[Episode]) -> bool:
    if not episodes:
        return False

    count = sum(_extract_publish_time(ep) is not None for ep in episodes)
    return count == len(episodes)


def _episode_sub_order(title: str) -> int:
    """
    同一主编号下的次序微调。

    数字越小越靠前：
    0 = 默认主条目
    1 = 上
    2 = 中
    3 = 下
    4 = 焦点问题 / 扩展问题
    5 = 免费 / 试听
    """
    title = title or ""

    if "（上）" in title or "(上)" in title or "-上" in title or "上：" in title:
        return 1

    if "（中）" in title or "(中)" in title or "-中" in title or "中：" in title:
        return 2

    if "（下）" in title or "(下)" in title or "-下" in title or "下：" in title:
        return 3

    if "焦点问题" in title:
        return 4

    if "免费" in title or "试听" in title:
        return 5

    return 0


def _track_sort_key(ep: Episode, explicit_index: int | None) -> tuple[int, int, int]:
    """
    编号型 album 的排序规则。

    group:
    0 = 正片 / 显式编号
    1 = 番外
    2 = 附录
    3 = 免费试听
    4 = 其他兜底
    """
    title = ep.title or ""

    # 免费试听最后，优先级最高
    if "免费试听" in title:
        return (3, 9999, 0)

    if explicit_index is not None:
        return (0, explicit_index, _episode_sub_order(title))

    # 番外放在正片后
    if "番外" in title:
        return (1, 9000, 0)

    # 附录放番外后，尽量按标题里的日常节目编号排
    m = re.search(r"第\s*0*(\d+)\s*期", title)
    if title.startswith("附") and m:
        return (2, int(m.group(1)), 0)

    if title.startswith("附"):
        return (2, 9999, 0)

    return (4, 9999, 0)


def _assign_track_indexes(episodes: list[Episode]) -> list[Episode]:
    indexed_episodes = [
        (ep, _extract_title_index(ep.title))
        for ep in episodes
    ]

    explicit_count = sum(index is not None for _, index in indexed_episodes)

    # 多数条目能提取编号，就认为这是编号型专辑，而不是 feed 型专辑
    use_title_index = (
        len(episodes) > 0
        and explicit_count >= 3
        and explicit_count >= len(episodes) * 0.5
    )

    if use_title_index:
        indexed_episodes = sorted(
            indexed_episodes,
            key=lambda pair: _track_sort_key(pair[0], pair[1]),
        )

        episodes = [ep for ep, _ in indexed_episodes]

        total = len(episodes)
        for index, ep in enumerate(episodes, start=1):
            setattr(ep, "track_index", index)
            setattr(ep, "track_total", total)
            print(
                f"[DEBUG] track index from title-sort: "
                f"{index}/{total} | {ep.title}"
            )

    else:
        total = len(episodes)
        for index, ep in enumerate(episodes, start=1):
            setattr(ep, "track_index", index)
            setattr(ep, "track_total", total)
            print(
                f"[DEBUG] track index from album order: "
                f"{index}/{total} | {ep.title}"
                )

    return episodes


def _extract_title_index(title: str) -> int | None:
    """
    从标题中提取显式节目序号。

    优先识别标题开头附近的编号，避免误抓正文里的年份/评分/期数。
    """
    title = (title or "").strip()

    patterns = [
        # 001、xxx / 001. xxx / 001：xxx
        r"^\s*0*(\d{1,4})\s*[、.．:：\-—_]\s*",

        # EP001 / E001 / No.001 / #001
        r"^\s*(?:EP|E|No\.?|#)\s*0*(\d{1,4})\b",

        # 第001期 / 第001集 / 第001回
        r"^\s*第\s*0*(\d{1,4})\s*[期集回话讲章]\b",

        # 系列名001：xxx / QA007（上） / QA007-上 / 书影012：xxx
        # 例：书影012、QA009、会员问答005、某某专题012、QA007（上）
        r"^\s*[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9·\-\s]{0,20}?\s*0*(\d{1,4})(?=\s*[:：\-—_、 （(]|$)",
    ]

    for pattern in patterns:
        m = re.search(pattern, title, re.I)
        if not m:
            continue

        try:
            value = int(m.group(1))
        except ValueError:
            continue

        # 防止误抓年份，比如 2018、2024
        if 1 <= value <= 999:
            return value

    return None


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


def _normalize_guessed_album(album: str) -> str:
    """
    对从标题里猜出来的伪 album 做归一化，避免作者改标题导致目录分裂。

    例：
    “十年直播”精修
    “十年直播”精修版
    -> “十年直播”精修版
    """
    album = (album or "").strip()
    album = album.strip(" -_—－:：，,、")

    alias_rules = [
        # 反派影评这个系列标题近期出现过：
        # “十年直播”精修之xxx
        # “十年直播”精修版之xxx
        (
            r"^([“\"']?十年直播[”\"']?)精修$",
            r"\1精修版",
        ),
    ]

    for pattern, repl in alias_rules:
        album = re.sub(pattern, repl, album)

    return album or POST_OUTPUT_TITLE


def _guess_single_post_album_from_title(title: str) -> str:
    """
    从爱发电单条 post 标题推断 album。

    例：
    “十年直播”精修版之“柏小莲”：简中媒体消亡史。
    -> “十年直播”精修版
    """
    title = (title or "").strip()

    patterns = [
        # “十年直播”精修版之“柏小莲”：xxx
        r"^(.{2,80}?)\s*之\s*[“\"《（(【\[]?.{1,80}",

        # 兜底：xxx：yyy / xxx: yyy
        # 避免太短标题误切，要求冒号前至少 4 个字符
        r"^(.{4,80}?)\s*[：:]\s*.{2,}",
    ]

    for pattern in patterns:
        m = re.search(pattern, title)
        if not m:
            continue

        album = m.group(1).strip()
        album = _normalize_guessed_album(album)
        if len(album) >= 2:
            return album

    return POST_OUTPUT_TITLE



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
    offset: int = 0,
    domain: str = AFDIAN_DOMAIN,
) -> list[dict]:
    """
    latest=n: desc 取最新 n 条。
    offset 会在最终列表上应用，保持和现有 CLI 习惯一致。
    """
    items: list[dict] = []
    seen = set()

    params = {
            "album_id": album_id,
            "lastRank": 0,
            "rankOrder": "asc",
            "rankField": "rank",
        }
    wanted_total = None

    while True:
        resp = session.get(
            _api_url("/api/user/get-album-post", domain),
            params=params,
            timeout=30,
        )

        print("[DEBUG] album-post status:", resp.status_code)
        print("[DEBUG] album-post url:", resp.url)
        print("[DEBUG] album-post preview:", resp.text[:500])

        resp.raise_for_status()

        raw = resp.json()
        print("[DEBUG] album-post json keys:", raw.keys())
        print("[DEBUG] album-post ec:", raw.get("ec"))
        print("[DEBUG] album-post msg:", raw.get("msg"))

        raw = resp.json()

        ec = raw.get("ec")
        em = raw.get("em") or raw.get("msg") or ""

        if ec != 200:
            print(f"[ERROR] Afdian API error: ec={ec}, em={em}")

            if ec == 40100:
                print("[HINT] 当前 session 没有有效登录态。请确认浏览器已登录 ifdian.net，并且脚本读取的是同一个浏览器 profile。")
                print("[HINT] 如果 cookie names 里没有 auth_token，说明没有拿到爱发电登录 cookie。")

            break

        data = raw.get("data", {})
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

        if page_items:
            params["lastRank"] = page_items[-1].get(
                "rank",
                params.get("lastRank", 0) + 10,
            )

        if not has_more:
            break

    offset = max(offset or 0, 0)
    return items[offset:]


def get_album_episodes(
    album_id: str,
    session,
    *,
    latest: int | None = None,
    offset: int = 0,
    domain: str = AFDIAN_DOMAIN,
) -> list[Episode]:
    album_name = get_album_name(album_id, session=session, domain=domain)

    # 关键：先取全量 album 列表。
    # 这样 _assign_track_indexes() 才能知道每一集在整个 album 里的真实位置。
    all_items = iter_album_items(
        album_id,
        session,
        offset=0,
        domain=domain,
    )

    all_episodes: list[Episode] = []

    for item in all_items:
        ep = _episode_from_item(item, podcast_title=album_name)
        if ep:
            setattr(ep, "afdian_item", item)
            all_episodes.append(ep)

    all_episodes = _assign_track_indexes(all_episodes)

    offset = max(offset or 0, 0)

    if latest is None:
        return all_episodes[offset:]

    # _assign_track_indexes() 返回的是老到新排序。
    # latest 语义应该是最新 n 条，所以从尾部倒着取，再恢复为新到旧下载。
    selected = list(reversed(all_episodes))[offset : offset + latest]

    return selected


def get_single_post_episode(
    post_id: str,
    session,
    *,
    domain: str = AFDIAN_DOMAIN,
) -> Episode | None:
    item = get_post_from_page(post_id, session=session, domain=domain)

    title = str(item.get("title") or "").strip()
    podcast_title = _guess_single_post_album_from_title(title)

    print(f"[INFO] single post album guessed: {podcast_title}")
    
    return _episode_from_item(
        item,
        podcast_title=podcast_title,
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
