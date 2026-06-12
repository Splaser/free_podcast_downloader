# podcast_archiver/session_utils.py
from __future__ import annotations

from urllib.parse import urlparse
from pathlib import Path
from .firefox_cookie_sqlite import find_best_firefox_cookiejar
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


def _is_afdian_domain(domain: str) -> bool:
    normalized = _normalize_domain(domain)
    return "ifdian.net" in normalized or "afdian.com" in normalized


def _has_cookie_name(cookiejar, name: str) -> bool:
    return any(c.name == name for c in cookiejar)


def _normalize_domain(domain: str) -> str:
    domain = (domain or "").strip()

    if not domain:
        return ""

    if "://" in domain:
        return urlparse(domain).netloc.lower()

    return domain.lower().strip("/")


def _domain_variants(domain: str) -> list[str]:
    domain = _normalize_domain(domain)

    if not domain:
        return []

    root = domain
    if root.startswith("www."):
        root = root[4:]
    if root.startswith("."):
        root = root[1:]

    return list(
        dict.fromkeys(
            [
                root,
                f".{root}",
                f"www.{root}",
            ]
        )
    )


def _cookie_domains_for(domain: str) -> list[str]:
    normalized = _normalize_domain(domain)

    if "ifdian.net" in normalized or "afdian.com" in normalized:
        return AFDIAN_COOKIE_DOMAINS

    return _domain_variants(normalized)


def _load_browser_cookies(
    browser: str,
    domains: list[str],
    *,
    cookie_file: str | None = None,
):
    merged = requests.cookies.RequestsCookieJar()
    browser = (browser or "").lower()

    for domain in domains:
        try:
            kwargs = {"domain_name": domain}

            # Firefox 多 profile 时，用 cookie_file 强制指定 cookies.sqlite
            if cookie_file:
                kwargs["cookie_file"] = cookie_file

            if browser == "firefox":
                cj = browser_cookie3.firefox(**kwargs)
            elif browser == "chrome":
                # Chrome 一般不建议手动 cookie_file，这里保守不传
                if cookie_file:
                    print(
                        "[WARN] cookie_file is mainly supported for firefox in this workflow"
                    )
                cj = browser_cookie3.chrome(domain_name=domain)
            else:
                raise ValueError(f"Unsupported browser: {browser}")

            cookies = list(cj)
            if cookies:
                print(f"[INFO] loaded {len(cookies)} cookies for {domain}")

            merged.update(cj)

        except Exception as e:
            print(f"[WARN] failed to load cookies for {domain}: {e}")

    return merged


def _print_cookie_summary(session_obj: requests.Session) -> None:
    cookies = sorted(
        [(c.name, c.domain, c.path) for c in session_obj.cookies],
        key=lambda x: (x[1], x[0], x[2]),
    )

    if not cookies:
        print("[INFO] cookie names: (none)")
        return

    print("[INFO] cookies loaded:")
    for name, domain, path in cookies:
        print(f"  - {name} | domain={domain} | path={path}")


def create_session(
    browser: str | None = None,
    domain: str = "listennotes.com",
    *,
    cookie_file: str | None = None,
):
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

        if cookie_file:
            cookie_path = Path(cookie_file)
            print(f"[INFO] using explicit cookie_file: {cookie_path}")

            if not cookie_path.exists():
                print(f"[WARN] cookie_file not found: {cookie_path}")
                cookie_file = None

        cj = _load_browser_cookies(
            browser,
            domains,
            cookie_file=cookie_file,
        )
        session.cookies.update(cj)

        # Afdian 特殊兜底：
        # browser_cookie3 默认 profile 没拿到 auth_token 时，自动扫描 Firefox profiles。
        if (
            browser.lower() == "firefox"
            and not cookie_file
            and _is_afdian_domain(domain)
            and not _has_cookie_name(session.cookies, "auth_token")
        ):
            print("[WARN] auth_token not found from default Firefox cookie loading")
            print("[INFO] trying Firefox sqlite profile auto-detection...")

            _, fallback_cj = find_best_firefox_cookiejar(
                hosts=[
                    "ifdian.net",
                    "www.ifdian.net",
                    "afdian.com",
                    "www.afdian.com",
                ],
                required_cookie="auth_token",
                debug=True,
            )

            if _has_cookie_name(fallback_cj, "auth_token"):
                session.cookies.update(fallback_cj)
                print("[INFO] auth_token loaded via Firefox sqlite profile auto-detection")
            else:
                print("[WARN] Firefox sqlite profile auto-detection did not find auth_token")

        cookie_names = sorted({c.name for c in session.cookies})

        print(f"[INFO] {browser} cookies loaded for {domain}")
        _print_cookie_summary(session)
        print(
            "[INFO] cookie names:",
            ", ".join(cookie_names) if cookie_names else "(none)",
        )

        if not cookie_names:
            print(
                "[WARN] no browser cookies loaded. Make sure the target site is logged in with this browser profile."
            )

        if _is_afdian_domain(domain):
            if "auth_token" not in cookie_names:
                print(
                    "[WARN] auth_token not found. Afdian paid/private resources may return empty data."
                )

            if "cf_clearance" not in cookie_names:
                print(
                    "[INFO] cf_clearance not found; okay unless Afdian returns 403."
                )

    return session
