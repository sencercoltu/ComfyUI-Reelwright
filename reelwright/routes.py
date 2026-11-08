"""/reelwright/* HTTP routes used by the editor."""

import asyncio
import functools
import importlib.util
import json
import logging
import math  # added 2026-11-03 v0.6.0
import os
import re
import shutil
import subprocess
import threading  # added 2026-11-05 v0.7.0: filmstrip slots
import uuid  # added 2026-11-03 v0.6.0

import comfy.samplers
import folder_paths
from aiohttp import web
from server import PromptServer

# [OLD 2026-11-02 v0.2.2->v0.3.0] from . import VERSION, assemble, continuity, llm, media, merge
# [OLD 2026-11-03 v0.3.9->v0.4.0] from . import VERSION, assemble, continuity, llm, media, merge, profiles
from . import VERSION, assemble, continuity, llm, media, merge, profiles
from . import files as diskuse  # added 2026-11-03 v0.4.0 ("files" is already the name of a route below)
from . import scriptparts  # added 2026-11-03 v0.4.2
from .analysis import analyze, plan_response
# [OLD 2026-11-02 v0.3.3->v0.3.4] from .model import normalize_project, project_index
from .model import cast_description, normalize_project, project_index
# [OLD 2026-11-03 v0.5.1->v0.6.0] from .storage import ProjectStore, Roots, check_id, check_slug, read_json, safe_join
from . import beats, cache, jobs  # added 2026-11-03 v0.6.0
from . import spec  # added 2026-11-06 v0.10.0: /reelwright/speech
from .storage import ID_RE, ProjectStore, Roots, SlugConflict, check_id, check_slug, read_json, safe_join

log = logging.getLogger("reelwright")
routes = PromptServer.instance.routes


def roots():
    return Roots(folder_paths.get_output_directory(), folder_paths.get_input_directory(),
                 folder_paths.get_user_directory())


def wired_flags(store):
    return read_json(os.path.join(store.dir, "wired.json"), {}) or {}


# [OLD 2026-11-03 v0.4.1->v0.4.2] an exception without a message (asyncio.TimeoutError) answered {"error": ""}, which the editor showed as
# nothing at all; LLM failures were logged with a full traceback
# def json_route(fn):
#     @functools.wraps(fn)
#     async def wrapper(request):
#         try:
#             return web.json_response(await fn(request))
#         except (ValueError, KeyError, FileNotFoundError, merge.MergeError, json.JSONDecodeError) as e:
#             return web.json_response({"error": str(e)}, status=400)
#         except Exception as e:
#             log.exception("Reelwright route %s failed", request.path)
#             return web.json_response({"error": str(e)}, status=500)
#     return wrapper
# [/OLD]
def _message(e):
    return str(e) or e.__class__.__name__


def json_route(fn):
    @functools.wraps(fn)
    async def wrapper(request):
        try:
            # [OLD 2026-11-03 v0.5.1->v0.6.0] return web.json_response(await fn(request))
            out = await fn(request)
            return out if isinstance(out, web.StreamResponse) else web.json_response(out)
        except SlugConflict as e:
            # added 2026-11-03 v0.6.0: the project folder holds another project (see storage.slug_conflict)
            return web.json_response({"error": _message(e), "reason": "slug_conflict", "other": e.other}, status=409)
        except merge.MergeBusy as e:
            # added 2026-11-03 v0.6.0: one merge per project at a time
            return web.json_response({"error": "busy", "message": _message(e)}, status=409)
        except (llm.LLMError, llm.NoAnswer) as e:
            # added 2026-11-03 v0.4.2: the LLM failed; say why, and give the editor the reason (e.g. "cut")
            log.warning("Reelwright %s: %s", request.path, _message(e))
            return web.json_response({"error": _message(e), "reason": e.reason}, status=502)
        except (ValueError, KeyError, FileNotFoundError, merge.MergeError, json.JSONDecodeError) as e:
            return web.json_response({"error": _message(e)}, status=400)
        except Exception as e:
            log.exception("Reelwright route %s failed", request.path)
            return web.json_response({"error": _message(e)}, status=500)
    return wrapper


async def body_of(request):
    # [OLD 2026-11-03 v0.5.1->v0.6.0] return await request.json()
    b = await request.json()
    if not isinstance(b, dict):  # added 2026-11-03 v0.6.0: a list or number answered 500
        raise ValueError("the request body must be a JSON object")
    return b


