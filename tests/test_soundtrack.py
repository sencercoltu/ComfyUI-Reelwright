"""Soundtrack tracks (added 2026-11-03 v0.5.0): a song laid on the cut, sent to every pass as the part it covers,
mixed unchanged in the merge."""

import copy
import os
import subprocess

import pytest

from reelwright import assemble, cache, merge, soundtrack, spec, validate
from reelwright.analysis import analyze
from reelwright.model import default_project, normalize_project, scene_starts
from reelwright.planner import plan_scene
from reelwright.prompt import build_pass

needs_ffmpeg = pytest.mark.skipif(merge.ffmpeg_bin() is None, reason="ffmpeg not installed")


def _song(p, **kw):
    p["assets"].append({"id": "a_song", "kind": "audio", "name": "song", "code": "A9",
                        "file": "reelwright/harbor_lights/voice.wav", "duration": 120.0})
    t = dict({"asset": "a_song"}, **kw)
    p["soundtrack"] = [t]
    return normalize_project(p)


def _build(p, i, n=0):
    plan = plan_scene(p, p["scenes"][i], i)
    return build_pass(p, p["scenes"][i], i, plan, plan["passes"][n]), plan


# ---- model ---------------------------------------------------------------------------------------------------------

def test_defaults_and_score_migration():
    p = normalize_project(default_project("x"))
    assert p["soundtrack"] == []
    assert p["global"]["merge"]["scene_audio"] == {"mix": False, "volume_db": -12.0}
    old = default_project("y")
    old["assets"] = [{"id": "a_bed", "kind": "audio", "name": "bed", "file": "bed.wav"}]
    old["global"]["merge"]["score"] = {"asset": "a_bed", "volume_db": -9.0, "duck": False}
    p = normalize_project(old)
    t = p["soundtrack"][0]
    assert (t["asset"], t["volume_db"], t["duck"], t["loop"], t["sync"], t["mix"]) == ("a_bed", -9.0, False, True, False, True)
    assert p["global"]["merge"]["score"]["asset"] == ""
    assert p["global"]["merge"]["scene_audio"]["mix"] is True  # the scenes stay audible, as they were over a score
    again = normalize_project(p)
    assert len(again["soundtrack"]) == 1  # migrates once


def test_track_normalize_cleans_values():
    t = soundtrack.normalize_track({"asset": "a", "start": "2.5", "in": -3, "volume_db": "x", "marker": "nope",
                                    "fade_in": -1, "mute": 0})
    assert (t["start"], t["in"], t["volume_db"], t["marker"], t["fade_in"], t["mute"]) == (2.5, 0.0, 0.0, "fully_copy", 0.0, False)


def test_scene_starts_are_cut_times(harbor):
    starts, total = scene_starts(harbor)
    assert starts["s_one"] == 0
    assert starts["s_long"] == pytest.approx(8 - 39 / 24)  # the tail scene repeats the last 39 frames of scene 1
    assert starts["s_short"] == pytest.approx(8 - 39 / 24 + 32)
    assert total == pytest.approx(8 - 39 / 24 + 32 + 2.5)


# ---- one song segment per pass --------------------------------------------------------------------------------------

def test_pass_window_and_pieces(harbor):
    p = _song(harbor, start=2.0, **{"in": 10.0})
    plan = plan_scene(p, p["scenes"][0], 0)
    x = plan["passes"][0]
    song = soundtrack.pass_soundtrack(p, 0.0, x)
    assert song["start"] == 0 and song["length"] == pytest.approx(min(15, x["gen_frames"] / 24))
    assert song["pieces"] == [{"asset": "a_song", "file": "reelwright/harbor_lights/voice.wav", "src_in": 10.0,
                               "src_out": pytest.approx(10 + song["length"] - 2), "at": 2.0}]
    assert song["marker"] == "fully_copy" and song["codes"] == ["A9"]
    # the long tail scene: every pass starts where its generated frame 0 plays in the cut
    starts = scene_starts(p)[0]
    plan = plan_scene(p, p["scenes"][1], 1)
    for x in plan["passes"]:
        s = soundtrack.pass_soundtrack(p, starts["s_long"], x)
        assert s["start"] == pytest.approx(starts["s_long"] + x["start"])
        assert s["pieces"][0]["src_in"] == pytest.approx(10 + s["start"] - 2)
        assert s["pieces"][0]["at"] == 0


