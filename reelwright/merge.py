"""Join clips with ffmpeg: scene stitching (passes) and the final merge.

The filter graph is built in Python and run in one ffmpeg call. Clips are
normalised to one size, 24 fps and 48 kHz stereo, then joined pairwise with
concat (cuts) or xfade/acrossfade (crossfades, dips, continuation overlaps).
"""

import json
import logging  # added 2026-11-03 v0.6.0
import os
import re
import shutil
import subprocess
import tempfile  # added 2026-11-03 v0.6.0: the filter graph goes to ffmpeg in a file
import threading  # added 2026-11-03 v0.6.0: stderr / stdout are drained in threads
import zipfile
# [OLD 2026-11-03 v0.5.1->v0.6.0] from xml.sax.saxutils import escape  (escape() leaves " in attributes)
from xml.sax.saxutils import quoteattr

from . import spec

FPS = spec.FPS
AUDIO_RATE = 48000
log = logging.getLogger("reelwright")  # added 2026-11-03 v0.6.0


class MergeError(RuntimeError):
    pass


class MergeBusy(MergeError):
    """added 2026-11-03 v0.6.0: another merge of the same project is running."""


class MergeCancelled(MergeError):
    """added 2026-11-03 v0.6.0: the merge was cancelled; ffmpeg was stopped and partial files removed."""


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


# [OLD 2026-11-03 v0.6.0 review] exact seconds, while the merged file is whole frames: each segment was cut to
# round(length * 24) frames on its own, so the rounding added up (a picture 1.4 frames early after 8 scenes of
# 7.3 s) and a later crossfade, placed at the exact time, outran the shorter picture and dropped the rest of it
# def plan_timeline(segments):
#     """Start time of every segment in the output and the total length."""
#     starts, cur = [], 0.0
#     for i, seg in enumerate(segments):
#         length = seg["out"] - seg["in"]
#         if i == 0 or seg["join"] == "cut":
#             starts.append(cur)
#             cur += length
#         else:
#             starts.append(cur - seg["dur"])
#             cur += length - seg["dur"]
#     return starts, cur
# [/OLD]
def frame_index(seconds):
    """added 2026-11-03 v0.6.0 review: seconds to whole frames, half frames up (the side files' _frames rule)."""
    return _frames(seconds)


def frame_timeline(segments):
    """added 2026-11-03 v0.6.0 review: the cut on the 24 fps frame grid, the frames build_command really writes.
    Returns ([(start, frames, overlap)] per segment, total frames): start is the segment's first frame in the cut,
    frames how many frames it gives, overlap how many it shares with what came before (a crossfade or dip; 0 for a
    cut, and for a transition shorter than half a frame, which is then joined as a cut). The frames are cumulative: a
    segment ends at round(its exact end * 24), so the cut is round(exact total * 24) frames and rounding never adds
    up from segment to segment."""
    rows, cur, cur_f = [], 0.0, 0
    for i, seg in enumerate(segments):
        length = float(seg["out"]) - float(seg["in"])
        d = float(seg.get("dur") or 0.0) if i > 0 and seg["join"] != "cut" else 0.0
        d_f = min(_frames(d), cur_f) if d > 0 else 0
        start_f = cur_f - d_f
        cur += length - d
        end_f = max(start_f + max(1, d_f), _frames(cur))  # never empty, never shorter than its transition
        rows.append((start_f, end_f - start_f, d_f))
        cur_f = end_f
    return rows, cur_f


def plan_timeline(segments):
    """Start time of every segment in the output and the total length.
    added 2026-11-03 v0.6.0 review: on the frame grid (frame_timeline), the times the merged file really has."""
    rows, total_f = frame_timeline(segments)
    return [r[0] / FPS for r in rows], total_f / FPS


