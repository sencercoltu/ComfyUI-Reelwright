"""Script import in parts."""

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


# ---- imported scene length vs its shots -----------------------------
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


# ---- an opening scene before the first heading is not lost -----------------------------
def test_opening_scene_without_a_heading_is_the_first_block():
    scenes = ["INT. ROOM {} - NIGHT\n\nMara walks in.\n\nMARA\nHello there, number {}.".format(i, i) for i in range(12)]
    opening = "FADE IN:\n\nA dark harbor. Gulls cry over the water."
    out = split_script(opening + "\n\n" + "\n\n".join(scenes), 600)
    assert out["notes"] == "" and out["parts"][0][0] == opening and out["blocks"] == 13
    cue = "A dark harbor. Mara waits on the pier.\n\nMARA\nWhere is he?"
    out = split_script(cue + "\n\n" + "\n\n".join(scenes), 600)
    assert out["parts"][0][0] == cue and out["notes"] == ""


def test_premise_and_title_page_stay_notes():
    scenes = ["INT. ROOM {} - NIGHT\n\nMara walks in.\n\nMARA\nHello there, number {}.".format(i, i) for i in range(12)]
    title = "Title: Harbor Lights\nAuthor: Sencer\nDraft date: 2026-11-03"
    out = split_script(title + "\n\n" + "\n\n".join(scenes), 600)
    assert out["notes"] == title and out["parts"][0][0].startswith("INT. ROOM 0")
    premise = "A music video. Mara is a sailor singing the song. No dialogue."
    out = split_script(premise + "\n\n" + rows(46), 3000)
    assert out["notes"] == premise


def test_a_title_in_capitals_over_the_premise_stays_notes():
    """Bug 9: "HARBOR LIGHTS" over a line of premise counted as a character cue, so the premise became an opening
    scene the LLM was asked to make scenes from, and no part got it as notes."""
    scenes = ["INT. LIGHTHOUSE - NIGHT {}\nMara climbs the stairs. ".format(k) + "x" * 900 for k in range(6)]
    premise = "HARBOR LIGHTS\nA short film about a lighthouse keeper's last night. Moody, rain, neon."
    out = split_script(premise + "\n\n" + "\n\n".join(scenes), 3000)
    assert out["notes"] == premise and out["parts"][0][0].startswith("INT. LIGHTHOUSE - NIGHT 0")
    # a first line that is a speaker of the script, or has an extension, is still a cue
    talk = ["INT. ROOM {} - NIGHT\n\nMara walks in.\n\nMARA\nHello there, number {}.".format(i, i) for i in range(12)]
    for opening in ("MARA\nWhere is he?", "FINN (V.O.)\nShe never came back."):
        out = split_script(opening + "\n\n" + "\n\n".join(talk), 600)
        assert out["parts"][0][0] == opening and out["notes"] == ""


def test_rules_between_table_rows_keep_the_rows():
    """Review 7a: every row over a rule counted as a table heading, so in a table with a rule between its rows each
    shot row went to the notes ("Table columns") and no part made a scene of it."""
    text = "| # | Time | Shot |\n|---|:---:|---|\n" + "\n|---|---|---|\n".join(ROW.format(i, i, i + 1, i) for i in range(1, 41))
    out = split_script(text, 1500)
    assert out["notes"] == "Table columns:\n| # | Time | Shot |\n|---|:---:|---|" and out["blocks"] == 40
    assert [b for p in out["parts"] for b in p][0].startswith("| 01 |")
    # a rule above the heading (a boxed table) does not make the heading a row, and two tables have two headings
    boxed = "|---|---|\n| # | Shot |\n|---|---|\n" + rows(30) + "\n\nThe second act.\n\n| No | Shot |\n|--|--|\n" + rows(30)
    out = split_script(boxed, 1500)
    assert out["notes"].count("Table columns:") == 2 and out["blocks"] == 60  # "The second act." joins row 30
    assert "| # | Shot |" not in "".join(b for p in out["parts"] for b in p)
