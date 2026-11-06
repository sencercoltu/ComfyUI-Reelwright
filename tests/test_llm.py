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
    # v0.8.0: the import's default budget is 24576 (was 16384), for the longer shots
    assert got == {"timeout_s": 10, "max_wait_s": 30, "retries": 5, "context_tokens": 0, "import_part_chars": 0,
                   "import_max_tokens": 24576, "import_thinking": "off", "import_guides": True}
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
    # [OLD 2026-11-06 v0.9.0->v0.10.0] assert first["cast"] == [{"name": "Bren", "kind": "character", "description": "", "speaker": "", "language": ""}]
    assert first["cast"] == [{"name": "Bren", "kind": "character", "description": "", "speaker": "", "language": "",
                              "voice_desc": ""}]  # added 2026-11-06 v0.10.0: voice_desc
    user = seen[0]["messages"][1]["content"]
    assert 'Give every character who speaks (a narrator or an off-screen voice too) a "voice"' in user  # v0.10.0
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


# ---- added 2026-11-05 v0.8.0: Write prompts (one request per pass) and the longer import ---------------------------

def long_scene(harbor):
    """The harbor's 32 s continuing scene with a second shot in pass 2, normalised. Three passes split at shot cuts:
    0-14.375 (shots at 0 and 6), 14.375-22 (shots at 14.375 and 18, "Almost home." at 16), 22-32."""
    from reelwright.model import normalize_project
    harbor["scenes"][1]["shots"].append({"t": 18.0, "camera": "Close", "text": "rain runs down her face"})
    p = normalize_project(harbor)
    return p, p["scenes"][1]


def asked_pass(body):
    import re
    m = re.search(r"Write the prompt of pass (\d+) of", body["messages"][1]["content"])
    return int(m.group(1)) if m else 1


def filler(n):
    return " ".join(["rain"] * n)


PASS_ANSWERS = {
    1: {"subject_definitions": "<Subject 1> is Mara.",
        "summary": "[reference generation] <Subject 1> leaves the pier (pass one).",
        "retention_analysis": "<Subject 1>: fully_preserved - identity.",
        "detailed_description": "Live-action, dusk light.\n[Shot1] At 00:00.000, the shot cuts to a wide shot: <Subject 1> "
                                "leaves the pier. " + filler(160) + "\n[Shot 2] At 00:05.000, the shot cuts to a tracking "
                                "shot along the seawall. " + filler(160),
        "overall_soundscape": "Gulls and the sound of <Audio 1>.", "non_diegetic_music": "N/A"},
    # scene numbering and scene times: renumbered and moved to pass time
    2: {"summary": "The rain starts.",
        "detailed_description": "[Shot 3] A medium shot: the rain starts. @Mara (S1) mutters, <d>[English] Almost "
                                "home.</d> " + filler(150) + "\n[Shot 4] At 00:18.000, the shot cuts to a close-up of "
                                "rain on her face. " + filler(150),
        "overall_soundscape": "Rain.", "non_diegetic_music": ""},
    3: {"summary": "She reaches the door.", "detailed_description": "[Shot 1] A wide shot: she reaches the door."},
}


def pass_server(seen, answers=PASS_ANSWERS):
    async def handler(request):
        body = await request.json()
        seen.append(body)
        return await stream_response(request, sse((json.dumps(answers[asked_pass(body)]), "")))
    return handler


