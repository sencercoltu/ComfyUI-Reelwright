"""Beat markers for the soundtrack: tempo and beat times of an audio file.

numpy only (imported when needed); ffmpeg decodes the file to mono 22 050 Hz float samples.

1. Onset envelope: log-magnitude spectrogram (1024-sample Hann window, hop 512, about 43 frames a second), the
   positive spectral flux summed over 30 Hz - 8 kHz, with its local mean (half a second) taken off.
2. Tempo: autocorrelation of the (slightly smoothed) envelope over lags of 60-200 BPM, weighted towards 120 BPM (a
   log-normal prior, one octave wide); the peak is interpolated.
3. Beats: dynamic programming (Ellis 2007): a frame's score is its onset strength plus the best score one period
   earlier, less a penalty for intervals that stray from the period; backtracked from the best frame near the end.
   Weak beats in silent lead-ins and tails are dropped.
4. Downbeats: 4/4 is assumed: the phase (1 of 4) whose beats carry the most low-frequency (30-200 Hz) onset energy.

Results are cached as JSON by the file's content digest (see cached()).
"""

import json
import os
import subprocess

RATE = 22050
NFFT = 1024
HOP = 512
MIN_BPM, MAX_BPM, PRIOR_BPM = 60.0, 200.0, 120.0
CACHE_VERSION = 1


class BeatError(RuntimeError):
    pass


def decode(path, ffmpeg, max_seconds=900):
    """Mono float32 samples at RATE (at most max_seconds)."""
    import numpy as np
    r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-t", str(max_seconds), "-i", path, "-vn",
                        "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"], capture_output=True,
                       stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise BeatError("ffmpeg could not read {}: {}".format(
            os.path.basename(path), r.stderr.decode(errors="replace").strip()[-400:]))
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def _spectral_flux(y):
    """(full-band flux, low-band flux, RMS level) per frame; frame k is centred on sample k * HOP."""
    import numpy as np
    pad = NFFT // 2
    y = np.concatenate([np.zeros(pad, np.float32), y.astype(np.float32), np.zeros(pad, np.float32)])
    n = 1 + max(0, (len(y) - NFFT) // HOP)
    window = np.hanning(NFFT).astype(np.float32)
    freqs = np.fft.rfftfreq(NFFT, 1.0 / RATE)
    full = (freqs >= 30) & (freqs <= 8000)
    low = (freqs >= 30) & (freqs <= 200)
    flux, lflux, rms = np.zeros(n, np.float32), np.zeros(n, np.float32), np.zeros(n, np.float32)
    prev = None
    step = 2048  # frames per chunk, to keep memory small for long files
    for a in range(0, n, step):
        b = min(n, a + step)
        idx = np.arange(a, b)[:, None] * HOP + np.arange(NFFT)[None, :]
        frames = y[idx]
        rms[a:b] = np.sqrt(np.mean(frames * frames, axis=1))
        spec = np.log1p(100.0 * np.abs(np.fft.rfft(frames * window, axis=1))).astype(np.float32)
        before = np.vstack([np.zeros_like(spec[:1]) if prev is None else prev[None, :], spec[:-1]])
        d = np.maximum(0.0, spec - before)
        flux[a:b] = d[:, full].sum(axis=1)
        lflux[a:b] = d[:, low].sum(axis=1)
        prev = spec[-1]
    if n > 1:
        flux[0] = min(flux[0], flux[1:].max())
        lflux[0] = min(lflux[0], lflux[1:].max())
    return flux, lflux, rms


def _detrend(x, frames):
    import numpy as np
    if len(x) < 2:
        return x
    k = max(1, int(frames))
    kernel = np.ones(k, np.float32) / k
    mean = np.convolve(x, kernel, mode="same")
    out = np.maximum(0.0, x - mean)
    sd = out.std()
    return out / sd if sd > 0 else out


def onset_envelope(y):
    """(onset strength, low-band onset strength, RMS level), RATE / HOP frames a second."""
    flux, lflux, rms = _spectral_flux(y)
    fps = RATE / HOP
    return _detrend(flux, fps / 2), _detrend(lflux, fps / 2), rms


def estimate_tempo(env, fps):
    """BPM from the envelope's autocorrelation (0.0 when there is no periodicity)."""
    import numpy as np
    n = len(env)
    if n < 8 or not env.any():
        return 0.0
    # onsets are about one frame wide and a beat period is rarely a whole number of frames: smooth them first so
    # the autocorrelation does not favour twice the period
    g = np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2)
    x = np.convolve(env, g / g.sum(), mode="same")
    x = x - x.mean()
    f = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    if ac[0] <= 0:
        return 0.0
    ac = ac / ac[0]
    lo = max(1, int(np.floor(fps * 60.0 / MAX_BPM)))
    hi = min(n - 2, int(np.ceil(fps * 60.0 / MIN_BPM)))
    if hi <= lo:
        return 0.0
    lags = np.arange(lo, hi + 1)
    bpm = 60.0 * fps / lags
    prior = np.exp(-0.5 * (np.log2(bpm / PRIOR_BPM) / 1.0) ** 2)
    score = np.maximum(0.0, ac[lags]) * prior
    k = int(np.argmax(score))
    if score[k] <= 0:
        return 0.0
    lag = float(lags[k])
    if 0 < k < len(lags) - 1:  # parabolic interpolation around the peak
        a, b, c = score[k - 1], score[k], score[k + 1]
        den = a - 2 * b + c
        if den < 0:
            lag += 0.5 * (a - c) / den
    return 60.0 * fps / lag


