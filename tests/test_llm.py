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
    # v0.6.0: the answer comes back in the editor's shapes (coerce_script)
    assert first["scenes"] == [{"title": "One", "cast": [], "shots": [], "dialogue": []}] and first["attempts"] == 1
    assert first["cast"] == [{"name": "Bren", "kind": "character", "description": "", "speaker": "", "language": ""}]
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


# ---- added 2026-11-03 v0.6.0 --------------------------------------------------------------------------------------

def test_reply_with_only_a_closing_think_tag():
    # Qwen3-style templates open <think> in the prompt, so the reply carries only "</think>"
    assert llm.read_reply(reply("Let me see.\nOK.</think>\n\nA red coat."), 100) == ("A red coat.", "Let me see.\nOK.", "stop")
    assert llm._split_reasoning("plan</think>answer <think>more</think>end", "") == ("answer end", "planmore")

    async def handler(request):
        return await stream_response(request, sse(("Hmm, the coat", ""), (" is red.</think>", ""), ("A red coat.", "")))
    text, _, _ = run_app(lambda cfg: llm.chat(cfg, "s", "u"), handler)
    assert text == "A red coat."


def test_raw_rewrite_cut_off_is_retried_with_a_bigger_budget(harbor):
    from reelwright.model import normalize_project
    p = normalize_project(harbor)
    scene = p["scenes"][0]
    scene["prompt"].update(mode="raw", raw="@Mara walks.")
    seen = []

    async def handler(request):
        seen.append(await request.json())
        if len(seen) == 1:
            return await stream_response(request, sse(("@Mara walks along the pier and", ""), finish="length"))
        return await stream_response(request, sse(("@Mara walks along the pier.", "")))
    out = run_app(lambda cfg: llm.rewrite(cfg, p, scene, ""), handler, retries=2)
    assert out["raw"] == "@Mara walks along the pier." and [b["max_tokens"] for b in seen] == [2048, 4096]

    async def always_cut(request):
        seen.append(await request.json())
        return await stream_response(request, sse(("@Mara walks", ""), finish="length"))

    async def go(cfg):
        with pytest.raises(llm.LLMError) as e:
            await llm.rewrite(cfg, p, scene, "")
        return e.value
    seen.clear()
    err = run_app(go, always_cut, retries=1, max_tokens=20000)
    assert err.reason == "cut" and "cut off at 32,768 tokens" in str(err) and "tried 2 times" in str(err)
    assert [b["max_tokens"] for b in seen] == [20000, 32768]
    seen.clear()
    err = run_app(go, always_cut, retries=3, max_tokens=32768)   # already at the cap: not asked again
    assert len(seen) == 1 and "already had 32,768 tokens" in str(err)


def test_rate_limit_is_retried_after_the_wait_the_server_asks():
    calls = []

    async def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return web.json_response({"error": {"message": "rate limit"}}, status=429, headers={"Retry-After": "0"})
        return await stream_response(request, sse(("ok", "")))
    assert run_app(lambda cfg: llm.ask(cfg, "s", "u"), handler, retries=2) == "ok" and len(calls) == 2

    async def busy(request):
        calls.append(1)
        return web.json_response({"error": "slow down"}, status=429, headers={"Retry-After": "600"})

    async def go(cfg):
        with pytest.raises(llm.LLMError) as e:
            await llm.ask(cfg, "s", "u")
        return e.value
    calls.clear()
    err = run_app(go, busy, retries=3)
    assert len(calls) == 1 and err.reason == "busy" and "wait 600 s" in str(err)
    assert llm.retry_after("2.5") == 2.5 and llm.retry_after("nope") is None and llm.retry_after("") is None


def test_context_errors_are_not_retried_and_explain_themselves():
    calls = []

    async def in_stream(request):
        calls.append(1)
        r = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await r.prepare(request)
        await r.write(b'data: {"error": {"message": "This model\'s maximum context length is 8192 tokens"}}\n\n')
        await r.write_eof()
        return r

    async def go(cfg):
        with pytest.raises(llm.LLMError) as e:
            await llm.ask(cfg, "s", "u")
        return e.value
    err = run_app(go, in_stream, retries=3)
    assert len(calls) == 1 and err.reason == "context" and "context window" in str(err) and "Script part size" in str(err)

    async def as_500(request):
        calls.append(1)
        return web.json_response({"error": {"message": "prompt is too long for the model"}}, status=500)
    calls.clear()
    err = run_app(go, as_500, retries=3)
    assert len(calls) == 1 and err.reason == "context"


