"""Folders, path containment, take indexes and autosave versions.

Every read-modify-write of a project's files (index.json, project.json, the cut counter)
holds the project's lock (jobs.lock); JSON is written through a unique temp file; damaged JSON reads as missing
(project.json falls back to the newest readable autosave); repair() rebuilds take lists from the takes' meta.json.
"""

import json
import logging
import os
import re
import shutil
import sys
import time
import uuid

from . import jobs

log = logging.getLogger("reelwright")

SLUG_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]{0,63}\Z")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}\Z")
VERSION_RE = re.compile(r"^project_\d{8}_\d{6}\.json\Z")
MAX_VERSIONS = 50
VERSION_INTERVAL = 120  # seconds between automatic version snapshots
# A deleted take's folder while delete_take removes it (ID_RE refuses the ".", so
# takes_on_disk, repair() and the take routes never see it as a take)
DELETING = ".deleting-"
DELETING_RE = re.compile(r"^\.deleting-v(\d+)-[0-9a-f]+\Z")


class Roots:
    def __init__(self, output, input, user):
        self.output = os.path.realpath(output)
        self.input = os.path.realpath(input)
        self.user = os.path.realpath(user)


def safe_join(root, *parts):
    root = os.path.realpath(root)
    path = os.path.realpath(os.path.join(root, *[str(x) for x in parts]))
    if path != root and os.path.commonpath([root, path]) != root:
        raise ValueError("path is outside {}".format(root))
    return path


def check_slug(slug):
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise ValueError("invalid project slug: {!r}".format(slug))
    return slug


def check_id(value):
    if not isinstance(value, str) or not ID_RE.match(value):
        raise ValueError("invalid id: {!r}".format(value))
    return value


def write_json(path, data):
    """Written to a temp file of its own (two writers never share one), flushed to disk,
    then moved over the old file in one step."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "{}.{}.{}.tmp".format(path, os.getpid(), uuid.uuid4().hex[:12])
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        _replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _replace(src, dst):
    """os.replace; on Windows a reader holding the file open makes it fail for a moment."""
    for attempt in range(10):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if sys.platform != "win32" or attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def load_json(path):
    """(data, status) with status "ok", "missing" or "damaged"."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), "ok"
    except FileNotFoundError:
        return None, "missing"
    except (json.JSONDecodeError, UnicodeDecodeError, IsADirectoryError, NotADirectoryError) as e:
        log.warning("Reelwright: %s is damaged and is read as missing: %s", path, e)
        return None, "damaged"


def read_json(path, default=None):
    """A damaged file (half written, not JSON) reads as `default` and is logged."""
    data, status = load_json(path)
    return data if status == "ok" else default