def track_beats(env, fps, bpm, tightness=100.0, level=None):
    """Beat frames (dynamic programming, Ellis 2007). level: RMS per frame; beats at the ends that are more than
    20 dB under the beats' median level (silence, a noise floor) are dropped."""
    import numpy as np
    n = len(env)
    if bpm <= 0 or n < 2:
        return []
    period = 60.0 * fps / bpm
    dmin, dmax = max(1, int(round(period / 2))), max(2, int(round(2 * period)))
    offs = np.arange(dmin, dmax + 1)
    pen = -tightness * np.log(offs / period) ** 2
    # local score: the envelope smoothed by a Gaussian about a fifth of a period wide
    w = max(1, int(round(period / 8)))
    g = np.exp(-0.5 * (np.arange(-2 * w, 2 * w + 1) / w) ** 2)
    local = np.convolve(env, g / g.sum(), mode="same")
    score = local.astype(np.float64).copy()
    back = np.full(n, -1, dtype=np.int64)
    for t in range(dmin, n):
        cand_t = t - offs  # previous beat positions, nearest first
        valid = cand_t >= 0
        if not valid.any():
            continue
        c = score[cand_t[valid]] + pen[valid]
        k = int(np.argmax(c))
        if c[k] > 0:
            score[t] = local[t] + c[k]
            back[t] = cand_t[valid][k]
    # the last beat: the best-scoring local maximum in the final period
    tail = max(0, n - int(round(period)) - 1)
    end = tail + int(np.argmax(score[tail:]))
    beats = [end]
    while back[beats[-1]] >= 0:
        beats.append(int(back[beats[-1]]))
    beats.reverse()
    # drop weak beats in silent lead-ins and tails
    if beats:
        strong = local[beats]
        thr = 0.5 * np.sqrt(np.mean(np.asarray(strong) ** 2)) if len(strong) else 0
        if level is not None:
            near = np.array([level[max(0, f - 1):f + 2].max() for f in beats])
            quiet = near < 0.1 * np.median(near)
        else:
            quiet = np.zeros(len(beats), bool)
        a, b = 0, len(beats)
        while a < b and (strong[a] < thr or quiet[a]):
            a += 1
        while b > a and (strong[b - 1] < thr or quiet[b - 1]):
            b -= 1
        beats = beats[a:b]
    return beats


def downbeat_phase(beats, low_env, env, bar=4):
    """Index (0..bar-1) of the first downbeat among `beats`, by low-frequency onset energy (then all onsets)."""
    import numpy as np
    if len(beats) < bar:
        return 0
    def near(x, f):  # a beat can sit a frame or two off its onset peak
        return float(x[max(0, f - 2):f + 3].max())
    best, best_v = 0, None
    for ph in range(bar):
        sel = beats[ph::bar]
        v = (float(np.mean([near(low_env, f) for f in sel])), float(np.mean([near(env, f) for f in sel])))
        if best_v is None or v > best_v:
            best, best_v = ph, v
    return best


def analyze_samples(y):
    """{bpm, beats, downbeats, duration} for mono samples at RATE."""
    import numpy as np
    duration = len(y) / RATE
    out = {"bpm": 0.0, "beats": [], "downbeats": [], "duration": round(duration, 3)}
    if duration < 2.0 or not np.any(np.abs(y) > 1e-4):
        return out
    env, low, level = onset_envelope(y)
    fps = RATE / HOP
    bpm = estimate_tempo(env, fps)
    if bpm <= 0:
        return out
    frames = track_beats(env, fps, bpm, level=level)
    if len(frames) >= 2:  # the mean interval of the beats found (more exact than the autocorrelation peak)
        bpm = 60.0 * fps * (len(frames) - 1) / float(frames[-1] - frames[0])
    ph = downbeat_phase(frames, low, env)
    times = [round(f * HOP / RATE, 4) for f in frames]
    out.update(bpm=round(bpm, 2), beats=times, downbeats=times[ph::4])
    return out


def analyze(path, ffmpeg, max_seconds=900):
    return analyze_samples(decode(path, ffmpeg, max_seconds))


_MEMO = {}


def cached(path, ffmpeg, cache_dir, digest):
    """analyze(), remembered in memory and in <cache_dir>/<digest>.json (digest = the file's content hash, so a
    renamed or copied file is not analysed again)."""
    if digest in _MEMO:
        return _MEMO[digest]
    store = os.path.join(cache_dir, "{}.json".format(digest)) if cache_dir else None
    if store and os.path.isfile(store):
        try:
            with open(store, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("version") == CACHE_VERSION:
                data.pop("version", None)
                _MEMO[digest] = data
                return data
        except (OSError, ValueError):
            pass
    data = analyze(path, ffmpeg)
    if store:
        try:
            from .storage import write_json
            write_json(store, dict(data, version=CACHE_VERSION))
        except OSError:
            pass
    if len(_MEMO) > 64:
        _MEMO.clear()
    _MEMO[digest] = data
    return data
