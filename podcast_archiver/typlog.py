import requests
from bs4 import BeautifulSoup
from .downloader import download_episode
import re
from .filename import sanitize_filename



def probe_episode(url: str):
    """
    probe 一个 Typlog episode 页面
    返回 dict：
        index, title, mp3, cover, description, date, slug
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. episode index 从 slug 或 URL 提取
    slug = url.split("/")[-1]
    index = None
    m = re.search(r'(\d+)', slug)
    if m:
        index = int(m.group(1))

    # 2. 收集 headers 去掉 UI
    raw_headers = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)]
    headers_clean = [h for h in raw_headers if h not in ["Subscribe", "Listen This"]]

    # 3. episode title = 第三个 header（实测）
    episode_title = headers_clean[2] if len(headers_clean) >= 3 else headers_clean[-1]

    # 4. cover
    meta_cover = soup.find("meta", property="og:image")
    cover = meta_cover.get("content") if meta_cover else None

    # 5. description
    meta_desc = soup.find("meta", property="og:description")
    description = meta_desc.get("content") if meta_desc else ""

    # 6. mp3
    mp3 = None
    audio = soup.find("audio")
    if audio and audio.get("src"):
        mp3 = audio.get("src")
    if not mp3:
        source = soup.find("source")
        if source and source.get("src"):
            mp3 = source.get("src")
    if not mp3:
        matches = re.findall(r'https://[^"]+\.mp3', resp.text)
        if matches:
            mp3 = matches[0]

    return {
        "slug": slug,
        "index": index,
        "title": episode_title,
        "cover": cover,
        "mp3": mp3,
        "description": description,
        "date": None,
    }


def download_typlog_episode(url: str, output_dir: str, session=None, write_tag=True, retag_existing=False):
    """
    下载单条 Typlog episode
    """
    episode = probe_episode(url)

    class EpisodeObj:
        pass
    ep = EpisodeObj()
    ep.title = episode["title"]
    ep.podcast_title = "Typlog Podcast"
    ep.author = None
    ep.description = episode["description"]
    ep.cover_url = episode["cover"]
    ep.audio_url = episode["mp3"]
    ep.ext = ".mp3"

    # 生成 target path 时用 index + title 拼文件名
    if episode["index"] is not None:
        filename = f"{episode['index']:03d} {ep.title}{ep.ext}"
    else:
        filename = f"{ep.title}{ep.ext}"

    # 手动构建完整输出路径
    from pathlib import Path
    output_path = Path(output_dir) / sanitize_filename(ep.podcast_title) / sanitize_filename(filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 调用现有 pipeline
    download_episode(
        ep,
        output_dir=str(output_path.parent),
        session=session,
        write_tag=write_tag,
        retag_existing=retag_existing
    )

    return output_path