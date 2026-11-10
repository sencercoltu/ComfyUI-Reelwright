"""Per-scene merge settings, scene.merge.

The migration from v0.6.1's scene.transition and Global -> Merge (and that such a project merges exactly as v0.6.1
did: the v0.6.1 code is loaded by path from REELWRIGHT_BASE_V061 when it is there), every transition type, fades from
and to a colour, the scene's sound (fades, level, mute), colour match per scene, eq, the soundtrack-locked dip, the
lints and the timeline filmstrip. Everything that makes video runs real ffmpeg and checks frames and pixels.
"""

import array
import copy
import importlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import types

import pytest

from reelwright import assemble, merge, model
from reelwright.analysis import analyze
from reelwright.model import normalize_project, scene_starts

needs_ffmpeg = pytest.mark.skipif(merge.ffmpeg_bin() is None, reason="ffmpeg not installed")
BASE_V061 = os.environ.get("REELWRIGHT_BASE_V061",
                           "/tmp/claude-0/-home-claude/7b99d167-01d6-5fae-b8d3-79743cdbb38f/scratchpad/v070/base_2b5d7ff")


# ---- helpers ----------------------------------------------------------------------------------------------------------

def solid(path, seconds, color="0x0000ff", freq=440, audio=True, size="64x36"):
    """A clip of one colour (0xRRGGBB or a test source) with a steady sine tone."""
    src = "{}=s={}:r=24:d={}".format(color, size, seconds) if not color.startswith("0x") else \
        "color=c={}:s={}:r=24:d={}".format(color, size, seconds)
    args = [merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", src]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=f={}:sample_rate=48000:d={}".format(freq, seconds), "-ac", "2"]
    args += ["-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p"] + (["-c:a", "pcm_s16le"] if audio else []) + \
        ["-t", str(seconds), path]
    subprocess.run(args, check=True)
    return path


def frame_rgb(path, n, size="16x9"):
    """Mean (r, g, b) of frame n (0-based) of a video."""
    raw = subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-i", path, "-vf",
                          "select=eq(n\\,{}),scale={}".format(n, size.replace("x", ":")), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    assert raw, "no frame {}".format(n)
    k = len(raw) // 3
    return tuple(sum(raw[c::3]) / k for c in range(3))


