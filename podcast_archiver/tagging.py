# podcast_archiver/tagging.py
import requests
from mutagen.mp4 import MP4, MP4Cover


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