def test_base_url_and_web_page_answers():
    assert llm.normalize_base_url("localhost:8000/v1/") == "http://localhost:8000/v1"
    assert llm.normalize_base_url(" https://x.org/v1/chat/completions ") == "https://x.org/v1"
    assert llm.normalize_base_url("") == ""
    with pytest.raises(ValueError):
        llm.normalize_base_url("ftp://x.org")
    cfg = llm.resolve({"base_url": "192.168.1.5:30000/v1"}, {"base_url": "", "model": "", "api_key": ""})
    assert cfg["base_url"] == "http://192.168.1.5:30000/v1"

    async def page(request):
        return web.Response(text="<!DOCTYPE html><html><body>Open WebUI</body></html>", content_type="text/html")

    async def go(cfg):
        with pytest.raises(llm.LLMError) as e:
            await llm.ask(cfg, "s", "u")
        return e.value
    err = run_app(go, page, retries=2)
    assert err.reason == "html" and "web page, not JSON" in str(err) and "/v1" in str(err)

    async def page_404(request):
        return web.Response(text="<html><body>404 Not Found</body></html>", status=404, content_type="text/html")
    err = run_app(go, page_404, retries=2)
    assert err.reason == "html" and str(err).startswith("HTTP 404: the server sent a web page")


def test_tolerant_json():
    assert llm.parse_json('Here it is:\n```json\n{"a": [1, 2,],}\n```\nDone.') == {"a": [1, 2]}
    assert llm.parse_json('{"a": "x"} and then some words with a } brace') == {"a": "x"}
    assert llm.parse_json("{'a': 'x', 'b': None, 'c': True}") == {"a": "x", "b": None, "c": True}
    assert llm.parse_json('[{"title": "One"}]') == [{"title": "One"}]
    with pytest.raises(ValueError):
        llm.parse_json("no json here")


def test_bracketed_number_in_a_preface_is_not_the_answer():
    """Bug 3 (v0.6.0 review): the first value from the first { or [ won, so "passes [1, 2]:" became the answer and
    Split turned [1, 2] into the pass prompts "1" and "2"."""
    answer = {"1": "summary:\nA wide shot", "2": "summary:\nThe rain"}
    for pre in ("Here are the prompts for passes [1, 2]:\n", "Rewritten per pass [2]:\n", "Note [1]: it continues.\n"):
        text = pre + json.dumps(answer)
        assert llm.parse_json(text, dict) == answer
        assert llm.parse_json(text) == answer  # a value with more JSON after it is skipped
        assert llm.split_prompts(llm.json_answer(text, {}, "split", dict), 2) == answer
    # the expected type wins over JSON after it; the objects inside a value are not values of their own
    assert llm.parse_json('{"a": {"b": 1},} see [3]', dict) == {"a": {"b": 1}}
    assert llm.parse_json("{'a': [1, 2], 'b': None}", dict) == {"a": [1, 2], "b": None}
    # no object at all: the last value (a bare list of scenes)
    assert llm.parse_json('Scenes [2]:\n[{"title": "One"}]', dict) == [{"title": "One"}]
    assert llm.parse_json('```json\n[1]\n```\n{"a": 1}', dict) == {"a": 1}  # the fence has no object


