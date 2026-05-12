# podcast_archiver/listen_notes_list.py
from __future__ import annotations

import json
from urllib.parse import urljoin, urlparse
import html
import re
from bs4 import BeautifulSoup
from .listen_notes import Episode
from datetime import datetime, timezone



def _extract_one_int(patterns: list[str], text: str) -> int | None:
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None


def _extract_one_str(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1)
    return ""


def _fetch_episode_page_for_context(episode_url: str, session) -> str:
    resp = session.get(
        episode_url,
        timeout=30,
        headers={
            "Referer": "https://www.listennotes.com/",
        },
    )

    print(f"[INFO] Listen Notes context GET {episode_url}")
    print(f"[INFO] status={resp.status_code}")

    resp.raise_for_status()
    return resp.text


def _extract_context_from_episode_html(page_html: str) -> dict:
    """
    从 Listen Notes episode 页面提取 channel_uuid / pub_date_ms。
    作为列表页 HTML 缺失上下文时的 fallback。
    """
    channel_uuid = _extract_one_str(
        [
            r'"channel_uuid"\s*:\s*"([a-f0-9]{32})"',
            r'"channelUuid"\s*:\s*"([a-f0-9]{32})"',
            r'"channel"\s*:\s*\{.*?"channel_uuid"\s*:\s*"([a-f0-9]{32})"',
            r"/endpoints/v1/channels/([a-f0-9]{32})/episodes",
        ],
        page_html,
    )

    pub_date_ms = _extract_one_int(
        [
            r'"pub_date_ms"\s*:\s*(\d+)',
            r'"pubDateMs"\s*:\s*(\d+)',
            r'"datePublished"\s*:\s*"[^"]*"',  # placeholder，保留以后扩展
        ],
        page_html,
    )

    return {
        "channel_uuid": channel_uuid,
        "pub_date_ms": pub_date_ms,
    }


def _fill_list_context_from_episode_pages(ctx: dict, session) -> dict:
    """
    如果列表页 HTML 里没有 channel_uuid / pub_date_ms，
    就从首尾 episode 页面补。
    """
    links = ctx.get("links") or []

    if not links:
        return ctx

    need_channel = not ctx.get("channel_uuid")
    need_dates = not ctx.get("prev_pub_date") or not ctx.get("next_pub_date")

    if not need_channel and not need_dates:
        return ctx

    first_url = links[0]
    last_url = links[-1]

    first_ctx = {}
    last_ctx = {}

    try:
        first_html = _fetch_episode_page_for_context(first_url, session=session)
        first_ctx = _extract_context_from_episode_html(first_html)
    except Exception as e:
        print(f"[WARN] failed to extract context from first episode: {e}")

    if last_url != first_url:
        try:
            last_html = _fetch_episode_page_for_context(last_url, session=session)
            last_ctx = _extract_context_from_episode_html(last_html)
        except Exception as e:
            print(f"[WARN] failed to extract context from last episode: {e}")

    if not ctx.get("channel_uuid"):
        ctx["channel_uuid"] = (
            first_ctx.get("channel_uuid")
            or last_ctx.get("channel_uuid")
            or ""
        )

    first_pub = first_ctx.get("pub_date_ms")
    last_pub = last_ctx.get("pub_date_ms")

    pub_values = [v for v in [first_pub, last_pub] if isinstance(v, int)]

    if pub_values:
        ctx["prev_pub_date"] = ctx.get("prev_pub_date") or max(pub_values)
        ctx["next_pub_date"] = ctx.get("next_pub_date") or min(pub_values)

    return ctx

def _guess_ext_from_api_item(item: dict) -> str:
    audio_url = (
        item.get("audio_play_url_extension")
        or item.get("audio_play_url")
        or item.get("audio")
        or ""
    ).lower()

    for ext in [".mp3", ".m4a", ".aac", ".ogg", ".wav"]:
        if ext in audio_url:
            return ext

    return ".mp3"


def _html_to_text(value: str) -> str:
    if not value:
        return ""

    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _episode_from_api_item(item: dict) -> Episode:
    channel = item.get("channel") or {}

    title = (
        item.get("episode_title")
        or item.get("title")
        or "episode"
    )

    podcast_title = (
        channel.get("title")
        or channel.get("channel_title")
        or "Podcast"
    )

    # Listen Notes API 的 channel.author 可能是 uploader / slug，
    # 例如 lamesbond。这里统一用 podcast title，保证 tag artist 稳定。
    author = podcast_title

    cover_url = (
        item.get("episode_specific_image_big")
        or item.get("episode_specific_image")
        or channel.get("channel_image_big")
        or channel.get("channel_image")
        or ""
    )

    audio_url = (
        item.get("audio_play_url_extension")
        or item.get("audio_play_url")
        or item.get("audio")
        or ""
    )

    source_url = item.get("absolute_url") or ""

    return Episode(
        title=title.strip(),
        podcast_title=podcast_title.strip(),
        author=author.strip(),
        description=_html_to_text(item.get("description") or ""),
        audio_url=audio_url,
        cover_url=cover_url,
        source_url=source_url,
        ext=_guess_ext_from_api_item(item),
    )