# ---- input checks (added 2026-11-03 v0.6.0): wrong types answer 400 with a reason, not 500 --------------------

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
    """added 2026-11-03 v0.6.0: ComfyUI's /view URL of an output-relative file (the editor adds its API base)."""
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
            "insightface_error": continuity.error() or "",  # added 2026-11-03 v0.4.1
            # [OLD 2026-11-03 v0.5.1->v0.6.0] "h3_nodes": importlib.util.find_spec("comfy_extras.nodes_minimax_h3") is not None}  (true when the module exists but fails to import)
            # added 2026-11-03 v0.6.0: render imports H3 lazily and knows whether it worked
            "h3_nodes": _h3()[0], "h3_error": _h3()[1]}


def _h3():
    """added 2026-11-03 v0.6.0: (H3 nodes importable, why not)."""
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


UPLOAD_CHUNK = 1 << 20  # added 2026-11-03 v0.6.0


def _check_media(path):
    """added 2026-11-03 v0.6.0: media.describe, and the file must really be readable media of its kind (a picture
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
    """added 2026-11-03 v0.6.0: move an uploaded temp file to a free name in the project's input folder."""
    with jobs.lock(store.slug):
        os.makedirs(store.input_dir, exist_ok=True)
        n, name = 1, base + ext
        while os.path.exists(os.path.join(store.input_dir, name)):
            n += 1
            name = "{}_{}{}".format(base, n, ext)
        saved = safe_join(store.input_dir, name)
        os.replace(tmp, saved)
        return saved


# [OLD 2026-11-03 v0.5.1->v0.6.0] kept files that could not be read, joined several file parts into one corrupt file and
# held the whole upload in memory on the event loop
# @routes.post("/reelwright/upload")
# @json_route
# async def upload(request):
#     reader = await request.multipart()
#     slug, saved, original = None, None, None
#     tmp_parts = []
#     while True:
#         part = await reader.next()
#         if part is None:
#             break
#         if part.name == "slug":
#             slug = check_slug((await part.text()).strip())
#         elif part.name == "file":
#             original = part.filename
#             tmp_parts.append(await part.read(decode=False))
#     if not slug or not tmp_parts:
#         raise ValueError("upload needs a file and a slug")
#     base, ext = _safe_filename(original)
#     if media.kind_of(base + ext) is None:
#         raise ValueError("unsupported file type: " + ext)
#     store = slug_store(slug)
#     os.makedirs(store.input_dir, exist_ok=True)
#     n, name = 1, base + ext
#     while os.path.exists(os.path.join(store.input_dir, name)):
#         n += 1
#         name = "{}_{}{}".format(base, n, ext)
#     saved = safe_join(store.input_dir, name)
#     with open(saved, "wb") as f:
#         f.write(b"".join(tmp_parts))
#     info = await asyncio.to_thread(media.describe, saved)
#     category = {"image": "subject", "video": "motion", "audio": "voice"}[info["kind"]]
#     return {"asset": dict(info, file=os.path.relpath(saved, store.roots.input).replace(os.sep, "/"),
#                           name=os.path.splitext(original or name)[0], category=category)}
# [/OLD]
@routes.post("/reelwright/upload")
@json_route
async def upload(request):
    """One file part ("file") and the project slug ("slug"), in either order. The file is streamed to a temp file
    in 1 MB chunks (writes off the event loop), checked to be readable media, then moved into
    input/reelwright/<slug>/ (added 2026-11-03 v0.6.0)."""
    # added 2026-11-04 v0.6.1: another body (JSON, none) hit an assert in aiohttp's multipart reader: 500, not 400
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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] one folder with an unexpected name made the whole list fail (400)
    # ids = [d for d in os.listdir(sdir) if os.path.isdir(os.path.join(sdir, d))] if os.path.isdir(sdir) else []
    ids = [d for d in os.listdir(sdir) if ID_RE.match(d) and os.path.isdir(os.path.join(sdir, d))] \
        if os.path.isdir(sdir) else []
    # [OLD 2026-11-03 v0.5.1->v0.6.0] return {"scenes": {sid: store.read_index(sid) for sid in ids}}  (takes now hold per-pass prompts)
    from .analysis import TAKE_FIELDS_NOT_IN_PLAN  # added 2026-11-03 v0.6.0

    def lean(idx):
        idx["takes"] = [{k: v for k, v in t.items() if k not in TAKE_FIELDS_NOT_IN_PLAN} for t in idx.get("takes", [])]
        return idx
    return {"scenes": {sid: lean(store.read_index(sid)) for sid in ids}}


