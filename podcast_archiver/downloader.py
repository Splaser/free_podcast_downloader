# podcast_archiver/downloader.py
from pathlib import Path

import requests

from podcast_archiver.filename import sanitize_filename
from podcast_archiver.tagging import tag_m4a, tag_mp3, has_basic_tags
import subprocess


# key = str(output_path)，value = 已下载字节数
_downloaded_progress = {}


def has_aria2():
    try:
        subprocess.run(["aria2c", "-v"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def download_file_aria2(url: str, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "aria2c",
        "-c",  # 断点续传
        "-x", "16",  # 最大 16 线程
        "-s", "16",  # 分段源数
        "-o", str(output_path.name),
        "-d", str(output_path.parent),
        url
    ]
    print(f"[INFO] aria2 downloading {url}")
    subprocess.run(cmd, check=True)
    print(f"[INFO] saved: {output_path}")


def download_file(url: str, output_path: Path, session=None, chunk_size=1024*256):
    """
    普通下载文件（requests fallback），断点续传由 download_file_resume 或者文件大小控制
    """
    s = session or requests.Session()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
        "Accept": "audio/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    downloaded = _downloaded_progress.get(str(output_path), 0)
    if output_path.exists():
        downloaded = max(downloaded, output_path.stat().st_size)
    _downloaded_progress[str(output_path)] = downloaded

    try:
        with s.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True) as resp:
            if resp.status_code not in [200, 206]:
                resp.raise_for_status()

            total = resp.headers.get("content-length")
            if total and total.isdigit():
                total = int(total) + downloaded if downloaded else int(total)
            else:
                total = None

            mode = "ab" if downloaded else "wb"
            with open(output_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    _downloaded_progress[str(output_path)] = downloaded
                    if total:
                        percent = min(downloaded * 100 / total, 100)
                        print(f"\r[INFO] downloading... {percent:.1f}%", end="", flush=True)
        print()
        print(f"[INFO] saved: {output_path}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"[ERROR] Failed to download file via requests: {url} | {e}")


def download_file_resume(url: str, output_path: Path, session=None, chunk_size=1024*256):
    """
    下载单个文件，支持断点续传。
    优先使用 aria2（多线程 + 断点续传），无 aria2 则 fallback requests。
    """
    # 优先 aria2
    if has_aria2():
        try:
            download_file_aria2(url, output_path)
            return
        except Exception as e:
            print(f"[WARN] aria2 failed ({e}), fallback to requests download")

    s = session or requests.Session()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
        "Accept": "audio/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    key = str(output_path)
    downloaded = _downloaded_progress.get(key, 0)
    if output_path.exists():
        downloaded = max(downloaded, output_path.stat().st_size)
    _downloaded_progress[key] = downloaded

    # 增加简单重试机制
    for attempt in range(3):
        try:
            with s.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True) as resp:
                if resp.status_code not in [200, 206]:
                    resp.raise_for_status()

                total = resp.headers.get("content-length")
                if total and total.isdigit():
                    total = int(total) + \
                        downloaded if downloaded else int(total)
                else:
                    total = None

                mode = "ab" if downloaded else "wb"
                with open(output_path, mode) as f:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            percent = min(downloaded * 100 / total, 100)
                            print(f"\r[INFO] downloading... {percent:.1f}%", end="", flush=True)
                print()
                print(f"[INFO] saved: {output_path}")
                return  # 下载成功，退出重试
        except requests.exceptions.RequestException as e:
            print(f"[WARN] download attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                print("[INFO] retrying in 3s...")
                import time
                time.sleep(3)
            else:
                raise RuntimeError(f"[ERROR] Failed to download after 3 attempts: {url}")


def download_episode(
    episode,
    output_dir: str = "downloads",
    session=None,
    write_tag: bool = True,
    retag_existing: bool = False,
):
    """
    下载 episode。

    逻辑：
    - 文件不存在：下载，然后写 tag
    - 文件存在且已有基础 tag：默认直接跳过
    - 文件存在但缺 tag：补 tag
    - retag_existing=True：即使已有 tag，也强制重写
    """
    podcast_dir = sanitize_filename(episode.podcast_title)
    filename = sanitize_filename(episode.title) + episode.ext

    output_path = Path(output_dir) / podcast_dir / filename

    file_existed = output_path.exists()

    if file_existed and write_tag and not retag_existing and has_basic_tags(str(output_path), episode.ext):
        print("[INFO] skip download and retag")
    else:
        download_file_resume(episode.audio_url, output_path, session=session)

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

    elif write_tag and episode.ext.lower() == ".mp3":
        tag_mp3(
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