def test_short_scene_window_starts_before_the_scene(harbor):
    p = _song(harbor)
    plan = plan_scene(p, p["scenes"][2], 2)
    x = plan["passes"][0]
    assert x["start"] < 0  # 1.208 s generated before the kept part
    s = soundtrack.pass_soundtrack(p, scene_starts(p)[0]["s_short"], x)
    assert s["start"] == pytest.approx(scene_starts(p)[0]["s_short"] + x["start"])


def test_too_little_sound_and_loops(harbor):
    p = _song(harbor, start=7.0, out=1.5)  # 1.5 s of song
    plan = plan_scene(p, p["scenes"][0], 0)
    assert soundtrack.pass_soundtrack(p, 0.0, plan["passes"][0]) is None
    p["soundtrack"][0]["loop"] = True
    p["soundtrack"][0]["start"] = 0.0
    s = soundtrack.pass_soundtrack(p, 0.0, plan["passes"][0])
    assert len(s["pieces"]) >= 5 and all(x["src_out"] - x["src_in"] <= 1.5 + 1e-6 for x in s["pieces"])
    assert [x["at"] for x in s["pieces"][:3]] == [0, 1.5, 3.0]
    p["soundtrack"][0]["mute"] = True
    assert soundtrack.pass_soundtrack(p, 0.0, plan["passes"][0]) is None
    p["soundtrack"][0].update(mute=False, sync=False)
    assert soundtrack.pass_soundtrack(p, 0.0, plan["passes"][0]) is None
    assert soundtrack.locked(p)  # still mixed, so the timing is still locked


# ---- prompt, cache, lint --------------------------------------------------------------------------------------------

def test_prompt_sends_the_song_instead_of_voices(harbor):
    # v0.6.0: a voice goes only to the passes where its character speaks (Mara's line at 16 s)
    plan = plan_scene(harbor, harbor["scenes"][1], 1)
    k = next(n for n, x in enumerate(plan["passes"]) if x["dialogue"])
    before, _ = _build(harbor, 1, k)
    assert any(a["cast"] for a in before["audios"])
    p = _song(harbor)
    p["scenes"][1]["prompt"]["sections"]["summary"] += " She sings along to @soundtrack."
    b, _ = _build(p, 1, k)
    assert not any(a.get("cast") for a in b["audios"])
    song = [a for a in b["audios"] if a.get("song")]
    assert len(song) == 1
    n = int(b["tag_map"]["@soundtrack"].split()[1].rstrip(">"))
    assert n == 2  # <Audio 1> is the dolly video's own sound
    assert "<Audio {}> is the song this part of the film is cut to".format(n) in b["prompt"]
    assert "<Audio {}>: fully_copy".format(n) in b["prompt"]
    assert "sings along to <Audio {}>".format(n) in b["prompt"]
    assert "@soundtrack" not in b["unknown"] and not any("soundtrack" in u for u in b["unknown"])
    assert b["tag_map"]["@soundtrack"] == "<Audio {}>".format(n)


def test_cache_key_follows_the_song(harbor):
    p = _song(harbor, start=0.0)
    b, plan = _build(p, 0)
    key = lambda bb: cache.pass_key({}, bb, plan["passes"][0], lambda a: "d-" + a, None, None)
    k1 = key(b)
    p2 = copy.deepcopy(p)
    p2["soundtrack"][0]["start"] = 0.5
    k2 = key(_build(p2, 0)[0])
    p3 = copy.deepcopy(p)
    p3["soundtrack"][0]["volume_db"] = -6.0  # the level only matters for the mix, not for the reference
    k3 = key(_build(p3, 0)[0])
    assert k1 != k2 and k1 == k3
    # a track that starts after scene 1 does not touch scene 1
    p4 = copy.deepcopy(p)
    p4["soundtrack"][0]["start"] = 20.0
    p5 = copy.deepcopy(p4)
    p5["soundtrack"][0]["start"] = 21.0
    assert key(_build(p4, 0)[0]) == key(_build(p5, 0)[0])