def test_script_answer_is_coerced():
    data = {"scenes": [
        {"title": ["Dawn", "at sea"], "duration": "12 s", "summary": {"what": "a boat", "mood": "calm"},
         "cast": "Mara", "music": 5,
         "shots": [{"t": "0:02", "duration": "abc", "camera": None, "text": ["Wide.", "Waves."]}, "A close-up of Mara.", 7],
         "dialogue": ["MARA: Hello there.", {"speaker": {"name": "Finn"}, "t": "x", "text": "Hi."}, {"text": ""}]},
        "not a scene"], "cast": ["Mara", {"name": "Pier", "kind": "place"}, {"kind": "prop"}, 5]}
    scenes, cast, warnings = llm.coerce_script(data)
    s = scenes[0]
    assert s["title"] == "Dawn\nat sea" and s["duration"] == 12.0 and s["summary"] == "what: a boat\nmood: calm"
    assert s["cast"] == ["Mara"] and s["music"] == "5"
    assert s["shots"] == [{"camera": "", "text": "Wide.\nWaves.", "t": 2.0}, {"camera": "", "text": "A close-up of Mara."}]
    assert s["dialogue"] == [{"speaker": "MARA", "text": "Hello there.", "language": "", "delivery": ""},
                             {"speaker": "Finn", "text": "Hi.", "language": "", "delivery": ""}]
    assert len(scenes) == 1
    assert [c["name"] for c in cast] == ["Mara", "Pier"] and cast[1]["kind"] == "character"
    for bit in ("Scene 2: not an object", "shot 1: duration 'abc'", "shot 3: not an object", "line 2: time 'x'",
                "line 3: no words", "Cast 3: no name", "kind 'place'"):
        assert any(bit in w for w in warnings), bit
    from reelwright.scriptparts import fit_scene
    assert fit_scene(s) == "" and s["duration"] == 12.0   # nothing in it can break the fit any more


def test_split_answer_keys_and_values():
    data = {"pass 1": {"summary": "@Mara walks.", "detailed_description": ["[Shot 1] Wide.", "[Shot 2] Close."]},
            "02": "plain text", "Pass_3": {"prompt": "third"}, "4": "too many", "notes": "ignored", "P0": "zero"}
    out = llm.split_prompts(data, 3)
    assert set(out) == {"1", "2", "3"} and out["2"] == "plain text" and out["3"] == "third"
    assert out["1"].startswith("subject_definitions:\nN/A\n\nsummary:\n@Mara walks.\n\nretention_analysis:\nN/A")
    assert "detailed_description:\n[Shot 1] Wide.\n[Shot 2] Close." in out["1"] and "{" not in out["1"]
    assert llm.split_prompts({"passes": ["one", {"pass": 3, "prompt": "three"}]}, 3) == {"1": "one", "3": "three"}
    with pytest.raises(llm.LLMError):
        llm.split_prompts("text", 2)


def test_tags_in_warnings_and_scene_context_follow_the_editor_rule(harbor):
    w = llm.preserved_warnings("@Mara writes to bob@example.com", "Mara writes to bob@example.com @P9")
    assert w == ["Dropped references: @Mara", "New references the scene does not have: @P9"]
    from reelwright.model import normalize_project
    p = normalize_project(harbor)
    p["cast"][0]["name"] = "O'Brien"
    p["cast"].append(dict(p["cast"][0], id="c_k", name="Old Keeper"))
    p["scenes"][0]["cast"] = [{"id": "c_mara", "outfit": ""}, {"id": "c_k", "outfit": ""}]
    ctx = llm.scene_context(p, p["scenes"][0])
    assert "@O'Brien - " in ctx and "@{Old Keeper} - " in ctx


def test_script_part_skips_known_cast_without_a_text_name(harbor, monkeypatch):
    """Bug 7 (v0.6.0 review): known_cast [{"name": 5}] raised AttributeError (the route answered 500)."""
    seen = {}

    async def fake_ask(cfg, system, user, parse=None, **kw):
        seen["user"] = user
        return parse('{"scenes": [], "cast": []}', {})
    monkeypatch.setattr(llm, "ask", fake_ask)
    cfg = llm.resolve({"base_url": "http://127.0.0.1:9/v1"}, {"base_url": "", "model": "", "api_key": ""})
    out = asyncio.run(llm.script_part(cfg, harbor, "INT. HOUSE\nHello.",
                                      known_cast=[{"name": 5}, {"name": "Finn"}, {"name": ""}, "Ola"]))
    assert isinstance(out, dict)
    assert "Finn (character)" in seen["user"] and "5 (" not in seen["user"]
