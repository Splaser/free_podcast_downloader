# podcast_archiver/session_utils.py
from __future__ import annotations

from urllib.parse import urlparse
from pathlib import Path
import os
import sys

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


def _firefox_profiles_root() -> Path | None:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        return Path(appdata) / "Mozilla" / "Firefox" / "Profiles"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"

    return Path.home() / ".mozilla" / "firefox"


def _find_firefox_cookie_files() -> list[Path]:
    root = _firefox_profiles_root()
    if not root or not root.exists():
        return []

    cookie_files = []

    for profile_dir in root.iterdir():
        if not profile_dir.is_dir():
            continue

        cookie_file = profile_dir / "cookies.sqlite"
        if cookie_file.exists():
            cookie_files.append(cookie_file)

    return cookie_files


def _load_firefox_cookies_from_profiles(domains: list[str], required_cookie: str = "auth_token"):
    """
    Firefox 多 profile 兜底：
    自动扫描所有 profile，优先选择能读到 required_cookie 的 cookies.sqlite。
    """
    best = None
    best_score = -1

    cookie_files = _find_firefox_cookie_files()

    if not cookie_files:
        print("[WARN] no Firefox cookies.sqlite found in profiles")
        return requests.cookies.RequestsCookieJar()

    print(f"[INFO] scanning Firefox profiles for {required_cookie}: {len(cookie_files)} profile(s)")

    for cookie_file in cookie_files:
        merged = requests.cookies.RequestsCookieJar()

        for domain in domains:
            try:
                cj = browser_cookie3.firefox(
                    domain_name=domain,
                    cookie_file=str(cookie_file),
                )
                merged.update(cj)
            except Exception as e:
                print(f"[WARN] failed to read {cookie_file.parent.name} for {domain}: {e}")

        names = {c.name for c in merged}

        score = 0
        if required_cookie in names:
            score += 1000

        # cookie 数量多一点通常也更像真实登录 profile
        score += len(names)

        if score > best_score:
            best_score = score
            best = (cookie_file, merged, names)

    if not best:
        return requests.cookies.RequestsCookieJar()

    cookie_file, merged, names = best

    if required_cookie in names:
        print(f"[INFO] Firefox profile auto-selected: {cookie_file.parent.name}")
        print(f"[INFO] matched cookie_file: {cookie_file}")
    else:
        print("[WARN] no Firefox profile contains required cookie:", required_cookie)

    return merged


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
            print("[INFO] trying Firefox profile auto-detection...")

            fallback_cj = _load_firefox_cookies_from_profiles(
                domains,
                required_cookie="auth_token",
            )

            if _has_cookie_name(fallback_cj, "auth_token"):
                session.cookies.update(fallback_cj)
                print("[INFO] auth_token loaded via Firefox profile auto-detection")
            else:
                print("[WARN] Firefox profile auto-detection did not find auth_token")

        cookie_names = sorted({c.name for c in session.cookies})

        print(f"[INFO] {browser} cookies loaded for {domain}")
        _print_cookie_summary(session)
        print(
            "[INFO] cookie names:",
            ", ".join(cookie_names) if cookie_names else "(none)",
        )

        normalized = _normalize_domain(domain)

        if not cookie_names:
            print(
                "[WARN] no browser cookies loaded. Make sure the target site is logged in with this browser profile."
            )

        if "ifdian.net" in normalized or "afdian.com" in normalized:
            if "auth_token" not in cookie_names:
                print(
                    "[WARN] auth_token not found. Afdian paid/private resources may return empty data."
                )

            if "cf_clearance" not in cookie_names:
                print(
                    "[WARN] cf_clearance not found. If you get 403, open the page in browser first and pass Cloudflare."
                )

    return session
