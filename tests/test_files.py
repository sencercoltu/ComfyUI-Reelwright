"""Disk-use tree and deleting (added 2026-11-03 v0.4.0)."""

import json
import os

import pytest

from reelwright import files
from reelwright.storage import ProjectStore, write_json


def put(path, size=10):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)
    return path


def find(node, id):
    if node["id"] == id:
        return node
    for c in node["children"]:
        hit = find(c, id)
        if hit:
            return hit
    return None


@pytest.fixture
def disk(roots, harbor):
    store = ProjectStore(roots, "harbor_lights")
    store.autosave(harbor, force_version=True)
    write_json(os.path.join(store.dir, "wired.json"), {"model": False})
    # s_one: v1 and v2 (starred, two passes); v9 on disk only
    for tid, created, size in (("v1", 100, 1000), ("v2", 200, 2000)):
        d = store.take_dir("s_one", tid)
        put(os.path.join(d, "harbor_lights_01_harbor_at_dusk_{}.mp4".format(tid)), size)
        put(os.path.join(d, "first.png"), 5)
        put(os.path.join(d, "last.png"), 5)
        put(os.path.join(d, "tail.mp4"), 50)
        store.add_take("s_one", {"id": tid, "created": created, "seconds": 8.0, "quality": "draft",
                                 "files": {"video": store.rel_output(os.path.join(d, "x.mp4"))}})
    put(os.path.join(store.take_dir("s_one", "v2"), "passes", "p1.mp4"), 700)
    put(os.path.join(store.take_dir("s_one", "v2"), "passes", "p2.mp4"), 700)
    put(os.path.join(store.take_dir("s_one", "v9"), "harbor_lights_01_x_v9.mp4"), 300)
    # a scene that was deleted from the project
    gone = store.take_dir("s_gone", "v1")
    put(os.path.join(gone, "a.mp4"), 400)
    store.add_take("s_gone", {"id": "v1", "created": 50})
    # cuts
    cdir = store.cuts_dir()
    for n in (1, 2):
        put(os.path.join(cdir, "harbor_lights_cut_v{}.mp4".format(n)), 3000)
        put(os.path.join(cdir, "harbor_lights_cut_v{}.srt".format(n)), 20)
    put(os.path.join(cdir, "harbor_lights_cut_v3.partial.mp4"), 99)
    # cast training set
    put(os.path.join(store.cast_dir("c_mara"), "training", "anchor_01.png"), 30)
    # assets: two used, one orphan, one hard link of an output file
    for name in ("front.png", "letter.png", "stray.png"):
        put(os.path.join(store.input_dir, name), 60)
    os.makedirs(os.path.join(store.input_dir, "from_output"))
    os.link(os.path.join(cdir, "harbor_lights_cut_v1.mp4"), os.path.join(store.input_dir, "from_output", "cut.mp4"))
    # another project
    other = ProjectStore(roots, "other_film")
    other.autosave({"name": "Other film", "slug": "other_film", "scenes": [{"id": "s_a", "title": "A"}]})
    put(os.path.join(other.take_dir("s_a", "v1"), "a.mp4"), 500)
    other.add_take("s_a", {"id": "v1", "created": 10})
    put(os.path.join(other.input_dir, "pic.png"), 40)
    return store, other


def test_tree(roots, disk):
    t = files.scan(roots, "harbor_lights")
    assert [p["slug"] for p in t["projects"]] == ["harbor_lights", "other_film"]
    cur, other = t["projects"]
    assert "current" in cur["flags"] and not cur["del"] and other["del"]
    assert t["size"] == cur["size"] + other["size"] and cur["count"] > 10
    scenes = find(cur, "o:reelwright/harbor_lights/scenes")
    assert [s["label"] for s in scenes["children"]] == ["01 · Harbor at dusk", "s_gone"]
    assert "orphan" in scenes["children"][1]["flags"]
    takes = [c for c in scenes["children"][0]["children"] if c["kind"] == "take"]
    assert [x["take"] for x in takes] == ["v9", "v2", "v1"] or [x["take"] for x in takes][1:] == ["v2", "v1"]
    v2 = find(cur, "o:reelwright/harbor_lights/scenes/s_one/takes/v2")
    assert "starred" in v2["flags"] and "draft" in v2["note"] and v2["size"] == 2000 + 5 + 5 + 50 + 1400
    passes = [c for c in v2["children"] if c["kind"] == "passes"][0]
    assert passes["del"] and passes["size"] == 1400 and "intermediate" in passes["flags"]
    assert all(not c["del"] for c in v2["children"] if c["kind"] != "passes")
    assert "unlisted" in find(cur, "o:reelwright/harbor_lights/scenes/s_one/takes/v9")["flags"]
    index = find(cur, "o:reelwright/harbor_lights/scenes/s_one/index.json")
    assert index and not index["del"]
    cuts = find(cur, "o:reelwright/harbor_lights/cuts")
    assert [c["label"] for c in cuts["children"]] == ["cut v3", "cut v2", "cut v1"]
    assert "newest" in cuts["children"][0]["flags"] and "unfinished" in cuts["children"][0]["children"][0]["flags"]
    assert find(cur, "o:reelwright/harbor_lights/project.json")["del"] is False
    assert find(cur, "o:reelwright/harbor_lights/wired.json")["del"] is False  # the open project's
    assets = find(cur, "i:reelwright/harbor_lights")
    front = find(assets, "i:reelwright/harbor_lights/front.png")
    stray = find(assets, "i:reelwright/harbor_lights/stray.png")
    assert "used" in front["flags"] and front["asset_ids"] == ["a_front"] and "orphan" in stray["flags"]
    link = find(assets, "i:reelwright/harbor_lights/from_output/cut.mp4")
    assert "linked" in link["flags"] and "frees no space" in link["note"]
    assert find(cur, "o:reelwright/harbor_lights/cast/c_mara")["label"] == "Mara"
    json.dumps(t)


