import json
import os
import subprocess
import xml.etree.ElementTree as ET

import pytest

from reelwright import assemble, merge
from reelwright.analysis import analyze

pytestmark = pytest.mark.skipif(merge.ffmpeg_bin() is None, reason="ffmpeg not installed")


def clip(path, seconds, color="testsrc2", audio=True):
    args = [merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "{}=s=320x180:r=24:d={}".format(color, seconds)]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=f=440:sample_rate=32000:d={}".format(seconds), "-ac", "2"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else []) + ["-shortest", path]
    subprocess.run(args, check=True)
    return path


def test_timeline_math():
    segs = [{"in": 0, "out": 8, "join": "first", "dur": 0},
            {"in": 1.125, "out": 10, "join": "xfade", "dur": 0.5},
            {"in": 0, "out": 4, "join": "cut", "dur": 0}]
    starts, total = merge.plan_timeline(segs)
    assert starts == [0, 7.5, 16.375]
    assert total == pytest.approx(20.375)


def test_join_cut_xfade_dip_and_slate(tmp_path):
    a = clip(str(tmp_path / "a.mp4"), 3)
    b = clip(str(tmp_path / "b.mp4"), 4, "smptebars")
    c = clip(str(tmp_path / "c.mp4"), 2, "rgbtestsrc", audio=False)
    segs = [{"path": a, "in": 0, "out": 3, "has_audio": True, "join": "first", "dur": 0},
            {"path": b, "in": 1.125, "out": 4, "has_audio": True, "join": "xfade", "dur": 0.5},
            {"path": c, "in": 0, "out": 2, "has_audio": False, "join": "dip", "dur": 0.25},
            {"path": None, "in": 0, "out": 1, "join": "cut", "dur": 0},
            {"path": a, "in": 0.5, "out": 2.5, "has_audio": True, "join": "cut", "dur": 0}]
    out = str(tmp_path / "cut.mp4")
    chapters = str(tmp_path / "ch.txt")
    merge.write_chapters([{"title": "One", "start": 0}, {"title": "Two", "start": 2.5}], 9.125, chapters)
    seen = []
    starts, total = merge.join(segs, out, 320, 180, progress=seen.append, loudness=-16.0, chapters_file=chapters)
    info = merge.probe(out)
    assert info["has_audio"] and info["width"] == 320
    assert info["duration"] == pytest.approx(total, abs=0.1)
    assert total == pytest.approx(3 + 2.875 - 0.5 + 2 - 0.25 + 1 + 2)
    meta = subprocess.run([merge.ffprobe_bin(), "-v", "error", "-show_chapters", "-of", "json", out],
                          capture_output=True, text=True, check=True).stdout
    assert len(json.loads(meta)["chapters"]) == 2


def test_score_ducking_and_color_gains(tmp_path):
    a = clip(str(tmp_path / "a.mp4"), 3)
    b = clip(str(tmp_path / "b.mp4"), 3, "smptebars")
    score = str(tmp_path / "score.wav")
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "sine=f=220:d=2", score], check=True)
    segs = [{"path": a, "in": 0, "out": 3, "has_audio": True, "join": "first", "dur": 0},
            {"path": b, "in": 0, "out": 3, "has_audio": True, "join": "cut", "dur": 0}]
    gains = merge.color_gains(segs, 0)
    assert gains[0] == pytest.approx((1.0, 1.0, 1.0))
    assert all(0.8 <= g <= 1.25 for g in gains[1])
    for s, g in zip(segs, gains):
        s["gain"] = g
    out = str(tmp_path / "scored.mp4")
    _, total = merge.join(segs, out, 320, 180, score={"path": score, "volume_db": -12, "duck": True})
    assert merge.probe(out)["duration"] == pytest.approx(total, abs=0.1)


def test_side_files(tmp_path):
    entries = [{"scene_id": "s_1", "title": "01 One", "path": str(tmp_path / "a.mp4"), "start": 0.0,
                "src_in": 0.0, "src_out": 8.0, "src_len": 8.0,
                "dialogue": [{"t": 1.0, "speaker": "Mara", "text": "Is anyone there?"},
                             {"t": 1.5, "speaker": "Mara", "text": "Hello?"}]},
               {"scene_id": "s_2", "title": "02 Two & more", "path": str(tmp_path / "b.mp4"), "start": 7.5,
                "src_in": 1.125, "src_out": 10.0, "src_len": 10.0,
                "dialogue": [{"t": 0.5, "speaker": "", "text": "in the overlap"},
                             {"t": 3.0, "speaker": "Keeper", "text": "Get inside!"}]}]
    cues = merge.subtitle_cues(entries)
    assert [c[2] for c in cues] == ["Mara: Is anyone there?", "Mara: Hello?", "Keeper: Get inside!"]
    assert cues[0][1] <= 1.45  # cut short before the next line
    assert cues[2][0] == pytest.approx(7.5 + 3.0 - 1.125)
    srt = tmp_path / "x.srt"
    assert merge.write_srt(entries, str(srt)) == 3
    assert "00:00:01,000 --> " in srt.read_text()
    otio = tmp_path / "x.otio"
    merge.write_otio("Film", entries, str(otio))
    doc = json.loads(otio.read_text())
    assert doc["OTIO_SCHEMA"] == "Timeline.1" and len(doc["tracks"]["children"]) == 4
    fcp = tmp_path / "x.fcpxml"
    merge.write_fcpxml("Film", entries, 16.375, 1344, 768, str(fcp))
    root = ET.parse(str(fcp)).getroot()
    clips = root.findall(".//asset-clip")
    assert [c.get("offset") for c in clips] == ["0/24s", "180/24s"]
    assert clips[0].get("duration") == "180/24s"


