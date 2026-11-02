"""/reelwright/* HTTP routes used by the editor."""

import asyncio
import functools
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess

import comfy.samplers
import folder_paths
from aiohttp import web
from server import PromptServer

# [OLD 2026-11-02 v0.2.2->v0.3.0] from . import VERSION, assemble, continuity, llm, media, merge
from . import VERSION, assemble, continuity, llm, media, merge, profiles
from .analysis import analyze, plan_response
# [OLD 2026-11-02 v0.3.3->v0.3.4] from .model import normalize_project, project_index
from .model import cast_description, normalize_project, project_index
from .storage import ProjectStore, Roots, check_id, check_slug, read_json, safe_join

log = logging.getLogger("reelwright")
routes = PromptServer.instance.routes


def roots():
    return Roots(folder_paths.get_output_directory(), folder_paths.get_input_directory(),
                 folder_paths.get_user_directory())


def wired_flags(store):
    return read_json(os.path.join(store.dir, "wired.json"), {}) or {}


def json_route(fn):
    @functools.wraps(fn)
    async def wrapper(request):
        try:
            return web.json_response(await fn(request))
        except (ValueError, KeyError, FileNotFoundError, merge.MergeError, json.JSONDecodeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            log.exception("Reelwright route %s failed", request.path)
            return web.json_response({"error": str(e)}, status=500)
    return wrapper


async def body_of(request):
    return await request.json()


def project_store(project):
    p = normalize_project(project)
    return p, ProjectStore(roots(), p["slug"])


def slug_store(slug):
    return ProjectStore(roots(), check_slug(slug))


@routes.get("/reelwright/info")
@json_route
async def info(request):
    return {"version": VERSION, "ffmpeg": merge.ffmpeg_bin() or False,
            "insightface": continuity.available(),
            "h3_nodes": importlib.util.find_spec("comfy_extras.nodes_minimax_h3") is not None}


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


@routes.post("/reelwright/upload")
@json_route
async def upload(request):
    reader = await request.multipart()
    slug, saved, original = None, None, None
    tmp_parts = []
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "slug":
            slug = check_slug((await part.text()).strip())
        elif part.name == "file":
            original = part.filename
            tmp_parts.append(await part.read(decode=False))
    if not slug or not tmp_parts:
        raise ValueError("upload needs a file and a slug")
    base, ext = _safe_filename(original)
    if media.kind_of(base + ext) is None:
        raise ValueError("unsupported file type: " + ext)
    store = slug_store(slug)
    os.makedirs(store.input_dir, exist_ok=True)
    n, name = 1, base + ext
    while os.path.exists(os.path.join(store.input_dir, name)):
        n += 1
        name = "{}_{}{}".format(base, n, ext)
    saved = safe_join(store.input_dir, name)
    with open(saved, "wb") as f:
        f.write(b"".join(tmp_parts))
    info = await asyncio.to_thread(media.describe, saved)
    category = {"image": "subject", "video": "motion", "audio": "voice"}[info["kind"]]
    return {"asset": dict(info, file=os.path.relpath(saved, store.roots.input).replace(os.sep, "/"),
                          name=os.path.splitext(original or name)[0], category=category)}


@routes.get("/reelwright/takes")
@json_route
async def takes(request):
    store = slug_store(request.query.get("slug", ""))
    sdir = os.path.join(store.dir, "scenes")
    ids = [d for d in os.listdir(sdir) if os.path.isdir(os.path.join(sdir, d))] if os.path.isdir(sdir) else []
    return {"scenes": {sid: store.read_index(sid) for sid in ids}}


@routes.post("/reelwright/takes/star")
@json_route
async def star(request):
    b = await body_of(request)
    slug_store(b["slug"]).star(check_id(b["scene_id"]), check_id(b["take_id"]))
    return {"ok": True}


@routes.post("/reelwright/takes/delete")
@json_route
async def delete_take(request):
    b = await body_of(request)
    slug_store(b["slug"]).delete_take(check_id(b["scene_id"]), check_id(b["take_id"]))
    return {"ok": True}


@routes.post("/reelwright/merge")
@json_route
async def merge_route(request):
    b = await body_of(request)
    p, store = project_store(b["project"])
    server = PromptServer.instance

    def progress(x):
        server.send_sync("reelwright.merge", {"slug": p["slug"], "phase": "progress", "percent": round(x * 100, 1)})

    def work():
        store.autosave(p)
        result = analyze(p, store, wired_flags(store))
        return assemble.merge_project(result, store, progress)

    server.send_sync("reelwright.merge", {"slug": p["slug"], "phase": "start"})
    try:
        out = await asyncio.to_thread(work)
    except Exception as e:
        server.send_sync("reelwright.merge", {"slug": p["slug"], "phase": "end", "error": str(e)})
        raise
    server.send_sync("reelwright.merge", {"slug": p["slug"], "phase": "end", "files": out["files"]})
    return dict(out, ok=True)


@routes.post("/reelwright/autosave")
@json_route
async def autosave(request):
    b = await body_of(request)
    p, store = project_store(b["project"])
    version = await asyncio.to_thread(store.autosave, b["project"], bool(b.get("version")))
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
    names = [v["name"] for v in store.list_versions()] if b.get("all") else b.get("names") or []
    removed = await asyncio.to_thread(store.delete_versions, names)
    return {"removed": removed, "versions": store.list_versions()}


@routes.get("/reelwright/version")
@json_route
async def version(request):
    store = slug_store(request.query.get("slug", ""))
    return {"project": store.read_version(request.query.get("name", ""))}


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
    base = (b.get("base_url") or s["base_url"]).rstrip("/")
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
    p, store = project_store(b["project"])
    cfg = _cfg(p)
    scene = _scene(p, b["scene_id"])
    result = await asyncio.to_thread(analyze, p, store, wired_flags(store))
    prompts = result["scenes"][scene["id"]]["prompts"]
    return await llm.rewrite(cfg, p, scene, b.get("instruction", ""), prompts[0] if prompts else "")


@routes.post("/reelwright/llm/split")
@json_route
async def llm_split(request):
    b = await body_of(request)
    p, store = project_store(b["project"])
    cfg = _cfg(p)  # [OLD 2026-11-02 v0.1.0->v0.2.0] llm.resolve(p["global"]["llm"], llm.load_settings(_user_root()))
    result = await asyncio.to_thread(analyze, p, store, wired_flags(store))
    sr = result["scenes"][_scene(p, b["scene_id"])["id"]]
    pass_prompts = await llm.split(cfg, p, _scene(p, b["scene_id"]), sr["passes"], sr["prompts"])
    return {"pass_prompts": pass_prompts}


@routes.post("/reelwright/llm/script")
@json_route
async def llm_script(request):
    b = await body_of(request)
    p = normalize_project(b["project"])
    cfg = _cfg(p)  # [OLD 2026-11-02 v0.1.0->v0.2.0] llm.resolve(p["global"]["llm"], llm.load_settings(_user_root()))
    if not (b.get("script") or "").strip():
        raise ValueError("Paste a script first")
    return await llm.script_to_scenes(cfg, p, b["script"])


# added 2026-11-02 v0.2.0: describe pictures (or video frames) with a vision model
@routes.post("/reelwright/llm/describe")
@json_route
async def llm_describe(request):
    b = await body_of(request)
    p, store = project_store(b["project"])
    idx = project_index(p)
    images = []
    for aid in (b.get("asset_ids") or [])[:4]:
        a = idx["assets"].get(aid)
        if not a:
            raise ValueError("unknown asset")
        path = store.input_path(a["file"])
        if not os.path.isfile(path):
            raise FileNotFoundError("{} file is missing".format(a["code"]))
        images += await asyncio.to_thread(media.stills_for_vision, path)
    return await llm.describe(_cfg(p), images[:6], (b.get("prompt") or "").strip())


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
    return await asyncio.to_thread(media.list_media, _media_root(q.get("root", "input")), q.get("q", ""),
                                   q.get("kind", ""), min(1000, int(q.get("limit", 400))))


@routes.post("/reelwright/import")
@json_route
async def import_file(request):
    """Use a file that is already in ComfyUI's input or output folder as an asset.
    Input files are used where they are; output files are linked (or copied) into the project's input folder."""
    b = await body_of(request)
    store = slug_store(b["slug"])
    root = b.get("root", "input")
    src = safe_join(_media_root(root), b["rel"])
    if not os.path.isfile(src) or media.kind_of(src) is None:
        raise ValueError("not a picture, video or audio file: " + b["rel"])
    if root == "input":
        dst = src
    else:
        base, ext = _safe_filename(b["rel"])
        folder = os.path.join(store.input_dir, "from_output")
        os.makedirs(folder, exist_ok=True)
        dst, n = os.path.join(folder, base + ext), 1
        while os.path.exists(dst) and not os.path.samefile(dst, src) and os.path.getsize(dst) != os.path.getsize(src):
            n += 1
            dst = os.path.join(folder, "{}_{}{}".format(base, n, ext))
        if not os.path.exists(dst):
            try:
                os.link(src, dst)
            except OSError:
                await asyncio.to_thread(shutil.copyfile, src, dst)
    info = await asyncio.to_thread(media.describe, dst)
    category = {"image": "subject", "video": "motion", "audio": "voice"}[info["kind"]]
    return {"asset": dict(info, file=os.path.relpath(dst, store.roots.input).replace(os.sep, "/"),
                          name=os.path.splitext(os.path.basename(src))[0], category=category)}


# ---- takes, cast, continuity -----------------------------------------------

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
    store = slug_store(b["slug"])
    take = _take(store, b["scene_id"], b["take_id"])
    which = b.get("which", "last")
    os.makedirs(store.input_dir, exist_ok=True)
    name = "promoted_{}_{}_{}.png".format(check_id(b["scene_id"]), check_id(take["id"]),
                                         which if which != "time" else "t{:.2f}".format(float(b.get("t") or 0)))
    dst = safe_join(store.input_dir, name)
    if which in ("first", "last"):
        shutil.copyfile(store.output_path(take["files"][which]), dst)
    else:
        ff = merge.ffmpeg_bin()
        if not ff:
            raise ValueError("ffmpeg is needed to grab a frame at a time")
        await asyncio.to_thread(subprocess.run, [ff, "-hide_banner", "-loglevel", "error", "-y", "-ss",
                                                 str(float(b.get("t") or 0)), "-i", store.output_path(take["files"]["video"]),
                                                 "-frames:v", "1", dst], check=True)
    info = await asyncio.to_thread(media.describe, dst)
    return {"asset": dict(info, file=os.path.relpath(dst, store.roots.input).replace(os.sep, "/"),
                          name="{} frame".format(which), category="subject")}


@routes.post("/reelwright/cast/export")
@json_route
async def cast_export(request):
    b = await body_of(request)
    p, store = project_store(b["project"])
    idx = project_index(p)
    c = idx["cast"].get(b["cast_id"])
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
    idx = store.read_index(scene["id"])
    for t in idx["takes"]:
        if t["id"] == take["id"]:
            t["face"] = scores
    store.write_index(scene["id"], idx)
    return {"available": True, "scores": scores}
