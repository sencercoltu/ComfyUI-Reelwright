"""/reelwright/* HTTP routes used by the editor."""

import asyncio
import functools
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import threading
import time
import uuid

import comfy.samplers
import folder_paths
from aiohttp import web
from server import PromptServer

from . import VERSION, assemble, beats, cache, continuity, detect, jobs, llm, media, merge, profiles, scriptparts, spec
from . import files as diskuse
from .analysis import analyze, plan_response
from .model import cast_description, normalize_project, project_index, slugify
from .storage import ID_RE, ProjectStore, Roots, SlugConflict, check_id, check_slug, read_json, safe_join

log = logging.getLogger("reelwright")
routes = PromptServer.instance.routes


def roots():
    return Roots(folder_paths.get_output_directory(), folder_paths.get_input_directory(),
                 folder_paths.get_user_directory())


def wired_flags(store):
    return read_json(os.path.join(store.dir, "wired.json"), {}) or {}


def _message(e):
    return str(e) or e.__class__.__name__


def json_route(fn):
    @functools.wraps(fn)
    async def wrapper(request):
        try:
            out = await fn(request)
            return out if isinstance(out, web.StreamResponse) else web.json_response(out)
        except SlugConflict as e:
            return web.json_response({"error": _message(e), "reason": "slug_conflict", "other": e.other}, status=409)
        except merge.MergeBusy as e:
            return web.json_response({"error": "busy", "message": _message(e)}, status=409)
        except (llm.LLMError, llm.NoAnswer) as e:
            log.warning("Reelwright %s: %s", request.path, _message(e))
            return web.json_response({"error": _message(e), "reason": e.reason}, status=502)
        except (ValueError, KeyError, FileNotFoundError, merge.MergeError, json.JSONDecodeError) as e:
            return web.json_response({"error": _message(e)}, status=400)
        except Exception as e:
            log.exception("Reelwright route %s failed", request.path)
            return web.json_response({"error": _message(e)}, status=500)
    return wrapper


async def body_of(request):
    b = await request.json()
    if not isinstance(b, dict):
        raise ValueError("the request body must be a JSON object")
    return b


# ---- input checks: wrong types answer 400 with a reason, not 500 ----------------------------------------------

def _str(b, key, default=None, required=True, max_len=4096):
    v = b.get(key, default)
    if v is None and not required:
        return None
    if not isinstance(v, str):
        raise ValueError("{} must be text".format(key))
    if len(v) > max_len:
        raise ValueError("{} is too long".format(key))
    return v


def _int(v, name, lo=None, hi=None):
    if isinstance(v, bool) or v is None:
        raise ValueError("{} must be a whole number".format(name))
    try:
        n = int(v) if not isinstance(v, float) or v.is_integer() else None
    except (TypeError, ValueError):
        n = None
    if n is None:
        raise ValueError("{} must be a whole number".format(name))
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        raise ValueError("{} must be between {} and {}".format(name, lo, hi))
    return n


def _num(v, name):
    if isinstance(v, bool):
        raise ValueError("{} must be a number".format(name))
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError("{} must be a number".format(name))
    if not math.isfinite(x):
        raise ValueError("{} must be a number".format(name))
    return x


def _str_list(v, name, max_items=None):
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError("{} must be a list of text".format(name))
    if max_items is not None and len(v) > max_items:
        raise ValueError("{} has too many entries".format(name))
    return v


def _project(b):
    p = b.get("project")
    if not isinstance(p, (dict, str)):
        raise ValueError("project must be an object")
    return p


def project_store(project):
    p = normalize_project(project)
    return p, ProjectStore(roots(), p["slug"])


def _view(rel):
    """ComfyUI's /view URL of an output-relative file (the editor adds its API base)."""
    from urllib.parse import quote
    folder, _, name = rel.rpartition("/")
    return "/view?filename={}&subfolder={}&type=output".format(quote(name), quote(folder))


def slug_store(slug):
    return ProjectStore(roots(), check_slug(slug))


@routes.get("/reelwright/info")
@json_route
async def info(request):
    return {"version": VERSION, "ffmpeg": merge.ffmpeg_bin() or False,
            "insightface": continuity.available(),
            "insightface_error": continuity.error() or "",
            "h3_nodes": _h3()[0], "h3_error": _h3()[1]}


def _h3():
    """(H3 nodes importable, why not)."""
    try:
        from . import render
        return bool(render.h3_available()), render.h3_error() or ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


@routes.get("/reelwright/models")
@json_route
async def models(request):
    def names(folder):
        try:
            return folder_paths.get_filename_list(folder)
        except KeyError:
            return []
    return {"diffusion_models": names("diffusion_models"), "text_encoders": names("text_encoders"),
            "vae": names("vae"), "loras": names("loras"), "latent_upscale_models": names("latent_upscale_models"),
            "samplers": list(comfy.samplers.KSampler.SAMPLERS), "schedulers": list(comfy.samplers.KSampler.SCHEDULERS)}


@routes.post("/reelwright/plan")
@json_route
async def plan(request):
    body = await body_of(request)
    p, store = project_store(body["project"])
    result = await asyncio.to_thread(analyze, p, store, wired_flags(store))
    return plan_response(result)


def _safe_filename(name):
    base, ext = os.path.splitext(os.path.basename(name or "file"))
    base = re.sub(r"[^\w.-]+", "_", base).strip("._") or "file"
    return base[:80], ext.lower()


UPLOAD_CHUNK = 1 << 20


def _check_media(path):
    """media.describe, and the file must really be readable media of its kind (a picture
    that decodes, a video with a picture, audio with sound); ValueError otherwise."""
    kind = media.kind_of(path)
    try:
        info = media.describe(path)
        if kind == "image":
            from PIL import Image
            with Image.open(path) as im:
                im.load()
        else:
            pr = merge.probe(path)
            if (kind == "video" and not pr["has_video"]) or (kind == "audio" and not pr["has_audio"]):
                raise ValueError("no {} in it".format("picture" if kind == "video" else "sound"))
    except (OSError, ValueError, merge.MergeError, SyntaxError) as e:  # PIL raises OSError / SyntaxError subclasses
        raise ValueError("this file can't be read as {}: {}".format(kind or "media", _message(e)[:200]))
    return info


def _place_upload(store, tmp, base, ext):
    """Move an uploaded temp file to a free name in the project's input folder."""
    with jobs.lock(store.slug):
        os.makedirs(store.input_dir, exist_ok=True)
        n, name = 1, base + ext
        while os.path.exists(os.path.join(store.input_dir, name)):
            n += 1
            name = "{}_{}{}".format(base, n, ext)
        saved = safe_join(store.input_dir, name)
        os.replace(tmp, saved)
        return saved


