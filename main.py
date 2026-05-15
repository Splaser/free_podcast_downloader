# main.py
import argparse
import sys

from podcast_archiver.cli_handlers import dispatch_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download publicly available podcast episodes from "
            "Listen Notes, WeChat articles, or RSS feeds."
        )
    )

    source = parser.add_mutually_exclusive_group(required=True)

    source.add_argument(
        "--url",
        help="Episode/article URL. Supports Listen Notes episode URLs and WeChat article URLs.",
    )

    source.add_argument(
        "--rss",
        help="Podcast RSS feed URL.",
    )
    
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max pages to fetch in Listen Notes list mode. Auto calculated when omitted.",
    )
    parser.add_argument(
        "--browser",
        choices=["firefox", "chrome"],
        default="firefox",
        help="Browser to load cookies from for Listen Notes. Default: firefox",
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
        help="Only parse and print metadata, do not download",
    )

    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip first n episodes before applying --latest. Useful for batch archive.",
    )

    parser.add_argument(
        "--latest",
        type=int,
        default=None,
        help="In RSS mode, select latest n episodes.",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="In RSS mode, download all episodes. Use carefully.",
    )

    parser.add_argument(
        "--fix-cover",
        action="store_true",
        help="Only fix missing embedded covers for existing files",
    )

    parser.add_argument(
        "--retag-existing",
        action="store_true",
        help="Retag existing files even if basic metadata already exists.",
    )

    parser.add_argument("--channel-uuid", default=None)
    parser.add_argument("--next-pub-date", type=int, default=None)
    parser.add_argument("--prev-pub-date", type=int, default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return dispatch_args(args)

    except KeyboardInterrupt:
        print("\n[WARN] interrupted by user")
        return 130

    except Exception as e:
        print(f"[ERROR] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())