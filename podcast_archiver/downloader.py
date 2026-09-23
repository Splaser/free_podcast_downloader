# podcast_archiver/downloader.py
from pathlib import Path
import re
import time

import requests
import tempfile

from .tagging import tag_m4a, tag_mp3, has_basic_tags
from .markdown_sidecar import write_episode_markdown_sidecar
from .planner import build_target_path

import subprocess

# key = str(output_path)，value = 已下载字节数
_downloaded_progress = {}


def has_aria2():
    try:
        subprocess.run(
            ["aria2c", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except FileNotFoundError:
        return False


def download_file_aria2(url: str, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "aria2c",
        "-c",  # 断点续传
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        "-x",
        "4",
        "-s",
        "4",
        "-o",
        str(output_path.name),
        "-d",
        str(output_path.parent),
        url,
    ]
    print(f"[INFO] aria2 downloading {url}")
    subprocess.run(cmd, check=True)
    print(f"[INFO] saved: {output_path}")


def download_files_aria2(
    urls: list[str], output_dir: Path, filenames: list[str] | None = None
):
    """
    使用 aria2 批量下载所有 url，直接指定输出文件名，避免后续 rename。

    urls: List of download links
    output_dir: 存储目录
    filenames: List of target filenames（与 urls 对应），若为 None，则自动生成 ep_1, ep_2...
    """
    if not has_aria2():
        raise RuntimeError("[ERROR] aria2 not found!")

    output_dir.mkdir(parents=True, exist_ok=True)

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
        "-i",
        list_file,
        "-c",
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        "-x",
        "2",
        "-s",
        "2",
        "--min-split-size=10M",
        "--max-tries=5",
        "--retry-wait=5",
        "-d",
        str(output_dir),
    ]

    print(f"[INFO] aria2 batch downloading {len(urls)} files to {output_dir}")
    subprocess.run(cmd, check=True)
    print(f"[INFO] aria2 batch download finished")


def download_file(url: str, output_path: Path, session=None, chunk_size=1024 * 256):
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
        with s.get(
            url, stream=True, timeout=60, headers=headers, allow_redirects=True
        ) as resp:
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
                        print(
                            f"\r[INFO] downloading... {percent:.1f}%",
                            end="",
                            flush=True,
                        )
        print()
        print(f"[INFO] saved: {output_path}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"[ERROR] Failed to download file via requests: {url} | {e}")


def download_file_resume(
    url: str, output_path: Path, session=None, chunk_size=1024 * 256
):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_name(output_path.name + ".part")
    control_path = partial_path.with_name(partial_path.name + ".aria2")

    # 优先 aria2 下载
    if has_aria2():
        try:
            download_file_aria2(url, partial_path)
            if not partial_path.is_file() or control_path.exists():
                raise RuntimeError("aria2 did not complete the partial file")
            partial_path.replace(output_path)
            return
        except Exception as e:
            print(f"[WARN] aria2 failed ({e}), fallback to requests download")

    # requests fallback + chunked + retry
    s = session or requests.Session()
    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
        "Accept": "audio/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    for attempt in range(3):
        downloaded = partial_path.stat().st_size if partial_path.exists() else 0
        headers = dict(base_headers)
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"
        try:
            with s.get(
                url, stream=True, timeout=60, headers=headers, allow_redirects=True
            ) as resp:
                if resp.status_code == 416 and downloaded:
                    match = re.fullmatch(
                        r"bytes \*/(\d+)", resp.headers.get("Content-Range", "")
                    )
                    if match and int(match.group(1)) == downloaded:
                        control_path.unlink(missing_ok=True)
                        partial_path.replace(output_path)
                        print(f"[INFO] saved: {output_path}")
                        return
                if resp.status_code not in (200, 206):
                    resp.raise_for_status()
                    raise RuntimeError(f"unexpected download status {resp.status_code}")

                if resp.status_code == 206:
                    match = re.fullmatch(
                        r"bytes (\d+)-(\d+)/(\d+|\*)",
                        resp.headers.get("Content-Range", ""),
                    )
                    if not match or int(match.group(1)) != downloaded:
                        raise RuntimeError("server returned a mismatched Content-Range")
                    total = int(match.group(3)) if match.group(3) != "*" else None
                    mode = "ab" if downloaded else "wb"
                else:
                    if downloaded:
                        print(
                            "[WARN] server ignored Range request, "
                            "restarting download from 0"
                        )
                    downloaded = 0
                    total = None
                    mode = "wb"

                content_length = resp.headers.get("Content-Length")
                expected = (
                    int(content_length)
                    if content_length and content_length.isdigit()
                    else None
                )
                received = 0
                with open(partial_path, mode) as f:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            received += len(chunk)
                            if expected:
                                percent = min(received * 100 / expected, 100)
                                print(
                                    f"\r[INFO] downloading... {percent:.1f}%",
                                    end="",
                                    flush=True,
                                )
                if expected is not None and received != expected:
                    if received > expected:
                        partial_path.unlink()
                    raise RuntimeError(
                        f"incomplete response: received {received}/{expected} bytes"
                    )
                if total is not None and partial_path.stat().st_size != total:
                    raise RuntimeError(
                        f"incomplete file: {partial_path.stat().st_size}/{total} bytes"
                    )
                if partial_path.stat().st_size == 0:
                    raise RuntimeError("download returned an empty file")
            print()
            control_path.unlink(missing_ok=True)
            partial_path.replace(output_path)
            print(f"[INFO] saved: {output_path}")
            return
        except (requests.exceptions.RequestException, RuntimeError) as e:
            print(f"[WARN] download attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(3)
            else:
                raise RuntimeError(
                    f"[ERROR] Failed to download after 3 attempts: {url}"
                ) from e


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
    track_index = getattr(episode, "track_index", None)
    track_total = getattr(episode, "track_total", None)

    output_path = build_target_path(episode, output_dir)

    # 旧版 aria2 曾直接写最终路径；其控制文件表明该文件尚未完成。
    legacy_control = output_path.with_name(output_path.name + ".aria2")
    was_incomplete = legacy_control.exists()
    if was_incomplete:
        partial_path = output_path.with_name(output_path.name + ".part")
        if output_path.exists() and not partial_path.exists():
            output_path.replace(partial_path)
            legacy_control.replace(partial_path.with_name(partial_path.name + ".aria2"))
        else:
            # 已有 .part 时以它为续传来源，丢弃旧版未完成的最终路径。
            output_path.unlink(missing_ok=True)
            legacy_control.unlink()
        print(f"[INFO] resuming incomplete file: {output_path}")

    file_existed = output_path.exists() and not was_incomplete

    if file_existed:
        if write_tag:
            if not retag_existing and has_basic_tags(str(output_path), episode.ext):
                print(
                    "[INFO] file exists and basic tags exist, skip download and retag"
                )
                return output_path
            else:
                print("[INFO] file exists, skip download and write/refresh tags")
        else:
            print("[INFO] file exists, skip download")
            return output_path
    else:
        download_file_resume(episode.audio_url, output_path, session=session)

    if write_tag and episode.ext.lower() in [".m4a", ".mp4"]:
        tagged = tag_m4a(
            str(output_path),
            title=episode.title,
            artist=episode.author or episode.podcast_title,
            album=episode.podcast_title,
            description=episode.description,
            cover_url=episode.cover_url,
            session=session,
            track_index=track_index,
            track_total=track_total,
        )

    elif write_tag and episode.ext.lower() == ".mp3":
        tagged = tag_mp3(
            str(output_path),
            title=episode.title,
            artist=episode.author or episode.podcast_title,
            album=episode.podcast_title,
            description=episode.description,
            cover_url=episode.cover_url,
            session=session,
            track_index=track_index,
            track_total=track_total,
        )

    elif write_tag:
        print(f"[WARN] tagging skipped for unsupported ext: {episode.ext}")
        tagged = True

    if write_tag and not tagged:
        raise RuntimeError(f"failed to write metadata tags: {output_path}")

    try:
        write_episode_markdown_sidecar(
            episode,
            output_path,
            overwrite=retag_existing,
        )
    except Exception as e:
        print(f"[WARN] markdown sidecar failed: {output_path} | {e}")

    return output_path
