# podcast_archiver/markdown_sidecar.py
from pathlib import Path
from bs4 import BeautifulSoup
import re

from .filename import sanitize_filename


def html_to_markdownish(raw: str) -> str:
    """
    轻量 HTML -> Markdown。
    保留链接，处理换行，不追求完美排版。
    """
    if not raw:
        return ""

    soup = BeautifulSoup(raw, "html.parser")

    # a 标签转 markdown link
    for a in soup.find_all("a"):
        text = a.get_text(strip=True) or a.get("href", "")
        href = a.get("href", "")
        if href:
            a.replace_with(f"[{text}]({href})")
        else:
            a.replace_with(text)

    # br 转换行
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # p/div/li 后面补换行
    for tag in soup.find_all(["p", "div", "li"]):
        tag.append("\n")

    text = soup.get_text()

    # 清理过多空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_episode_markdown(episode) -> str:
    body = html_to_markdownish(episode.description or "")

    lines = [
        f"# {episode.title}",
        "",
        f"- Album: {episode.podcast_title}",
        f"- Author: {episode.author or episode.podcast_title}",
    ]

    if getattr(episode, "source_url", ""):
        lines.append(f"- Source: {episode.source_url}")

    if getattr(episode, "audio_url", ""):
        lines.append(f"- Audio: {episode.audio_url}")

    if getattr(episode, "cover_url", ""):
        lines.append(f"- Cover: {episode.cover_url}")

    lines.extend([
        "",
        "---",
        "",
        body or "_No description captured._",
        "",
    ])

    return "\n".join(lines)


def write_episode_markdown_sidecar(
    episode,
    audio_path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    md_path = audio_path.with_suffix(".md")

    if md_path.exists() and not overwrite:
        print(f"[INFO] md exists, skip: {md_path}")
        return md_path

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(
        build_episode_markdown(episode),
        encoding="utf-8",
        newline="\n",
    )

    print(f"[INFO] markdown sidecar saved: {md_path}")
    return md_path