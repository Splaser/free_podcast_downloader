# probe.py
import argparse
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from podcast_archiver.session_utils import create_session


AUDIO_EXT_RE = re.compile(
    r"https?://[^\"'\s<>]+?\.(?:mp3|m4a|aac|ogg|wav)(?:\?[^\"'\s<>]*)?",
    re.I,
)

URL_RE = re.compile(
    r"https?://[^\"'\s<>\\]+",
    re.I,
)


def is_interesting_url(url: str) -> bool:
    lowered = url.lower()

    keywords = [
        "audio",
        "mp3",
        "m4a",
        "media",
        "download",
        "episode",
        "rss",
        "feed",
        "json",
        "api",
        "listen-api",
        "cdn",
    ]

    return any(k in lowered for k in keywords)


def recursive_find_urls(obj, path=""):
    """
    递归扫描 JSON 中的 URL。
    返回 [(path, url)]。
    """
    found = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}" if path else key
            found.extend(recursive_find_urls(value, child_path))

    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            child_path = f"{path}[{index}]"
            found.extend(recursive_find_urls(item, child_path))

    elif isinstance(obj, str):
        if obj.startswith("http"):
            found.append((path, obj))
        else:
            for m in URL_RE.finditer(obj):
                found.append((path, m.group(0)))

    return found


def try_load_json_from_url(session, url: str):
    try:
        resp = session.get(
            url,
            timeout=20,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": url,
            },
        )
        print(f"[JSON] GET {url}")
        print(f"       status={resp.status_code} content-type={resp.headers.get('content-type')}")

        if resp.status_code != 200:
            return None

        text = resp.text.strip()

        if not text:
            return None

        if "json" not in resp.headers.get("content-type", "").lower() and not text.startswith("{"):
            print("       not json-like, skipped")
            return None

        return resp.json()

    except Exception as e:
        print(f"[WARN] JSON request failed: {url}")
        print(f"       {e}")
        return None


def extract_json_scripts(soup: BeautifulSoup):
    """
    提取页面内 application/json / ld+json script。
    """
    results = []

    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        text = script.string or script.get_text() or ""

        if not text.strip():
            continue

        if "json" not in script_type:
            continue

        try:
            data = json.loads(text.strip())
            results.append((script_type, data))
        except Exception:
            continue

    return results


def probe_page(url: str, browser: str | None = None):
    session = create_session(browser=browser, domain="listennotes.com")

    print(f"[INFO] Fetching page: {url}")
    resp = session.get(url, timeout=30)
    print(f"[INFO] status={resp.status_code}")
    print(f"[INFO] content-type={resp.headers.get('content-type')}")

    resp.raise_for_status()

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    print("\n========== Page title ==========")
    print(soup.title.get_text(strip=True) if soup.title else "(no title)")

    print("\n========== Interesting <a href> ==========")
    anchors = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = urljoin(url, a["href"])

        if (
            is_interesting_url(href)
            or "api" in text.lower()
            or "json" in text.lower()
            or "rss" == text.strip().lower()
            or "download" in text.lower()
            or "下载" in text
        ):
            anchors.append((text, href))

    # 去重
    seen = set()
    for text, href in anchors:
        key = (text, href)
        if key in seen:
            continue
        seen.add(key)
        print(f"[A] text={text!r}")
        print(f"    href={href}")

    print("\n========== Direct audio URLs in HTML ==========")
    audio_urls = sorted(set(m.group(0) for m in AUDIO_EXT_RE.finditer(html)))

    if not audio_urls:
        print("(no direct .mp3/.m4a/.aac/.ogg/.wav URL found)")
    else:
        for u in audio_urls:
            print(u)

    print("\n========== Interesting raw URLs in HTML ==========")
    raw_urls = sorted(set(m.group(0) for m in URL_RE.finditer(html)))
    interesting_raw_urls = [u for u in raw_urls if is_interesting_url(u)]

    if not interesting_raw_urls:
        print("(no interesting raw URL found)")
    else:
        for u in interesting_raw_urls[:100]:
            print(u)

    print("\n========== JSON script probing ==========")
    json_scripts = extract_json_scripts(soup)

    if not json_scripts:
        print("(no JSON script found)")
    else:
        for script_type, data in json_scripts:
            print(f"\n[SCRIPT JSON] type={script_type}")
            urls = recursive_find_urls(data)

            interesting = [(p, u) for p, u in urls if is_interesting_url(u)]

            if not interesting:
                print("  no interesting URL")
            else:
                for path, u in interesting[:50]:
                    print(f"  {path}: {u}")

    print("\n========== Fetch API JSON links ==========")
    json_links = []

    for text, href in anchors:
        if "json" in text.lower() or "api" in text.lower() or "json" in href.lower() or "api" in href.lower():
            json_links.append(href)

    json_links = list(dict.fromkeys(json_links))

    if not json_links:
        print("(no API/JSON link found from anchors)")
    else:
        for json_url in json_links:
            data = try_load_json_from_url(session, json_url)
            if data is None:
                continue

            print(f"\n[JSON URLS] {json_url}")
            urls = recursive_find_urls(data)
            interesting = [(p, u) for p, u in urls if is_interesting_url(u)]

            if not interesting:
                print("  no interesting URL")
            else:
                for path, u in interesting[:100]:
                    print(f"  {path}: {u}")

            # 保存一份，方便手动看结构
            parsed = urlparse(json_url)
            safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", parsed.path.strip("/") or "api_json")
            out = f"debug_{safe_name}.json"

            with open(out, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"  saved: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe Listen Notes episode page")
    parser.add_argument("--url", required=True)
    parser.add_argument("--browser", choices=["firefox", "chrome"], default=None)

    args = parser.parse_args()

    probe_page(args.url, browser=args.browser)