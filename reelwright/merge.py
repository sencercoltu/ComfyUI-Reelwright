"""Join clips with ffmpeg: scene stitching (passes) and the final merge.

The filter graph is built in Python and run in one ffmpeg call. Clips are
normalised to one size, 24 fps and 48 kHz stereo, then joined pairwise with
concat (cuts) or xfade/acrossfade (crossfades, dips, continuation overlaps).
"""

import json
import os
import re
import shutil
import subprocess
import zipfile
from xml.sax.saxutils import escape

from . import spec

FPS = spec.FPS
AUDIO_RATE = 48000


class MergeError(RuntimeError):
    pass


def ffmpeg_bin():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # optional fallback shipped by some ComfyUI installs
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def ffprobe_bin():
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    ff = ffmpeg_bin()
    if ff:
        cand = os.path.join(os.path.dirname(ff), "ffprobe" + (".exe" if ff.endswith(".exe") else ""))
        if os.path.isfile(cand):
            return cand
    return None


def probe(path):
    """{duration, width, height, has_audio} via ffprobe, falling back to PyAV."""
    exe = ffprobe_bin()
    if exe:
        # [OLD 2026-11-02 v0.2.0->v0.2.1] a broken or half-written file raised CalledProcessError out of the node
        # out = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
        #                      capture_output=True, text=True, check=True).stdout
        # [/OLD]
        r = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise MergeError("ffprobe could not read {}: {}".format(os.path.basename(path), (r.stderr or "").strip()[-400:]))
        out = r.stdout
        info = json.loads(out)
        v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
        a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
        dur = float(info["format"].get("duration") or (v or a or {}).get("duration") or 0)
        return {"duration": dur, "width": int(v["width"]) if v else 0, "height": int(v["height"]) if v else 0,
                "has_video": v is not None, "has_audio": a is not None}
    import av
    with av.open(path) as c:
        v = c.streams.video[0] if c.streams.video else None
        dur = float(c.duration / 1e6) if c.duration else 0.0
        return {"duration": dur, "width": v.width if v else 0, "height": v.height if v else 0,
                "has_video": v is not None, "has_audio": bool(c.streams.audio)}


def _f(x):
    return "{:.6f}".format(max(0.0, x)).rstrip("0").rstrip(".") or "0"


def plan_timeline(segments):
    """Start time of every segment in the output and the total length."""
    starts, cur = [], 0.0
    for i, seg in enumerate(segments):
        length = seg["out"] - seg["in"]
        if i == 0 or seg["join"] == "cut":
            starts.append(cur)
            cur += length
        else:
            starts.append(cur - seg["dur"])
            cur += length - seg["dur"]
    return starts, cur


