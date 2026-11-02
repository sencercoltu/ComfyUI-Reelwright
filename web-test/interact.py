"""Interaction checks against the mock harness: resize, split, undo, autocomplete,
queueing and persistence. Run: python3 web-test/interact.py"""

import json
import sys

from playwright.sync_api import sync_playwright

from shoot import serve


def project(page):
    return json.loads(page.evaluate("window.__host.getProject()"))


def main():
    httpd = serve()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/web-test/harness.html"
    errors, failures = [], []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.goto(url)
        page.wait_for_selector(".rw-scene")
        page.wait_for_timeout(600)

        # Resize scene 01 by dragging its right edge; snapping keeps it on the 17k+5 grid.
        handle = page.locator(".rw-scene").nth(0).locator(".rw-resize")
        box = handle.bounding_box()
        page.mouse.move(box["x"] + 3, box["y"] + 20)
        page.mouse.down()
        page.mouse.move(box["x"] + 3 + 60, box["y"] + 20, steps=6)
        page.mouse.up()
        page.wait_for_timeout(400)
        d = project(page)["scenes"][0]["duration"]
        frames = round(d * 24)
        check(d > 8.0, f"resize did not lengthen scene 01 ({d})")
        check(frames % 17 == 5, f"snap did not land on 17k+5 ({frames} f)")

        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(project(page)["scenes"][0]["duration"] == 8.0, "undo did not restore the duration")

        # Split the selected scene at the playhead with S.
        n = len(project(page)["scenes"])
        page.locator(".rw-root").focus()
        page.keyboard.press("s")
        page.wait_for_timeout(300)
        check(len(project(page)["scenes"]) == n + 1, "S did not split the scene")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(len(project(page)["scenes"]) == n, "undo did not revert the split")

        # Join chip cycles the start mode of scene 02.
        page.locator(".rw-join").first.click()
        page.wait_for_timeout(300)
        check(project(page)["scenes"][1]["start"]["mode"] == "tail", "join chip did not cycle last_frame → tail")

        # Prompt autocomplete inserts an asset tag.
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(300)
        ta = page.locator(".rw-psec").nth(1).locator("textarea")
        ta.click()
        ta.press("End")
        ta.type(" with @P", delay=20)
        page.wait_for_timeout(200)
        check(page.locator(".rw-ac.on .rw-ac-item").count() > 0, "autocomplete list did not open")
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        page.locator(".rw-card-title:has-text('Duration')").click()
        page.wait_for_timeout(500)
        summary = project(page)["scenes"][2]["prompt"]["sections"]["summary"]
        check("@P1" in summary, f"autocomplete did not insert @P1: {summary!r}")

        # Render scope buttons queue a request.
        page.click(".rw-tab:has-text('Render')")
        page.wait_for_timeout(300)
        page.click(".rw-scope button:has-text('Selected')")
        page.wait_for_timeout(300)
        q = page.evaluate("window.__host.queued")
        check(q and q[-1]["action"] == "selected" and q[-1]["scenes"] == ["s_03"], f"queue request wrong: {q}")

        # Global seed edit persists to the widget value.
        page.click(".rw-tab:has-text('Global')")
        page.wait_for_timeout(300)
        seed = page.locator("input[data-help='global.sampling.seed']")
        seed.fill("42")
        seed.press("Tab")
        page.wait_for_timeout(500)
        check(project(page)["global"]["sampling"]["seed"] == 42, "seed edit not persisted")

        # ---- added 2026-11-02 v0.2.0 ----
        shots = __import__("shoot").SHOTS

        # LLM model combobox filters as you type and accepts a typed id.
        page.click("button[data-help='global.llm.listModels']")
        page.wait_for_timeout(300)
        model = page.locator(".rw-combo input[data-help='global.llm.model']")
        model.click()
        model.fill("minimax")
        page.wait_for_timeout(150)
        opts = page.locator(".rw-combo-list .rw-combo-opt:not(.free)").all_inner_texts()
        check(opts and all("minimax" in o.lower() for o in opts), f"model filter showed {opts}")
        page.screenshot(path=str(shots / "v020_model_filter.png"), clip={"x": 0, "y": 0, "width": 1600, "height": 1000})
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        check(project(page)["global"]["llm"]["model"] == opts[1], f"arrow+Enter did not pick {opts[1:2]}")
        model.click()
        model.fill("my-custom-vl")
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        check(project(page)["global"]["llm"]["model"] == "my-custom-vl", "free model id not accepted")

        # Language accepts a value that is not in the list.
        lang = page.locator(".rw-combo input[data-help='global.defaults.language']")
        lang.click()
        lang.fill("Turk")
        page.wait_for_timeout(150)
        lang.fill("Klingon")
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        check(project(page)["global"]["defaults"]["language"] == "Klingon", "free language not accepted")

        # Guides download updates the status.
        page.click("button[data-help='global.llm.guidesFetch']")
        page.wait_for_timeout(400)
        check("official" in page.inner_text("[data-help='global.llm.guidesStatus']"), "guide status not updated")

        # ? popover opens to the right of its icon, stays inside the node and can be dragged.
        q = page.locator(".rw-card-head .rw-q").first
        q.click()
        page.wait_for_timeout(200)
        qb, pb, rb = q.bounding_box(), page.locator(".rw-pop").bounding_box(), page.locator(".rw-root").bounding_box()
        check(pb["x"] >= qb["x"] + qb["width"] - 1 or pb["x"] + pb["width"] <= qb["x"] + 1, f"popover not beside the ?: {qb} {pb}")
        check(pb["x"] >= rb["x"] and pb["x"] + pb["width"] <= rb["x"] + rb["width"] and pb["y"] + pb["height"] <= rb["y"] + rb["height"], "popover leaves the node")
        hb = page.locator(".rw-pop-head").bounding_box()
        page.mouse.move(hb["x"] + 40, hb["y"] + 10)
        page.mouse.down()
        page.mouse.move(hb["x"] + 240, hb["y"] + 130, steps=6)
        page.mouse.up()
        pb2 = page.locator(".rw-pop").bounding_box()
        check(abs(pb2["x"] - pb["x"] - 200) < 3 and abs(pb2["y"] - pb["y"] - 120) < 3, f"popover drag moved {pb} -> {pb2}")
        page.screenshot(path=str(shots / "v020_popover.png"))
        page.keyboard.press("Escape")

        # Scene preview uses the Ref2VA section labels.
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(400)
        pre = page.inner_text(".rw-prompt-preview")
        check(pre.startswith("subject_definitions:\n") and "\nretention_analysis:\n" in pre and "Subjects:" not in pre, f"preview format: {pre[:80]!r}")

        # Assets: add a generated file from ComfyUI's output folder, then describe it.
        page.click(".rw-tab:has-text('Assets')")
        page.wait_for_timeout(300)
        page.click("button[data-help='assets.browse']")
        page.wait_for_timeout(300)
        page.click("button[data-help='assets.browse.root'] >> text=Output")
        page.wait_for_timeout(300)
        n_assets = len(project(page)["assets"])
        page.locator(".rw-browse-tile").nth(2).click()
        page.wait_for_timeout(150)
        page.screenshot(path=str(shots / "v020_browse.png"))
        page.click("button[data-help='assets.browse.add']")
        page.wait_for_timeout(500)
        assets = project(page)["assets"]
        check(len(assets) == n_assets + 1 and "from_output/" in assets[-1]["file"], "output file not imported")
        page.locator(".rw-asset-card:has-text('mara_portrait')").click()
        page.wait_for_timeout(300)
        page.click("button[data-help='assets.describe']")
        page.wait_for_timeout(400)
        page.screenshot(path=str(shots / "v020_describe.png"))
        page.click("button[data-help='assets.describe.use']")
        page.wait_for_timeout(400)
        check("pea coat" in project(page)["assets"][-1]["description"], "describe result not used")

        # Render tab: Merge lives next to the takes, and every scene shows its rendered file.
        check(page.locator(".rw-tabbar button[data-help='app.merge']").count() == 0, "Merge still in the tab bar")
        page.click(".rw-tab:has-text('Render')")
        page.wait_for_timeout(400)
        files = page.locator(".rw-tfile").all_inner_texts()
        check(files and files[0].startswith("harbor_lights_01_harbor_at_dusk_"), f"file column: {files[:2]}")
        page.click(".rw-card-head button[data-help='app.merge']")
        page.wait_for_timeout(400)
        check(page.locator("a[data-help='render.lastCut']").count() == 1, "last cut link missing after merge")
        page.screenshot(path=str(shots / "v020_render.png"))

        # ---- added 2026-11-02 v0.2.2 ----
        # Right-click on a scene opens the editor's own menu; its actions work.
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        n = len(project(page)["scenes"])
        page.locator(".rw-scene").nth(1).click(button="right")
        page.wait_for_timeout(200)
        items = page.locator(".rw-ctx .rw-ctx-item").all_inner_texts()
        check(any(i.startswith("Delete scene") for i in items) and any(i.startswith("Duplicate") for i in items), f"scene menu items: {items}")
        page.screenshot(path=str(shots / "v022_scene_menu.png"))
        page.locator(".rw-ctx .rw-ctx-item:has-text('Duplicate')").click()
        page.wait_for_timeout(300)
        check(len(project(page)["scenes"]) == n + 1, "menu Duplicate did not add a scene")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        page.locator(".rw-scene").nth(1).click(button="right")
        page.wait_for_timeout(200)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        check(page.locator(".rw-ctx").count() == 0, "Escape did not close the scene menu")
        # A press on a combobox list (scrollbar gutter included) keeps it open with the filter.
        page.click(".rw-tab:has-text('Global')")
        page.wait_for_timeout(300)
        lang = page.locator(".rw-combo input[data-help='global.defaults.language']")
        lang.click()
        lang.fill("an")
        page.wait_for_timeout(150)
        bb = page.locator(".rw-combo-list").bounding_box()
        page.mouse.move(bb["x"] + bb["width"] - 3, bb["y"] + 10)
        page.mouse.down()
        page.mouse.up()
        page.wait_for_timeout(200)
        check(page.locator(".rw-combo-list").count() == 1 and lang.input_value() == "an", "list closed or filter lost after pressing the list")
        page.keyboard.press("Escape")

        # ---- added 2026-11-02 v0.3.0 ----
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        # Delete scene asks first; Cancel keeps it, Delete removes it.
        n = len(project(page)["scenes"])
        page.locator(".rw-scene").nth(1).click(button="right")
        page.wait_for_timeout(200)
        page.locator(".rw-ctx .rw-ctx-item:has-text('Delete scene')").click()
        page.wait_for_timeout(200)
        check(page.locator(".rw-modal").count() == 1, "delete scene did not ask for confirmation")
        page.screenshot(path=str(shots / "v030_confirm.png"))
        page.locator(".rw-modal button:has-text('Cancel')").click()
        page.wait_for_timeout(200)
        check(len(project(page)["scenes"]) == n and page.locator(".rw-modal").count() == 0, "Cancel deleted the scene")
        page.locator(".rw-scene").nth(1).click(button="right")
        page.wait_for_timeout(200)
        page.locator(".rw-ctx .rw-ctx-item:has-text('Delete scene')").click()
        page.wait_for_timeout(200)
        page.locator(".rw-modal button:has-text('Delete')").click()
        page.wait_for_timeout(300)
        check(len(project(page)["scenes"]) == n - 1, "confirmed delete did not remove the scene")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(len(project(page)["scenes"]) == n, "undo did not bring the scene back")

        # Deleting the only scene resets it to an empty scene.
        orig = page.evaluate("window.__host.getProject()")
        one = json.loads(orig)
        one["scenes"] = one["scenes"][:1]
        page.evaluate("j => window.__editor.load(j)", json.dumps(one))
        page.wait_for_timeout(400)
        page.locator(".rw-scene").nth(0).click(button="right")
        page.wait_for_timeout(200)
        items = page.locator(".rw-ctx .rw-ctx-item").all_inner_texts()
        check(any(i.startswith("Reset scene") for i in items), f"single scene menu: {items}")
        page.locator(".rw-ctx .rw-ctx-item:has-text('Reset scene')").click()
        page.wait_for_timeout(200)
        page.locator(".rw-modal .rw-btn-danger, .rw-modal button:has-text('Reset')").first.click()
        page.wait_for_timeout(300)
        sc = project(page)["scenes"]
        check(len(sc) == 1 and sc[0]["title"] == "Scene 1" and not sc[0]["prompt"]["sections"].get("summary") and not sc[0].get("refs") and not sc[0].get("dialogue"),
              f"last scene not reset: {sc[0]['title']!r} {sc[0]['prompt']['sections'].get('summary', '')[:40]!r}")
        page.evaluate("j => window.__editor.load(j)", orig)
        page.wait_for_timeout(400)

        # Assets can be deleted from their right-click menu; references go with them.
        page.click(".rw-tab:has-text('Assets')")
        page.wait_for_timeout(300)
        n_assets = len(project(page)["assets"])
        card = page.locator(".rw-asset-card").first
        aid = project(page)["assets"][0]["id"]
        card.click(button="right")
        page.wait_for_timeout(200)
        page.locator(".rw-ctx .rw-ctx-item:has-text('Delete asset')").click()
        page.wait_for_timeout(200)
        page.locator(".rw-modal button:has-text('Delete')").click()
        page.wait_for_timeout(300)
        pj = project(page)
        check(len(pj["assets"]) == n_assets - 1 and aid not in json.dumps(pj["scenes"]), "asset not deleted or still referenced")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)

        # Profiles: save, mark as default, change a setting, apply it back.
        page.click(".rw-tab:has-text('Global')")
        page.wait_for_timeout(400)
        page.fill("input[data-help='global.profiles.name']", "Studio A")
        page.click("button[data-help='global.profiles.save']")
        page.wait_for_timeout(400)
        prof = page.evaluate("window.__mockProfiles")
        check(len(prof["profiles"]) == 1 and prof["profiles"][0]["name"] == "Studio A", f"profile not saved: {prof}")
        page.click("[data-help='global.profiles.default']")
        page.wait_for_timeout(400)
        check(page.evaluate("window.__mockProfiles.default") == prof["profiles"][0]["id"], "default profile not set")
        seed = page.locator("input[data-help='global.sampling.seed']")
        seed.fill("777")
        seed.press("Tab")
        page.wait_for_timeout(400)
        page.click("button[data-help='global.profiles.apply']")
        page.wait_for_timeout(200)
        page.locator(".rw-modal button.rw-btn-primary, .rw-modal button:has-text('Apply')").last.click()
        page.wait_for_timeout(400)
        check(project(page)["global"]["sampling"]["seed"] == 42, "apply did not restore the profile seed")
        page.screenshot(path=str(shots / "v030_profiles.png"))
        # A new node starts from the default profile and offers the banner.
        page.evaluate("window.__editor.startNew()")
        page.wait_for_timeout(500)
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        check(page.locator(".rw-profile-banner").count() == 1, "profile banner missing on a new node")
        page.screenshot(path=str(shots / "v030_banner.png"))
        page.locator(".rw-profile-banner button[data-help='common.close']").click()
        page.wait_for_timeout(200)

        # Per-scene quality and transition.
        pj = project(page)
        fi = next(i for i, s in enumerate(pj["scenes"]) if i > 0 and s["start"]["mode"] == "fresh")
        page.locator(".rw-scene").nth(fi).click()
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(400)
        page.locator("[data-help='scene.override.quality'] button:has-text('Draft')").first.click()
        page.wait_for_timeout(300)
        check(project(page)["scenes"][fi]["overrides"].get("quality") == "draft", "scene quality override not set")
        page.locator("[data-help='scene.transition.mode'] button:has-text('Dip to black')").first.click()
        page.wait_for_timeout(300)
        nf = page.locator("input[data-help='scene.transition.frames']")
        nf.fill("20")
        nf.press("Tab")
        page.wait_for_timeout(300)
        tr = project(page)["scenes"][fi]["transition"]
        check(tr["mode"] == "dip" and tr["frames"] == 20, f"scene transition: {tr}")
        page.screenshot(path=str(shots / "v030_scene.png"))
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        check(page.locator(".rw-scene").nth(fi).locator(".rw-qtag").count() == 1, "draft tag missing on the timeline")

        # Run progress: scene k of n in the Render tab and in the node title.
        page.click(".rw-tab:has-text('Render')")
        page.wait_for_timeout(300)
        page.evaluate("""() => { const h = window.__host;
          h.emit('reelwright.run', { slug: 'harbor_lights', phase: 'start', targets: ['s_01', 's_02'], reused: ['s_03'] });
          h.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_01', pass: 1, passes: 1, step: 28, steps: 28, phase: 'done' });
          h.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 2, step: 14, steps: 28, phase: 'sample' }); }""")
        page.wait_for_timeout(400)
        banner = page.inner_text("[data-help='render.banner']")
        check("Scene 2 of 2" in banner and page.locator("[data-help='render.progress.total']").count() == 1, f"banner: {banner!r}")
        titles = page.evaluate("window.__host.titles")
        check(titles and titles[-1] == "rendering 2/2 · 63%", f"node title: {titles[-3:]}")
        page.screenshot(path=str(shots / "v030_progress.png"))
        page.evaluate("window.__host.emit('reelwright.run', { slug: 'harbor_lights', phase: 'end', targets: ['s_01', 's_02'], reused: [] })")
        page.wait_for_timeout(300)
        check(page.evaluate("window.__host.titles").pop() is None, "title not cleared after the run")

        # Ctrl + wheel over the node goes to the canvas, but not over a text field.
        page.click(".rw-tab:has-text('Global')")
        page.wait_for_timeout(300)
        hb = page.locator(".rw-card-head").first.bounding_box()
        page.mouse.move(hb["x"] + 30, hb["y"] + 8)
        page.keyboard.down("Control")
        page.mouse.wheel(0, -120)
        page.keyboard.up("Control")
        page.wait_for_timeout(100)
        w1 = len(page.evaluate("window.__host.wheels"))
        ib = page.locator("input[data-help='global.sampling.seed']").bounding_box()
        page.mouse.move(ib["x"] + 10, ib["y"] + 5)
        page.keyboard.down("Control")
        page.mouse.wheel(0, -120)
        page.keyboard.up("Control")
        page.wait_for_timeout(100)
        w2 = len(page.evaluate("window.__host.wheels"))
        check(w1 == 1 and w2 == 1, f"ctrl+wheel forwarding: {w1}, {w2}")

        # LLM connection test reports success and failure.
        page.click("button[data-help='global.llm.test']")
        page.wait_for_timeout(400)
        check(page.locator(".rw-note.ok").count() == 1, "LLM test success not shown")
        url = page.locator("input[data-help='global.llm.url'], input[data-help='global.llm.baseUrl']").first
        url.fill("http://down.local:1/v1")
        url.press("Tab")
        page.wait_for_timeout(300)
        page.click("button[data-help='global.llm.test']")
        page.wait_for_timeout(400)
        check(page.locator(".rw-note.err").count() >= 1, "LLM test failure not shown")
        page.screenshot(path=str(shots / "v030_llm.png"))

        # ---- added 2026-11-02 v0.3.1 ----
        # Script import: insert after the selected scene, append, or replace every scene.
        def propose(mode_label):
            page.click(".rw-tab:has-text('Global')")
            page.wait_for_timeout(300)
            page.fill("textarea[data-help='global.script.text']", "INT. HARBOR - NIGHT\nThe postman cycles up.")
            page.click("button[data-help='global.script.run']")
            page.wait_for_timeout(400)
            page.locator("[data-help='global.script.mode'] button").filter(has_text=mode_label).first.click()
            page.wait_for_timeout(200)
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        page.locator(".rw-scene").nth(2).click()
        page.wait_for_timeout(200)
        before = [s["id"] for s in project(page)["scenes"]]
        propose("After 03")
        page.screenshot(path=str(shots / "v031_import.png"))
        page.click("button[data-help='global.script.apply']")
        page.wait_for_timeout(400)
        pj = project(page)
        ids = [s["id"] for s in pj["scenes"]]
        check(len(ids) == len(before) + 1 and ids[:3] == before[:3] and ids[4:] == before[3:] and pj["scenes"][3]["title"] == "The postman arrives"
              and pj["ui"]["selected"] == ids[3], f"insert after selected: {[s['title'] for s in pj['scenes']]}")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check([s["id"] for s in project(page)["scenes"]] == before, "undo did not remove the inserted scene")
        propose("At the end")
        page.click("button[data-help='global.script.apply']")
        page.wait_for_timeout(400)
        pj = project(page)
        check(len(pj["scenes"]) == len(before) + 1 and pj["scenes"][-1]["title"] == "The postman arrives", "append did not add at the end")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        propose("Replace all")
        page.click("button[data-help='global.script.apply']")
        page.wait_for_timeout(300)
        check(page.locator(".rw-modal").count() == 1, "replace did not ask first")
        page.locator(".rw-modal button:has-text('Replace scenes')").click()
        page.wait_for_timeout(400)
        pj = project(page)
        check(len(pj["scenes"]) == 1 and pj["scenes"][0]["title"] == "The postman arrives" and pj["scenes"][0]["start"]["mode"] == "fresh", f"replace: {[s['title'] for s in pj['scenes']]}")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check([s["id"] for s in project(page)["scenes"]] == before, "undo did not restore the replaced scenes")

        # ---- added 2026-11-02 v0.3.2 ----
        # Thinking switch: the test explains a thinking model; Off is saved with the project.
        page.click(".rw-tab:has-text('Global')")
        page.wait_for_timeout(300)
        url = page.locator("input[data-help='global.llm.baseUrl']")
        url.fill("http://llm.local:30000/v1")
        url.press("Tab")
        page.wait_for_timeout(300)
        page.click("button[data-help='global.llm.test']")
        page.wait_for_timeout(400)
        check(page.locator(".rw-note[data-help='global.llm.thinking']").count() == 1, "thinking note missing after the test")
        page.locator("[data-help='global.llm.thinking'] button:has-text('Off')").first.click()
        page.wait_for_timeout(300)
        check(project(page)["global"]["llm"]["thinking"] == "off", "thinking switch not saved")
        page.screenshot(path=str(shots / "v032_thinking.png"))

        # ---- added 2026-11-02 v0.3.3 ----
        # Timeline: wheel scrolls sideways, click on the ruler moves the playhead, hovering does not,
        # dragging pans without touching the playhead, the playhead label scrubs.
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        page.wait_for_timeout(800)  # let the plan/autosave refresh from the previous steps land first
        z0 = project(page)["ui"]["zoom"] or 22
        page.locator(".rw-root").focus()
        for _ in range(4):
            page.keyboard.press("+")
        page.wait_for_timeout(400)
        check(abs(project(page)["ui"]["zoom"] - z0 * 1.25 ** 4) < 0.6, f"zoom after four + presses: {z0} -> {project(page)['ui']['zoom']}")
        # read the DOM in one evaluate: the editor re-renders asynchronously, so a locator can resolve an element
        # that is replaced a moment later (a detached element reports scrollLeft 0 and no bounding box)
        sl = lambda: page.evaluate("document.querySelector('.rw-lanes').scrollLeft")
        box = lambda sel, i=0: page.evaluate("([s, i]) => { const e = document.querySelectorAll(s)[i]; if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; }", [sel, i])
        ph = lambda: project(page)["ui"]["playhead"]
        lb = box(".rw-lanes")
        check(page.evaluate("(() => { const el = document.querySelector('.rw-lanes'); return el.scrollWidth > el.clientWidth; })()"), "timeline did not overflow after zooming in")
        page.evaluate("document.querySelector('.rw-lanes').scrollLeft = 0")
        page.mouse.move(lb["x"] + 400, lb["y"] + 200)
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(300)
        check(sl() > 100, f"wheel did not scroll sideways ({sl()})")
        rb = box(".rw-ruler-lane")
        page.mouse.click(lb["x"] + 500, rb["y"] + rb["height"] / 2)
        page.wait_for_timeout(300)
        t1 = ph()
        expect = (lb["x"] + 500 - rb["x"]) / project(page)["ui"]["zoom"]
        check(abs(t1 - expect) < 0.1, f"ruler click put the playhead at {t1:.2f}, expected {expect:.2f}")
        page.mouse.move(lb["x"] + 900, lb["y"] + 250, steps=6)
        page.wait_for_timeout(200)
        check(ph() == t1, "playhead followed the mouse without a press")
        # drag an empty spot of the dialogue lane: pans, playhead stays, selection stays
        sel = project(page)["ui"]["selected"]
        dl = box(".rw-lane-body", 4)
        s0 = sl()
        page.mouse.move(lb["x"] + 800, dl["y"] + dl["height"] - 4)
        page.mouse.down()
        page.mouse.move(lb["x"] + 600, dl["y"] + dl["height"] - 4, steps=8)
        page.mouse.up()
        page.wait_for_timeout(300)
        check(abs((sl() - s0) - 200) < 3 and ph() == t1 and project(page)["ui"]["selected"] == sel, f"pan: scroll {s0}->{sl()}, playhead {ph()} vs {t1}")
        # a drag that starts on a scene block pans too and does not select it
        bb = box(".rw-scene", 5)
        s0 = sl()
        page.mouse.move(bb["x"] + 30, bb["y"] + 40)
        page.mouse.down()
        page.mouse.move(bb["x"] + 130, bb["y"] + 40, steps=6)
        page.mouse.up()
        page.wait_for_timeout(300)
        s1, sel1, ph1 = sl(), project(page)["ui"]["selected"], ph()
        check(abs((s0 - s1) - 100) < 3 and sel1 == sel, f"drag on a scene block did not pan or selected it: scroll {s0}->{s1}, selected {sel1} vs {sel}, playhead {ph1}")
        # the playhead label scrubs
        hb = box(".rw-playhead-label")
        check(hb is not None, f"playhead label not visible (tab {page.inner_text('.rw-tab.on')})")
        if hb:
            page.mouse.move(hb["x"] + hb["width"] / 2, hb["y"] + hb["height"] / 2)
            page.mouse.down()
            page.mouse.move(hb["x"] + hb["width"] / 2 + 120, hb["y"] + hb["height"] / 2, steps=6)
            page.mouse.up()
            page.wait_for_timeout(300)
            check(abs(ph() - (t1 + 120 / project(page)["ui"]["zoom"])) < 0.15, f"playhead drag: {ph():.2f}")
        # a release that never reaches the editor: the next move without a button ends the drag
        t2 = ph()
        page.evaluate("""() => {
          const r = document.querySelector('.rw-ruler-lane'), b = r.getBoundingClientRect();
          r.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, buttons: 1, clientX: b.left + 50, clientY: b.top + 5 }));
          window.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, buttons: 0, clientX: b.left + 400, clientY: b.top + 5 }));
          window.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, buttons: 1, clientX: b.left + 600, clientY: b.top + 5 }));
        }""")
        page.wait_for_timeout(200)
        check(ph() == t2 and not page.evaluate("document.querySelector('.rw-root').classList.contains('rw-panning')"), "a lost release left the drag running")
        page.screenshot(path=str(shots / "v033_timeline.png"))

        # ---- added 2026-11-02 v0.3.4 ----
        # An asset's description is shown live wherever it is used, and a character without its own
        # description picks up its first described anchor.
        page.wait_for_timeout(600)
        page.evaluate("document.querySelector('.rw-lanes').scrollLeft = 0")
        page.locator(".rw-scene").nth(4).click()
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(400)
        rd = page.locator(".rw-ref-desc").first
        check("No description" in rd.inner_text(), f"empty description not flagged: {rd.inner_text()!r}")
        rd.click()
        page.wait_for_timeout(400)
        ta = page.locator("textarea[data-help='assets.description']")
        ta.fill("dark storm clouds rolling in over a grey sea")
        ta.press("Tab")
        page.wait_for_timeout(400)
        uses = page.inner_text("[data-help='assets.description.uses']")
        check("scene 05" in uses, f"uses box: {uses!r}")
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(400)
        check("dark storm clouds" in page.locator(".rw-ref-desc").first.inner_text(), "scene reference does not show the new description")
        # Mara's anchor P1: her own description wins; once it is cleared, P1's is used
        page.click(".rw-tab:has-text('Assets')")
        page.wait_for_timeout(300)
        page.locator(".rw-asset-card:has-text('Mara — portrait')").click()
        page.wait_for_timeout(300)
        ta = page.locator("textarea[data-help='assets.description']")
        ta.fill("a woman with short auburn hair and a navy pea coat")
        ta.press("Tab")
        page.wait_for_timeout(400)
        check("Not used for Mara" in page.inner_text("[data-help='assets.description.uses']"), "anchor note missing while Mara has her own description")
        page.screenshot(path=str(shots / "v034_uses.png"))
        page.locator("[data-help='assets.description.uses'] button:has-text('Mara')").first.click()
        page.wait_for_timeout(400)
        cd = page.locator("textarea[data-help='cast.description']")
        cd.fill("")
        cd.press("Tab")
        page.wait_for_timeout(400)
        check(page.locator("[data-help='cast.description.fromAnchor']").count() == 1 and "P1" in (cd.get_attribute("placeholder") or ""), "cast tab does not show the anchor fallback")
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        page.locator(".rw-scene").nth(1).click()
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(400)
        cast_lines = page.locator("[data-help='scene.cast.description']").all_inner_texts()
        check(any(t.startswith("from P1: ") and "navy pea coat" in t for t in cast_lines), f"scene cast row: {cast_lines}")
        page.screenshot(path=str(shots / "v034_scene.png"))
        browser.close()
    httpd.shutdown()

    for e in errors:
        print("console:", e)
    for f in failures:
        print("FAIL:", f)
    print("ok" if not (errors or failures) else f"{len(failures)} failures, {len(errors)} errors")
    return 1 if errors or failures else 0


if __name__ == "__main__":
    sys.exit(main())
