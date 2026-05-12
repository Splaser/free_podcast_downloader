# podcast_archiver/listen_notes.py
import html
import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup


AUDIO_EXT_RE = re.compile(
    r"https?://[^\"'\s<>]+?\.(?:mp3|m4a|aac|ogg|wav)(?:\?[^\"'\s<>]*)?",
    re.I,
)


@dataclass
class Episode:
    title: str
    podcast_title: str
    author: str
    description: str
    audio_url: str
    cover_url: str
    source_url: str
    ext: str = ".mp3"


def _parse_title_from_page_title(page_title: str) -> tuple[str, str]:
    """
    页面 title 通常类似：
    236《首尔之春》我会牢牢记住你的脸 - 反派影评 (播客) | Listen Notes

    返回:
    episode_title, podcast_title
    """
    if not page_title:
        return "", ""

    left = page_title
    right = ""

    if " - " in page_title:
        left, right = page_title.split(" - ", 1)

    episode_title = left.strip()

    podcast_title = ""
    if right:
        podcast_title = (
            right.split("|", 1)[0]
            .replace("(播客)", "")
            .replace("(Podcast)", "")
            .strip()
        )

    return episode_title, podcast_title


def _recursive_find_key(obj, keys: set[str]):
    results = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and v:
                results.append(v)
            results.extend(_recursive_find_key(v, keys))

    elif isinstance(obj, list):
        for item in obj:
            results.extend(_recursive_find_key(item, keys))

    return results


def _first_str(values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _guess_ext(audio_url: str) -> str:
    lowered = audio_url.lower()

    for ext in [".mp3", ".m4a", ".aac", ".ogg", ".wav"]:
        if ext in lowered:
            return ext

    return ".mp3"


def _extract_json_scripts(soup: BeautifulSoup):
    results = []

    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        text = script.string or script.get_text() or ""

        if not text.strip():
            continue

        if "json" not in script_type:
            continue

        try:
            results.append(json.loads(html.unescape(text.strip())))
        except Exception:
            continue

    return results


def parse_listen_notes_episode(url: str, session) -> Episode:
    resp = session.get(
        url,
        timeout=30,
        headers={
            "Referer": "https://www.listennotes.com/",
        },
    )
    print(f"[INFO] GET {url}")
    print(f"[INFO] status={resp.status_code}")

    if resp.status_code == 403:
        with open("debug_403_listennotes.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print("[WARN] 403 page saved to debug_403_listennotes.html")


    resp.raise_for_status()

    page_html = resp.text
    soup = BeautifulSoup(page_html, "html.parser")

    page_title = soup.title.get_text(strip=True) if soup.title else ""

    page_episode_title, page_podcast_title = _parse_title_from_page_title(page_title)
    
    json_objects = _extract_json_scripts(soup)

    audio_url = ""
    play_url = ""
    cover_url = ""
    title = page_episode_title
    description = ""
    podcast_title = page_podcast_title
    author = ""

    for obj in json_objects:
        if not audio_url:
            audio_url = _first_str(_recursive_find_key(obj, {"audio", "audio_url", "audioUrl"}))

        if not play_url:
            play_url = _first_str(_recursive_find_key(obj, {"play_url", "playUrl"}))

        if not cover_url:
            cover_url = _first_str(
                _recursive_find_key(
                    obj,
                    {"image", "thumbnail", "cover", "cover_url", "coverUrl"},
                )
            )

        if not title:
            title = _first_str(_recursive_find_key(obj, {"title"}))

        if not description:
            description = _first_str(_recursive_find_key(obj, {"description", "desc"}))

        if not podcast_title:
            if " - " in page_title:
                right = page_title.split(" - ", 1)[1]
                podcast_title = right.split("|", 1)[0].replace("(播客)", "").strip()
            else:
                podcast_title = "Podcast"

    if not audio_url:
        direct_audio = AUDIO_EXT_RE.findall(page_html)
        if direct_audio:
            audio_url = direct_audio[0]

    if not audio_url and play_url:
        audio_url = play_url

    if not title:
        title = page_title.split(" - ")[0].strip() if page_title else "episode"

    if not podcast_title:
        # 页面 title 类似：236《首尔之春》... - 反派影评 (播客) | Listen Notes
        if " - " in page_title:
            right = page_title.split(" - ", 1)[1]
            podcast_title = right.split("|", 1)[0].replace("(播客)", "").strip()
        else:
            podcast_title = "Podcast"

    if not author:
        author = podcast_title

    if not audio_url:
        raise RuntimeError("未解析到 audio_url，请检查页面结构或 cookie 状态")

    return Episode(
        title=title,
        podcast_title=podcast_title,
        author=author,
        description=description,
        audio_url=audio_url,
        cover_url=cover_url,
        source_url=url,
        ext=_guess_ext(audio_url),
    )