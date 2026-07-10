# apple_podcasts.py
import re
import requests
from urllib.parse import urlparse

APPLE_HOSTS = {"podcasts.apple.com", "itunes.apple.com"}

def is_apple_podcast_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in APPLE_HOSTS or host.endswith(".podcasts.apple.com")

def extract_apple_podcast_id(url: str) -> str:
    m = re.search(r"/id(\d+)", url)
    if not m:
        raise ValueError(f"无法从 Apple Podcasts URL 解析 podcast id: {url}")
    return m.group(1)

def resolve_apple_podcast_rss_url(url: str, session=None) -> str:
    podcast_id = extract_apple_podcast_id(url)
    s = session or requests.Session()

    resp = s.get(
        "https://itunes.apple.com/lookup",
        params={
            "id": podcast_id,
            "entity": "podcast",
            "country": "us",
        },
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"Apple lookup 没有返回结果: id={podcast_id}")

    feed_url = results[0].get("feedUrl")
    if not feed_url:
        raise RuntimeError(
            f"Apple lookup 返回了播客信息，但没有 feedUrl，可能是创作者隐藏/移除了 RSS: id={podcast_id}"
        )

    return feed_url