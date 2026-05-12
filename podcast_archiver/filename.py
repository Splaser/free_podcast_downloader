# podcast_archiver/filename.py
import re


def sanitize_filename(name: str, max_len: int = 160) -> str:
    """
    清理 Windows / macOS / Linux 下常见非法文件名字符。
    """
    if not name:
        name = "untitled"

    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip(".")

    if len(name) > max_len:
        name = name[:max_len].rstrip()

    return name or "untitled"