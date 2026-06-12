from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .filename import sanitize_filename


@dataclass(frozen=True)
class DownloadJob:
    """
    一条待处理下载任务。

    planner 只负责“计划”，不负责真正下载、tag、写 markdown。
    """

    episode: Any
    target_path: Path
    relative_path: Path
    exists: bool
    incomplete: bool

    @property
    def audio_url(self) -> str:
        return self.episode.audio_url

    @property
    def aria2_control_path(self) -> Path:
        return self.target_path.with_name(self.target_path.name + ".aria2")


def build_target_path(episode: Any, output_dir: str | Path) -> Path:
    """
    根据 episode 生成最终音频文件路径。

    规则保持和原 cli_handlers.py / downloader.py 一致：
    downloads / podcast_title / title.ext
    """
    output_root = Path(output_dir)

    return (
        output_root
        / sanitize_filename(episode.podcast_title)
        / (sanitize_filename(episode.title) + episode.ext)
    )


def build_download_job(episode: Any, output_dir: str | Path) -> DownloadJob:
    output_root = Path(output_dir)
    target_path = build_target_path(episode, output_root)
    aria2_control_path = target_path.with_name(target_path.name + ".aria2")

    return DownloadJob(
        episode=episode,
        target_path=target_path,
        relative_path=target_path.relative_to(output_root),
        exists=target_path.exists(),
        incomplete=aria2_control_path.exists(),
    )


def plan_downloads(episodes: list[Any], output_dir: str | Path) -> list[DownloadJob]:
    return [build_download_job(ep, output_dir) for ep in episodes]


def split_pending_jobs(
    jobs: list[DownloadJob],
) -> tuple[list[DownloadJob], list[DownloadJob]]:
    """
    返回：
    - pending: 目标文件不存在，需要下载
    - existing: 目标文件已经存在
    """
    pending = [job for job in jobs if not job.exists]
    existing = [job for job in jobs if job.exists]
    return pending, existing