# [OLD 2026-11-03 v0.4.3->v0.5.0] def build_command(segments, out_path, width, height, codec="h264", crf=16, audio_fade_frames=6,
# [OLD 2026-11-03 v0.4.3->v0.5.0]                   loudness=None, score=None, chapters_file=None, ffmpeg=None):
def build_command(segments, out_path, width, height, codec="h264", crf=16, audio_fade_frames=6,
                  loudness=None, score=None, chapters_file=None, ffmpeg=None, tracks=None, scene_audio=None):
    """segments: [{path|None, in, out, has_audio, join: first|cut|xfade|dip, dur, gain: (r,g,b)|None}].
    A segment with path None is a dark slate of out-in seconds.
    added 2026-11-03 v0.5.0: a segment's vfade_in / vfade_out (seconds) fade its picture from / to black without
    overlapping its neighbours (a dip that keeps the timing). tracks: soundtrack files laid on the cut,
    [{path, start, in, length, volume_db, fade_in, fade_out, duck, loop}]; they are mixed unchanged (loudness
    normalisation only touches the scenes' sound). scene_audio: {"mix": bool, "volume_db": float}, the scenes' own
    sound under the tracks."""
    if not segments:
        raise MergeError("nothing to merge")
    ffmpeg = ffmpeg or ffmpeg_bin()
    if not ffmpeg:
        raise MergeError("ffmpeg was not found on PATH")
    starts, total = plan_timeline(segments)
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    graph = []
    n_in = 0
    fade = audio_fade_frames / FPS
    for k, seg in enumerate(segments):
        length = seg["out"] - seg["in"]
        if length <= 0:
            raise MergeError("segment {} has no length".format(k))
        if seg.get("path"):
            args += ["-i", seg["path"]]
            src = n_in
            n_in += 1
            v = ("[{s}:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,fps={fps},"
                 "scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
                 "setsar=1,format=yuv420p").format(s=src, a=_f(seg["in"]), b=_f(seg["out"]), fps=FPS, w=width, h=height)
            if seg.get("gain"):
                r, g, b = seg["gain"]
                v += ",colorchannelmixer=rr={:.4f}:gg={:.4f}:bb={:.4f}".format(r, g, b)
            v += _vfades(seg, length)  # added 2026-11-03 v0.5.0
            graph.append(v + "[v{}]".format(k))
            if seg.get("has_audio", True):
                a = ("[{s}:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,aresample={r},"
                     "aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={d}").format(
                    s=src, a=_f(seg["in"]), b=_f(seg["out"]), r=AUDIO_RATE, d=_f(length))
            else:
                a = "anullsrc=r={}:cl=stereo,atrim=duration={}".format(AUDIO_RATE, _f(length))
        else:
            graph.append("color=c=0x15171C:s={}x{}:r={}:d={},format=yuv420p,setsar=1[v{}]".format(
                width, height, FPS, _f(length), k))
            a = "anullsrc=r={}:cl=stereo,atrim=duration={}".format(AUDIO_RATE, _f(length))
        nxt = segments[k + 1]["join"] if k + 1 < len(segments) else None
        # [OLD 2026-11-02 v0.2.2->v0.3.0] one audio fade for every cut; a segment's "fade" (seconds) now sets the fade at the cut into it
        # if fade > 0 and k > 0 and seg["join"] == "cut":
        #     a += ",afade=t=in:d={}".format(_f(min(fade, length / 2)))
        # if fade > 0 and nxt == "cut":
        #     a += ",afade=t=out:st={}:d={}".format(_f(length - min(fade, length / 2)), _f(min(fade, length / 2)))
        # [/OLD]
        fin = seg.get("fade", fade)
        fout = segments[k + 1].get("fade", fade) if k + 1 < len(segments) else 0
        if fin > 0 and k > 0 and seg["join"] == "cut":
            a += ",afade=t=in:d={}".format(_f(min(fin, length / 2)))
        if fout > 0 and nxt == "cut":
            a += ",afade=t=out:st={}:d={}".format(_f(length - min(fout, length / 2)), _f(min(fout, length / 2)))
        graph.append(a + "[a{}]".format(k))

    vcur, acur = "v0", "a0"
    for k in range(1, len(segments)):
        seg = segments[k]
        if seg["join"] == "cut":
            graph.append("[{}][v{}]concat=n=2:v=1:a=0[vc{}]".format(vcur, k, k))
            graph.append("[{}][a{}]concat=n=2:v=0:a=1[ac{}]".format(acur, k, k))
        else:
            trans = "fadeblack" if seg["join"] == "dip" else "fade"
            graph.append("[{}][v{}]xfade=transition={}:duration={}:offset={}[vc{}]".format(
                vcur, k, trans, _f(seg["dur"]), _f(starts[k]), k))
            graph.append("[{}][a{}]acrossfade=d={}[ac{}]".format(acur, k, _f(seg["dur"]), k))
        vcur, acur = "vc{}".format(k), "ac{}".format(k)

    # added 2026-11-03 v0.5.0: soundtrack tracks. The scenes' sound (the bus built above) is normalised on its own,
    # set to the scene level and laid under the tracks; the tracks pass through as they are.
    tracks = [t for t in (tracks or []) if t.get("path") and t.get("length", 0) > 0]
    if tracks:
        sa = scene_audio or {"mix": True, "volume_db": 0.0}
        labels = []
        for j, t in enumerate(tracks):
            args += ["-i", t["path"]]
            labels.append(_track_filter(graph, n_in, j, t, total))
            n_in += 1
        scene_bus = None
        if sa.get("mix"):
            norm = "loudnorm=I={}:TP=-1.5:LRA=11,aresample={},".format(loudness, AUDIO_RATE) if loudness is not None else ""
            graph.append("[{}]{}volume={}dB,{}[scn]".format(acur, norm, float(sa.get("volume_db", 0.0)), _PIN))
            scene_bus = "scn"
            ducked = [k for k, t in enumerate(tracks) if t.get("duck")]
            if ducked:
                graph.append("[scn]asplit={}[scn0]{}".format(len(ducked) + 1, "".join(
                    "[side{}]".format(k) for k in ducked)))
                scene_bus = "scn0"
                for k in ducked:
                    graph.append("[{}][side{}]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=350[tdk{}]".format(
                        labels[k], k, k))
                    labels[k] = "tdk{}".format(k)
        else:
            graph.append("[{}]anullsink".format(acur))
        ins = ([scene_bus] if scene_bus else []) + labels
        if len(ins) == 1:
            graph.append("[{}]{}[aout]".format(ins[0], _PIN))
        else:
            # the tracks can overlap each other and the scenes: the sum is limited, never turned down
            graph.append("{}amix=inputs={}:duration=longest:normalize=0,alimiter=limit=0.98:level=0:latency=1,"
                         "atrim=duration={},{}[aout]".format("".join("[{}]".format(x) for x in ins), len(ins),
                                                             _f(total), _PIN))
        graph.append("[{}]null[vout]".format(vcur))
        return _finish(args, graph, n_in, chapters_file, codec, crf, total, out_path), starts, total
    if score and score.get("path"):
        args += ["-stream_loop", "-1", "-i", score["path"]]
        sidx = n_in
        n_in += 1
        graph.append("[{}:a]aresample={},aformat=sample_fmts=fltp:channel_layouts=stereo,atrim=duration={},volume={}dB[score]".format(
            sidx, AUDIO_RATE, _f(total), score.get("volume_db", -12.0)))
        if score.get("duck", True):
            graph.append("[{}]asplit=2[am1][am2]".format(acur))
            graph.append("[score][am2]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=350[ducked]")
            graph.append("[am1][ducked]amix=inputs=2:duration=first:normalize=0[amix]")
        else:
            graph.append("[{}][score]amix=inputs=2:duration=first:normalize=0[amix]".format(acur))
        acur = "amix"
    # [OLD 2026-11-02 v0.2.0->v0.2.1] newer ffmpeg builds (8.x) let the aac encoder take any channel layout, so
    # the link after this last aresample had no layout to pick: "Cannot select channel layout ... format_out"
    # if loudness is not None:
    #     graph.append("[{}]loudnorm=I={}:TP=-1.5:LRA=11,aresample={}[aout]".format(acur, loudness, AUDIO_RATE))
    # else:
    #     graph.append("[{}]anull[aout]".format(acur))
    # [/OLD]
    pin = "aformat=sample_fmts=fltp:sample_rates={}:channel_layouts=stereo".format(AUDIO_RATE)
    if loudness is not None:
        graph.append("[{}]loudnorm=I={}:TP=-1.5:LRA=11,aresample={},{}[aout]".format(acur, loudness, AUDIO_RATE, pin))
    else:
        graph.append("[{}]{}[aout]".format(acur, pin))
    graph.append("[{}]null[vout]".format(vcur))
    # added 2026-11-03 v0.5.0: the output options moved to _finish so the soundtrack branch shares them
    return _finish(args, graph, n_in, chapters_file, codec, crf, total, out_path), starts, total


