import os
import tempfile
import unittest
from unittest import mock

from tubeclipper import engine, ffmpegtool, formats, source


FORMATS = [
    {
        "format_id": "137", "url": "https://media.invalid/video",
        "vcodec": "avc1.640028", "acodec": "none", "height": 1080,
        "fps": 30, "tbr": 4500, "ext": "mp4",
        "http_headers": {"User-Agent": "TubeClipper test"},
    },
    {
        "format_id": "248", "url": "https://media.invalid/vp9",
        "vcodec": "vp9", "acodec": "none", "height": 1080,
        "fps": 60, "tbr": 3500, "ext": "webm",
    },
    {
        "format_id": "140", "url": "https://media.invalid/audio",
        "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129,
        "ext": "m4a",
    },
    {
        "format_id": "18", "url": "https://media.invalid/muxed",
        "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "height": 360,
        "fps": 30, "tbr": 700, "ext": "mp4",
    },
]


class TimecodeTests(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(source.parse_timecode("90"), 90)
        self.assertEqual(source.parse_timecode("1:30.5"), 90.5)
        self.assertEqual(source.parse_timecode("1:02:03.250"), 3723.25)
        self.assertIsNone(source.parse_timecode("one minute"))
        self.assertEqual(source.format_timecode(3723.25), "1:02:03.250")

    def test_link_normalisation(self):
        self.assertTrue(source.looks_like_url("dQw4w9WgXcQ"))
        self.assertEqual(source.normalise("dQw4w9WgXcQ"),
                         "https://www.youtube.com/watch?v=dQw4w9WgXcQ")


class SelectionTests(unittest.TestCase):
    def test_fast_mp4_prefers_h264_and_aac(self):
        selected = source.select({"formats": FORMATS}, max_height=1080,
                                 prefer_compatible=True)
        self.assertEqual(selected.video.format_id, "137")
        self.assertEqual(selected.audio.format_id, "140")

    def test_audio_only(self):
        selected = source.select({"formats": FORMATS}, audio_only=True,
                                 prefer_compatible=True)
        self.assertIsNone(selected.video)
        self.assertEqual(selected.audio.acodec, "mp4a.40.2")

    def test_preview_uses_best_progressive_under_cap(self):
        more = FORMATS + [{
            "format_id": "22", "url": "https://media.invalid/720",
            "vcodec": "avc1", "acodec": "aac", "height": 720,
            "tbr": 2000,
        }]
        selected = source.preview_stream({"formats": more})
        self.assertEqual(selected.video.height, 720)
        self.assertTrue(selected.progressive)
        self.assertEqual(selected.note, "")

    def test_preview_pairs_adaptive_video_and_audio(self):
        selected = source.preview_stream({"formats": FORMATS[:-1]})
        self.assertEqual(selected.video.format_id, "137")
        self.assertEqual(selected.audio.format_id, "140")
        self.assertFalse(selected.progressive)


class CommandTests(unittest.TestCase):
    def spec(self, key="mp4", fast=False):
        return engine.ExportSpec(
            url="https://youtube.invalid/watch?v=test",
            title="A title", video_id="test",
            clip=engine.Clip(12.5, 20.0, "Part one"),
            preset_key=key, quality=formats.Quality(height=1080, abr=192),
            fast=fast, out_dir=".", info={"formats": FORMATS},
        )

    def test_exact_mp4_maps_two_inputs_and_encodes(self):
        args, note, video, audio = engine.build_command(self.spec())
        self.assertEqual(args.count("-i"), 2)
        self.assertIn("libx264", args)
        self.assertIn("aac", args)
        self.assertIn("1:a:0", args)
        self.assertEqual((video, audio), ("vp9", "mp4a.40.2"))
        self.assertEqual(note, "")

    def test_fast_mp4_copies_compatible_streams(self):
        args, note, video, audio = engine.build_command(self.spec(fast=True))
        self.assertIn("copy", args)
        self.assertEqual(video, "avc1.640028")
        self.assertEqual(audio, "mp4a.40.2")
        self.assertEqual(note, "")

    def test_gif_uses_one_video_input_and_no_audio_map(self):
        args, _note, _video, _audio = engine.build_command(self.spec("gif"))
        self.assertEqual(args.count("-i"), 1)
        joined = " ".join(args)
        self.assertNotIn("a:0", joined)

    def test_required_download_cannot_fall_back_to_network(self):
        spec = self.spec()
        spec.require_local = True
        spec.local_path = os.path.join(tempfile.gettempdir(), "not-a-real-file.mp4")
        with self.assertRaisesRegex(RuntimeError, "did not complete"):
            engine.build_command(spec)

    def test_audio_command_has_no_video(self):
        args, _note, video, audio = engine.build_command(self.spec("mp3"))
        self.assertIn("-vn", args)
        self.assertEqual(video, "")
        self.assertEqual(audio, "mp4a.40.2")


class NamingAndCacheTests(unittest.TestCase):
    def test_windows_safe_names(self):
        self.assertEqual(engine.safe_name('  bad<>:"/\\|?* name. '), "bad_________ name")
        self.assertEqual(engine.safe_name("CON"), "CON_")

    def test_unique_path_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = os.path.join(tmp, "clip.mp4")
            open(first, "wb").close()
            self.assertEqual(engine.unique_path(tmp, "clip", ".mp4"),
                             os.path.join(tmp, "clip (2).mp4"))

    def test_audio_and_video_cache_names_do_not_collide(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("tubeclipper.engine.cache_dir", return_value=tmp):
            video = os.path.join(tmp, "abc.video.best.mkv")
            audio = os.path.join(tmp, "abc.audio.best.m4a")
            open(video, "wb").close()
            open(audio, "wb").close()
            self.assertEqual(engine.cached_download("abc", None), video)
            self.assertEqual(engine.cached_download("abc", None, True), audio)


class FormatTests(unittest.TestCase):
    def test_all_presets_have_extensions_and_builders(self):
        self.assertGreaterEqual(len(formats.PRESETS), 10)
        for preset in formats.PRESETS:
            self.assertTrue(preset.ext.startswith("."), preset.key)
            if preset.kind == "video":
                self.assertIsNotNone(preset.video, preset.key)
                self.assertIsNotNone(preset.audio, preset.key)

    def test_header_block_omits_range_and_ends_with_crlf(self):
        block = ffmpegtool.header_block({"User-Agent": "x", "Range": "bytes=1-"})
        self.assertEqual(block, "User-Agent: x\r\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
