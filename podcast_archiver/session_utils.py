# podcast_archiver/session_utils.py
import browser_cookie3
import requests


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
    "Gecko/20100101 Firefox/150.0"
)


def _load_browser_cookies(browser: str, domains: list[str]):
    merged = requests.cookies.RequestsCookieJar()

    for domain in domains:
        try:
            if browser.lower() == "firefox":
                cj = browser_cookie3.firefox(domain_name=domain)
            elif browser.lower() == "chrome":
                cj = browser_cookie3.chrome(domain_name=domain)
            else:
                raise ValueError("Unsupported browser")

            merged.update(cj)
        except Exception as e:
            print(f"[WARN] failed to load cookies for {domain}: {e}")

    return merged


def create_session(browser: str | None = None, domain: str = "listennotes.com"):
    session = requests.Session()

    session.headers.update({
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
    })

    if browser:
        domains = [
            domain,
            f".{domain}",
            f"www.{domain}",
        ]

        cj = _load_browser_cookies(browser, domains)
        session.cookies.update(cj)

        print(f"[INFO] {browser} cookies loaded for {domain}")

        cookie_names = sorted({c.name for c in session.cookies})
        print("[INFO] cookie names:", ", ".join(cookie_names) if cookie_names else "(none)")

        if "cf_clearance" not in cookie_names:
            print("[WARN] cf_clearance not found. If you get 403, open the page in browser first and pass Cloudflare.")

    return session