def _get_cookie_value(session, name: str) -> str:
    try:
        return session.cookies.get(name) or ""
    except Exception:
        return ""

def _fetch_listen_notes_api_page(
    channel_uuid: str,
    session,
    next_pub_date: int,
    prev_pub_date: int,
    referer_url: str = "https://www.listennotes.com/",
) -> dict:
    """
    调用 Listen Notes Load more API。
    Header 尽量贴近浏览器 HAR。
    """
    url = f"https://www.listennotes.com/endpoints/v1/channels/{channel_uuid}/episodes"

    data = {
        "for_transcripts": "false",
        "next_pub_date": str(next_pub_date),
        "prev_pub_date": str(prev_pub_date),
        "sort_type": "recent_first",
    }

    csrf_token = _get_cookie_value(session, "csrftoken")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": referer_url,
        "Origin": "https://www.listennotes.com",
        "DNT": "1",
        "Sec-GPC": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    if csrf_token:
        headers["X-CSRFToken"] = csrf_token

    print(f"[INFO] Listen Notes API POST {url}")
    print(f"[INFO] referer={referer_url}")
    print(f"[INFO] csrf token: {'yes' if csrf_token else 'no'}")
    print(f"[INFO] next_pub_date={next_pub_date}")
    print(f"[INFO] prev_pub_date={prev_pub_date}")

    resp = session.post(
        url,
        data=data,
        headers=headers,
        timeout=30,
        allow_redirects=True,
    )

    print(f"[INFO] status={resp.status_code}")
    print(f"[INFO] final_url={resp.url}")
    print(f"[INFO] content-type={resp.headers.get('content-type')}")

    if resp.status_code >= 400:
        with open("debug_listennotes_api_error.html", "w", encoding="utf-8") as f:
            f.write(resp.text)

        preview = resp.text[:500].replace("\n", "\\n")
        print("[WARN] api error response saved to debug_listennotes_api_error.html")
        print(f"[WARN] api error preview={preview}")

    resp.raise_for_status()

    raw = resp.content

    if not raw:
        raise RuntimeError("Listen Notes API returned empty response body")

    # preview = raw[:500].decode("utf-8", errors="replace").replace("\n", "\\n")
    # print(f"[INFO] api response preview={preview}")

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        with open("debug_listennotes_api_response.bin", "wb") as f:
            f.write(raw)
        print("[WARN] api raw response saved to debug_listennotes_api_response.bin")
        raise

def fetch_more_episodes_from_listen_notes_api(
    channel_uuid: str,
    session,
    next_pub_date: int,
    prev_pub_date: int,
    max_pages: int = 1,
    referer_url: str = "https://www.listennotes.com/",
) -> list[Episode]:
    """
    从 Listen Notes Load more API 继续抓 episode。

    返回直接可下载的 Episode 列表。
    """
    episodes: list[Episode] = []

    current_next = next_pub_date
    current_prev = prev_pub_date

    for page_index in range(max_pages):
        data = _fetch_listen_notes_api_page(
            channel_uuid=channel_uuid,
            session=session,
            next_pub_date=current_next,
            prev_pub_date=current_prev,
            referer_url=referer_url,
        )

        bundle = data.get("bundle") or {}
        items = bundle.get("episodes") or []

        if not items:
            print(f"[WARN] API page {page_index + 1}: no episodes")
            break

        for item in items:
            audio_url = (
                item.get("audio_play_url_extension")
                or item.get("audio_play_url")
                or item.get("audio")
                or ""
            )

            if not audio_url:
                continue

            episodes.append(_episode_from_api_item(item))

        print(f"[INFO] API page {page_index + 1}: extracted {len(items)} episodes")

        has_next = bool(bundle.get("has_next"))
        next_value = bundle.get("next_pub_date")
        prev_value = bundle.get("previous_pub_date")

        if not has_next or not next_value:
            break

        current_next = int(next_value)

        if prev_value:
            current_prev = int(prev_value)

    return episodes

def _normalize_html(text: str) -> str:
    """
    用于 regex 前的轻度归一化。
    """
    if not text:
        return ""

    text = html.unescape(text)
    text = text.replace("\\/", "/")
    return text


