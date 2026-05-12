# test_wechat_parse.py
import argparse

from podcast_archiver.wechat import parse_wechat_article


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)

    args = parser.parse_args()

    audio = parse_wechat_article(args.url)

    print("title:", audio.title)
    print("account:", audio.account)
    print("mediaid:", audio.mediaid)
    print("audio:", audio.audio_url)
    print("ext:", audio.ext)