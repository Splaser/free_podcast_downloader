# probe_wechat.py
import argparse
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


URL_RE = re.compile(r"https?://[^\"'\s<>\\]+", re.I)

MEDIAID_RE = re.compile(
    r"(?:mediaid|voice_encode_fileid|voiceid|fileid)[\"'\s:=]+([A-Za-z0-9_\-]+)",
    re.I,
)

GETVOICE_RE = re.compile(
    r"https?://res\.wx\.qq\.com/voice/getvoice\?mediaid=[A-Za-z0-9_\-]+",
    re.I,
)

INTERESTING_KEYS = [
    "voice",
    "audio",
    "mp3",
    "m4a",
    "getvoice",
    "mediaid",
    "fileid",
    "readtemplate",
    "cgi-bin",
    "res.wx.qq.com",
    "mp.weixin.qq.com",
]


def is_interesting_url(url: str) -> bool:
    lowered = url.lower()
    return any(k in lowered for k in INTERESTING_KEYS)


def fetch(url: str, browser_like: bool = True) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)

    print(f"[INFO] GET {url}")
    print(f"[INFO] status={resp.status_code}")
    print(f"[INFO] final_url={resp.url}")
    print(f"[INFO] content-type={resp.headers.get('content-type')}")

    preview = resp.text[:300].replace("\n", "\\n")
    print(f"[INFO] preview={preview}")

    resp.raise_for_status()
    return resp.text


def probe_wechat_article(url: str):
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    print("\n========== Page title ==========")
    print(soup.title.get_text(strip=True) if soup.title else "(no title)")

    print("\n========== audio/source tags ==========")
    found = False
    for tag in soup.find_all(["audio", "source"]):
        src = tag.get("src")
        if src:
            found = True
            print(f"[{tag.name}] src={urljoin(url, src)}")

    if not found:
        print("(no audio/source src found)")

    print("\n========== getvoice URLs ==========")
    getvoice_urls = sorted(set(GETVOICE_RE.findall(html)))

    if getvoice_urls:
        for u in getvoice_urls:
            print(u)
    else:
        print("(no direct getvoice URL found)")

    print("\n========== possible media ids ==========")
    media_ids = sorted(set(MEDIAID_RE.findall(html)))

    if media_ids:
        for mid in media_ids[:100]:
            print(mid)
            print(f"  candidate: https://res.wx.qq.com/voice/getvoice?mediaid={mid}")
    else:
        print("(no mediaid-like value found)")

    print("\n========== interesting raw URLs ==========")
    raw_urls = sorted(set(URL_RE.findall(html)))
    interesting = [u for u in raw_urls if is_interesting_url(u)]

    if interesting:
        for u in interesting[:200]:
            print(u)
    else:
        print("(no interesting raw URL found)")

    debug_file = "debug_wechat_article.html"
    with open(debug_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n[INFO] saved html: {debug_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe WeChat article audio")
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    probe_wechat_article(args.url)