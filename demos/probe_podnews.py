# probe_podnews.py
import argparse
import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


URL_RE = re.compile(r"https?://[^\"'\s<>\\]+", re.I)

INTERESTING_KEYS = [
    "rss",
    "feed",
    "xml",
    "mp3",
    "m4a",
    "audio",
    "enclosure",
    "wechat",
    "weixin",
    "mp.weixin.qq.com",
    "podcast",
    "episodes",
    "json",
    "api",
]


def is_interesting_url(url: str) -> bool:
    lowered = url.lower()
    return any(k in lowered for k in INTERESTING_KEYS)


def recursive_find_urls(obj, path=""):
    found = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else k
            found.extend(recursive_find_urls(v, child_path))

    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            child_path = f"{path}[{i}]"
            found.extend(recursive_find_urls(item, child_path))

    elif isinstance(obj, str):
        if obj.startswith("http"):
            found.append((path, obj))
        else:
            for m in URL_RE.finditer(obj):
                found.append((path, m.group(0)))

    return found


def fetch(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
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


def probe_podnews_page(url: str):
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    print("\n========== Page title ==========")
    print(soup.title.get_text(strip=True) if soup.title else "(no title)")

    print("\n========== Interesting <a href> ==========")
    seen = set()

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = urljoin(url, a["href"])

        if is_interesting_url(href) or is_interesting_url(text):
            key = (text, href)
            if key in seen:
                continue
            seen.add(key)

            print(f"[A] text={text!r}")
            print(f"    href={href}")

    print("\n========== Interesting <audio>/<source> ==========")
    found_audio = False

    for tag in soup.find_all(["audio", "source"]):
        src = tag.get("src")
        if src:
            found_audio = True
            print(f"[{tag.name}] src={urljoin(url, src)}")

    if not found_audio:
        print("(no audio/source src found in server HTML)")

    print("\n========== Script src ==========")
    for script in soup.find_all("script", src=True):
        src = urljoin(url, script["src"])
        print(src)

    print("\n========== Interesting raw URLs in HTML ==========")
    raw_urls = sorted(set(URL_RE.findall(html)))
    interesting = [u for u in raw_urls if is_interesting_url(u)]

    if not interesting:
        print("(no interesting raw URL found)")
    else:
        for u in interesting[:200]:
            print(u)

    print("\n========== Possible RSS_URL values ==========")

    patterns = [
        r"RSS_URL\s*=\s*['\"]([^'\"]+)['\"]",
        r"rss_url\s*=\s*['\"]([^'\"]+)['\"]",
        r"feed_url\s*=\s*['\"]([^'\"]+)['\"]",
        r"https://rss\.shawnxli\.com/[a-zA-Z0-9._/-]+",
    ]

    found = set()

    for pattern in patterns:
        for m in re.finditer(pattern, html):
            value = m.group(1) if m.groups() else m.group(0)
            found.add(value)

    if not found:
        print("(no RSS_URL found)")
    else:
        for value in sorted(found):
            print(value)

    print("\n========== JSON script probing ==========")
    found_json = False

    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        text = script.string or script.get_text() or ""

        if not text.strip():
            continue

        if "json" not in script_type:
            continue

        try:
            data = json.loads(text.strip())
        except Exception:
            continue

        found_json = True
        print(f"[SCRIPT JSON] type={script_type}")

        urls = recursive_find_urls(data)
        interesting_urls = [(p, u) for p, u in urls if is_interesting_url(u)]

        if not interesting_urls:
            print("  no interesting URL")
        else:
            for path, u in interesting_urls[:100]:
                print(f"  {path}: {u}")

    if not found_json:
        print("(no JSON script parsed)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe Podnews episode page")
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    probe_podnews_page(args.url)