def frame_count(path):
    r = subprocess.run([merge.ffprobe_bin(), "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return int(r.stdout.strip())


def levels(path, start, end):
    """RMS (0..1) of the sound between start and end seconds (mono)."""
    raw = subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-ss", str(start), "-t",
                          str(end - start), "-i", path, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    a = array.array("h", raw)
    return math.sqrt(sum(x * x for x in a) / max(1, len(a))) / 32768.0


def near(rgb, want, tol=30):
    return all(abs(a - b) <= tol for a, b in zip(rgb, want))


def project(harbor, scenes, **merge_global):
    """The harbor project with these scenes (dicts; "merge" entries patch model.default_merge)."""
    p = copy.deepcopy(harbor)
    p["global"]["output"].update(width=64, height=36)
    p["global"]["merge"].update(dict(dict(normalize=False, subtitles=False, chapters=False, otio=False, fcpxml=False),
                                     **merge_global))
    out = []
    for k, s in enumerate(scenes):
        s = dict(s)
        s.setdefault("title", s["id"].upper())
        s.setdefault("start", {"mode": "fresh"})
        if "merge" in s:
            s["merge"] = dict(model.default_merge(), **s["merge"])
        out.append(s)
    p["scenes"] = out
    p["soundtrack"] = []
    return normalize_project(p)


def take(store, roots, sid, path, seconds, overlap=0):
    store.add_take(sid, {"id": "v1", "seconds": seconds, "overlap_frames": overlap,
                         "files": {"video": os.path.relpath(path, roots.output).replace(os.sep, "/")}})


# ---- the schema and the migration -------------------------------------------------------------------------------------

def v061_raw():
    """A v0.6.1 project: Global crossfade 12, audio fade 6, colour match on with scene D as the reference, and one
    scene (B) with its own transition (a dip of 18 frames, no audio fade). C continues B from its last frame, E
    continues D by a 22-frame tail, F has no take (skipped)."""
    return {
        "name": "Harbor Lights", "slug": "harbor_lights",
        "global": {"output": {"width": 64, "height": 36},
                   "merge": {"hard_cut": "crossfade", "transition_frames": 12, "audio_fade_frames": 6,
                             "color_match": True, "color_ref_scene": "s_d", "normalize": True, "loudness": -16.0,
                             "subtitles": False, "chapters": False, "otio": False, "fcpxml": False}},
        "scenes": [
            {"id": "s_a", "title": "A", "duration": 3.0, "start": {"mode": "fresh"}},
            {"id": "s_b", "title": "B", "duration": 3.0, "start": {"mode": "fresh"},
             "transition": {"mode": "dip", "frames": 18, "audio_fade_frames": 0}},
            {"id": "s_c", "title": "C", "duration": 2.5, "start": {"mode": "last_frame"}},
            {"id": "s_d", "title": "D", "duration": 3.0, "start": {"mode": "fresh"}},
            {"id": "s_e", "title": "E", "duration": 3.0, "start": {"mode": "tail", "overlap_frames": 22}},
            {"id": "s_f", "title": "F", "duration": 2.0, "start": {"mode": "fresh"}},
            {"id": "s_g", "title": "G", "duration": 2.0, "start": {"mode": "fresh"}},
        ]}


def test_migration_from_v061_settings():
    p = normalize_project(v061_raw())
    m = {s["id"]: s["merge"] for s in p["scenes"]}
    for sid in ("s_a", "s_c", "s_d", "s_e", "s_f", "s_g"):
        assert (m[sid]["transition"], m[sid]["frames"], m[sid]["audio_frames"]) == ("crossfade", 12, 6), sid
    assert (m["s_b"]["transition"], m["s_b"]["frames"], m["s_b"]["audio_frames"]) == ("dip", 18, 0)
    assert m["s_d"]["color_match"] == "off" and m["s_d"]["color_ref"] == ""  # the reference itself
    assert all(m[sid]["color_match"] == "scene" and m[sid]["color_ref"] == "s_d" for sid in m if sid != "s_d")
    rest = {k: v for k, v in m["s_a"].items() if k not in ("transition", "frames", "audio_frames", "color_match",
                                                           "color_ref")}
    assert rest == {k: v for k, v in model.default_merge().items() if k in rest}
    # the old keys stay (deprecated); normalising again changes nothing
    assert p["scenes"][1]["transition"]["mode"] == "dip" and p["global"]["merge"]["hard_cut"] == "crossfade"
    assert normalize_project(p)["scenes"] == p["scenes"]
    # a reference scene that is gone means the first scene; colour match off
    raw = v061_raw()
    raw["global"]["merge"]["color_ref_scene"] = "s_gone"
    q = normalize_project(raw)
    assert q["scenes"][0]["merge"]["color_match"] == "off"
    assert all(s["merge"]["color_ref"] == "s_a" for s in q["scenes"][1:])
    raw["global"]["merge"].update(color_match=False, hard_cut="zoom")  # not a v0.6.1 transition: it was a cut
    q = normalize_project(raw)
    assert [s["merge"]["transition"] for s in q["scenes"]] == ["cut", "dip", "cut", "cut", "cut", "cut", "cut"]
    assert all(s["merge"]["color_match"] == "off" for s in q["scenes"])
    # new scenes get the defaults, whatever Global -> Merge says
    assert model.default_scene(q)["merge"] == model.default_merge()


def test_merge_values_are_clamped():
    p = normalize_project({"scenes": [{"merge": {"transition": "spin", "direction": "diagonal", "frames": -3,
                                                 "color": "#GG0000", "audio_frames": 99999, "volume_db": 99,
                                                 "brightness": -7, "contrast": "1.5", "saturation": 9,
                                                 "fade_in": {"frames": 30.9, "color": "#AbCdEf"},
                                                 "color_match": "nearest"}}]})
    m = p["scenes"][0]["merge"]
    assert (m["transition"], m["direction"], m["frames"], m["color"]) == ("cut", "left", 0, "#000000")
    assert m["audio_frames"] == model.MERGE_MAX_FRAMES and m["volume_db"] == 24
    assert (m["brightness"], m["contrast"], m["saturation"]) == (-1, 1.5, 3)
    assert m["fade_in"] == {"frames": 30, "color": "#abcdef"} and m["color_match"] == "off"


def load_v061():
    root = os.path.join(BASE_V061, "reelwright")
    if not os.path.isfile(os.path.join(root, "assemble.py")):
        pytest.skip("the v0.6.1 code is not at REELWRIGHT_BASE_V061")
    name = "reelwright_v061"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, os.path.join(root, "__init__.py"),
                                                      submodule_search_locations=[root])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return types.SimpleNamespace(**{m: importlib.import_module(name + "." + m)
                                    for m in ("analysis", "assemble", "merge", "storage")})


def _v061_takes(store, roots):
    d = os.path.join(roots.output, "clips")
    os.makedirs(d, exist_ok=True)
    srcs = {"s_a": ("testsrc2", 3.0), "s_b": ("smptebars", 3.0), "s_c": ("rgbtestsrc", 2.5),
            "s_d": ("0x806040", 3.0), "s_e": ("testsrc", 3.0), "s_g": ("0x304070", 2.0)}
    for sid, (src, secs) in srcs.items():
        path = solid(os.path.join(d, sid + ".mp4"), secs, src, freq=300 + 40 * len(sid) + ord(sid[-1]))
        take(store, roots, sid, path, secs, overlap=22 if sid == "s_e" else 0)


@needs_ffmpeg
@pytest.mark.parametrize("locked", [False, True])
def test_a_v061_project_merges_exactly_as_before(harbor, store, roots, locked):
    """The ffmpeg command v0.7.0 builds for a migrated v0.6.1 project is v0.6.1's, but for one thing: v0.6.1 ran the
    colour reference scene through an identity colour mixer (gains 1, 1, 1), which v0.7.0 leaves out."""
    old = load_v061()
    _v061_takes(store, roots)
    raw = v061_raw()
    if locked:  # a soundtrack sets the timing: crossfades and dips become dips through black inside the scenes
        song = os.path.join(roots.input, "reelwright", "harbor_lights", "song.wav")
        subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "sine=f=220:d=30", song], check=True)
        raw["assets"] = [{"id": "a_song", "kind": "audio", "name": "song", "duration": 30.0,
                          "file": "reelwright/harbor_lights/song.wav"}]
        raw["soundtrack"] = [{"id": "t_1", "asset": "a_song", "start": 0.0}]
    old_store = old.storage.ProjectStore(old.storage.Roots(roots.output, roots.input, roots.user), "harbor_lights")

    r0 = old.analysis.analyze(copy.deepcopy(raw), old_store)
    segs0, entries0, skipped0 = old.assemble.cut_plan(r0, old_store)
    m0 = r0["project"]["global"]["merge"]
    ref_index = next((k for k, s in enumerate(segs0) if s.get("scene_id") == m0["color_ref_scene"]), 0)
    for seg, gain in zip(segs0, old.merge.color_gains(segs0, ref_index)):
        seg["gain"] = gain

    r1 = analyze(copy.deepcopy(raw), store)
    segs1, entries1, skipped1 = assemble.cut_plan(r1, store)
    assert assemble.color_match(r1, store, segs1) == []

    kw = dict(codec="h264", crf=16, loudness=-16.0, chapters_file=None, scene_audio={"mix": False, "volume_db": -12.0},
              preset="medium", stems=None)
    tracks = []
    if locked:
        tracks = [{"path": os.path.join(roots.input, "reelwright", "harbor_lights", "song.wav"), "start": 0.0,
                   "in": 0.0, "length": 30.0, "volume_db": 0.0, "fade_in": 0.0, "fade_out": 0.0, "duck": False,
                   "loop": False}]
    args0, starts0, total0 = old.merge.build_command(segs0, "out.mp4", 64, 36, audio_fade_frames=6, tracks=tracks, **kw)
    args1, starts1, total1 = merge.build_command(segs1, "out.mp4", 64, 36, audio_fade_frames=0, tracks=tracks, **kw)

    assert skipped1 == skipped0 == ["s_f"]
    assert (starts1, total1) == (starts0, total0)
    ref = next(k for k, s in enumerate(segs0) if s.get("scene_id") == "s_d")
    assert segs0[ref]["gain"] == (1.0, 1.0, 1.0) and segs1[ref].get("gain") is None
    gi = args0.index("-filter_complex") + 1
    g0 = args0[gi].split(";")
    v_ref = next(k for k, x in enumerate(g0) if x.endswith("[v{}]".format(ref)))
    g0[v_ref] = g0[v_ref].replace(",colorchannelmixer=rr=1.0000:gg=1.0000:bb=1.0000", "")
    assert args1[:gi] == args0[:gi] and args1[gi + 1:] == args0[gi + 1:]
    assert args1[gi].split(";") == g0
    graph = args1[args1.index("-filter_complex") + 1]
    if locked:  # the tail continuation E still crossfades inside its overlap; the dips keep the timing
        assert "fadeblack" not in graph and "fade=t=out:" in graph and ":color=black" in graph
    else:
        assert "xfade=transition=fade:" in graph and "xfade=transition=fadeblack:" in graph
    assert [s.get("scene_id") for s in segs1 if s.get("gain")] == ["s_a", "s_b", "s_c", "s_e", "s_g"]
    for e0, e1 in zip(entries0, entries1):
        assert e0 == e1


