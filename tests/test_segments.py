"""Streams YouTube is still processing, served as numbered pieces."""

import os
import struct
import tempfile
import unittest

from tubeclipper import engine, segments


def box(kind, body):
    return struct.pack(">I4s", 8 + len(body), kind) + body


def piece(start_seconds, timescale=90000, payload=b"x"):
    """A minimal self-initialising fragment: moov/mdhd + moof/tfdt + mdat."""
    mdhd = box(b"mdhd", b"\0\0\0\0" + b"\0" * 8 + struct.pack(">II", timescale, 0))
    moov = box(b"moov", box(b"trak", box(b"mdia", mdhd)))
    tfdt = box(b"tfdt", b"\1\0\0\0" + struct.pack(">Q", int(start_seconds * timescale)))
    moof = box(b"moof", box(b"traf", tfdt))
    return box(b"ftyp", b"iso6") + moov + moof + box(b"mdat", payload)


class FakeSegmented(segments.Segmented):
    """Pieces held in memory: short ones at the start, a gap in the middle."""

    def __init__(self, starts):
        fmt = {"protocol": "http_dash_segments", "format_id": "136",
               "target_duration": 5,
               "fragments": [{"url": f"https://example.invalid/sq={i}"}
                             for i in range(len(starts))]}
        super().__init__(fmt)
        self.pieces = [piece(s, payload=bytes([i % 256])) for i, s in enumerate(starts)]
        self.requests = 0

    def _get(self, index, head_only=False, timeout=30):
        self.requests += 1
        return self.pieces[index]


def youtube_like(n=400, gap_at=200, gap=37.0):
    starts = [0.0, 1.333]
    for k in range(2, n):
        s = 5 * k - 3.533
        if k >= gap_at:
            s += gap
        starts.append(s)
    return starts


class PieceStart(unittest.TestCase):
    def test_reads_tfdt_over_timescale(self):
        self.assertAlmostEqual(segments.piece_start(piece(3596.4667)), 3596.4667, places=3)

    def test_audio_timescale(self):
        self.assertAlmostEqual(segments.piece_start(piece(12.5, timescale=44100)), 12.5)

    def test_garbage_is_none(self):
        self.assertIsNone(segments.piece_start(b"not an mp4 at all"))

    def test_detects_segmented_formats(self):
        self.assertTrue(segments.is_segmented(
            {"protocol": "http_dash_segments", "fragments": [{"url": "u"}]}))
        self.assertFalse(segments.is_segmented({"protocol": "https"}))


class IndexFor(unittest.TestCase):
    def setUp(self):
        self.starts = youtube_like()
        self.seg = FakeSegmented(self.starts)

    def expected(self, t):
        # Against the times as stored in the pieces (whole 1/90000 ticks).
        stored = [int(s * 90000) / 90000 for s in self.starts]
        return max(i for i, s in enumerate(stored) if s <= t)

    def test_finds_the_piece_everywhere(self):
        for t in (0, 0.5, 1.333, 1.4, 6.4, 6.467, 500, 994.0, 999.9, 1100, 1960.4):
            self.assertEqual(self.seg.index_for(t), self.expected(t), t)

    def test_few_requests_per_lookup(self):
        self.seg.index_for(1500)
        self.assertLessEqual(self.seg.requests, 6)

    def test_past_the_end_is_the_last_piece(self):
        self.assertEqual(self.seg.index_for(10 ** 6), len(self.starts) - 1)


class Fetch(unittest.TestCase):
    def test_pieces_are_written_in_order(self):
        seg = FakeSegmented(youtube_like(40, gap_at=1000))
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            path, offset = seg.fetch_span(
                20, 60, os.path.join(tmp, "out.mp4"),
                report=lambda f, t: seen.append(f))
            with open(path, "rb") as handle:
                data = handle.read()
        first, last = seg.index_for(20), seg.index_for(60 - 0.001)
        self.assertEqual(data, b"".join(seg.pieces[first:last + 1]))
        self.assertAlmostEqual(offset, seg.start(first))
        self.assertEqual(seen[-1], 1.0)

    def test_duration_excludes_the_piece_still_being_written(self):
        seg = FakeSegmented(youtube_like(40, gap_at=1000))
        seg.head_time = 10 ** 6
        self.assertAlmostEqual(seg.duration(), seg.start(39) + 5)


class ExportInput(unittest.TestCase):
    def test_seek_is_relative_to_the_fetched_copy(self):
        class S:
            segmented = object()
            url, headers = "https://example.invalid/v", {}
        clip = engine.Clip(3600.0, 3630.0)
        args = engine._input_for(S(), clip, lambda s, a, b: ("/tmp/v.mp4", 3596.4667))
        self.assertEqual(args[args.index("-ss") + 1], "3.533300")
        self.assertEqual(args[args.index("-i") + 1], "/tmp/v.mp4")

    def test_dry_run_leaves_the_address_alone(self):
        class S:
            segmented = object()
            url, headers = "https://example.invalid/v", {}
        args = engine._input_for(S(), engine.Clip(10.0, 20.0), None)
        self.assertEqual(args[args.index("-i") + 1], "https://example.invalid/v")


if __name__ == "__main__":
    unittest.main()