# [OLD 2026-11-03 v0.4.3->v0.5.0] def build_command(segments, out_path, width, height, codec="h264", crf=16, audio_fade_frames=6,
# [OLD 2026-11-03 v0.4.3->v0.5.0]                   loudness=None, score=None, chapters_file=None, ffmpeg=None):
# [OLD 2026-11-03 v0.5.1->v0.6.0] def build_command(segments, out_path, width, height, codec="h264", crf=16, audio_fade_frames=6,
# [OLD 2026-11-03 v0.5.1->v0.6.0]                   loudness=None, score=None, chapters_file=None, ffmpeg=None, tracks=None, scene_audio=None):
def build_command(segments, out_path, width, height, codec="h264", crf=16, audio_fade_frames=6,
                  loudness=None, score=None, chapters_file=None, ffmpeg=None, tracks=None, scene_audio=None,
                  preset="medium", stems=None):
    """segments: [{path|None, in, out, has_audio, join: first|cut|xfade|dip, dur, gain: (r,g,b)|None}].
    A segment with path None is a dark slate of out-in seconds.
    added 2026-11-03 v0.5.0: a segment's vfade_in / vfade_out (seconds) fade its picture from / to black without
    overlapping its neighbours (a dip that keeps the timing). tracks: soundtrack files laid on the cut,
    [{path, start, in, length, volume_db, fade_in, fade_out, duck, loop}]; they are mixed unchanged (loudness
    normalisation only touches the scenes' sound). scene_audio: {"mix": bool, "volume_db": float}, the scenes' own
    sound under the tracks.
    added 2026-11-03 v0.6.0: preset (x264/x265 preset; "veryfast" for drafts). stems: {"scenes": wav, "mix": wav,
    "tracks": [wav per track]} also writes the audio stems in the same ffmpeg run: the scenes' sound (after loudness
    normalisation, at the level it has in the mix; at 0 dB when it is not mixed), each track as heard in the cut
    (after ducking) and the final mix."""
    if not segments:
        raise MergeError("nothing to merge")
    ffmpeg = ffmpeg or ffmpeg_bin()
    if not ffmpeg:
        raise MergeError("ffmpeg was not found on PATH")
    starts, total = plan_timeline(segments)
    # added 2026-11-03 v0.6.0 review: every segment, picture and sound, is the whole number of frames frame_timeline
    # gives it (cumulative, so the cut is round(total * 24) frames); a transition under half a frame is a cut
    rows, _total_f = frame_timeline(segments)
    joins = ["first"] + [s["join"] if s["join"] != "cut" and rows[k][2] else "cut"
                         for k, s in enumerate(segments) if k > 0]
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    graph = []
    n_in = 0
    fade = audio_fade_frames / FPS
    for k, seg in enumerate(segments):
        length = seg["out"] - seg["in"]
        if length <= 0:
            raise MergeError("segment {} has no length".format(k))
        n_frames = rows[k][1]  # added 2026-11-03 v0.6.0 review
        length = n_frames / FPS  # added 2026-11-03 v0.6.0 review: its length on the frame grid, for picture and sound
        if seg.get("path"):
            args += ["-i", seg["path"]]
            src = n_in
            n_in += 1
            # [OLD 2026-11-03 v0.5.1->v0.6.0] a file a frame or two shorter than its segment shortened the cut, and every
            # later scene drifted against the soundtrack
            # v = ("[{s}:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,fps={fps},"
            #      "scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            #      "setsar=1,format=yuv420p").format(s=src, a=_f(seg["in"]), b=_f(seg["out"]), fps=FPS, w=width, h=height)
            # [/OLD]
            # added 2026-11-03 v0.6.0: exactly round(length * 24) frames (the last frame is held when the file is short)
            # [OLD 2026-11-03 v0.6.0 review] round(length * 24) per segment drifted from the planned times
            # v = ("[{s}:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,fps={fps},"
            #      "tpad=stop_mode=clone:stop_duration=1,trim=end_frame={n},"
            #      "scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            #      "setsar=1,format=yuv420p").format(s=src, a=_f(seg["in"]), b=_f(seg["out"]), fps=FPS, w=width, h=height,
            #                                        n=max(1, int(round(length * FPS))))
            # [/OLD]
            # added 2026-11-03 v0.6.0 review: the frame_timeline frame count, read from in .. in + that many frames
            v = ("[{s}:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,fps={fps},"
                 "tpad=stop_mode=clone:stop_duration=1,trim=end_frame={n},"
                 "scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
                 "setsar=1,format=yuv420p").format(s=src, a=_f(seg["in"]), b=_f(seg["in"] + length), fps=FPS, w=width,
                                                   h=height, n=n_frames)
            if seg.get("gain"):
                r, g, b = seg["gain"]
                v += ",colorchannelmixer=rr={:.4f}:gg={:.4f}:bb={:.4f}".format(r, g, b)
            v += _vfades(seg, length)  # added 2026-11-03 v0.5.0
            graph.append(v + "[v{}]".format(k))
            if seg.get("has_audio", True):
                # [OLD 2026-11-03 v0.6.0 review] a = ("[{s}:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,aresample={r},"
                # [OLD 2026-11-03 v0.6.0 review]      "aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={d}").format(
                # [OLD 2026-11-03 v0.6.0 review]     s=src, a=_f(seg["in"]), b=_f(seg["out"]), r=AUDIO_RATE, d=_f(length))
                # added 2026-11-03 v0.6.0 review: the sound of the same frames (length is on the frame grid now)
                a = ("[{s}:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,aresample={r},"
                     "aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={d}").format(
                    s=src, a=_f(seg["in"]), b=_f(seg["in"] + length), r=AUDIO_RATE, d=_f(length))
            else:
                a = "anullsrc=r={}:cl=stereo,atrim=duration={}".format(AUDIO_RATE, _f(length))
        else:
            # [OLD 2026-11-03 v0.6.0 review] a slate of 0.6 frames (d=0.025) still gave a whole dark frame
            # graph.append("color=c=0x15171C:s={}x{}:r={}:d={},format=yuv420p,setsar=1[v{}]".format(
            #     width, height, FPS, _f(length), k))
            # [/OLD]
            # added 2026-11-03 v0.6.0 review: exactly its frame_timeline frames
            graph.append("color=c=0x15171C:s={}x{}:r={}:d={},trim=end_frame={},format=yuv420p,setsar=1[v{}]".format(
                width, height, FPS, _f((n_frames + 0.5) / FPS), n_frames, k))
            a = "anullsrc=r={}:cl=stereo,atrim=duration={}".format(AUDIO_RATE, _f(length))
        # [OLD 2026-11-03 v0.6.0 review] nxt = segments[k + 1]["join"] if k + 1 < len(segments) else None
        nxt = joins[k + 1] if k + 1 < len(segments) else None  # added 2026-11-03 v0.6.0 review: a 0-frame xfade is a cut
        # [OLD 2026-11-02 v0.2.2->v0.3.0] one audio fade for every cut; a segment's "fade" (seconds) now sets the fade at the cut into it
        # if fade > 0 and k > 0 and seg["join"] == "cut":
        #     a += ",afade=t=in:d={}".format(_f(min(fade, length / 2)))
        # if fade > 0 and nxt == "cut":
        #     a += ",afade=t=out:st={}:d={}".format(_f(length - min(fade, length / 2)), _f(min(fade, length / 2)))
        # [/OLD]
        fin = seg.get("fade", fade)
        fout = segments[k + 1].get("fade", fade) if k + 1 < len(segments) else 0
        # [OLD 2026-11-03 v0.6.0 review] if fin > 0 and k > 0 and seg["join"] == "cut":
        if fin > 0 and k > 0 and joins[k] == "cut":  # added 2026-11-03 v0.6.0 review: a 0-frame xfade is a cut
            a += ",afade=t=in:d={}".format(_f(min(fin, length / 2)))
        if fout > 0 and nxt == "cut":
            a += ",afade=t=out:st={}:d={}".format(_f(length - min(fout, length / 2)), _f(min(fout, length / 2)))
        graph.append(a + "[a{}]".format(k))

    vcur, acur = "v0", "a0"
    for k in range(1, len(segments)):
        seg = segments[k]
        # [OLD 2026-11-03 v0.6.0 review] if seg["join"] == "cut":
        if joins[k] == "cut":  # added 2026-11-03 v0.6.0 review: a transition under half a frame is a cut
            # [OLD 2026-11-03 v0.5.1->v0.6.0] concat outputs timebase 1/1000000 and a later xfade needs 1/24
            # graph.append("[{}][v{}]concat=n=2:v=1:a=0[vc{}]".format(vcur, k, k))
            # [/OLD]
            graph.append("[{}][v{}]concat=n=2:v=1:a=0,settb=expr=1/{}[vc{}]".format(vcur, k, FPS, k))
            graph.append("[{}][a{}]concat=n=2:v=0:a=1[ac{}]".format(acur, k, k))
        else:
            trans = "fadeblack" if seg["join"] == "dip" else "fade"
            # [OLD 2026-11-03 v0.6.0 review] exact seconds; the picture before it could be shorter than offset + duration
            # graph.append("[{}][v{}]xfade=transition={}:duration={}:offset={}[vc{}]".format(
            #     vcur, k, trans, _f(seg["dur"]), _f(starts[k]), k))
            # graph.append("[{}][a{}]acrossfade=d={}[ac{}]".format(acur, k, _f(seg["dur"]), k))
            # [/OLD]
            # added 2026-11-03 v0.6.0 review: whole frames from frame_timeline; the picture before is exactly
            # offset + duration frames, so the crossfade keeps every frame of both
            dur = rows[k][2] / FPS
            graph.append("[{}][v{}]xfade=transition={}:duration={}:offset={}[vc{}]".format(
                vcur, k, trans, _f(dur), _f(rows[k][0] / FPS), k))
            graph.append("[{}][a{}]acrossfade=d={}[ac{}]".format(acur, k, _f(dur), k))
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
        stem_out = []  # added 2026-11-03 v0.6.0: (label, wav path) of each stem
        if sa.get("mix"):
            # [OLD 2026-11-03 v0.6.0 review] norm = "loudnorm=I={}:TP=-1.5:LRA=11,aresample={},".format(loudness, AUDIO_RATE) if loudness is not None else ""
            norm = _loudnorm(loudness, total) + "," if loudness is not None else ""  # added 2026-11-03 v0.6.0 review
            graph.append("[{}]{}volume={}dB,{}[scn]".format(acur, norm, float(sa.get("volume_db", 0.0)), _PIN))
            scene_bus = "scn"
            if stems and stems.get("scenes"):  # added 2026-11-03 v0.6.0
                graph.append("[scn]asplit=2[scnm][stem_scenes]")
                scene_bus = "scnm"
                stem_out.append(("stem_scenes", stems["scenes"]))
            ducked = [k for k, t in enumerate(tracks) if t.get("duck")]
            if ducked:
                # [OLD 2026-11-03 v0.5.1->v0.6.0] graph.append("[scn]asplit={}[scn0]{}".format(len(ducked) + 1, "".join(  (the bus may be split for a stem first)
                graph.append("[{}]asplit={}[scn0]{}".format(scene_bus, len(ducked) + 1, "".join(
                    "[side{}]".format(k) for k in ducked)))
                scene_bus = "scn0"
                for k in ducked:
                    graph.append("[{}][side{}]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=350[tdk{}]".format(
                        labels[k], k, k))
                    labels[k] = "tdk{}".format(k)
        # [OLD 2026-11-03 v0.5.1->v0.6.0] else:
        # [OLD 2026-11-03 v0.5.1->v0.6.0]     graph.append("[{}]anullsink".format(acur))
        elif stems and stems.get("scenes"):  # added 2026-11-03 v0.6.0: not in the mix, still a stem (normalised, 0 dB)
            # [OLD 2026-11-03 v0.6.0 review] norm = "loudnorm=I={}:TP=-1.5:LRA=11,aresample={},".format(loudness, AUDIO_RATE) if loudness is not None else ""
            norm = _loudnorm(loudness, total) + "," if loudness is not None else ""  # added 2026-11-03 v0.6.0 review
            graph.append("[{}]{}{}[stem_scenes]".format(acur, norm, _PIN))
            stem_out.append(("stem_scenes", stems["scenes"]))
        else:
            graph.append("[{}]anullsink".format(acur))
        for k, path in enumerate((stems or {}).get("tracks") or []):  # added 2026-11-03 v0.6.0: each track as heard
            if path and k < len(labels):
                graph.append("[{}]asplit=2[trm{}][stem_t{}]".format(labels[k], k, k))
                labels[k] = "trm{}".format(k)
                stem_out.append(("stem_t{}".format(k), path))
        ins = ([scene_bus] if scene_bus else []) + labels
        if len(ins) == 1:
            graph.append("[{}]{}[aout]".format(ins[0], _PIN))
        else:
            # the tracks can overlap each other and the scenes: the sum is limited, never turned down
            graph.append("{}amix=inputs={}:duration=longest:normalize=0,alimiter=limit=0.98:level=0:latency=1,"
                         "atrim=duration={},{}[aout]".format("".join("[{}]".format(x) for x in ins), len(ins),
                                                             _f(total), _PIN))
        graph.append("[{}]null[vout]".format(vcur))
        # [OLD 2026-11-03 v0.5.1->v0.6.0] return _finish(args, graph, n_in, chapters_file, codec, crf, total, out_path), starts, total
        return _finish(args, graph, n_in, chapters_file, codec, crf, total, out_path, preset,
                       _mix_stem(graph, stems, stem_out)), starts, total
    stem_out = []  # added 2026-11-03 v0.6.0
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
        # [OLD 2026-11-03 v0.6.0 review] graph.append("[{}]loudnorm=I={}:TP=-1.5:LRA=11,aresample={},{}[aout]".format(acur, loudness, AUDIO_RATE, pin))
        graph.append("[{}]{},{}[aout]".format(acur, _loudnorm(loudness, total), pin))  # added 2026-11-03 v0.6.0 review
    else:
        graph.append("[{}]{}[aout]".format(acur, pin))
    graph.append("[{}]null[vout]".format(vcur))
    # added 2026-11-03 v0.5.0: the output options moved to _finish so the soundtrack branch shares them
    # [OLD 2026-11-03 v0.5.1->v0.6.0] return _finish(args, graph, n_in, chapters_file, codec, crf, total, out_path), starts, total
    # added 2026-11-03 v0.6.0: without tracks the scenes' sound is the mix, so scenes.wav copies it
    return _finish(args, graph, n_in, chapters_file, codec, crf, total, out_path, preset,
                   _mix_stem(graph, stems, stem_out, scenes_from_mix=True)), starts, total


