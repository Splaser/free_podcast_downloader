from __future__ import annotations

from typing import Iterable


def print_job(job, index: int | None = None) -> None:
    episode = job.episode

    prefix = f"{index}. " if index is not None else ""

    print(f"{prefix}{episode.title}")
    print(f"   podcast: {episode.podcast_title}")
    print(f"   audio: {episode.audio_url}")
    print(f"   ext: {episode.ext}")
    print(f"   target: {job.target_path}")
    print(f"   exists: {job.exists}")
    print(f"   incomplete: {job.incomplete}")
    print()


def print_jobs(jobs: Iterable, start: int = 1) -> None:
    for index, job in enumerate(jobs, start=start):
        print_job(job, index=index)