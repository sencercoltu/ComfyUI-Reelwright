"""Storage under concurrency and damage: unique temp files, locks, damaged JSON, take ids,
repair, project identity (slug conflicts), cut numbers."""

import json
import os
import threading

import pytest

from reelwright import jobs, storage
from reelwright.storage import ProjectStore, read_json, write_json


def put(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def make_take(store, sid, tid, created=100, video=True, meta=True):
    d = os.path.join(store.scene_dir(sid), "takes", tid)
    os.makedirs(d, exist_ok=True)
    entry = {"id": tid, "key": "k" + tid, "created": created, "seconds": 2.0,
             "files": {"video": store.rel_output(os.path.join(d, "v.mp4"))}}
    if video:
        put(os.path.join(d, "v.mp4"))
    if meta:
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(dict(entry, passes=[{"index": 1}], settings={"steps": 8}, loras=[], prompts=["p"]), f)
    return entry


# ---- JSON files ------------------------------------------------------------------------------------------------------

def test_write_json_uses_unique_temp_files_and_never_leaves_them(tmp_path):
    path = str(tmp_path / "a" / "x.json")
    errors = []

    def writer(n):
        try:
            for k in range(30):
                write_json(path, {"writer": n, "k": k, "pad": "y" * 2000})
        except Exception as e:  # pragma: no cover - the old fixed .tmp name failed here
            errors.append(e)
    ts = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errors == []
    assert read_json(path)["k"] == 29
    assert os.listdir(str(tmp_path / "a")) == ["x.json"]


def test_damaged_json_reads_as_default(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"half": ')
    assert read_json(str(p), {"d": 1}) == {"d": 1}
    p.write_bytes(b"\xff\xfe\x00garbage")
    assert read_json(str(p)) is None
    assert storage.load_json(str(p))[1] == "damaged"
    assert storage.load_json(str(tmp_path / "none.json"))[1] == "missing"


def test_project_json_falls_back_to_the_newest_readable_version(roots, harbor):
    store = ProjectStore(roots, harbor["slug"])
    store.autosave(dict(harbor, name="Old"), force_version=True)
    vdir = os.path.join(store.dir, "versions")
    names = sorted(os.listdir(vdir))
    os.rename(os.path.join(vdir, names[0]), os.path.join(vdir, "project_20260101_000000.json"))
    write_json(os.path.join(vdir, "project_20990101_000000.json"), {"name": "x"})  # newest, readable
    with open(os.path.join(vdir, "project_20991231_000000.json"), "w") as f:
        f.write("{not json")  # newer still, damaged
    with open(os.path.join(store.dir, "project.json"), "w") as f:
        f.write("{")
    assert store.load_project() == {"name": "x"}
    os.remove(os.path.join(vdir, "project_20990101_000000.json"))
    assert store.load_project()["name"] == "Old"


# ---- take lists ------------------------------------------------------------------------------------------------------

def test_concurrent_add_take_loses_nothing(store):
    def add(n):
        store.add_take("s_one", {"id": "v{}".format(n), "created": n})
    ts = [threading.Thread(target=add, args=(n,)) for n in range(1, 41)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(int(t["id"][1:]) for t in store.read_index("s_one")["takes"]) == list(range(1, 41))


def test_new_take_id_never_reuses_a_folder(store):
    store.add_take("s_one", {"id": "v1"})
    os.makedirs(os.path.join(store.scene_dir("s_one"), "takes", "v3", "passes"))  # an unfinished render
    assert store.new_take_id("s_one") == "v4"
    assert os.path.isdir(os.path.join(store.scene_dir("s_one"), "takes", "v4"))  # reserved at once
    assert store.new_take_id("s_one") == "v5"
    ids = []
    ts = [threading.Thread(target=lambda: ids.append(store.new_take_id("s_two"))) for _ in range(10)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(ids, key=lambda x: int(x[1:])) == ["v{}".format(n) for n in range(1, 11)]


def test_damaged_index_is_rebuilt_from_meta(store):
    make_take(store, "s_one", "v1", created=10)
    make_take(store, "s_one", "v2", created=20)
    make_take(store, "s_one", "v3", created=30, video=False)  # unfinished: no video
    with open(os.path.join(store.scene_dir("s_one"), "index.json"), "w") as f:
        f.write('{"takes": [')
    idx = store.read_index("s_one")
    assert [t["id"] for t in idx["takes"]] == ["v1", "v2"] and idx["starred"] == "v2"
    assert "passes" not in idx["takes"][0] and "settings" not in idx["takes"][0] and idx["takes"][0]["prompts"] == ["p"]
    # the next write keeps them
    store.add_take("s_one", {"id": "v4", "created": 40}, star=False)
    assert [t["id"] for t in store.read_index("s_one")["takes"]] == ["v1", "v2", "v4"]


def test_repair(store):
    # s_one: index lost entirely
    make_take(store, "s_one", "v1", created=10)
    make_take(store, "s_one", "v2", created=20)
    # s_long: index lists v1 (folder deleted by hand, starred) and v2; v3 on disk but not listed
    e2 = make_take(store, "s_long", "v2", created=20)
    make_take(store, "s_long", "v3", created=30)
    store.write_index("s_long", {"starred": "v1", "takes": [{"id": "v1", "created": 5}, e2], "project_id": "p_x"})
    # s_short: fine
    e = make_take(store, "s_short", "v1")
    store.add_take("s_short", e)
    # a pass cache next to the takes is not a take
    put(os.path.join(store.scene_dir("s_short"), "passes", "abc.mp4"))
    out = store.repair()
    assert sorted(out["repaired"]) == ["s_long", "s_one"]
    assert out["takes_found"] == 5 and out["added"] == 3 and out["dropped"] == 1
    one = store.read_index("s_one")
    assert [t["id"] for t in one["takes"]] == ["v1", "v2"] and one["starred"] == "v2"
    long_ = store.read_index("s_long")
    assert [t["id"] for t in long_["takes"]] == ["v2", "v3"] and long_["starred"] == "v3"
    assert long_["project_id"] == "p_x"  # other keys are kept
    assert store.repair()["repaired"] == []  # nothing left to do


def test_delete_take_removes_a_linked_take_folder_not_its_target(store, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "keep.mp4").write_bytes(b"precious")
    os.makedirs(os.path.join(store.scene_dir("s_one"), "takes"))
    os.symlink(str(outside), os.path.join(store.scene_dir("s_one"), "takes", "v1"))
    store.add_take("s_one", {"id": "v1"})
    store.delete_take("s_one", "v1")
    assert (outside / "keep.mp4").read_bytes() == b"precious"
    assert not os.path.lexists(os.path.join(store.scene_dir("s_one"), "takes", "v1"))
    assert store.read_index("s_one")["takes"] == []


def test_add_take_stamps_the_project_id(store, harbor):
    store.autosave(dict(harbor, project_id="p_mine"))
    store.add_take("s_one", {"id": "v1"})
    assert store.read_index("s_one")["project_id"] == "p_mine"


# ---- versions, project identity, cut numbers -------------------------------------------------------------------------

def test_delete_versions_refuses_non_text(store):
    for bad in ([5], [None], "project_x.json", [["a"]]):
        with pytest.raises(ValueError):
            store.delete_versions(bad)
    with pytest.raises(ValueError):
        store.read_version(5)


def test_slug_conflict_and_takeover(store, harbor):
    a = dict(harbor, project_id="p_a", name="Film A")
    b = dict(harbor, project_id="p_b", name="Film B")
    store.autosave(a, owner_check=True)
    store.autosave(a, owner_check=True)  # the same project: fine
    with pytest.raises(storage.SlugConflict) as e:
        store.autosave(b, owner_check=True)
    assert e.value.other == {"id": "p_a", "name": "Film A"}
    assert read_json(os.path.join(store.dir, "project.json"))["project_id"] == "p_a"
    store.autosave(b, owner_check=False)  # take over (force)
    assert read_json(os.path.join(store.dir, "project.json"))["project_id"] == "p_b"
    # a folder from an older version (no id) adopts the incoming id; a project without an id never conflicts
    store.autosave(dict(harbor, project_id=""))
    assert store.slug_conflict(a) is None
    store.autosave(a, owner_check=True)
    assert store.slug_conflict(dict(harbor, project_id="")) is None


def test_cut_numbers_are_never_reused(store):
    first = store.next_cut_path()
    assert first.endswith("harbor_lights_cut_v1")
    put(first + ".mp4")
    second = store.next_cut_path(suffix="_draft")
    assert second.endswith("harbor_lights_cut_v2_draft")
    os.remove(first + ".mp4")
    assert store.next_cut_path().endswith("_cut_v3")  # v1 was deleted: not handed out again
    os.remove(os.path.join(store.cuts_dir(), storage.CUT_COUNTER))  # counter lost: the files still count
    put(os.path.join(store.cuts_dir(), "harbor_lights_cut_v7.mp4"))
    assert store.next_cut_path().endswith("_cut_v8")
    got = []
    ts = [threading.Thread(target=lambda: got.append(store.next_cut_path())) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(set(got)) == 12


def test_storage_methods_hold_the_project_lock(store):
    lk = jobs.lock(store.slug)
    done = threading.Event()
    lk.acquire()
    try:
        t = threading.Thread(target=lambda: (store.add_take("s_one", {"id": "v1"}), done.set()))
        t.start()
        assert not done.wait(0.3)  # waits for the lock
    finally:
        lk.release()
    t.join(5)
    assert done.is_set()


def test_delete_take_removes_its_folder_after_letting_go_of_the_lock(roots, monkeypatch):
    """Bug 6: a big take folder was removed while holding the project lock."""
    store = ProjectStore(roots, "film")
    make_take(store, "s_a", "v1")
    store.add_take("s_a", {"id": "v1", "files": {}})
    free = []
    rmtree = storage.shutil.rmtree

    def probe(path, *a, **k):
        def other():
            lk = jobs.lock("film")
            ok = lk.acquire(timeout=1)
            if ok:
                lk.release()
            free.append(ok)
        t = threading.Thread(target=other)
        t.start()
        t.join()
        return rmtree(path, *a, **k)
    monkeypatch.setattr(storage.shutil, "rmtree", probe)
    store.delete_take("s_a", "v1")
    assert free == [True]
    assert not os.path.exists(os.path.join(store.scene_dir("s_a"), "takes", "v1"))
    assert store.read_index("s_a")["takes"] == []


def test_two_versions_in_one_second_are_two_files(store, harbor, monkeypatch):
    """Review 5: the version name had only seconds, so a second snapshot in the same second overwrote the first."""
    monkeypatch.setattr(storage.time, "time", lambda: 1793700000.25)
    a = store.autosave(dict(harbor, name="first"), force_version=True)
    b = store.autosave(dict(harbor, name="second"), force_version=True)
    assert a != b and storage.VERSION_RE.match(a) and storage.VERSION_RE.match(b) and b > a
    names = [v["name"] for v in store.list_versions()]
    assert names == [b, a]
    assert store.read_version(a)["name"] == "first" and store.read_version(b)["name"] == "second"


def test_repair_during_delete_does_not_bring_the_take_back(store, monkeypatch):
    """Review 6: delete_take removes the folder after letting go of the lock; a repair() (or a damaged-index rebuild)
    in that window listed the take again from its meta.json, and starred it."""
    e1 = make_take(store, "s_one", "v1", created=10)
    store.add_take("s_one", e1)
    seen = {}
    rmtree = storage.shutil.rmtree

    def repair_meanwhile(path, *a, **k):
        assert not os.path.exists(os.path.join(store.scene_dir("s_one"), "takes", "v1"))  # set aside already
        t = threading.Thread(target=lambda: seen.update(repair=store.repair(), rebuilt=store.index_from_takes("s_one"),
                                                        next_id=store.new_take_id("s_one")))
        t.start()
        t.join()
        return rmtree(path, *a, **k)
    monkeypatch.setattr(storage.shutil, "rmtree", repair_meanwhile)
    store.delete_take("s_one", "v1")
    idx = store.read_index("s_one")
    assert idx["takes"] == [] and idx["starred"] is None
    assert seen["repair"]["takes_found"] == 0 and seen["rebuilt"]["takes"] == []
    assert seen["next_id"] == "v2"  # the number of the folder still being removed is not handed out
    assert sorted(os.listdir(os.path.join(store.scene_dir("s_one"), "takes"))) == ["v2"]


def test_take_created_that_is_not_a_number(store):
    """Review (minor, cache.py:155): a hand-edited "created" made /plan answer 500."""
    from reelwright import cache
    assert cache.created_of({"created": "yesterday"}) == 0 and cache.created_of({"created": "12.7"}) == 12
    assert cache.created_of({"created": float("nan")}) == 0 and cache.created_of(None) == 0
    assert cache.created_of({"created": 1793700000}) == 1793700000
    t = {"id": "v1", "key": "L", "created": "yesterday"}
    res = cache.resolve({}, {"takes": [t], "starred": "v1"}, "K", False, legacy_key="L",
                        upstream={"id": "u", "created": 5})
    assert res["status"] == "stale" and res["match"] is None


def test_job_ids_are_never_shared(store):
    """Review 8: running() replaced and popped entries by id alone (the first of two jobs with one id to end removed
    the other's entry), and a made-up id ("render-3") could be the id a caller chose for another job."""
    with jobs.running(store.slug, "x", "same") as first:
        with pytest.raises(jobs.Busy):
            with jobs.running(store.slug, "y", "same"):
                pass
        assert jobs.get("same") is first
    assert jobs.get("same") is None
    chosen = "render-{}".format(next(jobs._ids) + 1)  # the id running() would make up next
    with jobs.exclusive(store.slug, "merge", chosen) as merge_job:
        with jobs.running(store.slug, "render") as render_job:
            assert render_job.id != chosen and jobs.get(chosen) is merge_job and jobs.get(render_job.id) is render_job
            assert jobs.is_busy(store.slug, "merge") and jobs.is_busy(store.slug, "render")
        assert jobs.get(chosen) is merge_job
    assert not jobs.is_busy(store.slug)


def test_deleting_the_starred_take_stars_the_newest(store):
    """The star goes to the newest take by created time (as repair()), not
    to the last one in the list (a take added again moves to the end)."""
    store.add_take("s_one", {"id": "v3", "created": 200.0})
    store.add_take("s_one", {"id": "v1", "created": 100.0}, star=False)
    store.add_take("s_one", {"id": "v2", "created": 300.0})
    store.delete_take("s_one", "v2")
    assert store.read_index("s_one")["starred"] == "v3"