def test_merge_project_end_to_end(harbor, store, roots):
    r = analyze(harbor, store)
    for sid, secs in (("s_one", 8.0), ("s_long", 4.0), ("s_short", 2.5)):
        d = store.take_dir(sid, "v1")
        os.makedirs(d)
        clip(os.path.join(d, "video.mp4"), secs)
        store.add_take(sid, {"id": "v1", "key": r["scenes"][sid]["key"], "seconds": secs,
                             "overlap_frames": 39 if sid == "s_long" else 0,
                             "files": {"video": store.rel_output(os.path.join(d, "video.mp4"))}})
    harbor["global"]["merge"].update(otio=True, fcpxml=True, subtitles=True, chapters=True, bundle=True)
    store.autosave(harbor)
    out = assemble.merge_project(analyze(harbor, store), store)
    # 8 + (4 - 39/24) + 2.5, continuation crossfade happens inside the overlap
    assert out["duration"] == pytest.approx(8 + 4 - 39 / 24 + 2.5, abs=0.01)
    for k in ("video", "srt", "otio", "fcpxml", "chapters", "bundle"):
        assert os.path.isfile(store.output_path(out["files"][k])), k
    assert merge.probe(store.output_path(out["files"]["video"]))["duration"] == pytest.approx(out["duration"], abs=0.1)


def test_missing_scene_policies(harbor, store):
    r = analyze(harbor, store)
    d = store.take_dir("s_one", "v1")
    os.makedirs(d)
    clip(os.path.join(d, "video.mp4"), 3)
    store.add_take("s_one", {"id": "v1", "key": r["scenes"]["s_one"]["key"], "seconds": 3.0,
                             "files": {"video": store.rel_output(os.path.join(d, "video.mp4"))}})
    harbor["global"]["merge"]["missing"] = "block"
    with pytest.raises(merge.MergeError):
        assemble.cut_plan(analyze(harbor, store), store)
    harbor["global"]["merge"]["missing"] = "slate"
    segs, entries, skipped = assemble.cut_plan(analyze(harbor, store), store)
    assert [s.get("path") is None for s in segs] == [False, True, True]
    assert skipped == ["s_long", "s_short"]


def test_pass_segments_for_long_scene(harbor):
    from reelwright.planner import plan_scene
    plan = plan_scene(harbor, harbor["scenes"][1], 1)
    segs = assemble.pass_segments(plan, ["p{}.mp4".format(x["index"]) for x in plan["passes"]], 12)
    _, total = merge.plan_timeline(segs)
    assert total == pytest.approx(32.0, abs=1 / 24)


# added 2026-11-02 v0.2.1: ffmpeg 8 lets aac take any channel layout, so the last audio link must be pinned
def test_final_audio_link_is_pinned_to_stereo(tmp_path):
    segs = [{"path": "a.mp4", "in": 0, "out": 2, "has_audio": True, "join": "first", "dur": 0}]
    for loudness in (-16.0, None):
        args, _, _ = merge.build_command(segs, str(tmp_path / "o.mp4"), 320, 180, loudness=loudness)
        graph = args[args.index("-filter_complex") + 1]
        last = [x for x in graph.split(";") if x.endswith("[aout]")][0]
        assert "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]" in last
        assert args[args.index("-ac") + 1] == "2"


def test_failed_join_leaves_no_cut_and_probe_raises(tmp_path):
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(merge.MergeError):
        merge.probe(str(bad))
    out = tmp_path / "cut_v1.mp4"
    segs = [{"path": str(bad), "in": 0, "out": 2, "has_audio": True, "join": "first", "dur": 0}]
    with pytest.raises(merge.MergeError):
        merge.join(segs, str(out), 320, 180, loudness=-16.0)
    assert not out.exists() and not (tmp_path / "cut_v1.partial.mp4").exists()


