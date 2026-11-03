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

        # ---- added 2026-11-02 v0.3.5 ----
        # The latent preview shows only in the Render tab, in a small window, and goes away after the run.
        page.evaluate("""() => { const h = window.__host, c = document.createElement('canvas'); c.width = 42; c.height = 24;
          const g = c.getContext('2d'); const gr = g.createLinearGradient(0, 0, 42, 24); gr.addColorStop(0, '#203a5a'); gr.addColorStop(1, '#c8783c'); g.fillStyle = gr; g.fillRect(0, 0, 42, 24);
          h.emit('reelwright.run', { slug: 'harbor_lights', phase: 'start', targets: ['s_02'], reused: [] });
          h.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 1, step: 9, steps: 20, phase: 'sample' });
          h.emit('reelwright.preview', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 1, step: 9, steps: 20, image: c.toDataURL('image/jpeg') }); }""")
        page.wait_for_timeout(400)
        check(page.locator(".rw-run-preview").count() == 0, "latent preview shown outside the Render tab")
        page.click(".rw-tab:has-text('Render')")
        page.wait_for_timeout(400)
        pb = page.evaluate("(() => { const e = document.querySelector('.rw-run-preview img'); if (!e) return null; const r = e.getBoundingClientRect(); return [r.width, r.height, e.naturalWidth]; })()")
        check(pb is not None and pb[0] <= 220 and pb[2] == 42, f"render preview window: {pb}")
        page.screenshot(path=str(shots / "v035_preview.png"))
        page.evaluate("window.__host.emit('reelwright.run', { slug: 'harbor_lights', phase: 'end', targets: ['s_02'], reused: [] })")
        page.wait_for_timeout(300)
        check(page.locator(".rw-run-preview").count() == 0, "preview stayed after the run ended")

        # ---- added 2026-11-02 v0.3.6 ----
        # Autosaved versions: one line each, delete one, then delete all.
        page.click("button[data-help='render.versions.load']")
        page.wait_for_timeout(400)
        rows = page.locator(".rw-version")
        n0 = rows.count()
        check(n0 == 4, f"versions listed: {n0}")
        hts = page.evaluate("[...document.querySelectorAll('.rw-version-when')].map(e => e.getBoundingClientRect().height)")
        check(hts and max(hts) < 22, f"version date wraps: {hts}")
        page.locator(".rw-versions").scroll_into_view_if_needed()
        page.screenshot(path=str(shots / "v036_versions.png"))
        rows.nth(1).locator("button[data-help='render.versions.delete']").click()
        page.wait_for_timeout(200)
        rows.nth(1).locator(".rw-confirm button:has-text('Confirm')").click()
        page.wait_for_timeout(400)
        check(page.locator(".rw-version").count() == n0 - 1, "single delete did not remove a row")
        page.click("button[data-help='render.versions.deleteAll']")
        page.wait_for_timeout(200)
        page.locator(".rw-modal button:has-text('Delete all')").click()
        page.wait_for_timeout(400)
        check(page.locator(".rw-version").count() == 0 and page.locator(".rw-versions").count() == 0, "delete all left versions")

        # ---- added 2026-11-02 v0.3.8 ----
        # The preview window is one element that survives re-renders, shows every preview through a blob: URL, keeps
        # the last good picture when one can't be decoded, and never shows a broken image.
        page.evaluate("""() => { const h = window.__host;
          window.__pv = (step, w) => { const c = document.createElement('canvas'); c.width = w || 42; c.height = 24;
            const g = c.getContext('2d'); g.fillStyle = `hsl(${step * 17}, 60%, 50%)`; g.fillRect(0, 0, c.width, 24);
            h.emit('reelwright.preview', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 1, step, steps: 40, image: c.toDataURL('image/jpeg') }); };
          h.emit('reelwright.run', { slug: 'harbor_lights', phase: 'start', targets: ['s_02'], reused: [] });
          h.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 1, step: 1, steps: 40, phase: 'sample' });
          window.__pv(1); }""")
        page.wait_for_timeout(400)
        st = page.evaluate("""(() => { const e = document.querySelector('.rw-run-preview img'); if (!e) return null; e.__mark = 1;
          return { src: e.src.slice(0, 5), w: e.naturalWidth, cap: document.querySelector('.rw-run-preview figcaption').textContent }; })()""")
        check(st is not None and st["src"] == "blob:" and st["w"] == 42 and st["cap"].endswith("1/40"), f"preview through a blob: URL: {st}")
        # re-renders (progress events) keep the same element
        page.evaluate("""() => { for (let i = 2; i < 6; i++) window.__host.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 1, step: i, steps: 40, phase: 'sample' }); }""")
        page.wait_for_timeout(400)
        check(page.evaluate("document.querySelector('.rw-run-preview img')?.__mark === 1"), "preview element rebuilt on re-render")
        # a preview that can't be decoded keeps the last good one
        first = page.evaluate("document.querySelector('.rw-run-preview img').src")
        page.evaluate("""() => window.__host.emit('reelwright.preview', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 1, step: 6, steps: 40, image: 'data:image/jpeg;base64,AAAAAAAA' })""")
        page.wait_for_timeout(400)
        st = page.evaluate("""(() => { const e = document.querySelector('.rw-run-preview img');
          const f = e.closest('.rw-run-preview');
          return { same: e.src === %r, w: e.naturalWidth, failed: f.classList.contains('failed'), cap: f.querySelector('figcaption').textContent }; })()""" % first)
        check(st["same"] and st["w"] == 42 and not st["failed"] and st["cap"].endswith("1/40"), f"bad preview replaced a good one: {st}")
        # fast updates: 30 previews 15 ms apart; never broken, ends on the last one, earlier object URLs are released
        samples = page.evaluate("""async () => { const out = [];
          for (let s = 7; s <= 36; s++) { window.__pv(s, 40 + (s % 2)); await new Promise(r => setTimeout(r, 15));
            const e = document.querySelector('.rw-run-preview img'); out.push(e && e.complete && e.naturalWidth > 0 ? 1 : 0); }
          await new Promise(r => setTimeout(r, 300));
          const e = document.querySelector('.rw-run-preview img');
          return { ok: out.every(Boolean), cap: document.querySelector('.rw-run-preview figcaption').textContent, src: e.src }; }""")
        check(samples["ok"] and samples["cap"].endswith("36/40"), f"fast previews: {samples['ok']} {samples['cap']}")
        n_err = len(errors)
        revoked = page.evaluate("""async u => { try { await (await fetch(u)).blob(); return false; } catch { return true; } }""", first)
        page.wait_for_timeout(100)
        # the fetch of a released URL is expected to fail ("Failed to load resource"); that is not an editor error
        errors[n_err:] = [e for e in errors[n_err:] if "ERR_FILE_NOT_FOUND" not in e]
        check(revoked, "the first preview's object URL was never released")
        # a run whose previews can't be decoded shows a note, not a broken image
        page.evaluate("""() => { const h = window.__host;
          h.emit('reelwright.run', { slug: 'harbor_lights', phase: 'end', targets: ['s_02'], reused: [] });
          h.emit('reelwright.run', { slug: 'harbor_lights', phase: 'start', targets: ['s_02'], reused: [] });
          h.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 1, step: 1, steps: 40, phase: 'sample' });
          h.emit('reelwright.preview', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 1, step: 1, steps: 40, image: 'data:image/jpeg;base64,AAAAAAAA' }); }""")
        page.wait_for_timeout(500)
        st = page.evaluate("""(() => { const f = document.querySelector('.rw-run-preview'); if (!f) return null;
          return { failed: f.classList.contains('failed'), cap: f.querySelector('figcaption').textContent, vis: getComputedStyle(f.querySelector('img')).display, frame: f.querySelector('.rw-run-preview-frame').getBoundingClientRect().width }; })()""")
        check(st is not None and st["failed"] and "could not be decoded" in st["cap"] and st["vis"] == "none" and st["frame"] > 150, f"undecodable preview: {st}")
        page.locator(".rw-run-preview").scroll_into_view_if_needed()
        page.screenshot(path=str(shots / "v038_preview_failed.png"))
        page.evaluate("window.__host.emit('reelwright.run', { slug: 'harbor_lights', phase: 'end', targets: ['s_02'], reused: [] })")
        page.wait_for_timeout(300)
        check(page.locator(".rw-run-preview").count() == 0, "preview stayed after the run ended (v0.3.8)")

        # ---- added 2026-11-02 v0.3.9 ----
        # A frame from VideoHelperSuite's animated previews (24 header bytes, then the JPEG) is shown, not "could not be decoded".
        st = page.evaluate("""async () => { const h = window.__host;
          h.emit('reelwright.run', { slug: 'harbor_lights', phase: 'start', targets: ['s_02'], reused: [] });
          h.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_02', pass: 1, passes: 1, step: 3, steps: 6, phase: 'sample' });
          const c = document.createElement('canvas'); c.width = 46; c.height = 26; c.getContext('2d').fillRect(0, 0, 46, 26);
          const jpeg = await new Promise(r => c.toBlob(r, 'image/jpeg'));
          const head = new Uint8Array(24); head[3] = 1; head[7] = 2; head[8] = 2; head[9] = 0x31; head[10] = 0x32;
          window.__editor.showComfyPreview(new Blob([head, jpeg], { type: 'image/jpeg' }));
          await new Promise(r => setTimeout(r, 500));
          const f = document.querySelector('.rw-run-preview');
          return f && { failed: f.classList.contains('failed'), w: f.querySelector('img').naturalWidth, cap: f.querySelector('figcaption').textContent }; }""")
        check(st is not None and not st["failed"] and st["w"] == 46 and st["cap"].endswith("3/6"), f"VHS-style preview frame: {st}")
        page.evaluate("window.__host.emit('reelwright.run', { slug: 'harbor_lights', phase: 'end', targets: ['s_02'], reused: [] })")

        # ---- added 2026-11-03 v0.4.0 ----
        # Files tab: a tree of everything on disk; select, delete, quick selections, guards.
        page.wait_for_timeout(300)
        page.click(".rw-tab:has-text('Files')")
        page.wait_for_selector(".rw-ftree-row")
        rows = lambda: page.evaluate("[...document.querySelectorAll('.rw-ftree-row')].map(r => r.dataset.id)")
        row = lambda rid: f".rw-ftree-row[data-id='{rid}']"
        first = rows()
        check(first[0] == "p:harbor_lights" and "o:reelwright/harbor_lights/scenes" in first and "p:lighthouse_test" in first, f"files tree: {first[:4]}")
        check(page.locator(row("p:harbor_lights") + " .rw-ftree-flag").first.inner_text() == "open", "current project not flagged")
        # open scene 03: an unlisted take, the starred one and two more
        s3 = "o:reelwright/harbor_lights/scenes/s_03"
        page.click(row(s3) + " .rw-ftree-caret")
        page.wait_for_timeout(200)
        takes3 = [r for r in rows() if r.startswith(s3 + "/takes/") and r.count("/") == 5]
        check(takes3[0] == s3 + "/takes/v4" and sorted(takes3[1:]) == [s3 + "/takes/v1", s3 + "/takes/v2", s3 + "/takes/v3"], f"scene 03 takes: {takes3}")
        check(page.locator(row(s3 + "/takes/v3") + " .rw-ftree-flag").first.inner_text().startswith("★"), "starred take not flagged")
        # ticking the scene covers its takes
        page.click(row(s3) + " .rw-ftree-check")
        page.wait_for_timeout(150)
        st = page.evaluate(f"""(() => {{ const c = document.querySelector("{row(s3 + '/takes/v2')} .rw-ftree-check"); return [c.checked, c.disabled]; }})()""")
        check(st == [True, True], f"scene tick covers takes: {st}")
        page.click(row(s3) + " .rw-ftree-check")
        page.wait_for_timeout(150)
        # quick selection: unstarred takes (no starred one)
        page.click("button[data-help='files.pick.takes']")
        page.wait_for_timeout(200)
        st = page.evaluate(f"""(() => {{ const q = id => document.querySelector(`.rw-ftree-row[data-id="${{id}}"] .rw-ftree-check`)?.checked;
          return {{ v3: q("{s3}/takes/v3"), v2: q("{s3}/takes/v2"), v4: q("{s3}/takes/v4"), label: document.querySelector("button[data-help='files.deleteSelected']").innerText }}; }})()""")
        check(st["v3"] is False and st["v2"] and st["v4"] and st["label"].startswith("Delete "), f"unstarred pick: {st}")
        page.screenshot(path=str(shots / "v040_files_pick.png"))
        page.click("button[data-help='files.deleteSelected']")
        page.wait_for_timeout(200)
        msg = page.locator(".rw-modal-msg").inner_text()
        check("removed for good" in msg, f"delete confirm text: {msg!r}")
        page.locator(".rw-modal button:has-text('Delete from disk')").click()
        page.wait_for_timeout(700)
        left = [r for r in rows() if r.startswith(s3 + "/takes/") and r.count("/") == 5]
        check(left == [s3 + "/takes/v3"], f"after deleting unstarred takes: {left}")
        check(page.evaluate("window.__editor.project.ui.tab") == "files", "tab changed after delete")
        # one cut by its bin
        page.click(row("o:reelwright/harbor_lights/cuts") + " .rw-ftree-caret")
        page.wait_for_timeout(200)
        page.click(row("cut:harbor_lights:harbor_lights_cut_v1") + " button[data-help='files.delete']")
        page.wait_for_timeout(200)
        page.locator(".rw-modal button:has-text('Delete from disk')").click()
        page.wait_for_timeout(600)
        check("cut:harbor_lights:harbor_lights_cut_v1" not in rows() and "cut:harbor_lights:harbor_lights_cut_v2" in rows(), "cut v1 not deleted")
        # an asset this project uses: deleted from disk and removed from the project
        page.click(row("i:reelwright/harbor_lights") + " .rw-ftree-caret")
        page.wait_for_timeout(200)
        asset_row = page.evaluate("""(() => { const r = [...document.querySelectorAll('.rw-ftree-row.k-asset')].find(x => x.querySelector('.rw-ftree-flag')?.innerText === 'used'); return r?.dataset.id; })()""")
        aid = page.evaluate("id => window.__editor.project.assets.find(a => 'i:' + a.file === id)?.id", asset_row)
        page.click(row(asset_row) + " button[data-help='files.delete']")
        page.wait_for_timeout(200)
        msg = page.locator(".rw-modal-msg").inner_text()
        check("removed from it too" in msg, f"asset delete warns: {msg!r}")
        page.locator(".rw-modal button:has-text('Delete from disk')").click()
        page.wait_for_timeout(700)
        check(aid and not page.evaluate("id => window.__editor.project.assets.some(a => a.id === id)", aid), f"asset {aid} still in the project")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(page.evaluate("id => window.__editor.project.assets.some(a => a.id === id)", aid), "undo did not bring the asset entry back")
        # the open project can't go as a whole, another one can
        check(page.locator(row("p:harbor_lights") + " button[data-help='files.delete']").count() == 0, "open project has a delete button")
        page.click(row("p:lighthouse_test") + " button[data-help='files.delete']")
        page.wait_for_timeout(200)
        check("Whole project" in page.locator(".rw-modal-msg").inner_text(), "project delete note missing")
        page.locator(".rw-modal button:has-text('Delete from disk')").click()
        page.wait_for_timeout(600)
        check("p:lighthouse_test" not in rows(), "other project not deleted")
        # while this project renders, its rows are locked
        page.evaluate("window.__host.emit('reelwright.run', { slug: 'harbor_lights', phase: 'start', targets: ['s_07'], reused: [] })")
        page.wait_for_timeout(300)
        st = page.evaluate(f"""(() => [document.querySelector("{row('o:reelwright/harbor_lights/cuts')} .rw-ftree-check").disabled, !!document.querySelector('.rw-files-tab .rw-banner')])()""")
        check(st == [True, True], f"render lock: {st}")
        page.evaluate("window.__host.emit('reelwright.run', { slug: 'harbor_lights', phase: 'end', targets: ['s_07'], reused: [] })")
        page.wait_for_timeout(300)
        page.click("button[data-help='files.order.size']")
        page.click("button[data-help='files.expandAll']")
        page.wait_for_timeout(300)
        page.screenshot(path=str(shots / "v040_files.png"))

        # ---- added 2026-11-03 v0.4.1 ----
        # Files tab preview: a take previews its video in a pane that survives re-renders; files open on click.
        page.click("button[data-help='files.collapseAll']")
        page.click("button[data-help='files.order.natural']")
        page.wait_for_timeout(200)
        page.click(row("p:harbor_lights") + " .rw-ftree-caret")
        page.wait_for_timeout(150)
        page.click(row("o:reelwright/harbor_lights/scenes") + " .rw-ftree-caret")
        page.wait_for_timeout(150)
        s2 = "o:reelwright/harbor_lights/scenes/s_02"
        page.click(row(s2) + " .rw-ftree-caret")
        page.wait_for_timeout(200)
        take = [r for r in rows() if r.startswith(s2 + "/takes/") and r.count("/") == 5][0]
        page.click(row(take) + " button[data-help='files.preview.show']")
        page.wait_for_timeout(300)
        st = page.evaluate("""(() => { const v = document.querySelector('.rw-fprev video'); if (!v) return null; v.__mark = 1;
          return { head: document.querySelector('.rw-fprev-head b').innerText, path: document.querySelector('.rw-fprev-meta div').innerText }; })()""")
        check(st is not None and st["head"].endswith(".mp4") and st["path"].startswith("output/reelwright/harbor_lights/scenes/s_02"), f"take preview: {st}")
        page.evaluate("""() => { for (let i = 0; i < 5; i++) window.__host.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_07', pass: 1, passes: 3, step: i, steps: 28, phase: 'sample' }); }""")
        page.wait_for_timeout(300)
        check(page.evaluate("document.querySelector('.rw-fprev video')?.__mark === 1"), "preview video was rebuilt by a re-render")
        page.click(row(take) + " .rw-ftree-caret")
        page.wait_for_timeout(200)
        page.locator(row(take + "/first.png") + " .rw-ftree-label").click()
        page.wait_for_timeout(300)
        check(page.locator(".rw-fprev img.rw-fprev-media").count() == 1, "picture preview missing")
        page.click(row("o:reelwright/harbor_lights/cuts") + " .rw-ftree-caret")
        page.wait_for_timeout(200)
        cut = [r for r in rows() if r.startswith("cut:")][1]
        page.click(row(cut) + " .rw-ftree-caret")
        page.wait_for_timeout(200)
        srt = [r for r in rows() if r.endswith(".srt")][0]
        page.locator(row(srt) + " .rw-ftree-label").click()
        page.wait_for_timeout(400)
        check(page.locator(".rw-fprev pre.rw-fprev-text").count() == 1, "text preview missing")
        check("-->" in page.locator(".rw-fprev pre.rw-fprev-text").inner_text(), "srt preview does not show the subtitles")  # added 2026-11-03 v0.4.1
        page.screenshot(path=str(shots / "v041_files_preview.png"))
        page.click("button[data-help='files.preview.close']")
        page.wait_for_timeout(200)
        check(page.locator(".rw-fprev").count() == 0, "preview did not close")

        # Typing while the editor re-renders keeps every character in place (was "Sencer" -> "Seernc").
        page.evaluate("""() => { window.__tick = setInterval(() => window.__host.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_07', pass: 1, passes: 3, step: 3, steps: 28, phase: 'sample' }), 60); }""")
        page.click(".rw-tab:has-text('Cast')")
        page.wait_for_timeout(300)
        name = page.locator("input[data-help='cast.name']").first
        name.click()
        name.press("Control+a")
        page.keyboard.type("Sencer", delay=80)
        page.wait_for_timeout(150)
        typed = page.evaluate("document.activeElement.value")
        page.keyboard.press("Enter")
        page.evaluate("clearInterval(window.__tick)")
        page.wait_for_timeout(200)
        check(typed == "Sencer" and page.evaluate("window.__editor.project.cast[0].name") == "Sencer", f"typing during re-renders: {typed!r}")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(200)

        # Anchor packing: Auto / One sheet / Separate, with the sheet as the renderer builds it.
        page.click("button[data-help='cast.anchors.sheet.off']")
        page.wait_for_timeout(200)
        check(page.evaluate("window.__editor.project.cast[0].pack_sheet") is False and page.locator(".rw-sheet-img").count() == 0, "separate anchors")
        page.click("button[data-help='cast.anchors.sheet.on']")
        page.wait_for_timeout(200)
        src = page.evaluate("document.querySelector('.rw-sheet-img')?.getAttribute('src') || ''")
        check(page.evaluate("window.__editor.project.cast[0].pack_sheet") is True and src != "", "one sheet shows the built sheet")
        page.click("button[data-help='cast.anchors.sheet.auto']")
        page.wait_for_timeout(200)
        note = page.locator(".rw-sheet-row .rw-dim.small").first.inner_text()
        check(page.evaluate("window.__editor.project.cast[0].pack_sheet") == "auto" and "9 pictures" in note, f"auto packing note: {note!r}")
        size = page.locator("[data-help='cast.anchors.size']").inner_text()
        check("px" in size, f"anchor size note: {size!r}")
        page.screenshot(path=str(shots / "v041_cast_sheet.png"))

        # ---- added 2026-11-03 v0.4.2 ----
        # LLM limits in Global; a long script imported in parts: progress, Stop/Continue, a cut part split in two,
        # a failed part retried on its own, the premise sent with every part, cast merged across parts.
        page.evaluate("() => clearInterval(window.__tick)")
        page.click(".rw-tab:has-text('Global')")
        page.wait_for_timeout(300)
        for hid in ("timeout", "maxWait", "retries", "context", "importPart", "importTokens"):
            check(page.locator(f"input[data-help='global.llm.{hid}']").count() == 1, f"limit field {hid} missing")
        part = page.locator("input[data-help='global.llm.importPart']")
        part.fill("600")
        part.press("Tab")
        page.click("button[data-help='global.llm.importThinking.off']")
        page.wait_for_timeout(200)
        llm_cfg = project(page)["global"]["llm"]
        check(llm_cfg["import_part_chars"] == 600 and llm_cfg["import_thinking"] == "off" and llm_cfg["timeout_s"] == 120, f"limits not saved: {llm_cfg}")
        page.locator("[data-help='global.llm.limits']").first.scroll_into_view_if_needed()
        page.screenshot(path=str(shots / "v042_limits.png"))
        rows = []
        for i in range(1, 13):
            tag = " CUT" if i == 5 else " FAILONCE" if i == 10 else ""
            rows.append(f"| {i:02d} | 00:{i:02d}:00 | 8.00 | Verse | Ada walks past grave number {i} in the mist, candles burning{tag} |")
        script = "Ada is a young necromancer singing the song from <audio 1>. No dialogue.\n\n" + "\n".join(rows)
        page.fill("textarea[data-help='global.script.text']", script)
        page.click("button[data-help='global.script.run']")
        page.wait_for_timeout(250)
        check(page.locator(".rw-script-part.run").count() == 1, "no running part shown")
        line = page.locator(".rw-script-part.run span").last.inner_text()
        check("tokens" in line, f"progress line: {line!r}")
        page.screenshot(path=str(shots / "v042_import_running.png"))
        page.click("button[data-help='global.script.stop']")
        page.wait_for_timeout(700)
        check(page.locator(".rw-script-part.stopped").count() == 1 and page.locator("button[data-help='global.script.retry']").count() == 1, "stop did not leave a Continue button")
        check("Continue" in page.locator("button[data-help='global.script.retry']").inner_text(), "button should say Continue")
        page.click("button[data-help='global.script.retry']")
        for _ in range(80):
            page.wait_for_timeout(250)
            if page.evaluate("!window.__editor.eph?.scriptDraft?.busy && document.querySelector(\"button[data-help='global.script.retry']\") !== null"):
                break
        failed = page.locator(".rw-script-part.failed")
        check(failed.count() == 1 and "Stall timeout" in failed.inner_text(), "the FAILONCE part should have failed")
        check("Retry failed parts" in page.locator("button[data-help='global.script.retry']").inner_text(), "retry label")
        check(page.locator(".rw-script-parts .rw-note").count() == 1 and "split in two" in page.locator(".rw-script-parts .rw-note").inner_text(), "split note missing")
        page.screenshot(path=str(shots / "v042_import_failed.png"))
        page.click("button[data-help='global.script.retry']")
        for _ in range(40):
            page.wait_for_timeout(250)
            if page.evaluate("!window.__editor.eph?.scriptDraft?.busy"):
                break
        draft = page.evaluate("(() => { const d = window.__editor.eph.scriptDraft; return { parts: d.parts.map(p => p.status), scenes: d.scenes.map(s => s.summary), cast: d.cast.map(c => [c.name, c.description, c.speaker]) }; })()")
        check(all(st == "done" for st in draft["parts"]) and len(draft["parts"]) >= 4, f"parts after retry: {draft['parts']}")
        check(len(draft["scenes"]) == 12 and draft["scenes"][0].startswith("Ada walks past grave number 1 ") and "number 12 " in draft["scenes"][-1], f"scenes in order: {len(draft['scenes'])}")
        names = [c[0] for c in draft["cast"]]
        check(names.count("Ada") == 1 and dict((c[0], c[1]) for c in draft["cast"])["Ada"] == "A young necromancer.", f"cast merge: {draft['cast']}")
        calls = page.evaluate("window.__host.scriptCalls.filter(c => c.rows > 0)")
        check(all(c["notes"].startswith("Ada is a young necromancer") for c in calls) and all(c["rows"] >= 1 for c in calls), "premise not sent with every part")
        check("Ada" in calls[-1]["known"], f"later parts should know the cast: {calls[-1]}")
        page.screenshot(path=str(shots / "v042_import_done.png"))
        n_before = len(project(page)["scenes"])
        page.locator("[data-help='global.script.mode'] button").filter(has_text="At the end").first.click()
        page.click("button[data-help='global.script.apply']")
        page.wait_for_timeout(400)
        check(len(project(page)["scenes"]) == n_before + 12, "imported scenes not added")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)

        # Rewrite shows what the LLM is doing and can be stopped.
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(300)
        page.click("button[data-help='scene.rewrite.run']")
        page.wait_for_timeout(250)
        busy = page.locator(".rw-llm-busy")
        check(busy.count() == 1 and ("tokens" in busy.inner_text() or "waiting" in busy.inner_text()), "rewrite progress line missing")
        page.click("button[data-help='scene.rewrite.stop']")
        page.wait_for_timeout(500)
        check(page.locator(".rw-llm-busy").count() == 0 and page.evaluate("!window.__editor.eph.rewrite"), "rewrite did not stop")
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
