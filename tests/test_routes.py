"""HTTP routes, served by aiohttp's test server with a stand-in PromptServer.

routes.py imports ComfyUI (server, folder_paths, comfy.samplers), so this runs with COMFYUI_PATH pointing at a
ComfyUI checkout whose requirements are installed, like test_render_flow.py.
"""

import asyncio
import importlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time

import pytest

COMFY = os.environ.get("COMFYUI_PATH")
pytestmark = pytest.mark.skipif(not COMFY or importlib.util.find_spec("torch") is None,
                                reason="needs COMFYUI_PATH and torch")


@pytest.fixture
def api(monkeypatch, roots):
    sys.path.insert(0, COMFY)
    from comfy.cli_args import args
    args.cpu = True
    import folder_paths
    import server
    from aiohttp import web
    folder_paths.set_output_directory(roots.output)
    folder_paths.set_input_directory(roots.input)
    folder_paths.set_user_directory(roots.user)
    events = []

    class FakeServer:
        def __init__(self):
            self.routes = web.RouteTableDef()

        def send_sync(self, event, data, sid=None):
            events.append((event, data))
    fake = FakeServer()
    monkeypatch.setattr(server.PromptServer, "instance", fake, raising=False)
    sys.modules.pop("reelwright.routes", None)
    routes = importlib.import_module("reelwright.routes")
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.add_routes(fake.routes)

    def run(fn):
        from aiohttp.test_utils import TestClient, TestServer

        async def main():
            async with TestClient(TestServer(app)) as client:
                return await fn(client)
        return asyncio.run(main())
    yield run, routes, events
    sys.modules.pop("reelwright.routes", None)
    sys.path.remove(COMFY)


async def post(c, path, body):
    r = await c.post(path, json=body)
    return r.status, await r.json()


async def get(c, path):
    r = await c.get(path)
    return r.status, await r.json()


def png_bytes(color=(200, 30, 30)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buf, "PNG")
    return buf.getvalue()


def ff_clip(path, seconds, size="160x90"):
    from reelwright import merge
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=s={}:r=24:d={}".format(size, seconds), "-f", "lavfi", "-i",
                    "sine=f=440:sample_rate=48000:d={}".format(seconds), "-ac", "2", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", "-c:a", "aac", "-shortest", path], check=True)
    return path


def small(harbor):
    harbor["global"]["output"].update(width=160, height=96)
    return harbor


# ---- input checks ---------------------------------------------------------------------------------------------------

def test_wrong_types_answer_400(api, store, harbor):
    run, routes, _ = api
    store.add_take("s_one", {"id": "v1", "files": {}})

    async def go(c):
        out = []
        out.append(await post(c, "/reelwright/versions/delete", {"slug": "harbor_lights", "names": [5]}))
        out.append(await get(c, "/reelwright/sheet?files=[1]"))
        out.append(await post(c, "/reelwright/takes/star", [1, 2]))
        out.append(await post(c, "/reelwright/autosave", {"project": ["x"]}))
        out.append(await post(c, "/reelwright/promote_frame", {"slug": "harbor_lights", "scene_id": "s_one",
                                                               "take_id": "v1", "which": "../mara"}))
        out.append(await post(c, "/reelwright/llm/script", {"project": harbor, "script": ["a"]}))
        out.append(await post(c, "/reelwright/llm/describe", {"project": harbor, "asset_ids": {"a": 1}}))
        out.append(await post(c, "/reelwright/import", {"slug": "harbor_lights", "root": "input", "rel": 5}))
        out.append(await post(c, "/reelwright/merge", {"project": harbor, "range": "s_one"}))
        return out
    for status, body in run(go):
        assert status == 400 and body["error"], body


def test_takes_skips_folders_with_odd_names(api, store):
    run, _, _ = api
    store.add_take("s_one", {"id": "v1"})
    os.makedirs(os.path.join(store.dir, "scenes", "bad name!"))
    status, body = run(lambda c: get(c, "/reelwright/takes?slug=harbor_lights"))
    assert status == 200 and list(body["scenes"]) == ["s_one"]


# ---- upload ---------------------------------------------------------------------------------------------------------

