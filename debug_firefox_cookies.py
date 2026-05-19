# debug_firefox_cookies.py
from pathlib import Path
import sqlite3
import shutil
import tempfile
import os

profiles_root = Path(os.environ["APPDATA"]) / "Mozilla" / "Firefox" / "Profiles"

for profile in profiles_root.iterdir():
    cookies_db = profile / "cookies.sqlite"
    if not cookies_db.exists():
        continue

    print("\n[PROFILE]", profile.name)

    # 避免 Firefox 占用 sqlite，复制一份再读
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
        tmp_path = Path(tmp.name)

    shutil.copy2(cookies_db, tmp_path)

    try:
        conn = sqlite3.connect(tmp_path)
        cur = conn.cursor()

        cur.execute("""
            SELECT host, name, path, expiry
            FROM moz_cookies
            WHERE host LIKE '%ifdian%'
               OR host LIKE '%afdian%'
            ORDER BY host, name
            """)

        rows = cur.fetchall()
        if not rows:
            print("  no afdian/ifdian cookies")
        else:
            for host, name, path, expiry in rows:
                print(f"  {name} | host={host} | path={path} | expiry={expiry}")

        conn.close()

    finally:
        tmp_path.unlink(missing_ok=True)
