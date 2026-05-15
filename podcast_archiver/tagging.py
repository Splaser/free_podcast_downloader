# podcast_archiver/tagging.py
import requests
import re
from pathlib import Path
from urllib.parse import urlparse

from mutagen.mp4 import MP4, MP4Cover
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, COMM, ID3NoHeaderError

_cover_cache: dict[str, bytes | None] = {}
_local_cover_cache: dict[str, bytes | None] = {}


def has_m4a_basic_tags(filename: str) -> bool:
    """
    检查 m4a 是否已有基础 metadata。
    只检查 title / artist / album，不强制检查封面。
    """
    try:
        audio = MP4(filename)

        title = audio.get("\xa9nam")
        artist = audio.get("\xa9ART")
        album = audio.get("\xa9alb")

        return bool(title and artist and album)

    except Exception:
        return False


def has_mp3_basic_tags(filename: str) -> bool:
    """
    检查 mp3 是否已有基础 metadata。
    只检查 title / artist / album，不强制检查封面。
    """
    try:
        audio = EasyID3(filename)

        title = audio.get("title")
        artist = audio.get("artist")
        album = audio.get("album")

        return bool(title and artist and album)

    except Exception:
        return False


def has_basic_tags(filename: str, ext: str) -> bool:
    ext = ext.lower()

    if ext in [".m4a", ".mp4"]:
        return has_m4a_basic_tags(filename)

    if ext == ".mp3":
        return has_mp3_basic_tags(filename)

    return False


def _guess_cover_referer(cover_url: str) -> str:
    host = urlparse(cover_url).netloc.lower()

    if "firstory.me" in host:
        return "https://open.firstory.me/"

    if "listennotes.com" in host:
        return "https://www.listennotes.com/"

    if "afdian" in host or "afdiancdn" in host:
        return "https://ifdian.net/"

    return ""


def _download_cover(cover_url: str, session=None) -> bytes | None:
    if not cover_url:
        return None

    if cover_url in _cover_cache:
        return _cover_cache[cover_url]

    s = session or requests.Session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
    }

    referer = _guess_cover_referer(cover_url)
    if referer:
        headers["Referer"] = referer

    try:
        resp = s.get(
            cover_url,
            timeout=30,
            headers=headers,
            allow_redirects=True,
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "").lower()
        if (
            content_type
            and "image" not in content_type
            and "octet-stream" not in content_type
        ):
            print(
                f"[WARN] cover content-type looks unusual: {content_type} | {cover_url}"
            )

        _cover_cache[cover_url] = resp.content
        return resp.content

    except Exception as e:
        print(f"[WARN] remote cover unavailable, will try local fallback: {cover_url} | {e}")
        _cover_cache[cover_url] = None
        return None


def _guess_image_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"

    return "image/jpeg"


def _extract_cover_from_mp3(path: Path) -> bytes | None:
    try:
        id3 = ID3(str(path))
        apics = id3.getall("APIC")

        if not apics:
            return None

        return apics[0].data

    except Exception:
        return None


def _extract_cover_from_m4a(path: Path) -> bytes | None:
    try:
        audio = MP4(str(path))
        covers = audio.get("covr")

        if not covers:
            return None

        return bytes(covers[0])

    except Exception:
        return None


def _extract_cover_from_file(path: Path) -> bytes | None:
    key = str(path)

    if key in _local_cover_cache:
        return _local_cover_cache[key]

    ext = path.suffix.lower()

    if ext == ".mp3":
        data = _extract_cover_from_mp3(path)
    elif ext in [".m4a", ".mp4"]:
        data = _extract_cover_from_m4a(path)
    else:
        data = None

    _local_cover_cache[key] = data
    return data


def _normalize_title_for_prefix(title: str) -> str:
    title = title or ""

    title = re.sub(r"\s+", " ", title).strip()
    title = title.replace("：", ":")
    title = title.replace("－", "-")
    title = title.replace("—", "-")

    return title