@routes.post("/reelwright/upload")
@json_route
async def upload(request):
    """One file part ("file") and the project slug ("slug"), in either order. The file is streamed to a temp file
    in 1 MB chunks (writes off the event loop), checked to be readable media, then moved into
    input/reelwright/<slug>/."""
    if not request.content_type.startswith("multipart/"):
        raise ValueError("send the file as multipart/form-data (fields \"file\" and \"slug\")")
    reader = await request.multipart()
    slug, original, tmp, base, ext = None, None, None, None, None
    try:
        while True:
            part = await reader.next()
            if part is None:
                break
            if not hasattr(part, "read_chunk"):  # a nested multipart
                raise ValueError("send the file as a plain form field")
            if part.name == "slug":
                slug = check_slug((await part.text()).strip())
            elif part.name == "file":
                if tmp:
                    raise ValueError("send one file per upload")
                original = part.filename or "file"
                base, ext = _safe_filename(original)
                if media.kind_of(base + ext) is None:
                    raise ValueError("unsupported file type: " + (ext or "(none)"))
                tdir = os.path.join(roots().input, "reelwright", ".uploads")
                await asyncio.to_thread(os.makedirs, tdir, exist_ok=True)
                tmp = os.path.join(tdir, uuid.uuid4().hex + ext)
                f = await asyncio.to_thread(open, tmp, "wb")
                try:
                    while True:
                        chunk = await part.read_chunk(UPLOAD_CHUNK)
                        if not chunk:
                            break
                        await asyncio.to_thread(f.write, chunk)
                finally:
                    await asyncio.to_thread(f.close)
            else:
                await part.release()
        if not slug or not tmp:
            raise ValueError("upload needs a file and a slug")
        if os.path.getsize(tmp) == 0:
            raise ValueError("the file is empty")
        store = slug_store(slug)
        info = await asyncio.to_thread(_check_media, tmp)
        saved = await asyncio.to_thread(_place_upload, store, tmp, base, ext)
        tmp = None
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    category = {"image": "subject", "video": "motion", "audio": "voice"}[info["kind"]]
    return {"asset": dict(info, file=os.path.relpath(saved, store.roots.input).replace(os.sep, "/"),
                          name=os.path.splitext(os.path.basename(original))[0] or base, category=category)}


@routes.get("/reelwright/takes")
@json_route
async def takes(request):
    store = slug_store(request.query.get("slug", ""))
    sdir = os.path.join(store.dir, "scenes")
    ids = [d for d in os.listdir(sdir) if ID_RE.match(d) and os.path.isdir(os.path.join(sdir, d))] \
        if os.path.isdir(sdir) else []
    from .analysis import TAKE_FIELDS_NOT_IN_PLAN

    def lean(idx):
        idx["takes"] = [{k: v for k, v in t.items() if k not in TAKE_FIELDS_NOT_IN_PLAN} for t in idx.get("takes", [])]
        return idx
    return {"scenes": {sid: lean(store.read_index(sid)) for sid in ids}}


@routes.post("/reelwright/takes/star")
@json_route
async def star(request):
    b = await body_of(request)
    await asyncio.to_thread(slug_store(b["slug"]).star, check_id(b["scene_id"]), check_id(b["take_id"]))
    return {"ok": True}


@routes.post("/reelwright/takes/delete")
@json_route
async def delete_take(request):
    b = await body_of(request)
    await asyncio.to_thread(slug_store(b["slug"]).delete_take, check_id(b["scene_id"]), check_id(b["take_id"]))
    return {"ok": True}


@routes.post("/reelwright/merge")
@json_route
async def merge_route(request):
    """{project, draft?, range?: [from_sid, to_sid], stems?, job?}. One merge per project:
    409 {error: "busy"} while one runs. POST /reelwright/merge/cancel {job} stops it; it then answers
    {ok: false, cancelled: true, job}. reelwright.merge events carry `job`."""
    b = await body_of(request)
    p, store = project_store(_project(b))
    job_id = _job_id(b) or "merge-" + uuid.uuid4().hex[:10]
    rng = b.get("range") or None
    if rng is not None:
        rng = _str_list(rng, "range")
        if len(rng) != 2:
            raise ValueError("range must be [first scene id, last scene id]")
    opts = {"draft": bool(b.get("draft")), "range": rng, "stems": bool(b.get("stems")), "interruptible": False}
    if jobs.is_busy(store.slug, "merge"):
        raise merge.MergeBusy("another merge of this project is running")
    server = PromptServer.instance
    ev = {"slug": p["slug"], "job": job_id}

    def progress(x):
        server.send_sync("reelwright.merge", dict(ev, phase="progress", percent=round(x * 100, 1)))

    def work():
        # the job is registered before the autosave and the analysis, so Cancel works from the first moment
        try:
            with jobs.exclusive(store.slug, "merge", job_id) as job:
                server.send_sync("reelwright.merge", dict(ev, phase="start", draft=opts["draft"], range=rng,
                                                          stems=opts["stems"]))
                store.autosave(p, owner_check=True)
                job.check()
                result = analyze(p, store, wired_flags(store))
                job.check()
                return assemble.merge_with_job(result, store, job, progress, opts)
        except jobs.Busy as e:
            raise merge.MergeBusy("another merge of this project is running") from e
        except jobs.Cancelled as e:
            raise merge.MergeCancelled("merge cancelled") from e

    try:
        out = await asyncio.to_thread(work)
    except merge.MergeBusy:
        raise
    except merge.MergeCancelled:
        server.send_sync("reelwright.merge", dict(ev, phase="end", cancelled=True))
        return {"ok": False, "cancelled": True, "job": job_id}
    except Exception as e:
        server.send_sync("reelwright.merge", dict(ev, phase="end", error=_message(e)))
        raise
    server.send_sync("reelwright.merge", dict(ev, phase="end", files=out["files"], duration=out.get("duration"),
                                              loudness=out.get("loudness"), draft=out.get("draft"),
                                              range=out.get("range")))
    return dict(out, ok=True)


@routes.post("/reelwright/merge/cancel")
@json_route
async def merge_cancel(request):
    """{job} stops that merge; {slug} without a job stops any merge of the project (the
    merge after a render has a job id the editor may not know). Answers {ok, cancelled: bool}."""
    b = await body_of(request)
    job_id = _job_id(b)
    done = False
    if job_id:
        j = jobs.get(job_id)
        if j and j.kind == "merge":
            done = jobs.cancel(job_id)
    elif b.get("slug"):
        for j in jobs.busy(check_slug(_str(b, "slug")), "merge"):
            done = jobs.cancel(j.id) or done
    else:
        raise ValueError("cancel needs a job or a slug")
    return {"ok": True, "cancelled": done}


@routes.post("/reelwright/autosave")
@json_route
async def autosave(request):
    b = await body_of(request)
    project = b.get("project")
    if not isinstance(project, dict):
        raise ValueError("project must be an object")
    p, store = project_store(project)
    version = await asyncio.to_thread(store.autosave, project, bool(b.get("version")), not b.get("force"))
    return {"ok": True, "version": version}