@routes.post("/reelwright/takes/star")
@json_route
async def star(request):
    b = await body_of(request)
    # [OLD 2026-11-03 v0.6.0 review] slug_store(b["slug"]).star(check_id(b["scene_id"]), check_id(b["take_id"]))
    # added 2026-11-03 v0.6.0 review: the project lock is waited for in a worker thread, not on the event loop (an
    # import hashing a big file held it and every request of the whole server waited)
    await asyncio.to_thread(slug_store(b["slug"]).star, check_id(b["scene_id"]), check_id(b["take_id"]))
    return {"ok": True}


@routes.post("/reelwright/takes/delete")
@json_route
async def delete_take(request):
    b = await body_of(request)
    # [OLD 2026-11-03 v0.6.0 review] slug_store(b["slug"]).delete_take(check_id(b["scene_id"]), check_id(b["take_id"]))
    # added 2026-11-03 v0.6.0 review: the lock and the folder removal in a worker thread, not on the event loop
    await asyncio.to_thread(slug_store(b["slug"]).delete_take, check_id(b["scene_id"]), check_id(b["take_id"]))
    return {"ok": True}


# [OLD 2026-11-03 v0.5.1->v0.6.0] one merge could run over another (same cut files), no cancel, no draft / range / stems
# @routes.post("/reelwright/merge")
# @json_route
# async def merge_route(request):
#     b = await body_of(request)
#     p, store = project_store(b["project"])
#     server = PromptServer.instance
#
#     def progress(x):
#         server.send_sync("reelwright.merge", {"slug": p["slug"], "phase": "progress", "percent": round(x * 100, 1)})
#
#     def work():
#         store.autosave(p)
#         result = analyze(p, store, wired_flags(store))
#         return assemble.merge_project(result, store, progress)
#
#     server.send_sync("reelwright.merge", {"slug": p["slug"], "phase": "start"})
#     try:
#         out = await asyncio.to_thread(work)
#     except Exception as e:
#         server.send_sync("reelwright.merge", {"slug": p["slug"], "phase": "end", "error": str(e)})
#         raise
#     server.send_sync("reelwright.merge", {"slug": p["slug"], "phase": "end", "files": out["files"]})
#     return dict(out, ok=True)
# [/OLD]
@routes.post("/reelwright/merge")
@json_route
async def merge_route(request):
    """added 2026-11-03 v0.6.0: {project, draft?, range?: [from_sid, to_sid], stems?, job?}. One merge per project:
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
    """added 2026-11-03 v0.6.0: {job} stops that merge; {slug} without a job stops any merge of the project (the
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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] p, store = project_store(b["project"])
    # [OLD 2026-11-03 v0.5.1->v0.6.0] version = await asyncio.to_thread(store.autosave, b["project"], bool(b.get("version")))
    # added 2026-11-03 v0.6.0: the project must be an object; a folder that holds a different project answers 409
    # {reason: "slug_conflict", other: {id, name}} unless the body says force: true (take the folder over)
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


# added 2026-11-02 v0.3.6: delete autosaved versions; {"names": [...]} or {"all": true}
@routes.post("/reelwright/versions/delete")
@json_route
async def versions_delete(request):
    b = await body_of(request)
    store = slug_store(b.get("slug", ""))
    # [OLD 2026-11-03 v0.5.1->v0.6.0] names = [v["name"] for v in store.list_versions()] if b.get("all") else b.get("names") or []
    names = [v["name"] for v in store.list_versions()] if b.get("all") else _str_list(b.get("names"), "names")
    removed = await asyncio.to_thread(store.delete_versions, names)
    return {"removed": removed, "versions": store.list_versions()}


@routes.get("/reelwright/version")
@json_route
async def version(request):
    store = slug_store(request.query.get("slug", ""))
    return {"project": store.read_version(request.query.get("name", ""))}