def test_upload_streams_checks_and_refuses(api, roots):
    run, _, _ = api
    from aiohttp import FormData

    def form(*files, slug="film", slug_first=False):
        f = FormData()
        if slug_first:
            f.add_field("slug", slug)
        for name, data in files:
            f.add_field("file", data, filename=name, content_type="application/octet-stream")
        if not slug_first:
            f.add_field("slug", slug)
        return f

    async def go(c):
        out = []
        for f in (form(("pic.png", png_bytes())),                                   # slug after the file
                  form(("pic.png", png_bytes((0, 0, 255))), slug_first=True),       # a second one: pic_2.png
                  form(("broken.png", b"\x89PNG not really")),
                  form(("song.mp3", b"ID3 nope" * 100)),
                  form(("a.png", png_bytes()), ("b.png", png_bytes())),
                  form(("empty.png", b"")),
                  form(("x.exe", b"MZ"))):
            r = await c.post("/reelwright/upload", data=f)
            out.append((r.status, await r.json()))
        return out
    res = run(go)
    assert [s for s, _ in res] == [200, 200, 400, 400, 400, 400, 400]
    assert res[0][1]["asset"]["file"] == "reelwright/film/pic.png" and res[0][1]["asset"]["kind"] == "image"
    assert res[1][1]["asset"]["file"] == "reelwright/film/pic_2.png"
    assert "can't be read" in res[2][1]["error"] and "one file" in res[4][1]["error"]
    assert sorted(os.listdir(os.path.join(roots.input, "reelwright", "film"))) == ["pic.png", "pic_2.png"]
    assert os.listdir(os.path.join(roots.input, "reelwright", ".uploads")) == []


# ---- autosave: one project per folder ---------------------------------------------------------------------------------

def test_autosave_slug_conflict(api, harbor):
    run, _, _ = api
    a = dict(harbor, project_id="p_a", name="Harbor Lights")
    b = dict(harbor, project_id="p_b", name="Harbor Lights")

    async def go(c):
        return [await post(c, "/reelwright/autosave", {"project": a}),
                await post(c, "/reelwright/autosave", {"project": b}),
                await post(c, "/reelwright/autosave", {"project": b, "force": True}),
                await post(c, "/reelwright/autosave", {"project": a})]
    res = run(go)
    assert [s for s, _ in res] == [200, 409, 200, 409]
    assert res[1][1]["reason"] == "slug_conflict" and res[1][1]["other"] == {"id": "p_a", "name": "Harbor Lights"}
    assert res[3][1]["other"]["id"] == "p_b"


# ---- merge: one at a time, cancel, options ----------------------------------------------------------------------------

def _takes(store, harbor):
    from reelwright.analysis import analyze
    r = analyze(harbor, store)
    for sid, secs in (("s_one", 2.0), ("s_short", 2.5)):
        d = store.take_dir(sid, "v1")
        os.makedirs(d, exist_ok=True)
        ff_clip(os.path.join(d, "v.mp4"), secs)
        store.add_take(sid, {"id": "v1", "key": r["scenes"][sid]["key"], "seconds": secs,
                             "files": {"video": store.rel_output(os.path.join(d, "v.mp4"))}})


def test_merge_route_busy_options_and_events(api, store, harbor):
    run, routes, events = api
    from reelwright import jobs
    p = small(harbor)
    _takes(store, p)

    async def go(c):
        out = []
        with jobs.exclusive("harbor_lights", "merge", "held"):
            out.append(await post(c, "/reelwright/merge", {"project": p}))
        out.append(await post(c, "/reelwright/merge/cancel", {"job": "nope"}))
        out.append(await post(c, "/reelwright/merge/cancel", {}))
        out.append(await post(c, "/reelwright/merge", {"project": p, "job": "j1", "draft": True, "stems": True,
                                                       "range": ["s_one", "s_long"]}))
        return out
    busy, nope, empty, ok = run(go)
    assert busy == (409, {"error": "busy", "message": busy[1]["message"]})
    assert nope == (200, {"ok": True, "cancelled": False}) and empty[0] == 400
    assert ok[0] == 200 and ok[1]["ok"] and ok[1]["job"] == "j1" and ok[1]["files"]["video"].endswith("_draft_s01-02.mp4")
    assert ok[1]["loudness"]["integrated"] is not None and ok[1]["range"] == ["s_one", "s_long"]
    merges = [d for e, d in events if e == "reelwright.merge"]
    assert merges[0]["phase"] == "start" and merges[-1]["phase"] == "end" and all(d["job"] == "j1" for d in merges)
    assert merges[-1]["files"] == ok[1]["files"]


def test_merge_cancel_while_analysing(api, store, harbor, monkeypatch):
    run, routes, events = api
    p = small(harbor)
    _takes(store, p)
    real = routes.analyze

    def slow(*a, **k):
        time.sleep(1.0)
        return real(*a, **k)
    monkeypatch.setattr(routes, "analyze", slow)

    async def go(c):
        task = asyncio.ensure_future(post(c, "/reelwright/merge", {"project": p, "job": "j2"}))
        await asyncio.sleep(0.4)
        cancel = await post(c, "/reelwright/merge/cancel", {"job": "j2"})
        return cancel, await task
    cancel, res = run(go)
    assert cancel == (200, {"ok": True, "cancelled": True})
    assert res == (200, {"ok": False, "cancelled": True, "job": "j2"})
    left = sorted(os.listdir(store.cuts_dir())) if os.path.isdir(store.cuts_dir()) else []
    assert left in ([], [".next"])
    assert [d for e, d in events if e == "reelwright.merge"][-1].get("cancelled") is True


