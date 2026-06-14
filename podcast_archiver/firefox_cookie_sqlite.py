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


def _copy_sqlite_snapshot(
    cookie_file: Path,
) -> tuple[tempfile.TemporaryDirectory, Path]:
    """
    复制 SQLite 主库及 WAL/SHM，获得尽量一致的临时快照。
    """
    temp_dir = tempfile.TemporaryDirectory()

    try:
        temp_root = Path(temp_dir.name)
        target_db = temp_root / cookie_file.name

        shutil.copy2(cookie_file, target_db)

        wal_file = cookie_file.with_name(cookie_file.name + "-wal")
        if wal_file.exists():
            shutil.copy2(
                wal_file,
                temp_root / wal_file.name,
            )

        shm_file = cookie_file.with_name(cookie_file.name + "-shm")
        if shm_file.exists():
            try:
                shutil.copy2(
                    shm_file,
                    temp_root / shm_file.name,
                )
            except OSError:
                # SHM 是辅助索引文件，SQLite通常可以重建。
                pass

        return temp_dir, target_db

    except Exception:
        temp_dir.cleanup()
        raise


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

    同时复制 WAL/SHM，尽量读取 Firefox 尚未 checkpoint
    到主数据库的最新 Cookie。
    """
    cookie_file = Path(cookie_file)
    jar = requests.cookies.RequestsCookieJar()

    if not cookie_file.exists():
        return jar

    hosts = _host_variants(hosts)

    if not hosts:
        return jar

    temp_dir = None

    try:
        temp_dir, tmp_path = _copy_sqlite_snapshot(cookie_file)

        placeholders = ",".join("?" for _ in hosts)

        # 临时副本可写且用完即删，不强制 mode=ro，
        # 避免 SQLite 读取 WAL 时遇到只读 SHM 问题。
        with sqlite3.connect(tmp_path) as conn:
            rows = conn.execute(
                f"""
                SELECT host, name, value, path, expiry, isSecure
                FROM moz_cookies
                WHERE host IN ({placeholders})
                """,
                hosts,
            ).fetchall()

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
        if temp_dir is not None:
            temp_dir.cleanup()

    return jar


def find_best_firefox_cookiejar(
    *,
    hosts: list[str],
    required_cookie: str | None = None,
    debug: bool = False,
    retries: int = 1,
    retry_delay: float = 0.5,
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
            f"[INFO] scanning Firefox profiles via sqlite: "
            f"{len(cookie_files)} profile(s)"
        )

    best_file: Path | None = None
    best_jar = requests.cookies.RequestsCookieJar()
    best_score = -1

    for cookie_file in cookie_files:
        jar = load_firefox_sqlite_cookies(
            cookie_file,
            hosts=hosts,
        )
        jar_names = {c.name for c in jar}

        score = len(jar_names)

        if required_cookie and required_cookie in jar_names:
            score += 1000

        if debug:
            print(
                f"[DEBUG] profile={cookie_file.parent.name}, "
                f"cookies={sorted(jar_names) if jar_names else []}, "
                f"score={score}"
            )

        if score > best_score:
            best_score = score
            best_file = cookie_file
            best_jar = jar

    # 必须检查 best_jar，而不是循环中最后一个 profile 的 names。
    best_names = {c.name for c in best_jar}

    if (
        required_cookie
        and required_cookie not in best_names
        and retries > 0
    ):
        if debug:
            print(
                f"[DEBUG] required cookie not found; "
                f"retrying SQLite snapshot in {retry_delay:.1f}s"
            )

        time.sleep(retry_delay)

        return find_best_firefox_cookiejar(
            hosts=hosts,
            required_cookie=required_cookie,
            debug=debug,
            retries=retries - 1,
            retry_delay=retry_delay,
        )

    if required_cookie:
        if required_cookie in best_names and best_file:
            print(
                f"[INFO] Firefox profile auto-selected: "
                f"{best_file.parent.name}"
            )
            print(f"[INFO] matched cookie_file: {best_file}")
        else:
            print(
                f"[WARN] no Firefox profile contains required cookie: "
                f"{required_cookie}"
            )

    return best_file, best_jar