def _guess_series_prefix(title: str) -> str:
    """
    从标题中猜测系列前缀。

    例：
    苏联二战前干了些啥 第08集 北极熊没捞到啥便宜
    -> 苏联二战前干了些啥

    反攻欧陆 第03集 天上掉下个大肉馅
    -> 反攻欧陆

    二战番外篇 第01集 罪恶滔天
    -> 二战番外篇
    """
    title = _normalize_title_for_prefix(title)

    patterns = [
        r"^(.*?)[\s　]*第\s*[0-9一二三四五六七八九十百零〇]+\s*[集期回话讲章]",
        r"^(.*?)[\s　]*EP\s*\.?\s*\d+",
        r"^(.*?)[\s　]*E\s*\.?\s*\d+",
        r"^(.*?)[\s　]*No\.?\s*\d+",
        r"^(.*?)[\s　]*#\s*\d+",
        r"^(.*?)[\s　]*\d{1,4}\s*[:：]",
    ]

    for pattern in patterns:
        m = re.search(pattern, title, re.I)
        if not m:
            continue

        prefix = m.group(1).strip(" -_—－:：，,、")
        if len(prefix) >= 3:
            return prefix

    # fallback：取前 10 个字符，避免完全没有聚类能力
    return title[:10].strip(" -_—－:：，,、")


def _candidate_score(
    target_title: str, candidate_title: str, target_prefix: str
) -> int:
    target_title = _normalize_title_for_prefix(target_title)
    candidate_title = _normalize_title_for_prefix(candidate_title)

    score = 0

    if target_prefix and candidate_title.startswith(target_prefix):
        score += 100

    candidate_prefix = _guess_series_prefix(candidate_title)
    if target_prefix and candidate_prefix == target_prefix:
        score += 80

    # 简单共同前缀长度加权
    common = 0
    for a, b in zip(target_title, candidate_title):
        if a != b:
            break
        common += 1

    score += min(common, 30)

    # 同系列常见情况下，文件名越接近越可能是同一批
    if target_prefix and target_prefix in candidate_title:
        score += 20

    return score


def _find_reusable_cover(filename: str, title: str, album: str = "") -> bytes | None:
    """
    本地封面兜底：
    - 只在当前 podcast 目录里找；
    - 优先找同系列前缀；
    - 找到已有 embedded cover 的文件就复用。
    """
    target_path = Path(filename)
    folder = target_path.parent

    if not folder.exists():
        return None

    target_prefix = _guess_series_prefix(title)
    if not target_prefix or len(target_prefix) < 3:
        return None

    candidates: list[tuple[int, Path]] = []

    for path in folder.iterdir():
        if not path.is_file():
            continue

        if path == target_path:
            continue

        if path.suffix.lower() not in [".mp3", ".m4a", ".mp4"]:
            continue

        # aria2 半截文件或异常文件跳过
        aria2_control_file = path.with_name(path.name + ".aria2")
        if aria2_control_file.exists():
            continue

        candidate_title = path.stem
        score = _candidate_score(title, candidate_title, target_prefix)

        if score >= 100:
            candidates.append((score, path))

    if not candidates:
        print(f"[INFO] no local cover candidates for prefix: {target_prefix} -> {target_path.name}")
        return None

    # 分数高优先；同分时，离目标文件修改时间近的优先
    target_mtime = target_path.stat().st_mtime if target_path.exists() else 0

    candidates.sort(
        key=lambda item: (
            item[0],
            -abs((item[1].stat().st_mtime if item[1].exists() else 0) - target_mtime),
        ),
        reverse=True,
    )

    for score, path in candidates:
        data = _extract_cover_from_file(path)

        if data:
            print(f"[INFO] reused local cover from: {path.name} -> {target_path.name}")
            return data

    return None


def _find_any_folder_cover(filename: str) -> bytes | None:
    """
    最后一层兜底：
    在当前 podcast 目录里找任意一个已有 embedded cover 的音频文件。

    用途：
    - 远程封面 403
    - 同系列 prefix 没找到 cover
    - 但同 podcast 目录里其他节目已有封面
    """
    target_path = Path(filename)
    folder = target_path.parent

    if not folder.exists():
        return None

    candidates = []

    for path in folder.iterdir():
        if not path.is_file():
            continue

        if path == target_path:
            continue

        if path.suffix.lower() not in [".mp3", ".m4a", ".mp4"]:
            continue

        aria2_control_file = path.with_name(path.name + ".aria2")
        if aria2_control_file.exists():
            continue

        candidates.append(path)

    # 修改时间新的优先，通常更可能刚刚成功写过封面
    candidates.sort(
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )

    for path in candidates:
        data = _extract_cover_from_file(path)

        if data:
            print(f"[INFO] reused folder cover from: {path.name} -> {target_path.name}")
            return data

    return None