# ---- every transition, the dip colour, fades, sound, colour match and eq (real ffmpeg) ------------------------------

TYPES = [("crossfade", "left"), ("dissolve", "left"), ("wipe", "left"), ("wipe", "up"), ("slide", "right"),
         ("slide", "down"), ("circle", "left"), ("pixelize", "left"), ("radial", "left"), ("zoom", "left"),
         ("dip", "left")]


@needs_ffmpeg
def test_every_transition_type_merges(harbor, store, roots):
    a = solid(os.path.join(roots.output, "a.mp4"), 2.0, "0x0000ff")
    b = solid(os.path.join(roots.output, "b.mp4"), 2.0, "0x00ff00")
    scenes = [{"id": "s_0", "duration": 2.0}]
    colors = ["#000000", "#ffffff", "#ff0000"]
    for k, (kind, d) in enumerate(TYPES + [("dip", "left"), ("dip", "left")]):
        scenes.append({"id": "s_{}".format(k + 1), "duration": 2.0,
                       "merge": {"transition": kind, "direction": d, "frames": 8 + k % 3,
                                 "color": colors[k - len(TYPES) + 1] if k >= len(TYPES) - 1 else "#000000"}})
    p = project(harbor, scenes)
    for k, s in enumerate(p["scenes"]):
        take(store, roots, s["id"], a if k % 2 == 0 else b, 2.0)
    r = analyze(p, store)
    segs, _, _ = assemble.cut_plan(r, store)
    names = [s.get("transition") for s in segs[1:]]
    assert names == ["fade", "dissolve", "wipeleft", "wipeup", "slideright", "slidedown", "circleopen", "pixelize",
                     "radial", "zoomin", "fadeblack", "fadewhite", "custom"]
    assert segs[-1]["transition_expr"].startswith("(A*") and segs[-1]["join"] == "dip"
    out = assemble.merge_project(r, store)
    video = store.output_path(out["files"]["video"])
    overlap = sum(8 + k % 3 for k in range(len(scenes) - 1))
    assert frame_count(video) == round(out["duration"] * 24) == 48 * len(scenes) - overlap
    assert merge.probe(video)["duration"] == pytest.approx(out["duration"], abs=0.05)


