# podcast_archiver/firefox_cookie_sqlite.py
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import time
from http.cookiejar import Cookie
from pathlib import Path

import requests


def firefox_profiles_root() -> Path | None:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        return Path(appdata) / "Mozilla" / "Firefox" / "Profiles"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"

    return Path.home() / ".mozilla" / "firefox"


def find_firefox_cookie_files() -> list[Path]:
    root = firefox_profiles_root()
    if not root or not root.exists():
        return []

    cookie_files: list[Path] = []

    for profile_dir in root.iterdir():
        if not profile_dir.is_dir():
            continue

        cookie_file = profile_dir / "cookies.sqlite"
        if cookie_file.exists():
            cookie_files.append(cookie_file)

    return cookie_files


def _normalize_expiry(expiry) -> int | None:
    if expiry is None:
        return None

    try:
        expiry = int(expiry)
    except Exception:
        return None

    # 秒级时间戳一般是 10 位；毫秒级可能是 13 位
    if expiry > 10_000_000_000:
        expiry = expiry // 1000

    return expiry


def _make_cookie(
    *,
    name: str,
    value: str,
    domain: str,
    path: str = "/",
    expires: int | None = None,
    secure: bool = False,
) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=bool(domain),
        domain_initial_dot=domain.startswith("."),
        path=path or "/",
        path_specified=True,
        secure=secure,
        expires=expires,
        discard=False if expires else True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


def _host_variants(hosts: list[str]) -> list[str]:
    result: list[str] = []

    for host in hosts:
        host = (host or "").strip().lower()
        if not host:
            continue

        host = host.removeprefix("https://").removeprefix("http://").strip("/")

        result.append(host)

        if host.startswith("www."):
            root = host[4:]
            result.append(root)
            result.append("." + root)
        elif not host.startswith("."):
            result.append("." + host)
            result.append("www." + host)

    return list(dict.fromkeys(result))


def load_firefox_sqlite_cookies(
    cookie_file: str | Path,
    *,
    hosts: list[str],
    skip_expired: bool = True,
) -> requests.cookies.RequestsCookieJar:
    """
    从指定 Firefox cookies.sqlite 中读取指定 hosts 的 cookies。

    用途：
    - browser_cookie3 自动 profile 选择失败时兜底；
    - 处理 host-only cookie，例如 ifdian.net 的 auth_token。
    """
    cookie_file = Path(cookie_file)
    jar = requests.cookies.RequestsCookieJar()

    if not cookie_file.exists():
        return jar

    hosts = _host_variants(hosts)

    if not hosts:
        return jar

    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
        tmp_path = Path(tmp.name)

    try:
        # Firefox 运行中 cookies.sqlite 可能被锁，复制后读
        shutil.copy2(cookie_file, tmp_path)

        conn = sqlite3.connect(tmp_path)
        cur = conn.cursor()

        placeholders = ",".join("?" for _ in hosts)

        cur.execute(
            f"""
            SELECT host, name, value, path, expiry, isSecure
            FROM moz_cookies
            WHERE host IN ({placeholders})
            """,
            hosts,
        )

        rows = cur.fetchall()
        conn.close()

        now = int(time.time())

        for host, name, value, path, expiry, is_secure in rows:
            expires = _normalize_expiry(expiry)

            if skip_expired and expires and expires < now:
                continue

            jar.set_cookie(
                _make_cookie(
                    name=name,
                    value=value,
                    domain=host,
                    path=path or "/",
                    expires=expires,
                    secure=bool(is_secure),
                )
            )

    except Exception as e:
        print(f"[WARN] sqlite cookie load failed: {cookie_file} | {e}")

    finally:
        tmp_path.unlink(missing_ok=True)

    return jar


def find_best_firefox_cookiejar(
    *,
    hosts: list[str],
    required_cookie: str | None = None,
    debug: bool = False,
) -> tuple[Path | None, requests.cookies.RequestsCookieJar]:
    """
    扫描所有 Firefox profiles，返回最匹配的 cookie jar。

    scoring:
    - 包含 required_cookie：+1000
    - cookie 数量：+len(names)
    """
    cookie_files = find_firefox_cookie_files()

    if not cookie_files:
        print("[WARN] no Firefox cookies.sqlite found in profiles")
        return None, requests.cookies.RequestsCookieJar()

    if required_cookie:
        print(
            f"[INFO] scanning Firefox profiles via sqlite for {required_cookie}: "
            f"{len(cookie_files)} profile(s)"
        )
    else:
        print(
            f"[INFO] scanning Firefox profiles via sqlite: {len(cookie_files)} profile(s)"
        )

    best_file: Path | None = None
    best_jar = requests.cookies.RequestsCookieJar()
    best_score = -1

    for cookie_file in cookie_files:
        jar = load_firefox_sqlite_cookies(cookie_file, hosts=hosts)
        names = {c.name for c in jar}

        score = len(names)

        if required_cookie and required_cookie in names:
            score += 1000

        if debug:
            print(
                f"[DEBUG] profile={cookie_file.parent.name}, "
                f"cookies={sorted(names) if names else []}, "
                f"score={score}"
            )

        if score > best_score:
            best_score = score
            best_file = cookie_file
            best_jar = jar

    names = {c.name for c in best_jar}

    if required_cookie:
        if required_cookie in names and best_file:
            print(f"[INFO] Firefox profile auto-selected: {best_file.parent.name}")
            print(f"[INFO] matched cookie_file: {best_file}")
        else:
            print(
                f"[WARN] no Firefox profile contains required cookie: {required_cookie}"
            )

    return best_file, best_jar
