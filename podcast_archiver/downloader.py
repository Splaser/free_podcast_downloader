# podcast_archiver/downloader.py
from pathlib import Path

import requests

from podcast_archiver.filename import sanitize_filename
from podcast_archiver.tagging import tag_m4a


def download_file(url: str, output_path: Path, session=None):
    s = session or requests.Session()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "audio/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    with s.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True) as resp:
        print(f"[INFO] audio GET status={resp.status_code}")
        print(f"[INFO] audio final_url={resp.url}")
        print(f"[INFO] audio content-type={resp.headers.get('content-type')}")

        if resp.status_code >= 400:
            preview = resp.content[:500].decode("utf-8", errors="replace")
            print("[WARN] audio error preview:")
            print(preview)
            resp.raise_for_status()

        total = resp.headers.get("content-length")
        total = int(total) if total and total.isdigit() else None

        downloaded = 0

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue

                f.write(chunk)
                downloaded += len(chunk)

                if total:
                    percent = downloaded * 100 / total
                    print(f"\r[INFO] downloading... {percent:.1f}%", end="")

    print()
    print(f"[INFO] saved: {output_path}")


def download_episode(episode, output_dir: str = "downloads", session=None, write_tag: bool = True):
    """
    下载 parse_listen_notes_episode() 返回的 Episode。
    """
    podcast_dir = sanitize_filename(episode.podcast_title)
    filename = sanitize_filename(episode.title) + episode.ext

    output_path = Path(output_dir) / podcast_dir / filename

    if output_path.exists():
        print(f"[INFO] file exists, skip download: {output_path}")
    else:
        download_file(episode.audio_url, output_path, session=session)

    if write_tag and episode.ext.lower() in [".m4a", ".mp4"]:
        tag_m4a(
            str(output_path),
            title=episode.title,
            artist=episode.author or episode.podcast_title,
            album=episode.podcast_title,
            description=episode.description,
            cover_url=episode.cover_url,
            session=session,
        )
    elif write_tag:
        print(f"[WARN] tagging skipped for unsupported ext: {episode.ext}")

    return output_path