"""Speech found in a take, and spoken lines timed to it (added 2026-11-06 v0.10.0): speech.segments / align /
timed_lines and assemble.speech_timed (the merge's subtitles)."""

import os
import shutil
import subprocess
import wave

import pytest

np = pytest.importorskip("numpy")

from reelwright import assemble, merge, speech  # noqa: E402

R = speech.RATE


def voiced(seconds, bursts, hum=True, seed=1):
    """Samples with a quiet noise floor, an optional held hum, and syllable-like bursts (4 Hz) at (start, end)."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * R)) / R
    y = 0.003 * rng.standard_normal(len(t))
    if hum:
        y += 0.01 * np.sin(2 * np.pi * 110 * t)
    for a, b in bursts:
        m = (t >= a) & (t < b)
        tt = t[m] - a
        env = (0.5 + 0.5 * np.sin(2 * np.pi * 4 * tt)) ** 2
        y[m] += 0.08 * env * sum(np.sin(2 * np.pi * f * tt) for f in (500, 900, 1400, 2300))
    return y.astype(np.float32)


def test_segments_find_the_bursts_and_skip_a_held_tone():
    segs = speech.segments(voiced(12, [(1.3, 3.0), (5.6, 7.9), (9.0, 10.2)]))
    assert len(segs) == 3
    for (a, b), (wa, wb) in zip(segs, [(1.3, 3.0), (5.6, 7.9), (9.0, 10.2)]):
        assert abs(a - wa) < 0.1 and abs(b - wb) < 0.15
    # a loud steady tone in the speech band is not speech
    t = np.arange(int(6 * R)) / R
    tone = (0.003 * np.random.default_rng(2).standard_normal(len(t))).astype(np.float32)
    tone[(t > 1) & (t < 5)] += (0.2 * np.sin(2 * np.pi * 800 * t[(t > 1) & (t < 5)])).astype(np.float32)
    assert speech.segments(tone) == []
    # silence or a flat level: no clear speech
    assert speech.segments(np.zeros(R * 3, dtype=np.float32)) == []
    assert speech.segments(np.zeros(10, dtype=np.float32)) == []


def test_align_moves_lines_to_their_speech_in_order():
    segs = [(1.3, 2.95), (5.6, 7.9), (9.0, 10.15)]
    lines = [{"id": "a", "t": 1.0, "duration": 1.6}, {"id": "b", "t": 4.0, "duration": 2.0},
             {"id": "c", "t": 8.7, "duration": 1.0}, {"id": "d", "t": 11.5, "duration": 0.8}]
    out = {x["id"]: x for x in speech.align(lines, segs, 12.0)}
    assert out["a"]["t"] == 1.3 and out["a"]["end"] == 2.95 and out["a"]["matched"]
    assert out["b"]["t"] == 5.6 and out["c"]["t"] == 9.0
    assert not out["d"]["matched"] and out["d"]["t"] == 11.5 and out["d"]["end"] == 11.95  # cut before the end
    # without speech: planned times and lengths; any input order comes back in time order
    plain = speech.align(list(reversed(lines)), [], 12.0)
    assert [x["id"] for x in plain] == ["a", "b", "c", "d"] and plain[1]["t"] == 4.0 and plain[1]["end"] == 6.0
    # an onset more than WINDOW seconds away is not taken; two lines never share one onset
    far = speech.align([{"id": "x", "t": 0.0, "duration": 1}], [(5.0, 6.0)], 10.0)
    assert not far[0]["matched"] and far[0]["t"] == 0.0
    two = speech.align([{"id": "x", "t": 1.0, "duration": 1}, {"id": "y", "t": 1.2, "duration": 1}], [(1.1, 2.0)], 10.0)
    assert sum(x["matched"] for x in two) == 1 and two[1]["t"] >= two[0]["t"] + 0.2
    # a line's speech goes on over a short pause, but stops before the next line
    joined = speech.align([{"id": "x", "t": 1.0, "duration": 3}, {"id": "y", "t": 6.0, "duration": 1}],
                          [(1.0, 2.0), (2.4, 3.6), (6.1, 7.0)], 10.0)
    assert joined[0]["end"] == 3.6 and joined[1]["t"] == 6.1


def _write_wav(path, y):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(R)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_timed_lines_and_merge_subtitles_follow_the_speech(tmp_path):
    wav = str(tmp_path / "speech.wav")
    _write_wav(wav, voiced(8, [(1.5, 2.6), (4.4, 6.0)]))
    take = str(tmp_path / "take.mp4")
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=64x64:r=24:d=8", "-i", wav, "-shortest", "-c:v", "libx264", "-c:a", "aac",
                    "-y", take], check=True, capture_output=True)
    ff = merge.ffmpeg_bin()
    out = speech.timed_lines(take, ff, [{"id": "1", "t": 1.0, "duration": 1.0}, {"id": "2", "t": 3.5, "duration": 1.5}])
    assert abs(out[0]["t"] - 1.5) < 0.12 and abs(out[1]["t"] - 4.4) < 0.12 and out[0]["matched"] and out[1]["matched"]
    assert speech.take_segments(take, ff) is speech.take_segments(take, ff)  # cached
    # the merge: entries in the take's time; a line keeps its words and speaker, gets the speech's time and length
    entries = [{"scene_id": "s", "title": "01 S", "path": take, "src_in": 0.0, "src_out": 8.0, "src_len": 8.0, "start": 10.0,
                "dialogue": [{"t": 1.0, "speaker": "Mara", "text": "Almost home.", "duration": None},
                             {"t": 3.5, "speaker": "Tom", "text": "Wait for me, please.", "duration": None}]}]
    timed = assemble.speech_timed(entries)
    assert timed[0]["dialogue"][0]["text"] == "Almost home." and abs(timed[0]["dialogue"][0]["t"] - 1.5) < 0.12
    cues = merge.subtitle_cues(timed)
    assert abs(cues[0][0] - 11.5) < 0.12 and abs(cues[1][0] - 14.4) < 0.12 and cues[1][2].startswith("Tom: ")
    assert entries[0]["dialogue"][0]["t"] == 1.0  # the input is not changed
    # a take that can't be read keeps the planned times
    bad = [dict(entries[0], path=str(tmp_path / "missing.mp4"))]
    assert assemble.speech_timed(bad)[0]["dialogue"][0]["t"] == 1.0
    os.remove(take)