def test_lint_counts_the_song_and_checks_tracks(harbor, store):
    p = _song(harbor, start=0.0)
    # [OLD 2026-11-05 v0.6.1->v0.7.0] p["scenes"][2]["transition"] = {"mode": "crossfade", "frames": 12, "audio_fade_frames": None}
    p["scenes"][2]["merge"].update(transition="crossfade", frames=12)  # added 2026-11-05 v0.7.0: scene.merge
    r = analyze(p, store)
    msgs = [i["message"] for s in r["scenes"].values() for i in s["issues"]] + [i["message"] for i in r["issues"]]
    assert not any("reference audio clips" in m for m in msgs)
    # [OLD 2026-11-05 v0.6.1->v0.7.0] assert any("dip through black inside the scenes" in m for m in msgs)
    assert any("crossfade plays as a dip through black inside both scenes" in m for m in msgs)  # v0.7.0: per scene
    p["soundtrack"].append(soundtrack.normalize_track({"asset": "a_front"}))
    p["soundtrack"].append(soundtrack.normalize_track({"asset": "a_song", "in": 200.0}))
    p["soundtrack"].append(soundtrack.normalize_track({"asset": "gone"}))
    plans = {s["id"]: plan_scene(p, s, i) for i, s in enumerate(p["scenes"])}
    builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}
    issues = validate.lint_project(p, plans, builds, lambda a: True)
    text = " | ".join(i["message"] for i in issues)
    assert "is not an audio file" in text and "trimmed past the end" in text and "no longer exists" in text


# ---- merge graph ----------------------------------------------------------------------------------------------------

def _graph(args):
    return args[args.index("-filter_complex") + 1]


def test_track_graph_keeps_the_song_untouched():
    segs = [{"path": "a.mp4", "in": 0, "out": 4, "has_audio": True, "join": "first", "dur": 0}]
    tracks = [{"path": "song.wav", "start": 1.0, "in": 30.0, "length": 60.0, "volume_db": 0.0}]
    args, _, total = merge.build_command(segs, "o.mp4", 64, 32, loudness=-16.0, tracks=tracks,
                                         scene_audio={"mix": False, "volume_db": -12})
    g = _graph(args)
    assert "anullsink" in g and "loudnorm" not in g and "amix" not in g and "volume=" not in g
    trk = [x for x in g.split(";") if x.endswith("[trk0]")][0]
    assert "atrim=start=30:end=90" in trk and "adelay=delays=1000:all=1" in trk and "atrim=duration=4" in trk
    args, _, _ = merge.build_command(segs, "o.mp4", 64, 32, loudness=-16.0, tracks=[dict(tracks[0], duck=True)],
                                     scene_audio={"mix": True, "volume_db": -6})
    g = _graph(args)
    scn = [x for x in g.split(";") if x.endswith("[scn]")][0]
    assert "loudnorm" in scn and "volume=-6.0dB" in scn
    assert "sidechaincompress" in g and "alimiter=limit=0.98:level=0" in g
    assert "loudnorm" not in [x for x in g.split(";") if x.endswith("[trk0]")][0]


def test_track_before_the_film_and_loop():
    segs = [{"path": "a.mp4", "in": 0, "out": 10, "has_audio": True, "join": "first", "dur": 0}]
    args, _, _ = merge.build_command(segs, "o.mp4", 64, 32, tracks=[
        {"path": "s.wav", "start": -2.0, "in": 0.0, "length": 5.0, "fade_in": 1.0},
        {"path": "bed.wav", "start": 0.0, "in": 0.0, "length": 3.0, "loop": True, "volume_db": -12.0}],
        scene_audio={"mix": False})
    g = _graph(args)
    t0 = [x for x in g.split(";") if x.endswith("[trk0]")][0]
    assert "atrim=start=2,asetpts" in t0 and "atrim=duration=3" in t0 and "afade=t=in" not in t0
    t1 = [x for x in g.split(";") if x.endswith("[trk1]")][0]
    assert "aloop=loop=-1:size=144000" in t1 and "atrim=duration=10" in t1 and "volume=-12.0dB" in t1