@routes.get("/reelwright/versions")
@json_route
async def versions(request):
    return {"versions": slug_store(request.query.get("slug", "")).list_versions()}


# Delete autosaved versions; {"names": [...]} or {"all": true}
@routes.post("/reelwright/versions/delete")
@json_route
async def versions_delete(request):
    b = await body_of(request)
    store = slug_store(b.get("slug", ""))
    names = [v["name"] for v in store.list_versions()] if b.get("all") else _str_list(b.get("names"), "names")
    removed = await asyncio.to_thread(store.delete_versions, names)
    return {"removed": removed, "versions": store.list_versions()}


@routes.get("/reelwright/version")
@json_route
async def version(request):
    store = slug_store(request.query.get("slug", ""))
    return {"project": store.read_version(request.query.get("name", ""))}


# ---- anchor sheet preview --------------------------------------------------------
# The exact sheet the renderer sends for a character's anchors (media.sheet_image), as a JPEG.

@routes.get("/reelwright/sheet")
async def anchor_sheet(request):
    try:
        rels = json.loads(request.query.get("files", "[]"))
        if not isinstance(rels, list) or not rels or len(rels) > 64 or not all(isinstance(r, str) for r in rels):
            raise ValueError("files must be a list of 1-64 input paths")
        cell = max(64, min(768, int(request.query.get("cell", 256))))
        paths = [safe_join(roots().input, str(r)) for r in rels]
        missing = [r for r, path in zip(rels, paths) if not os.path.isfile(path)]
        if missing:
            raise FileNotFoundError("missing: " + ", ".join(missing))

        def make():
            import io as _io
            buf = _io.BytesIO()
            media.sheet_image(paths, cell).save(buf, "JPEG", quality=88)
            return buf.getvalue()
        return web.Response(body=await asyncio.to_thread(make), content_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        return web.json_response({"error": str(e)}, status=400)
    except (OSError, SyntaxError) as e:
        return web.json_response({"error": "a picture can't be read: {}".format(_message(e)[:300])}, status=400)


# ---- soundtrack waveforms --------------------------------------------------------
# Peak levels of an input audio file for the timeline's soundtrack lanes: u8 values, X-Per-Second of them per second.

_PEAKS = {}


@routes.get("/reelwright/waveform")
async def waveform(request):
    try:
        path = safe_join(roots().input, request.query.get("file", ""))
        if not os.path.isfile(path):
            raise FileNotFoundError("missing: " + request.query.get("file", ""))
        per_second = max(10, min(200, int(request.query.get("per_second", 50))))
        st = os.stat(path)
        key = (path, st.st_size, st.st_mtime_ns, per_second)
        if key not in _PEAKS:
            if len(_PEAKS) > 64:
                _PEAKS.clear()
            _PEAKS[key] = await asyncio.to_thread(merge.waveform_peaks, path, per_second)
        w = _PEAKS[key]
        return web.Response(body=w["peaks"], content_type="application/octet-stream",
                            headers={"X-Per-Second": str(w["per_second"]), "X-Duration": str(w["duration"]),
                                     "Cache-Control": "no-store"})
    except (ValueError, FileNotFoundError, merge.MergeError) as e:
        return web.json_response({"error": str(e)}, status=400)


# ---- timeline filmstrips --------------------------------------------------------
# A row of small frames of a rendered video, so a scene block shows the frame that is at each time (merge.filmstrip).

_STRIP_SLOTS = threading.BoundedSemaphore(2)  # ffmpeg runs at once for filmstrips (the timeline asks for many)


@routes.get("/reelwright/filmstrip")
@json_route
async def filmstrip(request):
    """?file=<output-relative video under reelwright/>&h=<tile height, 16-256, default 54> -> {file (the sprite,
    output-relative), url, interval, count, tile_w, tile_h, duration}: tile k (from the left, tile_w px wide) shows the
    video at about k * interval seconds. Made once next to the video and reused while the video is unchanged. 400 for
    a path outside output/reelwright or a file that is not a video, 404 for a missing file."""
    rel = _str(request.query, "file", "")
    h = _int(request.query.get("h", "54"), "h", 16, 256)
    parts = rel.replace("\\", "/").split("/")
    if len(parts) < 2 or parts[0] != "reelwright" or any(x in ("", ".", "..") or ":" in x or "\x00" in x
                                                         for x in parts):
        raise ValueError("file must be a video under the output folder's reelwright/")
    path = safe_join(os.path.join(roots().output, "reelwright"), *parts[1:])
    if os.path.splitext(path)[1].lower() not in media.VIDEO_EXT:
        raise ValueError("file must be a video")
    if not os.path.isfile(path):
        return web.json_response({"error": "missing: " + rel}, status=404)

    def make():
        with _STRIP_SLOTS:
            return merge.filmstrip(path, h)
    out = await asyncio.to_thread(make)
    sprite = "/".join(parts[:-1] + [os.path.basename(out["path"])])
    return {"file": sprite, "url": "{}&v={}".format(_view(sprite), out.get("mtime_ns") or out.get("size") or 0),
            "interval": out["interval"], "count": out["count"], "tile_w": out["tile_w"], "tile_h": out["tile_h"],
            "duration": out["duration"]}


# ---- speech timing ----------------------------------------------------------
# The Timeline monitor's captions follow the speech H3 made, the same way the merge's subtitles do (speech.py).

def _output_video(rel):
    """The path of an output-relative video under reelwright/ (the filmstrip route's checks)."""
    parts = str(rel or "").replace("\\", "/").split("/")
    if len(parts) < 2 or parts[0] != "reelwright" or any(x in ("", ".", "..") or ":" in x or "\x00" in x for x in parts):
        raise ValueError("file must be a video under the output folder's reelwright/")
    path = safe_join(os.path.join(roots().output, "reelwright"), *parts[1:])
    if os.path.splitext(path)[1].lower() not in media.VIDEO_EXT:
        raise ValueError("file must be a video")
    return path


@routes.post("/reelwright/speech")
@json_route
async def speech_timing(request):
    """{file: <output-relative take video>, lines: [{id, t, duration}] (seconds in the take), start?, end?} ->
    {lines: [{id, t, end, matched, planned}], segments: [[start, end]]}: the lines timed to the speech found in the
    take (speech.align). No speech found: every line keeps its time and length. 404 for a missing file."""
    from . import speech
    b = await body_of(request)
    path = _output_video(_str(b, "file"))
    if not os.path.isfile(path):
        return web.json_response({"error": "missing: " + _str(b, "file")}, status=404)
    raw = b.get("lines")
    if not isinstance(raw, list) or len(raw) > 500:
        raise ValueError("lines must be a list of at most 500 lines")
    lines = []
    for x in raw:
        if not isinstance(x, dict):
            raise ValueError("every line must be an object")
        lines.append({"id": str(x.get("id", "")), "t": float(spec.num(x.get("t"), 0.0)),
                      "duration": float(spec.num(x.get("duration"), 1.2))})
    start = float(spec.num(b.get("start"), 0.0))
    end = spec.num(b.get("end"), None)
    ff = merge.ffmpeg_bin()
    if not ff:
        raise ValueError("ffmpeg is not installed")

    def run():
        with _STRIP_SLOTS:
            segs = speech.take_segments(path, ff)
            return segs, speech.timed_lines(path, ff, lines, start, None if end is None else float(end))
    try:
        segs, timed = await asyncio.to_thread(run)
    except speech.SpeechError as e:
        raise ValueError(str(e))
    return {"lines": timed, "segments": [list(x) for x in segs]}


# ---- disk use ----------------------------------------------------------------
# Every Reelwright project's files as a tree, and deleting parts of it (see files.py for what can be deleted).

@routes.get("/reelwright/storage")
@json_route
async def storage_tree(request):
    current = request.query.get("current", "")
    return await asyncio.to_thread(diskuse.scan, roots(), check_slug(current) if current else None)


@routes.post("/reelwright/storage/delete")
@json_route
async def storage_delete(request):
    b = await body_of(request)
    current = check_slug(b["current"]) if b.get("current") else None
    ids = b.get("ids") or []
    if not isinstance(ids, list):
        raise ValueError("ids must be a list of ids")
    result = await asyncio.to_thread(diskuse.delete, roots(), ids, current)
    log.info("Reelwright: deleted %d item(s), %.1f MB freed%s", result["removed"], result["freed"] / 1048576,
             "; {} refused".format(len(result["errors"])) if result["errors"] else "")
    return result


# Files tab "Repair": re-list takes from their meta.json, rebuild missing/damaged index.json
@routes.post("/reelwright/storage/repair")
@json_route
async def storage_repair(request):
    b = await body_of(request)
    store = slug_store(_str(b, "slug"))
    out = await asyncio.to_thread(store.repair)
    log.info("Reelwright: repaired %s: %d scene(s) changed, %d take(s) found", store.slug, len(out["repaired"]),
             out["takes_found"])
    return dict(out, ok=True)


# ---- beat markers and the soundtrack a pass hears ----------------------------------------------------------------

@routes.get("/reelwright/beats")
@json_route
async def beats_route(request):
    """?file=<input-relative audio/video path> -> {bpm, beats: [s], downbeats: [s], duration}; cached by the file's
    content in user/reelwright/cache/beats/."""
    rel = request.query.get("file", "")
    path = safe_join(roots().input, rel)
    if not rel or not os.path.isfile(path):
        raise FileNotFoundError("missing: " + rel)
    ff = merge.ffmpeg_bin()
    if not ff:
        raise ValueError("ffmpeg is needed to find beats")
    try:
        import numpy  # noqa: F401  (inside ComfyUI it is always there)
    except ImportError:
        raise ValueError("numpy is needed to find beats")
    digest = await asyncio.to_thread(cache.file_digest, path)
    cache_dir = os.path.join(roots().user, "reelwright", "cache", "beats")
    try:
        data = await asyncio.to_thread(beats.cached, path, ff, cache_dir, digest)
    except beats.BeatError as e:
        raise ValueError(str(e))
    return dict(data, file=rel)


@routes.post("/reelwright/soundtrack/excerpt")
@json_route
async def soundtrack_excerpt(request):
    """{slug, scene_id, pass, project?} -> {url, file, start, length, codes, marker} of the WAV H3 gets as the
    soundtrack for that pass (1-based), made with the same calls a render makes (and shared with it); {url: null,
    reason} when the pass gets no song. Without `project` the project saved in the slug's folder is used."""
    b = await body_of(request)
    if isinstance(b.get("project"), dict):
        p, store = project_store(b["project"])
    else:
        store = slug_store(_str(b, "slug"))
        raw = await asyncio.to_thread(store.load_project)
        if not isinstance(raw, dict):
            raise ValueError("the project is not saved yet")
        p = normalize_project(raw)
    scene_id = _str(b, "scene_id")
    n = _int(b.get("pass", 1), "pass", 1, 1000)

    def work():
        result = analyze(p, store, wired_flags(store))
        return assemble.pass_song(result, store, scene_id, n)
    song, path = await asyncio.to_thread(work)
    if not song:
        return {"url": None, "file": None, "reason": "This pass gets no soundtrack (less than 2 s of it plays here)."}
    rel = store.rel_output(path)
    return {"url": _view(rel), "file": rel, "start": song["start"], "length": song["length"],
            "codes": song.get("codes", []), "marker": song.get("marker", ""),
            "pieces": [{k: x[k] for k in ("asset", "src_in", "src_out", "at")} for x in song["pieces"]]}


# ---- LLM -------------------------------------------------------------------

def _user_root():
    return roots().user


@routes.get("/reelwright/llm/settings")
@json_route
async def llm_settings_get(request):
    s = llm.load_settings(_user_root())
    return {"base_url": s["base_url"], "model": s["model"], "has_key": bool(s["api_key"]),
            "guides": llm.guide_status(_user_root()), "guide_urls": llm.GUIDES}


# Download MiniMax's official prompt guides into user/reelwright/guides
@routes.post("/reelwright/llm/guides")
@json_route
async def llm_guides_fetch(request):
    return {"guides": await llm.fetch_guides(_user_root())}


def _cfg(p):
    """LLM config for a project, with the downloaded guides attached."""
    stored = llm.load_settings(_user_root())
    stored["guides"] = llm.load_guides(_user_root())
    return llm.resolve(p["global"]["llm"], stored)


@routes.post("/reelwright/llm/settings")
@json_route
async def llm_settings_set(request):
    s = llm.save_settings(_user_root(), await body_of(request))
    return {"ok": True, "has_key": bool(s["api_key"])}


@routes.post("/reelwright/llm/models")
@json_route
async def llm_models(request):
    b = await body_of(request)
    s = llm.load_settings(_user_root())
    base = (_str(b, "base_url", required=False) or s["base_url"] or "").rstrip("/")
    if not base:
        raise ValueError("Set the LLM base URL first")
    return {"models": await llm.list_models(base, s["api_key"])}


# ---- Global profiles ------------------------------------------------------------------------

@routes.get("/reelwright/profiles")
@json_route
async def profiles_list(request):
    return profiles.load(_user_root())


@routes.post("/reelwright/profiles/save")
@json_route
async def profiles_save(request):
    b = await body_of(request)
    return profiles.save(_user_root(), b.get("name"), b.get("global"), b.get("id"), b.get("default"))


@routes.post("/reelwright/profiles/delete")
@json_route
async def profiles_delete(request):
    return profiles.delete(_user_root(), (await body_of(request)).get("id"))


@routes.post("/reelwright/profiles/default")
@json_route
async def profiles_default(request):
    return profiles.set_default(_user_root(), (await body_of(request)).get("id") or "")


@routes.post("/reelwright/llm/test")
@json_route
async def llm_test(request):
    b = await body_of(request)
    cfg = _cfg(normalize_project(b.get("project") or {}))
    return await llm.test(cfg)


def _scene(p, scene_id):
    s = next((x for x in p["scenes"] if x["id"] == scene_id), None)
    if not s:
        raise ValueError("unknown scene")
    return s


@routes.post("/reelwright/llm/rewrite")
@json_route
async def llm_rewrite(request):
    b = await body_of(request)
    p, store = project_store(_project(b))
    cfg = _cfg(p)
    scene = _scene(p, b.get("scene_id"))
    instruction = _str(b, "instruction", "")
    job = _job_id(b)

    # The job is registered before the analysis, so Stop during it is not lost
    async def work():
        result = await asyncio.to_thread(analyze, p, store, wired_flags(store))
        prompts = result["scenes"][scene["id"]]["prompts"]
        builds = result["scenes"][scene["id"]]["builds"]
        return await llm.rewrite(cfg, p, scene, instruction, prompts[0] if prompts else "",
                                 builds[0]["tag_map"] if builds else None, progress=_llm_progress(job))
    return await _llm_job(job, work())


@routes.post("/reelwright/llm/split")
@json_route
async def llm_split(request):
    b = await body_of(request)
    p, store = project_store(_project(b))
    cfg = _cfg(p)
    scene = _scene(p, b.get("scene_id"))
    job = _job_id(b)

    # The job is registered before the analysis, so Stop during it is not lost
    async def work():
        result = await asyncio.to_thread(analyze, p, store, wired_flags(store))
        sr = result["scenes"][scene["id"]]
        return await llm.split(cfg, p, scene, sr["passes"], sr["prompts"], progress=_llm_progress(job))
    out = await _llm_job(job, work())
    return out if isinstance(out, dict) and out.get("cancelled") else {"pass_prompts": out}


# Write prompts. The six sections of each requested pass of a scene, one LLM request per pass
# in order (llm.write_passes), with reelwright.llm progress events that say which pass, and Stop (/llm/cancel).
# Stopped, it answers {cancelled: true} with the passes written so far; a request that fails after a pass was written
# answers 200 with those passes plus error / reason / failed; one that fails before answers 502 like the other routes.
@routes.post("/reelwright/llm/passes")
@json_route
async def llm_passes(request):
    b = await body_of(request)
    p = normalize_project(_project(b))
    cfg = _cfg(p)
    scene = _scene(p, b.get("scene_id"))
    instruction = _str(b, "instruction", "", required=False) or ""
    wanted = b.get("passes")
    if wanted is not None:
        if not isinstance(wanted, list):
            raise ValueError("passes must be a list of pass numbers (1 = the first pass), or null for every pass")
        wanted = [_int(v, "passes", 1, 1000) for v in wanted]
    job = _job_id(b)
    state = {"passes": [], "warnings": [], "tokens": 0, "ms": 0}

    async def work():  # the job is registered before the passes are planned, so Stop then is not lost either
        plan, builds = await asyncio.to_thread(llm.scene_builds, p, scene)
        return await llm.write_passes(cfg, p, scene, wanted, instruction, state=state, plan=plan, builds=builds,
                                      progress=_llm_progress(job, scene_id=scene["id"]))
    out = await _llm_job(job, work())
    if isinstance(out, dict) and out.get("cancelled") and out is not state:
        return dict(state, cancelled=True)  # the passes written before Stop
    return out


@routes.post("/reelwright/llm/script")
@json_route
async def llm_script(request):
    b = await body_of(request)
    p = normalize_project(_project(b))
    cfg = _cfg(p)
    if not (_str(b, "script", "", max_len=10 ** 7) or "").strip():
        raise ValueError("Paste a script first")
    job = _job_id(b)
    part, parts = max(1, _int(b.get("part") or 1, "part")), max(1, _int(b.get("parts") or 1, "parts"))
    if part > parts:
        raise ValueError("part must be between 1 and parts")
    if not isinstance(b.get("known_cast") or [], list):
        raise ValueError("known_cast must be a list")
    if not all(isinstance(c, dict) and isinstance(c.get("name", ""), str) for c in b.get("known_cast") or []):
        raise ValueError("known_cast must be a list of {name: text, kind}")
    return await _llm_job(job, llm.script_part(
        cfg, p, b["script"], part=part, parts=parts, notes=str(b.get("notes") or ""),
        known_cast=b.get("known_cast") or [], progress=_llm_progress(job, part=part, parts=parts),
        retry_cut=not b.get("can_split")))


# ---- long LLM requests: parts, progress, cancel -------------------------------------------------

LLM_JOBS = {}  # job id -> the asyncio task doing the request
LLM_CANCELLED = set()


def _job_id(b):
    return str(b.get("job") or "")[:64]


def _llm_progress(job, **extra):
    """progress() for llm.ask: reelwright.llm websocket events, tagged with the editor's job id."""
    if not job:
        return None
    server = PromptServer.instance
    return lambda d: server.send_sync("reelwright.llm", dict(d, job=job, **extra))


async def _llm_job(job, coro):
    """Run an LLM request as a task that POST /reelwright/llm/cancel can stop; a cancelled one answers
    {"cancelled": true}."""
    task = asyncio.ensure_future(coro)
    if job:
        LLM_JOBS[job] = task
    try:
        return await task
    except asyncio.CancelledError:
        if task in LLM_CANCELLED:
            return {"cancelled": True}
        raise
    finally:
        if job and LLM_JOBS.get(job) is task:
            LLM_JOBS.pop(job, None)
        LLM_CANCELLED.discard(task)


# Chat tab: a general question to the configured LLM, with the conversation so far. Progress
# events carry the answer as it comes ("text"); Stop is /reelwright/llm/cancel with the same job id.
@routes.post("/reelwright/llm/chat")
@json_route
async def llm_chat(request):
    b = await body_of(request)
    cfg = _cfg(normalize_project(b.get("project") or {}))
    msgs = b.get("messages")
    if not isinstance(msgs, list) or not msgs:
        raise ValueError("messages must be a non-empty list")
    if not all(isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
               for m in msgs):
        raise ValueError("each message must be {role: user|assistant, content: text}")
    if msgs[-1]["role"] != "user" or not msgs[-1]["content"].strip():
        raise ValueError("the last message must be the user's question")
    if sum(len(m["content"]) for m in msgs) > llm.CHAT_MAX_CHARS:
        raise ValueError("the conversation is too long; clear it and start again")
    job = _job_id(b)
    return await _llm_job(job, llm.chat_turn(cfg, [{"role": m["role"], "content": m["content"]} for m in msgs],
                                             progress=_llm_progress(job)))


@routes.post("/reelwright/llm/cancel")
@json_route
async def llm_cancel(request):
    job = _job_id(await body_of(request))
    task = LLM_JOBS.get(job)
    if not task or task.done():
        return {"ok": True, "cancelled": False}
    LLM_CANCELLED.add(task)
    task.cancel()
    return {"ok": True, "cancelled": True}


@routes.post("/reelwright/llm/script/parts")
@json_route
async def llm_script_parts(request):
    b = await body_of(request)
    size = llm.limits({"import_part_chars": b.get("part_chars", 3000)})["import_part_chars"]
    return scriptparts.split_script(_str(b, "script", "", required=False, max_len=10 ** 7) or "", size)


# Describe pictures and videos with a vision model. asset_ids: pictures and whole videos; clips: parts of videos
# ({"asset", "in", "out"}, a cast member's video anchors). The first video also goes as a video file when the server
# takes video (llm.video_wanted) and it is short enough; every video gets frames for the fallback. At most 4 pictures,
# 3 videos and 10 pictures in all (with the frames).
DESCRIBE_FRAMES = {1: 6, 2: 3, 3: 2}


@routes.post("/reelwright/llm/describe")
@json_route
async def llm_describe(request):
    b = await body_of(request)
    p, store = project_store(b["project"])
    idx = project_index(p)
    cfg = _cfg(p)

    def asset_path(aid):
        a = idx["assets"].get(aid)
        if not a:
            raise ValueError("unknown asset")
        path = store.input_path(a["file"])
        if not os.path.isfile(path):
            raise FileNotFoundError("{} file is missing".format(a["code"]))
        return a, path

    pictures, videos = [], []
    for aid in _str_list(b.get("asset_ids"), "asset_ids")[:4]:
        a, path = asset_path(aid)
        if a["kind"] == "video":
            videos.append((a, path, 0.0, None))
        else:
            pictures.append(path)
    clips = b.get("clips") or []
    if not isinstance(clips, list) or not all(isinstance(c, dict) for c in clips):
        raise ValueError("clips must be a list of {asset, in, out}")
    for c in clips[:3]:
        a, path = asset_path(_str(c, "asset", ""))
        if a["kind"] != "video":
            raise ValueError("{} is not a video".format(a["code"]))
        out = c.get("out")
        videos.append((a, path, _num(c.get("in") or 0, "in"), None if out is None else _num(out, "out")))
    videos = videos[:3]
    images = []
    for path in pictures:
        images += await asyncio.to_thread(media.stills_for_vision, path)
    room = max(0, 10 - len(images))
    sent = []
    for k, (a, path, start, end) in enumerate(videos):
        start, end = await asyncio.to_thread(media.clip_range, path, start, end)
        n = min(DESCRIBE_FRAMES.get(len(videos), 2), max(1, room // max(1, len(videos) - k)))
        room -= n
        v = {"name": a["code"] or a["name"], "seconds": end - start, "video": None,
             "frames": await asyncio.to_thread(media.vision_frames, path, start, end, n)}
        if k == 0 and llm.video_wanted(cfg) and end - start <= llm.DESCRIBE_VIDEO_SECONDS:
            v["video"] = await asyncio.to_thread(media.vision_clip, path, start, end)
        sent.append(v)
    return await llm.describe(cfg, images, (_str(b, "prompt", "") or "").strip(), sent)


# ---- ComfyUI input/output browser --------------------------------------------------------

def _media_root(name):
    r = roots()
    if name == "input":
        return r.input
    if name == "output":
        return r.output
    raise ValueError("root must be input or output")


@routes.get("/reelwright/files")
@json_route
async def files(request):
    q = request.query
    return await asyncio.to_thread(media.list_media, _media_root(q.get("root", "input")), q.get("q", ""),
                                   q.get("kind", ""), max(1, min(1000, _int(q.get("limit", 400), "limit"))))


@routes.post("/reelwright/import")
@json_route
async def import_file(request):
    """Use a file that is already in ComfyUI's input or output folder as an asset.
    Input files are used where they are; output files are linked (or copied) into the project's input folder."""
    b = await body_of(request)
    store = slug_store(b.get("slug"))
    root = b.get("root", "input")
    rel = _str(b, "rel")
    src = safe_join(_media_root(root), rel)
    if not os.path.isfile(src) or media.kind_of(src) is None:
        raise ValueError("not a picture, video or audio file: " + rel)
    if root == "input":
        dst = src
    else:
        base, ext = _safe_filename(rel)
        folder = os.path.join(store.input_dir, "from_output")
        dst = await asyncio.to_thread(_import_target, store, folder, src, base, ext)
    info = await asyncio.to_thread(media.describe, dst)
    category = {"image": "subject", "video": "motion", "audio": "voice"}[info["kind"]]
    return {"asset": dict(info, file=os.path.relpath(dst, store.roots.input).replace(os.sep, "/"),
                          name=os.path.splitext(os.path.basename(src))[0], category=category)}


# ---- takes, cast, continuity -----------------------------------------------

def _same_content(a, b):
    try:
        if os.path.samefile(a, b):
            return True
        return os.path.getsize(a) == os.path.getsize(b) and cache.file_digest(a) == cache.file_digest(b)
    except OSError:
        return False


def _import_target(store, folder, src, base, ext):
    """The file in from_output/ that holds src's bytes: an existing one with the same
    content, else a new hard link (or copy) under a free name.
    The hashing and the copy happen outside the project lock; the lock is held only
    to give the finished copy its free name."""
    os.makedirs(folder, exist_ok=True)

    def name(n):
        return os.path.join(folder, base + ext if n == 1 else "{}_{}{}".format(base, n, ext))
    differs, n = set(), 1
    while os.path.exists(name(n)):  # an earlier import of the same bytes
        if _same_content(name(n), src):
            return name(n)
        differs.add(name(n))
        n += 1
    tmp = os.path.join(folder, ".import-{}{}".format(uuid.uuid4().hex[:12], ext))
    try:
        try:
            os.link(src, tmp)
        except OSError:
            shutil.copyfile(src, tmp)
        with jobs.lock(store.slug):
            n = 1
            while os.path.exists(name(n)):
                if name(n) not in differs and _same_content(name(n), src):  # made by another import meanwhile
                    return name(n)
                n += 1
            os.replace(tmp, name(n))
            return name(n)
    finally:
        if os.path.lexists(tmp):
            os.remove(tmp)


def _take(store, scene_id, take_id):
    idx = store.read_index(check_id(scene_id))
    t = next((x for x in idx["takes"] if x["id"] == take_id), None)
    if not t:
        raise ValueError("unknown take")
    return t


@routes.post("/reelwright/promote_frame")
@json_route
async def promote_frame(request):
    b = await body_of(request)
    store = slug_store(b.get("slug"))
    take = _take(store, b.get("scene_id"), b.get("take_id"))
    which = b.get("which", "last")
    if which not in ("first", "last", "time"):
        raise ValueError("which must be first, last or time")
    t = max(0.0, _num(b.get("t") or 0, "t"))
    os.makedirs(store.input_dir, exist_ok=True)
    name = "promoted_{}_{}_{}.png".format(check_id(b["scene_id"]), check_id(take["id"]),
                                         which if which != "time" else "t{:.2f}".format(t))
    dst = safe_join(store.input_dir, name)
    if which in ("first", "last"):
        shutil.copyfile(store.output_path(take["files"][which]), dst)
    else:
        ff = merge.ffmpeg_bin()
        if not ff:
            raise ValueError("ffmpeg is needed to grab a frame at a time")
        r = await asyncio.to_thread(subprocess.run, [ff, "-hide_banner", "-loglevel", "error", "-y", "-ss",
                                                     str(t), "-i", store.output_path(take["files"]["video"]),
                                                     "-frames:v", "1", dst], capture_output=True, text=True)
        if r.returncode != 0:
            raise merge.MergeError("ffmpeg could not grab a frame at {:.2f} s: {}".format(
                t, (r.stderr or "").strip()[-400:] or "exit code {}".format(r.returncode)))
    try:
        info = await asyncio.to_thread(media.describe, dst)
    except FileNotFoundError:
        raise
    except (OSError, SyntaxError) as e:
        raise ValueError("the frame can't be read as a picture: {}".format(_message(e)[:300])) from e
    return {"asset": dict(info, file=os.path.relpath(dst, store.roots.input).replace(os.sep, "/"),
                          name="{} frame".format(which), category="subject")}


# A frame of a cast member's video anchor as a picture, for the character's identity. The editor stores the
# picture as an image asset (cast.video_anchors[].frame_asset), offered under Cast -> Anchors -> + Add anchor.
@routes.post("/reelwright/anchor_frame")
@json_route
async def anchor_frame(request):
    """{slug, file (the video asset's file, under ComfyUI's input folder), t (seconds in it), cast_id, anchor_id} ->
    {asset: {file, kind: "image", width, height, name, category: "subject"}, t}. The frame at t (on whole frames) is
    written to input/reelwright/<project>/frame_<cast>_<anchor>_<frame>f.png; 400 when the file is missing or ffmpeg
    can't read a frame there."""
    b = await body_of(request)
    store = slug_store(b.get("slug"))
    cast_id = check_id(_str(b, "cast_id"))
    anchor_id = check_id(_str(b, "anchor_id"))
    src = store.input_path(_str(b, "file"))
    if not os.path.isfile(src):
        raise FileNotFoundError("the video {} is not in ComfyUI's input folder".format(_str(b, "file")))
    frame = int(math.floor(max(0.0, _num(b.get("t") or 0, "t")) * spec.FPS + 0.5))
    t = frame / spec.FPS
    ff = merge.ffmpeg_bin()
    if not ff:
        raise ValueError("ffmpeg is needed to take a frame from a video")
    os.makedirs(store.input_dir, exist_ok=True)
    dst = safe_join(store.input_dir, "frame_{}_{}_{}f.png".format(cast_id, anchor_id, frame))
    # -ss after -i: the exact frame (slower than seeking before it, but anchors are short clips)
    r = await asyncio.to_thread(subprocess.run, [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
                                                 "-ss", "{:.6f}".format(t), "-frames:v", "1", dst],
                                capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(dst):
        raise merge.MergeError("ffmpeg could not take a frame at {:.3f} s: {}".format(
            t, (r.stderr or "").strip()[-400:] or "no frame there (past the end of the video?)"))
    try:
        info = await asyncio.to_thread(media.describe, dst)
    except (OSError, SyntaxError) as e:
        raise ValueError("the frame can't be read as a picture: {}".format(_message(e)[:300])) from e
    return {"asset": dict(info, file=os.path.relpath(dst, store.roots.input).replace(os.sep, "/"), kind="image",
                          category="subject"), "t": t}


# ---- crop a picture into a new one, and find faces and things in it first (detect.py) --------------------------------

def _box(v):
    """[x, y, w, h] as parts of a picture (0..1), inside it."""
    if not isinstance(v, list) or len(v) != 4:
        raise ValueError("box must be [x, y, w, h]")
    x, y, w, h = (_num(n, "box") for n in v)
    if w <= 0 or h <= 0 or x < -0.01 or y < -0.01 or x + w > 1.01 or y + h > 1.01:
        raise ValueError("box must lie inside the picture")
    return [x, y, w, h]


def _picture(store, b):
    rel = _str(b, "file")
    src = store.input_path(rel)
    if not os.path.isfile(src):
        raise FileNotFoundError("the picture {} is not in ComfyUI's input folder".format(rel))
    if media.kind_of(src) != "image":
        raise ValueError("only a picture can be cropped or searched")
    return rel, src


@routes.post("/reelwright/crop")
@json_route
async def crop_picture(request):
    """{slug, file (a picture under ComfyUI's input folder), box [x, y, w, h] (parts of it), name} ->
    {asset: {file, kind: "image", width, height, name, category: "subject"}, small}. Written to
    input/reelwright/<project>/crops/<name>_<key>.png, the key from the picture and the box (cropping the same box
    again gives the same file); small: its short side is under 400 px."""
    b = await body_of(request)
    store = slug_store(b.get("slug"))
    rel, src = _picture(store, b)
    box = _box(b.get("box"))
    name = (_str(b, "name", "", max_len=200) or "").strip() or "crop"
    key = hashlib.sha1(json.dumps([rel, int(os.path.getmtime(src)), [round(v, 4) for v in box]]).encode()).hexdigest()[:10]
    dst = safe_join(store.input_dir, "crops", "{}_{}.png".format(slugify(name)[:40] or "crop", key))
    w, h = await asyncio.to_thread(detect.crop, src, box, dst)
    return {"asset": {"file": os.path.relpath(dst, store.roots.input).replace(os.sep, "/"), "kind": "image",
                      "width": w, "height": h, "name": name, "category": "subject"},
            "small": min(w, h) < detect.SMALL_SIDE}


@routes.get("/reelwright/detect/status")
@json_route
async def detect_status(request):
    return await asyncio.to_thread(detect.status)


@routes.post("/reelwright/detect/download")
@json_route
async def detect_download(request):
    return await asyncio.to_thread(detect.download)


@routes.post("/reelwright/detect")
@json_route
async def detect_things(request):
    """{slug, file (a picture), mode: "faces" | "objects", queries: ["dog", "tea cup"] (objects)} ->
    {boxes: [{box: [x, y, w, h], label, score}], engine, ms}. Faces come with their head and shoulders, from
    insightface, else from the object finder; objects from the object finder (detect.find_objects)."""
    b = await body_of(request)
    store = slug_store(b.get("slug"))
    _rel, src = _picture(store, b)
    mode = _str(b, "mode", "objects")
    t0 = time.time()
    if mode == "faces":
        if continuity.available():
            boxes, engine = await asyncio.to_thread(detect.find_faces, src), "insightface"
        elif detect.detector_ready():
            boxes, engine = await asyncio.to_thread(detect.faces_with_detector, src), "grounding-dino"
        else:
            raise ValueError("Finding faces needs insightface (the face check's package) or the object finder "
                             "(Download in the crop window)")
    elif mode == "objects":
        queries = _str_list(b.get("queries"), "queries", max_items=12)
        boxes, engine = await asyncio.to_thread(detect.find_objects, src, queries), "grounding-dino"
    else:
        raise ValueError("mode must be faces or objects")
    return {"boxes": boxes, "engine": engine, "ms": int((time.time() - t0) * 1000)}


VOICE_MIN, VOICE_MAX = 2.0, 15.0  # H3's audio references: 2-15 s


@routes.post("/reelwright/voice_from_take")
@json_route
async def voice_from_take(request):
    """{slug, scene_id, take_id, cast_id, lines: [{id, t, duration}] (the character's lines in the scene, scene time)}
    -> {asset: {file, kind: "audio", duration, name, category: "voice"}, used: [line ids], seconds}. Each line is timed
    to the speech in the take (speech.py) and its span cut from the take's sound; the spans are joined with 0.25 s of
    silence, up to 15 s, into input/reelwright/<project>/voice_<cast>_<scene>_<take>.wav. 400 when the lines give less
    than 2 s of speech."""
    from . import speech
    b = await body_of(request)
    store = slug_store(b.get("slug"))
    take = _take(store, b.get("scene_id"), b.get("take_id"))
    cast_id = check_id(_str(b, "cast_id"))
    raw = b.get("lines")
    if not isinstance(raw, list) or not raw or len(raw) > 200:
        raise ValueError("lines must be a list of 1-200 lines")
    lines = []
    for x in raw:
        if not isinstance(x, dict):
            raise ValueError("every line must be an object")
        lines.append({"id": str(x.get("id", "")), "t": max(0.0, _num(x.get("t") or 0, "t")),
                      "duration": max(0.3, _num(x.get("duration") or 1.2, "duration"))})
    ff = merge.ffmpeg_bin()
    if not ff:
        raise ValueError("ffmpeg is needed to cut the voice from the take")
    video = store.output_path(take["files"]["video"])
    os.makedirs(store.input_dir, exist_ok=True)
    name = "voice_{}_{}_{}.wav".format(cast_id, check_id(b["scene_id"]), check_id(take["id"]))
    dst = safe_join(store.input_dir, name)

    def make():
        import numpy as np
        timed = speech.timed_lines(video, ff, lines)
        y = speech.decode(video, ff)
        gap = np.zeros(int(0.25 * speech.RATE), dtype=np.float32)
        parts, used, total = [], [], 0.0
        for x in sorted(timed, key=lambda q: q["t"]):
            a, e = max(0.0, x["t"] - 0.08), x["end"] + 0.12
            seg = y[int(a * speech.RATE):int(e * speech.RATE)]
            if not len(seg):
                continue
            room = VOICE_MAX - total - (0.25 if parts else 0)
            if room < 0.5:
                break
            seg = seg[:int(room * speech.RATE)]
            if parts:
                parts.append(gap)
                total += 0.25
            parts.append(seg)
            total += len(seg) / speech.RATE
            used.append(x["id"])
        if total < VOICE_MIN:
            raise ValueError("the lines give {:.1f} s of speech; a voice reference needs at least {:.0f} s (render a "
                             "scene where the character says more)".format(total, VOICE_MIN))
        out = np.concatenate(parts)
        peak = float(np.max(np.abs(out))) or 1.0
        pcm = (np.clip(out / max(peak, 1e-6) * 0.89, -1, 1) * 32767).astype("<i2")
        import wave
        with wave.open(dst, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(speech.RATE)
            w.writeframes(pcm.tobytes())
        return used, total
    try:
        used, total = await asyncio.to_thread(make)
    except speech.SpeechError as e:
        raise ValueError(str(e))
    return {"asset": {"file": os.path.relpath(dst, store.roots.input).replace(os.sep, "/"), "kind": "audio",
                      "duration": round(total, 3), "name": "voice from take", "category": "voice"},
            "used": used, "seconds": round(total, 3)}


@routes.post("/reelwright/cast/export")
@json_route
async def cast_export(request):
    b = await body_of(request)
    p, store = project_store(b["project"])
    idx = project_index(p)
    c = idx["cast"].get(_str(b, "cast_id"))
    if not c:
        raise ValueError("unknown cast member")
    folder = os.path.join(store.cast_dir(c["id"]), "training")
    os.makedirs(folder, exist_ok=True)
    caption = "{}, {}".format(re.sub(r"\W+", "_", c["name"]).lower(), cast_description(c, idx["assets"])[0]).strip(", ")
    files = []

    def add(src, stem):
        if not os.path.isfile(src):
            return
        dst = os.path.join(folder, stem + os.path.splitext(src)[1].lower())
        shutil.copyfile(src, dst)
        with open(os.path.splitext(dst)[0] + ".txt", "w", encoding="utf-8") as f:
            f.write(caption)
        files.append(store.rel_output(dst))

    for n, aid in enumerate(c["anchors"], 1):
        a = idx["assets"].get(aid)
        if a and a["kind"] == "image":
            add(store.input_path(a["file"]), "anchor_{:02d}".format(n))
    for s in p["scenes"]:
        if any(e["id"] == c["id"] for e in s["cast"]):
            t = store.starred_take(s["id"])
            if t:
                for which in ("first", "last"):
                    add(store.output_path(t["files"][which]), "{}_{}_{}".format(s["id"], t["id"], which))
    return {"folder": store.rel_output(folder), "files": files}


@routes.post("/reelwright/continuity/check")
@json_route
async def continuity_check(request):
    b = await body_of(request)
    if not continuity.available():
        return {"available": False, "scores": {}}
    p, store = project_store(b["project"])
    scene = _scene(p, b["scene_id"])
    take = store.starred_take(scene["id"])
    if not take:
        raise ValueError("this scene has no take yet")
    scores = await asyncio.to_thread(continuity.check_scene, p, scene, store, store.output_path(take["files"]["video"]))

    def save():
        with jobs.lock(store.slug):
            idx = store.read_index(scene["id"])
            for t in idx["takes"]:
                if t["id"] == take["id"]:
                    t["face"] = scores
            store.write_index(scene["id"], idx)
    await asyncio.to_thread(save)
    return {"available": True, "scores": scores}
