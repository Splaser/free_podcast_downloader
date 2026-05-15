# podcast_archiver/wechat.py
from __future__ import annotations

import html
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup


WECHAT_GETVOICE_BASE = "https://res.wx.qq.com/voice/getvoice"


@dataclass
class WechatAudio:
    title: str
    account: str
    mediaid: str
    audio_url: str
    source_url: str
    ext: str = ".mp3"


def _clean_text(text: str) -> str:
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_title(soup: BeautifulSoup, page_html: str) -> str:
    # 常见公众号文章标题
    title_tag = soup.find(id="activity-name")
    if title_tag:
        title = _clean_text(title_tag.get_text(" ", strip=True))
        if title:
            return title

    # meta og:title
    meta = soup.find("meta", attrs={"property": "og:title"})
    if meta and meta.get("content"):
        return _clean_text(meta["content"])

    # JS 变量 fallback
    patterns = [
        r'var\s+msg_title\s*=\s*"([^"]+)"',
        r"var\s+msg_title\s*=\s*'([^']+)'",
    ]

    for pattern in patterns:
        m = re.search(pattern, page_html)
        if m:
            return _clean_text(m.group(1))

    return "wechat_audio"


def _extract_account(soup: BeautifulSoup, page_html: str) -> str:
    # 常见公众号名
    account_tag = soup.find(id="js_name")
    if account_tag:
        account = _clean_text(account_tag.get_text(" ", strip=True))
        if account:
            return account

    # JS 变量 fallback
    patterns = [
        r'var\s+nickname\s*=\s*"([^"]+)"',
        r"var\s+nickname\s*=\s*'([^']+)'",
    ]

    for pattern in patterns:
        m = re.search(pattern, page_html)
        if m:
            return _clean_text(m.group(1))

    return "WeChat"

def _extract_mediaid_candidates(page_html: str) -> list[str]:
    """
    从微信公众号文章 HTML 里提取可能的语音 mediaid。

    实测可用形态：
    MzIxMTMzNTc5OF8yMjQ3NDk1MjAw

    关键点：
    - mediaid 通常是 base64-ish + 下划线；
    - 不应该包含 /，否则会误匹配 JS/CSS 路径；
    - 优先保留以 Mz 开头的公众号语音 mediaid。
    """
    candidates: list[str] = []

    explicit_patterns = [
        r'data-mid=["\']([^"\']+)["\']',
        r'data-mediaid=["\']([^"\']+)["\']',
        r'mediaid\s*[:=]\s*["\']([^"\']+)["\']',
        r'voiceid\s*[:=]\s*["\']([^"\']+)["\']',
        r'voice_encode_fileid\s*[:=]\s*["\']([^"\']+)["\']',
    ]

    for pattern in explicit_patterns:
        for m in re.finditer(pattern, page_html, re.I):
            candidates.append(m.group(1))

    # 严格匹配公众号语音 mediaid：
    # 不允许 /，避免误匹配 com/mmbizappmsg/... 这类路径
    strict_patterns = [
        r"\bMz[A-Za-z0-9=]{8,}_[A-Za-z0-9=]{8,}\b",
        r"\b[A-Za-z0-9=]{16,}_[A-Za-z0-9=]{8,}\b",
    ]

    for pattern in strict_patterns:
        for m in re.finditer(pattern, page_html):
            candidates.append(m.group(0))

    bad_values = {
        "decodeURIComponent",
        "mpaudio",
        "profile",
    }

    result: list[str] = []
    seen = set()

    for item in candidates:
        item = html.unescape(item).strip()

        if not item or item in bad_values:
            continue

        # 排除路径、URL、JS 资源名
        if "/" in item or "\\" in item:
            continue

        if "." in item:
            continue

        if item.startswith("com"):
            continue

        if "assets" in item.lower():
            continue

        # 太短的一般不是目标 mediaid
        if len(item) < 20:
            continue

        if item not in seen:
            seen.add(item)
            result.append(item)

    # 优先测试 Mz 开头的候选
    result.sort(key=lambda x: (not x.startswith("Mz"), x))

    return result

def build_getvoice_url(mediaid: str) -> str:
    return f"{WECHAT_GETVOICE_BASE}?mediaid={mediaid}"


def probe_getvoice(mediaid: str, session=None) -> tuple[bool, str, str]:
    """
    测试 mediaid 是否能返回音频。
    返回: (ok, content_type, audio_url)
    """
    s = session or requests.Session()
    audio_url = build_getvoice_url(mediaid)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "audio/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Referer": "https://mp.weixin.qq.com/",
    }

    try:
        resp = s.get(audio_url, headers=headers, timeout=30, stream=True)
        content_type = resp.headers.get("content-type") or ""

        ok = (
            resp.status_code == 200
            and (
                "audio" in content_type.lower()
                or "octet-stream" in content_type.lower()
            )
        )

        # 不把整段音频读完，只关闭连接
        resp.close()

        return ok, content_type, audio_url

    except Exception:
        return False, "", audio_url


def parse_wechat_article(url: str, session=None) -> WechatAudio:
    """
    解析微信公众号文章，提取可播放语音 mediaid。
    """
    s = session or requests.Session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
    }

    resp = s.get(url, headers=headers, timeout=30, allow_redirects=True)
    print(f"[INFO] WeChat GET {url}")
    print(f"[INFO] status={resp.status_code}")
    print(f"[INFO] final_url={resp.url}")
    print(f"[INFO] content-type={resp.headers.get('content-type')}")

    resp.raise_for_status()

    page_html = resp.text
    soup = BeautifulSoup(page_html, "html.parser")

    title = _extract_title(soup, page_html)
    account = _extract_account(soup, page_html)

    mediaids = _extract_mediaid_candidates(page_html)

    if not mediaids:
        raise RuntimeError("No WeChat voice mediaid found")

    print(f"[INFO] found mediaid candidates: {len(mediaids)}")

    for mediaid in mediaids:
        ok, content_type, audio_url = probe_getvoice(mediaid, session=s)

        print(f"[INFO] probe mediaid={mediaid} ok={ok} content-type={content_type}")

        if ok:
            ext = ".mp3"
            ct = content_type.lower()

            if "mp4" in ct or "m4a" in ct:
                ext = ".m4a"
            elif "amr" in ct:
                ext = ".amr"
            elif "mp3" in ct or "mpeg" in ct:
                ext = ".mp3"

            return WechatAudio(
                title=title,
                account=account,
                mediaid=mediaid,
                audio_url=audio_url,
                source_url=url,
                ext=ext,
            )

    raise RuntimeError("Found mediaid candidates, but none returned audio")