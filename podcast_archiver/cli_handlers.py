# podcast_archiver/cli_handlers.py
from pathlib import Path
import re

from urllib.parse import urlparse
from .tagging import tag_m4a, tag_mp3, has_basic_tags
from .session_utils import create_session
from .wechat import parse_wechat_article
from .rss import (
    parse_rss_feed,
    print_episodes,
    extract_original_url_from_proxy,
)
from .downloader import (
    download_episode,
    download_files_aria2,
    has_aria2,
)
from .filename import sanitize_filename
from .listen_notes_cursor_cache import get_best_cursor
from .listen_notes import parse_listen_notes_episode, Episode
from .listen_notes_list import (
    is_listen_notes_podcast_page,
    extract_listen_notes_list_context,
    fetch_more_episodes_from_listen_notes_api,
)
from .typlog import download_typlog_episode
from .afdian import (
    is_afdian_url,
    parse_input_url as parse_afdian_input_url,
    get_album_episodes,
    get_single_post_episode,
    download_afdian_episodes,
    print_afdian_episode,
)


def _get_arg(args, name: str, default=None):
    return getattr(args, name, default)


def handle_afdian_url(url: str, args) -> int:
    """
    爱发电入口：支持 /album/{album_id} 和 /p/{post_id}。

    - album：默认全量归档；传 --latest n 时只取最新 n 条；支持 --offset。
    - post：单条下载；如果误传 --latest，会忽略。
    """
    session = create_session(
        browser=_get_arg(args, "browser", "firefox") or "firefox",
        domain="ifdian.net",
    )

    kind, resource_id = parse_afdian_input_url(url)

    output_dir = _get_arg(args, "output", "downloads")
    offset = max(_get_arg(args, "offset", 0) or 0, 0)
    latest = _get_arg(args, "latest", None)

    if kind == "album":
        if latest is not None:
            print(f"[INFO] Afdian album latest={latest}, offset={offset}")
            episodes = get_album_episodes(
                resource_id,
                session=session,
                latest=latest,
                offset=offset,
            )
        else:
            print(f"[INFO] Afdian album full archive, offset={offset}")
            episodes = get_album_episodes(
                resource_id,
                session=session,
                latest=None,
                offset=offset,
            )

        print(f"[INFO] selected episodes: {len(episodes)}")

        if _get_arg(args, "list", False):
            for index, episode in enumerate(episodes, start=offset + 1):
                print_afdian_episode(episode, index=index)
            return 0

        download_afdian_episodes(
            episodes,
            output_dir=output_dir,
            session=session,
            write_tag=not _get_arg(args, "no_tag", False),
            retag_existing=_get_arg(args, "retag_existing", False),
        )
        return 0

    if kind == "post":
        if latest is not None:
            print("[WARN] /p/ 单条资源不支持 --latest 参数，已忽略")

        episode = get_single_post_episode(resource_id, session=session)
        if episode is None:
            print("[ERROR] this Afdian post has no audio")
            return 1

        if _get_arg(args, "list", False):
            print_afdian_episode(episode)
            return 0

        download_afdian_episodes(
            [episode],
            output_dir=output_dir,
            session=session,
            write_tag=not _get_arg(args, "no_tag", False),
            retag_existing=_get_arg(args, "retag_existing", False),
            sleep_time=0,
        )
        return 0

    print(f"[ERROR] unsupported Afdian resource kind: {kind}")
    return 1


def handle_afdian_id(album_id: str, args) -> int:
    """
    兼容旧项目 --id：默认视为 album_id。
    """
    url = f"https://ifdian.net/album/{album_id}"
    return handle_afdian_url(url, args)


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

    episode = Episode(
        title=audio.title,
        podcast_title=audio.account or "WeChat",
        author=audio.account or "WeChat",
        description=audio.source_url,
        audio_url=audio.audio_url,
        cover_url="",
        source_url=audio.source_url,
        ext=audio.ext,
    )

    output_path = download_episode(
        episode,
        output_dir=args.output,
        session=None,
        write_tag=not args.no_tag,
        retag_existing=args.retag_existing,
    )

    print("done:", output_path)
    return 0