# added 2026-11-02 v0.3.0: each scene chooses the transition into it
def test_per_scene_transition(harbor, store, roots):
    a = clip(os.path.join(roots.output, "a.mp4"), 3)
    b = clip(os.path.join(roots.output, "b.mp4"), 3, "smptebars")
    c = clip(os.path.join(roots.output, "c.mp4"), 3, "rgbtestsrc")
    p = harbor
    for s in p["scenes"]:
        s["start"]["mode"] = "fresh"
    p["global"]["merge"].update(hard_cut="cut", transition_frames=12, audio_fade_frames=6, missing="block")
    p["scenes"][1]["transition"] = {"mode": "dip", "frames": 24, "audio_fade_frames": None}
    p["scenes"][2]["transition"] = {"mode": "", "frames": None, "audio_fade_frames": 0}
    for s in p["scenes"]:  # added 2026-11-05 v0.7.0: a v0.6.1 project; scene.merge is built from these on load
        s.pop("merge", None)
    takes = {}
    for s, path in zip(p["scenes"], (a, b, c)):
        store.add_take(s["id"], {"id": "v1", "key": "k", "files": {"video": os.path.relpath(path, roots.output)}, "seconds": 3.0})
    segs, _, _ = assemble.cut_plan(analyze(p, store), store)
    assert [x["join"] for x in segs] == ["first", "dip", "cut"]
    assert segs[1]["dur"] == pytest.approx(1.0)
    assert segs[2]["fade"] == 0
    args, _, _ = merge.build_command(segs, "o.mp4", 64, 32, audio_fade_frames=6)
    graph = args[args.index("-filter_complex") + 1]
    a1 = [x for x in graph.split(";") if x.endswith("[a1]")][0]
    assert "afade=t=out" not in a1  # scene 3 asked for no fade at its cut


# ---- added 2026-11-03 v0.6.0 ---------------------------------------------------------------------------------------

import sys  # noqa: E402
import time  # noqa: E402

from reelwright import jobs  # noqa: E402
from reelwright.model import normalize_project  # noqa: E402