@needs_ffmpeg
def test_dip_colour_fades_and_eq_are_on_the_right_frames(harbor, store, roots, tmp_path):
    blue = solid(os.path.join(roots.output, "blue.mp4"), 2.0, "0x0000ff")
    grey = solid(os.path.join(roots.output, "grey.mp4"), 2.0, "0x808080")
    p = project(harbor, [
        {"id": "s_a", "duration": 2.0, "merge": {"fade_in": {"frames": 12, "color": "#ff0000"}}},
        {"id": "s_b", "duration": 2.0, "merge": {"transition": "dip", "frames": 12, "color": "#ff0000",
                                                 "fade_out": {"frames": 12, "color": "#00ff00"}}},
        {"id": "s_c", "duration": 2.0, "merge": {"brightness": 0.25}},
    ])
    take(store, roots, "s_a", blue, 2.0)
    take(store, roots, "s_b", grey, 2.0)
    take(store, roots, "s_c", grey, 2.0)
    out = assemble.merge_project(analyze(p, store), store)
    v = store.output_path(out["files"]["video"])
    assert frame_count(v) == 48 + 48 - 12 + 48
    # fade in from red over 12 frames: frame 0 red, frame 6 half way, frame 12 the picture
    assert near(frame_rgb(v, 0), (255, 0, 0))
    assert near(frame_rgb(v, 6), (128, 0, 128), 40)
    assert near(frame_rgb(v, 12), (0, 0, 255))
    # the dip through red: the overlap is frames 36..47; it is red a quarter of the way in, grey after it
    assert near(frame_rgb(v, 35), (0, 0, 255))
    assert near(frame_rgb(v, 39), (255, 0, 0), 40)
    assert near(frame_rgb(v, 48), (128, 128, 128))
    # B fades out to green: its last frame (83) is green, frame 71 still grey
    assert near(frame_rgb(v, 71), (128, 128, 128))
    assert near(frame_rgb(v, 83), (0, 255, 0), 40)
    assert near(frame_rgb(v, 77), (64, 192, 64), 40)
    # C is brighter than the same grey without eq
    c = frame_rgb(v, 100)
    assert all(x > 160 for x in c) and near(c, (c[0], c[0], c[0]), 6)


