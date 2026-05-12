# podcast_archiver/listen_notes_list.py
from __future__ import annotations

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


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
    """
    parts = urlparse(url).path.strip("/").split("/")

    # /zh-hans/podcasts/<podcast-slug>/<episode-slug>/
    if len(parts) >= 4 and parts[1] == "podcasts":
        return True

    # /podcasts/<podcast-slug>/<episode-slug>/
    if len(parts) >= 3 and parts[0] == "podcasts":
        return True

    return False


def extract_episode_links_from_listen_notes_page(page_url: str, session) -> list[str]:
    """
    从 Listen Notes podcast 列表页提取当前 HTML 中已经渲染出的 episode links。

    注意：
    - 当前只处理页面初始 HTML；
    - Load more / pagination 后续再单独逆向接口；
    - 返回的是 episode page URL，可继续交给 parse_listen_notes_episode()。
    """
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

    soup = BeautifulSoup(resp.text, "html.parser")

    links: list[str] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])

        if not is_listen_notes_episode_page(href):
            continue

        # 排除列表页自身
        if href.rstrip("/") == page_url.rstrip("/"):
            continue

        if href in seen:
            continue

        seen.add(href)
        links.append(href)

    return links


def print_episode_links(links: list[str], limit: int | None = None) -> None:
    selected = links[:limit] if limit is not None else links

    for index, link in enumerate(selected, start=1):
        print(f"{index}. {link}")