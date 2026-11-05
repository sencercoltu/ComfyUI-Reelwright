"""Disk use of every Reelwright project, as a tree, and deleting parts of it (added 2026-11-03 v0.4.0).

Only Reelwright's own folders are scanned and touched:
  output/reelwright/<slug>/   project.json, versions, scenes/<id>/takes/<take>, cuts, cast training sets
  input/reelwright/<slug>/    uploaded and promoted assets

Node ids name what to delete: "p:<slug>" is a whole project (both folders), "o:<rel>" and "i:<rel>" are paths
relative to ComfyUI's output and input folders. The ids are checked again on delete; nothing outside the two
reelwright folders can be named, the open project can't be deleted as a whole, and its project.json is kept.
"""

import os
import re
import shutil
import time
from collections import Counter

from . import cache  # added 2026-11-04 v0.6.1: cache.created_of
from . import jobs  # added 2026-11-03 v0.6.0: nothing a render or merge is using is deleted
from .model import normalize_project
# [OLD 2026-11-03 v0.5.1->v0.6.0] from .storage import SLUG_RE, VERSION_RE, ProjectStore, check_slug, read_json, safe_join
from .storage import CUT_COUNTER, SLUG_RE, VERSION_RE, ProjectStore, check_slug, read_json, safe_join
from .storage import DELETING  # added 2026-11-04 v0.6.1

TAKE_RE = re.compile(r"^scenes/([A-Za-z0-9_-]{1,64})/takes/([A-Za-z0-9_-]{1,64})$")
# [OLD 2026-11-03 v0.5.1->v0.6.0] CUT_RE = re.compile(r"^(?P<stem>.+_cut_v(?P<n>\d+))(?P<rest>(\.partial)?\..+)$")
# added 2026-11-03 v0.6.0: draft and range cuts (<slug>_cut_v4_draft_s02-05.mp4), the stems folder and loudness report
CUT_RE = re.compile(r"^(?P<stem>.+_cut_v(?P<n>\d+)(?:_draft)?(?:_s\d+-\d+)?)"
                    r"(?P<rest>_stems(?:\.partial)?|_loudness\.json|(?:\.partial)?\..+)$")
STEM_ID_RE = re.compile(r"[A-Za-z0-9_.-]+_cut_v\d+(?:_draft)?(?:_s\d+-\d+)?")  # added 2026-11-03 v0.6.0
TAKE_PART_RE = re.compile(r"^scenes/[^/]+/takes/[^/]+/(?P<part>.+)$")  # added 2026-11-03 v0.6.0
# added 2026-11-05 v0.7.0: the timeline's filmstrip of a video (merge.filmstrip: <video>.filmstrip_<h>.jpg / .json, and
# the .partial files of one being made); a cache, made again when needed, so it may go without its take
FILMSTRIP_RE = re.compile(r"^[^/]*\.filmstrip_\d+\.[^/]*$")
PROTECTED = {"project.json": "the project file (delete the whole project instead)",
             "wired.json": "which node inputs are wired; tiny"}


class Node(dict):
    """{id, label, kind, size, count, mtime, note, flags, del, why, view, type, children}"""


def _node(id, label, kind, **kw):
    n = Node(id=id, label=label, kind=kind, size=0, count=0, mtime=0, note="", flags=[], children=[])
    n.update(kw)
    n.setdefault("del", True)
    return n


def _add(parent, child):
    parent["children"].append(child)
    parent["size"] += child["size"]
    parent["count"] += child["count"]
    parent["mtime"] = max(parent["mtime"], child["mtime"])
    return child


def _file(root_key, root, path, label=None, **kw):
    st = os.lstat(path)
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    n = _node("{}:{}".format(root_key, rel), label or os.path.basename(path), "file",
              size=st.st_size, count=1, mtime=int(st.st_mtime), view=rel, type="output" if root_key == "o" else "input", **kw)
    if st.st_nlink > 1:
        n["flags"].append("linked")
    return n