def _mix_stem(graph, stems, stem_out, scenes_from_mix=False):
    """added 2026-11-03 v0.6.0: split the final audio [aout] into the encoder's input [aenc] and the stems that copy
    it (mix.wav, and scenes.wav when there are no tracks). Returns every [(label, wav path)] for _finish."""
    if not stems:
        return []
    copies = []
    if scenes_from_mix and stems.get("scenes"):
        copies.append(("stem_scenes", stems["scenes"]))
    if stems.get("mix"):
        copies.append(("stem_mix", stems["mix"]))
    if not copies:
        return list(stem_out)
    graph.append("[aout]asplit={}[aenc]{}".format(len(copies) + 1, "".join("[{}]".format(lab) for lab, _ in copies)))
    return list(stem_out) + copies


_PIN = "aformat=sample_fmts=fltp:sample_rates={}:channel_layouts=stereo".format(AUDIO_RATE)


def _loudnorm(loudness, total):
    """added 2026-11-03 v0.6.0 review: loudnorm on under 3 s of silence gives NaN samples and the AAC encoder stops
    ("Input contains (near) NaN", nothing written): the sound is padded with silence to 3 s for it and cut back to
    the cut's length. A cut of 3 s or more is not changed."""
    return "apad=whole_dur=3,loudnorm=I={}:TP=-1.5:LRA=11,aresample={},atrim=duration={}".format(
        loudness, AUDIO_RATE, _f(total))


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


