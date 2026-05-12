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
    extract_listen_notes_list_context,
    fetch_more_episodes_from_listen_notes_api,
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
        retag_existing=args.retag_existing,
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
                retag_existing=args.retag_existing,
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

    ctx = extract_listen_notes_list_context(url, session=session)

    links = ctx["links"]
    channel_uuid = args.channel_uuid or ctx["channel_uuid"]
    prev_pub_date = args.prev_pub_date or ctx["prev_pub_date"]
    next_pub_date = args.next_pub_date or ctx["next_pub_date"]

    print(f"[INFO] initial episode links: {len(links)}")
    print(f"[INFO] channel_uuid: {channel_uuid or '(not found)'}")
    print(f"[INFO] prev_pub_date: {prev_pub_date}")
    print(f"[INFO] next_pub_date: {next_pub_date}")

    # 先处理首屏 links，保持原逻辑
    first_page_links = links

    # 如果用户要的数量超过首屏，且 max_pages > 1，则调用 API 补后续
    api_episodes = []

    wanted = args.latest if args.latest is not None else None

    need_more = (
        channel_uuid
        and prev_pub_date
        and next_pub_date
        and args.max_pages > 1
        and (wanted is None or wanted > len(first_page_links))
    )

    if need_more:
        extra_pages = args.max_pages - 1
        api_episodes = fetch_more_episodes_from_listen_notes_api(
            channel_uuid=channel_uuid,
            session=session,
            next_pub_date=next_pub_date,
            prev_pub_date=prev_pub_date,
            max_pages=extra_pages,
            referer_url=url,
        )

    if (
        args.max_pages > 1
        and wanted is not None
        and wanted > len(first_page_links)
        and not need_more
    ):
        print("[WARN] Load-more requested but context is incomplete.")
        print(f"[WARN] wanted={wanted}, first_page_links={len(first_page_links)}")
        print(f"[WARN] channel_uuid={channel_uuid or '(not found)'}")
        print(f"[WARN] prev_pub_date={prev_pub_date}")
        print(f"[WARN] next_pub_date={next_pub_date}")
        print("[HINT] Auto context extraction failed. Check debug_listennotes_context.html or pass override args.")

    # --list 模式：
    # 首屏显示 URL，API 页显示 source_url
    if args.list:
        combined = []

        for link in first_page_links:
            combined.append(("url", link))

        for episode in api_episodes:
            combined.append(("api", episode.source_url or episode.title))

        if args.latest is not None:
            combined = combined[: args.latest]

        print(f"[INFO] extracted episodes: {len(combined)}")

        for index, (_, value) in enumerate(combined, start=1):
            print(f"{index}. {value}")

        return 0

    if not args.all and args.latest is None:
        print("[ERROR] Listen Notes list mode requires --latest n or --all")
        print("[HINT] Example: python main.py --url LISTEN_NOTES_PODCAST_URL --latest 30 --max-pages 3")
        return 1

    # 下载阶段：
    # 首屏 links 走 parse_listen_notes_episode
    # API episodes 直接 download_episode
    if args.latest is not None:
        remaining = args.latest
    else:
        remaining = None

    downloaded_count = 0

    selected_links = first_page_links
    if remaining is not None:
        selected_links = selected_links[:remaining]

    for index, episode_url in enumerate(selected_links, start=1):
        print(f"[INFO] downloading episode {downloaded_count + 1}")
        print("[INFO] episode url:", episode_url)

        try:
            episode = parse_listen_notes_episode(episode_url, session)
            print_episode(episode)

            output_path = download_episode(
                episode,
                output_dir=args.output,
                session=session,
                write_tag=not args.no_tag,
                retag_existing=args.retag_existing,
            )

            print("done:", output_path)
            downloaded_count += 1

        except Exception as e:
            print(f"[ERROR] failed episode: {episode_url}")
            print(f"[ERROR] {e}")
            print()
            continue

    if remaining is not None:
        remaining -= downloaded_count

    selected_api_episodes = api_episodes
    if remaining is not None:
        selected_api_episodes = selected_api_episodes[:remaining]

    for episode in selected_api_episodes:
        print(f"[INFO] downloading episode {downloaded_count + 1}")
        print("[INFO] episode url:", episode.source_url)
        print_episode(episode)

        try:
            output_path = download_episode(
                episode,
                output_dir=args.output,
                session=session,
                write_tag=not args.no_tag,
                retag_existing=args.retag_existing,
            )

            print("done:", output_path)
            downloaded_count += 1

        except Exception as e:
            print(f"[ERROR] failed episode: {episode.source_url or episode.title}")
            print(f"[ERROR] {e}")
            print()
            continue

    return 0