# ---- anchor sheet preview (added 2026-11-03 v0.4.1) ------------------------------
# The exact sheet the renderer sends for a character's anchors (media.sheet_image), as a JPEG.

@routes.get("/reelwright/sheet")
async def anchor_sheet(request):
    try:
        rels = json.loads(request.query.get("files", "[]"))
        # [OLD 2026-11-03 v0.5.1->v0.6.0] if not isinstance(rels, list) or not rels or len(rels) > 64:
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
    # added 2026-11-04 v0.6.1: a file that is not a readable picture (PIL's UnidentifiedImageError is an OSError, a
    # truncated one OSError or SyntaxError) answered 500
    except (OSError, SyntaxError) as e:
        return web.json_response({"error": "a picture can't be read: {}".format(_message(e)[:300])}, status=400)


# ---- soundtrack waveforms (added 2026-11-03 v0.5.0) ------------------------------
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


# ---- timeline filmstrips (added 2026-11-05 v0.7.0) ------------------------------
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


# ---- speech timing (added 2026-11-06 v0.10.0) -------------------------------
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


# ---- disk use (added 2026-11-03 v0.4.0) --------------------------------------
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
    # [OLD 2026-11-03 v0.6.0 review] result = await asyncio.to_thread(diskuse.delete, roots(), b.get("ids") or [], current)
    # added 2026-11-03 v0.6.0 review: {"ids": 5} answered 500 ("'int' object is not iterable")
    ids = b.get("ids") or []
    if not isinstance(ids, list):
        raise ValueError("ids must be a list of ids")
    result = await asyncio.to_thread(diskuse.delete, roots(), ids, current)
    log.info("Reelwright: deleted %d item(s), %.1f MB freed%s", result["removed"], result["freed"] / 1048576,
             "; {} refused".format(len(result["errors"])) if result["errors"] else "")
    return result


# added 2026-11-03 v0.6.0: Files tab "Repair": re-list takes from their meta.json, rebuild missing/damaged index.json
@routes.post("/reelwright/storage/repair")
@json_route
async def storage_repair(request):
    b = await body_of(request)
    store = slug_store(_str(b, "slug"))
    out = await asyncio.to_thread(store.repair)
    log.info("Reelwright: repaired %s: %d scene(s) changed, %d take(s) found", store.slug, len(out["repaired"]),
             out["takes_found"])
    return dict(out, ok=True)


# ---- beat markers and the soundtrack a pass hears (added 2026-11-03 v0.6.0) --------------------------------------

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
    # [OLD 2026-11-02 v0.1.0->v0.2.0] return {"base_url": s["base_url"], "model": s["model"], "has_key": bool(s["api_key"])}
    return {"base_url": s["base_url"], "model": s["model"], "has_key": bool(s["api_key"]),
            "guides": llm.guide_status(_user_root()), "guide_urls": llm.GUIDES}


# added 2026-11-02 v0.2.0: download MiniMax's official prompt guides into user/reelwright/guides
@routes.post("/reelwright/llm/guides")
@json_route
async def llm_guides_fetch(request):
    return {"guides": await llm.fetch_guides(_user_root())}


def _cfg(p):
    """LLM config for a project, with the downloaded guides attached (added 2026-11-02 v0.2.0)."""
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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] base = (b.get("base_url") or s["base_url"]).rstrip("/")
    base = (_str(b, "base_url", required=False) or s["base_url"] or "").rstrip("/")
    if not base:
        raise ValueError("Set the LLM base URL first")
    return {"models": await llm.list_models(base, s["api_key"])}


