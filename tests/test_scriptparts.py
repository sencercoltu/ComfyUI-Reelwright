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