def _dir(root_key, root, path, label=None, kind="dir", skip=(), **kw):
    """A folder and everything in it (files sorted by name, folders first)."""
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    n = _node("{}:{}".format(root_key, rel), label or os.path.basename(path), kind, **kw)
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return n
    dirs = [x for x in names if x not in skip and os.path.isdir(os.path.join(path, x)) and not os.path.islink(os.path.join(path, x))]
    for x in dirs:
        _add(n, _dir(root_key, root, os.path.join(path, x)))
    for x in names:
        if x in skip or x in dirs:
            continue
        try:
            _add(n, _file(root_key, root, os.path.join(path, x)))
        except OSError:
            pass
    return n


def _listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _mtime(path):
    """added 2026-11-04 v0.6.1: modification time, 0 when the path went away meanwhile."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def _asset_uses(p):
    uses = Counter()
    for s in p["scenes"]:
        for r in s.get("refs", []):
            uses[r.get("asset")] += 1
    for c in p["cast"]:
        for a in c.get("anchors", []):
            uses[a] += 1
        if c.get("voice"):
            uses[c["voice"]] += 1
        for o in c.get("outfits", []) or []:
            for a in o.get("assets", []) or []:
                uses[a] += 1
    score = (p.get("global", {}).get("merge", {}).get("score") or {}).get("asset")
    if score:
        uses[score] += 1
    for t in p.get("soundtrack") or []:  # added 2026-11-03 v0.5.0
        if t.get("asset"):
            uses[t["asset"]] += 1
    return uses


def _scene_owner(store, p):
    """added 2026-11-03 v0.6.0: owner(scene_id) -> ("this" | "other" | "unknown", other project's name) for a scene
    folder that is not in the project. The take list says which project rendered into it (index.json project_id,
    written since v0.6.0); older folders are looked up in the autosaved versions (each has its project's id)."""
    pid = (p or {}).get("project_id") if isinstance((p or {}).get("project_id"), str) else ""
    versions = []

    def load_versions():
        if versions:
            return versions
        vdir = os.path.join(store.dir, "versions")
        for x in _listdir(vdir):
            if VERSION_RE.match(x):
                v = read_json(os.path.join(vdir, x), None)
                if isinstance(v, dict) and isinstance(v.get("scenes"), list):
                    ids = {sc.get("id") for sc in v["scenes"] if isinstance(sc, dict)}
                    versions.append((v.get("project_id") if isinstance(v.get("project_id"), str) else "",
                                     str(v.get("name") or ""), ids))
        versions.append(None)  # loaded
        return versions

    def owner(sid):
        if not pid:
            return "this", ""  # a project from before v0.6.0: every folder here is its own
        try:
            stamp = store.read_index(sid).get("project_id")
        except ValueError:
            return "unknown", ""
        if isinstance(stamp, str) and stamp:
            if stamp == pid:
                return "this", ""
            return "other", next((x[1] for x in load_versions() if x and x[0] == stamp), "")
        hits = [x for x in load_versions() if x and sid in x[2]]
        if any(x[0] == pid for x in hits):
            return "this", ""
        other = next((x for x in hits if x[0] and x[0] != pid), None)
        if other:
            return "other", other[1]
        return "unknown", ""

    return owner


def _when(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""


def scan_project(roots, slug, current=None):
    store = ProjectStore(roots, slug)
    # [OLD 2026-11-03 v0.5.1->v0.6.0] raw = read_json(os.path.join(store.dir, "project.json"), None)
    raw = store.load_project()  # added 2026-11-03 v0.6.0: a damaged project.json falls back to the newest version
    try:
        p = normalize_project(raw) if isinstance(raw, dict) else None
    except Exception:  # a damaged project.json must not hide the files
        p = None
    is_current = slug == current
    title = (p or {}).get("name") or slug
    proj = _node("p:" + slug, title, "project", slug=slug, flags=["current"] if is_current else [],
                 note="open in this node" if is_current else "")
    if is_current:
        proj["del"], proj["why"] = False, "the project open in this node; delete its parts instead"
    o, i = roots.output, roots.input

    # scenes and takes, in project order; folders of scenes that are no longer in the project come last
    sdir = os.path.join(store.dir, "scenes")
    if os.path.isdir(sdir):
        order = {s["id"]: (k, s["title"]) for k, s in enumerate((p or {}).get("scenes", []))}
        scenes = _node("o:" + os.path.relpath(sdir, o).replace(os.sep, "/"), "Scenes and takes", "group")
        ids = [x for x in _listdir(sdir) if os.path.isdir(os.path.join(sdir, x))]
        owner = _scene_owner(store, p)  # added 2026-11-03 v0.6.0
        for sid in sorted(ids, key=lambda x: (x not in order, order.get(x, (0,))[0], x)):
            scene_dir = os.path.join(sdir, sid)
            known = sid in order
            label = "{:02d} · {}".format(order[sid][0] + 1, order[sid][1]) if known else sid
            # [OLD 2026-11-03 v0.5.1->v0.6.0] sn = _node("o:" + os.path.relpath(scene_dir, o).replace(os.sep, "/"), label, "scene", sid=sid,
            # [OLD 2026-11-03 v0.5.1->v0.6.0]            flags=[] if known else ["orphan"], note="" if known else "not in the project any more")
            # added 2026-11-03 v0.6.0: a scene folder that is not in the project is an orphan only when it belongs to
            # this project (its take list or an autosaved version says so); two projects can share a folder
            flags, note = [], ""
            if not known:
                who, other_name = owner(sid)
                if who == "this":
                    flags, note = ["orphan"], "not in the project any more"
                elif who == "other":
                    flags, note = ["other_project"], "belongs to another project that used this folder{}".format(
                        " ({})".format(other_name) if other_name else "")
                else:
                    flags, note = ["unknown_owner"], "not in this project; it may belong to another project that used this folder"
            sn = _node("o:" + os.path.relpath(scene_dir, o).replace(os.sep, "/"), label, "scene", sid=sid,
                       flags=flags, note=note)
            try:
                idx = store.read_index(sid)
            except ValueError:
                idx = {"starred": None, "takes": []}
            listed = {t["id"]: t for t in idx["takes"]}
            tdir = os.path.join(scene_dir, "takes")
            take_ids = [x for x in _listdir(tdir) if os.path.isdir(os.path.join(tdir, x))]
            # [OLD 2026-11-04 v0.6.0->v0.6.1] a take folder removed during the scan (getmtime) or a "created" that is not a
            # number (unary minus on text) answered 500
            # take_ids.sort(key=lambda x: (-(listed.get(x, {}).get("created") or os.path.getmtime(os.path.join(tdir, x))), x))
            take_ids.sort(key=lambda x: (-(cache.created_of(listed.get(x)) or _mtime(os.path.join(tdir, x))), x))  # added 2026-11-04 v0.6.1
            for tid in take_ids:
                t = listed.get(tid)
                tn = _dir("o", o, os.path.join(tdir, tid), label=tid, kind="take", skip=())
                tn["take"] = tid
                tn["scene"] = sid
                for c in tn["children"]:
                    if c["kind"] == "dir" and c["label"] == "passes":
                        c["kind"] = "passes"
                        c["note"] = "intermediate pass videos; the take's video is already assembled"
                        c["flags"].append("intermediate")
                    elif c["kind"] == "file" and FILMSTRIP_RE.match(c["label"]):  # added 2026-11-05 v0.7.0
                        c["note"] = "the timeline's filmstrip of the take; made again when needed"
                        c["flags"].append("cache")
                    else:
                        c["del"], c["why"] = False, "part of the take; delete the take"
                if t is None:
                    tn["flags"].append("unlisted")
                    tn["note"] = "not in the take list (an unfinished or older render)"
                    if tid.startswith(DELETING):  # added 2026-11-04 v0.6.1: storage.delete_take sets the folder aside
                        tn["note"] = "a deleted take whose folder is being removed (left over if it stays)"
                else:
                    if idx["starred"] == tid:
                        tn["flags"].append("starred")
                    # [OLD 2026-11-04 v0.6.0->v0.6.1] _when(t.get("created")) raised on a "created" that is not a number
                    bits = [t.get("quality") or "", "{:.1f} s".format(t["seconds"]) if t.get("seconds") else "",
                            _when(cache.created_of(t))]  # added 2026-11-04 v0.6.1
                    tn["note"] = " · ".join(b for b in bits if b)
                _add(sn, tn)
            for x in _listdir(scene_dir):  # index.json and anything else next to takes/
                if x == "takes":
                    continue
                path = os.path.join(scene_dir, x)
                # [OLD 2026-11-03 v0.5.1->v0.6.0] if os.path.isdir(path):
                if x == "passes" and os.path.isdir(path) and not os.path.islink(path):
                    # added 2026-11-03 v0.6.0: the scene's pass cache (finished passes kept for re-use)
                    c = _add(sn, _dir("o", o, path, label="Pass cache", kind="passes"))
                    c["note"] = "finished passes kept for re-use (after Stop, a retake of one pass, a moved keep window); made again when needed"
                    c["flags"].append("cache")
                elif os.path.isdir(path):
                    _add(sn, _dir("o", o, path))
                else:
                    f = _add(sn, _file("o", o, path))
                    if x == "index.json":
                        f["del"], f["why"] = False, "the scene's take list; delete the scene instead"
            _add(scenes, sn)
        _add(proj, scenes)

    # merged cuts, grouped by version (the .mp4 and its .srt, .otio, .fcpxml, .chapters.txt, .zip)
    cdir = store.cuts_dir()
    if os.path.isdir(cdir):
        cuts = _node("o:" + os.path.relpath(cdir, o).replace(os.sep, "/"), "Merged cuts", "group")
        groups, loose = {}, []
        for x in _listdir(cdir):
            path = os.path.join(cdir, x)
            m = CUT_RE.match(x)
            # [OLD 2026-11-03 v0.5.1->v0.6.0] if m and os.path.isfile(path):
            if m and (os.path.isfile(path) or (os.path.isdir(path) and not os.path.islink(path))):
                groups.setdefault((int(m.group("n")), m.group("stem")), []).append(path)
            elif os.path.isdir(path):
                loose.append(_dir("o", o, path))
            elif x == CUT_COUNTER:  # added 2026-11-03 v0.6.0
                f = _file("o", o, path, label="next cut number")
                f["del"], f["why"] = False, "the next cut number; numbers are never reused"
                loose.append(f)
            else:
                loose.append(_file("o", o, path))
        newest = max(groups) if groups else None
        for key in sorted(groups, reverse=True):
            # [OLD 2026-11-03 v0.5.1->v0.6.0] g = _node("cut:{}:{}".format(slug, key[1]), "cut v{}".format(key[0]), "cut", stem=key[1])
            kind_ = [w for w, on in (("draft", "_draft" in key[1]), ("range", re.search(r"_s\d+-\d+$", key[1]))) if on]
            g = _node("cut:{}:{}".format(slug, key[1]), "cut v{}{}".format(key[0], "".join(" " + w for w in kind_)),
                      "cut", stem=key[1])
            g["flags"] += kind_  # added 2026-11-03 v0.6.0: draft / range cuts
            for path in sorted(groups[key]):
                # [OLD 2026-11-03 v0.5.1->v0.6.0] f = _add(g, _file("o", o, path))
                f = _add(g, _dir("o", o, path, label="stems") if os.path.isdir(path) else _file("o", o, path))
                if ".partial" in os.path.basename(path):
                    f["flags"].append("unfinished")
                    f["note"] = "left over from a merge that didn't finish"
            g["note"] = " · ".join(b for b in ["newest" if key == newest else "", _when(g["mtime"])] if b)
            if key == newest:
                g["flags"].append("newest")
            _add(cuts, g)
        for n in loose:
            _add(cuts, n)
        _add(proj, cuts)

    # autosaved versions, newest first
    vdir = os.path.join(store.dir, "versions")
    if os.path.isdir(vdir):
        vers = _node("o:" + os.path.relpath(vdir, o).replace(os.sep, "/"), "Autosaved versions", "group")
        for x in sorted(_listdir(vdir), reverse=True):
            path = os.path.join(vdir, x)
            if os.path.isfile(path):
                f = _add(vers, _file("o", o, path))
                if VERSION_RE.match(x):
                    f["kind"] = "version"
        _add(proj, vers)

    # cast training sets
    cast_root = os.path.join(store.dir, "cast")
    if os.path.isdir(cast_root):
        names = {c["id"]: c.get("name") or c["id"] for c in (p or {}).get("cast", [])}
        cast = _node("o:" + os.path.relpath(cast_root, o).replace(os.sep, "/"), "Cast training sets", "group")
        for cid in _listdir(cast_root):
            path = os.path.join(cast_root, cid)
            if os.path.isdir(path):
                _add(cast, _dir("o", o, path, label=names.get(cid, cid), note="" if cid in names else "not in the project any more"))
        _add(proj, cast)

    # anything else in the project's output folder
    for x in _listdir(store.dir):
        if x in ("scenes", "cuts", "versions", "cast"):
            continue
        path = os.path.join(store.dir, x)
        n = _add(proj, _dir("o", o, path) if os.path.isdir(path) else _file("o", o, path))
        if x == "soundtrack" and os.path.isdir(path):  # added 2026-11-03 v0.5.0
            n["note"] = "the part of the soundtrack each pass was sent; made again when needed"
        if x in PROTECTED and n["kind"] == "file":
            n["note"] = PROTECTED[x]
            if is_current or x == "project.json":
                n["del"], n["why"] = False, PROTECTED[x]

    # assets: the project's input folder; each file says whether the project uses it
    if os.path.isdir(store.input_dir):
        by_file = {}
        uses = _asset_uses(p) if p else Counter()
        for a in (p or {}).get("assets", []):
            by_file.setdefault(a.get("file") or "", []).append(a)
        assets = _dir("i", i, store.input_dir, label="Assets", kind="group")
        assets["note"] = "input/reelwright/" + slug
        # added 2026-11-04 v0.6.1: the folder itself can't be deleted by id (_resolve wants reelwright/<slug>/<name>;
        # the whole project goes with "p:<slug>"), so it was offered and always refused; its files are deleted one by one
        assets["del"], assets["why"] = False, "the project's asset folder; select the files in it, or delete the whole project"

        def mark(n):
            for c in n["children"]:
                if c["kind"] == "file":
                    found = by_file.get(c["view"], [])
                    c["kind"] = "asset"
                    c["asset_ids"] = [a["id"] for a in found]
                    if not found:
                        c["flags"].append("orphan")
                        c["note"] = "not in the project"
                    else:
                        n_uses = sum(uses[a["id"]] for a in found)
                        names = ", ".join("{} {}".format(a.get("code") or "", a.get("name") or "").strip() for a in found)
                        c["flags"].append("used" if n_uses else "unused")
                        c["note"] = "{} · {}".format(names, "used {}×".format(n_uses) if n_uses else "in the library, not used")
                    if "linked" in c["flags"]:
                        c["note"] += " · hard link: frees no space while the original exists"
                else:
                    mark(c)
        mark(assets)
        _add(proj, assets)
    return proj


def scan(roots, current=None):
    slugs = set()
    for base in (os.path.join(roots.output, "reelwright"), os.path.join(roots.input, "reelwright")):
        slugs.update(x for x in _listdir(base) if SLUG_RE.match(x) and os.path.isdir(os.path.join(base, x)))
    if current:
        slugs.add(check_slug(current))
    projects = [scan_project(roots, s, current) for s in slugs]
    projects.sort(key=lambda n: ("current" not in n["flags"], -n["mtime"], n["slug"]))
    return {"projects": projects, "size": sum(n["size"] for n in projects), "current": current or ""}


# ---- deleting ---------------------------------------------------------------

def _resolve(roots, item):
    """(kind, slug, path or args) for a node id, refusing anything outside reelwright/<slug>/."""
    if item.startswith("p:"):
        return "project", check_slug(item[2:]), None
    if item.startswith("cut:"):
        parts = item.split(":", 2)
        # [OLD 2026-11-03 v0.5.1->v0.6.0] if len(parts) != 3 or not re.fullmatch(r"[A-Za-z0-9_.-]+_cut_v\d+", parts[2]):
        if len(parts) != 3 or not STEM_ID_RE.fullmatch(parts[2]):
            raise ValueError("invalid cut id: " + item)
        return "cut", check_slug(parts[1]), parts[2]
    key, _, rel = item.partition(":")
    if key not in ("o", "i") or not rel:
        raise ValueError("invalid id: " + item)
    parts = rel.replace("\\", "/").split("/")
    if len(parts) < 3 or parts[0] != "reelwright" or any(x in ("", ".", "..") for x in parts):
        raise ValueError("not a Reelwright file: " + item)
    # added 2026-11-03 v0.6.0: a drive ("D:", "C:x") or stream name in a part would leave the folder on Windows
    if any(":" in x or "\x00" in x for x in parts):
        raise ValueError("not a Reelwright file: " + item)
    slug = check_slug(parts[1])
    root = roots.output if key == "o" else roots.input
    base = safe_join(root, "reelwright", slug)
    parent = safe_join(base, *parts[2:-1]) if len(parts) > 3 else base
    path = os.path.join(parent, parts[-1])  # the link itself, never what a link points to
    if os.path.dirname(path) != parent:  # added 2026-11-03 v0.6.0
        raise ValueError("not a Reelwright file: " + item)
    return ("output" if key == "o" else "input"), slug, (path, "/".join(parts[2:]))


def _busy_reason(slug, kind, rel=""):
    """added 2026-11-03 v0.6.0: why this can't be deleted now (a render or merge of the project uses it), or None.
    A render uses the scenes, the soundtrack excerpts and the assets; a merge the takes, cuts and assets."""
    render, merging = jobs.is_busy(slug, "render"), jobs.is_busy(slug, "merge")
    if not (render or merging):
        return None
    what = "a render" if render else "a merge"
    msg = "{} of this project is running; delete this when it ends".format(what)
    if kind == "project" or kind == "input":
        return msg
    if kind == "cut":
        return msg if merging else None
    top = rel.split("/", 1)[0]
    if top == "scenes" or (top == "soundtrack" and render) or (top == "cuts" and merging) or (top == "cast" and render):
        return msg
    return None


def _size(path):
    if os.path.islink(path) or os.path.isfile(path):
        st = os.lstat(path)
        return st.st_size if st.st_nlink <= 1 else 0
    total = 0
    for dirpath, dirs, files in os.walk(path):
        for f in files:
            try:
                st = os.lstat(os.path.join(dirpath, f))
                total += st.st_size if st.st_nlink <= 1 else 0
            except OSError:
                pass
    return total


def _remove(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    else:
        raise FileNotFoundError("already gone")


def _paths(item):
    """The output/input paths a node id stands for, as "o:reelwright/..." strings."""
    if item.startswith("p:"):
        return ["o:reelwright/" + item[2:], "i:reelwright/" + item[2:]]
    if item.startswith("cut:"):
        parts = item.split(":", 2)
        if len(parts) == 3:
            return ["o:reelwright/{}/cuts/{}".format(parts[1], parts[2])]
    return [item]


def _covers(a, b):
    if a == b:
        return False
    return any(pb.startswith(pa + "/") or (a.startswith("p:") and pb == pa) for pa in _paths(a) for pb in _paths(b))


def delete(roots, ids, current=None):
    """Delete the named nodes. Returns {removed, freed, errors:[{id, error}], deleted:[ids]}."""
    # added 2026-11-03 v0.6.0 review: ids that are not a list (5, "x", {...}) are refused, not a TypeError
    if ids is not None and not isinstance(ids, (list, tuple)):
        raise ValueError("ids must be a list of ids")
    ids = [x for x in dict.fromkeys(ids or []) if isinstance(x, str)]
    ids = [b for b in ids if not any(_covers(a, b) for a in ids)]  # a path inside another selected one goes with it
    removed, freed, errors, deleted = 0, 0, [], []
    for item in ids:
        try:
            kind, slug, arg = _resolve(roots, item)
            store = ProjectStore(roots, slug)
            busy = _busy_reason(slug, kind, arg[1] if isinstance(arg, tuple) else "")  # added 2026-11-03 v0.6.0
            if busy:
                raise ValueError(busy)
            if kind == "project":
                if current and slug == current:
                    raise ValueError("the project open in this node can't be deleted as a whole")
                # [OLD 2026-11-03 v0.5.1->v0.6.0] store.dir is the resolved path: a project folder that is a link was
                # deleted at its target
                # for d in (store.dir, store.input_dir):
                #     if os.path.isdir(d):
                #         freed += _size(d)
                #         shutil.rmtree(d)
                # [/OLD]
                for d in (os.path.join(roots.output, "reelwright", slug), os.path.join(roots.input, "reelwright", slug)):
                    if os.path.islink(d):  # added 2026-11-03 v0.6.0: the link goes, its target stays
                        os.remove(d)
                    elif os.path.isdir(d):
                        freed += _size(d)
                        shutil.rmtree(d)
            elif kind == "cut":
                cdir = store.cuts_dir()
                gone = 0
                for x in _listdir(cdir):
                    m = CUT_RE.match(x)
                    if m and m.group("stem") == arg:
                        path = os.path.join(cdir, x)
                        freed += _size(path)
                        # [OLD 2026-11-03 v0.5.1->v0.6.0] os.remove(path)
                        _remove(path)  # added 2026-11-03 v0.6.0: the stems folder too
                        gone += 1
                if not gone:
                    raise FileNotFoundError("already gone")
            else:
                path, rel = arg
                if kind == "output" and rel in PROTECTED and (rel == "project.json" or slug == current):
                    raise ValueError("{} is kept: {}".format(rel, PROTECTED[rel]))
                if kind == "output" and re.match(r"^scenes/[^/]+/index\.json$", rel):
                    raise ValueError("a scene's take list is kept; delete the scene instead")
                # added 2026-11-03 v0.6.0: a take's own files go only with the take (its passes/ may go alone)
                part = TAKE_PART_RE.match(rel) if kind == "output" else None
                # [OLD 2026-11-05 v0.6.1->v0.7.0] if part and part.group("part").split("/")[0] != "passes":
                # added 2026-11-05 v0.7.0: a take's filmstrip (a cache) may go alone too
                if part and part.group("part").split("/")[0] != "passes" and not FILMSTRIP_RE.match(part.group("part")):
                    raise ValueError("part of a take; delete the take")
                if kind == "output" and rel == "cuts/" + CUT_COUNTER:
                    raise ValueError("the next cut number is kept")
                m = TAKE_RE.match(rel) if kind == "output" else None
                if m:
                    listed = any(t["id"] == m.group(2) for t in store.read_index(m.group(1))["takes"]) \
                        if os.path.isdir(os.path.dirname(os.path.dirname(path))) else False
                    if not os.path.isdir(path) and not listed:
                        raise FileNotFoundError("already gone")
                    size = _size(path) if os.path.isdir(path) else 0
                    store.delete_take(m.group(1), m.group(2))  # also drops it from index.json and re-stars
                    freed += size
                else:
                    if not os.path.lexists(path):
                        raise FileNotFoundError("already gone")
                    freed += _size(path)
                    _remove(path)
            removed += 1
            deleted.append(item)
        except (ValueError, OSError) as e:
            errors.append({"id": item, "error": str(e)})
    return {"removed": removed, "freed": freed, "errors": errors, "deleted": deleted}
