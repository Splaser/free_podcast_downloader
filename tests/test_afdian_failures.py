import unittest
from types import SimpleNamespace
from unittest.mock import patch

from podcast_archiver.afdian import download_afdian_episodes, iter_album_items
from podcast_archiver.cli_handlers import handle_afdian_url


class ApiResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class ApiSession:
    def __init__(self, payloads):
        self.responses = iter(ApiResponse(payload) for payload in payloads)

    def get(self, *_args, **_kwargs):
        return next(self.responses)


class AfdianFailureTests(unittest.TestCase):
    def test_api_error_after_first_page_is_not_treated_as_complete(self):
        session = ApiSession([
            {"ec": 200, "data": {"list": [{"post_id": "one", "rank": 1}], "has_more": 1}},
            {"ec": 40100, "em": "login required", "data": {}},
        ])
        with self.assertRaisesRegex(RuntimeError, "40100"):
            iter_album_items("album", session)

    def test_empty_followup_page_is_not_treated_as_complete(self):
        session = ApiSession([
            {"ec": 200, "data": {"list": [{"post_id": "one", "rank": 1}], "has_more": 1}},
            {"ec": 200, "data": {"list": [], "has_more": 0}},
        ])
        with self.assertRaisesRegex(RuntimeError, "empty page"):
            iter_album_items("album", session)

    def test_unexpected_empty_payload_is_not_treated_as_empty_album(self):
        session = ApiSession([{"ec": 200, "data": {}}])
        with self.assertRaisesRegex(RuntimeError, "empty page"):
            iter_album_items("album", session)

    @patch("podcast_archiver.afdian.download_episode")
    def test_batch_continues_but_reports_failure(self, download):
        download.side_effect = [OSError("disk error"), "second.mp3"]
        episodes = [
            SimpleNamespace(title="first", podcast_title="album", audio_url="one"),
            SimpleNamespace(title="second", podcast_title="album", audio_url="two"),
        ]
        result = download_afdian_episodes(episodes, sleep_time=0)
        self.assertEqual(result, 1)
        self.assertEqual(download.call_count, 2)

    @patch("podcast_archiver.cli_handlers.download_afdian_episodes", return_value=1)
    @patch("podcast_archiver.cli_handlers.get_album_episodes", return_value=[])
    @patch("podcast_archiver.cli_handlers.create_session")
    def test_cli_propagates_batch_failure(self, *_):
        args = SimpleNamespace(output="downloads", offset=0, latest=None)
        result = handle_afdian_url("https://afdian.com/album/abcd", args)
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