def _resolve_cover_data(
    *,
    filename: str,
    title: str,
    album: str,
    cover_url: str = "",
    session=None,
) -> bytes | None:
    """
    封面统一解析逻辑：
    1. 优先远程 cover_url
    2. 失败后尝试同目录同系列文件复用 embedded cover
    """
    target_name = Path(filename).name

    if cover_url:
        cover_data = _download_cover(cover_url, session=session)

        if cover_data:
            print(f"[INFO] cover resolved from remote: {target_name}")
            return cover_data

        print(f"[INFO] remote cover unavailable, try local fallback: {target_name}")

    else:
        print(f"[INFO] no remote cover_url, try local fallback: {target_name}")

    cover_data = _find_reusable_cover(
        filename=filename,
        title=title,
        album=album,
    )

    if cover_data:
        return cover_data

    cover_data = _find_any_folder_cover(filename)

    if cover_data:
        return cover_data


    print(f"[INFO] no reusable local cover found: {target_name}")
    return None


def tag_m4a(
    filename: str,
    title: str,
    artist: str,
    album: str,
    description: str = "",
    cover_url: str = "",
    session=None,
):
    """
    给 m4a/mp4 写 metadata。

    常用 MP4 atoms:
    \xa9nam = title
    \xa9ART = artist
    \xa9alb = album
    desc = description
    covr = cover
    """
    try:
        audio = MP4(filename)

        audio["\xa9nam"] = [title]
        audio["\xa9ART"] = [artist]
        audio["\xa9alb"] = [album]

        if description:
            audio["desc"] = [description]

        cover_data = _resolve_cover_data(
            filename=filename,
            title=title,
            album=album,
            cover_url=cover_url,
            session=session,
        )

        if cover_data:
            image_format = MP4Cover.FORMAT_JPEG

            if cover_data.startswith(b"\x89PNG\r\n\x1a\n"):
                image_format = MP4Cover.FORMAT_PNG

            audio["covr"] = [MP4Cover(cover_data, imageformat=image_format)]

        audio.save()
        print(f"[INFO] m4a metadata saved: {filename}")
        return True

    except Exception as e:
        print(f"[WARN] m4a tagging failed: {e}")
        return False


def tag_mp3(
    filename: str,
    title: str,
    artist: str,
    album: str,
    description: str = "",
    cover_url: str = "",
    session=None,
):
    """
    给 MP3 写 ID3 metadata。

    EasyID3:
    - title
    - artist
    - album
    - comment

    ID3:
    - APIC cover
    - COMM description/comment
    """
    try:
        try:
            audio = EasyID3(filename)
        except ID3NoHeaderError:
            audio = EasyID3()
            audio.save(filename)
            audio = EasyID3(filename)

        audio["title"] = title
        audio["artist"] = artist
        audio["album"] = album

        audio.save()

        # EasyID3 不处理封面，所以封面用 ID3 APIC 写
        id3 = ID3(filename)

        if description:
            id3.delall("COMM")
            id3.add(
                COMM(
                    encoding=3,
                    lang="eng",
                    desc="desc",
                    text=description,
                )
            )

        cover_data = _resolve_cover_data(
            filename=filename,
            title=title,
            album=album,
            cover_url=cover_url,
            session=session,
        )

        if cover_data:
            id3.delall("APIC")
            id3.add(
                APIC(
                    encoding=3,
                    mime=_guess_image_mime(cover_data),
                    type=3,
                    desc="Cover",
                    data=cover_data,
                )
            )

        id3.save(filename)

        print(f"[INFO] mp3 metadata saved: {filename}")
        return True

    except Exception as e:
        print(f"[WARN] mp3 tagging failed: {e}")
        return False
