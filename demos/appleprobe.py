from __future__ import annotations

import argparse
import sys

from podcast_archiver.apple_podcasts import (
    extract_apple_podcast_id,
    resolve_apple_podcast_rss_url,
)
from podcast_archiver.rss import parse_rss_feed
from podcast_archiver.session_utils import create_session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Apple Podcasts show URL")
    parser.add_argument("--latest", type=int, default=5)
    args = parser.parse_args()

    session = create_session(browser=None)

    print("[INFO] input:", args.url)

    podcast_id = extract_apple_podcast_id(args.url)
    print("[INFO] apple podcast id:", podcast_id)

    rss_url = resolve_apple_podcast_rss_url(args.url, session=session)
    print("[INFO] resolved RSS:", rss_url)

    episodes, track_index_map, track_total = parse_rss_feed(
        rss_url,
        session=session,
    )

    print("[INFO] parsed episodes:", len(episodes))
    print("[INFO] track_total:", track_total)
    print()

    for index, ep in enumerate(episodes[: args.latest], start=1):
        track_index = track_index_map.get(ep.audio_url)

        print(f"{index}. {ep.title}")
        print(f"   podcast: {ep.podcast_title}")
        print(f"   author: {ep.author}")
        print(f"   track: {track_index}/{track_total}")
        print(f"   audio: {ep.audio_url}")
        print(f"   cover: {ep.cover_url}")
        print(f"   ext: {ep.ext}")
        print(f"   source: {ep.source_url}")
        print()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("[ERROR]", e)
        raise