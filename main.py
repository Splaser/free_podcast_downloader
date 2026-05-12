# main.py
import argparse
import sys

from podcast_archiver.session_utils import create_session
from podcast_archiver.listen_notes import parse_listen_notes_episode
from podcast_archiver.downloader import download_episode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download publicly available podcast episodes from Listen Notes."
    )

    parser.add_argument(
        "--url",
        required=True,
        help="Listen Notes episode URL",
    )

    parser.add_argument(
        "--browser",
        choices=["firefox", "chrome"],
        default="firefox",
        help="Browser to load cookies from. Default: firefox",
    )

    parser.add_argument(
        "--output",
        default="downloads",
        help="Output directory. Default: downloads",
    )

    parser.add_argument(
        "--no-tag",
        action="store_true",
        help="Do not write metadata tags to downloaded audio file",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="Only parse and print episode metadata, do not download",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        session = create_session(
            browser=args.browser,
            domain="listennotes.com",
        )

        episode = parse_listen_notes_episode(args.url, session)

        print("title:", episode.title)
        print("podcast:", episode.podcast_title)
        print("author:", episode.author)
        print("cover:", episode.cover_url)
        print("audio:", episode.audio_url)
        print("ext:", episode.ext)

        if args.list:
            return 0

        output_path = download_episode(
            episode,
            output_dir=args.output,
            session=session,
            write_tag=not args.no_tag,
        )

        print("done:", output_path)
        return 0

    except KeyboardInterrupt:
        print("\n[WARN] interrupted by user")
        return 130

    except Exception as e:
        print(f"[ERROR] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())