def test_vfades_keep_the_timing():
    segs = [{"path": "a.mp4", "in": 0, "out": 4, "has_audio": True, "join": "first", "dur": 0, "vfade_out": 0.25},
            {"path": "b.mp4", "in": 0, "out": 4, "has_audio": True, "join": "cut", "dur": 0, "vfade_in": 0.25}]
    args, starts, total = merge.build_command(segs, "o.mp4", 64, 32)
    g = _graph(args)
    assert starts == [0, 4] and total == 8
    assert "fade=t=out:st=3.75:d=0.25:color=black" in g and "fade=t=in:st=0:d=0.25:color=black" in g


# ---- cut plan when the soundtrack sets the timing -------------------------------------------------------------------

def _clip(path, seconds, audio=True):
    args = [merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=s=160x90:r=24:d={}".format(seconds)]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=f=880:sample_rate=48000:d={}".format(seconds), "-ac", "2"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else []) + ["-shortest", path]
    subprocess.run(args, check=True)
    return path


def _tone(path, seconds, freq=220):
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=f={}:sample_rate=44100:d={}".format(freq, seconds), "-ac", "2", path], check=True)
    return path


def _take(store, r, sid, secs, overlap=0):
    d = store.take_dir(sid, "v1")
    os.makedirs(d, exist_ok=True)
    _clip(os.path.join(d, "video.mp4"), secs)
    store.add_take(sid, {"id": "v1", "key": r["scenes"][sid]["key"], "seconds": secs, "overlap_frames": overlap,
                         "files": {"video": store.rel_output(os.path.join(d, "video.mp4"))}})


@needs_ffmpeg
def test_locked_cut_plan_matches_the_timeline(harbor, store, roots):
    p = _song(harbor)
    p["global"]["merge"].update(missing="skip", hard_cut="crossfade", transition_frames=12)
    for s in p["scenes"]:  # added 2026-11-05 v0.7.0: Global -> Merge's hard cut is read once, into scene.merge
        s.pop("merge", None)
    r = analyze(p, store)
    _take(store, r, "s_one", 7.0)  # an old take, 1 s shorter than the scene
    _take(store, r, "s_short", 2.5)
    segs, entries, skipped = assemble.cut_plan(analyze(p, store), store)
    _, total = merge.plan_timeline(segs)
    assert total == pytest.approx(scene_starts(p)[1], abs=1e-6)
    assert skipped == ["s_long"]
    assert [s.get("path") is None for s in segs] == [False, True, True, False]  # gap slate, missing scene, insert
    assert segs[-1]["join"] == "cut" and segs[-1].get("vfade_in") == pytest.approx(0.25)
    p["soundtrack"] = []  # without a soundtrack the old rules apply: skip and crossfade
    segs, _, _ = assemble.cut_plan(analyze(p, store), store)
    assert [s["join"] for s in segs] == ["first", "xfade"]