def test_rewrite_stop_during_analysis_is_not_lost(api, store, harbor, monkeypatch):
    run, routes, _ = api
    p = dict(harbor)
    p["global"]["llm"]["base_url"] = "http://127.0.0.1:9/v1"
    monkeypatch.setattr(routes, "analyze", lambda *a, **k: time.sleep(1.0))  # a None result would answer 500

    async def go(c):
        task = asyncio.ensure_future(post(c, "/reelwright/llm/rewrite", {"project": p, "scene_id": "s_one",
                                                                         "instruction": "x", "job": "jj"}))
        await asyncio.sleep(0.3)
        stop = await post(c, "/reelwright/llm/cancel", {"job": "jj"})
        return stop, await task
    stop, res = run(go)
    assert stop[1]["cancelled"] is True and res == (200, {"cancelled": True})


# ---- import, promote_frame, repair ----------------------------------------------------------------------------------

def test_import_tells_files_apart_by_content(api, roots):
    run, _, _ = api
    a = os.path.join(roots.output, "renders", "a", "take.wav")
    b = os.path.join(roots.output, "renders", "b", "take.wav")
    from reelwright import merge
    for path, freq in ((a, 440), (b, 880)):
        os.makedirs(os.path.dirname(path))
        subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "sine=f={}:d=1".format(freq), path], check=True)
    assert os.path.getsize(a) == os.path.getsize(b)

    async def go(c):
        return [await post(c, "/reelwright/import", {"slug": "film", "root": "output", "rel": rel})
                for rel in ("renders/a/take.wav", "renders/b/take.wav", "renders/a/take.wav")]
    res = run(go)
    files = [r[1]["asset"]["file"] for r in res]
    assert files == ["reelwright/film/from_output/take.wav", "reelwright/film/from_output/take_2.wav",
                     "reelwright/film/from_output/take.wav"]
    with open(os.path.join(roots.input, files[1]), "rb") as f, open(b, "rb") as g:
        assert f.read() == g.read()


def test_promote_frame_and_repair(api, store, roots):
    run, _, _ = api
    d = store.take_dir("s_one", "v1")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "first.png"), "wb") as f:
        f.write(png_bytes())
    ff_clip(os.path.join(d, "v.mp4"), 1)
    entry = {"id": "v1", "created": 5, "files": {"video": store.rel_output(os.path.join(d, "v.mp4")),
                                                 "first": store.rel_output(os.path.join(d, "first.png"))}}
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump(entry, f)
    with open(os.path.join(store.scene_dir("s_one"), "index.json"), "w") as f:
        f.write("{broken")

    async def go(c):
        return [await post(c, "/reelwright/storage/repair", {"slug": "harbor_lights"}),
                await post(c, "/reelwright/promote_frame", {"slug": "harbor_lights", "scene_id": "s_one",
                                                            "take_id": "v1", "which": "first"}),
                await post(c, "/reelwright/promote_frame", {"slug": "harbor_lights", "scene_id": "s_one",
                                                            "take_id": "v1", "which": "time", "t": "nan"})]
    repair, first, nan = run(go)
    assert repair[0] == 200 and repair[1]["repaired"] == ["s_one"] and repair[1]["takes_found"] == 1
    assert first[0] == 200 and first[1]["asset"]["file"].endswith("promoted_s_one_v1_first.png")
    assert nan[0] == 400


# ---- beats and the pass excerpt --------------------------------------------------------------------------------------

def test_beats_route(api, roots):
    run, _, _ = api
    import wave

    import numpy as np
    rate = 22050
    y = np.zeros(rate * 12, np.float32)
    for k in range(24):
        i = int((0.25 + k * 0.5) * rate)
        y[i:i + 400] = 0.5 * np.sin(np.arange(400) * 0.4)
    path = os.path.join(roots.input, "reelwright", "film", "clicks.wav")
    os.makedirs(os.path.dirname(path))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((y * 32767).astype(np.int16).tobytes())

    async def go(c):
        return [await get(c, "/reelwright/beats?file=reelwright/film/clicks.wav"),
                await get(c, "/reelwright/beats?file=reelwright/film/none.wav"),
                await get(c, "/reelwright/beats?file=../../etc/passwd")]
    ok, missing, outside = run(go)
    assert ok[0] == 200 and ok[1]["bpm"] == pytest.approx(120, rel=0.02) and len(ok[1]["beats"]) >= 20
    assert len(os.listdir(os.path.join(roots.user, "reelwright", "cache", "beats"))) == 1
    assert missing[0] == 400 and outside[0] == 400