def test_write_passes_one_request_per_pass(harbor):
    from reelwright import prompt
    p, scene = long_scene(harbor)
    seen, events = [], []
    out = run_app(lambda cfg: llm.write_passes(cfg, p, scene, None, "make it rain harder", progress=events.append),
                  pass_server(seen), include_guides=True, guides={"ref-en.txt": "REF-GUIDE", "base-en.txt": "BASE-GUIDE"})
    assert [asked_pass(b) for b in seen] == [1, 2, 3]
    systems = {b["messages"][0]["content"] for b in seen}
    assert len(systems) == 1  # one system prompt for the whole batch (the server's prefix cache)
    system = systems.pop()
    assert "REF-GUIDE" in system and "BASE-GUIDE" in system and "350-500 English words in detailed_description" in system
    assert [b["max_tokens"] for b in seen] == [8192] * 3  # thinking may be on: at least PASS_MIN_TOKENS_THINKING
    u1, u2, u3 = (b["messages"][1]["content"] for b in seen)
    # pass 1: the start of a tail scene, no pass before it
    assert "The pass before" not in u1 and "It continues seamlessly from the end of the scene before (@tail)." in u1
    assert "@tail -> <Video 1>: the end of the scene before; [Shot 1] continues seamlessly from its final frames" in u1
    assert "The pass after (pass 2, scene 00:14.375 to 00:22.000), only so this pass leads into it" in u1
    # pass 2: its range, shots and line in pass and scene time, the pass before as just written, the pass after
    assert "Write the prompt of pass 2 of 3. It covers scene time 00:14.375 to 00:22.000 (7.62 s)" in u2
    assert ("[Shot 2] 00:03.625 to 00:07.625 in the pass (scene 00:18.000 to 00:22.000, 4.00 s): Close | rain runs "
            "down her face") in u2
    import re
    assert re.search(r"00:01\.625 in the pass \(scene 00:16\.000\), in \[Shot 1\](, about 1\.0 s)?: @Mara \(S1\) mutters, "
                     r"<d>\[English\] Almost home\.</d>", u2)
    assert "The pass before (pass 1, scene 00:00.000 to 00:14.375) was just written." in u2
    assert "Its summary: @Mara leaves the pier (pass one)." in u2
    assert "Its last shot: [Shot 2] At 00:06.000, the shot cuts to a tracking shot along the seawall." in u2
    assert "Shot at scene 00:22.000: Wide | she reaches the door" in u2 and "Shot at scene 00:00.000" not in u2
    assert "Whole-scene note" in u2 and "@Mara walks home as a storm builds" in u2
    assert "Not sent with this pass (the editor writes them as words): @P3" in u2
    assert "Instruction: make it rain harder" in u2 and "2 [Shot N] lines (about 212 words per shot, 350-500" in u2
    assert "Leave subject_definitions empty" in u2 and "What H3 receives for this pass now" in u2
    # [OLD 2026-11-06 v0.9.0->v0.10.0] assert "The pass after" not in u3 and "Its last spoken line: @Mara <d>[English] Almost home.</d>" in u3
    # added 2026-11-06 v0.10.0: the last line of the pass before is plain words, marked as already spoken
    assert "The pass after" not in u3 and \
        'Its last spoken line (already spoken in pass 2; never write it again): @Mara: "Almost home."' in u3
    assert ("Frame guides of this pass (sent as pictures when the text names them):\n@P3 is the keyframe at 00:03.000 in "
            "the pass (scene 00:25.000), in [Shot 1]: name it in that shot, for example \"the shot's keyframe corresponds "
            "to @P3\"") in u3
    assert "Not sent with this pass" not in u3
    # the answers, tidied
    plan, _ = llm.scene_builds(p, scene)
    assert [(x["index"], x["start"], x["end"]) for x in out["passes"]] == \
        [(x["index"], x["start"], x["end"]) for x in plan["passes"]]
    s1, s2, s3 = (x["sections"] for x in out["passes"])
    assert set(s1) == set(prompt.REF2VA_SECTIONS)
    assert s1["summary"] == "@Mara leaves the pier (pass one)."  # labels back to @ tokens, no task-type prefix
    assert s1["subject_definitions"] == "" and s1["retention_analysis"] == ""  # the editor writes them (auto)
    d1 = s1["detailed_description"].split("\n")
    assert d1[0] == "Live-action, dusk light." and d1[1].startswith("[Shot 1] A wide shot: @Mara leaves the pier.")
    assert d1[2].startswith("[Shot 2] At 00:06.000, the shot cuts to a tracking shot")
    assert s1["overall_soundscape"] == "Gulls and the sound of @tail." and s1["non_diegetic_music"] == "N/A"
    d2 = s2["detailed_description"].split("\n")
    assert d2[0].startswith("[Shot 1] A medium shot: the rain starts. @Mara (S1) mutters, <d>[English] Almost home.</d>")
    assert d2[1].startswith("[Shot 2] At 00:03.625, the shot cuts to a close-up of rain on her face.")
    assert s3 == {"subject_definitions": "", "summary": "She reaches the door.", "retention_analysis": "",
                  "detailed_description": "[Shot 1] A wide shot: she reaches the door.", "overall_soundscape": "",
                  "non_diegetic_music": ""}
    w = out["warnings"]
    assert "Pass 1: cut times set to the timeline's: [Shot 2] 00:05.000 -> 00:06.000" in w
    assert "Pass 2: the shots were numbered [Shot 3], [Shot 4] and are numbered from [Shot 1] in the pass" in w
    assert "Pass 2: cut times set to the timeline's: [Shot 2] 00:18.000 -> 00:03.625" in w
    assert any(x.startswith("Pass 3: the detailed description has 7 words; H3's guide asks for 350-500") for x in w)
    assert "Pass 3: the keyframe @P3 is not named, so it is only anchored, not sent as a picture" in w
    assert not any(x.startswith(("Pass 1: the detailed", "Pass 2: the detailed", "Pass 2: spoken")) for x in w)
    assert out["scene_id"] == "s_long" and out["pass_count"] == 3 and out["tokens"] == 3 and out["ms"] >= 0
    # progress: every event says which pass of how many, and how far the batch is
    assert {(e["pass"], e["passes"], e["item"], e["items"]) for e in events} == {(1, 3, 1, 3), (2, 3, 2, 3), (3, 3, 3, 3)}
    assert [e["completed"] for e in events if e["phase"] == "waiting"] == [0, 1, 2]