@needs_ffmpeg
def test_the_scene_sound_fades_level_and_mute(harbor, store, roots):
    tone = solid(os.path.join(roots.output, "tone.mp4"), 2.0, "0x404040")
    p = project(harbor, [
        {"id": "s_a", "duration": 2.0, "merge": {"audio_fade_in": 24, "audio_frames": 0}},
        {"id": "s_b", "duration": 2.0, "merge": {"volume_db": -6.0, "audio_frames": 0, "audio_fade_out": 12}},
        {"id": "s_c", "duration": 2.0, "merge": {"mute": True, "audio_frames": 0}},
        {"id": "s_d", "duration": 2.0, "merge": {"audio_frames": 0}},
    ])
    for s in p["scenes"]:
        take(store, roots, s["id"], tone, 2.0)
    out = assemble.merge_project(analyze(p, store), store)
    v = store.output_path(out["files"]["video"])
    full = levels(v, 7.0, 7.9)  # D, untouched
    assert full > 0.05
    assert levels(v, 0.0, 0.1) < 0.15 * full  # A fades in over its first second
    assert levels(v, 1.2, 1.9) == pytest.approx(full, rel=0.05)
    assert levels(v, 2.1, 3.3) == pytest.approx(full / 2, rel=0.08)  # B at -6 dB
    assert levels(v, 3.9, 4.0) < 0.2 * full  # ... fading out in its last half second
    assert levels(v, 4.05, 5.95) < 0.01  # C is muted


@needs_ffmpeg
def test_colour_match_previous_and_a_chosen_scene_outside_a_range(harbor, store, roots):
    warm = solid(os.path.join(roots.output, "warm.mp4"), 2.0, "0xa06060")
    cool = solid(os.path.join(roots.output, "cool.mp4"), 2.0, "0x6060a0")
    p = project(harbor, [
        {"id": "s_a", "duration": 2.0},
        {"id": "s_b", "duration": 2.0, "merge": {"color_match": "previous"}},
        {"id": "s_c", "duration": 2.0, "merge": {"color_match": "previous"}},
        {"id": "s_d", "duration": 2.0, "merge": {"color_match": "scene", "color_ref": "s_a"}},
        {"id": "s_e", "duration": 2.0, "merge": {"color_match": "scene", "color_ref": "s_none"}},
        {"id": "s_f", "duration": 2.0, "merge": {"color_match": "scene", "color_ref": "s_g"}},
        {"id": "s_g", "duration": 2.0},
    ])
    take(store, roots, "s_a", cool, 2.0)
    for sid in ("s_b", "s_c", "s_d", "s_e", "s_f"):
        take(store, roots, sid, warm, 2.0)
    r = analyze(p, store)
    segs, _, _ = assemble.cut_plan(r, store)
    warnings = assemble.color_match(r, store, segs)
    gains = {s["scene_id"]: s.get("gain") for s in segs}
    assert gains["s_a"] is None and gains["s_e"] is None and gains["s_f"] is None
    assert gains["s_b"] == pytest.approx((0.8, 1.0, 1.25), abs=0.03)  # warm towards cool, clamped
    # C matches B as corrected, so it gets about the same gains (not B's raw warm colour)
    assert gains["s_c"] == pytest.approx(gains["s_b"], abs=0.03)
    assert gains["s_d"] == pytest.approx((0.8, 1.0, 1.25), abs=0.03)
    assert len(warnings) == 2 and "not in the project" in warnings[0] and "has no finished take" in warnings[1]
    # a range merge without A still measures A's take
    segs, _, _ = assemble.cut_plan(r, store, {"range": ["s_d", "s_d"]})
    assert assemble.color_match(r, store, segs) == [] and segs[0]["gain"] == pytest.approx((0.8, 1.0, 1.25), abs=0.03)
    out = assemble.merge_project(analyze(p, store), store, options={"range": ["s_b", "s_f"]})
    assert out["warnings"] == warnings
    v = store.output_path(out["files"]["video"])
    assert near(frame_rgb(v, 10), (160, 96, 96), 12)  # B starts this cut: nothing before it to match
    assert near(frame_rgb(v, 100), (128, 96, 120), 12)  # D matches A (cool), outside the range


