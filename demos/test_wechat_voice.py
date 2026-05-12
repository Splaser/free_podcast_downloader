# test_wechat_voice.py
import argparse
from pathlib import Path

import requests


def test_getvoice(mediaid: str, output_dir: str = "downloads_wechat"):
    url = f"https://res.wx.qq.com/voice/getvoice?mediaid={mediaid}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "audio/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Referer": "https://mp.weixin.qq.com/",
    }

    print("[INFO] GET", url)

    resp = requests.get(url, headers=headers, timeout=60, stream=True)

    print("[INFO] status:", resp.status_code)
    print("[INFO] final_url:", resp.url)
    print("[INFO] content-type:", resp.headers.get("content-type"))
    print("[INFO] content-length:", resp.headers.get("content-length"))

    if resp.status_code != 200:
        preview = resp.text[:500]
        print("[WARN] response preview:")
        print(preview)
        return

    content_type = (resp.headers.get("content-type") or "").lower()

    if "audio" not in content_type and "octet-stream" not in content_type:
        preview = resp.content[:500].decode("utf-8", errors="replace")
        print("[WARN] response does not look like audio:")
        print(preview)
        return

    ext = ".mp3"
    if "mpeg" in content_type or "mp3" in content_type:
        ext = ".mp3"
    elif "amr" in content_type:
        ext = ".amr"
    elif "mp4" in content_type or "m4a" in content_type:
        ext = ".m4a"

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out = out_dir / f"{mediaid}{ext}"

    with open(out, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            if chunk:
                f.write(chunk)

    print("[INFO] saved:", out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mediaid", required=True)
    parser.add_argument("--output", default="downloads_wechat")

    args = parser.parse_args()

    test_getvoice(args.mediaid, output_dir=args.output)