# test_parse.py
import argparse

from podcast_archiver.session_utils import create_session
from podcast_archiver.listen_notes import parse_listen_notes_episode


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--browser", choices=["firefox", "chrome"], default="firefox")
    args = parser.parse_args()

    session = create_session(browser=args.browser, domain="listennotes.com")
    episode = parse_listen_notes_episode(args.url, session)

    print("title:", episode.title)
    print("podcast:", episode.podcast_title)
    print("author:", episode.author)
    print("cover:", episode.cover_url)
    print("audio:", episode.audio_url)
    print("ext:", episode.ext)