def frame_count(path):
    r = subprocess.run([merge.ffprobe_bin(), "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return int(r.stdout.strip())


def audio_seconds(path):
    r = subprocess.run([merge.ffprobe_bin(), "-v", "error", "-select_streams", "a:0", "-show_entries",
                        "stream=duration", "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    return {"a": clip(str(d / "a.mp4"), 3), "b": clip(str(d / "b.mp4"), 3, "smptebars"),
            "c": clip(str(d / "c.mp4"), 4, "rgbtestsrc"), "p": clip(str(d / "p.mp4"), 6)}


def _check_join(tmp_path, segs, name):
    out = str(tmp_path / (name + ".mp4"))
    _, total = merge.join(segs, out, 160, 90)
    assert frame_count(out) == round(total * 24), name
    assert audio_seconds(out) == pytest.approx(total, abs=0.03), name
    return total


def test_transitions_after_a_cut_keep_every_frame(tmp_path, clips):
    """Fix #1: concat outputs timebase 1/1000000 and a later xfade needs 1/24 ("Failed to inject frame")."""
    a, b, c = clips["a"], clips["b"], clips["c"]
    first = {"path": a, "in": 0, "out": 3, "has_audio": True, "join": "first", "dur": 0}
    cut = {"path": b, "in": 0, "out": 3, "has_audio": True, "join": "cut", "dur": 0}
    # scene 1 fresh -> scene 2 last_frame (cut) -> scene 3 tail (crossfade inside the overlap)
    t = _check_join(tmp_path, [first, dict(cut, **{"in": 1 / 24}),
                               {"path": c, "in": 27 / 24, "out": 4, "has_audio": True, "join": "xfade", "dur": 0.5}],
                    "cut_xfade")
    assert t == pytest.approx(3 + 3 - 1 / 24 + 4 - 27 / 24 - 0.5)
    _check_join(tmp_path, [first, cut, {"path": c, "in": 0, "out": 4, "has_audio": False, "join": "dip", "dur": 0.5}],
                "cut_dip")
    # a slate (missing scene) followed by a tail scene
    _check_join(tmp_path, [first, {"path": None, "in": 0, "out": 1.0, "join": "cut", "dur": 0},
                           {"path": c, "in": 0.5, "out": 4, "has_audio": True, "join": "xfade", "dur": 0.5}],
                "slate_tail")


def test_long_scene_passes_with_a_cut_then_an_overlap_seam(tmp_path, clips):
    p = clips["p"]
    plan = {"passes": [
        {"index": 1, "keep_in": 0.0, "keep_out": 124 / 24, "seam_before": "none", "overlap_frames": 0},
        {"index": 2, "keep_in": 0.0, "keep_out": 124 / 24, "seam_before": "cut", "overlap_frames": 0},
        {"index": 3, "keep_in": 0.0, "keep_out": 124 / 24, "seam_before": "overlap", "overlap_frames": 22}]}
    segs = assemble.pass_segments(plan, [p, p, p], 12)
    assert [s["join"] for s in segs] == ["first", "cut", "xfade"]
    total = _check_join(tmp_path, segs, "passes")
    assert round(total * 24) == 124 * 3 - 22


def test_run_ffmpeg_drains_a_chatty_stderr(tmp_path):
    code = ("import sys\nfor i in range(2000):\n    sys.stderr.write('x' * 200 + '\\n')\n"
            "print('out_time_us=500000', flush=True)\nsys.exit(3)\n")
    with pytest.raises(merge.MergeError) as e:
        merge.run_ffmpeg([sys.executable, "-c", code])  # 400 KB of stderr before stdout: hung before v0.6.0
    assert "xxxx" in str(e.value) and len(str(e.value)) < 2100
    seen = []
    out = merge.run_ffmpeg([sys.executable, "-c", "import sys; sys.stderr.write('y' * 300000); "
                            "print('out_time_us=1000000', flush=True); import time; time.sleep(0.5)"],
                           total=2.0, progress=seen.append)
    assert out.endswith("y" * 10) and seen and seen[-1] == 1.0 and 0.5 in seen


def test_run_ffmpeg_cancel_and_interrupt_kill_ffmpeg():
    ff = merge.ffmpeg_bin()
    args = [ff, "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc2=s=64x36:r=24:d=30",
            "-f", "null", "-"]
    t0 = time.time()
    with pytest.raises(merge.MergeCancelled):
        merge.run_ffmpeg(args, cancel=lambda: time.time() - t0 > 0.5)
    assert time.time() - t0 < 5

    class Interrupted(Exception):
        pass

    def interrupt():
        if time.time() - t0 > 0.3:
            raise Interrupted()
        return False
    t0 = time.time()
    with pytest.raises(Interrupted):
        merge.run_ffmpeg(args, cancel=interrupt)
    assert time.time() - t0 < 5


def test_the_filter_graph_goes_in_a_file(tmp_path, clips):
    segs = [{"path": clips["a"], "in": 0, "out": 1, "has_audio": True, "join": "first", "dur": 0}]
    args, _, _ = merge.build_command(segs, str(tmp_path / "o.mp4"), 64, 32)
    graph = args[args.index("-filter_complex") + 1]
    new, script = merge._graph_to_file(args)
    try:
        flag = merge.script_flag(merge.ffmpeg_bin())
        assert flag in ("-filter_complex_script", "-/filter_complex")
        assert "-filter_complex" not in new and new[new.index(flag) + 1] == script
        assert open(script, encoding="utf-8").read() == graph
    finally:
        os.remove(script)
    before = set(os.listdir(os.path.dirname(script)))
    merge.run_ffmpeg(args)
    assert not [x for x in set(os.listdir(os.path.dirname(script))) - before if x.startswith("rw_graph_")]
    assert os.path.isfile(str(tmp_path / "o.mp4"))


def test_subtitles_last_frame_line_and_blank_lines():
    entries = [{"scene_id": "s_2", "title": "02", "path": "x.mp4", "start": 5.0, "src_in": 1 / 24, "src_out": 4.0,
                "src_len": 4.0, "dialogue": [{"t": 0.0, "speaker": "Mara", "text": "First line\n\n  second part\r\n"},
                                             {"t": 2.0, "speaker": "", "text": "\n \n"}]}]
    cues = merge.subtitle_cues(entries)
    assert cues == [(5.0, pytest.approx(5.0 + 0.6 + 0.07 * len("Mara: First line\nsecond part")),
                     "Mara: First line\nsecond part")]


def test_otio_positions_are_whole_frames_from_the_start():
    entries = [{"scene_id": "s_{}".format(k), "title": "{:02d}".format(k), "path": "/x/{}.mp4".format(k),
                "start": st, "src_in": si, "src_out": so, "src_len": so, "dialogue": []}
               for k, (st, si, so) in enumerate([(0.0, 0.0, 7.52), (7.0208, 1.1, 9.0), (14.9208, 0.0, 3.3),
                                                 (18.2208, 0.04, 5.51), (23.69, 0.0, 2.02)])]
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "x.otio")
    merge.write_otio("Film", entries, path, total=25.71)
    doc = json.load(open(path))
    for tr in doc["tracks"]["children"]:
        pos = 0
        sub = [e for i, e in enumerate(entries) if i % 2 == (0 if tr["name"].endswith("A") else 1)]
        k = 0
        for ch in tr["children"]:
            if ch["OTIO_SCHEMA"] == "Clip.2":
                assert pos == merge._frames(sub[k]["start"]), (tr["name"], k)
                k += 1
            pos += int(ch["source_range"]["duration"]["value"])
        assert k == len(sub)


def test_fcpxml_gaps_quotes_soundtrack_and_markers(tmp_path):
    title = 'He said "go" & ran <fast>'
    entries = [{"scene_id": "s_1", "title": title, "path": str(tmp_path / 'a "b".mp4'), "start": 0.0, "src_in": 0.0,
                "src_out": 3.0, "src_len": 3.0, "dialogue": []},
               {"scene_id": "s_2", "title": "02 Two", "path": str(tmp_path / "b.mp4"), "start": 4.0, "src_in": 0.5,
                "src_out": 3.5, "src_len": 4.0, "dialogue": []}]
    tracks = [{"id": "t_1", "code": "A9", "path": str(tmp_path / "song.wav"), "start": 0.5, "in": 2.0, "length": 5.0,
               "loop": False, "volume_db": -6.0, "file_duration": 30.0}]
    markers = [{"t": 1.0, "text": 'drop "here"', "color": "amber"}, {"t": 3.5, "text": "in the gap", "color": "blue"}]
    path = str(tmp_path / "x.fcpxml")
    merge.write_fcpxml('Film "One"', entries, 7.0, 160, 90, path, tracks=tracks, markers=markers)
    root = ET.parse(path).getroot()
    spine = root.find(".//spine")
    kids = list(spine)
    assert [k.tag for k in kids] == ["asset-clip", "gap", "asset-clip"]
    assert [(k.get("offset"), k.get("duration")) for k in kids] == [("0/24s", "72/24s"), ("72/24s", "24/24s"),
                                                                     ("96/24s", "72/24s")]
    assert kids[0].get("name") == title and kids[2].get("start") == "12/24s"
    song = kids[0].find("asset-clip")
    assert song.get("lane") == "-1" and song.get("offset") == "12/24s" and song.get("start") == "48/24s"
    assert song.get("duration") == "120/24s" and song.find("adjust-volume").get("amount") == "-6.00dB"
    assert kids[0].find("marker").get("value") == 'drop "here"' and kids[0].find("marker").get("start") == "24/24s"
    assert kids[1].find("marker").get("start") == "12/24s"
    assert root.find(".//project").get("name") == 'Film "One"'
    otio = str(tmp_path / "x.otio")
    merge.write_otio("Film", entries, otio, tracks=tracks, markers=markers, total=7.0)
    doc = json.load(open(otio))
    st = [t for t in doc["tracks"]["children"] if t["name"] == "Soundtrack A9"][0]
    assert [c["OTIO_SCHEMA"] for c in st["children"]] == ["Gap.1", "Clip.2"]
    assert st["children"][0]["source_range"]["duration"]["value"] == 12
    assert st["children"][1]["source_range"]["start_time"]["value"] == 48
    mk = doc["tracks"]["markers"]
    assert [(m["name"], m["color"], m["marked_range"]["start_time"]["value"]) for m in mk] == [
        ('drop "here"', "ORANGE", 24), ("in the gap", "BLUE", 84)]


def _chain_project(harbor):
    p = harbor
    p["global"]["continuity"]["reanchor_after"] = 1
    p["global"]["long"]["crossfade_frames"] = 12
    p["scenes"] = [
        dict(p["scenes"][0], id="s_a", title="A", duration=3.0),
        {"id": "s_b", "title": "B", "duration": 3.0, "start": {"mode": "tail", "overlap_frames": 22}},
        {"id": "s_c", "title": "C", "duration": 3.0, "start": {"mode": "tail", "overlap_frames": 22}},  # re-anchored
        {"id": "s_d", "title": "D", "duration": 1.5, "start": {"mode": "fresh"}},
        {"id": "s_e", "title": "E", "duration": 3.0, "start": {"mode": "tail", "overlap_frames": 73}},  # capped by D
    ]
    return normalize_project(p)


def test_cut_plan_trims_by_how_each_scene_really_starts(harbor, store, roots, clips):
    import shutil
    p = _chain_project(harbor)
    video = os.path.join(roots.output, "c.mp4")
    shutil.copyfile(clips["c"], video)
    for s in p["scenes"]:
        store.add_take(s["id"], {"id": "v1", "seconds": float(s["duration"]),
                                 "overlap_frames": 22,  # what an old take may claim
                                 "files": {"video": "c.mp4"}})
    r = analyze(p, store)
    assert r["scenes"]["s_c"]["plan"]["start_mode"] == "last_frame"
    segs, entries, _ = assemble.cut_plan(r, store)
    assert [s["join"] for s in segs] == ["first", "xfade", "cut", "cut", "xfade"]
    assert segs[1]["in"] == pytest.approx(10 / 24) and segs[1]["dur"] == pytest.approx(0.5)
    assert segs[2]["in"] == pytest.approx(1 / 24)  # re-anchored: one repeated frame, not a crossfade
    assert segs[4]["in"] == pytest.approx((22 - 12) / 24)  # 73 frames capped by D (36 frames -> 22)
    from reelwright.model import scene_starts
    p["soundtrack"] = []
    _, total = merge.plan_timeline(segs)
    assert total == pytest.approx(scene_starts(p)[1], abs=1e-6)  # the cut is as long as the timeline says


def test_merge_draft_range_and_stems(harbor, store, roots):
    r = analyze(harbor, store)
    for sid, secs in (("s_one", 3.0), ("s_long", 4.0), ("s_short", 2.5)):
        d = store.take_dir(sid, "v1")
        os.makedirs(d, exist_ok=True)
        clip(os.path.join(d, "video.mp4"), secs)
        store.add_take(sid, {"id": "v1", "key": r["scenes"][sid]["key"], "seconds": secs,
                             "files": {"video": store.rel_output(os.path.join(d, "video.mp4"))}})
    harbor["global"]["merge"].update(otio=True, fcpxml=True, subtitles=True, chapters=True, bundle=True)
    store.autosave(harbor)
    out = assemble.merge_project(analyze(harbor, store), store,
                                 options={"draft": True, "range": ["s_short", "s_long"], "stems": True})
    assert out["files"]["video"].endswith("harbor_lights_cut_v1_draft_s02-03.mp4") and out["draft"]
    assert out["range"] == ["s_long", "s_short"]
    assert out["duration"] == pytest.approx(4 - 39 / 24 + 2.5, abs=0.01)  # the tail scene's repeat is trimmed
    video = store.output_path(out["files"]["video"])
    info = merge.probe(video)
    assert (info["width"], info["height"]) == (672, 384)
    stems = store.output_path(out["files"]["stems"])
    assert sorted(os.listdir(stems)) == ["mix.wav", "scenes.wav"]
    assert merge.probe(os.path.join(stems, "mix.wav"))["duration"] == pytest.approx(out["duration"], abs=0.05)
    loud = out["loudness"]
    assert loud["integrated"] == pytest.approx(-16, abs=2.5) and loud["true_peak"] is not None
    assert set(loud["mix"]) == {"integrated", "lra", "true_peak"} and "scenes" in loud
    assert json.load(open(store.output_path(out["files"]["loudness"])))["integrated"] == loud["integrated"]
    import zipfile
    names = zipfile.ZipFile(store.output_path(out["files"]["bundle"])).namelist()
    assert "stems/mix.wav" in names and "project.json" in names
    from reelwright import files
    tree = files.scan(roots, "harbor_lights")
    cut = [c for c in tree["projects"][0]["children"] if c["label"] == "Merged cuts"][0]["children"][0]
    assert cut["label"] == "cut v1 draft range" and any(c["label"] == "stems" for c in cut["children"])
    r = files.delete(roots, [cut["id"]], current="harbor_lights")
    assert r["errors"] == [] and sorted(os.listdir(store.cuts_dir())) == [".next"]


def test_one_merge_per_project_and_cancel(harbor, store, roots):
    r = analyze(harbor, store)
    d = store.take_dir("s_one", "v1")
    os.makedirs(d, exist_ok=True)
    clip(os.path.join(d, "video.mp4"), 3)
    store.add_take("s_one", {"id": "v1", "key": r["scenes"]["s_one"]["key"], "seconds": 3.0,
                             "files": {"video": store.rel_output(os.path.join(d, "video.mp4"))}})
    with jobs.exclusive(store.slug, "merge", "other"):
        with pytest.raises(merge.MergeBusy):
            assemble.merge_project(analyze(harbor, store), store)
    calls = []

    def progress(x):  # cancel as soon as ffmpeg reports progress
        calls.append(x)
        jobs.cancel("job-x")
    with pytest.raises(merge.MergeCancelled):
        assemble.merge_project(analyze(harbor, store), store, progress=progress, job_id="job-x")
    assert calls and not jobs.is_busy(store.slug)
    assert sorted(os.listdir(store.cuts_dir())) == [".next"]  # the chapters file and the partial cut are gone
    out = assemble.merge_project(analyze(harbor, store), store)
    assert out["files"]["video"].endswith("_cut_v2.mp4")  # the cancelled merge's number is not reused


# ---- added 2026-11-03 v0.6.0 review --------------------------------------------------------------------------------

from reelwright.model import scene_starts  # noqa: E402


def _locked_film(harbor, store, roots, take_frames, n=10, seconds=7.3):
    """n scenes of `seconds` (not whole frames: 7.3 s = 175.2 frames) on a soundtrack, every take `take_frames`."""
    p = harbor
    p["global"]["output"].update(width=64, height=32)
    p["scenes"] = [dict(p["scenes"][0], id="s_%d" % k, title="S%d" % k, duration=seconds, start={"mode": "fresh"},
                        dialogue=[], refs=[], cast=[]) for k in range(n)]
    song = os.path.join(roots.input, "reelwright", "harbor_lights", "song.wav")
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=f=220:d={}".format(n * seconds + 5), song], check=True)
    p["assets"].append({"id": "a_song", "kind": "audio", "code": "A9", "name": "song", "duration": n * seconds + 5,
                        "file": "reelwright/harbor_lights/song.wav"})
    p["soundtrack"] = [{"id": "t_1", "asset": "a_song", "start": 0.0}]
    p = normalize_project(p)
    clip(os.path.join(roots.output, "take.mp4"), take_frames / 24)
    for s in p["scenes"]:
        store.add_take(s["id"], {"id": "v1", "seconds": take_frames / 24, "frames": take_frames,
                                 "files": {"video": "take.mp4"}})
    return p


def _whole(x):
    return abs(x * 24 - round(x * 24)) < 1e-6


def test_locked_cut_is_planned_in_whole_frames_without_dark_flashes(harbor, store, roots):
    """Bug 1: ten 7.3 s scenes with 175-frame takes got 0.6-frame slates (each drawn as a whole dark frame) and the
    picture drifted from the song. Now every scene ends on the film frame round(end * 24); a take one frame short of
    its slot holds its last frame."""
    p = _locked_film(harbor, store, roots, 175)
    segs, entries, _ = assemble.cut_plan(analyze(p, store), store)
    assert all(s.get("path") for s in segs)  # no slate at all
    assert all(_whole(s["out"] - s["in"]) for s in segs)
    rows, total_f = merge.frame_timeline(segs)
    starts = scene_starts(p)[0]
    assert [r[0] + r[1] for r in rows] == [merge.frame_index(starts[s["id"]] + 7.3) for s in p["scenes"]]
    assert total_f == round(73 * 24) == 1752
    assert all(e["src_out"] <= e["src_len"] + 1e-9 for e in entries)  # a held frame is not in the side files' clip
    out = assemble.merge_project(analyze(p, store), store)
    video = store.output_path(out["files"]["video"])
    assert out["duration"] == pytest.approx(1752 / 24)
    assert frame_count(video) == 1752
    assert audio_seconds(video) == pytest.approx(1752 / 24, abs=0.03)


def test_locked_take_two_frames_short_gets_a_whole_frame_slate(harbor, store, roots):
    p = _locked_film(harbor, store, roots, 170, n=4)
    segs, _, _ = assemble.cut_plan(analyze(p, store), store)
    slates = [round((s["out"] - s["in"]) * 24, 6) for s in segs if not s.get("path")]
    assert slates and all(x >= 2 and x == int(x) for x in slates)
    assert all(_whole(s["out"] - s["in"]) for s in segs)
    assert merge.frame_timeline(segs)[1] == merge.frame_index(4 * 7.3)


def test_join_is_cumulative_frames_and_a_late_crossfade_keeps_every_frame(tmp_path, clips):
    """Bug 1: per-segment round(len * 24) frames drifted (8 x 7.3 s gave 1400 frames for 1401.6) and a crossfade
    after the drift dropped the rest of the picture (1400 frames instead of 1521)."""
    src = clip(str(tmp_path / "src.mp4"), 8)
    segs = [{"path": src, "in": 0.0, "out": 7.3, "has_audio": True, "join": "first" if k == 0 else "cut", "dur": 0.0}
            for k in range(8)]
    out = str(tmp_path / "cut.mp4")
    starts, total = merge.join(segs, out, 64, 32)
    assert total == pytest.approx(round(8 * 7.3 * 24) / 24) and frame_count(out) == round(8 * 7.3 * 24) == 1402
    assert starts[7] == pytest.approx(round(7 * 7.3 * 24) / 24)  # scene 8 starts on the frame its film time rounds to
    segs.append({"path": src, "in": 0.0, "out": 5.0, "has_audio": True, "join": "xfade", "dur": 1 / 24})
    starts, total = merge.join(segs, out, 64, 32)
    assert frame_count(out) == round(total * 24) == 1521
    assert audio_seconds(out) == pytest.approx(total, abs=0.03)


def test_slates_and_transitions_are_whole_frames():
    segs = [{"path": "a.mp4", "in": 0, "out": 1.0, "has_audio": False, "join": "first", "dur": 0},
            {"path": None, "in": 0, "out": 0.025, "join": "cut", "dur": 0},
            {"path": "a.mp4", "in": 0, "out": 1.0, "has_audio": False, "join": "xfade", "dur": 0.01}]
    rows, total_f = merge.frame_timeline(segs)
    # cumulative: each segment ends on round(exact end * 24); the 0.01 s crossfade is joined as a cut
    assert rows == [(0, 24, 0), (24, 1, 0), (25, 23, 0)] and total_f == 48 == round((2.025 - 0.01) * 24)
    args, starts, total = merge.build_command(segs, "o.mp4", 64, 32)
    graph = args[args.index("-filter_complex") + 1]
    assert "trim=end_frame=1,format=yuv420p,setsar=1[v1]" in graph  # the slate is exactly one frame
    assert "trim=end_frame=23," in graph
    assert "xfade" not in graph  # a crossfade under half a frame is a cut
    assert total == 48 / 24 and args[args.index("-t", args.index("-filter_complex")) + 1] == merge._f(48 / 24)


def test_range_merge_without_soundtrack_is_in_cut_time(harbor, store, roots):
    """Bug 4: a range merge without a soundtrack kept film time for its markers (a marker before the range was
    kept, at its film time). Subtitles and chapters are cut time too."""
    harbor["global"]["output"].update(width=64, height=32)
    r = analyze(harbor, store)
    for sid, secs in (("s_one", 8.0), ("s_long", 32.0), ("s_short", 2.5)):
        d = store.take_dir(sid, "v1")
        os.makedirs(d, exist_ok=True)
        subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=s=64x32:r=24:d={}".format(secs), "-f", "lavfi", "-i", "sine=d={}".format(secs),
                        "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                        os.path.join(d, "video.mp4")], check=True)
        store.add_take(sid, {"id": "v1", "key": r["scenes"][sid]["key"], "seconds": secs,
                             "files": {"video": store.rel_output(os.path.join(d, "video.mp4"))}})
    starts, _ = scene_starts(harbor)
    harbor["markers"] = [{"id": "m_in", "t": starts["s_short"] + 1.0, "text": "door"},
                         {"id": "m_out", "t": 3.0, "text": "pier"}]
    harbor["global"]["merge"].update(otio=True, fcpxml=True, subtitles=True, chapters=True, bundle=False)
    info = {}
    assemble.cut_plan(analyze(harbor, store), store, {"range": ["s_long", "s_short"]}, info)
    assert info["offset"] == pytest.approx(8.0)  # s_long starts at 6.375 and its 39-frame tail is trimmed off
    out = assemble.merge_project(analyze(harbor, store), store, options={"range": ["s_long", "s_short"]})
    doc = json.load(open(store.output_path(out["files"]["otio"])))
    marks = [(m["name"], m["marked_range"]["start_time"]["value"] / 24) for m in doc["tracks"]["markers"]]
    assert marks == [("door", pytest.approx(31.375))]  # 1 s into the insert; "pier" is before the range
    fcp = open(store.output_path(out["files"]["fcpxml"])).read()
    assert "pier" not in fcp and "door" in fcp
    srt = open(store.output_path(out["files"]["srt"])).read()
    assert "00:00:14,375 -->" in srt and "Almost home." in srt  # film 22.375 s - 8 s
    ch = open(store.output_path(out["files"]["chapters"])).read()
    assert "START=0\n" in ch and "START=30375\n" in ch


def test_scene_with_no_frame_of_its_own_is_left_out(harbor, store, roots, tmp_path):
    """Bug 10: a 1-frame scene with a last-frame start keeps no frame (its only frame repeats the scene before), and
    cut_plan raised MergeError for the whole merge. Same for a tail scene whose overlap is all of it when it starts
    the cut or its upstream is missing."""
    p = harbor
    p["global"]["output"].update(width=64, height=32)
    p["scenes"] = [{"id": "a", "title": "A", "duration": 1 / 24, "start": {"mode": "fresh"}},
                   {"id": "b", "title": "B", "duration": 1 / 24, "start": {"mode": "last_frame"}},
                   {"id": "c", "title": "C", "duration": 0.3, "start": {"mode": "last_frame"}},
                   {"id": "x", "title": "X", "duration": 2.0, "start": {"mode": "fresh"}},
                   {"id": "y", "title": "Y", "duration": 5 / 24, "start": {"mode": "tail", "overlap_frames": 5}},
                   {"id": "z", "title": "Z", "duration": 2.0, "start": {"mode": "tail", "overlap_frames": 5}}]
    p = normalize_project(p)
    for s in p["scenes"]:
        n = int(round(float(s["duration"]) * 24))
        d = store.take_dir(s["id"], "v1")
        os.makedirs(d, exist_ok=True)
        subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=s=64x32:r=24:d={}".format(n / 24), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                        "-t", str(n / 24), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        os.path.join(d, "video.mp4")], check=True)
        store.add_take(s["id"], {"id": "v1", "seconds": n / 24, "files": {"video": store.rel_output(
            os.path.join(d, "video.mp4"))}})
    r = analyze(p, store)
    assert assemble.scene_join(r, p, 1)[0] == "last_frame" and assemble.scene_join(r, p, 4) == ("tail", 5)
    segs, entries, skipped = assemble.cut_plan(r, store)
    assert [s.get("scene_id") for s in segs] == ["a", "c", "x", "y", "z"] and not skipped
    assert segs[1]["join"] == "cut" and segs[1]["in"] == pytest.approx(1 / 24)  # C still joins A (B was transparent)
    assert segs[3]["join"] == "xfade" and segs[3]["out"] - segs[3]["in"] == pytest.approx(segs[3]["dur"])
    out = assemble.merge_project(r, store)  # the xfade where Y is all transition works in ffmpeg
    # A 1 + C 6 + X 48 + Z 48 - 5 (Y's 5 frames lie in X's last 5 and Z crossfades over the same 5)
    assert frame_count(store.output_path(out["files"]["video"])) == round(out["duration"] * 24) == 1 + 6 + 48 + 43
    # the 5-frame tail scene Y first in the cut: left out, Z starts the cut
    segs, _, _ = assemble.cut_plan(r, store, {"range": ["y", "z"]})
    assert [s.get("scene_id") for s in segs] == ["z"] and segs[0]["in"] == pytest.approx(5 / 24)
    # ... and with its upstream X missing
    os.remove(store.output_path(assemble.pick_take(r["scenes"]["x"], "starred")["files"]["video"]))
    r = analyze(p, store)
    segs, _, skipped = assemble.cut_plan(r, store)
    assert [s.get("scene_id") for s in segs] == ["a", "c", "z"] and skipped == ["x"]
    assert segs[2]["join"] == "cut" and segs[2]["in"] == pytest.approx(5 / 24)
    # short and silent, normalised: loudnorm on under 3 s of silence gave NaN and the merge failed
    p["scenes"] = p["scenes"][:3]
    out = assemble.merge_project(analyze(p, store), store)
    assert frame_count(store.output_path(out["files"]["video"])) == round(out["duration"] * 24) == 7
