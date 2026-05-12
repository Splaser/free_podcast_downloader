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

    first_page_links = links
    api_episodes = []

    offset = max(args.offset or 0, 0)
    latest = args.latest

    page_size = len(first_page_links) or 10

    if latest is not None:
        wanted_total = offset + latest
    elif args.all:
        wanted_total = None
    else:
        wanted_total = len(first_page_links)

    if args.max_pages is not None:
        max_pages = max(args.max_pages, 1)
    elif wanted_total is not None:
        max_pages = max(1, (wanted_total + page_size - 1) // page_size)
    else:
        # --all 没有显式 max-pages 时，默认只抓首屏，避免误全量狂拉
        max_pages = 1

    print(f"[INFO] page_size={page_size}")
    print(f"[INFO] wanted_total={wanted_total}")
    print(f"[INFO] max_pages={max_pages}")

    need_more = (
        channel_uuid
        and prev_pub_date
        and next_pub_date
        and max_pages > 1
        and (
            wanted_total is None
            or wanted_total > len(first_page_links)
        )
    )

    if need_more:
        extra_pages = max_pages - 1

        print(f"[INFO] load-more enabled: max_pages={max_pages}, extra_pages={extra_pages}")

        api_episodes = fetch_more_episodes_from_listen_notes_api(
            channel_uuid=channel_uuid,
            session=session,
            next_pub_date=next_pub_date,
            prev_pub_date=prev_pub_date,
            max_pages=extra_pages,
            referer_url=url,
        )

    if (
        max_pages > 1
        and wanted_total is not None
        and wanted_total > len(first_page_links)
        and not need_more
    ):
        print("[WARN] Load-more requested but context is incomplete.")
        print(f"[WARN] wanted_total={wanted_total}, first_page_links={len(first_page_links)}")
        print(f"[WARN] channel_uuid={channel_uuid or '(not found)'}")
        print(f"[WARN] prev_pub_date={prev_pub_date}")
        print(f"[WARN] next_pub_date={next_pub_date}")
        print("[HINT] Auto context extraction failed. Check debug_listennotes_context.html or pass override args.")

    jobs = []

    for link in first_page_links:
        jobs.append(("url", link))

    for episode in api_episodes:
        jobs.append(("api", episode))

    if args.all:
        selected_jobs = jobs[offset:]
    elif latest is not None:
        selected_jobs = jobs[offset: offset + latest]
    else:
        print("[ERROR] Listen Notes list mode requires --latest n or --all")
        print("[HINT] Example: python main.py --url LISTEN_NOTES_PODCAST_URL --latest 30")
        return 1

    print(f"[INFO] total collected episodes: {len(jobs)}")
    print(f"[INFO] offset={offset}")
    print(f"[INFO] selected episodes: {len(selected_jobs)}")

    if latest is not None and len(selected_jobs) < latest:
        print(f"[WARN] selected episodes less than requested: selected={len(selected_jobs)}, requested={latest}")
        print("[HINT] Increase --max-pages or check load-more context.")

    if args.list:
        for absolute_index, (kind, value) in enumerate(selected_jobs, start=offset + 1):
            if kind == "url":
                print(f"{absolute_index}. {value}")
            else:
                print(f"{absolute_index}. {value.source_url or value.title}")

        return 0

    for absolute_index, (kind, value) in enumerate(selected_jobs, start=offset + 1):
        print(f"[INFO] downloading episode {absolute_index}")

        try:
            if kind == "url":
                episode_url = value
                print("[INFO] episode url:", episode_url)
                episode = parse_listen_notes_episode(episode_url, session)
            else:
                episode = value
                print("[INFO] episode url:", episode.source_url)

            print_episode(episode)

            output_path = download_episode(
                episode,
                output_dir=args.output,
                session=session,
                write_tag=not args.no_tag,
                retag_existing=args.retag_existing,
            )

            print("done:", output_path)

        except Exception as e:
            target = value if kind == "url" else (value.source_url or value.title)
            print(f"[ERROR] failed episode: {target}")
            print(f"[ERROR] {e}")
            print()
            continue

    return 0