_PIN = "aformat=sample_fmts=fltp:sample_rates={}:channel_layouts=stereo".format(AUDIO_RATE)


def _vfades(seg, length):
    """added 2026-11-03 v0.5.0: picture fades to / from black inside a segment."""
    out = ""
    fi, fo = min(seg.get("vfade_in", 0.0), length / 2), min(seg.get("vfade_out", 0.0), length / 2)
    if fi > 0:
        out += ",fade=t=in:st=0:d={}:color=black".format(_f(fi))
    if fo > 0:
        out += ",fade=t=out:st={}:d={}:color=black".format(_f(length - fo), _f(fo))
    return out


def _track_filter(graph, src, j, t, total):
    """added 2026-11-03 v0.5.0: one soundtrack track as a stereo stream exactly `total` seconds long."""
    start, src_in, length = float(t.get("start", 0.0)), float(t.get("in", 0.0)), float(t["length"])
    skip = 0.0
    if start < 0:  # the part before the film is not heard
        skip, start = -start, 0.0
    chain = "[{}:a]atrim=start={}:end={},asetpts=PTS-STARTPTS,aresample={},aformat=sample_fmts=fltp:" \
            "channel_layouts=stereo".format(src, _f(src_in), _f(src_in + length), AUDIO_RATE)
    play = max(0.0, total - start)
    if t.get("loop"):
        chain += ",aloop=loop=-1:size={},asetpts=N/SR/TB".format(max(1, int(round(length * AUDIO_RATE))))
        if skip:
            chain += ",atrim=start={},asetpts=PTS-STARTPTS".format(_f(skip))
        chain += ",atrim=duration={}".format(_f(play))
        heard = play
    else:
        if skip:
            chain += ",atrim=start={},asetpts=PTS-STARTPTS".format(_f(skip))
        heard = min(play, max(0.0, length - skip))
        chain += ",atrim=duration={}".format(_f(heard))
    if float(t.get("volume_db", 0.0)):
        chain += ",volume={}dB".format(float(t["volume_db"]))
    fi, fo = min(float(t.get("fade_in", 0.0)), heard / 2), min(float(t.get("fade_out", 0.0)), heard / 2)
    if fi > 0 and not skip:
        chain += ",afade=t=in:d={}".format(_f(fi))
    if fo > 0:
        chain += ",afade=t=out:st={}:d={}".format(_f(heard - fo), _f(fo))
    if start > 0:
        chain += ",adelay=delays={}:all=1,asetpts=N/SR/TB".format(int(round(start * 1000)))
    chain += ",apad,atrim=duration={}".format(_f(total))
    graph.append(chain + "[trk{}]".format(j))
    return "trk{}".format(j)