@needs_ffmpeg
def test_segment_wav_and_merge_with_a_real_song(harbor, store, roots):
    song_rel = "reelwright/harbor_lights/song.wav"
    _tone(os.path.join(roots.input, song_rel), 30)
    p = copy.deepcopy(harbor)
    p["assets"].append({"id": "a_song", "kind": "audio", "name": "song", "file": song_rel, "duration": 30.0})
    p["soundtrack"] = [{"asset": "a_song", "start": 1.0, "in": 5.0}]
    p = normalize_project(p)
    plan = plan_scene(p, p["scenes"][0], 0)
    song = soundtrack.pass_soundtrack(p, 0.0, plan["passes"][0])
    pieces = [dict(x, path=os.path.join(roots.input, x["file"])) for x in song["pieces"]]
    out_dir = os.path.join(store.dir, "soundtrack")
    wav = merge.render_segment(pieces, song["length"], out_dir, cache.file_digest)
    assert merge.probe(wav)["duration"] == pytest.approx(song["length"], abs=0.02)
    assert merge.render_segment(pieces, song["length"], out_dir, cache.file_digest) == wav  # made once
    w = merge.waveform_peaks(wav, 50)
    assert w["duration"] == pytest.approx(song["length"], abs=0.02)
    assert max(w["peaks"][:45]) < 3 and min(w["peaks"][55:100]) > 15  # silence for 1 s, then the tone (-18 dB)
    r = analyze(p, store)
    for sid, secs, ov in (("s_one", 8.0, 0), ("s_long", 32.0, 39), ("s_short", 2.5, 0)):
        _take(store, r, sid, secs, ov)
    store.autosave(p)
    out = assemble.merge_project(analyze(p, store), store)
    assert out["soundtrack"] == 1
    assert out["duration"] == pytest.approx(scene_starts(p)[1], abs=0.01)
    info = merge.probe(store.output_path(out["files"]["video"]))
    assert info["has_audio"] and info["duration"] == pytest.approx(out["duration"], abs=0.1)
    # scene sound is off by default: the cut is silent until the song starts at 1 s, then it is the song
    w = merge.waveform_peaks(store.output_path(out["files"]["video"]), 50)
    assert max(w["peaks"][:45]) < 3 and min(w["peaks"][60:1200]) > 15
    assert max(w["peaks"][int(26 * 50):int(30 * 50)]) < 3  # the 30 s file ran out 25 s in (in = 5 s)


@needs_ffmpeg
def test_scene_sound_under_ducked_and_looped_tracks_runs(tmp_path):
    a = _clip(str(tmp_path / "a.mp4"), 3)
    b = _clip(str(tmp_path / "b.mp4"), 3, audio=False)
    song = _tone(str(tmp_path / "song.wav"), 4)
    bed = _tone(str(tmp_path / "bed.wav"), 1.5, 330)
    segs = [{"path": a, "in": 0, "out": 3, "has_audio": True, "join": "first", "dur": 0, "vfade_out": 0.25},
            {"path": b, "in": 0, "out": 3, "has_audio": False, "join": "cut", "dur": 0, "vfade_in": 0.25},
            {"path": None, "in": 0, "out": 1, "join": "cut", "dur": 0}]
    tracks = [{"path": song, "start": -0.5, "in": 0.0, "length": 4.0, "fade_out": 0.5, "duck": True},
              {"path": bed, "start": 2.0, "in": 0.0, "length": 1.5, "loop": True, "volume_db": -6.0}]
    out = str(tmp_path / "o.mp4")
    starts, total = merge.join(segs, out, 160, 90, loudness=-16.0, tracks=tracks,
                               scene_audio={"mix": True, "volume_db": -12.0})
    assert total == 7 and merge.probe(out)["duration"] == pytest.approx(7, abs=0.1)
    w = merge.waveform_peaks(out, 50)
    assert min(w["peaks"][10:150]) > 5  # song from the first frame (its first half second is before the film)


# ---- added 2026-11-03 v0.6.0: soundtrack in the side files, stems, the pass excerpt, old profiles ------------------

