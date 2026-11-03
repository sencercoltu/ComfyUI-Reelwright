"""Script import in parts (added 2026-11-03 v0.4.2)."""

from reelwright.scriptparts import split_script

ROW = "| {:02d} | 00:{:02d}:00 → 00:{:02d}:00 | 13.00 | Verse | L{} | A shot description long enough to look like a real row"


def rows(n):
    return "\n".join(ROW.format(i, i, i + 1, i) for i in range(1, n + 1))


def joined(parts):
    return ["\n".join(p) for p in parts]


def test_short_script_is_one_part_as_written():
    text = "A premise.\n\n" + rows(3)
    out = split_script(text, 3000)
    assert out["parts"] == [[text]] and out["notes"] == ""
    assert split_script(rows(60), 0)["parts"] == [[rows(60)]]
    assert split_script("   \n", 3000)["parts"] == []


def test_table_rows_are_blocks_and_the_premise_is_a_note():
    text = "Mara is a sailor singing the song from <audio 1>. No dialogue.\n\n" + rows(46)
    out = split_script(text, 3000)
    assert out["notes"].startswith("Mara is a sailor") and out["blocks"] == 46
    assert len(out["parts"]) == 2 and all(len(t) <= 3000 for t in joined(out["parts"]))
    assert sum(len(p) for p in out["parts"]) == 46
    assert out["parts"][0][0].startswith("| 01 |") and out["parts"][-1][-1].startswith("| 46 |")
    assert "Mara" not in "".join(joined(out["parts"]))


def test_table_heading_goes_to_the_notes():
    text = "| # | Time | Shot |\n|---|:---:|---|\n" + rows(40)
    out = split_script(text, 1500)
    assert out["notes"] == "Table columns:\n| # | Time | Shot |\n|---|:---:|---|"
    assert all(not b.startswith("|---") and "| # |" not in b for p in out["parts"] for b in p)
    assert out["blocks"] == 40


def test_screenplay_scenes_stay_whole():
    scenes = ["INT. ROOM {} - NIGHT\n\nMara walks in.\n\nMARA\nHello there, number {}.".format(i, i) for i in range(30)]
    out = split_script("\n\n".join(scenes), 600)
    assert out["blocks"] == 30 and out["notes"] == ""
    assert [b for p in out["parts"] for b in p] == scenes
    forced = split_script(".OSSUARY\nShe waits.\n\n.GRAVEYARD\nShe walks.\n\n" + "x" * 900, 500)
    assert forced["parts"][0] == [".OSSUARY\nShe waits."] and forced["parts"][1][0].startswith(".GRAVEYARD\nShe walks.")


def test_plain_prose_splits_at_paragraphs_and_huge_blocks_are_cut():
    prose = "\n\n".join(("Paragraph {} ".format(i)) * 30 for i in range(10))
    out = split_script(prose, 1000)
    assert out["notes"] == "" and all(len(t) <= 1000 for t in joined(out["parts"]))
    assert "\n\n".join(b for p in out["parts"] for b in p) == prose
    huge = "# Act one\n" + "\n".join("line {} of a very long act".format(i) for i in range(400))
    out = split_script(huge, 1000)
    assert out["blocks"] > 5 and all(len(b) <= 2000 for p in out["parts"] for b in p)


def test_a_long_premise_is_script_not_notes():
    premise = "\n\n".join("Backstory paragraph {}. ".format(i) * 20 for i in range(8))
    out = split_script(premise + "\n\n" + rows(10), 1500)
    assert out["notes"] == "" and out["parts"][0][0].startswith("Backstory paragraph 0")


# ---- added 2026-11-03 v0.4.3: imported scene length vs its shots ----
from reelwright.scriptparts import fit_scene, typical_shot  # noqa: E402


def test_shot_durations_set_the_starts_and_the_length():
    s = {"duration": 30, "shots": [{"t": 0, "duration": d} for d in (8.42, 8.42, 8.17, 6, 8.96, 8.04, 9, 11)]}
    note = fit_scene(s)
    assert [x["t"] for x in s["shots"]] == [0.0, 8.42, 16.84, 25.01, 31.01, 39.97, 48.01, 57.01]
    assert s["duration"] == 68.0417                              # 68.01 s up to a whole frame
    assert note == "length set from its shots (68.04 s; the LLM gave 30.00 s)"


def test_start_times_only_lengthen_the_scene():
    s = {"duration": 30, "shots": [{"t": t} for t in (0, 8.42, 16.59, 24.76, 33.76, 41.81, 50.81, 61.81)]}
    assert typical_shot([x["t"] for x in s["shots"]]) == 8.42
    assert fit_scene(s).startswith("lengthened to fit its shots (70.25 s")
    assert s["duration"] == 70.25
    ok = {"duration": 20, "shots": [{"t": 10}, {"t": 0}]}
    assert fit_scene(ok) == "" and [x["t"] for x in ok["shots"]] == [0.0, 10.0] and ok["duration"] == 20


def test_dialogue_and_missing_values():
    s = {"duration": 12, "shots": [{"t": 0}, {"t": 5}], "dialogue": [{"t": 11.8}]}
    assert fit_scene(s).startswith("lengthened to fit its dialogue") and s["duration"] == 13.8333
    s = {"title": "no timing"}
    assert fit_scene(s) == "" and "duration" not in s
    s = {"shots": [{"t": "x"}, {"t": 6}]}                       # no scene length: taken from the shots
    assert fit_scene(s) == "length taken from its shots" and s["duration"] == 12.0 and s["shots"][0]["t"] == 0.0
    s = {"duration": 10, "shots": [{"t": 0, "duration": 4}, {"t": 4}]}   # not every shot has a duration
    assert fit_scene(s) == "" and s["duration"] == 10
