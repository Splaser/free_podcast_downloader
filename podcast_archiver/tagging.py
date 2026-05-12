# podcast_archiver/tagging.py
import requests
from mutagen.mp4 import MP4, MP4Cover
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, COMM, ID3NoHeaderError


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

def _download_cover(cover_url: str, session=None) -> bytes | None:
    if not cover_url:
        return None

    s = session or requests.Session()

    try:
        resp = s.get(cover_url, timeout=30)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"[WARN] cover download failed: {e}")
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

        cover_data = _download_cover(cover_url, session=session)

        if cover_data:
            # Listen Notes 封面大多是 jpg
            audio["covr"] = [
                MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)
            ]

        audio.save()
        print("[INFO] m4a metadata saved")
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

        cover_data = _download_cover(cover_url, session=session)

        if cover_data:
            id3.delall("APIC")
            id3.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=cover_data,
                )
            )

        id3.save(filename)

        print("[INFO] mp3 metadata saved")
        return True

    except Exception as e:
        print(f"[WARN] mp3 tagging failed: {e}")
        return False