@needs_ffmpeg
def test_range_merge_exports_the_soundtrack_where_it_plays(harbor, store, roots):
    import json
    import xml.etree.ElementTree as ET
    song_rel = "reelwright/harbor_lights/song.wav"
    _tone(os.path.join(roots.input, song_rel), 60)
    p = copy.deepcopy(harbor)
    p["assets"].append({"id": "a_song", "kind": "audio", "name": "song", "file": song_rel, "duration": 60.0})
    p["soundtrack"] = [{"asset": "a_song", "start": 1.0, "in": 5.0}]
    p["markers"] = [{"id": "m_1", "t": 39.0, "text": "door", "color": "green"}, {"id": "m_2", "t": 3.0, "text": "early"}]
    p = normalize_project(p)
    tid = p["soundtrack"][0]["id"]
    r = analyze(p, store)
    _take(store, r, "s_short", 2.5)
    store.autosave(p)
    out = assemble.merge_project(analyze(p, store), store,
                                 options={"range": ["s_short", "s_short"], "draft": True, "stems": True})
    offset = scene_starts(p)[0]["s_short"]
    assert out["duration"] == pytest.approx(2.5, abs=0.01)
    stems = store.output_path(out["files"]["stems"])
    assert sorted(os.listdir(stems)) == sorted(["mix.wav", "scenes.wav", "track_{}.wav".format(tid)])
    assert out["loudness"]["track_{}".format(tid)]["integrated"] is not None
    doc = json.load(open(store.output_path(out["files"]["otio"])))
    st = [t for t in doc["tracks"]["children"] if t["name"].startswith("Soundtrack")][0]
    clip0 = st["children"][0]
    assert clip0["OTIO_SCHEMA"] == "Clip.2"  # the song already plays when the range starts
    assert clip0["source_range"]["start_time"]["value"] == round((5.0 + offset - 1.0) * 24)
    assert [m["name"] for m in doc["tracks"]["markers"]] == ["door"]
    assert doc["tracks"]["markers"][0]["marked_range"]["start_time"]["value"] == round((39.0 - offset) * 24)
    root = ET.parse(store.output_path(out["files"]["fcpxml"])).getroot()
    conn = root.find(".//spine/asset-clip/asset-clip")
    assert conn is not None and conn.get("lane") == "-1"
    assert conn.get("start") == "{}/24s".format(round((5.0 + offset - 1.0) * 24))


@needs_ffmpeg
def test_pass_excerpt_is_the_file_a_render_sends(harbor, store, roots):
    song_rel = "reelwright/harbor_lights/song.wav"
    _tone(os.path.join(roots.input, song_rel), 30)
    p = copy.deepcopy(harbor)
    p["assets"].append({"id": "a_song", "kind": "audio", "name": "song", "file": song_rel, "duration": 30.0})
    p["soundtrack"] = [{"asset": "a_song", "start": 1.0, "in": 5.0}]
    p = normalize_project(p)
    r = analyze(p, store)
    song, path = assemble.pass_song(r, store, "s_one", 1)
    assert song == next(a["song"] for a in r["scenes"]["s_one"]["builds"][0]["audios"] if a.get("song"))
    assert os.path.dirname(path) == os.path.join(store.dir, "soundtrack")
    pieces = [{"path": os.path.join(roots.input, x["file"]), "src_in": x["src_in"], "src_out": x["src_out"],
               "at": x["at"]} for x in song["pieces"]]
    assert merge.render_segment(pieces, song["length"], os.path.join(store.dir, "soundtrack"), cache.file_digest) == path
    assert merge.probe(path)["duration"] == pytest.approx(song["length"], abs=0.02)
    with pytest.raises(ValueError):
        assemble.pass_song(r, store, "s_one", 9)
    p["soundtrack"][0]["start"] = 500.0  # after the film: no pass hears it
    assert assemble.pass_song(analyze(p, store), store, "s_one", 1) == (None, None)


def test_old_profile_does_not_bring_the_score_back(roots):
    from reelwright import profiles
    from reelwright.model import default_global
    from reelwright.storage import write_json
    g = default_global()
    g["merge"]["score"] = {"asset": "a_bed", "volume_db": -9.0, "duck": True}
    g["merge"].pop("scene_audio", None)
    write_json(profiles.profiles_path(roots.user), {"profiles": [{"id": "g_1", "name": "old", "global": g}],
                                                    "default": "g_1"})
    got = profiles.load(roots.user)["profiles"][0]["global"]["merge"]
    assert got["score"]["asset"] == "" and got["scene_audio"] == {"mix": True, "volume_db": 0.0}
    saved = profiles.save(roots.user, "again", g)["profile"]["global"]["merge"]
    assert saved["score"]["asset"] == ""