def _finish(args, graph, n_in, chapters_file, codec, crf, total, out_path):
    if chapters_file:
        args += ["-f", "ffmetadata", "-i", chapters_file]
    args += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]"]
    if chapters_file:
        args += ["-map_chapters", str(n_in)]
    if codec == "h265":
        args += ["-c:v", "libx265", "-tag:v", "hvc1"]
    else:
        args += ["-c:v", "libx264"]
    # [OLD 2026-11-02 v0.2.0->v0.2.1] no explicit channel count for the encoder
    # args += ["-preset", "medium", "-crf", str(int(crf)), "-pix_fmt", "yuv420p", "-r", str(FPS),
    #          "-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_RATE), "-movflags", "+faststart",
    #          "-t", _f(total), out_path]
    # [/OLD]
    args += ["-preset", "medium", "-crf", str(int(crf)), "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_RATE), "-ac", "2", "-movflags", "+faststart",
             "-t", _f(total), out_path]
    # [OLD 2026-11-03 v0.4.3->v0.5.0] return args, starts, total
    return args


# ---- soundtrack segments and waveforms (added 2026-11-03 v0.5.0) -------------------------------------------------

def segment_command(pieces, length, out_path, ffmpeg=None):
    """A WAV of `length` seconds with each piece {path, src_in, src_out, at} placed `at` seconds in, silence
    elsewhere. The pieces are not changed in level."""
    ffmpeg = ffmpeg or ffmpeg_bin()
    if not ffmpeg:
        raise MergeError("ffmpeg was not found on PATH")
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostats"]
    graph, labels = [], []
    for k, x in enumerate(pieces):
        args += ["-i", x["path"]]
        chain = "[{}:a]atrim=start={}:end={},asetpts=PTS-STARTPTS,aresample={},aformat=sample_fmts=fltp:" \
                "channel_layouts=stereo".format(k, _f(x["src_in"]), _f(x["src_out"]), AUDIO_RATE)
        if x.get("at", 0) > 0:
            # adelay leaves timestamps that make apad / atrim cut a second short: count samples instead
            chain += ",adelay=delays={}:all=1,asetpts=N/SR/TB".format(int(round(x["at"] * 1000)))
        graph.append(chain + "[p{}]".format(k))
        labels.append("[p{}]".format(k))
    if not labels:
        graph.append("anullsrc=r={}:cl=stereo,atrim=duration={}[out]".format(AUDIO_RATE, _f(length)))
    else:
        mix = "amix=inputs={}:duration=longest:normalize=0,".format(len(labels)) if len(labels) > 1 else "anull,"
        graph.append("{}{}apad,atrim=duration={}[out]".format("".join(labels), mix, _f(length)))
    return args + ["-filter_complex", ";".join(graph), "-map", "[out]", "-c:a", "pcm_s16le", "-ar", str(AUDIO_RATE),
                   "-ac", "2", out_path]


