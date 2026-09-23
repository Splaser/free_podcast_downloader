import unittest
from unittest.mock import patch

from podcast_archiver.afdian import (
    _assign_track_indexes,
    _extract_title_index,
    get_album_episodes,
)
from podcast_archiver.listen_notes import Episode


def episode(title, publish_time):
    ep = Episode(
        title=title,
        podcast_title="album",
        author="author",
        description="",
        audio_url="https://example.com/audio.mp3",
        cover_url="",
        source_url="",
    )
    ep.afdian_item = {"publish_time": publish_time}
    return ep


class AfdianOrderTests(unittest.TestCase):
    def test_publish_time_overrides_partial_title_numbering(self):
        # Four of eight titles have explicit numbers: the old 50% heuristic
        # moved the other four to the end and wrote incorrect track tags.
        episodes = [
            episode("opening", 100),
            episode("series001: first", 110),
            episode("series002上", 120),
            episode("series002下", 130),
            episode("series003: third", 140),
            episode("series004: fourth", 150),
            episode("special", 160),
            episode("series005: fifth", 170),
        ]
        self.assertEqual(
            sum(_extract_title_index(ep.title) is not None for ep in episodes), 4
        )

        ordered = _assign_track_indexes(list(reversed(episodes)))

        self.assertEqual(ordered, episodes)
        self.assertEqual([ep.track_index for ep in ordered], list(range(1, 9)))
        self.assertTrue(all(ep.track_total == 8 for ep in ordered))

    def test_latest_selection_keeps_full_album_track_numbers(self):
        items = [
            {"title": "series003", "publish_time": 300, "audio": "https://example.com/3.mp3"},
            {"title": "series001", "publish_time": 100, "audio": "https://example.com/1.mp3"},
            {"title": "series002上", "publish_time": 200, "audio": "https://example.com/2.mp3"},
        ]
        with patch("podcast_archiver.afdian.get_album_name", return_value="album"), patch(
            "podcast_archiver.afdian.iter_album_items", return_value=items
        ):
            all_episodes = get_album_episodes("album-id", session=object())
            latest = get_album_episodes("album-id", session=object(), latest=2)

        self.assertEqual([ep.track_index for ep in all_episodes], [1, 2, 3])
        self.assertEqual([ep.track_index for ep in latest], [3, 2])
        self.assertTrue(all(ep.track_total == 3 for ep in latest))


if __name__ == "__main__":
    unittest.main()
