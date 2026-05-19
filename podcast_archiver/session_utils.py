# podcast_archiver/session_utils.py
from __future__ import annotations

from urllib.parse import urlparse

import browser_cookie3
import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
    "Gecko/20100101 Firefox/150.0"
)


AFDIAN_COOKIE_DOMAINS = [
    "ifdian.net",
    ".ifdian.net",
    "www.ifdian.net",
    "afdian.com",
    ".afdian.com",
    "www.afdian.com",
]


def _print_cookie_summary(session_obj: requests.Session) -> None:
    cookies = sorted(
        [
            (c.name, c.domain, c.path)
            for c in session_obj.cookies
        ],
        key=lambda x: (x[1], x[0], x[2]),
    )

    if not cookies:
        print("[INFO] cookie names: (none)")
        return

    print("[INFO] cookies loaded:")
    for name, domain, path in cookies:
        print(f"  - {name} | domain={domain} | path={path}")


def _normalize_domain(domain: str) -> str:
    """
    允许传入:
    - ifdian.net
    - https://ifdian.net/album/xxx
    - www.ifdian.net
    最终统一成 hostname。
    """
    domain = (domain or "").strip()

    if not domain:
        return ""

    if "://" in domain:
        parsed = urlparse(domain)
        return parsed.netloc.lower()

    return domain.lower().strip("/")


def _domain_variants(domain: str) -> list[str]:
    domain = _normalize_domain(domain)

    if not domain:
        return []

    # 去掉开头的 www. 和 .，生成根域
    root = domain
    if root.startswith("www."):
        root = root[4:]
    if root.startswith("."):
        root = root[1:]

    variants = [
        root,
        f".{root}",
        f"www.{root}",
    ]

    return list(dict.fromkeys(variants))


def _cookie_domains_for(domain: str) -> list[str]:
    """
    特殊处理爱发电：
    浏览器里可能登录的是 ifdian.net，也可能 cookie 挂在 afdian.com。
    """
    normalized = _normalize_domain(domain)

    if "ifdian.net" in normalized or "afdian.com" in normalized:
        return AFDIAN_COOKIE_DOMAINS

    return _domain_variants(normalized)


def _load_browser_cookies(browser: str, domains: list[str]):
    merged = requests.cookies.RequestsCookieJar()
    browser = (browser or "").lower()

    for domain in domains:
        try:
            if browser == "firefox":
                cj = browser_cookie3.firefox(domain_name=domain)
            elif browser == "chrome":
                cj = browser_cookie3.chrome(domain_name=domain)
            else:
                raise ValueError(f"Unsupported browser: {browser}")

            count = len(list(cj))
            if count:
                print(f"[INFO] loaded {count} cookies for {domain}")

            merged.update(cj)

        except Exception as e:
            print(f"[WARN] failed to load cookies for {domain}: {e}")

    return merged


def create_session(browser: str | None = None, domain: str = "listennotes.com"):
    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": DEFAULT_UA,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "DNT": "1",
        }
    )

    if browser:
        domains = _cookie_domains_for(domain)

        print(f"[INFO] loading {browser} cookies for domains: {', '.join(domains)}")

        cj = _load_browser_cookies(browser, domains)
        session.cookies.update(cj)

        cookie_names = sorted({c.name for c in session.cookies})

        print(f"[INFO] {browser} cookies loaded for {domain}")
        _print_cookie_summary(session)

        if not cookie_names:
            print("[WARN] no browser cookies loaded. Make sure the target site is logged in with this browser profile.")
    
        print(
            "[INFO] cookie names:",
            ", ".join(cookie_names) if cookie_names else "(none)",
        )

        if not cookie_names:
            print(
                "[WARN] no browser cookies loaded. Make sure the target site is logged in with this browser profile."
            )

        if "ifdian.net" in _normalize_domain(
            domain
        ) or "afdian.com" in _normalize_domain(domain):
            if "auth_token" not in cookie_names:
                print(
                    "[WARN] auth_token not found. Afdian paid/private resources may return empty data."
                )

            if "cf_clearance" not in cookie_names:
                print(
                    "[WARN] cf_clearance not found. If you get 403, open the page in browser first and pass Cloudflare."
                )

    return session