# ---- Global profiles (added 2026-11-02 v0.3.0) ----------------------------------------------

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
    # [OLD 2026-11-02 v0.1.0->v0.2.0] cfg = llm.resolve((b.get("project") or {}).get("global", {}).get("llm", {}), llm.load_settings(_user_root()))
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
    # [OLD 2026-11-02 v0.1.0->v0.2.0] the rewrite did not see the built prompt or the guides
    # p = normalize_project(b["project"])
    # cfg = llm.resolve(p["global"]["llm"], llm.load_settings(_user_root()))
    # return await llm.rewrite(cfg, p, _scene(p, b["scene_id"]), b.get("instruction", ""))
    # [/OLD]
    # [OLD 2026-11-03 v0.5.1->v0.6.0] the job was registered after analyze: Stop during the analysis was lost
    # p, store = project_store(b["project"])
    # cfg = _cfg(p)
    # scene = _scene(p, b["scene_id"])
    # result = await asyncio.to_thread(analyze, p, store, wired_flags(store))
    # prompts = result["scenes"][scene["id"]]["prompts"]
    # # [OLD 2026-11-03 v0.4.0->v0.4.1] return await llm.rewrite(cfg, p, scene, b.get("instruction", ""), prompts[0] if prompts else "")
    # builds = result["scenes"][scene["id"]]["builds"]  # added 2026-11-03 v0.4.1: labels back to @ tokens
    # # [OLD 2026-11-03 v0.4.1->v0.4.2] return await llm.rewrite(cfg, p, scene, b.get("instruction", ""), prompts[0] if prompts else "",
    # #                              builds[0]["tag_map"] if builds else None)
    # job = _job_id(b)
    # return await _llm_job(job, llm.rewrite(cfg, p, scene, b.get("instruction", ""), prompts[0] if prompts else "",
    #                                        builds[0]["tag_map"] if builds else None, progress=_llm_progress(job)))
    # [/OLD]
    p, store = project_store(_project(b))
    cfg = _cfg(p)
    scene = _scene(p, b.get("scene_id"))
    instruction = _str(b, "instruction", "")  # added 2026-11-03 v0.6.0
    job = _job_id(b)

    # added 2026-11-03 v0.6.0: the job is registered before the analysis, so Stop during it is not lost
    async def work():
        result = await asyncio.to_thread(analyze, p, store, wired_flags(store))
        prompts = result["scenes"][scene["id"]]["prompts"]
        builds = result["scenes"][scene["id"]]["builds"]  # added 2026-11-03 v0.4.1: labels back to @ tokens
        return await llm.rewrite(cfg, p, scene, instruction, prompts[0] if prompts else "",
                                 builds[0]["tag_map"] if builds else None, progress=_llm_progress(job))
    return await _llm_job(job, work())


@routes.post("/reelwright/llm/split")
@json_route
async def llm_split(request):
    b = await body_of(request)
    # [OLD 2026-11-03 v0.5.1->v0.6.0] the job was registered after analyze: Stop during the analysis was lost
    # p, store = project_store(b["project"])
    # cfg = _cfg(p)  # [OLD 2026-11-02 v0.1.0->v0.2.0] llm.resolve(p["global"]["llm"], llm.load_settings(_user_root()))
    # result = await asyncio.to_thread(analyze, p, store, wired_flags(store))
    # sr = result["scenes"][_scene(p, b["scene_id"])["id"]]
    # # [OLD 2026-11-03 v0.4.1->v0.4.2] pass_prompts = await llm.split(cfg, p, _scene(p, b["scene_id"]), sr["passes"], sr["prompts"])
    # # return {"pass_prompts": pass_prompts}
    # job = _job_id(b)
    # out = await _llm_job(job, llm.split(cfg, p, _scene(p, b["scene_id"]), sr["passes"], sr["prompts"],
    #                                     progress=_llm_progress(job)))
    # return out if out.get("cancelled") else {"pass_prompts": out}
    # [/OLD]
    p, store = project_store(_project(b))
    cfg = _cfg(p)  # [OLD 2026-11-02 v0.1.0->v0.2.0] llm.resolve(p["global"]["llm"], llm.load_settings(_user_root()))
    scene = _scene(p, b.get("scene_id"))
    job = _job_id(b)

    # added 2026-11-03 v0.6.0: the job is registered before the analysis, so Stop during it is not lost
    async def work():
        result = await asyncio.to_thread(analyze, p, store, wired_flags(store))
        sr = result["scenes"][scene["id"]]
        return await llm.split(cfg, p, scene, sr["passes"], sr["prompts"], progress=_llm_progress(job))
    out = await _llm_job(job, work())
    return out if isinstance(out, dict) and out.get("cancelled") else {"pass_prompts": out}