def test_write_passes_stop_keeps_the_passes_written(harbor):
    p, scene = long_scene(harbor)
    seen, gate = [], []

    async def handler(request):
        body = await request.json()
        seen.append(body)
        if asked_pass(body) == 2:
            await asyncio.wait_for(gate[0].wait(), 5)
        return await stream_response(request, sse((json.dumps(PASS_ANSWERS[asked_pass(body)]), "")))

    async def go(cfg):
        gate.append(asyncio.Event())
        state = {}
        task = asyncio.ensure_future(llm.write_passes(cfg, p, scene, None, "", state=state))
        for _ in range(250):
            if state.get("passes") and len(seen) == 2:
                break
            await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
            stopped = False
        except asyncio.CancelledError:
            stopped = True
        gate[0].set()
        return state, stopped
    state, stopped = run_app(go, handler)
    assert stopped and [x["index"] for x in state["passes"]] == [1] and len(seen) == 2
    assert state["passes"][0]["sections"]["summary"] == "@Mara leaves the pier (pass one)."


def test_write_passes_retries_busy_and_cut_off_answers(harbor):
    p, scene = long_scene(harbor)
    calls, events = [], []

    async def handler(request):
        body = await request.json()
        calls.append((asked_pass(body), body["max_tokens"]))
        if len(calls) == 1:
            return web.json_response({"error": {"message": "rate limit"}}, status=429, headers={"Retry-After": "0"})
        if len(calls) == 3:
            return await stream_response(request, sse(('{"summary": "The rain sta', ""), finish="length"))
        return await stream_response(request, sse((json.dumps(PASS_ANSWERS[asked_pass(body)]), "")))
    out = run_app(lambda cfg: llm.write_passes(cfg, p, scene, [2, 1], "", progress=events.append), handler, retries=2)
    # pass 1 waits once after the 429; pass 2's cut-off answer is asked again with twice the budget
    assert calls == [(1, 8192), (1, 8192), (2, 8192), (2, 16384)]
    assert [x["index"] for x in out["passes"]] == [1, 2] and "error" not in out
    assert [(e["pass"], e["attempt"]) for e in events if e["phase"] == "retry"] == [(1, 2), (2, 2)]
    assert llm.pass_budget({"max_tokens": 2048, "thinking": "off"}) == 4096
    assert llm.pass_budget({"max_tokens": 10000, "thinking": "auto"}) == 10000


def test_write_passes_failure_keeps_the_passes_before_it(harbor):
    p, scene = long_scene(harbor)
    calls = []

    async def handler(request):
        body = await request.json()
        calls.append(asked_pass(body))
        if asked_pass(body) == 2:
            return web.json_response({"error": {"message": "model 'x' not found"}}, status=404)
        return await stream_response(request, sse((json.dumps(PASS_ANSWERS[asked_pass(body)]), "")))
    out = run_app(lambda cfg: llm.write_passes(cfg, p, scene), handler, retries=2)
    assert calls == [1, 2]  # a 404 is not retried, and the batch ends there
    assert [x["index"] for x in out["passes"]] == [1] and out["failed"] == 2 and out["reason"] == "http"
    assert "not found" in out["error"] and "Pass 2 was not written: model 'x' not found" in out["warnings"]

    async def go(cfg):  # nothing written yet: the error is raised, as for Rewrite
        with pytest.raises(llm.LLMError) as e:
            await llm.write_passes(cfg, p, scene, [2, 3])
        return e.value
    assert run_app(go, handler).reason == "http"