def test_soundtrack_excerpt_route(api, store, roots, harbor):
    run, _, _ = api
    from reelwright import merge
    song = os.path.join(roots.input, "reelwright", "harbor_lights", "song.wav")
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=f=220:d=30", "-ac", "2", song], check=True)
    p = dict(harbor)
    p["assets"] = p["assets"] + [{"id": "a_song", "kind": "audio", "name": "song", "code": "A9",
                                  "file": "reelwright/harbor_lights/song.wav", "duration": 30.0}]
    p["soundtrack"] = [{"id": "t_1", "asset": "a_song", "start": 1.0, "in": 0.0}]
    store.autosave(p)

    async def go(c):
        return [await post(c, "/reelwright/soundtrack/excerpt", {"project": p, "scene_id": "s_one", "pass": 1}),
                await post(c, "/reelwright/soundtrack/excerpt", {"slug": "harbor_lights", "scene_id": "s_one", "pass": 1}),
                await post(c, "/reelwright/soundtrack/excerpt", {"project": p, "scene_id": "s_one", "pass": 4}),
                await post(c, "/reelwright/soundtrack/excerpt", {"project": dict(p, soundtrack=[]),
                                                                 "scene_id": "s_one", "pass": 1})]
    a, b, bad, none = run(go)
    assert a[0] == 200 and a[1]["file"].startswith("reelwright/harbor_lights/soundtrack/")
    assert a[1]["url"].startswith("/view?filename=") and "type=output" in a[1]["url"]
    assert a[1]["codes"] == ["A9"] and a[1]["length"] > 2 and b[1]["file"] == a[1]["file"]
    assert os.path.isfile(os.path.join(roots.output, a[1]["file"]))
    assert bad[0] == 400
    assert none == (200, {"url": None, "file": None, "reason": none[1]["reason"]})


def test_star_and_delete_wait_for_the_lock_off_the_event_loop(api, store):
    """Bug 6: /takes/star and /takes/delete took the project lock on the event loop; while a worker thread held it
    (an import hashing a big file, repair()) every request of the whole server waited."""
    import threading
    run, _, _ = api
    from reelwright import jobs
    store.add_take("s_one", {"id": "v1"})
    store.add_take("s_one", {"id": "v2"})
    held = threading.Event()

    def hold():
        with jobs.lock(store.slug):
            held.set()
            time.sleep(1.5)

    async def go(c):
        threading.Thread(target=hold).start()
        held.wait(5)
        star = asyncio.ensure_future(post(c, "/reelwright/takes/star", {"slug": "harbor_lights", "scene_id": "s_one",
                                                                         "take_id": "v1"}))
        delete = asyncio.ensure_future(post(c, "/reelwright/takes/delete", {"slug": "harbor_lights",
                                                                             "scene_id": "s_one", "take_id": "v2"}))
        await asyncio.sleep(0.1)
        t0 = time.time()
        other = await get(c, "/reelwright/versions?slug=harbor_lights")  # lock-free
        took = time.time() - t0
        return took, other, await star, await delete
    took, other, star, delete = run(go)
    assert other[0] == 200 and took < 1.0
    assert star == (200, {"ok": True}) and delete == (200, {"ok": True})
    idx = store.read_index("s_one")
    assert idx["starred"] == "v1" and [t["id"] for t in idx["takes"]] == ["v1"]


def test_import_copies_outside_the_project_lock(api, roots, monkeypatch):
    """Bug 6: _import_target hashed and copied under the project lock."""
    import threading
    run, routes, _ = api
    from reelwright import jobs
    src = os.path.join(roots.output, "renders", "a", "take.wav")
    os.makedirs(os.path.dirname(src))
    from reelwright import merge
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=d=1", src], check=True)
    free = []
    copy = routes.shutil.copyfile

    def no_link(a, b):
        raise OSError("no hard links here")

    def copyfile(a, b):
        def probe():  # take and give back the lock in another thread
            lk = jobs.lock("film")
            ok = lk.acquire(timeout=1)
            if ok:
                lk.release()
            free.append(ok)
        t = threading.Thread(target=probe)
        t.start()
        t.join()
        return copy(a, b)
    monkeypatch.setattr(routes.os, "link", no_link)
    monkeypatch.setattr(routes.shutil, "copyfile", copyfile)
    res = run(lambda c: post(c, "/reelwright/import", {"slug": "film", "root": "output", "rel": "renders/a/take.wav"}))
    assert res[0] == 200 and res[1]["asset"]["file"] == "reelwright/film/from_output/take.wav"
    assert free == [True]  # another thread could take the lock while the file was copied
    folder = os.path.join(roots.input, "reelwright", "film", "from_output")
    assert sorted(os.listdir(folder)) == ["take.wav"]  # no temporary file left


