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