def test_write_passes_checks_its_input(harbor):
    import copy
    p, scene = long_scene(harbor)
    cfg = llm.resolve({"base_url": "http://127.0.0.1:9/v1"}, {"base_url": "", "model": "", "api_key": ""})
    with pytest.raises(ValueError, match="pass 4, 7 is not in this scene, which is made in 3 passes"):
        asyncio.run(llm.write_passes(cfg, p, scene, [7, 4]))
    raw = copy.deepcopy(scene)
    raw["prompt"]["mode"] = "raw"
    with pytest.raises(ValueError, match="raw text"):
        asyncio.run(llm.write_passes(cfg, p, raw))


def test_pass_request_for_one_pass_and_after_an_overlap_seam(harbor):
    from reelwright.model import normalize_project
    p, scene = long_scene(harbor)
    one = p["scenes"][0]
    plan, builds = llm.scene_builds(p, one)
    user = llm.pass_request(p, one, plan, builds, 1)
    assert "This scene is made in one pass; write its prompt." in user
    assert "The pass before" not in user and "The pass after" not in user
    p["global"]["long"]["seam_mode"] = "overlap"
    plan, builds = llm.scene_builds(p, scene)
    user = llm.pass_request(p, scene, plan, builds, 2, {}, [{}, {}, {"summary": "She reaches the door at last."}])
    assert ("It starts at an overlap seam, in the middle of a shot: its first 1.62 s repeat the end of pass 1, and its "
            "[Shot 1] continues that shot seamlessly.") in user
    assert "- it continues the shot that is running at the end of pass 1: Tracking | along the seawall" in user
    assert "@tail -> <Video 1>: the end of pass 1; [Shot 1] continues seamlessly from its final frames" in user
    assert '(its own sound is sent as <Audio 2>; write it as "the sound of @V1")' in user
    assert "has no text of its own yet" in user
    assert "Its last shot: [Shot 3] At 00:14.375, the shot cuts to a medium shot: the rain starts." in user  # as built
    assert "Its summary: She reaches the door at last." in user  # the pass after, written earlier
    # texts stored for the current layout are found again
    scene["prompt"]["passes"] = [{"start": plan["passes"][0]["start"], "end": plan["passes"][0]["end"],
                                  "sections": {"summary": "Stored one."}}]
    p = normalize_project(p)
    scene = p["scenes"][1]
    assert llm.stored_pass_texts(p, scene, plan)[0]["summary"] == "Stored one."


def test_pass_answers_in_other_shapes():
    secs = {"summary": "S", "detailed_description": "D"}
    assert llm.pass_sections(secs, 2) == secs
    assert llm.pass_sections({"sections": secs}, 2) == secs
    assert llm.pass_sections({"passes": [{"index": 1, "sections": {"summary": "one"}}, {"index": 2, "sections": secs}]},
                             2) == secs
    assert llm.pass_sections({"pass 2": secs, "pass 3": {"summary": "x"}}, 2) == secs
    assert llm.pass_sections({"P2": secs}, 5) == secs  # the only one
    assert llm.pass_sections([secs], 2) == secs
    assert llm.pass_sections({"prompt": "summary:\nS\n\ndetailed_description:\nD"}, 2) == secs
    assert llm.pass_sections("Here it is.\nsummary: S\ndetailed_description:\nD", 2) == secs
    assert llm.pass_sections({"notes": "x"}, 2) is None and llm.pass_sections([1, 2], 2) is None
    parse = llm._pass_parser(2)
    assert parse('Sure! {"summary": "S", "detailed_description": "D",}', {}) == secs
    assert parse("summary:\nS\n\ndetailed_description:\nD", {}) == secs  # labelled text, not JSON
    with pytest.raises(llm.LLMError) as e:
        parse("summary:\nS", {"finish": "length", "budget": 8192})
    assert e.value.reason == "cut" and "pass 2 was cut off at 8,192 tokens" in str(e.value)
    with pytest.raises(llm.LLMError) as e:
        parse("I cannot do that.", {})
    assert e.value.reason == "bad_json"