# added 2026-11-05 v0.8.0: Write prompts. The six sections of each requested pass of a scene, one LLM request per pass
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
    cfg = _cfg(p)  # [OLD 2026-11-02 v0.1.0->v0.2.0] llm.resolve(p["global"]["llm"], llm.load_settings(_user_root()))
    # [OLD 2026-11-03 v0.5.1->v0.6.0] if not (b.get("script") or "").strip():
    if not (_str(b, "script", "", max_len=10 ** 7) or "").strip():
        raise ValueError("Paste a script first")
    # [OLD 2026-11-03 v0.4.1->v0.4.2] return await llm.script_to_scenes(cfg, p, b["script"])
    # added 2026-11-03 v0.4.2: one part of a script (see /reelwright/llm/script/parts), with progress events and Cancel
    job = _job_id(b)
    # [OLD 2026-11-03 v0.5.1->v0.6.0] part, parts = max(1, int(b.get("part") or 1)), max(1, int(b.get("parts") or 1))
    part, parts = max(1, _int(b.get("part") or 1, "part")), max(1, _int(b.get("parts") or 1, "parts"))
    if not isinstance(b.get("known_cast") or [], list):  # added 2026-11-03 v0.6.0
        raise ValueError("known_cast must be a list")
    # added 2026-11-03 v0.6.0 review: [{"name": 5}] answered 500 ("'int' object has no attribute 'lower'")
    if not all(isinstance(c, dict) and isinstance(c.get("name", ""), str) for c in b.get("known_cast") or []):
        raise ValueError("known_cast must be a list of {name: text, kind}")
    return await _llm_job(job, llm.script_part(
        cfg, p, b["script"], part=part, parts=parts, notes=str(b.get("notes") or ""),
        known_cast=b.get("known_cast") or [], progress=_llm_progress(job, part=part, parts=parts),
        retry_cut=not b.get("can_split")))


# ---- long LLM requests: parts, progress, cancel (added 2026-11-03 v0.4.2) -----------------------

LLM_JOBS = {}  # job id -> the asyncio task doing the request
LLM_CANCELLED = set()  # added 2026-11-04 v0.6.1: holds the cancelled tasks (it held job ids)


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
    # [OLD 2026-11-04 v0.6.0->v0.6.1] two requests with one job id shared an entry: the first to end removed the
    # other's (Cancel then missed it) and cleared its cancel mark
    # if job:
    #     LLM_JOBS[job] = task
    # try:
    #     return await task
    # except asyncio.CancelledError:
    #     if job in LLM_CANCELLED:
    #         return {"cancelled": True}
    #     raise
    # finally:
    #     if job:
    #         LLM_JOBS.pop(job, None)
    #         LLM_CANCELLED.discard(job)
    # [/OLD]
    # added 2026-11-04 v0.6.1: the newest request owns the job id; each one removes only its own entry and mark
    # (LLM_CANCELLED holds the cancelled tasks)
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


# added 2026-11-12 v0.13.0: Chat tab: a general question to the configured LLM, with the conversation so far. Progress
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
    # [OLD 2026-11-04 v0.6.0->v0.6.1] LLM_CANCELLED.add(job)  (by id: a second request with that id inherited the mark)
    LLM_CANCELLED.add(task)  # added 2026-11-04 v0.6.1: the task that is cancelled
    task.cancel()
    return {"ok": True, "cancelled": True}


@routes.post("/reelwright/llm/script/parts")
@json_route
async def llm_script_parts(request):
    b = await body_of(request)
    size = llm.limits({"import_part_chars": b.get("part_chars", 3000)})["import_part_chars"]
    # [OLD 2026-11-03 v0.6.0 review] return scriptparts.split_script(str(b.get("script") or ""), size)  (a list became "['a']")
    # added 2026-11-03 v0.6.0 review: the script must be text, as for /llm/script
    return scriptparts.split_script(_str(b, "script", "", required=False, max_len=10 ** 7) or "", size)


# added 2026-11-02 v0.2.0: describe pictures (or video frames) with a vision model
@routes.post("/reelwright/llm/describe")
@json_route
async def llm_describe(request):
    b = await body_of(request)
    p, store = project_store(b["project"])
    idx = project_index(p)
    images = []
    # [OLD 2026-11-03 v0.5.1->v0.6.0] for aid in (b.get("asset_ids") or [])[:4]:
    for aid in _str_list(b.get("asset_ids"), "asset_ids")[:4]:
        a = idx["assets"].get(aid)
        if not a:
            raise ValueError("unknown asset")
        path = store.input_path(a["file"])
        if not os.path.isfile(path):
            raise FileNotFoundError("{} file is missing".format(a["code"]))
        images += await asyncio.to_thread(media.stills_for_vision, path)
    # [OLD 2026-11-03 v0.5.1->v0.6.0] return await llm.describe(_cfg(p), images[:6], (b.get("prompt") or "").strip())
    return await llm.describe(_cfg(p), images[:6], (_str(b, "prompt", "") or "").strip())