# [OLD 2026-11-03 v0.5.1->v0.6.0] def _finish(args, graph, n_in, chapters_file, codec, crf, total, out_path):
def _finish(args, graph, n_in, chapters_file, codec, crf, total, out_path, preset="medium", stem_out=()):
    if chapters_file:
        args += ["-f", "ffmetadata", "-i", chapters_file]
    # [OLD 2026-11-03 v0.5.1->v0.6.0] args += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]"]
    # added 2026-11-03 v0.6.0: with stems the final audio is split; the encoder takes [aenc]
    aenc = "[aenc]" if any("[aenc]" in x for x in graph) else "[aout]"
    args += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", aenc]
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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] args += ["-preset", "medium", "-crf", str(int(crf)), "-pix_fmt", "yuv420p", "-r", str(FPS),
    args += ["-preset", str(preset or "medium"), "-crf", str(int(crf)), "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_RATE), "-ac", "2", "-movflags", "+faststart",
             "-t", _f(total), out_path]
    for label, path in stem_out:  # added 2026-11-03 v0.6.0: audio stems as 48 kHz stereo WAVs, same length as the cut
        args += ["-map", "[{}]".format(label), "-c:a", "pcm_s16le", "-ar", str(AUDIO_RATE), "-ac", "2",
                 "-t", _f(total), path]
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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] two makers of the same segment at once (a render and the editor's excerpt)
    # shared one temp name; the graph went on the command line
    # tmp = path[:-4] + ".partial.wav"
    # r = subprocess.run(segment_command(pieces, length, tmp, ffmpeg), capture_output=True, text=True)
    # if r.returncode != 0:
    #     if os.path.exists(tmp):
    #         os.remove(tmp)
    #     raise MergeError("ffmpeg could not cut the soundtrack: " + (r.stderr or "").strip()[-800:])
    # [/OLD]
    tmp = "{}.{}.{}.partial.wav".format(path[:-4], os.getpid(), threading.get_ident())
    try:
        run_ffmpeg(segment_command(pieces, length, tmp, ffmpeg))
        os.replace(tmp, path)
    except MergeCancelled:
        raise
    except MergeError as e:
        raise MergeError("ffmpeg could not cut the soundtrack: " + str(e)[-800:])
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
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


# [OLD 2026-11-03 v0.5.1->v0.6.0] stdout was read to the end before stderr, so more than a pipe's worth of stderr
# (64 KB) hung ffmpeg and the node for ever; it could not be stopped; the whole graph was on the command line
# (Windows allows 32 767 characters: about 55 scenes)
# def run_ffmpeg(args, total=None, progress=None):
#     proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
#     for line in proc.stdout:
#         if progress and total and line.startswith("out_time_us="):
#             try:
#                 progress(min(1.0, int(line.split("=", 1)[1]) / 1e6 / total))
#             except ValueError:
#                 pass
#     err = proc.stderr.read()
#     if proc.wait() != 0:
#         raise MergeError("ffmpeg failed: " + err.strip()[-2000:])
# [/OLD]
_SCRIPT_FLAG = {}  # added 2026-11-03 v0.6.0: ffmpeg path -> how it reads a filter graph from a file
STDERR_KEEP = 256 * 1024


def script_flag(ffmpeg):
    """added 2026-11-03 v0.6.0: the option that reads a filter graph from a file: "-filter_complex_script" (ffmpeg
    6 and older; deprecated later), "-/filter_complex" (ffmpeg 7+), or None (keep the graph on the command line).
    Found once per ffmpeg by trying a tiny graph."""
    if ffmpeg in _SCRIPT_FLAG:
        return _SCRIPT_FLAG[ffmpeg]
    found = None
    fd, path = tempfile.mkstemp(prefix="rw_probe_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("anullsrc=r=8000:cl=mono,atrim=duration=0.01[a]")
        for flag in ("-filter_complex_script", "-/filter_complex"):
            try:
                r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", flag, path, "-map", "[a]", "-f", "null",
                                    "-"], capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                continue
            if r.returncode == 0:
                found = flag
                break
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    _SCRIPT_FLAG[ffmpeg] = found
    return found


def _graph_to_file(args):
    """added 2026-11-03 v0.6.0: (args, script path or None): "-filter_complex <graph>" becomes the file form."""
    if "-filter_complex" not in args:
        return list(args), None
    k = args.index("-filter_complex")
    flag = script_flag(args[0])
    if not flag:
        return list(args), None
    fd, path = tempfile.mkstemp(prefix="rw_graph_", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(args[k + 1])
    return list(args[:k]) + [flag, path] + list(args[k + 2:]), path


def run_ffmpeg(args, total=None, progress=None, cancel=None):
    """Run ffmpeg (added 2026-11-03 v0.6.0: rewritten). stdout (-progress) and stderr are read by threads, so a
    chatty ffmpeg never blocks; the filter graph is passed in a file. progress(fraction) is called on this thread.
    cancel: a callable polled about 5 times a second; when it returns True, ffmpeg is killed and MergeCancelled
    raised; when it raises (e.g. ComfyUI's interrupt check), ffmpeg is killed and that exception goes on.
    Returns the tail of stderr."""
    args, script = _graph_to_file(args)
    err, latest = [], [None]
    err_size = [0]

    def drain_err(pipe):
        for chunk in iter(lambda: pipe.read(8192), b""):
            err.append(chunk)
            err_size[0] += len(chunk)
            while err_size[0] > STDERR_KEEP and len(err) > 1:
                err_size[0] -= len(err.pop(0))

    def drain_out(pipe):
        for line in iter(pipe.readline, b""):
            if line.startswith(b"out_time_us="):
                try:
                    latest[0] = int(line.split(b"=", 1)[1])
                except ValueError:
                    pass

    proc = None
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        threads = [threading.Thread(target=drain_out, args=(proc.stdout,), daemon=True),
                   threading.Thread(target=drain_err, args=(proc.stderr,), daemon=True)]
        for t in threads:
            t.start()
        sent = None
        while True:
            try:
                rc = proc.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                pass
            if progress and total and latest[0] is not None and latest[0] != sent:
                sent = latest[0]
                progress(max(0.0, min(1.0, sent / 1e6 / total)))
            if cancel and cancel():
                _kill(proc)
                raise MergeCancelled("cancelled")
        for t in threads:
            t.join(timeout=5)
        text = b"".join(err).decode("utf-8", errors="replace")
        if rc != 0:
            raise MergeError("ffmpeg failed: " + text.strip()[-2000:])
        if progress and total:
            progress(1.0)
        return text
    finally:
        if proc is not None and proc.poll() is None:  # an exception (cancel, interrupt, Ctrl+C) left it running
            _kill(proc)
        if script:
            try:
                os.remove(script)
            except OSError:
                pass


def _kill(proc):
    """added 2026-11-03 v0.6.0"""
    try:
        proc.kill()
        proc.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


_LOUD_RE = {"integrated": re.compile(r"I:\s+(-?[\d.]+|-inf)\s+LUFS"),
            "lra": re.compile(r"LRA:\s+(-?[\d.]+|-inf)\s+LU\b"),
            "true_peak": re.compile(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS")}


def measure_loudness(path, ffmpeg=None, cancel=None):
    """added 2026-11-03 v0.6.0: EBU R128 of a file's sound: {integrated (LUFS), lra (LU), true_peak (dBTP)};
    a value is None when the sound is silent (-inf)."""
    ffmpeg = ffmpeg or ffmpeg_bin()
    if not ffmpeg:
        raise MergeError("ffmpeg was not found on PATH")
    text = run_ffmpeg([ffmpeg, "-hide_banner", "-nostats", "-loglevel", "info", "-i", path, "-vn",
                       "-af", "ebur128=peak=true", "-f", "null", "-"], cancel=cancel)
    summary = text[text.rfind("Summary:"):] if "Summary:" in text else text
    out = {}
    for k, rx in _LOUD_RE.items():
        m = rx.search(summary)
        out[k] = float(m.group(1)) if m and m.group(1) != "-inf" else None
    return out


# [OLD 2026-11-02 v0.2.0->v0.2.1] ffmpeg wrote straight to the cut, so a failed merge left a broken
# <slug>_cut_vN.mp4 behind that the node then tried to play
# def join(segments, out_path, width, height, progress=None, **kw):
#     args, starts, total = build_command(segments, out_path, width, height, **kw)
#     run_ffmpeg(args, total, progress)
#     return starts, total
# [/OLD]
# [OLD 2026-11-03 v0.5.1->v0.6.0] def join(segments, out_path, width, height, progress=None, **kw):
def join(segments, out_path, width, height, progress=None, cancel=None, **kw):
    """Render into <name>.partial.mp4 and rename only when ffmpeg succeeded. cancel: see run_ffmpeg (added
    2026-11-03 v0.6.0)."""
    root, ext = os.path.splitext(out_path)
    tmp = root + ".partial" + ext
    args, starts, total = build_command(segments, tmp, width, height, **kw)
    try:
        # [OLD 2026-11-03 v0.5.1->v0.6.0] run_ffmpeg(args, total, progress)
        run_ffmpeg(args, total, progress, cancel)
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


# [OLD 2026-11-03 v0.5.1->v0.6.0] lines before src_in were dropped (a last_frame scene's line at 0 s); a blank line in a
# line of dialogue ended its SRT cue
# def subtitle_cues(entries):
#     """entries: [{start, src_in, src_out, dialogue:[{t, speaker, text}]}] -> [(start, end, text)]."""
#     cues = []
#     for e in entries:
#         lines = sorted(e.get("dialogue", []), key=lambda d: d["t"])
#         scene_end = e["start"] + (e["src_out"] - e["src_in"])
#         for i, d in enumerate(lines):
#             if d["t"] < e["src_in"] or d["t"] >= e["src_out"] or not d["text"].strip():
#                 continue
#             a = e["start"] + d["t"] - e["src_in"]
#             b = a + max(1.2, 0.6 + 0.07 * len(d["text"]))
#             if i + 1 < len(lines):
#                 b = min(b, e["start"] + lines[i + 1]["t"] - e["src_in"] - 0.05)
#             b = min(b, scene_end)
#             if b - a < 0.3:
#                 b = a + 0.3
#             text = (d["speaker"] + ": " if d.get("speaker") else "") + d["text"].strip()
#             cues.append((a, b, text))
#     return cues
# [/OLD]
def _cue_text(d):
    """added 2026-11-03 v0.6.0: a dialogue line as cue text; blank lines inside it would end the SRT cue."""
    lines = [x.strip() for x in str(d.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    text = "\n".join(x for x in lines if x)
    return (d["speaker"] + ": " if d.get("speaker") and text else "") + text


def subtitle_cues(entries):
    """entries: [{start, src_in, src_out, dialogue:[{t, speaker, text}]}] -> [(start, end, text)].
    added 2026-11-03 v0.6.0: a line up to one frame before the scene's cut-in point (a last_frame scene is cut in one
    frame late) is shown from the cut-in instead of being dropped; lines inside a tail scene's overlap stay out (that
    part of the scene is not in the cut)."""
    cues = []
    for e in entries:
        # an empty line is not a cue and does not cut the cue before it short
        lines = [d for d in sorted(e.get("dialogue", []), key=lambda d: d["t"]) if _cue_text(d)]
        scene_end = e["start"] + (e["src_out"] - e["src_in"])
        times = [max(float(d["t"]), e["src_in"]) for d in lines]
        for i, d in enumerate(lines):
            text = _cue_text(d)
            if d["t"] < e["src_in"] - 1.0 / FPS - 1e-6 or d["t"] >= e["src_out"]:
                continue
            a = e["start"] + times[i] - e["src_in"]
            b = a + max(1.2, 0.6 + 0.07 * len(text))
            if i + 1 < len(lines):
                b = min(b, e["start"] + times[i + 1] - e["src_in"] - 0.05)
            b = min(b, scene_end)
            if b - a < 0.3:
                b = a + 0.3
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


# [OLD 2026-11-03 v0.5.1->v0.6.0] every gap and clip length was rounded to frames on its own, so positions drifted by a
# frame; no soundtrack, no markers
# def write_otio(name, entries, path):
#     """A/B-roll OpenTimelineIO: alternating tracks so crossfading clips can overlap."""
#     def clip(e):
#         return {"OTIO_SCHEMA": "Clip.2", "name": e["title"], "metadata": {"reelwright": {"scene_id": e["scene_id"]}},
#                 "source_range": {"OTIO_SCHEMA": "TimeRange.1", "start_time": _rt(e["src_in"]),
#                                  "duration": _rt(e["src_out"] - e["src_in"])},
#                 "media_references": {"DEFAULT_MEDIA": {
#                     "OTIO_SCHEMA": "ExternalReference.1", "target_url": "file://" + os.path.abspath(e["path"]).replace(os.sep, "/"),
#                     "available_range": {"OTIO_SCHEMA": "TimeRange.1", "start_time": _rt(0), "duration": _rt(e["src_len"])}}},
#                 "active_media_reference_key": "DEFAULT_MEDIA", "effects": [], "markers": [], "enabled": True}
#
#     def track(kind, label, sub):
#         children, cur = [], 0.0
#         for e in sub:
#             if e["start"] > cur + 1e-6:
#                 children.append({"OTIO_SCHEMA": "Gap.1", "source_range": {"OTIO_SCHEMA": "TimeRange.1",
#                                  "start_time": _rt(0), "duration": _rt(e["start"] - cur)}})
#             children.append(clip(e))
#             cur = e["start"] + e["src_out"] - e["src_in"]
#         return {"OTIO_SCHEMA": "Track.1", "name": label, "kind": kind, "children": children,
#                 "effects": [], "markers": [], "enabled": True, "metadata": {}}
#
#     tracks = []
#     for kind in ("Video", "Audio"):
#         for parity, label in ((0, "A"), (1, "B")):
#             sub = [e for i, e in enumerate(entries) if i % 2 == parity]
#             if sub:
#                 tracks.append(track(kind, kind + " " + label, sub))
#     doc = {"OTIO_SCHEMA": "Timeline.1", "name": name, "global_start_time": _rt(0), "metadata": {},
#            "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": tracks,
#                       "effects": [], "markers": [], "enabled": True, "metadata": {}}}
#     with open(path, "w", encoding="utf-8") as f:
#         json.dump(doc, f, indent=1)
# [/OLD]


# ---- added 2026-11-03 v0.6.0: exact frame positions, soundtrack tracks and markers in OTIO and FCPXML ------------

def _frames(seconds):
    """Seconds to whole frames, half frames up (the same everywhere in the side files)."""
    return int((float(seconds) * FPS) + 0.5 + 1e-9) if seconds >= 0 else -int((-float(seconds) * FPS) + 0.5 + 1e-9)


def _rtf(frames):
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": float(FPS), "value": float(frames)}


def _otio_range(start_f, dur_f):
    return {"OTIO_SCHEMA": "TimeRange.1", "start_time": _rtf(start_f), "duration": _rtf(dur_f)}


def _url(path):
    return "file://" + os.path.abspath(path).replace(os.sep, "/")


OTIO_COLORS = {"amber": "ORANGE", "coral": "RED", "blue": "BLUE", "green": "GREEN", "pink": "PINK",
               "red": "RED", "orange": "ORANGE", "yellow": "YELLOW", "purple": "PURPLE", "cyan": "CYAN"}


def track_pieces(t, total):
    """The parts of an exported soundtrack track heard in the cut 0..total: [{src_in, src_out, at}] in seconds.
    t: {path, start (cut seconds), in, length, loop}."""
    from . import soundtrack
    return soundtrack.pieces([dict(t, asset=t.get("id", ""), file=t.get("path", ""))], 0.0, total)


def _spine(entries, total_f):
    """The cut as one row of clips and gaps, in whole frames: [{kind: clip|gap, at, src, dur, entry}]. A clip that
    overlaps the next one (a crossfade) is cut where the next starts; a slate or missing scene is a gap."""
    items, cur = [], 0
    for i, e in enumerate(entries):
        a = _frames(e["start"])
        own_end = _frames(e["start"] + e["src_out"] - e["src_in"])
        nxt = _frames(entries[i + 1]["start"]) if i + 1 < len(entries) else total_f
        src = _frames(e["src_in"])
        if a < cur:
            src, a = src + cur - a, cur
        end = min(own_end, max(nxt, a), total_f)
        if a > cur:
            items.append({"kind": "gap", "at": cur, "src": 0, "dur": a - cur})
            cur = a
        if end > a:
            items.append({"kind": "clip", "at": a, "src": src, "dur": end - a, "entry": e, "index": i})
            cur = end
    if cur < total_f:
        items.append({"kind": "gap", "at": cur, "src": 0, "dur": total_f - cur})
    return items


def write_otio(name, entries, path, tracks=None, markers=None, total=None):
    """A/B-roll OpenTimelineIO: alternating tracks so crossfading clips can overlap. Positions are whole frames
    counted from the start of the cut. tracks: soundtrack tracks laid on the cut ({id, code, path, start, in,
    length, loop, volume_db, fade_in, fade_out, file_duration}), one audio track each. markers: [{t, text, color}]
    on the timeline."""
    def media(path_, length_f):
        return {"DEFAULT_MEDIA": {"OTIO_SCHEMA": "ExternalReference.1", "target_url": _url(path_),
                                  "available_range": _otio_range(0, length_f)}}

    def clip(e, src_f, dur_f):
        return {"OTIO_SCHEMA": "Clip.2", "name": e["title"], "metadata": {"reelwright": {"scene_id": e["scene_id"]}},
                "source_range": _otio_range(src_f, dur_f), "media_references": media(e["path"], _frames(e["src_len"])),
                "active_media_reference_key": "DEFAULT_MEDIA", "effects": [], "markers": [], "enabled": True}

    def gap(dur_f):
        return {"OTIO_SCHEMA": "Gap.1", "name": "", "source_range": _otio_range(0, dur_f), "effects": [],
                "markers": [], "enabled": True, "metadata": {}}

    def track(kind, label, sub):
        children, cur = [], 0
        for e in sub:
            a = _frames(e["start"])
            b = _frames(e["start"] + e["src_out"] - e["src_in"])
            src = _frames(e["src_in"])
            if a < cur:
                src, a = src + cur - a, cur
            if a > cur:
                children.append(gap(a - cur))
            if b > a:
                children.append(clip(e, src, b - a))
                cur = b
        return {"OTIO_SCHEMA": "Track.1", "name": label, "kind": kind, "children": children,
                "effects": [], "markers": [], "enabled": True, "metadata": {}}

    if total is None:
        total = max([e["start"] + e["src_out"] - e["src_in"] for e in entries] or [0.0])
    out = []
    for kind in ("Video", "Audio"):
        for parity, label in ((0, "A"), (1, "B")):
            sub = [e for i, e in enumerate(entries) if i % 2 == parity]
            if sub:
                out.append(track(kind, kind + " " + label, sub))
    for t in tracks or []:
        children, cur = [], 0
        file_f = _frames(t.get("file_duration") or (t["in"] + t["length"]))
        for x in track_pieces(t, total):
            a, b = _frames(x["at"]), _frames(x["at"] + x["src_out"] - x["src_in"])
            if a < cur:
                a = cur
            if b <= a:
                continue
            if a > cur:
                children.append(gap(a - cur))
            children.append({"OTIO_SCHEMA": "Clip.2", "name": "Soundtrack {}".format(t.get("code") or ""),
                             "metadata": {"reelwright": {"track_id": t.get("id", ""), "volume_db": t.get("volume_db", 0.0),
                                                         "fade_in": t.get("fade_in", 0.0), "fade_out": t.get("fade_out", 0.0)}},
                             "source_range": _otio_range(_frames(x["src_in"]), b - a),
                             "media_references": media(t["path"], file_f), "active_media_reference_key": "DEFAULT_MEDIA",
                             "effects": [], "markers": [], "enabled": True})
            cur = b
        if children:
            out.append({"OTIO_SCHEMA": "Track.1", "name": "Soundtrack {}".format(t.get("code") or t.get("id", "")),
                        "kind": "Audio", "children": children, "effects": [], "markers": [], "enabled": True,
                        "metadata": {"reelwright": {"track_id": t.get("id", "")}}})
    total_f = _frames(total)
    marks = []
    for m in markers or []:
        f = _frames(m["t"])
        if 0 <= f <= total_f:
            marks.append({"OTIO_SCHEMA": "Marker.2", "name": str(m.get("text") or ""), "comment": "",
                          "color": OTIO_COLORS.get(str(m.get("color") or "").lower(), "RED"),
                          "marked_range": _otio_range(f, 0),
                          "metadata": {"reelwright": {"marker_id": m.get("id", "")}}})
    doc = {"OTIO_SCHEMA": "Timeline.1", "name": name, "global_start_time": _rtf(0), "metadata": {},
           "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": out,
                      "effects": [], "markers": marks, "enabled": True, "metadata": {}}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)


def _fr(seconds):
    return "{}/{}s".format(int(round(seconds * FPS)), FPS)


# [OLD 2026-11-03 v0.5.1->v0.6.0] escape() left " in attributes (a title with a quote broke the file); a clip ran on
# over the slate or gap after it
# def write_fcpxml(name, entries, total, width, height, path):
#     """Single-spine FCPXML 1.10; overlapping clips are cut where the next one starts."""
#     res = ['<format id="r0" name="FFVideoFormat{}p{}" frameDuration="1/{}s" width="{}" height="{}"/>'.format(
#         height, FPS, FPS, width, height)]
#     clips = []
#     for i, e in enumerate(entries):
#         res.append('<asset id="r{}" name="{}" start="0s" duration="{}" hasVideo="1" hasAudio="1" format="r0">'
#                    '<media-rep kind="original-media" src="{}"/></asset>'.format(
#                        i + 1, escape(e["title"]), _fr(e["src_len"]),
#                        escape("file://" + os.path.abspath(e["path"]).replace(os.sep, "/"))))
#         end = entries[i + 1]["start"] if i + 1 < len(entries) else total
#         clips.append('<asset-clip ref="r{}" name="{}" offset="{}" start="{}" duration="{}"/>'.format(
#             i + 1, escape(e["title"]), _fr(e["start"]), _fr(e["src_in"]), _fr(end - e["start"])))
#     xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.10">\n'
#            '<resources>\n{}\n</resources>\n<library><event name="{}"><project name="{}">'
#            '<sequence format="r0" duration="{}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">'
#            '<spine>\n{}\n</spine></sequence></project></event></library>\n</fcpxml>\n').format(
#         "\n".join(res), escape(name), escape(name), _fr(total), "\n".join(clips))
#     with open(path, "w", encoding="utf-8") as f:
#         f.write(xml)
# [/OLD]
def _ff(frames):
    """added 2026-11-03 v0.6.0: whole frames as an FCPXML time."""
    return "{}/{}s".format(int(frames), FPS)


def write_fcpxml(name, entries, total, width, height, path, tracks=None, markers=None):
    """Single-spine FCPXML 1.10; overlapping clips are cut where the next one starts (added 2026-11-03 v0.6.0:
    slates and missing scenes are <gap>s; soundtrack tracks are connected audio clips below the spine; markers sit
    on the clip or gap they fall in)."""
    total_f = _frames(total)
    res = ['<format id="r0" name="FFVideoFormat{}p{}" frameDuration="1/{}s" width="{}" height="{}"/>'.format(
        int(height), FPS, FPS, int(width), int(height))]
    for i, e in enumerate(entries):
        res.append('<asset id="r{}" name={} start="0s" duration="{}" hasVideo="1" hasAudio="1" format="r0" '
                   'audioSources="1" audioChannels="2" audioRate="48000">'
                   '<media-rep kind="original-media" src={}/></asset>'.format(
                       i + 1, quoteattr(e["title"]), _ff(_frames(e["src_len"])), quoteattr(_url(e["path"]))))
    items = _spine(entries, total_f)
    for x in items:
        x["inner"] = []

    def host(at_f):
        for x in items:
            if x["at"] <= at_f < x["at"] + x["dur"]:
                return x
        return None

    for j, t in enumerate(tracks or []):
        rid = "r{}".format(len(entries) + 1 + j)
        res.append('<asset id="{}" name={} start="0s" duration="{}" hasAudio="1" audioSources="1" audioChannels="2" '
                   'audioRate="48000"><media-rep kind="original-media" src={}/></asset>'.format(
                       rid, quoteattr("Soundtrack {}".format(t.get("code") or "")),
                       _ff(_frames(t.get("file_duration") or (t["in"] + t["length"]))), quoteattr(_url(t["path"]))))
        for p_ in track_pieces(t, total):
            a = _frames(p_["at"])
            dur = _frames(p_["at"] + p_["src_out"] - p_["src_in"]) - a
            x = host(a)
            if not x or dur <= 0:
                continue
            vol = float(t.get("volume_db") or 0.0)
            body = '<adjust-volume amount="{:.2f}dB"/>'.format(vol) if vol else ""
            x["inner"].append((0, '<asset-clip ref="{}" lane="-1" name={} offset="{}" start="{}" duration="{}" '
                                  'audioRole="music"{}'.format(
                                      rid, quoteattr("Soundtrack {}".format(t.get("code") or "")),
                                      _ff(x["src"] + a - x["at"]), _ff(_frames(p_["src_in"])), _ff(dur),
                                      ">{}</asset-clip>".format(body) if body else "/>")))
    for m in markers or []:
        f = _frames(m["t"])
        x = host(f)
        if x:
            x["inner"].append((1, '<marker start="{}" duration="{}" value={}/>'.format(
                _ff(x["src"] + f - x["at"]), _ff(1), quoteattr(str(m.get("text") or "Marker")))))
    spine = []
    for x in items:
        inner = "".join(v for _, v in sorted(x["inner"], key=lambda k: k[0]))  # connected clips before markers
        if x["kind"] == "gap":
            head = '<gap name="Gap" offset="{}" start="0s" duration="{}"'.format(_ff(x["at"]), _ff(x["dur"]))
            spine.append(head + (">{}</gap>".format(inner) if inner else "/>"))
        else:
            e = x["entry"]
            head = '<asset-clip ref="r{}" name={} offset="{}" start="{}" duration="{}"'.format(
                x["index"] + 1, quoteattr(e["title"]), _ff(x["at"]), _ff(x["src"]), _ff(x["dur"]))
            spine.append(head + (">{}</asset-clip>".format(inner) if inner else "/>"))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.10">\n'
           '<resources>\n{}\n</resources>\n<library><event name={}><project name={}>'
           '<sequence format="r0" duration="{}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">'
           '<spine>\n{}\n</spine></sequence></project></event></library>\n</fcpxml>\n').format(
        "\n".join(res), quoteattr(name), quoteattr(name), _ff(total_f), "\n".join(spine))
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)


def write_bundle(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for arcname, src in files.items():
            if src and os.path.isfile(src):
                z.write(src, arcname)