def test_tidy_pass_checks_the_answer(harbor):
    p, scene = long_scene(harbor)
    plan, builds = llm.scene_builds(p, scene)
    x, b = plan["passes"][1], builds[1]  # two shots, "Almost home."
    desc = ("[Shot 1] Rain. @Bob (S1) says, <d>[English] Hello there.</d>\n[Shot 2] At 00:03.625, the shot cuts to a "
            "close-up.\n[Shot 3] At 00:05.000, the shot cuts to more rain.")
    secs = {"summary": "N/A", "subject_definitions": "@Mara is the woman.", "detailed_description": desc,
            "overall_soundscape": "summary:\nRain on <Audio 7>."}
    out, warns = llm.tidy_pass(secs, x, b, {"subjects": False, "retention": True, "shots": True}, 2,
                               llm._scene_tokens(p, scene))
    assert out["summary"] == "" and out["subject_definitions"] == "@Mara is the woman." and out["retention_analysis"] == ""
    # [OLD 2026-11-06 v0.9.0->v0.10.0] a spoken line that is not the pass's stayed in the text (H3 said it)
    # assert out["detailed_description"] == desc  # three lines for two shots: kept as written
    # added 2026-11-06 v0.10.0: three lines for two shots are kept as written, but "Hello there." (not this pass's)
    # leaves with its sentence
    assert out["detailed_description"] == desc.replace(" @Bob (S1) says, <d>[English] Hello there.</d>", "")
    assert out["overall_soundscape"] == "summary:\nRain on <Audio 7>."  # another section's label: kept as written
    for bit in ("<Audio 7> left as written", "the answer has 3 [Shot N] lines for the pass's 2 shots",
                'spoken lines missing or changed: "Almost home."',
                # [OLD 2026-11-06 v0.9.0->v0.10.0] "spoken lines that are not this pass's (H3 would say them): \"Hello there.\"",
                # [OLD 2026-11-06 v0.9.0->v0.10.0] "references the scene does not have: @Bob",  (@Bob left with the line)
                "removed spoken lines that are not this pass's (H3 would have said them): \"Hello there.\"",
                "the detailed description has "):
        assert any(bit in w for w in warns), (bit, warns)
    # added 2026-11-06 v0.10.0: a line of the pass written twice keeps its first copy
    two = ("[Shot 1] Rain. @Mara (S1) mutters, <d>[English] Almost home.</d> She smiles.\n[Shot 2] At 00:03.625, the "
           "shot cuts to a close-up. @Mara (S1) repeats, <d>[English] Almost home!</d> while her lips tremble.")
    out, warns = llm.tidy_pass({"detailed_description": two}, x, b, {"subjects": True, "retention": True, "shots": True}, 2)
    assert out["detailed_description"].count("Almost home") == 1 and "She smiles." in out["detailed_description"]
    assert out["detailed_description"].endswith("the shot cuts to a close-up.") and "lips" not in out["detailed_description"]
    assert any(w.startswith('removed a second copy of: "Almost home!"') for w in warns), warns
    # the whole prompt in one key is split into its sections
    whole = {"detailed_description": "summary:\nShe walks.\n\ndetailed_description:\n[Shot 1] Rain.\n[Shot 2] Close."}
    out, _ = llm.tidy_pass(whole, x, b, {"subjects": True, "retention": True, "shots": True}, 2)
    assert out["summary"] == "She walks." and out["detailed_description"].startswith("[Shot 1] Rain.\n[Shot 2] At 00:03.625")


def test_script_import_asks_for_fuller_shots_and_a_scene_note():
    from reelwright.model import default_project
    seen = []
    answer = {"scenes": [{"title": "Pier", "summary": "Dusk at the harbor; Mara walks out and stops.", "shots": [
        {"t": 0, "duration": 4, "camera": "Wide", "composition": "A wide shot of the harbor at dusk", "subject": "Mara",
         "action": "Mara walks to the end of the pier", "sound": "gulls cry over the water"},
        {"t": 4, "duration": 3, "text": "Mara stops."}]}], "cast": []}

    async def handler(request):
        seen.append(await request.json())
        return await stream_response(request, sse((json.dumps(answer), "")))
    out = run_app(lambda cfg: llm.script_part(cfg, default_project("Demo"), "INT. PIER - DUSK\nMara walks."), handler)
    user = seen[0]["messages"][1]["content"]
    assert "Each shot's \"text\" is 2-4 English sentences" in user and "note on the whole scene in 2-4 sentences" in user
    assert "\"duration\": seconds, \"camera\"" in user  # the JSON shape is the same as before
    shots = out["scenes"][0]["shots"]
    assert shots[0]["text"] == ("A wide shot of the harbor at dusk. Mara walks to the end of the pier. gulls cry over the "
                                "water.")
    assert shots[1]["text"] == "Mara stops."  # an answer in the old shape is read as before
    assert out["scenes"][0]["summary"] == "Dusk at the harbor; Mara walks out and stops."
    # the default budget per part is bigger, in Python and in the editor's model
    assert llm.resolve({"base_url": "x:1/v1"}, {"base_url": "", "model": "", "api_key": ""})["import_max_tokens"] == 24576
    assert default_project("Demo")["global"]["llm"]["import_max_tokens"] == 24576 == llm.IMPORT_MAX_TOKENS