def handle_rss(rss_url: str, args) -> int:
    session = create_session(browser=None)

    episodes = parse_rss_feed(rss_url, session=session)
    print(f"[INFO] parsed total RSS episodes: {len(episodes)}")

    offset = max(args.offset or 0, 0)

    if args.all:
        episodes = episodes[offset:]
    elif args.latest is not None:
        episodes = episodes[offset : offset + args.latest]

    if args.list:
        print(f"[INFO] selected episodes: {len(episodes)}")
        print_episodes(episodes)
        return 0

    if not args.all and args.latest is None:
        print("[ERROR] RSS mode requires --latest n or --all")
        print("[HINT] Example: python main.py --rss RSS_URL --latest 5")
        return 1

    print(f"[INFO] selected episodes: {len(episodes)}")

    # 先统一生成 target path，方便 aria2 直接按目标文件名保存
    urls = []
    episode_map = {}   # audio_url -> episode
    download_map = {}  # audio_url -> target Path

    for episode in episodes:
        print("title:", episode.title)
        print("podcast:", episode.podcast_title)
        print("audio:", episode.audio_url)
        print("ext:", episode.ext)

        origin = extract_original_url_from_proxy(episode.audio_url)
        if origin:
            print("[INFO] original post url:", origin)

        target_path = (
            Path(args.output)
            / sanitize_filename(episode.podcast_title)
            / (sanitize_filename(episode.title) + episode.ext)
        )

        urls.append(episode.audio_url)
        episode_map[episode.audio_url] = episode
        download_map[episode.audio_url] = target_path

    if has_aria2():
        pending_urls = []
        pending_filenames = []

        for url in urls:
            episode = episode_map[url]
            target_path = download_map[url]

            if target_path.exists():
                print(f"[INFO] skip existing file before aria2: {target_path}")
                continue

            pending_urls.append(url)
            pending_filenames.append(str(target_path.relative_to(Path(args.output))))

        if pending_urls:
            try:
                download_files_aria2(
                    pending_urls,
                    Path(args.output),
                    filenames=pending_filenames,
                )
            except Exception as e:
                print(f"[WARN] aria2 batch failed: {e}")
                print("[WARN] fallback to original single-download loop")

                for url in pending_urls:
                    episode = episode_map.get(url)
                    if not episode:
                        continue

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
        else:
            print("[INFO] no new files to download")

    else:
        print("[INFO] Aria2 not detected, using original single-download loop")

        for index, episode in enumerate(episodes, start=1):
            print(f"[INFO] downloading {index}/{len(episodes)}")

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

    # aria2 batch 下载后统一补 tag。
    # 注意：已存在但缺 tag 的文件，也会在这里被补上。
    if not args.no_tag:
        for audio_url, episode in episode_map.items():
            target_path = download_map[audio_url]

            if not target_path.exists():
                continue
            
            aria2_control_file = target_path.with_name(target_path.name + ".aria2")
            if aria2_control_file.exists():
                print(f"[INFO] skip tagging incomplete aria2 file: {target_path}")
                continue

            if not args.retag_existing and has_basic_tags(str(target_path), episode.ext):
                print(f"[INFO] basic tags exist, skip retag: {target_path}")
                continue

            if episode.ext.lower() in [".m4a", ".mp4"]:
                tag_m4a(
                    str(target_path),
                    title=episode.title,
                    artist=episode.author or episode.podcast_title,
                    album=episode.podcast_title,
                    description=episode.description,
                    cover_url=episode.cover_url,
                    session=session,
                )

            elif episode.ext.lower() == ".mp3":
                tag_mp3(
                    str(target_path),
                    title=episode.title,
                    artist=episode.author or episode.podcast_title,
                    album=episode.podcast_title,
                    description=episode.description,
                    cover_url=episode.cover_url,
                    session=session,
                )

            else:
                print(f"[WARN] tagging skipped for unsupported ext: {episode.ext}")

    return 0

rss_path_patterns = [
    r"/rss(?:/|$)",
    r"/feed(?:/|$)",
    r"/podcast(?:/|$)",
    r"/feed\.xml$",
    r"/rss\.xml$",
    r"/podcast\.xml$",
    r"/atom\.xml$",
    r"\.rss$",
    r"\.xml$",
]

rss_query_keys = [
    "feed=rss",
    "feed=podcast",
    "format=rss",
    "format=xml",
]

