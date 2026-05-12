# test_wechat_download.py
import argparse
from pathlib import Path

from podcast_archiver.filename import sanitize_filename
from podcast_archiver.wechat import parse_wechat_article
from podcast_archiver.downloader import download_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", default="downloads")

    args = parser.parse_args()

    audio = parse_wechat_article(args.url)

    account_dir = sanitize_filename(audio.account)
    filename = sanitize_filename(audio.title) + audio.ext
    output_path = Path(args.output) / account_dir / filename

    print("title:", audio.title)
    print("account:", audio.account)
    print("audio:", audio.audio_url)
    print("output:", output_path)

    download_file(audio.audio_url, output_path)

    print("done:", output_path)