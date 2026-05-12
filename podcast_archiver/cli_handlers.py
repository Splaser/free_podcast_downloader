# podcast_archiver/cli_handlers.py
from pathlib import Path
from urllib.parse import urlparse

from podcast_archiver.session_utils import create_session
from podcast_archiver.wechat import parse_wechat_article
from podcast_archiver.rss import (
    parse_rss_feed,
    print_episodes,
    extract_original_url_from_proxy,
)
from podcast_archiver.downloader import download_episode, download_file
from podcast_archiver.filename import sanitize_filename

from podcast_archiver.listen_notes import parse_listen_notes_episode
from podcast_archiver.listen_notes_list import (
    is_listen_notes_podcast_page,
    extract_episode_links_from_listen_notes_page,
    print_episode_links,
)


def print_episode(episode) -> None:
    print("title:", episode.title)
    print("podcast:", episode.podcast_title)
    print("author:", episode.author)
    print("cover:", episode.cover_url)
    print("audio:", episode.audio_url)
    print("ext:", episode.ext)


def print_wechat_audio(audio) -> None:
    print("title:", audio.title)
    print("account:", audio.account)
    print("mediaid:", audio.mediaid)
    print("audio:", audio.audio_url)
    print("ext:", audio.ext)


def handle_listen_notes_url(url: str, args) -> int:
    session = create_session(
        browser=args.browser,
        domain="listennotes.com",
    )

    episode = parse_listen_notes_episode(url, session)
    print_episode(episode)

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


def handle_wechat_url(url: str, args) -> int:
    audio = parse_wechat_article(url)
    print_wechat_audio(audio)

    if args.list:
        return 0

    account_dir = sanitize_filename(audio.account)
    filename = sanitize_filename(audio.title) + audio.ext
    output_path = Path(args.output) / account_dir / filename

    print("output:", output_path)

    download_file(audio.audio_url, output_path)

    # 当前还没有接 MP3 tag，先明确提示。
    if not args.no_tag:
        print("[WARN] WeChat MP3 tagging is not implemented yet, skipped.")

    print("done:", output_path)
    return 0


def handle_rss(rss_url: str, args) -> int:
    session = create_session(browser=None)

    episodes = parse_rss_feed(rss_url, session=session)

    if args.latest is not None:
        episodes = episodes[: args.latest]

    if args.list:
        print(f"[INFO] selected episodes: {len(episodes)}")
        print_episodes(episodes)
        return 0

    if not args.all and args.latest is None:
        print("[ERROR] RSS mode requires --latest n or --all")
        print("[HINT] Example: python main.py --rss RSS_URL --latest 5")
        return 1

    print(f"[INFO] selected episodes: {len(episodes)}")

    for index, episode in enumerate(episodes, start=1):
        print(f"[INFO] downloading {index}/{len(episodes)}")
        print("title:", episode.title)
        print("podcast:", episode.podcast_title)
        print("audio:", episode.audio_url)
        print("ext:", episode.ext)

        origin = extract_original_url_from_proxy(episode.audio_url)
        if origin:
            print("[INFO] original post url:", origin)

        try:
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

    return 0


def handle_url(url: str, args) -> int:
    host = urlparse(url).netloc.lower()

    if "listennotes.com" in host:
        if is_listen_notes_podcast_page(url):
            return handle_listen_notes_list_url(url, args)

        return handle_listen_notes_url(url, args)

    if "mp.weixin.qq.com" in host:
        return handle_wechat_url(url, args)

    print(f"[ERROR] unsupported URL host: {host}")
    print("[HINT] Currently supported URL hosts: listennotes.com, mp.weixin.qq.com")
    return 1

def dispatch_args(args) -> int:
    """
    Main CLI dispatcher.
    """
    if args.rss:
        return handle_rss(args.rss, args)

    if args.url:
        return handle_url(args.url, args)

    return 1

def handle_listen_notes_list_url(url: str, args) -> int:
    session = create_session(
        browser=args.browser,
        domain="listennotes.com",
    )

    links = extract_episode_links_from_listen_notes_page(url, session=session)

    if args.latest is not None:
        links = links[: args.latest]

    print(f"[INFO] extracted episode links: {len(links)}")

    if args.list:
        print_episode_links(links)
        return 0

    if not args.all and args.latest is None:
        print("[ERROR] Listen Notes list mode requires --latest n or --all")
        print("[HINT] Example: python main.py --url LISTEN_NOTES_PODCAST_URL --latest 5")
        return 1

    for index, episode_url in enumerate(links, start=1):
        print(f"[INFO] downloading episode {index}/{len(links)}")
        print("[INFO] episode url:", episode_url)

        try:
            episode = parse_listen_notes_episode(episode_url, session)
            print_episode(episode)

            output_path = download_episode(
                episode,
                output_dir=args.output,
                session=session,
                write_tag=not args.no_tag,
            )

            print("done:", output_path)

        except Exception as e:
            print(f"[ERROR] failed episode: {episode_url}")
            print(f"[ERROR] {e}")
            print()
            continue

    return 0