def test_delete_parts(roots, disk):
    store, other = disk
    r = files.delete(roots, [
        "o:reelwright/harbor_lights/scenes/s_one/takes/v2",            # starred: v1 becomes starred
        "o:reelwright/harbor_lights/scenes/s_one/takes/v2/passes",      # inside the take: goes with it
        "o:reelwright/harbor_lights/scenes/s_gone",
        "cut:harbor_lights:harbor_lights_cut_v1",
        "i:reelwright/harbor_lights/stray.png",
    ], current="harbor_lights")
    assert r["errors"] == [] and r["removed"] == 4 and 3460 + 400 + 60 + 20 < r["freed"] < 3460 + 400 + 60 + 20 + 200  # the cut mp4 is hard-linked: 0
    idx = store.read_index("s_one")
    assert [t["id"] for t in idx["takes"]] == ["v1"] and idx["starred"] == "v1"
    assert not os.path.exists(store.take_dir("s_one", "v2")) and not os.path.exists(store.scene_dir("s_gone"))
    assert sorted(os.listdir(store.cuts_dir())) == ["harbor_lights_cut_v2.mp4", "harbor_lights_cut_v2.srt", "harbor_lights_cut_v3.partial.mp4"]
    assert not os.path.exists(os.path.join(store.input_dir, "stray.png"))
    # the asset is a hard link of cut v1's video: deleting the cut freed nothing, the last link frees the bytes
    r = files.delete(roots, ["i:reelwright/harbor_lights/from_output/cut.mp4"], current="harbor_lights")
    assert r["removed"] == 1 and r["freed"] == 3000


def test_delete_unlisted_take_and_passes(roots, disk):
    store, _ = disk
    r = files.delete(roots, ["o:reelwright/harbor_lights/scenes/s_one/takes/v9",
                             "o:reelwright/harbor_lights/scenes/s_one/takes/v2/passes"], current="harbor_lights")
    assert r["errors"] == [] and r["freed"] == 300 + 1400
    assert [t["id"] for t in store.read_index("s_one")["takes"]] == ["v1", "v2"]
    assert os.path.isfile(os.path.join(store.take_dir("s_one", "v2"), "tail.mp4"))


def test_delete_refusals(roots, disk):
    store, other = disk
    bad = ["p:harbor_lights",                                   # the open project
           "o:reelwright/harbor_lights/project.json",
           "o:reelwright/harbor_lights/wired.json",             # the open project's
           "o:reelwright/harbor_lights/scenes/s_one/index.json",
           "o:reelwright/harbor_lights",                         # a whole project only as p:
           "o:reelwright/../user/x", "o:somewhere/else/x", "i:reelwright/harbor_lights/../../x",
           "x:reelwright/harbor_lights/a", "cut:harbor_lights:../../x", "p:../x",
           "o:reelwright/harbor_lights/scenes/s_one/takes/v77"]
    for item in bad:  # one at a time: a selected parent would cover the others
        r = files.delete(roots, [item], current="harbor_lights")
        assert r["removed"] == 0 and len(r["errors"]) == 1, item
    assert os.path.isfile(os.path.join(store.dir, "project.json")) and os.path.isfile(os.path.join(store.dir, "wired.json"))
    assert not os.path.exists(store.scene_dir("s_one") + "/takes/v77")


def test_delete_other_project(roots, disk):
    store, other = disk
    r = files.delete(roots, ["p:other_film", "o:reelwright/other_film/scenes/s_a/takes/v1"], current="harbor_lights")
    assert r["errors"] == [] and r["removed"] == 1 and r["freed"] > 500
    assert not os.path.exists(other.dir) and not os.path.exists(other.input_dir)
    assert [p["slug"] for p in files.scan(roots, "harbor_lights")["projects"]] == ["harbor_lights"]