def _extract_channel_uuid(page_html: str) -> str:
    """
    从 Listen Notes 页面 HTML 中提取 channel_uuid。
    """
    text = _normalize_html(page_html)

    patterns = [
        r'"channel_uuid"\s*:\s*"([a-f0-9]{32})"',
        r'"channelUuid"\s*:\s*"([a-f0-9]{32})"',
        r'"channelUUID"\s*:\s*"([a-f0-9]{32})"',
        r'"channel"\s*:\s*\{[^{}]{0,2000}?"channel_uuid"\s*:\s*"([a-f0-9]{32})"',
        r"/endpoints/v1/channels/([a-f0-9]{32})/episodes",
        r"endpoints/v1/channels/([a-f0-9]{32})/episodes",
        r"data-channel-uuid=[\"']([a-f0-9]{32})[\"']",
        r"channel_uuid=[\"']?([a-f0-9]{32})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.S)
        if m:
            return m.group(1)

    return ""


def _iso_to_ms(value: str) -> int | None:
    """
    ISO datetime -> epoch milliseconds.
    """
    if not value:
        return None

    try:
        value = value.strip()

        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return int(dt.timestamp() * 1000)

    except Exception:
        return None


def _extract_pub_date_values_from_html(page_html: str) -> list[int]:
    """
    从 HTML / script / JSON-LD 中尽量提取 pub_date_ms。
    """
    text = _normalize_html(page_html)
    values: list[int] = []

    int_patterns = [
        r'"pub_date_ms"\s*:\s*(\d{12,16})',
        r'"pubDateMs"\s*:\s*(\d{12,16})',
        r'"pub_date"\s*:\s*(\d{12,16})',
        r"data-pub-date-ms=[\"'](\d{12,16})[\"']",
        r"pub_date_ms\s*[:=]\s*(\d{12,16})",
    ]

    for pattern in int_patterns:
        for m in re.finditer(pattern, text, re.I):
            try:
                values.append(int(m.group(1)))
            except Exception:
                pass

    iso_patterns = [
        r'"pub_date_iso"\s*:\s*"([^"]+)"',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r"datetime=['\"]([^'\"]+)['\"]",
    ]

    for pattern in iso_patterns:
        for m in re.finditer(pattern, text, re.I):
            ms = _iso_to_ms(m.group(1))
            if ms:
                values.append(ms)

    # 去重，保持顺序
    result = []
    seen = set()

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result


def _extract_pub_date_range_from_html(page_html: str) -> tuple[int | None, int | None]:
    """
    返回：
    - prev_pub_date: 当前页最新一条
    - next_pub_date: 当前页最旧一条
    """
    values = _extract_pub_date_values_from_html(page_html)

    if not values:
        return None, None

    return max(values), min(values)


def _extract_context_from_episode_html(page_html: str) -> dict:
    """
    从 episode 页面提取 channel_uuid / pub_date_ms。
    """
    channel_uuid = _extract_channel_uuid(page_html)
    values = _extract_pub_date_values_from_html(page_html)

    pub_date_ms = None
    if values:
        # episode 页面理论上只有一个主 pub_date；取最大值更稳一点
        pub_date_ms = max(values)

    return {
        "channel_uuid": channel_uuid,
        "pub_date_ms": pub_date_ms,
    }


def _fill_list_context_from_episode_pages(ctx: dict, session) -> dict:
    """
    列表页上下文不足时，从首尾 episode 页面补 channel_uuid / pub_date cursor。
    """
    links = ctx.get("links") or []

    if not links:
        return ctx

    need_channel = not ctx.get("channel_uuid")
    need_dates = not ctx.get("prev_pub_date") or not ctx.get("next_pub_date")

    if not need_channel and not need_dates:
        return ctx

    first_url = links[0]
    last_url = links[-1]

    first_ctx = {}
    last_ctx = {}

    try:
        first_html = _fetch_episode_page_for_context(first_url, session=session)
        first_ctx = _extract_context_from_episode_html(first_html)
    except Exception as e:
        print(f"[WARN] failed to extract context from first episode: {e}")

    if last_url != first_url:
        try:
            last_html = _fetch_episode_page_for_context(last_url, session=session)
            last_ctx = _extract_context_from_episode_html(last_html)
        except Exception as e:
            print(f"[WARN] failed to extract context from last episode: {e}")

    if not ctx.get("channel_uuid"):
        ctx["channel_uuid"] = (
            first_ctx.get("channel_uuid")
            or last_ctx.get("channel_uuid")
            or ""
        )

    pub_values = []

    for item in [first_ctx, last_ctx]:
        value = item.get("pub_date_ms")
        if isinstance(value, int):
            pub_values.append(value)

    if pub_values:
        ctx["prev_pub_date"] = ctx.get("prev_pub_date") or max(pub_values)
        ctx["next_pub_date"] = ctx.get("next_pub_date") or min(pub_values)

    return ctx


def is_listen_notes_podcast_page(url: str) -> bool:
    """
    判断是否为 Listen Notes podcast 列表页。

    支持：
    - https://www.listennotes.com/zh-hans/podcasts/<podcast-slug>/
    - https://www.listennotes.com/podcasts/<podcast-slug>/
    """
    parts = urlparse(url).path.strip("/").split("/")

    # /zh-hans/podcasts/<podcast-slug>/
    if len(parts) == 3 and parts[1] == "podcasts":
        return True

    # /podcasts/<podcast-slug>/
    if len(parts) == 2 and parts[0] == "podcasts":
        return True

    return False


def is_listen_notes_episode_page(url: str) -> bool:
    """
    判断是否为 Listen Notes episode 单集页。

    支持：
    - /zh-hans/podcasts/<podcast-slug>/<episode-slug>/
    - /podcasts/<podcast-slug>/<episode-slug>/

    排除：
    - /similar/
    - /reviews/
    - /recommendations/
    - podcast 首页自身
    """
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")

    if not parts:
        return False

    last = parts[-1].lower()

    blocked_last_parts = {
        "similar",
        "reviews",
        "review",
        "recommendations",
        "episodes",
        "podcasts",
        "about",
    }

    if last in blocked_last_parts:
        return False

    # /zh-hans/podcasts/<podcast-slug>/<episode-slug>/
    if len(parts) == 4 and parts[1] == "podcasts":
        return True

    # /podcasts/<podcast-slug>/<episode-slug>/
    if len(parts) == 3 and parts[0] == "podcasts":
        return True

    return False


def _fetch_list_page(page_url: str, session) -> str:
    resp = session.get(
        page_url,
        timeout=30,
        headers={
            "Referer": "https://www.listennotes.com/",
        },
    )

    print(f"[INFO] Listen Notes list GET {page_url}")
    print(f"[INFO] status={resp.status_code}")
    print(f"[INFO] content-type={resp.headers.get('content-type')}")

    if resp.status_code == 403:
        with open("debug_403_listennotes_list.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print("[WARN] 403 page saved to debug_403_listennotes_list.html")

    resp.raise_for_status()
    return resp.text


def _extract_episode_links_from_html(page_url: str, page_html: str) -> list[str]:
    soup = BeautifulSoup(page_html, "html.parser")

    links: list[str] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])

        if not is_listen_notes_episode_page(href):
            continue

        if href.rstrip("/") == page_url.rstrip("/"):
            continue

        if href in seen:
            continue

        seen.add(href)
        links.append(href)

    return links