def is_probable_rss_url(url: str) -> bool:
    """
    判断一个 URL 是否大概率是 RSS / XML feed。

    目的：
    - 让 RSS 也可以统一走 --url
    - 保留 --rss 老入口
    - 不做网络探测，避免误把普通网页也请求一遍
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()

    if any(re.search(pattern, path) for pattern in rss_path_patterns):
        return True

    if any(key in query for key in rss_query_keys):
        return True

    # 一些常见播客 feed 域名/路径特征
    host = parsed.netloc.lower()

    if "rss" in host and path:
        return True

    if "feed" in host and path:
        return True

    return False


def handle_url(url: str, args) -> int:
    host = urlparse(url).netloc.lower()

    if is_afdian_url(url):
        return handle_afdian_url(url, args)

    if is_probable_rss_url(url):
        print("[INFO] URL looks like RSS feed, dispatching to RSS handler")
        return handle_rss(url, args)

    if "listennotes.com" in host:
        if is_listen_notes_podcast_page(url):
            return handle_listen_notes_list_url(url, args)

        return handle_listen_notes_url(url, args)

    if "mp.weixin.qq.com" in host:
        return handle_wechat_url(url, args)

    if "siji.typlog.io" in host:
        # 判断是单条 episode 或 archive 页面
        if "/archive/" in url:
            import requests
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin

            resp = requests.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            episode_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("/episodes/") and href != "/episodes/":
                    episode_links.append(urljoin(url, href))

            episode_links = list(dict.fromkeys(episode_links))

            print(f"[INFO] found {len(episode_links)} episode links in archive")

            for ep_url in episode_links:
                print(f"[INFO] downloading {ep_url}")
                download_typlog_episode(
                    ep_url,
                    output_dir=args.output,
                    session=None,
                    write_tag=not args.no_tag,
                    retag_existing=args.retag_existing,
                )
            return 0

        else:
            if args.list:
                print(f"[INFO] Typlog episode: {url}")
                return 0

            download_typlog_episode(
                url,
                output_dir=args.output,
                session=None,
                write_tag=not args.no_tag,
                retag_existing=args.retag_existing,
            )
            return 0

    print(f"[ERROR] unsupported URL host: {host}")
    print(
        "[HINT] Currently supported URL hosts: listennotes.com, mp.weixin.qq.com, ifdian.net, afdian.com, RSS feed URLs"
    )
    return 1


def dispatch_args(args) -> int:
    """
    Main CLI dispatcher.
    """
    if args.rss:
        return handle_rss(args.rss, args)

    if args.url:
        return handle_url(args.url, args)

    if getattr(args, "id", None):
        return handle_afdian_id(args.id, args)

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

    cursor_hit = None
    virtual_offset_base = 0
    if offset > len(first_page_links) and channel_uuid:
        cursor_hit = get_best_cursor(channel_uuid, offset)

        if cursor_hit:
            cached_count = int(cursor_hit.get("collected_count") or 0)

            print(
                f"[INFO] Listen Notes cursor cache hit: "
                f"cached_count={cached_count}, requested_offset={offset}"
            )

            next_pub_date = int(cursor_hit["next_pub_date"])

            if cursor_hit.get("prev_pub_date"):
                prev_pub_date = int(cursor_hit["prev_pub_date"])

            virtual_offset_base = cached_count

            # 缓存命中后，首屏 links 不再参与本次 jobs。
            # 因为我们准备从 cached cursor 后面继续拉。
            first_page_links = []

    if latest is not None:
        wanted_total = max(offset - virtual_offset_base, 0) + latest
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

    cache_mode = bool(cursor_hit)

    if cache_mode:
        api_pages_needed = max_pages
    else:
        api_pages_needed = max_pages - 1

    need_more = (
        channel_uuid
        and prev_pub_date
        and next_pub_date
        and api_pages_needed > 0
        and (wanted_total is None or wanted_total > len(first_page_links))
    )

    if need_more:
        extra_pages = api_pages_needed

        print(
            f"[INFO] load-more enabled: max_pages={max_pages}, "
            f"extra_pages={extra_pages}, cache_mode={cache_mode}"
        )

        api_episodes = fetch_more_episodes_from_listen_notes_api(
            channel_uuid=channel_uuid,
            session=session,
            next_pub_date=next_pub_date,
            prev_pub_date=prev_pub_date,
            max_pages=extra_pages,
            referer_url=url,
            initial_collected_count=virtual_offset_base,
            initial_page_index=virtual_offset_base // page_size,
        )

    if (
        max_pages > 1
        and wanted_total is not None
        and wanted_total > len(first_page_links)
        and not need_more
    ):
        print("[WARN] Load-more requested but context is incomplete.")
        print(
            f"[WARN] wanted_total={wanted_total}, first_page_links={len(first_page_links)}"
        )
        print(f"[WARN] channel_uuid={channel_uuid or '(not found)'}")
        print(f"[WARN] prev_pub_date={prev_pub_date}")
        print(f"[WARN] next_pub_date={next_pub_date}")
        print(
            "[HINT] Auto context extraction failed. Check debug_listennotes_context.html or pass override args."
        )

    jobs = []

    for link in first_page_links:
        jobs.append(("url", link))

    for episode in api_episodes:
        jobs.append(("api", episode))

    effective_offset = max(offset - virtual_offset_base, 0)
    print(f"[INFO] effective_offset={effective_offset}")

    if args.all:
        selected_jobs = jobs[effective_offset:]
    elif latest is not None:
        selected_jobs = jobs[effective_offset : effective_offset + latest]
    else:
        print("[ERROR] Listen Notes list mode requires --latest n or --all")
        print(
            "[HINT] Example: python main.py --url LISTEN_NOTES_PODCAST_URL --latest 30"
        )
        return 1

    print(f"[INFO] total collected episodes: {len(jobs)}")
    print(f"[INFO] offset={offset}")
    print(f"[INFO] selected episodes: {len(selected_jobs)}")

    if latest is not None and len(selected_jobs) < latest:
        print(
            f"[WARN] selected episodes less than requested: selected={len(selected_jobs)}, requested={latest}"
        )
        print("[HINT] Increase --max-pages or check load-more context.")

    if args.list:
        for absolute_index, (kind, value) in enumerate(selected_jobs, start=offset + 1):
            if kind == "url":
                print(f"{absolute_index}. {value}")
            else:
                print(f"{absolute_index}. {value.source_url or value.title}")

        return 0

    # 收集所有 URL 与 episode 对象，并生成 target path
    urls = []
    episode_map = {}  # audio_url -> episode
    download_map = {}  # audio_url -> target Path

    for kind, value in selected_jobs:
        if kind == "url":
            episode = parse_listen_notes_episode(value, session)
        else:
            episode = value

        urls.append(episode.audio_url)
        episode_map[episode.audio_url] = episode

        target_path = (
            Path(args.output)
            / sanitize_filename(episode.podcast_title)
            / (sanitize_filename(episode.title) + episode.ext)
        )
        download_map[episode.audio_url] = target_path

    if has_aria2():
        pending_urls = []
        pending_filenames = []

        for url in urls:
            target_path = download_map[url]

            if target_path.exists():
                print(f"[INFO] skip existing file before aria2: {target_path}")
                continue

            pending_urls.append(url)
            pending_filenames.append(str(target_path.relative_to(Path(args.output))))

        if pending_urls:
            download_files_aria2(
                pending_urls,
                Path(args.output),
                filenames=pending_filenames,
            )
        else:
            print("[INFO] no new files to download")
    else:
        print("[INFO] Aria2 not detected, using original single-download loop")
        for url in urls:
            ep = episode_map.get(url)
            if ep:
                download_episode(
                    ep,
                    output_dir=args.output,
                    session=session,
                    write_tag=not args.no_tag,
                    retag_existing=args.retag_existing,
                )

    # 批量写 tag（只写，不再 download）
    if not args.no_tag:
        for audio_url, episode in episode_map.items():
            target_path = download_map[audio_url]
            if target_path.exists():
                if episode.ext.lower() in [".m4a", ".mp4"]:
                    tag_m4a(
                        str(target_path),
                        title=episode.title,
                        artist=episode.author or episode.podcast_title,
                        album=episode.podcast_title,
                        description=episode.description,
                        cover_url=episode.cover_url,
                        session=session,
                    )
                elif episode.ext.lower() == ".mp3":
                    tag_mp3(
                        str(target_path),
                        title=episode.title,
                        artist=episode.author or episode.podcast_title,
                        album=episode.podcast_title,
                        description=episode.description,
                        cover_url=episode.cover_url,
                        session=session,
                    )

    return 0