def test_bad_input_answers_400_not_500(api, harbor):
    """Bug 7: {"ids": 5} and known_cast [{"name": 5}] answered 500."""
    run, _, _ = api

    async def go(c):
        return [await post(c, "/reelwright/storage/delete", {"ids": 5}),
                await post(c, "/reelwright/storage/delete", {"ids": "p:film"}),
                await post(c, "/reelwright/llm/script", {"project": harbor, "script": "INT. HOUSE\nHello.",
                                                         "known_cast": [{"name": 5}]}),
                await post(c, "/reelwright/llm/script", {"project": harbor, "script": "INT. HOUSE\nHello.",
                                                         "known_cast": ["Mara"]}),
                await post(c, "/reelwright/llm/script/parts", {"script": ["a"]}),
                await post(c, "/reelwright/llm/script/parts", {"script": None})]
    out = run(go)
    for status, body in out[:-1]:
        assert status == 400 and body["error"], body
    assert out[-1][0] == 200 and out[-1][1]["parts"] == []


def test_a_script_part_past_the_parts_answers_400(api, harbor):
    """Part 5 of 3 was accepted."""
    run, _, _ = api
    harbor = dict(harbor, **{"global": dict(harbor["global"], llm=dict(harbor["global"]["llm"], base_url="http://127.0.0.1:9/v1"))})

    async def go(c):
        return await post(c, "/reelwright/llm/script", {"project": harbor, "script": "INT. HOUSE\nHello.", "part": 5,
                                                        "parts": 3})
    status, body = run(go)
    assert status == 400 and "part" in body["error"], body


def test_unreadable_input_answers_400_not_500(api, store, roots):
    """Review 11 and minor: an upload that is not multipart (an assert in aiohttp), an anchor sheet of a file that is
    not a picture (PIL's UnidentifiedImageError) and a frame grab from an unreadable take video (CalledProcessError)
    answered 500."""
    run, _, _ = api
    os.makedirs(store.input_dir, exist_ok=True)
    with open(os.path.join(store.input_dir, "fake.png"), "wb") as f:
        f.write(b"not a picture at all")
    d = store.take_dir("s_one", "v1")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "v.mp4"), "wb") as f:
        f.write(b"not a video either")
    store.add_take("s_one", {"id": "v1", "files": {"video": store.rel_output(os.path.join(d, "v.mp4"))}})

    async def go(c):
        out = [await post(c, "/reelwright/upload", {"slug": "harbor_lights"})]
        r = await c.post("/reelwright/upload", data=b"raw bytes")
        out.append((r.status, await r.json()))
        r = await c.get("/reelwright/sheet", params={"files": json.dumps(["reelwright/harbor_lights/fake.png"])})
        out.append((r.status, await r.json()))
        out.append(await post(c, "/reelwright/promote_frame", {"slug": "harbor_lights", "scene_id": "s_one",
                                                               "take_id": "v1", "which": "time", "t": 0.5}))
        return out
    for status, body in run(go):
        assert status == 400 and body["error"], (status, body)


def test_llm_requests_with_one_job_id_keep_their_own_entries(api):
    """Review 9: two requests with the same job id shared one LLM_JOBS entry; the first to end removed the other's,
    so Stop no longer reached the one still running."""
    run, routes, _ = api

    async def go(c):
        gates = [asyncio.Event(), asyncio.Event()]

        async def slow(ev):
            await ev.wait()
            return {"done": True}
        first = asyncio.ensure_future(routes._llm_job("jj", slow(gates[0])))
        await asyncio.sleep(0.05)
        second = asyncio.ensure_future(routes._llm_job("jj", slow(gates[1])))
        await asyncio.sleep(0.05)
        owner = routes.LLM_JOBS["jj"]
        gates[0].set()
        a = await first
        still = routes.LLM_JOBS.get("jj") is owner
        stop = await post(c, "/reelwright/llm/cancel", {"job": "jj"})
        try:
            b = await asyncio.wait_for(asyncio.shield(second), 5)
        except asyncio.TimeoutError:  # Stop missed it: let it end
            gates[1].set()
            b = await second
        return a, still, stop, b, dict(routes.LLM_JOBS), set(routes.LLM_CANCELLED)
    a, still, stop, b, left, marks = run(go)
    assert a == {"done": True} and still
    assert stop[1]["cancelled"] is True and b == {"cancelled": True}
    assert left == {} and marks == set()


# ---- the timeline filmstrip ------------------------------------------------------------------------------------------