def render_segment(pieces, length, out_dir, file_digest, ffmpeg=None):
    """The pass's soundtrack WAV, made once: <out_dir>/<hash>.wav, keyed by the source files' bytes and the cuts."""
    import hashlib
    key = json.dumps([round(length, 4), [[file_digest(x["path"]), x["src_in"], x["src_out"], x["at"]] for x in pieces]])
    path = os.path.join(out_dir, hashlib.sha1(key.encode()).hexdigest()[:20] + ".wav")
    if os.path.isfile(path):
        return path
    os.makedirs(out_dir, exist_ok=True)
    tmp = path[:-4] + ".partial.wav"
    r = subprocess.run(segment_command(pieces, length, tmp, ffmpeg), capture_output=True, text=True)
    if r.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise MergeError("ffmpeg could not cut the soundtrack: " + (r.stderr or "").strip()[-800:])
    os.replace(tmp, path)
    return path


def waveform_peaks(path, per_second=50, ffmpeg=None, max_seconds=3600):
    """Peak levels 0-255, `per_second` values per second of the file (mono mix), for the timeline lanes."""
    ffmpeg = ffmpeg or ffmpeg_bin()
    if not ffmpeg:
        raise MergeError("ffmpeg was not found on PATH")
    rate = 8000
    r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-t", str(max_seconds), "-i", path, "-vn",
                        "-ac", "1", "-ar", str(rate), "-f", "u8", "-"], capture_output=True)
    if r.returncode != 0:
        raise MergeError("ffmpeg could not read {}: {}".format(os.path.basename(path),
                                                               r.stderr.decode(errors="replace").strip()[-400:]))
    raw = r.stdout
    step = max(1, rate // int(per_second))
    try:
        import numpy as np
        a = np.abs(np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128)
        n = -(-len(a) // step)
        a = np.pad(a, (0, n * step - len(a)))
        peaks = np.minimum(255, 2 * a.reshape(n, step).max(axis=1)).astype(np.uint8).tobytes()
    except ImportError:
        peaks = bytes(min(255, 2 * max(abs(b - 128) for b in raw[i:i + step])) for i in range(0, len(raw), step))
    return {"per_second": rate / step, "duration": len(raw) / rate, "peaks": peaks}


def run_ffmpeg(args, total=None, progress=None):
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        if progress and total and line.startswith("out_time_us="):
            try:
                progress(min(1.0, int(line.split("=", 1)[1]) / 1e6 / total))
            except ValueError:
                pass
    err = proc.stderr.read()
    if proc.wait() != 0:
        raise MergeError("ffmpeg failed: " + err.strip()[-2000:])


# [OLD 2026-11-02 v0.2.0->v0.2.1] ffmpeg wrote straight to the cut, so a failed merge left a broken
# <slug>_cut_vN.mp4 behind that the node then tried to play
# def join(segments, out_path, width, height, progress=None, **kw):
#     args, starts, total = build_command(segments, out_path, width, height, **kw)
#     run_ffmpeg(args, total, progress)
#     return starts, total
# [/OLD]
def join(segments, out_path, width, height, progress=None, **kw):
    """Render into <name>.partial.mp4 and rename only when ffmpeg succeeded."""
    root, ext = os.path.splitext(out_path)
    tmp = root + ".partial" + ext
    args, starts, total = build_command(segments, tmp, width, height, **kw)
    try:
        run_ffmpeg(args, total, progress)
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return starts, total


def mean_rgb(path, start, end, samples=5):
    ff = ffmpeg_bin()
    totals, count = [0.0, 0.0, 0.0], 0
    for i in range(samples):
        t = start + (end - start) * (i + 0.5) / samples
        raw = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-ss", _f(t), "-i", path, "-frames:v", "1",
                              "-vf", "scale=32:18,format=rgb24", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        if not raw:
            continue
        for c in range(3):
            totals[c] += sum(raw[c::3]) / (len(raw) / 3)
        count += 1
    return [x / count for x in totals] if count else None


def color_gains(segments, ref_index):
    """Per-channel gains that move every clip's mean colour to the reference clip's."""
    means = [mean_rgb(s["path"], s["in"], s["out"]) if s.get("path") else None for s in segments]
    ref = means[ref_index] if 0 <= ref_index < len(means) else None
    if not ref:
        return [None] * len(segments)
    gains = []
    for m in means:
        if not m:
            gains.append(None)
            continue
        gains.append(tuple(min(1.25, max(0.8, ref[c] / max(1.0, m[c]))) for c in range(3)))
    return gains


# ---- side files -------------------------------------------------------------

def _srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "{:02d}:{:02d}:{:02d},{:03d}".format(h, m, s, ms)


def subtitle_cues(entries):
    """entries: [{start, src_in, src_out, dialogue:[{t, speaker, text}]}] -> [(start, end, text)]."""
    cues = []
    for e in entries:
        lines = sorted(e.get("dialogue", []), key=lambda d: d["t"])
        scene_end = e["start"] + (e["src_out"] - e["src_in"])
        for i, d in enumerate(lines):
            if d["t"] < e["src_in"] or d["t"] >= e["src_out"] or not d["text"].strip():
                continue
            a = e["start"] + d["t"] - e["src_in"]
            b = a + max(1.2, 0.6 + 0.07 * len(d["text"]))
            if i + 1 < len(lines):
                b = min(b, e["start"] + lines[i + 1]["t"] - e["src_in"] - 0.05)
            b = min(b, scene_end)
            if b - a < 0.3:
                b = a + 0.3
            text = (d["speaker"] + ": " if d.get("speaker") else "") + d["text"].strip()
            cues.append((a, b, text))
    return cues


def write_srt(entries, path):
    cues = subtitle_cues(entries)
    with open(path, "w", encoding="utf-8") as f:
        for n, (a, b, text) in enumerate(cues, 1):
            f.write("{}\n{} --> {}\n{}\n\n".format(n, _srt_time(a), _srt_time(b), text))
    return len(cues)


def write_chapters(entries, total, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        for i, e in enumerate(entries):
            end = entries[i + 1]["start"] if i + 1 < len(entries) else total
            title = re.sub(r"[=;#\\\n]", " ", e["title"])
            f.write("[CHAPTER]\nTIMEBASE=1/1000\nSTART={}\nEND={}\ntitle={}\n".format(
                int(e["start"] * 1000), int(end * 1000), title))


def _rt(seconds):
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": float(FPS), "value": float(round(seconds * FPS))}


def write_otio(name, entries, path):
    """A/B-roll OpenTimelineIO: alternating tracks so crossfading clips can overlap."""
    def clip(e):
        return {"OTIO_SCHEMA": "Clip.2", "name": e["title"], "metadata": {"reelwright": {"scene_id": e["scene_id"]}},
                "source_range": {"OTIO_SCHEMA": "TimeRange.1", "start_time": _rt(e["src_in"]),
                                 "duration": _rt(e["src_out"] - e["src_in"])},
                "media_references": {"DEFAULT_MEDIA": {
                    "OTIO_SCHEMA": "ExternalReference.1", "target_url": "file://" + os.path.abspath(e["path"]).replace(os.sep, "/"),
                    "available_range": {"OTIO_SCHEMA": "TimeRange.1", "start_time": _rt(0), "duration": _rt(e["src_len"])}}},
                "active_media_reference_key": "DEFAULT_MEDIA", "effects": [], "markers": [], "enabled": True}

    def track(kind, label, sub):
        children, cur = [], 0.0
        for e in sub:
            if e["start"] > cur + 1e-6:
                children.append({"OTIO_SCHEMA": "Gap.1", "source_range": {"OTIO_SCHEMA": "TimeRange.1",
                                 "start_time": _rt(0), "duration": _rt(e["start"] - cur)}})
            children.append(clip(e))
            cur = e["start"] + e["src_out"] - e["src_in"]
        return {"OTIO_SCHEMA": "Track.1", "name": label, "kind": kind, "children": children,
                "effects": [], "markers": [], "enabled": True, "metadata": {}}

    tracks = []
    for kind in ("Video", "Audio"):
        for parity, label in ((0, "A"), (1, "B")):
            sub = [e for i, e in enumerate(entries) if i % 2 == parity]
            if sub:
                tracks.append(track(kind, kind + " " + label, sub))
    doc = {"OTIO_SCHEMA": "Timeline.1", "name": name, "global_start_time": _rt(0), "metadata": {},
           "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": tracks,
                      "effects": [], "markers": [], "enabled": True, "metadata": {}}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)


def _fr(seconds):
    return "{}/{}s".format(int(round(seconds * FPS)), FPS)


def write_fcpxml(name, entries, total, width, height, path):
    """Single-spine FCPXML 1.10; overlapping clips are cut where the next one starts."""
    res = ['<format id="r0" name="FFVideoFormat{}p{}" frameDuration="1/{}s" width="{}" height="{}"/>'.format(
        height, FPS, FPS, width, height)]
    clips = []
    for i, e in enumerate(entries):
        res.append('<asset id="r{}" name="{}" start="0s" duration="{}" hasVideo="1" hasAudio="1" format="r0">'
                   '<media-rep kind="original-media" src="{}"/></asset>'.format(
                       i + 1, escape(e["title"]), _fr(e["src_len"]),
                       escape("file://" + os.path.abspath(e["path"]).replace(os.sep, "/"))))
        end = entries[i + 1]["start"] if i + 1 < len(entries) else total
        clips.append('<asset-clip ref="r{}" name="{}" offset="{}" start="{}" duration="{}"/>'.format(
            i + 1, escape(e["title"]), _fr(e["start"]), _fr(e["src_in"]), _fr(end - e["start"])))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.10">\n'
           '<resources>\n{}\n</resources>\n<library><event name="{}"><project name="{}">'
           '<sequence format="r0" duration="{}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">'
           '<spine>\n{}\n</spine></sequence></project></event></library>\n</fcpxml>\n').format(
        "\n".join(res), escape(name), escape(name), _fr(total), "\n".join(clips))
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)


def write_bundle(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for arcname, src in files.items():
            if src and os.path.isfile(src):
                z.write(src, arcname)
