# test_rss_download.py
import argparse

from podcast_archiver.rss import parse_rss_feed, print_episodes, extract_original_url_from_proxy
from podcast_archiver.downloader import download_episode
from podcast_archiver.session_utils import create_session


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rss", required=True)
    parser.add_argument("--latest", type=int, default=1)
    parser.add_argument("--output", default="downloads")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--no-tag", action="store_true")

    args = parser.parse_args()
    session = create_session(browser=None)
    episodes = parse_rss_feed(args.rss, session=session)

    if args.latest is not None:
        episodes = episodes[:args.latest]

    print(f"[INFO] selected episodes: {len(episodes)}")

    if args.list:
        print_episodes(episodes)
        raise SystemExit(0)

    for index, episode in enumerate(episodes, start=1):
        print(f"[INFO] downloading {index}/{len(episodes)}")
        print("title:", episode.title)
        print("podcast:", episode.podcast_title)
        print("audio:", episode.audio_url)
        print("ext:", episode.ext)

        try:
            origin = extract_original_url_from_proxy(episode.audio_url)
            if origin:
                print("[INFO] original post url:", origin)
            
            output_path = download_episode(
                episode,
                output_dir=args.output,
                session=session,
                write_tag=not args.no_tag,
            )

            print("done:", output_path)

        except Exception as e:
            print(f"[ERROR] download failed: {episode.title}")
            print(f"[ERROR] {e}")
            print()
            continue