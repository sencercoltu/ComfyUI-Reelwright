"""LLM client against a stub OpenAI-compatible server (added 2026-11-02 v0.3.2).

Thinking models put their reasoning in `reasoning_content` and leave `content` empty when the token
budget runs out; that used to surface as "The model returned no text. Is it a vision model?".
"""

import asyncio
import json

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web  # noqa: E402

from reelwright import llm  # noqa: E402


def reply(content, reasoning=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if reasoning is not None:
        msg["reasoning_content"] = reasoning
    return {"model": "stub", "choices": [{"message": msg, "finish_reason": finish}]}


def run_with_server(handler, coro_fn):
    async def main():
        app = web.Application()
        app.router.add_post("/v1/chat/completions", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        cfg = {"base_url": "http://127.0.0.1:{}/v1".format(port), "model": "stub", "api_key": "", "temperature": 0.4,
               "max_tokens": 2048, "thinking": "auto", "preset": "h3_ref2va", "include_guides": False}
        try:
            return await coro_fn(cfg)
        finally:
            await runner.cleanup()
    return asyncio.run(main())


IMG = [(b"\xff\xd8fake", "image/jpeg")]


def test_read_reply_variants():
    assert llm.read_reply(reply("A red coat."), 100) == ("A red coat.", "", "stop")
    assert llm.read_reply(reply("<think>hmm</think>A red coat."), 100) == ("A red coat.", "hmm", "stop")
    # no reasoning parser on the server and cut off while thinking
    assert llm.read_reply(reply("<think>still going", finish="length"), 100) == ("", "still going", "length")
    # vLLM / Ollama style field
    d = {"choices": [{"message": {"content": None, "reasoning": "x"}, "finish_reason": "length"}]}
    assert llm.read_reply(d, 100) == ("", "x", "length")


def test_describe_thinking_budget_then_retry_without_thinking():
    seen = []

    async def handler(request):
        body = await request.json()
        seen.append(body)
        if body.get("chat_template_kwargs", {}).get("enable_thinking") is False:
            return web.json_response(reply("the woman in a navy pea coat"))
        return web.json_response(reply(None, reasoning="Let me look at the coat... " * 50, finish="length"))

    out = run_with_server(handler, lambda cfg: llm.describe(cfg, IMG, "Describe her."))
    assert out["text"] == "the woman in a navy pea coat"
    assert "thinking off" in out["note"]
    assert seen[0]["max_tokens"] >= 6000 and "chat_template_kwargs" not in seen[0]
    assert seen[1]["chat_template_kwargs"] == {"enable_thinking": False} and seen[1]["max_tokens"] == 600


def test_describe_thinking_off_sends_switch_and_explains_cutoff():
    async def handler(request):
        body = await request.json()
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        return web.json_response(reply("", reasoning="", finish="length"))

    async def go(cfg):
        cfg["thinking"] = "off"
        with pytest.raises(llm.NoAnswer) as e:
            await llm.describe(cfg, IMG, "")
        return str(e.value)
    msg = run_with_server(handler, go)
    assert "cut off at 600 tokens" in msg


def test_describe_empty_answer_still_hints_vision():
    async def handler(request):
        return web.json_response(reply(""))

    async def go(cfg):
        with pytest.raises(RuntimeError) as e:
            await llm.describe(cfg, IMG, "")
        return str(e.value)
    assert "vision model" in run_with_server(handler, go)


def test_chat_explains_thinking_cutoff():
    async def handler(request):
        return web.json_response(reply(None, reasoning="thinking...", finish="length"))

    async def go(cfg):
        with pytest.raises(llm.NoAnswer) as e:
            await llm.chat(cfg, "sys", "user", max_tokens=6000)
        return e.value
    err = run_with_server(handler, go)
    assert err.reason == "thinking_cut" and "6000 tokens thinking" in str(err)


def test_connection_test_reports_thinking_model():
    async def handler(request):
        return web.json_response(reply(None, reasoning="The user wants", finish="length"))

    out = run_with_server(handler, llm.test)
    assert out["ok"] and out["thinking"] and out["reply"] == "" and "Thinking" in out["note"]
    assert json.dumps(out)


# added 2026-11-03 v0.4.1: the rewrite proposal no longer repeats what the editor writes automatically
def test_rewrite_is_tidied(harbor):
    from reelwright.model import normalize_project
    p = normalize_project(harbor)
    scene = p["scenes"][1]
    scene["prompt"]["auto"] = {"subjects": True, "retention": False, "shots": True}

    async def handler(request):
        whole = ("subject_definitions:\n<Subject 1> is Mara.\n\nsummary:\n[reference generation] <Subject 1> walks home.\n\n"
                 "retention_analysis:\n<Subject 1> (appears in [Shot 1]): fully_preserved - face.\n\n"
                 "detailed_description:\nLive-action, rain.\n[Shot 1] <Subject 1> walks.\n\noverall_soundscape:\nRain.\n\n"
                 "non_diegetic_music:\nN/A")
        return web.json_response(reply(json.dumps({"detailed_description": whole})))

    out = run_with_server(handler, lambda cfg: llm.rewrite(cfg, p, scene, "", "", {"@Mara": "<Subject 1>", "@P1": "<Picture 1>"}))
    sec = out["sections"]
    assert sec["subject_definitions"] == scene["prompt"]["sections"]["subject_definitions"]   # auto: kept as it was
    assert sec["summary"] == "[reference generation] @Mara walks home."
    assert sec["retention_analysis"] == "@Mara (appears in [Shot 1]): fully_preserved - face."
    assert sec["detailed_description"] == "Live-action, rain." and sec["overall_soundscape"] == "Rain."


# ---- v0.4.2: streaming, limits, retries, script parts (added 2026-11-03 v0.4.2) -------------------------------

def sse(*chunks, finish="stop", model="stub"):
    """An OpenAI-style event stream: each chunk is (content, reasoning)."""
    out = []
    for content, reasoning in chunks:
        delta = {}
        if content:
            delta["content"] = content
        if reasoning:
            delta["reasoning_content"] = reasoning
        out.append({"model": model, "choices": [{"delta": delta, "finish_reason": None}]})
    out.append({"model": model, "choices": [{"delta": {}, "finish_reason": finish}]})
    return "".join("data: {}\n\n".format(json.dumps(c)) for c in out) + "data: [DONE]\n\n"


async def stream_response(request, text, delay=0.0):
    r = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    await r.prepare(request)
    for block in text.split("\n\n"):
        if block:
            await r.write((block + "\n\n").encode())
            if delay:
                await asyncio.sleep(delay)
    await r.write_eof()
    return r


def run_app(coro_fn, chat_handler, models=None, **cfg):
    async def main():
        app = web.Application()
        app.router.add_post("/v1/chat/completions", chat_handler)
        if models is not None:
            async def list_models(request):
                return web.json_response(models)
            app.router.add_get("/v1/models", list_models)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        c = {"base_url": "http://127.0.0.1:{}/v1".format(port), "model": "stub", "api_key": "", "temperature": 0.4,
             "max_tokens": 2048, "thinking": "auto", "preset": "h3_ref2va", "include_guides": False,
             "timeout_s": 5, "max_wait_s": 30, "retries": 0, "retry_wait": 0, "context_tokens": 0,
             "import_part_chars": 3000, "import_max_tokens": 16384, "import_thinking": "same", "import_guides": False}
        c.update(cfg)
        llm._SERVER_CONTEXT.clear()
        try:
            return await coro_fn(c)
        finally:
            await runner.cleanup()
    return asyncio.run(main())


def test_limits_are_clamped():
    got = llm.limits({"timeout_s": 2, "max_wait_s": 5, "retries": 9, "context_tokens": 500, "import_part_chars": 100,
                      "import_max_tokens": "x", "import_thinking": "off", "import_guides": 1})
    assert got == {"timeout_s": 10, "max_wait_s": 30, "retries": 5, "context_tokens": 0, "import_part_chars": 0,
                   "import_max_tokens": 16384, "import_thinking": "off", "import_guides": True}
    assert llm.limits({})["max_wait_s"] == 900 and llm.limits({"timeout_s": 600, "max_wait_s": 60})["max_wait_s"] == 600


def test_streamed_answer_with_reasoning_and_progress():
    seen, events = [], []

    async def handler(request):
        seen.append(await request.json())
        return await stream_response(request, sse(("", "Let me "), ("", "think."), ("<b>Hel", ""), ("lo</b>", "")))

    async def go(cfg):
        info = {}
        out = await llm.chat(cfg, "sys", "user", info=info, progress=events.append)
        return out, info
    (text, ms, model), info = run_app(go, handler)
    assert text == "<b>Hello</b>" and model == "stub"
    assert seen[0]["stream"] is True and seen[0]["max_tokens"] == 2048
    assert info["finish"] == "stop" and info["tokens"] == 2 and info["reasoning_chars"] == len("Let me think.")
    assert events[0]["phase"] == "waiting" and events[-1]["phase"] == "done" and events[-1]["tokens"] == 2


def test_stall_timeout_names_the_setting():
    async def handler(request):
        await asyncio.sleep(3)
        return web.json_response(reply("late"))

    async def go(cfg):
        with pytest.raises(llm.LLMError) as e:
            await llm.chat(cfg, "sys", "user")
        return e.value
    err = run_app(go, handler, timeout_s=1)
    assert err.reason == "stall" and "for 1 s" in str(err) and "Stall timeout" in str(err)


def test_slow_stream_keeps_going_until_give_up():
    async def handler(request):
        return await stream_response(request, sse(*[("x", "")] * 40), delay=0.1)

    async def go(cfg):
        with pytest.raises(llm.LLMError) as e:
            await llm.chat(cfg, "sys", "user")
        return e.value
    # every gap is far below the 1 s stall timeout, but the whole answer takes longer than 2 s
    err = run_app(go, handler, timeout_s=1, max_wait_s=2)
    assert err.reason == "gave_up" and "Give up after" in str(err) and "tokens received" in str(err)


def test_retries_after_a_server_error_and_reports_it():
    calls, events = [], []

    async def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return web.json_response({"error": {"message": "overloaded"}}, status=503)
        return await stream_response(request, sse(('{"1": "pass one"}', "")))

    out = run_app(lambda cfg: llm.ask(cfg, "s", "u", parse=llm.json_answer, progress=events.append), handler, retries=2)
    assert out == {"1": "pass one"} and len(calls) == 2
    assert any(e["phase"] == "retry" and "overloaded" in e["note"] and e["attempt"] == 2 for e in events)


def test_client_error_is_not_retried():
    calls = []

    async def handler(request):
        calls.append(1)
        return web.json_response({"error": {"message": "model 'nope' not found"}}, status=404)

    async def go(cfg):
        with pytest.raises(llm.LLMError) as e:
            await llm.ask(cfg, "s", "u")
        return e.value
    err = run_app(go, handler, retries=3)
    assert len(calls) == 1 and err.reason == "http" and "not found" in str(err)


def test_context_window_from_the_server_caps_the_budget_and_refuses_too_big():
    seen = []

    async def handler(request):
        seen.append(await request.json())
        return await stream_response(request, sse(("ok", "")))

    models = {"data": [{"id": "other", "max_model_len": 99}, {"id": "stub", "max_model_len": 8192}]}
    run_app(lambda cfg: llm.chat(cfg, "s" * 3500, "u", max_tokens=16384), handler, models=models)
    assert seen[0]["max_tokens"] == 8192 - 1000 - 1 - 1 - 16 - 64   # context - prompt estimate - margin

    async def go(cfg):
        with pytest.raises(llm.LLMError) as e:
            await llm.chat(cfg, "s" * 35000, "u", max_tokens=16384)
        return e.value
    err = run_app(go, handler, models=models)
    assert err.reason == "context" and "8,192" in str(err) and len(seen) == 1   # refused before sending
    # a context window set by hand wins over the server's
    run_app(lambda cfg: llm.chat(cfg, "s", "u", max_tokens=16384), handler, models=models, context_tokens=4096)
    assert seen[-1]["max_tokens"] < 4096


def test_script_part_prompt_settings_and_cut_answer():
    from reelwright.model import default_project
    p = default_project("Demo")
    p["cast"] = [{"id": "c_1", "name": "Ada", "kind": "character"}]
    seen = []

    async def handler(request):
        seen.append(await request.json())
        if len(seen) == 1:
            return await stream_response(request, sse(('{"scenes": [{"title": "One"}], "cast": [{"name": "Bren"}]}', "")))
        return await stream_response(request, sse(('{"scenes": [{"title": "Two"', ""), finish="length"))

    async def go(cfg):
        first = await llm.script_part(cfg, p, "| 01 | crypt |", part=1, parts=2, notes="A song video.",
                                      known_cast=[{"name": "Valindra"}, {"name": "ada"}])
        with pytest.raises(llm.LLMError) as e:
            await llm.script_part(cfg, p, "| 02 | hall |", part=2, parts=2, retry_cut=False)
        return first, e.value
    first, err = run_app(go, handler, retries=2, import_thinking="off", import_max_tokens=12000, include_guides=True)
    assert first["scenes"] == [{"title": "One"}] and first["cast"] == [{"name": "Bren"}] and first["attempts"] == 1
    user = seen[0]["messages"][1]["content"]
    assert "part 1 of 2" in user and "A song video." in user and "Script part:\n| 01 | crypt |" in user
    assert "Ada (character), Valindra (character)" in user and user.count("Ada") == 1
    assert seen[0]["max_tokens"] == 12000 and seen[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "Official MiniMax" not in seen[0]["messages"][0]["content"] and "Ref2VA output format" not in seen[0]["messages"][0]["content"]
    assert err.reason == "cut" and "cut off at 12,000 tokens" in str(err) and len(seen) == 2   # a cut part is not retried


def test_script_part_asks_for_shot_durations_and_fits_the_scene():  # added 2026-11-03 v0.4.3
    from reelwright.model import default_project
    seen = []
    answer = {"scenes": [{"title": "Chorus", "duration": 30, "shots": [{"t": 0, "duration": 13}, {"t": 13, "duration": 12.96},
                                                                       {"t": 25.96, "duration": 12.08}]}], "cast": []}

    async def handler(request):
        seen.append(await request.json())
        return await stream_response(request, sse((json.dumps(answer), "")))

    out = run_app(lambda cfg: llm.script_part(cfg, default_project("Demo"), "| 01 | x |"), handler)
    scene = out["scenes"][0]
    assert "\"duration\": seconds, \"camera\"" in seen[0]["messages"][1]["content"]
    assert "sum of all its shot durations" in seen[0]["messages"][1]["content"]
    assert scene["duration"] == 38.0417 and scene["fit_note"].startswith("length set from its shots (38.04 s")