@needs_ffmpeg
def test_locked_transitions_dip_through_their_colour_on_the_frame_grid(harbor, store, roots):
    a = solid(os.path.join(roots.output, "a.mp4"), 3.0, "0x0000ff")
    b = solid(os.path.join(roots.output, "b.mp4"), 3.0, "0x808080")
    p = project(harbor, [{"id": "s_a", "duration": 2.9},
                         {"id": "s_b", "duration": 2.9, "merge": {"transition": "wipe", "frames": 12, "color": "#ff0000"}},
                         {"id": "s_c", "duration": 2.9, "merge": {"transition": "dip", "frames": 8, "color": "#00ff00"}}])
    song = os.path.join(roots.input, "reelwright", "harbor_lights", "song.wav")
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=f=220:d=12", song], check=True)
    p["assets"].append({"id": "a_song", "kind": "audio", "code": "A9", "name": "song", "duration": 12.0,
                        "file": "reelwright/harbor_lights/song.wav"})
    p["soundtrack"] = [{"id": "t_1", "asset": "a_song", "start": 0.0}]
    p = normalize_project(p)
    for s, path in zip(p["scenes"], (a, b, a)):
        take(store, roots, s["id"], path, 3.0)
    r = analyze(p, store)
    segs, _, _ = assemble.cut_plan(r, store)
    assert [s["join"] for s in segs] == ["first", "cut", "cut"]
    assert segs[0]["vfade_out_color"] == "#ff0000" and segs[1]["vfade_in"] == pytest.approx(0.25)
    assert segs[1]["vfade_out_color"] == "#00ff00" and segs[2]["vfade_in"] == pytest.approx(4 / 24)
    issues = [i["message"] for i in r["issues"] + [x for s in r["scenes"].values() for x in s["issues"]]]
    assert any("wipe plays as a dip through #ff0000 inside both scenes" in m for m in issues)
    assert any("dip through #00ff00 plays inside both scenes" in m for m in issues)
    out = assemble.merge_project(r, store)
    v = store.output_path(out["files"]["video"])
    n = merge.frame_index(scene_starts(p)[1])
    assert frame_count(v) == n == round(3 * 2.9 * 24)
    cut = merge.frame_index(2.9)  # 70: B's first frame
    assert near(frame_rgb(v, cut), (255, 0, 0), 40) and near(frame_rgb(v, cut - 1), (255, 0, 0), 60)
    assert near(frame_rgb(v, cut - 8), (0, 0, 255))


@needs_ffmpeg
def test_stems_draft_and_side_files_still_work_with_looks(harbor, store, roots):
    tone = solid(os.path.join(roots.output, "tone.mp4"), 2.0, "testsrc2")
    p = project(harbor, [{"id": "s_a", "duration": 2.0, "merge": {"fade_in": {"frames": 6, "color": "#ffffff"}}},
                         {"id": "s_b", "duration": 2.0, "merge": {"transition": "slide", "direction": "up",
                                                                  "frames": 10, "volume_db": -3, "saturation": 0}},
                         {"id": "s_c", "duration": 2.0, "merge": {"transition": "dip", "color": "#3366cc"}}],
                normalize=True, subtitles=True, chapters=True, otio=True, fcpxml=True)
    for s in p["scenes"]:
        take(store, roots, s["id"], tone, 2.0)
    out = assemble.merge_project(analyze(p, store), store, options={"draft": True, "stems": True})
    for k in ("video", "srt", "otio", "fcpxml", "chapters", "stems", "loudness"):
        assert os.path.exists(store.output_path(out["files"][k])), k
    v = store.output_path(out["files"]["video"])
    assert frame_count(v) == round(out["duration"] * 24) == 144 - 10 - 12
    assert out["loudness"]["integrated"] == pytest.approx(-16, abs=3)
    r, g, b = frame_rgb(v, 60)  # B: saturation 0 is grey
    assert near((r, g, b), (r, r, r), 8)


