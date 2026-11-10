"""Where speech is in a rendered take, and spoken lines timed to it.

H3 is told when each shot starts but not when each line is spoken inside a shot, so a line is often heard earlier or
later than its time on the timeline. Subtitles (the merge's .srt) and the Timeline monitor's captions use these
functions to follow the speech in the take instead.

numpy only (imported when needed); ffmpeg decodes the take's sound to mono 16 kHz float samples.

1. segments(): the level in the speech band (300-3400 Hz) every 10 ms (25 ms Hann windows). Frames well above the
   take's quiet level (its 15th percentile; at least 6 dB above it, or 40 % of the way to the 97th percentile) whose
   energy lies mostly in the speech band are voiced. Gaps under 0.25 s are closed, runs under 0.2 s dropped, and a
   run of more than 1.5 s whose level hardly moves (a held note, a hum) is not speech. A take whose loud and quiet
   parts are less than 8 dB apart has no clear speech: no segments.
2. align(): the lines in their order are matched to the starts of the segments (each start used once, in order) by
   dynamic programming: a match costs how far it moves the line (at most WINDOW seconds); a line left unmatched
   costs MISS and keeps its planned time. A line ends where its speech ends (later segments that follow within
   0.7 s join it), before the next line starts.
"""

import os
import subprocess

RATE = 16000
WIN = 400     # 25 ms
HOP = 160     # 10 ms
STEP = HOP / RATE
WINDOW = 4.0  # how far (s) a line may move to meet the speech
MISS = 2.5    # the cost of leaving a line where it is


class SpeechError(RuntimeError):
    pass


def decode(path, ffmpeg, start=0.0, length=None):
    """Mono float32 samples at RATE of `path` from `start` (s), at most `length` s (all when None)."""
    import numpy as np
    args = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if start and start > 0:
        args += ["-ss", "{:.3f}".format(start)]
    if length is not None:
        args += ["-t", "{:.3f}".format(max(0.05, length))]
    args += ["-i", path, "-vn", "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"]
    r = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise SpeechError("ffmpeg could not read {}: {}".format(
            os.path.basename(path), r.stderr.decode(errors="replace").strip()[-400:]))
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def _levels(y):
    """(speech-band level in dB, share of the frame's energy in the speech band) per 10 ms frame."""
    import numpy as np
    if len(y) < WIN:
        return np.zeros(0), np.zeros(0)
    n = 1 + (len(y) - WIN) // HOP
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * np.hanning(WIN)[None, :]
    spec = np.abs(np.fft.rfft(frames, n=512, axis=1)) ** 2
    freqs = np.fft.rfftfreq(512, 1.0 / RATE)
    band = (freqs >= 300) & (freqs <= 3400)
    e_band = spec[:, band].sum(axis=1)
    e_all = spec[:, freqs >= 60].sum(axis=1) + 1e-12
    return 10 * np.log10(e_band + 1e-10), e_band / e_all


def segments(y):
    """[(start, end)] in seconds of the voiced parts of samples y (see the module notes)."""
    import numpy as np
    lvl, share = _levels(y)
    if not len(lvl):
        return []
    floor, top = float(np.percentile(lvl, 15)), float(np.percentile(lvl, 97))
    if top - floor < 8.0:
        return []
    thr = floor + max(6.0, 0.4 * (top - floor))
    on = (lvl > thr) & (share > 0.45)
    # a 5-frame majority vote takes out single-frame flicker
    k = np.convolve(on.astype(float), np.ones(5) / 5, mode="same") > 0.5
    runs, i = [], 0
    while i < len(k):
        if k[i]:
            j = i
            while j < len(k) and k[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    merged = []
    for a, b in runs:
        if merged and (a - merged[-1][1]) * STEP < 0.25:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    lin = 10 ** (lvl / 10)
    for a, b in merged:
        length = (b - a) * STEP
        if length < 0.2:
            continue
        if length > 1.5:
            part = lin[a:b]
            if float(np.std(part) / (np.mean(part) + 1e-12)) < 0.35:  # a held tone, not syllables
                continue
        out.append((round(a * STEP + WIN / RATE / 2, 3), round(b * STEP + WIN / RATE / 2, 3)))
    return out


def align(lines, segs, end_time=None):
    """Lines timed to the speech. lines: [{id, t, duration}] (seconds, any order); segs: segments(). Returns
    [{id, t, end, matched, planned}] in time order. Without segments every line keeps its planned time and length."""
    order = sorted(range(len(lines)), key=lambda i: float(lines[i]["t"]))
    ls = [lines[i] for i in order]
    planned = [float(x["t"]) for x in ls]
    durs = [max(0.4, float(x.get("duration") or 0) or 1.2) for x in ls]
    onsets = [a for a, _ in segs]
    n, m = len(ls), len(onsets)
    INF = float("inf")
    # best[j]: the least cost so far with onset j-1 the last one used (best[0]: none used yet)
    best = [0.0] + [INF] * m
    back = []
    for i in range(n):
        new = [INF] * (m + 1)
        choice = [None] * (m + 1)
        for j in range(m + 1):  # leave line i where it is
            if best[j] + MISS < new[j]:
                new[j], choice[j] = best[j] + MISS, ("miss", j)
        run_min, run_arg = INF, None
        for k in range(1, m + 1):  # match line i to onset k-1, after the last onset used (any j < k)
            if best[k - 1] < run_min:
                run_min, run_arg = best[k - 1], k - 1
            d = abs(onsets[k - 1] - planned[i])
            if d <= WINDOW and run_min + d < new[k]:
                new[k], choice[k] = run_min + d, ("match", run_arg)
        back.append(choice)
        best = new
    # the cheapest end state, then back to the start
    j = min(range(m + 1), key=lambda x: best[x])
    match = [None] * n
    for i in range(n - 1, -1, -1):
        kind, prev = back[i][j]
        if kind == "match":
            match[i] = j - 1
        j = prev
    starts = [onsets[match[i]] if match[i] is not None else planned[i] for i in range(n)]
    for i in range(1, n):  # keep the order (a line left where it was can land before a moved one)
        starts[i] = max(starts[i], starts[i - 1] + 0.2)
    out = []
    for i in range(n):
        nxt = starts[i + 1] if i + 1 < n else (end_time if end_time is not None else INF)
        if match[i] is not None:
            k = match[i]
            end = segs[k][1]
            limit = starts[i] + max(2 * durs[i], durs[i] + 3.0)
            for a, b in segs[k + 1:]:
                if a >= nxt - 0.05 or a - end > 0.7 or a > limit:
                    break
                end = b
        else:
            end = starts[i] + durs[i]
        end = max(end, starts[i] + 0.4)
        end = max(min(end, nxt - 0.05), starts[i] + 0.05)
        out.append({"id": ls[i].get("id", ""), "t": round(starts[i], 3), "end": round(end, 3),
                    "matched": match[i] is not None, "planned": planned[i]})
    return out


_CACHE = {}


def take_segments(path, ffmpeg):
    """segments() of a whole file, cached by its path, size and modification time."""
    st = os.stat(path)
    key = (path, st.st_size, st.st_mtime_ns)
    if key not in _CACHE:
        if len(_CACHE) > 128:
            _CACHE.clear()
        _CACHE[key] = segments(decode(path, ffmpeg))
    return _CACHE[key]


def timed_lines(path, ffmpeg, lines, start=0.0, end=None):
    """align() of `lines` (file time) to the speech of `path` between start and end (s)."""
    segs = [(max(a, start), b if end is None else min(b, end)) for a, b in take_segments(path, ffmpeg)
            if b > start and (end is None or a < end)]
    return align(lines, segs, end)
