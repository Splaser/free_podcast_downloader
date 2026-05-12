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


def download_files_aria2(urls: list[str], output_dir: Path, filenames: list[str] | None = None):
    """
    使用 aria2 批量下载所有 url，直接指定输出文件名，避免后续 rename。
    
    urls: List of download links
    output_dir: 存储目录
    filenames: List of target filenames（与 urls 对应），若为 None，则自动生成 ep_1, ep_2...
    """
    if not has_aria2():
        raise RuntimeError("[ERROR] aria2 not found!")

    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建临时 txt 列表文件
    import tempfile
    with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
        for idx, url in enumerate(urls):
            # 如果用户提供 filenames，就用 target name，否则用默认 ep_1, ep_2...
            if filenames and idx < len(filenames):
                out_name = filenames[idx]
            else:
                out_name = f"ep_{idx+1}{Path(url).suffix}"
            # Aria2 list 文件里指定输出文件名
            f.write(f"{url}\n  out={out_name}\n")
        list_file = f.name

    cmd = [
        "aria2c",
        "-i", list_file,
        "-c",          # 断点续传
        "-x", "8",     # 最大 16 线程
        "-s", "8",     # 分段源数
        "--max-tries=5",
        "--retry-wait=5",
        "-d", str(output_dir),
    ]

    print(f"[INFO] aria2 batch downloading {len(urls)} files to {output_dir}")
    subprocess.run(cmd, check=True)
    print(f"[INFO] aria2 batch download finished")


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
    key = str(output_path)
    downloaded = _downloaded_progress.get(key, 0)
    if output_path.exists():
        downloaded = max(downloaded, output_path.stat().st_size)
    _downloaded_progress[key] = downloaded

    # 优先 aria2 下载
    if has_aria2():
        try:
            download_file_aria2(url, output_path)
            return
        except Exception as e:
            print(f"[WARN] aria2 failed ({e}), fallback to requests download")

    # requests fallback + chunked + retry
    s = session or requests.Session()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
        "Accept": "audio/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    for attempt in range(3):
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
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            _downloaded_progress[key] = downloaded
                            if total:
                                percent = min(downloaded * 100 / total, 100)
                                print(f"\r[INFO] downloading... {percent:.1f}%", end="", flush=True)
            print()
            print(f"[INFO] saved: {output_path}")
            return
        except requests.exceptions.RequestException as e:
            print(f"[WARN] download attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
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
