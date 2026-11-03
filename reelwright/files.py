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

from .model import normalize_project
from .storage import SLUG_RE, VERSION_RE, ProjectStore, check_slug, read_json, safe_join

TAKE_RE = re.compile(r"^scenes/([A-Za-z0-9_-]{1,64})/takes/([A-Za-z0-9_-]{1,64})$")
CUT_RE = re.compile(r"^(?P<stem>.+_cut_v(?P<n>\d+))(?P<rest>(\.partial)?\..+)$")
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
    return uses


def _when(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""


def scan_project(roots, slug, current=None):
    store = ProjectStore(roots, slug)
    raw = read_json(os.path.join(store.dir, "project.json"), None)
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
        for sid in sorted(ids, key=lambda x: (x not in order, order.get(x, (0,))[0], x)):
            scene_dir = os.path.join(sdir, sid)
            known = sid in order
            label = "{:02d} · {}".format(order[sid][0] + 1, order[sid][1]) if known else sid
            sn = _node("o:" + os.path.relpath(scene_dir, o).replace(os.sep, "/"), label, "scene", sid=sid,
                       flags=[] if known else ["orphan"], note="" if known else "not in the project any more")
            try:
                idx = store.read_index(sid)
            except ValueError:
                idx = {"starred": None, "takes": []}
            listed = {t["id"]: t for t in idx["takes"]}
            tdir = os.path.join(scene_dir, "takes")
            take_ids = [x for x in _listdir(tdir) if os.path.isdir(os.path.join(tdir, x))]
            take_ids.sort(key=lambda x: (-(listed.get(x, {}).get("created") or os.path.getmtime(os.path.join(tdir, x))), x))
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
                    else:
                        c["del"], c["why"] = False, "part of the take; delete the take"
                if t is None:
                    tn["flags"].append("unlisted")
                    tn["note"] = "not in the take list (an unfinished or older render)"
                else:
                    if idx["starred"] == tid:
                        tn["flags"].append("starred")
                    bits = [t.get("quality") or "", "{:.1f} s".format(t["seconds"]) if t.get("seconds") else "", _when(t.get("created"))]
                    tn["note"] = " · ".join(b for b in bits if b)
                _add(sn, tn)
            for x in _listdir(scene_dir):  # index.json and anything else next to takes/
                if x == "takes":
                    continue
                path = os.path.join(scene_dir, x)
                if os.path.isdir(path):
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
            if m and os.path.isfile(path):
                groups.setdefault((int(m.group("n")), m.group("stem")), []).append(path)
            elif os.path.isdir(path):
                loose.append(_dir("o", o, path))
            else:
                loose.append(_file("o", o, path))
        newest = max(groups) if groups else None
        for key in sorted(groups, reverse=True):
            g = _node("cut:{}:{}".format(slug, key[1]), "cut v{}".format(key[0]), "cut", stem=key[1])
            for path in sorted(groups[key]):
                f = _add(g, _file("o", o, path))
                if ".partial." in os.path.basename(path):
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
        if len(parts) != 3 or not re.fullmatch(r"[A-Za-z0-9_.-]+_cut_v\d+", parts[2]):
            raise ValueError("invalid cut id: " + item)
        return "cut", check_slug(parts[1]), parts[2]
    key, _, rel = item.partition(":")
    if key not in ("o", "i") or not rel:
        raise ValueError("invalid id: " + item)
    parts = rel.replace("\\", "/").split("/")
    if len(parts) < 3 or parts[0] != "reelwright" or any(x in ("", ".", "..") for x in parts):
        raise ValueError("not a Reelwright file: " + item)
    slug = check_slug(parts[1])
    root = roots.output if key == "o" else roots.input
    base = safe_join(root, "reelwright", slug)
    parent = safe_join(base, *parts[2:-1]) if len(parts) > 3 else base
    path = os.path.join(parent, parts[-1])  # the link itself, never what a link points to
    return ("output" if key == "o" else "input"), slug, (path, "/".join(parts[2:]))


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
    ids = [x for x in dict.fromkeys(ids or []) if isinstance(x, str)]
    ids = [b for b in ids if not any(_covers(a, b) for a in ids)]  # a path inside another selected one goes with it
    removed, freed, errors, deleted = 0, 0, [], []
    for item in ids:
        try:
            kind, slug, arg = _resolve(roots, item)
            store = ProjectStore(roots, slug)
            if kind == "project":
                if current and slug == current:
                    raise ValueError("the project open in this node can't be deleted as a whole")
                for d in (store.dir, store.input_dir):
                    if os.path.isdir(d):
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
                        os.remove(path)
                        gone += 1
                if not gone:
                    raise FileNotFoundError("already gone")
            else:
                path, rel = arg
                if kind == "output" and rel in PROTECTED and (rel == "project.json" or slug == current):
                    raise ValueError("{} is kept: {}".format(rel, PROTECTED[rel]))
                if kind == "output" and re.match(r"^scenes/[^/]+/index\.json$", rel):
                    raise ValueError("a scene's take list is kept; delete the scene instead")
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