# ---- ComfyUI input/output browser (added 2026-11-02 v0.2.0) ------------------------------

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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] q.get("kind", ""), min(1000, int(q.get("limit", 400))))
    return await asyncio.to_thread(media.list_media, _media_root(q.get("root", "input")), q.get("q", ""),
                                   q.get("kind", ""), max(1, min(1000, _int(q.get("limit", 400), "limit"))))


@routes.post("/reelwright/import")
@json_route
async def import_file(request):
    """Use a file that is already in ComfyUI's input or output folder as an asset.
    Input files are used where they are; output files are linked (or copied) into the project's input folder."""
    # [OLD 2026-11-03 v0.5.1->v0.6.0] same name and size counted as the same file
    # b = await body_of(request)
    # store = slug_store(b["slug"])
    # root = b.get("root", "input")
    # src = safe_join(_media_root(root), b["rel"])
    # if not os.path.isfile(src) or media.kind_of(src) is None:
    #     raise ValueError("not a picture, video or audio file: " + b["rel"])
    # if root == "input":
    #     dst = src
    # else:
    #     base, ext = _safe_filename(b["rel"])
    #     folder = os.path.join(store.input_dir, "from_output")
    #     os.makedirs(folder, exist_ok=True)
    #     dst, n = os.path.join(folder, base + ext), 1
    #     while os.path.exists(dst) and not os.path.samefile(dst, src) and os.path.getsize(dst) != os.path.getsize(src):
    #         n += 1
    #         dst = os.path.join(folder, "{}_{}{}".format(base, n, ext))
    #     if not os.path.exists(dst):
    #         try:
    #             os.link(src, dst)
    #         except OSError:
    #             await asyncio.to_thread(shutil.copyfile, src, dst)
    # [/OLD]
    b = await body_of(request)
    store = slug_store(b.get("slug"))
    root = b.get("root", "input")
    rel = _str(b, "rel")  # added 2026-11-03 v0.6.0
    src = safe_join(_media_root(root), rel)
    if not os.path.isfile(src) or media.kind_of(src) is None:
        raise ValueError("not a picture, video or audio file: " + rel)
    if root == "input":
        dst = src
    else:
        base, ext = _safe_filename(rel)
        folder = os.path.join(store.input_dir, "from_output")
        # added 2026-11-03 v0.6.0: an existing file is reused only when it has the same bytes (a different file
        # with the same name and size was attached before)
        dst = await asyncio.to_thread(_import_target, store, folder, src, base, ext)
    info = await asyncio.to_thread(media.describe, dst)
    category = {"image": "subject", "video": "motion", "audio": "voice"}[info["kind"]]
    return {"asset": dict(info, file=os.path.relpath(dst, store.roots.input).replace(os.sep, "/"),
                          name=os.path.splitext(os.path.basename(src))[0], category=category)}


# ---- takes, cast, continuity -----------------------------------------------

def _same_content(a, b):
    """added 2026-11-03 v0.6.0"""
    try:
        if os.path.samefile(a, b):
            return True
        return os.path.getsize(a) == os.path.getsize(b) and cache.file_digest(a) == cache.file_digest(b)
    except OSError:
        return False