def test_filmstrip_route(api, store, roots):
    run, _, _ = api
    d = store.take_dir("s_one", "v1")
    os.makedirs(d, exist_ok=True)
    video = ff_clip(os.path.join(d, "harbor_lights_01_harbor_v1.mp4"), 3.0)
    rel = store.rel_output(video)
    other = os.path.join(roots.output, "elsewhere.mp4")
    ff_clip(other, 1.0)
    with open(os.path.join(d, "notes.txt"), "w") as f:
        f.write("x")

    async def go(c):
        out = [await get(c, "/reelwright/filmstrip?file=" + rel),
               await get(c, "/reelwright/filmstrip?file={}&h=32".format(rel))]
        mtime = os.path.getmtime(os.path.join(roots.output, out[0][1]["file"]))
        out.append(await get(c, "/reelwright/filmstrip?file=" + rel))  # reused
        out.append(mtime == os.path.getmtime(os.path.join(roots.output, out[0][1]["file"])))
        for bad in ("elsewhere.mp4", "reelwright/../elsewhere.mp4", "reelwright/harbor_lights/../../elsewhere.mp4",
                    rel + "&h=8", rel + "&h=5.5", rel + "&h=x", rel.replace(".mp4", ".txt"),
                    "reelwright/harbor_lights/scenes/s_one/takes/v1/notes.txt", ""):
            out.append(await get(c, "/reelwright/filmstrip?file=" + bad))
        out.append(await get(c, "/reelwright/filmstrip?file=reelwright/harbor_lights/none.mp4"))
        return out
    out = run(go)
    (s1, a), (s2, b), (s3, again), same = out[:4]
    assert s1 == 200 and a["file"] == rel[:-4] + ".filmstrip_54.jpg" and a["tile_h"] == 54
    assert (a["interval"], a["count"], a["tile_w"]) == (0.25, 12, 96) and a["duration"] == pytest.approx(3.0)
    assert a["url"].startswith("/view?filename=harbor_lights_01_harbor_v1.filmstrip_54.jpg&subfolder=")
    assert os.path.isfile(os.path.join(roots.output, a["file"]))
    assert os.path.isfile(os.path.join(roots.output, rel[:-4] + ".filmstrip_54.json"))
    assert s2 == 200 and b["file"].endswith(".filmstrip_32.jpg") and (b["tile_w"], b["tile_h"]) == (56, 32)
    assert s3 == 200 and again == a and same
    for status, body in out[4:-1]:
        assert status == 400 and body["error"], body
    assert out[-1][0] == 404


# ---- Write prompts (/llm/passes) -----------------------------------------------------------------------------------

