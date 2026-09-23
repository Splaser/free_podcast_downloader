import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from podcast_archiver.downloader import download_episode, download_file_resume


class FakeResponse:
    def __init__(self, status, headers, chunks):
        self.status_code = status
        self.headers = headers
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.ranges = []

    def get(self, url, **kwargs):
        self.ranges.append(kwargs["headers"].get("Range"))
        return next(self.responses)


class DownloadReliabilityTests(unittest.TestCase):
    @patch("podcast_archiver.downloader.has_aria2", return_value=False)
    def test_already_complete_partial_file_is_promoted(self, *_):
        session = FakeSession([
            FakeResponse(416, {"Content-Range": "bytes */6"}, []),
        ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episode.mp3"
            Path(str(path) + ".part").write_bytes(b"abcdef")
            download_file_resume("https://example.com/audio", path, session=session)
            self.assertEqual(path.read_bytes(), b"abcdef")
        self.assertEqual(session.ranges, ["bytes=6-"])

    @patch("podcast_archiver.downloader.time.sleep")
    @patch("podcast_archiver.downloader.has_aria2", return_value=False)
    def test_retry_uses_current_partial_size(self, *_):
        session = FakeSession([
            FakeResponse(200, {"Content-Length": "6"}, [b"abc", requests.ConnectionError("drop")]),
            FakeResponse(206, {"Content-Length": "3", "Content-Range": "bytes 3-5/6"}, [b"def"]),
        ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episode.mp3"
            download_file_resume("https://example.com/audio", path, session=session)
            self.assertEqual(path.read_bytes(), b"abcdef")
            self.assertFalse(Path(str(path) + ".part").exists())
        self.assertEqual(session.ranges, [None, "bytes=3-"])

    @patch("podcast_archiver.downloader.time.sleep")
    @patch("podcast_archiver.downloader.has_aria2", return_value=False)
    def test_incomplete_response_never_becomes_final_file(self, *_):
        session = FakeSession([
            FakeResponse(200, {"Content-Length": "6"}, [b"ab"])
            for _ in range(3)
        ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episode.mp3"
            with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
                download_file_resume("https://example.com/audio", path, session=session)
            self.assertFalse(path.exists())
            self.assertEqual(Path(str(path) + ".part").read_bytes(), b"ab")
        self.assertEqual(session.ranges, [None, "bytes=2-", "bytes=2-"])

    @patch("podcast_archiver.downloader.tag_mp3", return_value=False)
    @patch("podcast_archiver.downloader.has_basic_tags", return_value=False)
    def test_tag_failure_is_reported(self, *_):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "album" / "episode.mp3"
            path.parent.mkdir()
            path.write_bytes(b"existing audio")
            ep = type("Episode", (), {
                "title": "episode",
                "podcast_title": "album",
                "author": "author",
                "description": "",
                "audio_url": "https://example.com/audio",
                "cover_url": "",
                "ext": ".mp3",
            })()
            with self.assertRaisesRegex(RuntimeError, "failed to write metadata"):
                download_episode(ep, output_dir=directory)

    @patch("podcast_archiver.downloader.write_episode_markdown_sidecar")
    @patch("podcast_archiver.downloader.has_aria2", return_value=False)
    def test_legacy_aria2_incomplete_file_is_resumed(self, *_):
        session = FakeSession([
            FakeResponse(206, {"Content-Length": "3", "Content-Range": "bytes 3-5/6"}, [b"def"]),
        ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "album" / "episode.mp3"
            path.parent.mkdir()
            path.write_bytes(b"abc")
            Path(str(path) + ".aria2").write_bytes(b"control")
            ep = type("Episode", (), {
                "title": "episode",
                "podcast_title": "album",
                "audio_url": "https://example.com/audio",
                "ext": ".mp3",
            })()
            download_episode(ep, output_dir=directory, session=session, write_tag=False)
            self.assertEqual(path.read_bytes(), b"abcdef")
            self.assertFalse(Path(str(path) + ".aria2").exists())
        self.assertEqual(session.ranges, ["bytes=3-"])


if __name__ == "__main__":
    unittest.main()