# [OLD 2026-11-03 v0.6.0 review] hashed and copied a big file while holding the project lock, so a star, a take
# delete or an autosave of the project waited for the whole copy
# def _import_target(store, folder, src, base, ext):
#     """added 2026-11-03 v0.6.0: the file in from_output/ that holds src's bytes: an existing one with the same
#     content, else a new hard link (or copy) under a free name."""
#     with jobs.lock(store.slug):
#         os.makedirs(folder, exist_ok=True)
#         dst, n = os.path.join(folder, base + ext), 1
#         while os.path.exists(dst) and not _same_content(dst, src):
#             n += 1
#             dst = os.path.join(folder, "{}_{}{}".format(base, n, ext))
#         if not os.path.exists(dst):
#             try:
#                 os.link(src, dst)
#             except OSError:
#                 shutil.copyfile(src, dst)
#         return dst
# [/OLD]
def _import_target(store, folder, src, base, ext):
    """added 2026-11-03 v0.6.0: the file in from_output/ that holds src's bytes: an existing one with the same
    content, else a new hard link (or copy) under a free name.
    added 2026-11-03 v0.6.0 review: the hashing and the copy happen outside the project lock; the lock is held only
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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] which was not checked
    # b = await body_of(request)
    # store = slug_store(b["slug"])
    # take = _take(store, b["scene_id"], b["take_id"])
    # which = b.get("which", "last")
    # os.makedirs(store.input_dir, exist_ok=True)
    # name = "promoted_{}_{}_{}.png".format(check_id(b["scene_id"]), check_id(take["id"]),
    #                                      which if which != "time" else "t{:.2f}".format(float(b.get("t") or 0)))
    # [/OLD]
    b = await body_of(request)
    store = slug_store(b.get("slug"))
    take = _take(store, b.get("scene_id"), b.get("take_id"))
    which = b.get("which", "last")
    # added 2026-11-03 v0.6.0: `which` went into the file name unchecked ("../x" wrote outside the promoted_ name)
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
        # [OLD 2026-11-03 v0.5.1->v0.6.0] str(float(b.get("t") or 0)), "-i", store.output_path(take["files"]["video"]),
        # [OLD 2026-11-04 v0.6.0->v0.6.1] check=True: an ffmpeg failure (unreadable take video) left as a 500
        # await asyncio.to_thread(subprocess.run, [ff, "-hide_banner", "-loglevel", "error", "-y", "-ss",
        #                                          str(t), "-i", store.output_path(take["files"]["video"]),
        #                                          "-frames:v", "1", dst], check=True)
        # [/OLD]
        # added 2026-11-04 v0.6.1: ffmpeg's own message, as a 400 like the other unreadable-media answers
        r = await asyncio.to_thread(subprocess.run, [ff, "-hide_banner", "-loglevel", "error", "-y", "-ss",
                                                     str(t), "-i", store.output_path(take["files"]["video"]),
                                                     "-frames:v", "1", dst], capture_output=True, text=True)
        if r.returncode != 0:
            raise merge.MergeError("ffmpeg could not grab a frame at {:.2f} s: {}".format(
                t, (r.stderr or "").strip()[-400:] or "exit code {}".format(r.returncode)))
    # [OLD 2026-11-04 v0.6.0->v0.6.1] info = await asyncio.to_thread(media.describe, dst)  (an unreadable picture: PIL's OSError, 500)
    try:  # added 2026-11-04 v0.6.1: 400 like the other unreadable-media answers
        info = await asyncio.to_thread(media.describe, dst)
    except FileNotFoundError:
        raise
    except (OSError, SyntaxError) as e:
        raise ValueError("the frame can't be read as a picture: {}".format(_message(e)[:300])) from e
    return {"asset": dict(info, file=os.path.relpath(dst, store.roots.input).replace(os.sep, "/"),
                          name="{} frame".format(which), category="subject")}


# added 2026-11-06 v0.10.0: a character's rendered lines as their voice reference (Cast tab -> Voice from a take)
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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] c = idx["cast"].get(b["cast_id"])
    c = idx["cast"].get(_str(b, "cast_id"))
    if not c:
        raise ValueError("unknown cast member")
    folder = os.path.join(store.cast_dir(c["id"]), "training")
    os.makedirs(folder, exist_ok=True)
    # [OLD 2026-11-02 v0.3.3->v0.3.4] caption = "{}, {}".format(re.sub(r"\W+", "_", c["name"]).lower(), c["description"]).strip(", ")
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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] read-modify-write of index.json without the project lock
    # idx = store.read_index(scene["id"])
    # for t in idx["takes"]:
    #     if t["id"] == take["id"]:
    #         t["face"] = scores
    # store.write_index(scene["id"], idx)
    # [/OLD]

    def save():  # added 2026-11-03 v0.6.0
        with jobs.lock(store.slug):
            idx = store.read_index(scene["id"])
            for t in idx["takes"]:
                if t["id"] == take["id"]:
                    t["face"] = scores
            store.write_index(scene["id"], idx)
    await asyncio.to_thread(save)
    return {"available": True, "scores": scores}