async def _stub_llm(handler):
    """An OpenAI-compatible stub on a free port, in the running loop: (base_url, runner)."""
    from aiohttp import web
    app = web.Application()
    app.router.add_post("/v1/chat/completions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return "http://127.0.0.1:{}/v1".format(site._server.sockets[0].getsockname()[1]), runner


def _pass_of(body):
    import re
    m = re.search(r"Write the prompt of pass (\d+) of", body["messages"][1]["content"])
    return int(m.group(1)) if m else 1


def _answer(k):
    return {"summary": "[reference generation] Pass {} of the walk.".format(k),
            "detailed_description": "[Shot 1] A wide shot of <Subject 1> in the rain. " + " ".join(["rain"] * 340),
            "overall_soundscape": "Rain.", "non_diegetic_music": "N/A"}


def test_llm_passes_route(api, harbor):
    run, routes, events = api
    from aiohttp import web
    seen, gate = [], []

    async def handler(request):
        body = await request.json()
        seen.append(_pass_of(body))
        if body["messages"][1]["content"].count("STOP-AT-3") and _pass_of(body) == 3:
            await asyncio.wait_for(gate[0].wait(), 5)
        return web.json_response({"model": "stub", "choices": [{"message": {"content": json.dumps(_answer(
            _pass_of(body)))}, "finish_reason": "stop"}]})

    async def go(c):
        gate.append(asyncio.Event())
        base, runner = await _stub_llm(handler)
        p = json.loads(json.dumps(harbor))
        p["global"]["llm"].update(base_url=base, retries=0)
        try:
            out = [await post(c, "/reelwright/llm/passes", {"project": p, "scene_id": "s_long", "passes": [3, 1],
                                                            "job": "wp"})]
            # Stop during the third pass: the answer holds the two passes written before it
            task = asyncio.ensure_future(post(c, "/reelwright/llm/passes", {
                "project": p, "scene_id": "s_long", "passes": None, "instruction": "STOP-AT-3", "job": "wp2"}))
            for _ in range(250):
                if seen.count(3) == 2:
                    break
                await asyncio.sleep(0.02)
            out.append(await post(c, "/reelwright/llm/cancel", {"job": "wp2"}))
            out.append(await task)
            gate[0].set()
            raw = json.loads(json.dumps(p))
            raw["scenes"][1]["prompt"].update(mode="raw", raw="@Mara walks.")
            for body in ({"project": p, "scene_id": "s_long", "passes": "2"},
                         {"project": p, "scene_id": "s_long", "passes": [0]},
                         {"project": p, "scene_id": "s_long", "passes": [7]},
                         {"project": p, "scene_id": "s_long", "passes": [1.5]},
                         {"project": p, "scene_id": "nope"},
                         {"project": raw, "scene_id": "s_long"},
                         {"project": p, "scene_id": "s_long", "instruction": 5}):
                out.append(await post(c, "/reelwright/llm/passes", body))
        finally:
            gate[0].set()
            await runner.cleanup()
        return out
    out = run(go)
    status, body = out[0]
    assert status == 200 and [x["index"] for x in body["passes"]] == [1, 3] and body["pass_count"] == 3
    assert body["scene_id"] == "s_long" and body["passes"][0]["start"] == 0.0 and body["passes"][0]["end"] == 14.375
    assert body["passes"][1]["sections"]["summary"] == "Pass 3 of the walk."
    assert body["passes"][1]["sections"]["detailed_description"].startswith("[Shot 1] A wide shot of @Mara in the rain.")
    assert body["warnings"] == ["Pass 1: the answer has 1 [Shot N] line for the pass's 2 shots; they are kept as written",
                                "Pass 3: the keyframe @P3 is not named, so it is only anchored, not sent as a picture"]
    assert "cancelled" not in body and "error" not in body
    llm_events = [d for e, d in events if e == "reelwright.llm" and d.get("job") == "wp"]
    assert llm_events and all(d["scene_id"] == "s_long" and d["passes"] == 3 for d in llm_events)
    assert [d["pass"] for d in llm_events if d["phase"] == "waiting"] == [1, 3]
    stop, stopped = out[1], out[2]
    assert stop == (200, {"ok": True, "cancelled": True})
    assert stopped[0] == 200 and stopped[1]["cancelled"] is True
    assert [x["index"] for x in stopped[1]["passes"]] == [1, 2]
    for status, body in out[3:]:
        assert status == 400 and body["error"], (status, body)
    assert "not in this scene" in out[5][1]["error"] and "raw text" in out[8][1]["error"]


# ---- speech timing and a voice cut from a take -----------------------------------------------------------------------

def speech_take(path, seconds, bursts):
    """An mp4 whose sound is syllable-like bursts (4 Hz, speech-band tones) at (start, end) over a quiet floor."""
    import wave
    np = pytest.importorskip("numpy")
    from reelwright import merge, speech
    rate = speech.RATE
    t = np.arange(int(seconds * rate)) / rate
    y = 0.003 * np.random.default_rng(3).standard_normal(len(t))
    for a, b in bursts:
        m = (t >= a) & (t < b)
        tt = t[m] - a
        y[m] += 0.08 * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * tt)) ** 2 * sum(np.sin(2 * np.pi * f * tt) for f in (500, 900, 1400, 2300))
    wav = path + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    subprocess.run([merge.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=64x64:r=24:d={}".format(seconds), "-i", wav, "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", path], check=True)
    os.remove(wav)
    return path


def test_speech_and_voice_from_take_routes(api, store, roots):
    run, _, _ = api
    d = store.take_dir("s_one", "v1")
    os.makedirs(d, exist_ok=True)
    video = speech_take(os.path.join(d, "harbor_lights_01_harbor_v1.mp4"), 8.0, [(1.5, 3.1), (4.4, 6.2)])
    rel = store.rel_output(video)
    store.add_take("s_one", {"id": "v1", "created": 5, "files": {"video": rel}})
    lines = [{"id": "d1", "t": 1.0, "duration": 1.5}, {"id": "d2", "t": 3.8, "duration": 1.6}]

    async def go(c):
        return [await post(c, "/reelwright/speech", {"file": rel, "lines": lines}),
                await post(c, "/reelwright/speech", {"file": "reelwright/harbor_lights/none.mp4", "lines": lines}),
                await post(c, "/reelwright/speech", {"file": "../elsewhere.mp4", "lines": lines}),
                await post(c, "/reelwright/speech", {"file": rel, "lines": "d1"}),
                await post(c, "/reelwright/voice_from_take", {"slug": "harbor_lights", "scene_id": "s_one", "take_id": "v1",
                                                              "cast_id": "c_mara", "lines": lines}),
                await post(c, "/reelwright/voice_from_take", {"slug": "harbor_lights", "scene_id": "s_one", "take_id": "v1",
                                                              "cast_id": "c_mara", "lines": [{"id": "d1", "t": 7.5, "duration": 0.3}]}),
                await post(c, "/reelwright/voice_from_take", {"slug": "harbor_lights", "scene_id": "s_one", "take_id": "v9",
                                                              "cast_id": "c_mara", "lines": lines})]
    (s1, timed), (s2, _), (s3, _), (s4, _), (s5, voice), (s6, short), (s7, _) = run(go)
    assert s1 == 200 and [round(x["t"], 1) for x in timed["lines"]] == [1.5, 4.4] and all(x["matched"] for x in timed["lines"])
    assert len(timed["segments"]) == 2
    assert s2 == 404 and s3 == 400 and s4 == 400
    assert s5 == 200 and voice["used"] == ["d1", "d2"] and 2.0 <= voice["seconds"] <= 15.0
    a = voice["asset"]
    assert a["kind"] == "audio" and a["category"] == "voice" and a["file"] == "reelwright/harbor_lights/voice_c_mara_s_one_v1.wav"
    assert os.path.isfile(os.path.join(roots.input, a["file"]))
    assert s6 == 400 and "at least 2" in short["error"]
    assert s7 == 400


# Chat tab route: checks the conversation, answers with the reply, Stop cancels it
def test_llm_chat_route(api, monkeypatch):
    run, routes, events = api
    seen = []

    async def fake_turn(cfg, msgs, progress=None):
        seen.append(msgs)
        progress({"phase": "writing", "tokens": 2, "text": "ok"})
        await asyncio.sleep(0.4)
        return {"reply": "ok:" + msgs[-1]["content"], "ms": 400, "model": "m", "tokens": 2, "reasoning": False}
    monkeypatch.setattr(routes.llm, "chat_turn", fake_turn)
    monkeypatch.setattr(routes, "_cfg", lambda p: {"base_url": "http://x", "model": "m"})
    max_chars = routes.llm.CHAT_MAX_CHARS

    async def go(c):
        out = []
        for body in ({}, {"messages": []}, {"messages": [{"role": "system", "content": "x"}]},
                     {"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]},
                     {"messages": [{"role": "user", "content": "  "}]}, {"messages": [{"role": "user", "content": 5}]},
                     {"messages": [{"role": "user", "content": "x" * (max_chars + 1)}]}):
            out.append(await post(c, "/reelwright/llm/chat", body))
        out.append(await post(c, "/reelwright/llm/chat", {"messages": [{"role": "user", "content": "hi"}], "job": "chat-1",
                                                          "extra": 1}))
        task = asyncio.ensure_future(post(c, "/reelwright/llm/chat", {"messages": [{"role": "user", "content": "slow"}],
                                                                       "job": "chat-2"}))
        await asyncio.sleep(0.15)
        cancel = await post(c, "/reelwright/llm/cancel", {"job": "chat-2"})
        out.append(cancel)
        out.append(await task)
        return out
    res = run(go)
    assert all(status == 400 and data.get("error") for status, data in res[:7]), res[:7]
    assert res[7] == (200, {"reply": "ok:hi", "ms": 400, "model": "m", "tokens": 2, "reasoning": False})
    assert res[8][1]["cancelled"] is True and res[9] == (200, {"cancelled": True})
    assert seen[0] == [{"role": "user", "content": "hi"}]
    assert ("reelwright.llm", {"phase": "writing", "tokens": 2, "text": "ok", "job": "chat-1"}) in events


# ---- a frame of a video anchor as a picture ------------------------------------------------------------------------

def test_anchor_frame_route(api, store, roots):
    run, _, _ = api
    d = os.path.join(roots.input, "reelwright", "harbor_lights")
    os.makedirs(d, exist_ok=True)
    ff_clip(os.path.join(d, "clip.mp4"), 2)
    body = {"slug": "harbor_lights", "file": "reelwright/harbor_lights/clip.mp4", "cast_id": "c_mara", "anchor_id": "va_1"}

    async def go(c):
        return [await post(c, "/reelwright/anchor_frame", dict(body, t=1.01)),
                await post(c, "/reelwright/anchor_frame", dict(body, t=9)),             # past the end
                await post(c, "/reelwright/anchor_frame", dict(body, file="../../etc/passwd", t=0)),
                await post(c, "/reelwright/anchor_frame", dict(body, file="reelwright/harbor_lights/none.mp4", t=0)),
                await post(c, "/reelwright/anchor_frame", dict(body, anchor_id="../x", t=0)),
                await post(c, "/reelwright/anchor_frame", dict(body, t="nan"))]
    ok, past, outside, missing, bad_id, nan = run(go)
    assert ok[0] == 200, ok
    a = ok[1]["asset"]
    assert a["file"] == "reelwright/harbor_lights/frame_c_mara_va_1_24f.png" and ok[1]["t"] == 1.0
    assert (a["kind"], a["width"], a["height"], a["category"]) == ("image", 160, 90, "subject")
    assert os.path.isfile(os.path.join(roots.input, a["file"]))
    assert past[0] == 400 and "could not take a frame" in past[1]["error"]
    assert outside[0] == 400 and missing[0] == 400 and bad_id[0] == 400 and nan[0] == 400