# ---- lints ------------------------------------------------------------------------------------------------------------

def test_merge_lints(harbor, store):
    p = project(harbor, [
        {"id": "s_a", "duration": 3.0, "merge": {"fade_out": {"frames": 12, "color": "#000000"}}},
        {"id": "s_b", "duration": 3.0, "start": {"mode": "last_frame"},
         "merge": {"fade_in": {"frames": 6, "color": "#ffffff"}, "color_match": "scene", "color_ref": "s_x"}},
        {"id": "s_c", "duration": 3.0, "merge": {"transition": "crossfade", "fade_out": {"frames": 4}}},
        {"id": "s_d", "duration": 3.0, "start": {"mode": "tail", "overlap_frames": 22},
         "merge": {"color_match": "scene", "color_ref": "s_a"}},
    ])
    r = analyze(p, store)
    by = {sid: [i["message"] for i in s["issues"]] for sid, s in r["scenes"].items()}
    assert any("fades out to black, but the next scene continues from its last frame, which is not" in m
               for m in by["s_a"])
    assert any("fades in from white, but it continues the scene before" in m for m in by["s_b"])
    assert any("colour match names a scene that is not in the project" in m for m in by["s_b"])
    assert any("continues from its last frames, which are not faded" in m for m in by["s_c"])
    assert not any("colour match" in m or "fades" in m for m in by["s_d"])
    assert not any("plays as a dip" in m for ms in by.values() for m in ms)  # no soundtrack: crossfades overlap


# ---- filmstrips -------------------------------------------------------------------------------------------------------

def test_filmstrip_layout():
    assert merge.filmstrip_layout(7.3, 1344, 768, 54) == (0.25, 30, 94, 54)
    iv, n, w, h = merge.filmstrip_layout(150.0, 1344, 768, 54)
    assert (iv, n) == (0.25, 600) and n * w <= 65500
    iv, n, w, h = merge.filmstrip_layout(1200.0, 1344, 768, 54)
    assert (iv, n) == (2.0, 600)
    iv, n, w, h = merge.filmstrip_layout(200.0, 1344, 576, 256)  # 21:9, tall tiles: capped by the JPEG width
    assert w == 598 and n == 65500 // 598 and iv == pytest.approx(200.0 / n) and n * w <= 65500
    assert merge.filmstrip_layout(0.01, 64, 36, 16)[1] == 1


@needs_ffmpeg
def test_filmstrip_shows_the_frame_at_each_time_and_is_reused(tmp_path):
    # one colour per second: red, green, blue, white
    path = str(tmp_path / "take.mp4")
    parts = "".join("color=c={}:s=64x36:r=24:d=1[c{}];".format(c, k) for k, c in enumerate(("red", "lime", "blue", "white")))
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-filter_complex",
                    parts + "[c0][c1][c2][c3]concat=n=4:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", path], check=True)
    out = merge.filmstrip(path, 18)
    assert out["path"] == str(tmp_path / "take.filmstrip_18.jpg") and os.path.isfile(out["path"])
    assert (out["interval"], out["count"], out["tile_w"], out["tile_h"]) == (0.25, 16, 32, 18)
    meta = json.load(open(str(tmp_path / "take.filmstrip_18.json")))
    assert meta["count"] == 16 and meta["duration"] == pytest.approx(4.0)
    from PIL import Image
    im = Image.open(out["path"]).convert("RGB")
    assert im.size == (16 * 32, 18)

    def tile(k):
        return im.getpixel((k * 32 + 16, 9))
    want = {1: (255, 0, 0), 5: (0, 255, 0), 9: (0, 0, 255), 13: (255, 255, 255), 15: (255, 255, 255)}
    for k, rgb in want.items():
        assert near(tile(k), rgb, 50), (k, tile(k))
    mtime = os.path.getmtime(out["path"])
    again = merge.filmstrip(path, 18)
    assert again["path"] == out["path"] and os.path.getmtime(out["path"]) == mtime  # reused
    # a new video (another size) makes it again
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=red:s=64x36:r=24:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True)
    os.utime(path, ns=(1, 1))
    third = merge.filmstrip(path, 18)
    assert third["count"] == 8 and Image.open(third["path"]).size == (8 * 32, 18)
    with pytest.raises(merge.MergeError):
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(b"not a video")
        merge.filmstrip(str(bad), 18)
    assert not [x for x in os.listdir(str(tmp_path)) if ".partial" in x]