def _extract_next_page_url(page_url: str, page_html: str) -> str:
    """
    尝试从 HTML 中提取 Load more / next page URL。

    注意：
    如果 Listen Notes 的 Load more 是纯 JS XHR，这里可能提取不到。
    后续需要根据 Network 里的真实接口补规则。
    """
    soup = BeautifulSoup(page_html, "html.parser")

    # 常见 data-url / data-href / href
    for tag in soup.find_all(["a", "button"]):
        text = tag.get_text(" ", strip=True).lower()

        attrs = [
            tag.get("data-url"),
            tag.get("data-href"),
            tag.get("data-next-url"),
            tag.get("href"),
        ]

        if "load more" in text or "更多" in text or "next" in text:
            for value in attrs:
                if value:
                    return urljoin(page_url, value)

    # JSON / JS 里可能有 next_url / load_more_url
    patterns = [
        r'"next_url"\s*:\s*"([^"]+)"',
        r'"nextUrl"\s*:\s*"([^"]+)"',
        r'"load_more_url"\s*:\s*"([^"]+)"',
        r'"loadMoreUrl"\s*:\s*"([^"]+)"',
        r'data-next-url=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        m = re.search(pattern, page_html)
        if m:
            raw = html.unescape(m.group(1)).replace("\\/", "/")
            return urljoin(page_url, raw)

    return ""

def extract_listen_notes_list_context(page_url: str, session) -> dict:
    page_html = _fetch_list_page(page_url, session=session)

    links = _extract_episode_links_from_html(page_url, page_html)
    channel_uuid = _extract_channel_uuid(page_html)

    prev_pub_date, next_pub_date = _extract_pub_date_range_from_html(page_html)

    ctx = {
        "links": links,
        "channel_uuid": channel_uuid,
        "prev_pub_date": prev_pub_date,
        "next_pub_date": next_pub_date,
    }

    ctx = _fill_list_context_from_episode_pages(ctx, session=session)

    if not ctx.get("channel_uuid") or not ctx.get("prev_pub_date") or not ctx.get("next_pub_date"):
        with open("debug_listennotes_context.html", "w", encoding="utf-8") as f:
            f.write(page_html)
        print("[WARN] list context incomplete; saved debug_listennotes_context.html")

    return ctx


def print_episode_links(links: list[str], limit: int | None = None) -> None:
    selected = links[:limit] if limit is not None else links

    for index, link in enumerate(selected, start=1):
        print(f"{index}. {link}")
