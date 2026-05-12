# test_rss.py
import argparse

from podcast_archiver.session_utils import create_session
from podcast_archiver.rss import parse_rss_feed, print_episodes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rss", required=True)
    parser.add_argument("--latest", type=int, default=None)
    parser.add_argument("--browser", choices=["firefox", "chrome"], default=None)

    args = parser.parse_args()

    session = create_session(browser=args.browser, domain="anchor.fm")

    episodes = parse_rss_feed(args.rss, session=session)

    print(f"[INFO] parsed episodes: {len(episodes)}")
    print_episodes(episodes, limit=args.latest)