class ProjectStore:
    def __init__(self, roots, slug):
        self.roots = roots
        self.slug = check_slug(slug)
        self.dir = safe_join(roots.output, "reelwright", self.slug)
        self.input_dir = safe_join(roots.input, "reelwright", self.slug)

    # paths
    def scene_dir(self, scene_id):
        return safe_join(self.dir, "scenes", check_id(scene_id))

    def take_dir(self, scene_id, take_id):
        return safe_join(self.scene_dir(scene_id), "takes", check_id(take_id))

    def cuts_dir(self):
        return safe_join(self.dir, "cuts")

    def cast_dir(self, cast_id):
        return safe_join(self.dir, "cast", check_id(cast_id))

    def rel_output(self, path):
        return os.path.relpath(path, self.roots.output).replace(os.sep, "/")

    def output_path(self, rel):
        return safe_join(self.roots.output, rel)

    def input_path(self, rel):
        return safe_join(self.roots.input, rel)

    # takes
    def read_index(self, scene_id):
        idx, status = load_json(os.path.join(self.scene_dir(scene_id), "index.json"))
        if status == "damaged" or (status == "ok" and not isinstance(idx, dict)):
            idx = self.index_from_takes(scene_id)
        if not isinstance(idx, dict):
            idx = {"starred": None, "takes": []}
        idx.setdefault("starred", None)
        idx.setdefault("takes", [])
        if not isinstance(idx["takes"], list):
            idx["takes"] = []
        idx["takes"] = [t for t in idx["takes"] if isinstance(t, dict) and isinstance(t.get("id"), str)]
        return idx

    # ---- rebuilding take lists from the takes' meta.json ------------------------------------------------------
    META_ONLY = ("passes", "settings", "loras")  # in meta.json but not in a take list entry

    def take_from_meta(self, scene_id, take_id):
        """The take list entry a take folder's meta.json describes, or None when the take is unfinished (no
        meta.json, or its video is missing)."""
        meta = read_json(os.path.join(self.scene_dir(scene_id), "takes", take_id, "meta.json"), None)
        if not isinstance(meta, dict):
            return None
        entry = {k: v for k, v in meta.items() if k not in self.META_ONLY}
        entry["id"] = take_id
        video = (entry.get("files") or {}).get("video") if isinstance(entry.get("files"), dict) else None
        try:
            if not video or not os.path.isfile(self.output_path(video)):
                return None
        except (ValueError, TypeError):
            return None
        return entry

    def takes_on_disk(self, scene_id):
        """{take_id: entry} for every finished take folder of a scene (the pass cache in passes/ is not a take)."""
        tdir = os.path.join(self.scene_dir(scene_id), "takes")
        out = {}
        for tid in _listdir(tdir):
            if ID_RE.match(tid) and os.path.isdir(os.path.join(tdir, tid)):
                e = self.take_from_meta(scene_id, tid)
                if e:
                    out[tid] = e
        return out

    def index_from_takes(self, scene_id):
        takes = sorted(self.takes_on_disk(scene_id).values(), key=_take_order)
        return {"starred": takes[-1]["id"] if takes else None, "takes": takes}

    def repair(self):
        """Re-list every scene's takes from the takes' meta.json: a missing or damaged index.json is rebuilt,
        finished takes that are not listed are added, listed takes whose folder is gone are dropped and a lost star
        moves to the newest take. Returns {repaired: [scene_id], takes_found, added, dropped, project}."""
        with jobs.lock(self.slug):
            sdir = os.path.join(self.dir, "scenes")
            repaired, found, added, dropped = [], 0, 0, 0
            for sid in _listdir(sdir):
                if not ID_RE.match(sid) or not os.path.isdir(os.path.join(sdir, sid)):
                    continue
                disk = self.takes_on_disk(sid)
                found += len(disk)
                raw, status = load_json(os.path.join(self.scene_dir(sid), "index.json"))
                ok = status == "ok" and isinstance(raw, dict) and isinstance(raw.get("takes"), list)
                if not ok and status == "missing" and not disk:
                    continue  # nothing rendered here yet
                idx = dict(raw) if ok else {"starred": None, "takes": []}
                before = list(idx["takes"])
                tdir = os.path.join(self.scene_dir(sid), "takes")
                kept = [t for t in before if isinstance(t, dict) and isinstance(t.get("id"), str)
                        and ID_RE.match(t["id"]) and os.path.isdir(os.path.join(tdir, t["id"]))]
                listed = {t["id"] for t in kept}
                new = sorted((e for tid, e in disk.items() if tid not in listed), key=_take_order)
                idx["takes"] = kept + new
                ids = [t["id"] for t in idx["takes"]]
                star = idx.get("starred") if idx.get("starred") in ids else (
                    max(idx["takes"], key=_take_order)["id"] if idx["takes"] else None)
                if not ok or new or len(kept) != len(before) or star != idx.get("starred"):
                    idx["starred"] = star
                    self.write_index(sid, idx)
                    repaired.append(sid)
                    added += len(new)
                    dropped += len(before) - len(kept)
            _, pstatus = load_json(os.path.join(self.dir, "project.json"))
            return {"repaired": repaired, "takes_found": found, "added": added, "dropped": dropped,
                    "project": pstatus}

    def write_index(self, scene_id, idx):
        with jobs.lock(self.slug):
            write_json(os.path.join(self.scene_dir(scene_id), "index.json"), idx)

    def new_take_id(self, scene_id):
        """The next take number after every listed take AND every take folder on disk; the
        folder is created at once, so the id is never handed out twice and never reuses an old folder."""
        with jobs.lock(self.slug):
            idx = self.read_index(scene_id)
            tdir = os.path.join(self.scene_dir(scene_id), "takes")
            used = [int(t["id"][1:]) for t in idx["takes"] if re.match(r"^v\d+$", str(t.get("id")))]
            used += [int(x[1:]) for x in _listdir(tdir) if re.match(r"^v\d+$", x)]
            used += [int(m.group(1)) for m in (DELETING_RE.match(x) for x in _listdir(tdir)) if m]
            n = 1 + max(used or [0])
            os.makedirs(tdir, exist_ok=True)
            while True:
                try:
                    os.mkdir(os.path.join(tdir, "v{}".format(n)))
                    return "v{}".format(n)
                except FileExistsError:
                    n += 1

    def _stamp(self, idx):
        """The take list remembers which project rendered into it (project.json's
        project_id), so the Files tab can tell this project's deleted scenes from another project's."""
        p = read_json(os.path.join(self.dir, "project.json"), None)
        pid = p.get("project_id") if isinstance(p, dict) else None
        if isinstance(pid, str) and pid:
            idx["project_id"] = pid

    def add_take(self, scene_id, take, star=True):
        with jobs.lock(self.slug):
            idx = self.read_index(scene_id)
            idx["takes"] = [t for t in idx["takes"] if t["id"] != take["id"]] + [take]
            if star:
                idx["starred"] = take["id"]
            self._stamp(idx)
            self.write_index(scene_id, idx)
            return idx

    def star(self, scene_id, take_id):
        with jobs.lock(self.slug):
            idx = self.read_index(scene_id)
            if not any(t["id"] == take_id for t in idx["takes"]):
                raise ValueError("unknown take {}".format(take_id))
            idx["starred"] = take_id
            self.write_index(scene_id, idx)

    def delete_take(self, scene_id, take_id):
        with jobs.lock(self.slug):
            idx = self.read_index(scene_id)
            idx["takes"] = [t for t in idx["takes"] if t["id"] != take_id]
            if idx["starred"] == take_id:
                idx["starred"] = max(idx["takes"], key=_take_order)["id"] if idx["takes"] else None
                idx["auto_star"] = idx["starred"]
            self.write_index(scene_id, idx)
            d = os.path.join(self.scene_dir(scene_id), "takes", check_id(take_id))
            target = d
            if os.path.isdir(d) and not os.path.islink(d):
                moved = os.path.join(os.path.dirname(d), "{}{}-{}".format(DELETING, take_id, uuid.uuid4().hex[:8]))
                try:
                    os.rename(d, moved)
                    target = moved
                except OSError as e:  # e.g. Windows while a file in it is open: removed in place, as before
                    log.warning("Reelwright: could not set the take folder %s aside before removing it: %s", d, e)
        if os.path.islink(target) or os.path.isfile(target):
            os.remove(target)
        elif os.path.isdir(target):
            shutil.rmtree(target)

    def starred_take(self, scene_id):
        idx = self.read_index(scene_id)
        return next((t for t in idx["takes"] if t["id"] == idx["starred"]), None)

    # project file and versions
    def load_project(self):
        """project.json, or the newest readable autosaved version when project.json is
        missing or damaged; None when there is neither."""
        p = read_json(os.path.join(self.dir, "project.json"), None)
        if isinstance(p, dict):
            return p
        for v in self.list_versions():
            p = read_json(os.path.join(self.dir, "versions", v["name"]), None)
            if isinstance(p, dict):
                return p
        return None

    def slug_conflict(self, project):
        """{id, name} of a different project that already lives in this folder, else
        None. Only projects that both have a project_id can conflict (a folder from an older version adopts the
        incoming id)."""
        pid = project.get("project_id") if isinstance(project, dict) else None
        if not isinstance(pid, str) or not pid:
            return None
        cur = self.load_project()
        other = cur.get("project_id") if isinstance(cur, dict) else None
        if isinstance(other, str) and other and other != pid:
            return {"id": other, "name": str(cur.get("name") or "")}
        return None

    def autosave(self, project, force_version=False, owner_check=False):
        """Holds the project lock; with owner_check a folder that holds another project
        (see slug_conflict) raises SlugConflict instead of being overwritten."""
        with jobs.lock(self.slug):
            if owner_check:
                other = self.slug_conflict(project)
                if other:
                    raise SlugConflict(other)
            os.makedirs(self.dir, exist_ok=True)
            path = os.path.join(self.dir, "project.json")
            previous = read_json(path)
            write_json(path, project)
            vdir = os.path.join(self.dir, "versions")
            versions = self.list_versions()
            newest = versions[0]["created"] if versions else 0
            changed = previous != project
            name = None
            if force_version or (changed and time.time() - newest >= VERSION_INTERVAL):
                name = _free_version_name(vdir)
                write_json(os.path.join(vdir, name), project)
                for v in self.list_versions()[MAX_VERSIONS:]:
                    try:
                        os.remove(os.path.join(vdir, v["name"]))
                    except FileNotFoundError:
                        pass
            return name

    def list_versions(self):
        vdir = os.path.join(self.dir, "versions")
        if not os.path.isdir(vdir):
            return []
        out = []
        for name in _listdir(vdir):
            if VERSION_RE.match(name):
                try:
                    st = os.stat(os.path.join(vdir, name))
                except OSError:
                    continue
                out.append({"name": name, "created": int(st.st_mtime), "size": st.st_size})
        return sorted(out, key=lambda v: v["name"], reverse=True)

    # Delete autosaved versions (project.json, the latest autosave, is never touched)
    def delete_versions(self, names):
        if not isinstance(names, (list, tuple)):
            raise ValueError("names must be a list of version names")
        names = list(names or [])
        bad = [n for n in names if not isinstance(n, str) or not VERSION_RE.match(n)]
        if bad:
            raise ValueError("invalid version name: {!r}".format(bad[0]))
        removed = 0
        with jobs.lock(self.slug):
            for name in names:
                path = safe_join(self.dir, "versions", name)
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
        return removed

    def read_version(self, name):
        if not isinstance(name, str) or not VERSION_RE.match(name):
            raise ValueError("invalid version name")
        data = read_json(safe_join(self.dir, "versions", name))
        if not isinstance(data, dict):
            raise ValueError("this version can't be read (missing or damaged)")
        return data

    def next_cut_path(self, ext=".mp4", suffix=""):
        """Cut numbers come from the counter cuts/.next (never reused, also after deletes),
        taken under the project lock. Returns the path without extension: <cuts>/<slug>_cut_vN<suffix>."""
        with jobs.lock(self.slug):
            d = self.cuts_dir()
            os.makedirs(d, exist_ok=True)
            counter = os.path.join(d, CUT_COUNTER)
            try:
                with open(counter, "r", encoding="utf-8") as f:
                    n = int(f.read().strip() or 1)
            except (OSError, ValueError):
                n = 1
            rx = re.compile(r"^{}_cut_v(\d+)".format(re.escape(self.slug)))
            on_disk = [int(m.group(1)) for m in (rx.match(x) for x in _listdir(d)) if m]
            n = max(n, 1 + max(on_disk or [0]))
            tmp = "{}.{}.tmp".format(counter, uuid.uuid4().hex[:8])
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(str(n + 1))
            _replace(tmp, counter)
            return os.path.join(d, "{}_cut_v{}{}".format(self.slug, n, suffix))


CUT_COUNTER = ".next"


class SlugConflict(ValueError):
    """The project folder holds a different project (see ProjectStore.slug_conflict)."""

    def __init__(self, other):
        super().__init__("the folder {!r} holds another project".format(other.get("name") or other.get("id")))
        self.other = other


def _free_version_name(vdir, now=None):
    """project_<date>_<time>.json for now, or for the next second that has no version yet
    (two versions in one second used to share one file: the second overwrote the first). The name keeps VERSION_RE's
    shape, so the editor and delete_versions read it as before."""
    now = time.time() if now is None else now
    for k in range(3600):
        name = time.strftime("project_%Y%m%d_%H%M%S.json", time.localtime(now + k))
        if not os.path.exists(os.path.join(vdir, name)):
            return name
    return time.strftime("project_%Y%m%d_%H%M%S.json", time.localtime(now))


def _listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _take_order(t):
    """Takes in the order they were made (created time, then take number)."""
    m = re.match(r"^v(\d+)$", str(t.get("id")))
    try:
        created = float(t.get("created") or 0)
    except (TypeError, ValueError):
        created = 0.0
    return (created, int(m.group(1)) if m else 0, str(t.get("id")))
