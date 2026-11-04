"""Beat markers (added 2026-11-03 v0.6.0): tempo, beats and downbeats of synthetic click tracks."""

import os
import wave

import pytest

np = pytest.importorskip("numpy")

from reelwright import beats, merge  # noqa: E402

pytestmark = pytest.mark.skipif(merge.ffmpeg_bin() is None, reason="ffmpeg not installed")


def click_track(path, bpm, seconds=24.0, lead=0.5, rate=44100, bar=4, noise=0.0):
    """Clicks on every beat; the first beat of every bar also has a low thump. Returns the beat times."""
    rng = np.random.default_rng(1)
    y = np.zeros(int(seconds * rate), np.float32)
    times, t, k = [], lead, 0
    n = int(0.03 * rate)
    tt = np.arange(n) / rate
    while t < seconds - 0.1:
        i = int(round(t * rate))
        tone = 0.4 * np.sin(2 * np.pi * 1500 * tt) * np.exp(-tt * 60)
        if k % bar == 0:
            tone += 0.8 * np.sin(2 * np.pi * 70 * tt) * np.exp(-tt * 20)
        y[i:i + n] += tone[:len(y) - i]
        times.append(t)
        t += 60.0 / bpm
        k += 1
    y += noise * rng.standard_normal(len(y)).astype(np.float32)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    return np.array(times)


@pytest.mark.parametrize("bpm,lead", [(120, 0.73), (97, 0.2), (174, 1.1), (65, 0.5)])
def test_tempo_beats_and_downbeats(tmp_path, bpm, lead):
    path = str(tmp_path / "clicks.wav")
    truth = click_track(path, bpm, lead=lead, noise=0.005)
    r = beats.analyze(path, merge.ffmpeg_bin())
    assert r["bpm"] == pytest.approx(bpm, rel=0.015)
    got = np.array(r["beats"])
    assert len(got) == pytest.approx(len(truth), abs=1)
    assert max(np.min(np.abs(truth - x)) for x in got) < 0.045  # within about two frames of 24 fps
    down = np.array(r["downbeats"])
    assert len(down) >= 3
    assert max(np.min(np.abs(truth[::4] - x)) for x in down) < 0.045  # the accented beats
    assert r["duration"] == pytest.approx(24.0, abs=0.05)


def test_silence_and_short_files(tmp_path):
    path = str(tmp_path / "quiet.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * 22050 * 5)
    assert beats.analyze(path, merge.ffmpeg_bin())["beats"] == []
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio")
    with pytest.raises(beats.BeatError):
        beats.analyze(str(bad), merge.ffmpeg_bin())


def test_cached_by_content(tmp_path, monkeypatch):
    path = str(tmp_path / "c.wav")
    click_track(path, 120, seconds=8)
    cache_dir = str(tmp_path / "cache")
    first = beats.cached(path, merge.ffmpeg_bin(), cache_dir, "abc123")
    assert os.path.isfile(os.path.join(cache_dir, "abc123.json"))
    beats._MEMO.clear()
    monkeypatch.setattr(beats, "analyze", lambda *a, **k: pytest.fail("analysed again"))
    assert beats.cached(path, merge.ffmpeg_bin(), cache_dir, "abc123") == first


# ---- added 2026-11-03 v0.6.0 review --------------------------------------------------------------------------------

def _clicks(bpm, secs, lead=0.0, pad=0.0):
    r = beats.RATE
    y = np.zeros(int(secs * r), np.float32)
    t = lead
    while t < secs:
        k = int(t * r)
        y[k:k + 200] += 0.8 * np.hanning(400)[200:].astype(np.float32)[: len(y[k:k + 200])]
        t += 60.0 / bpm
    if pad:  # a sustained chord and a little noise from the very first sample
        tt = np.arange(len(y)) / r
        y += pad * (np.sin(2 * np.pi * 220 * tt) + 0.5 * np.sin(2 * np.pi * 330 * tt) +
                    0.3 * np.sin(2 * np.pi * 1500 * tt)).astype(np.float32)
        y += (np.random.RandomState(3).randn(len(y)) * pad * 0.2).astype(np.float32)
    return y


def test_a_beat_at_zero_is_kept_and_a_sound_at_zero_does_not_swamp_the_tempo():
    """Bug 8: frame 0's flux was measured against itself, so the beat at t=0 was lost (19 beats in 10 s at 120 BPM).
    Measured against silence it must not outweigh the real onsets: a song that starts with sound read 120 BPM as 60."""
    out = beats.analyze_samples(_clicks(120, 10.0))
    assert out["beats"][0] < 0.03 and len(out["beats"]) == 20 and out["bpm"] == pytest.approx(120, abs=1.5)
    out = beats.analyze_samples(_clicks(120, 10.0, lead=0.25, pad=0.3))
    assert out["bpm"] == pytest.approx(120, abs=3) and out["beats"][0] == pytest.approx(0.25, abs=0.05)
    out = beats.analyze_samples(_clicks(100, 12.0, lead=0.1, pad=0.6))
    assert out["bpm"] == pytest.approx(100, abs=3) and len(out["beats"]) >= 19