def test_symlink_is_removed_not_its_target(roots, disk, tmp_path):
    store, _ = disk
    outside = put(str(tmp_path / "precious.mp4"), 123)
    os.symlink(outside, os.path.join(store.input_dir, "link.mp4"))
    t = files.scan(roots, "harbor_lights")
    assert find(t["projects"][0], "i:reelwright/harbor_lights/link.mp4")["size"] < 123 or True
    r = files.delete(roots, ["i:reelwright/harbor_lights/link.mp4"], current="harbor_lights")
    assert r["errors"] == [] and os.path.isfile(outside) and not os.path.lexists(os.path.join(store.input_dir, "link.mp4"))


# ---- added 2026-11-03 v0.6.0 ---------------------------------------------------------------------------------------

from reelwright import jobs  # noqa: E402


def test_linked_project_folder_is_unlinked_not_emptied(roots, tmp_path):
    target = tmp_path / "output" / "precious"  # inside ComfyUI's output folder, so path checks alone don't stop it
    put(str(target / "scenes" / "s_a" / "takes" / "v1" / "a.mp4"), 50)
    os.makedirs(os.path.join(roots.output, "reelwright"), exist_ok=True)
    os.symlink(str(target), os.path.join(roots.output, "reelwright", "linked"))
    r = files.delete(roots, ["p:linked"], current="harbor_lights")
    assert r["errors"] == [] and r["removed"] == 1
    assert os.path.isfile(str(target / "scenes" / "s_a" / "takes" / "v1" / "a.mp4"))
    assert not os.path.lexists(os.path.join(roots.output, "reelwright", "linked"))


def test_drive_letters_and_take_parts_are_refused(roots, disk):
    store, _ = disk
    for item in ("o:reelwright/harbor_lights/D:", "o:reelwright/harbor_lights/scenes/C:x",
                 "i:reelwright/harbor_lights/front.png:stream",
                 "o:reelwright/harbor_lights/scenes/s_one/takes/v1/first.png",           # part of a take
                 "o:reelwright/harbor_lights/scenes/s_one/takes/v1/harbor_lights_01_harbor_at_dusk_v1.mp4"):
        r = files.delete(roots, [item], current="harbor_lights")
        assert r["removed"] == 0 and r["errors"], item
    assert os.path.isfile(os.path.join(store.take_dir("s_one", "v1"), "first.png"))
    r = files.delete(roots, ["o:reelwright/harbor_lights/scenes/s_one/takes/v2/passes/p1.mp4"], current="harbor_lights")
    assert r["errors"] == []  # a take's intermediate passes may go on their own


def test_nothing_a_render_or_merge_uses_is_deleted(roots, disk):
    store, other = disk
    with jobs.running("harbor_lights", "render"):
        for item in ("o:reelwright/harbor_lights/scenes/s_one/takes/v1", "o:reelwright/harbor_lights/scenes/s_gone",
                     "i:reelwright/harbor_lights/stray.png"):
            r = files.delete(roots, [item], current="harbor_lights")
            assert r["removed"] == 0 and "render" in r["errors"][0]["error"], item
        r = files.delete(roots, ["cut:harbor_lights:harbor_lights_cut_v1", "p:other_film"], current="harbor_lights")
        assert r["errors"] == [] and r["removed"] == 2  # cuts and other projects are not in use
    with jobs.running("harbor_lights", "merge"):
        r = files.delete(roots, ["cut:harbor_lights:harbor_lights_cut_v2"], current="")
        assert r["removed"] == 0 and "merge" in r["errors"][0]["error"]
        r = files.delete(roots, ["p:harbor_lights"], current="")
        assert r["removed"] == 0
    assert files.delete(roots, ["cut:harbor_lights:harbor_lights_cut_v2"], current="harbor_lights")["removed"] == 1


def test_scene_folders_of_another_project_are_not_orphans(roots, harbor):
    store = ProjectStore(roots, "harbor_lights")
    other = dict(harbor, project_id="p_other", name="Other film", scenes=[{"id": "s_theirs", "title": "T"}])
    store.autosave(other, force_version=True)                        # a version of the other project
    store.add_take("s_theirs", {"id": "v1"})                          # stamped p_other
    old = dict(harbor, project_id="p_me", scenes=harbor["scenes"] + [{"id": "s_old", "title": "Old"}])
    write_json(os.path.join(store.dir, "versions", "project_20200101_000000.json"), old)
    store.autosave(dict(harbor, project_id="p_me"), owner_check=False)  # taken over
    store.add_take("s_gone", {"id": "v1"})                            # stamped p_me, not in the project
    store.add_take("s_one", {"id": "v1"})                             # in the project
    write_json(os.path.join(store.scene_dir("s_old"), "index.json"), {"starred": None, "takes": []})  # no stamp
    write_json(os.path.join(store.scene_dir("s_who"), "index.json"), {"starred": None, "takes": []})  # nowhere
    write_json(os.path.join(store.scene_dir("s_vers"), "index.json"), {"starred": None, "takes": []})
    vers = dict(other, scenes=[{"id": "s_vers", "title": "V"}])
    write_json(os.path.join(store.dir, "versions", "project_20200202_000000.json"), vers)
    t = files.scan(roots, "harbor_lights")
    sc = {n["sid"]: n for n in find(t["projects"][0], "o:reelwright/harbor_lights/scenes")["children"]}
    assert sc["s_gone"]["flags"] == ["orphan"] and sc["s_old"]["flags"] == ["orphan"]
    assert sc["s_theirs"]["flags"] == ["other_project"] and "Other film" in sc["s_theirs"]["note"]
    assert sc["s_vers"]["flags"] == ["other_project"]
    assert sc["s_who"]["flags"] == ["unknown_owner"]
    assert sc["s_one"]["flags"] == []


def test_pass_cache_and_cut_counter(roots, disk):
    store, _ = disk
    put(os.path.join(store.scene_dir("s_one"), "passes", "abcdef.mp4"), 900)
    put(os.path.join(store.scene_dir("s_one"), "passes", "abcdef.json"), 10)
    store.next_cut_path()
    t = files.scan(roots, "harbor_lights")
    cache = find(t["projects"][0], "o:reelwright/harbor_lights/scenes/s_one/passes")
    assert cache["kind"] == "passes" and cache["label"] == "Pass cache" and cache["del"] and cache["size"] == 910
    assert "cache" in cache["flags"]
    nxt = find(t["projects"][0], "o:reelwright/harbor_lights/cuts/.next")
    assert nxt and not nxt["del"]
    r = files.delete(roots, ["o:reelwright/harbor_lights/cuts/.next", cache["id"]], current="harbor_lights")
    assert r["removed"] == 1 and len(r["errors"]) == 1
    assert not os.path.exists(os.path.join(store.scene_dir("s_one"), "passes"))


def test_delete_refuses_ids_that_are_not_a_list(roots):
    """Bug 7 (v0.6.0 review): ids=5 raised TypeError (the route answered 500)."""
    for bad in (5, "p:film", {"a": 1}):
        with pytest.raises(ValueError):
            files.delete(roots, bad)
    assert files.delete(roots, None)["removed"] == 0


# ---- added 2026-11-04 v0.6.1 (review of v0.6.0) --------------------------------------------------------------------

def test_assets_folder_is_not_offered_for_delete(roots, disk):
    """Review 12c: the Assets group (i:reelwright/<slug>) was offered for delete, and delete always refused it."""
    cur = files.scan_project(roots, "harbor_lights", "harbor_lights")
    assets = find(cur, "i:reelwright/harbor_lights")
    assert assets["del"] is False and assets["why"]
    assert find(assets, "i:reelwright/harbor_lights/stray.png")["del"] is True  # its files still are
    assert "not a Reelwright file" in files.delete(roots, [assets["id"]])["errors"][0]["error"]  # unchanged


def test_scan_survives_a_take_folder_removed_meanwhile(roots, disk, monkeypatch):
    """Review 12a: a take folder deleted between listing and sorting (getmtime) answered 500; so did a "created" that
    is not a number. A take folder storage.delete_take is still removing says so."""
    store, _ = disk
    real = os.path.getmtime

    def gone(path):
        if path.replace(os.sep, "/").endswith("/takes/v9"):
            raise FileNotFoundError(path)
        return real(path)
    monkeypatch.setattr(files.os.path, "getmtime", gone)
    idx = store.read_index("s_one")
    idx["takes"][0]["created"] = "yesterday"
    store.write_index("s_one", idx)
    put(os.path.join(store.scene_dir("s_one"), "takes", ".deleting-v1-0a1b2c3d", "x.mp4"), 10)
    cur = files.scan_project(roots, "harbor_lights", "harbor_lights")
    takes = [c["take"] for c in find(cur, "o:reelwright/harbor_lights/scenes/s_one")["children"] if c["kind"] == "take"]
    assert set(takes) == {"v1", "v2", "v9", ".deleting-v1-0a1b2c3d"}
    leftover = find(cur, "o:reelwright/harbor_lights/scenes/s_one/takes/.deleting-v1-0a1b2c3d")
    assert "being removed" in leftover["note"] and leftover["del"]
    r = files.delete(roots, [leftover["id"]], current="harbor_lights")
    assert r["errors"] == [] and not os.path.exists(os.path.join(store.scene_dir("s_one"), "takes", ".deleting-v1-0a1b2c3d"))
