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
            print("FAIL:", msg, flush=True)  # added 2026-11-03 v0.6.0: shown at once (a later crash hides the summary)

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
        # v0.6.0: undo keeps the view (the drag selected scene 01); select scene 03 again for the checks below
        check(project(page)["ui"]["selected"] == "s_01", f"undo changed the selection: {project(page)['ui']['selected']}")
        page.evaluate("window.__editor.store.update(p => { p.ui.selected = 's_03'; p.ui.playhead = 21.375; }, { history: false, plan: false })")
        page.wait_for_timeout(200)

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
        # v0.6.0 (F2b): deleting a version asks in a dialog (the inline bar vanished on any re-render)
        rows.nth(1).locator("button[data-help='render.versions.delete']").click()
        page.wait_for_timeout(200)
        check(page.locator(".rw-confirm").count() == 0 and page.locator(".rw-modal").count() == 1, "version delete did not open a dialog")
        page.locator(".rw-modal button:has-text('Delete version')").click()
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
        cut = [r for r in rows() if r.startswith("cut:") and not r.endswith("_draft")][1]  # v0.6.0: the mock lists a draft cut first
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
        # [OLD 2026-11-03 v0.5.0->v0.5.1] the limit fields were always shown; now both groups fold (closed by default)
        check(page.locator("input[data-help='global.llm.timeout']").count() == 0, "Limits should start folded")
        check("stall 120 s" in page.locator("button.rw-fold[data-help='global.llm.limits']").inner_text(), "folded Limits shows no summary")
        page.click("button.rw-fold[data-help='global.llm.limits']")
        page.click("button.rw-fold[data-help='global.llm.import']")
        page.wait_for_timeout(200)
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

        # ---- added 2026-11-03 v0.4.3 ----
        # Shots after the end of a scene: shot lengths beside the start, Lengthen / Fit into, and the Issues button.
        saved = json.dumps(project(page))
        bad = json.loads(saved)
        sc = bad["scenes"][0]
        sc["duration"] = 30.0
        sc["shots"] = [{"id": f"h_x{i}", "t": t, "camera": "", "text": f"shot {i}"} for i, t in enumerate([0, 8.42, 16.59, 24.76, 33.76, 41.81, 50.81, 61.81])]
        sc["dialogue"] = []
        bad["scenes"][1]["shots"] = [{"id": "h_y1", "t": 0, "camera": "", "text": "a"}, {"id": "h_y2", "t": bad["scenes"][1]["duration"] + 3, "camera": "", "text": "b"}]
        bad["ui"]["selected"] = sc["id"]
        page.evaluate("j => window.__editor.load(j)", json.dumps(bad))
        page.wait_for_timeout(400)
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(300)
        lens = page.locator("[data-help='scene.shots.length']").all_inner_texts()
        check(lens[:4] == ["for 8.42 s", "for 8.17 s", "for 8.17 s", "for 5.24 s"] and lens[4:] == ["after the end"] * 4, f"shot lengths: {lens}")
        note = page.locator(".rw-overrun")
        check(note.count() == 1 and "4 shots start after the scene ends (30.00 s)" in note.inner_text(), f"overrun note: {note.inner_text() if note.count() else None}")
        page.screenshot(path=str(shots / "v043_overrun.png"))
        page.click("button[data-help='scene.shots.lengthen']")
        page.wait_for_timeout(300)
        d = project(page)["scenes"][0]["duration"]
        check(abs(d - 70.25) < 1e-6 and page.locator(".rw-overrun").count() == 0, f"lengthen: {d}")
        lens = page.locator("[data-help='scene.shots.length']").all_inner_texts()
        check(lens[-1] == "for 8.44 s · end", f"last shot runs to the end: {lens[-1]}")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(project(page)["scenes"][0]["duration"] == 30.0, "undo lengthen")
        page.click("button[data-help='scene.shots.squeeze']")
        page.wait_for_timeout(300)
        p0 = project(page)["scenes"][0]
        check(p0["duration"] == 30.0 and max(x["t"] for x in p0["shots"]) < 30 and page.locator(".rw-overrun").count() == 0, f"fit into: {[x['t'] for x in p0['shots']]}")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        page.click("button[data-help='app.issues']")
        page.wait_for_timeout(300)
        fix = page.locator(".rw-drawer-fix")
        check(fix.count() == 1 and "2 scenes have" in fix.inner_text(), f"issues fix row: {fix.inner_text() if fix.count() else None}")
        page.screenshot(path=str(shots / "v043_issues.png"))
        page.click("button[data-help='app.issues.fitShots']")
        page.wait_for_timeout(300)
        pj = project(page)
        check(pj["scenes"][0]["duration"] == 70.25 and pj["scenes"][1]["duration"] > pj["scenes"][1]["shots"][-1]["t"] and page.locator(".rw-drawer-fix").count() == 0, "lengthen all")
        page.click("button[data-help='app.issues']")
        page.evaluate("j => window.__editor.load(j)", saved)
        page.wait_for_timeout(300)

        # ---- added 2026-11-03 v0.5.0 ----
        # Soundtrack lanes: add a track, move and trim it on its lane, edit it in the inspector, scene sound in the merge.
        live = lambda: page.evaluate("JSON.parse(JSON.stringify(window.__editor.project))")
        saved = json.dumps(live())
        # the demo project's merge score became a looping track on load; start from no soundtrack
        base = json.loads(saved)
        check([t["id"] for t in base["soundtrack"]] == ["t_score"] and base["soundtrack"][0]["loop"] and not base["soundtrack"][0]["sync"],
              f"demo score not migrated: {base['soundtrack']}")
        base["soundtrack"] = []
        base["global"]["merge"]["scene_audio"] = {"mix": False, "volume_db": -12.0}
        page.evaluate("j => window.__editor.load(j)", json.dumps(base))
        page.wait_for_timeout(300)
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        pj = live()
        z = pj["ui"]["zoom"] or 22
        blocks = page.locator(".rw-scene")
        for _ in range(5):  # a re-render (a toast expiring, a plan answer) can replace a block while it is measured
            b1, b2 = blocks.nth(1).bounding_box(), blocks.nth(2).bounding_box()
            if b1 and b2:
                break
            page.wait_for_timeout(200)
        check(pj["scenes"][2]["start"]["mode"] == "tail" and abs(b1["x"] + b1["width"] + 2 - b2["x"]) < 1.5,
              f"a tail scene's block starts where the scene before ends: {b1}, {b2}")
        check(page.locator(".rw-lane.track.add").count() == 1, "no Soundtrack lane")
        page.click("button.rw-track-add")
        page.wait_for_timeout(200)
        page.locator(".rw-ctx-item:has-text('A3')").click()
        page.wait_for_timeout(500)
        st = live()["soundtrack"]
        check(len(st) == 1 and st[0]["asset"] == "a_a3" and st[0]["start"] == 0 and st[0]["sync"] and st[0]["mix"], f"track not added: {st}")
        check(page.locator(".rw-track-insp").count() == 1, "track inspector not shown")
        page.wait_for_timeout(300)
        check(page.locator(".rw-track-clip .rw-wave").count() >= 1, "no waveform on the clip")
        sc = page.evaluate("(() => { const r = document.querySelector('.rw-root'); const b = r.getBoundingClientRect(); return b.width / r.offsetWidth; })()")
        clip = page.locator(".rw-track-clip").first
        bx = clip.bounding_box()
        page.keyboard.down("Alt")
        page.mouse.move(bx["x"] + bx["width"] / 2, bx["y"] + bx["height"] / 2)
        page.mouse.down()
        page.mouse.move(bx["x"] + bx["width"] / 2 + 2 * z * sc, bx["y"] + bx["height"] / 2, steps=8)
        page.mouse.up()
        page.keyboard.up("Alt")
        page.wait_for_timeout(300)
        t = live()["soundtrack"][0]
        check(abs(t["start"] - 2.0) < 0.05, f"move: start {t['start']}")
        # v0.6.0 (F2a): the render after the drop can replace the clip while it is measured (bounding_box() gave None)
        bx = None
        for _ in range(10):
            bx = page.locator(".rw-track-clip").first.bounding_box()
            if bx:
                break
            page.wait_for_timeout(150)
        page.keyboard.down("Alt")
        page.mouse.move(bx["x"] + 2, bx["y"] + 10)
        page.mouse.down()
        page.mouse.move(bx["x"] + 2 + 1 * z * sc, bx["y"] + 10, steps=6)
        page.mouse.up()
        page.mouse.move(bx["x"] + bx["width"] - 2, bx["y"] + 10)
        page.mouse.down()
        page.mouse.move(bx["x"] + bx["width"] - 2 - 2 * z * sc, bx["y"] + 10, steps=6)
        page.mouse.up()
        page.keyboard.up("Alt")
        page.wait_for_timeout(300)
        t = live()["soundtrack"][0]
        check(abs(t["in"] - 1.0) < 0.06 and abs(t["start"] - 3.0) < 0.06, f"trim start: in {t['in']} start {t['start']}")
        check(abs(t["out"] - 7.5) < 0.1, f"trim end: out {t['out']}")
        page.screenshot(path=str(shots / "v050_track.png"))
        page.locator(".rw-track-insp input[data-key^='trk-volume_db']").fill("-6")
        page.locator(".rw-track-insp input[data-key^='trk-volume_db']").press("Enter")
        page.wait_for_timeout(200)
        page.locator(".rw-track-insp button.rw-toggle[data-help='timeline.track.loopToggle']").click()
        page.wait_for_timeout(300)
        t = live()["soundtrack"][0]
        check(t["volume_db"] == -6 and t["loop"], f"inspector edits: {t}")
        # v0.6.0 (F2a): the repeats are one pattern element that ends with the film
        ghost = page.locator(".rw-track-clip.ghost.pattern")
        check(ghost.count() == 1 and int(ghost.first.get_attribute("data-repeats") or 0) > 3, "loop repeats not drawn")
        gb = ghost.first.bounding_box() if ghost.count() else None
        add_b = page.locator(".rw-add-ghost").bounding_box()
        check(gb is not None and gb["x"] + gb["width"] <= add_b["x"] - 8 * sc + 1.5, f"loop repeats drawn past the film end: {gb} vs {add_b}")
        page.screenshot(path=str(shots / "v050_loop.png"))
        page.locator(".rw-track-insp button.rw-toggle[data-help='timeline.track.loopToggle']").click()
        page.wait_for_timeout(200)
        # the scene inspector shows that the song is sent, and the Scene tab's budget says so
        page.locator(".rw-scene").nth(0).click()
        page.wait_for_timeout(300)
        check(page.locator(".rw-insp [data-help='timeline.chip.song']").count() == 1, "SONG chip missing in the scene inspector")
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(300)
        check(page.locator("[data-help='scene.budget.song']").count() == 1, "budget does not mention the song")
        # the autocomplete offers @soundtrack
        ta = page.locator(".rw-psec").nth(1).locator("textarea")
        ta.click()
        ta.press("End")
        ta.type(" to @sou", delay=20)
        page.wait_for_timeout(200)
        check(page.locator(".rw-ac.on .rw-ac-item:has-text('@soundtrack')").count() == 1, "@soundtrack not offered")
        page.keyboard.press("Escape")
        # Merge card: scene sound under the soundtrack, off by default
        page.click(".rw-tab:has-text('Render')")
        page.wait_for_timeout(300)
        check(page.locator("[data-help='render.merge.locked']").count() == 1, "locked-timing note missing")
        tg = page.locator(".rw-merge [data-help='render.merge.sceneAudio'] .rw-toggle, .rw-merge .rw-toggle[data-help='render.merge.sceneAudio']").first
        check(not live()["global"]["merge"]["scene_audio"]["mix"], "scene sound should be off by default")
        tg.click()
        page.wait_for_timeout(300)
        check(live()["global"]["merge"]["scene_audio"]["mix"], "scene sound toggle")
        page.screenshot(path=str(shots / "v050_merge.png"))
        page.locator(".rw-root").focus()
        page.keyboard.press("Control+z")
        page.wait_for_timeout(200)
        check(not live()["global"]["merge"]["scene_audio"]["mix"], "undo scene sound")
        # playback: the take is silent under the song (scene sound off)
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        page.locator(".rw-root").focus()
        page.keyboard.press("Home")
        page.keyboard.press(" ")
        page.wait_for_timeout(500)
        vol = page.evaluate("document.querySelector('.rw-mon-video').volume")
        page.keyboard.press(" ")
        check(vol == 0, f"take should be muted under the soundtrack: {vol}")
        # delete and undo, then an old project's score becomes a looping track
        page.locator(".rw-track-clip").first.click()
        page.wait_for_timeout(200)
        page.locator(".rw-track-insp button[data-help='timeline.track.delete']").click()
        page.wait_for_timeout(200)
        check(live()["soundtrack"] == [], "track not deleted")
        page.locator(".rw-root").focus()
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(len(live()["soundtrack"]) == 1, "undo did not bring the track back")
        old = json.loads(json.dumps(base))
        old.pop("soundtrack", None)
        old["global"]["merge"]["score"] = {"asset": "a_a1", "volume_db": -9, "duck": True}
        page.evaluate("j => window.__editor.load(j)", json.dumps(old))
        page.wait_for_timeout(400)
        st = live()["soundtrack"]
        check(len(st) == 1 and st[0]["asset"] == "a_a1" and st[0]["loop"] and not st[0]["sync"] and st[0]["volume_db"] == -9,
              f"score migration: {st}")
        check(live()["global"]["merge"]["score"]["asset"] == "", "score not cleared")
        page.evaluate("j => window.__editor.load(j)", saved)
        page.wait_for_timeout(300)

        # ---- added 2026-11-03 v0.5.1 ----
        # A click on a button the render rebuilds (Add scene) used to leave focus on the page body, so Ctrl+Z went to
        # ComfyUI instead of the editor. Focus stays in the editor, and Ctrl+Z undoes the edit.
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        n = len(live()["scenes"])
        page.click("button[data-help='timeline.addScene'] >> nth=0")
        page.wait_for_timeout(400)
        check(page.evaluate("document.activeElement.classList.contains('rw-root') || !!document.activeElement.closest('.rw-root')"),
              f"focus left the editor: {page.evaluate('document.activeElement.className')}")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(len(live()["scenes"]) == n, "Ctrl+Z right after Add scene did not undo it")
        page.click(".rw-tab:has-text('Global')")
        page.wait_for_timeout(300)
        check(page.evaluate("!!document.activeElement.closest('.rw-root')"), "focus left the editor after a tab click")
        fold = page.locator("button.rw-fold[data-help='global.llm.import']")
        if fold.get_attribute("aria-expanded") == "true":
            fold.click()
            page.wait_for_timeout(200)
        check(page.locator("input[data-help='global.llm.importPart']").count() == 0 and "parts of" in fold.inner_text(), "Script import did not fold")
        page.screenshot(path=str(shots / "v051_llm_folded.png"))

        # ---- added 2026-11-03 v0.6.0 (F1: editor core) ----
        in_editor_keys = "(() => { const a = document.activeElement; return !!a && a.classList.contains('rw-keys') && !!a.closest('.rw-root'); })()"
        toast_text = lambda: " | ".join(page.locator(".rw-toast").all_inner_texts())
        page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
        page.wait_for_timeout(300)

        # Combobox: Enter and Escape leave focus in the editor (not on the page), so Ctrl+Z stays the editor's.
        page.click(".rw-tab:has-text('Global')")
        page.wait_for_timeout(300)
        lang = page.locator(".rw-combo input[data-help='global.defaults.language']")
        lang.click()
        lang.fill("Fren")
        page.wait_for_timeout(150)
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        check(live()["global"]["defaults"]["language"] == "French", f"combobox pick: {live()['global']['defaults']['language']}")
        check(page.evaluate(in_editor_keys), f"focus after combobox Enter: {page.evaluate('document.activeElement.tagName + \".\" + document.activeElement.className')}")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(live()["global"]["defaults"]["language"] != "French", "Ctrl+Z after a combobox pick did not undo it")
        lang.click()
        lang.fill("Ger")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        check(page.evaluate(in_editor_keys), "focus after combobox Escape")

        # Number field: partial typing ("-", "1e") puts the stored value back instead of storing null/0.
        seed = page.locator("input[data-help='global.sampling.seed']")
        seed0 = live()["global"]["sampling"]["seed"]
        seed.click()
        seed.press("Control+a")
        page.keyboard.type("-")
        seed.press("Tab")
        page.wait_for_timeout(300)
        check(live()["global"]["sampling"]["seed"] == seed0, f"'-' changed the seed to {live()['global']['sampling']['seed']}")
        seed.click()
        seed.press("Control+a")
        page.keyboard.type("1e")
        seed.press("Tab")
        page.wait_for_timeout(300)
        check(live()["global"]["sampling"]["seed"] == seed0 and seed.input_value() == str(seed0), f"'1e' changed the seed: {live()['global']['sampling']['seed']} / {seed.input_value()!r}")

        # Confirm dialog: a delete opens with Cancel focused, so Enter cancels; Tab stays inside; Ctrl+Z does nothing;
        # Enter on the delete button deletes.
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        n = len(live()["scenes"])
        page.locator(".rw-root").focus()
        page.keyboard.press("Delete")
        page.wait_for_timeout(200)
        check(page.locator(".rw-modal").count() == 1, "Delete did not ask")
        check(page.evaluate("document.activeElement.textContent") == "Cancel", f"dialog focus: {page.evaluate('document.activeElement.textContent')!r}")
        for _ in range(5):
            page.keyboard.press("Tab")
        check(page.evaluate("!!document.activeElement.closest('.rw-modal')"), "Tab left the dialog")
        page.keyboard.down("Control")
        check(page.evaluate("document.activeElement.tagName") == "INPUT", "Ctrl in the dialog: focus is not on a field (ComfyUI would undo)")
        page.keyboard.press("z")
        page.keyboard.up("Control")
        page.wait_for_timeout(200)
        check(page.locator(".rw-modal").count() == 1 and len(live()["scenes"]) == n, "Ctrl+Z in the dialog changed something")
        page.locator(".rw-modal button:has-text('Cancel')").focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        check(page.locator(".rw-modal").count() == 0 and len(live()["scenes"]) == n, "Enter on Cancel deleted the scene")
        check(page.evaluate("!!document.activeElement.closest('.rw-root')"), "focus left the editor after the dialog")
        page.keyboard.press("Delete")
        page.wait_for_timeout(200)
        page.keyboard.press("Tab")
        check(page.evaluate("document.activeElement.textContent") == "Delete scene", f"Tab to the delete button: {page.evaluate('document.activeElement.textContent')!r}")
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        check(len(live()["scenes"]) == n - 1, "Enter on the delete button did not delete")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(len(live()["scenes"]) == n, "undo of the delete")

        # Focus helper: a clicked <video controls> and Ctrl on a focused button hand focus to the key field.
        page.evaluate("""() => { const v = document.createElement('video'); v.controls = true; v.tabIndex = 0; v.id = 'rw-test-video';
          document.querySelector('.rw-root .rw-body').prepend(v); v.focus(); }""")
        page.wait_for_timeout(100)
        check(page.evaluate(in_editor_keys), "focus stayed on a <video controls>")
        page.evaluate("document.getElementById('rw-test-video')?.remove()")
        page.evaluate("document.querySelector('.rw-tab').focus()")
        page.keyboard.down("Control")
        check(page.evaluate(in_editor_keys), "Ctrl on a focused button did not move focus to the key field")
        page.keyboard.up("Control")

        # Split keeps the film's length: the second half (last_frame) is one frame longer, its shots move by cut - 1 frame,
        # and it gets its own seed number.
        page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
        page.wait_for_timeout(300)
        total = lambda: page.evaluate("import('../web/rw/model.js').then(m => m.sceneStarts(window.__editor.project).total)")
        t0 = total()
        sp = live()
        # a scene that the next one does not continue (a later re-anchored tail would change the length by design)
        cands = [k for k, x in enumerate(sp["scenes"]) if x["duration"] >= 2 and (k + 1 == len(sp["scenes"]) or sp["scenes"][k + 1]["start"]["mode"] == "fresh")]
        i = cands[0] if cands else len(sp["scenes"]) - 1
        sid = sp["scenes"][i]["id"]
        sc = sp["scenes"][i]
        start = page.evaluate("import('../web/rw/model.js').then(m => m.sceneStarts(window.__editor.project).starts[%r])" % sid)
        at = round(sc["duration"] / 2 * 24) / 24
        page.evaluate("window.__editor.actions.splitScene(%r, %r)" % (sid, at))
        page.wait_for_timeout(300)
        sp2 = live()
        a, b = sp2["scenes"][i], sp2["scenes"][i + 1]
        check(round(total() * 24) == round(t0 * 24), f"split changed the length: {t0} -> {total()}")
        check(b["start"]["mode"] == "last_frame" and round((a["duration"] + b["duration"]) * 24) == round(sc["duration"] * 24) + 1, f"split halves: {a['duration']} + {b['duration']} of {sc['duration']}")
        later_shots = [x["t"] for x in sc["shots"] if x["t"] >= at]
        check(all(abs(y["t"] - (x - at + 1 / 24)) < 1e-3 for x, y in zip(later_shots, b["shots"])), f"shot times in the second half: {[y['t'] for y in b['shots']]}")
        if "seed_n" in a:
            check(b.get("seed_n") not in [x.get("seed_n") for x in sp2["scenes"] if x["id"] != b["id"]], f"split seed number reused: {b.get('seed_n')}")
        page.evaluate("window.__editor.actions.duplicateScene(%r)" % sid)
        page.wait_for_timeout(300)
        sp3 = live()
        if "seed_n" in a:
            ns = [x.get("seed_n") for x in sp3["scenes"]]
            check(len(set(ns)) == len(ns), f"duplicate reused a seed number: {ns}")
        page.screenshot(path=str(shots / "v060_split.png"))

        # Named history: steps carry labels; the History menu jumps to one; the view (tab) is not part of it.
        labels = [x["label"] for x in page.evaluate("window.__editor.store.history()")]
        check(labels[-2:] == ["Split scene", "Duplicate scene"], f"history labels: {labels}")
        page.click(".rw-tab:has-text('Global')")
        page.wait_for_timeout(200)
        page.click("button[data-help='app.history']")
        page.wait_for_timeout(200)
        items = page.locator(".rw-ctx.rw-history .rw-ctx-item").all_inner_texts()
        check(len(items) >= 3 and items[0].startswith("Duplicate scene"), f"history menu: {items[:3]}")
        page.screenshot(path=str(shots / "v060_history.png"))
        page.locator(".rw-ctx.rw-history .rw-ctx-item:has-text('Split scene')").click()
        page.wait_for_timeout(300)
        check(len(live()["scenes"]) == len(sp2["scenes"]) and live()["ui"]["tab"] == "global", f"jump to 'Split scene': {len(live()['scenes'])} scenes, tab {live()['ui']['tab']}")
        page.evaluate("window.__editor.store.jumpTo(-1)")
        page.wait_for_timeout(300)
        check(len(live()["scenes"]) == len(sp["scenes"]), "jump to the start")
        page.evaluate("window.__editor.store.jumpTo(window.__editor.store.history().length - 1)")
        page.wait_for_timeout(300)
        check(len(live()["scenes"]) == len(sp3["scenes"]), "jump to the newest step")
        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(200)
        page.locator(".rw-root").focus()
        page.keyboard.press("Control+z")
        page.wait_for_timeout(300)
        check(live()["ui"]["tab"] == "timeline", "undo changed the tab")

        # Run state: "end" with failed / skipped / interrupted clears the run; a rejected run and ComfyUI's own
        # interrupt clear it too.
        page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
        page.wait_for_timeout(300)
        emit = lambda ev, d: page.evaluate("([e, d]) => window.__host.emit(e, d)", [ev, d])
        eph = lambda: page.evaluate("(() => { const e = window.__editor.eph; return { running: e.running, run: e.run, lastRun: e.lastRun, progress: e.progress }; })()")
        emit("reelwright.run", {"slug": "harbor_lights", "run_id": "r1", "phase": "start", "targets": ["s_02", "s_03"], "reused": []})
        emit("reelwright.progress", {"slug": "harbor_lights", "scene_id": "s_02", "pass": 1, "passes": 1, "step": 3, "steps": 20, "phase": "sample"})
        emit("reelwright.progress", {"slug": "harbor_lights", "scene_id": "s_02", "pass": 1, "passes": 1, "phase": "error", "message": "CUDA out of memory"})
        emit("reelwright.progress", {"slug": "harbor_lights", "scene_id": "s_03", "pass": 1, "passes": 1, "step": 2, "steps": 20, "phase": "sample"})
        page.wait_for_timeout(200)
        check(page.evaluate("window.__editor.eph.running") and page.evaluate("window.__editor.eph.run.failed.length") == 1, "progress error not recorded in the run")
        emit("reelwright.run", {"slug": "harbor_lights", "run_id": "r1", "phase": "end", "targets": ["s_02", "s_03"], "reused": [], "rendered": [],
                                "failed": [{"scene_id": "s_02", "error": "CUDA out of memory"}], "skipped": [{"scene_id": "s_03", "reason": "continues from s_02"}], "interrupted": True})
        page.wait_for_timeout(300)
        e = eph()
        check(not e["running"] and e["run"] is None, f"run still active after end: {e['running']} {e['run']}")
        check(e["lastRun"] and e["lastRun"]["interrupted"] and len(e["lastRun"]["failed"]) == 1 and len(e["lastRun"]["skipped"]) == 1, f"lastRun: {e['lastRun']}")
        check(all(x["phase"] in ("done", "cached", "error", "skipped") for x in e["progress"].values()), f"unfinished progress left: {e['progress']}")
        check("Render stopped" in toast_text(), f"stop toast: {toast_text()}")
        page.click(".rw-tab:has-text('Render')")
        page.wait_for_timeout(300)
        check(page.locator("[data-help='render.banner']").count() == 0, "run banner still shown after the end")
        page.screenshot(path=str(shots / "v060_run_end.png"))
        emit("reelwright.run", {"slug": "harbor_lights", "phase": "start", "targets": ["s_01"], "reused": []})
        emit("reelwright.run", {"slug": "harbor_lights", "phase": "rejected", "error": "Fix these first: Scene 1 has no prompt"})
        page.wait_for_timeout(200)
        check(not eph()["running"] and eph()["lastRun"]["rejected"] and "Render not started" in toast_text(), "rejected run")
        # ComfyUI's interrupt for this node's prompt (no "end" from the backend)
        emit("reelwright.run", {"slug": "harbor_lights", "phase": "start", "targets": ["s_01"], "reused": []})
        emit("execution_start", {"prompt_id": "pr-1"})
        emit("executing", "7")
        emit("reelwright.progress", {"slug": "harbor_lights", "scene_id": "s_01", "pass": 1, "passes": 1, "step": 4, "steps": 20, "phase": "sample"})
        emit("execution_interrupted", {"prompt_id": "pr-1", "node_id": "7"})
        page.wait_for_timeout(200)
        check(not eph()["running"] and "s_01" not in eph()["progress"], f"execution_interrupted did not clear the run: {eph()['running']}")
        # the end of the prompt (executing null) after a run that never sent "end"
        emit("reelwright.run", {"slug": "harbor_lights", "phase": "start", "targets": ["s_01"], "reused": []})
        emit("execution_start", {"prompt_id": "pr-2"})
        emit("executing", "7")
        emit("executing", None)
        page.wait_for_timeout(200)
        check(not eph()["running"], "executing null did not clear the run")
        # another node's error does not touch a run of this node
        emit("reelwright.run", {"slug": "harbor_lights", "phase": "start", "targets": ["s_01"], "reused": []})
        emit("execution_error", {"prompt_id": "pr-other", "node_id": "12:7", "exception_message": "boom"})
        page.wait_for_timeout(100)
        check(eph()["running"], "an error of node 12:7 (a subgraph node) ended this node's run")
        emit("reelwright.run", {"slug": "harbor_lights", "phase": "end", "targets": ["s_01"], "reused": [], "rendered": ["s_01"], "failed": [], "skipped": [], "interrupted": False})
        page.wait_for_timeout(200)
        check("Render finished" in toast_text(), f"finish toast: {toast_text()}")

        # Queue: a second click while the first request is on its way is ignored; extra fields reach the request.
        page.evaluate("window.__mockFlags.queueMs = 300")
        q0 = len(page.evaluate("window.__host.queued"))
        page.evaluate("Promise.all([window.__editor.actions.run('pending'), window.__editor.actions.run('pending')])")
        page.wait_for_timeout(500)
        check(len(page.evaluate("window.__host.queued")) == q0 + 1, f"double queue: {len(page.evaluate('window.__host.queued')) - q0} requests")
        page.evaluate("window.__mockFlags.queueMs = 0")
        page.evaluate("window.__editor.actions.run('pass_retake', [], { scene_id: 's_02', pass: 2 })")
        page.wait_for_timeout(200)
        lq = page.evaluate("window.__host.queued.at(-1)")
        check(lq["action"] == "pass_retake" and lq["scene_id"] == "s_02" and lq["pass"] == 2, f"pass_retake request: {lq}")
        page.evaluate("window.__host.emit('reelwright.run', { slug: 'harbor_lights', phase: 'end', targets: [], reused: [] })")
        page.wait_for_timeout(200)

        # Merge: one at a time, 409 busy, and Stop.
        page.evaluate("window.__mockFlags.mergeMs = 600")
        r = page.evaluate("""async () => { const a = window.__editor.actions; const p1 = a.merge({ draft: true }); const second = await a.merge();
          await new Promise(r => setTimeout(r, 100)); const job = window.__editor.eph.merge.job; await a.cancelMerge(); const first = await p1;
          return { second, first, job, phase: window.__editor.eph.merge.phase }; }""")
        check(r["second"] is False and r["first"] is False and r["job"] and r["phase"] == "cancelled", f"merge guard/cancel: {r}")
        page.evaluate("window.__mockFlags.mergeMs = 0; window.__mockFlags.mergeBusy = true")
        r = page.evaluate("window.__editor.actions.merge().then(ok => ({ ok, m: window.__editor.eph.merge }))")
        page.wait_for_timeout(150)
        check(r["ok"] is False and r["m"]["busy"] and "Another merge" in toast_text(), f"merge 409 busy: {r} / {toast_text()}")
        page.evaluate("window.__mockFlags.mergeBusy = false")
        r = page.evaluate("window.__editor.actions.merge({ draft: true }).then(ok => ({ ok, m: window.__editor.eph.merge }))")
        check(r["ok"] and r["m"]["phase"] == "end" and r["m"]["draft"], f"draft merge: {r}")

        # Ctrl+S waits for the disk and says when it fails.
        page.evaluate("window.__mockFlags.autosaveFail = true")
        page.locator(".rw-root").focus()
        page.keyboard.press("Control+s")
        page.wait_for_timeout(300)
        check("Not saved to disk" in toast_text() and "Disk full" in toast_text(), f"Ctrl+S failure: {toast_text()}")
        page.evaluate("window.__mockFlags.autosaveFail = false")
        page.keyboard.press("Control+s")
        page.wait_for_timeout(300)
        check("Saved · output/reelwright/harbor_lights" in toast_text(), f"Ctrl+S: {toast_text()}")

        # Folder conflict: /autosave answers 409 slug_conflict; "Use a separate project" moves to harbor_lights-2;
        # "Take over this folder" resends with force.
        page.evaluate("window.__mockFlags.slugConflict = 'harbor_lights'; window.__mockFlags.autosaves.length = 0")
        page.keyboard.press("Control+s")
        page.wait_for_timeout(300)
        check(page.locator(".rw-modal").count() == 1 and "Lighthouse Keeper" in page.inner_text(".rw-modal"), "slug conflict dialog missing")
        # v0.6.0 review: the harmless "Decide later" has focus (a Space typed on was "Use a separate project")
        check(page.evaluate("document.activeElement.textContent") == "Decide later", "conflict dialog focus")
        page.screenshot(path=str(shots / "v060_conflict.png"))
        page.locator(".rw-modal button:has-text('Decide later')").click()
        page.wait_for_timeout(200)
        check(page.locator(".rw-footer [data-help='footer.saveConflict']").count() == 1, "footer does not show the conflict")
        page.locator(".rw-footer [data-help='footer.saveConflict']").click()
        page.wait_for_timeout(200)
        page.locator(".rw-modal button:has-text('Use a separate project')").click()
        page.wait_for_timeout(400)
        check(live()["slug"] == "harbor_lights-2" and page.evaluate("window.__editor.eph.saveState") == "saved", f"separate project: {live()['slug']} {page.evaluate('window.__editor.eph.saveState')}")
        page.wait_for_timeout(300)
        check(page.evaluate("window.__editor.eph.takesSlug") == "harbor_lights-2", "takes not read for the new folder")
        page.evaluate("window.__mockFlags.slugConflict = 'harbor_lights-2'")
        page.keyboard.press("Control+s")
        page.wait_for_timeout(300)
        page.locator(".rw-modal button:has-text('Take over this folder')").click()
        page.wait_for_timeout(300)
        check(page.evaluate("window.__mockFlags.autosaves.at(-1).force") and page.evaluate("window.__editor.eph.saveState") == "saved", "take over did not force")
        page.evaluate("window.__mockFlags.slugConflict = ''")

        # Takes follow load() and slug changes; a copied node becomes its own project.
        page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
        page.wait_for_timeout(400)
        check(page.evaluate("window.__editor.eph.takesSlug") == "harbor_lights", "takes not refreshed after load()")
        pid = live().get("project_id")
        check(bool(pid), "the project has no project_id")
        new_slug = page.evaluate("window.__editor.forkProject(['harbor_lights-2'])")
        page.wait_for_timeout(400)
        fk = live()
        check(new_slug == "harbor_lights-3" and fk["slug"] == new_slug and fk["project_id"] != pid and not set(x["id"] for x in fk["scenes"]) & set(x["id"] for x in base["scenes"]),
              f"fork: {new_slug} {fk['project_id']} vs {pid}")
        check("copy of another Reelwright node" in toast_text() and page.evaluate("window.__editor.eph.takesSlug") == new_slug, "fork toast / takes")
        page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
        page.wait_for_timeout(300)

        # ChangeTracker: a widget write tells the host (ComfyUI marks the workflow changed).
        c0 = page.evaluate("window.__host.changes")
        page.evaluate("window.__editor.store.update(p => { p.notes = 'x'; }, { label: 'Notes' })")
        page.wait_for_timeout(400)
        check(page.evaluate("window.__host.changes") > c0, "no ChangeTracker notice after an edit")

        # IME: no re-render while composing (the textarea stays the same element); the render follows compositionend.
        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(300)
        ta = page.locator(".rw-psec").nth(1).locator("textarea")
        ta.click()
        page.evaluate("""() => { const t = document.querySelector('.rw-psec:nth-of-type(2) textarea') || document.querySelectorAll('.rw-psec textarea')[1];
          window.__imeTa = t; t.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true, data: '' }));
          window.__host.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_05', pass: 1, passes: 1, step: 1, steps: 9, phase: 'encode' }); }""")
        page.wait_for_timeout(300)
        check(page.evaluate("window.__imeTa.isConnected"), "re-rendered during an IME composition")
        page.evaluate("window.__imeTa.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true, data: 'あ' }))")
        page.wait_for_timeout(300)
        page.evaluate("window.__host.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_05', pass: 1, passes: 1, phase: 'done' })")
        page.wait_for_timeout(200)

        # Tags: e-mail addresses are text, @@ is a literal @.
        hl = page.evaluate("import('../web/rw/prompttext.js').then(m => m.highlightHTML('mail bob@example.com, @@x, @Anna. ok \\u0000' + '1\\u0000'))")
        check(hl.count("hl-at") == 1 and "hl-esc" in hl and "undefined" not in hl, f"tag highlight: {hl!r}")

        # Teardown: a second editor's listeners go away with destroy(), and its last edit is flushed into its widget.
        r = page.evaluate("""async () => {
          const { mountEditor } = await import('../web/rw/editor.js');
          const h = window.__host, before = h.listenerCount();
          let json = JSON.stringify(JSON.parse(h.getProject()));
          const h2 = Object.create(h);
          h2.getProject = () => json; h2.setProject = j => { json = j; };
          const div = document.createElement('div'); div.style.cssText = 'position:absolute;left:-4000px;top:0;width:1200px;height:800px';
          document.body.appendChild(div);
          const ed = mountEditor(div, h2);
          await new Promise(r => setTimeout(r, 100));
          const during = h.listenerCount();
          ed.store.update(p => { p.name = 'Torn down'; }, { label: 'Rename' });
          ed.destroy();
          const after = h.listenerCount();
          await new Promise(r => setTimeout(r, 300));
          const res = { before, during, after, flushed: JSON.parse(json).name, empty: div.childElementCount, destroyed: ed.destroyed };
          div.remove();
          return res; }""")
        check(r["during"] > r["before"] and r["after"] == r["before"], f"listeners after destroy: {r}")
        check(r["flushed"] == "Torn down" and r["empty"] == 0 and r["destroyed"], f"destroy flush/cleanup: {r}")
        page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
        page.wait_for_timeout(300)
        f2a_checks(page, check, saved, shots)  # added 2026-11-03 v0.6.0 (F2a): Timeline, soundtrack, Scene tabs
        f2b_checks(page, check, saved, shots)  # added 2026-11-03 v0.6.0 (F2b): Render, Files, Global, Assets, Cast tabs
        review_checks(page, check, saved, shots)  # added 2026-11-03 v0.6.0 review: frontend fixes of the second review
        v061_checks(page, check, saved, shots)  # added 2026-11-04 v0.6.1: frontend fixes of the third review
        browser.close()
    httpd.shutdown()

    for e in errors:
        print("console:", e)
    for f in failures:
        print("FAIL:", f)
    print("ok" if not (errors or failures) else f"{len(failures)} failures, {len(errors)} errors")
    return 1 if errors or failures else 0


# ---- added 2026-11-03 v0.6.0 (F2a: timeline-side tabs) ----
def f2a_checks(page, check, saved, shots):
    """v0.6.0 tabs (F2a): Next/Prev/Loop over continuing scenes, a loop over a take seeks the video, Delete acts on the
    selection, beats + Snap to beats, Auto-roll keeps later scenes on the song, the "what goes stale" preview, the pass's
    song excerpt (kept across renders), per-pass budget, shot keys after a re-sort, shots on the beat, no NaN after
    deleting the playing scene, progress updated in place (also at 300 scenes)."""
    import base64
    import os
    import shutil
    import subprocess
    import tempfile

    def cur():
        return page.evaluate("JSON.parse(JSON.stringify(window.__editor.project))")

    def load(p):
        page.evaluate("j => window.__editor.load(j)", json.dumps(p))
        page.wait_for_timeout(300)

    def tab(name):
        page.click(f".rw-tab:has-text('{name}')")
        page.wait_for_timeout(250)

    def timing():
        return page.evaluate("""() => import('../web/rw/model.js').then(m => { const p = window.__editor.project; const t = m.sceneStarts(p);
          return { starts: p.scenes.map(s => t.starts[s.id]), visible: p.scenes.map(s => t.visible[s.id]), total: t.total }; })""")

    def handle_box(sid):
        loc = page.locator(f".rw-scene[data-sid='{sid}'] .rw-resize")
        for _ in range(5):  # a render (a toast expiring, the plan arriving) can replace it while it is measured
            loc.wait_for(state="attached", timeout=5000)
            b = loc.bounding_box()
            if b:
                return b
            page.wait_for_timeout(200)
        return loc.bounding_box()

    def drag(x0, y0, dx, alt=False):
        if alt:
            page.keyboard.down("Alt")
        page.mouse.move(x0, y0)
        page.mouse.down()
        page.mouse.move(x0 + dx, y0, steps=6)
        page.mouse.up()
        if alt:
            page.keyboard.up("Alt")
        page.wait_for_timeout(300)

    def fresh():
        # the demo project's pre-0.5 score would become a second (looping) track on load: start without it
        q = json.loads(saved)
        q["global"]["merge"]["score"] = {"asset": "", "volume_db": -12, "duck": False}
        q["soundtrack"] = []
        return q

    sc = page.evaluate("(() => { const r = document.querySelector('.rw-root'); const b = r.getBoundingClientRect(); return b.width / r.offsetWidth; })()")
    song = [{"id": "t_song", "asset": "a_a3", "start": 0, "in": 0, "out": 0, "sync": True, "mix": True, "loop": True}]

    # 1. Next / Prev / Loop over a chain of continuing scenes (01 fresh -> 02 last frame -> 03 tail -> 04 tail)
    p = fresh()
    p["scenes"][3]["start"]["mode"] = "tail"
    p["soundtrack"] = []
    p["ui"]["playhead"] = 0
    load(p)
    tab("Timeline")
    tm = timing()
    page.locator(".rw-root").focus()
    page.keyboard.press("Home")
    seen = []
    for _ in range(4):
        page.locator("button[data-help='timeline.transport.next']").click()
        page.wait_for_timeout(120)
        seen.append(cur()["ui"]["playhead"])
    check(all(abs(seen[k] - tm["visible"][k + 1]) < 1e-6 for k in range(4)), f"Next over continuing scenes: {seen} vs {tm['visible'][1:5]}")
    page.evaluate("t => window.__editor.store.update(p => { p.ui.playhead = t; }, { history: false, plan: false })", tm["visible"][3] + 1.0)
    got = []
    for _ in range(3):
        page.locator("button[data-help='timeline.transport.prev']").click()
        page.wait_for_timeout(120)
        got.append(cur()["ui"]["playhead"])
    want = [tm["visible"][3], tm["visible"][2], tm["visible"][1]]
    check(all(abs(a - b) < 1e-6 for a, b in zip(got, want)), f"Prev over continuing scenes: {got} vs {want}")
    page.locator("button[data-help='timeline.transport.loop']").click()
    page.wait_for_timeout(150)
    lp = page.evaluate("window.__editor.eph.loop")
    check(bool(lp) and abs(lp["in"] - tm["visible"][1]) < 1e-6 and abs(lp["out"] - (tm["starts"][1] + p["scenes"][1]["duration"])) < 1e-6,
          f"Loop on a continuing scene: {lp}")
    page.locator("button[data-help='timeline.transport.loop']").click()
    page.wait_for_timeout(120)

    # 2. A loop over a rendered take seeks the take when the playhead wraps (it used to play on past the loop)
    vid = None
    if shutil.which("ffmpeg"):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "take.webm")
            r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x36:rate=24:duration=6",
                                "-c:v", "libvpx", "-b:v", "60k", "-g", "6", "-y", out], capture_output=True)
            if r.returncode == 0:
                with open(out, "rb") as f:
                    vid = base64.b64encode(f.read()).decode()
    if vid is None:
        print("note: no ffmpeg with libvpx; the loop-seek check is skipped", flush=True)
    else:
        page.evaluate("""b64 => { const bin = atob(b64); const u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
          const url = URL.createObjectURL(new Blob([u8], { type: 'video/webm' })); const h = window.__host; h.__apiURL0 = h.__apiURL0 || h.apiURL;
          h.apiURL = function (path) { const f = new URL(path, 'http://x').searchParams.get('filename') || ''; return f.endsWith('.mp4') ? url : h.__apiURL0.call(this, path); }; }""", vid)
        page.evaluate("window.__editor.store.update(p => { p.ui.playhead = 1.0; p.ui.selected = 's_01'; }, { history: false, plan: false })")
        page.wait_for_timeout(300)
        try:
            page.wait_for_function("document.querySelector('.rw-mon-video').readyState >= 2", timeout=5000)
        except Exception:
            pass
        page.evaluate("window.__editor.store.setEph({ loop: { in: 1.0, out: 2.0 } })")
        page.wait_for_timeout(100)
        page.locator(".rw-root").focus()
        page.keyboard.press(" ")
        page.wait_for_timeout(2800)
        st = page.evaluate("(() => { const v = document.querySelector('.rw-mon-video'); return { vt: v.currentTime, paused: v.paused, src: !!v.src, ph: window.__editor.project.ui.playhead }; })()")
        page.keyboard.press("k")
        page.wait_for_timeout(150)
        check(st["src"] and not st["paused"] and 0.95 <= st["ph"] <= 2.05 and st["vt"] <= 2.4, f"a loop over a take did not seek the take: {st}")
        page.evaluate("window.__editor.store.setEph({ loop: null })")
        page.evaluate("(() => { const h = window.__host; if (h.__apiURL0) { h.apiURL = h.__apiURL0; delete h.__apiURL0; } })()")

    # 3. Delete removes what is selected: a soundtrack track or a marker (no question), else the scene (it asks)
    p = fresh()
    p["soundtrack"] = song
    p["ui"]["playhead"] = 3.0
    load(p)
    tab("Timeline")
    page.locator(".rw-track-clip[data-tid='t_song']").first.click()
    page.wait_for_timeout(250)
    page.keyboard.press("Delete")
    page.wait_for_timeout(250)
    check(cur()["soundtrack"] == [] and page.locator(".rw-modal").count() == 0 and len(cur()["scenes"]) == 8,
          f"Delete did not remove the selected track: {len(cur()['soundtrack'])} tracks, modal {page.locator('.rw-modal').count()}")
    page.keyboard.press("Control+z")
    page.wait_for_timeout(300)
    check(len(cur()["soundtrack"]) == 1, "undo did not bring the deleted track back")
    page.locator(".rw-marker").first.click()
    page.wait_for_timeout(200)
    page.keyboard.press("Delete")
    page.wait_for_timeout(250)
    check(len(cur()["markers"]) == 1 and page.locator(".rw-modal").count() == 0, f"Delete did not remove the selected marker: {cur()['markers']}")
    page.keyboard.press("Control+z")
    page.wait_for_timeout(250)
    page.locator(".rw-marker").first.click()
    page.wait_for_timeout(200)
    page.locator(".rw-scene[data-sid='s_02']").click()
    page.wait_for_timeout(250)
    check(page.evaluate("window.__editor.eph.selectedMarker") in (None, "") and page.locator(".rw-insp-head").count() == 1,
          "a click on a scene did not close the marker inspector")
    page.keyboard.press("Delete")
    page.wait_for_timeout(250)
    check(page.locator(".rw-modal").count() == 1, "Delete with a scene selected should ask first")
    page.locator(".rw-modal button:has-text('Cancel')").click()
    page.wait_for_timeout(200)
    check(len(cur()["scenes"]) == 8 and len(cur()["markers"]) == 2, "Cancel changed the project")

    # 4. Beats: the tempo on the track, the Beats toggle, Snap to beats puts a scene edge on a beat
    check("BPM" in page.locator(".rw-track-clip[data-tid='t_song']").first.inner_text(), "no tempo on the soundtrack clip")
    tg = page.locator(".rw-tl-toolbar button.rw-toggle[data-help='timeline.beats']")
    check(tg.count() == 1, "no Beats toggle")
    tg.click()
    page.wait_for_timeout(200)
    check(cur()["ui"].get("beats") is False, "the Beats toggle did not turn the ticks off")
    page.locator(".rw-tl-toolbar button.rw-toggle[data-help='timeline.beats']").click()
    page.wait_for_timeout(200)
    page.locator(".rw-tl-toolbar button.rw-toggle[data-help='timeline.beatSnap']").click()
    page.wait_for_timeout(300)
    check(cur()["ui"].get("beatSnap") is True and cur()["ui"].get("beats") is not False, f"Snap to beats: {cur()['ui']}")
    beats = page.evaluate("() => import('../web/rw/tabs/soundtrack.js').then(m => Array.from(m.beatTimes({ p: window.__editor.project, store: { notify() {} } }).times))")
    z = cur()["ui"]["zoom"] or 22
    end0 = cur()["scenes"][0]["duration"]
    target = min((b for b in beats if b > end0 + 0.6), default=None)
    check(target is not None, f"no beats under the film: {beats[:5]}")
    if target is not None:
        hb = handle_box("s_01")
        drag(hb["x"] + hb["width"] / 2, hb["y"] + 20, (target + 0.06 - end0) * z * sc)
        d = cur()["scenes"][0]["duration"]
        check(round(d * 24) == round(target * 24), f"the scene edge did not snap to the beat at {target}: {d}")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(250)
    page.locator(".rw-tl-toolbar button.rw-toggle[data-help='timeline.beatSnap']").click()
    page.wait_for_timeout(200)
    # a render in the middle of a resize drag (plan or autosave state arriving) no longer ends it; nor does a lost pointerup
    hb = handle_box("s_01")
    d0 = cur()["scenes"][0]["duration"]
    page.mouse.move(hb["x"] + 4, hb["y"] + 20)
    page.mouse.down()
    page.mouse.move(hb["x"] + 4 + 1 * z * sc, hb["y"] + 20, steps=3)
    page.evaluate("window.__editor.store.notify()")
    page.wait_for_timeout(80)
    page.mouse.move(hb["x"] + 4 + 2.5 * z * sc, hb["y"] + 20, steps=3)
    page.evaluate("window.dispatchEvent(new PointerEvent('pointermove', { clientX: 5, clientY: 5, buttons: 0, bubbles: true }))")  # the button was let go elsewhere
    page.wait_for_timeout(250)
    d1 = cur()["scenes"][0]["duration"]
    page.mouse.move(hb["x"] + 4 + 6 * z * sc, hb["y"] + 20, steps=3)
    page.mouse.up()
    page.wait_for_timeout(250)
    check(d1 > d0 + 1.5 and cur()["scenes"][0]["duration"] == d1 and page.locator(".rw-drag-tip:visible").count() == 0,
          f"resize across a render / lost pointerup: {d0} -> {d1} -> {cur()['scenes'][0]['duration']}")
    page.keyboard.press("Control+z")
    page.wait_for_timeout(250)

    # 5. Auto-roll (on while the soundtrack sets the timing): a longer scene takes the time from the next one, so every
    # later scene keeps its place on the song; off, the later scenes move along (Ripple)
    check(page.locator(".rw-tl-toolbar button.rw-toggle[data-help='timeline.autoRoll']").count() == 1 and cur()["ui"]["ripple"],
          "no Auto-roll toggle with a locked soundtrack")
    tm0 = timing()
    d3, d4 = cur()["scenes"][3]["duration"], cur()["scenes"][4]["duration"]
    hb = handle_box("s_04")
    drag(hb["x"] + hb["width"] / 2, hb["y"] + 20, 2 * z * sc)
    tm1 = timing()
    q = cur()
    # v0.6.0 review: the sum of the two lengths is no longer the rule (tail overlaps are capped by the lengths around
    # them); the later scenes keeping their starts is
    check(q["scenes"][3]["duration"] > d3 and q["scenes"][4]["duration"] < d4
          and all(abs(tm1["starts"][k] - tm0["starts"][k]) < 1e-6 for k in range(5, 8)) and abs(tm1["total"] - tm0["total"]) < 1e-6,
          f"auto-roll moved later scenes: {tm0['starts']} -> {tm1['starts']}")
    page.locator(".rw-tl-toolbar button.rw-toggle[data-help='timeline.autoRoll']").click()
    page.wait_for_timeout(200)
    hb = handle_box("s_04")
    drag(hb["x"] + hb["width"] / 2, hb["y"] + 20, 2 * z * sc)
    tm2 = timing()
    check(cur()["ui"].get("autoRoll") is False and tm2["starts"][6] > tm1["starts"][6] + 0.5, f"with Auto-roll off the later scenes should move: {tm1['starts']} -> {tm2['starts']}")
    page.keyboard.press("Control+z")
    page.wait_for_timeout(200)
    page.locator(".rw-tl-toolbar button.rw-toggle[data-help='timeline.autoRoll']").click()
    page.wait_for_timeout(200)

    # 6. "What goes stale": dragging a synced track outlines the scenes whose song part would change, before the drop
    clip = page.locator(".rw-track-clip:not(.ghost)[data-tid='t_song']").first
    bx = None
    for _ in range(5):  # a render (a toast expiring) can replace the clip while it is measured
        clip.wait_for(state="visible", timeout=5000)
        bx = clip.bounding_box()
        if bx:
            break
        page.wait_for_timeout(200)
    page.mouse.move(bx["x"] + 30, bx["y"] + bx["height"] / 2)
    page.mouse.down()
    page.mouse.move(bx["x"] + 30 + 3 * z * sc, bx["y"] + bx["height"] / 2, steps=6)
    page.wait_for_timeout(200)
    n_stale = page.locator(".rw-scene.rw-stale-preview").count()
    tip = page.locator(".rw-track-clip[data-tid='t_song'] .rw-drag-tip").first.inner_text()
    page.screenshot(path=str(shots / "v060_stale_preview.png"))
    page.mouse.up()
    page.wait_for_timeout(300)
    check(n_stale >= 1 and "render again" in tip, f"stale preview while dragging: {n_stale} scenes, tip {tip!r}")
    check(page.locator(".rw-scene.rw-stale-preview").count() == 0, "the stale preview stayed after the drop")
    page.keyboard.press("Control+z")
    page.wait_for_timeout(250)

    # 7. "What H3 receives": listen to the pass's song excerpt; the <audio> survives re-renders
    page.evaluate("window.__editor.store.update(p => { p.ui.selected = 's_01'; }, { history: false, plan: false })")
    tab("Scene")
    ex = page.locator(".rw-excerpt")
    check(ex.count() == 1, "no song excerpt row in What H3 receives")
    if ex.count():
        ex.locator("button[data-help='scene.preview.listen']").click()
        try:
            page.wait_for_selector("audio.rw-excerpt-audio", timeout=4000)
        except Exception:
            pass
        page.evaluate("window.__exA = document.querySelector('audio.rw-excerpt-audio')")
        page.evaluate("window.__editor.store.notify()")
        page.wait_for_timeout(200)
        page.evaluate("window.__host.emit('reelwright.progress', { slug: window.__editor.project.slug, scene_id: 's_07', pass: 1, passes: 3, step: 1, steps: 28, phase: 'encode' })")
        page.wait_for_timeout(200)
        check(page.evaluate("!!window.__exA && document.querySelector('audio.rw-excerpt-audio') === window.__exA && window.__exA.isConnected"),
              "the excerpt player was rebuilt by a render (or never built)")
        page.evaluate("window.__host.emit('reelwright.progress', { slug: window.__editor.project.slug, scene_id: 's_07', pass: 1, passes: 3, phase: 'done' })")
        page.wait_for_timeout(150)

    # 8. A long scene shows its budget per pass; a shot time keeps focus on its own field after a re-sort
    page.evaluate("window.__editor.store.update(p => { p.ui.selected = 's_07'; }, { history: false, plan: false })")
    page.wait_for_timeout(300)
    check(page.locator(".rw-budget-pass").count() >= 2, "no per-pass budget for a long scene")
    f = page.locator("input[data-key='shot-t-h_12']")
    f.click()
    f.fill("3")
    f.press("Enter")
    page.wait_for_timeout(350)
    order = [x["id"] for x in cur()["scenes"][6]["shots"]]
    act = page.evaluate("document.activeElement?.dataset?.key || ''")
    rows = page.evaluate("[...document.querySelectorAll('input[data-help=\"scene.shots.time\"]')].map(e => e.dataset.key)")
    check(order[1] == "h_12" and act == "shot-t-h_12" and rows[1] == "shot-t-h_12", f"shot time focus after a re-sort: {act} {rows} {order}")
    page.locator(".rw-root").focus()

    # 9. Shots on the beat: proposed first, applied with one click (one undo step)
    page.locator("button[data-help='scene.shots.beat']").click()
    page.wait_for_timeout(300)
    check(page.locator(".rw-beat-plan").count() == 1, "no beat proposal")
    page.screenshot(path=str(shots / "v060_shots_on_beat.png"))
    apply = page.locator(".rw-beat-plan button[data-help='scene.shots.beatApply']")
    if apply.count():
        apply.click()
        page.wait_for_timeout(300)
        s7 = cur()["scenes"][6]
        st7 = timing()["starts"][6]
        local = [b - st7 for b in beats]
        off = [min(abs(sh["t"] - b) for b in local) for sh in s7["shots"][1:]]
        hist = page.evaluate("window.__editor.store.history().filter(x => x.done).at(-1)?.label")
        check(all(o <= 1 / 24 + 1e-6 for o in off) and hist == "Shots on the beat", f"shots on the beat: off {off}, history {hist!r}")

    # 10. Deleting (and undoing) the scene that is playing keeps the playhead a number and playback going
    tab("Timeline")
    tm = timing()
    page.evaluate("t => window.__editor.store.update(p => { p.ui.playhead = t; p.ui.selected = 's_05'; }, { history: false, plan: false })", tm["visible"][4] + 0.5)
    page.locator(".rw-root").focus()
    page.keyboard.press(" ")
    page.wait_for_timeout(300)
    page.evaluate("window.__editor.actions.deleteScene('s_05', { ask: false })")
    page.wait_for_timeout(400)
    ph1, tc1 = cur()["ui"]["playhead"], page.locator(".rw-tc").inner_text()
    page.keyboard.press("Control+z")
    page.wait_for_timeout(400)
    ph2, tc2 = cur()["ui"]["playhead"], page.locator(".rw-tc").inner_text()
    playing = page.evaluate("window.__editor.eph.playing")
    page.keyboard.press("k")
    page.wait_for_timeout(150)
    check(isinstance(ph1, (int, float)) and isinstance(ph2, (int, float)) and "NaN" not in tc1 + tc2 and playing and len(cur()["scenes"]) == 8,
          f"playhead after deleting the playing scene: {ph1} {ph2} {tc1!r} {tc2!r} playing={playing}")

    # 11. A render step updates the scene's progress bar in place (the tab is not rebuilt), also with 300 scenes
    probe = """async (sid) => { const f = () => new Promise(r => requestAnimationFrame(() => r()));
      const h = window.__host, slug = window.__editor.project.slug, sel = `.rw-scene[data-sid="${sid}"]`;
      h.emit('reelwright.progress', { slug, scene_id: sid, pass: 1, passes: 2, step: 1, steps: 28, phase: 'sample' }); await f(); await f();
      const b = document.querySelector(sel), ms = [];
      for (let k = 2; k < 12; k++) { const t0 = performance.now(); h.emit('reelwright.progress', { slug, scene_id: sid, pass: 1, passes: 2, step: k, steps: 28, phase: 'sample' }); await f(); ms.push(performance.now() - t0); }
      const b2 = document.querySelector(sel);
      const res = { same: !!b && b === b2, label: b2?.querySelector('.rw-scene-prog-label')?.textContent || '', ms: ms.sort((x, y) => x - y)[5] };
      h.emit('reelwright.progress', { slug, scene_id: sid, pass: 2, passes: 2, phase: 'done' });
      return res; }"""
    def settle():
        # toasts expiring, a plan or takes arriving re-render the tab on their own; wait until they are done
        try:
            page.wait_for_function("document.querySelectorAll('.rw-toast').length === 0", timeout=9000)
        except Exception:
            pass
        page.wait_for_timeout(700)

    settle()
    r = page.evaluate(probe, "s_07")
    if not r["same"]:  # once more, in case something else rendered in between
        settle()
        r = page.evaluate(probe, "s_07")
    check(r["same"] and "11/28" in r["label"], f"progress not updated in place: {r}")
    big = fresh()
    tmpl = big["scenes"]
    big["scenes"] = []
    for i in range(300):
        s = json.loads(json.dumps(tmpl[i % len(tmpl)]))
        s["id"] = f"s_p{i}"
        s["seed_n"] = i
        for lst in ("refs", "shots", "dialogue"):
            for x in s[lst]:
                x["id"] = f"{x['id']}_{i}"
        big["scenes"].append(s)
    big["scenes"][0]["start"]["mode"] = "fresh"
    big["soundtrack"] = song
    big["ui"]["selected"] = "s_p2"
    big["ui"]["playhead"] = 0
    big["ui"]["tab"] = "timeline"
    load(big)
    page.wait_for_timeout(800)  # plan, takes and beats arrive first
    settle()
    r = page.evaluate(probe, "s_p3")
    if not r["same"]:
        settle()
        r = page.evaluate(probe, "s_p3")
    print(f"note: a progress event with 300 scenes took {r['ms']:.1f} ms (v0.5.1: about 230 ms)", flush=True)
    check("11/28" in r["label"] and r["ms"] < 100, f"progress with 300 scenes: {r}")
    page.screenshot(path=str(shots / "v060_300_scenes.png"))

    load(json.loads(saved))
    tab("Timeline")


# ---- added 2026-11-03 v0.6.0 (F2b: project-side tabs) ----
def f2b_checks(page, check, saved, shots):
    """v0.6.0 tabs (F2b): upstream warning + re-render, pass retake, variants, estimates, prompt diff, merge options /
    Stop / loudness, version diff, Files repair / flags / refused deletes / asset cleanup, dialogs instead of inline bars,
    media kept across re-renders, outfit delete, From ComfyUI card, profile GETs, project rename, script import."""
    live = lambda: page.evaluate("JSON.parse(JSON.stringify(window.__editor.project))")
    emit = lambda ev, d: page.evaluate("([e, d]) => window.__host.emit(e, d)", [ev, d])
    queued = lambda: page.evaluate("window.__host.queued")
    toasts = lambda: " | ".join(page.locator(".rw-toast").all_inner_texts())
    labels = lambda: [x["label"] for x in page.evaluate("window.__editor.store.history()")]
    undo = lambda: (page.evaluate("window.__editor.store.undo()"), page.wait_for_timeout(250))
    S = "harbor_lights"
    prog = lambda sid, ph, **kw: emit("reelwright.progress", {"slug": S, "scene_id": sid, "pass": kw.get("pass_", 1), "passes": kw.get("passes", 3), "step": kw.get("step", 0), "steps": kw.get("steps", 28), "phase": ph, "message": kw.get("message", "")})
    page.evaluate("window.__fetch0 = window.__host.fetchApi")
    page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
    page.wait_for_timeout(300)
    if page.evaluate("window.__editor.eph.running"):
        emit("reelwright.run", {"slug": S, "phase": "end", "targets": [], "reused": [], "rendered": []})
    page.evaluate("window.__editor.store.setEph({ progress: {}, lastRun: null, openTakes: {}, compare: null })")
    page.click(".rw-tab:has-text('Render')")
    page.wait_for_function("!!window.__editor.eph.plan?.scenes?.s_03?.upstream_changed", timeout=8000)
    page.wait_for_timeout(300)
    order = [s["id"] for s in live()["scenes"]]
    trow = lambda sid: page.locator(".rw-trow:not(.head)").nth(order.index(sid))

    # "Continues from a different take": one click re-renders the scene and the scenes that continue from it.
    note = page.locator(".rw-trow-note[data-help='render.table.upstream']")
    check(note.count() == 1 and "Continues from a different take" in note.inner_text(), f"upstream note: {note.count()}")
    q0 = len(queued())
    note.locator("button[data-help='render.table.upstream.rerender']").click()
    page.wait_for_timeout(300)
    lq = queued()[-1]
    check(len(queued()) == q0 + 1 and lq["action"] == "selected" and lq["scenes"][0] == "s_03", f"upstream re-render request: {lq}")
    page.evaluate("window.__mockFlags.plan = { s_02: { upstream_changed: true, upstream_take: 'v1' } }; window.__editor.store.refreshPlan()")
    page.wait_for_timeout(400)
    want = page.evaluate("""async () => { const m = await import('../web/rw/model.js'); const p = window.__editor.project;
      const i = p.scenes.findIndex(s => s.id === 's_02'); const out = ['s_02'];
      for (let k = i + 1; k < p.scenes.length; k++) { if (m.effectiveStart(p, k) === 'fresh' || p.scenes[k].lock) break; out.push(p.scenes[k].id); }
      return out; }""")
    page.locator(".rw-trow-note[data-help='render.table.upstream']").first.locator("button").click()
    page.wait_for_timeout(300)
    lq = queued()[-1]
    check(lq["action"] == "selected" and lq["scenes"] == want and len(want) >= 2, f"re-render with dependents: {lq['scenes']} vs {want}")
    page.evaluate("window.__mockFlags.plan = {}; window.__editor.store.refreshPlan()")
    emit("reelwright.run", {"slug": S, "phase": "end", "targets": [], "reused": [], "rendered": []})
    page.wait_for_timeout(400)

    # Time estimate of the queue and per scene; passes kept in the pass cache.
    est = page.locator(".rw-estimate").inner_text() if page.locator(".rw-estimate").count() else ""
    check(est.startswith("≈") and "min" in est and "without history" in est, f"queue estimate: {est!r}")
    se = trow("s_03").locator("[data-help='render.table.estimate']")
    check(se.count() == 1 and "4 min" in se.inner_text(), "scene estimate missing")
    check("1 kept" in trow("s_07").inner_text(), f"cached passes: {trow('s_07').inner_text()!r}")
    check(page.locator("[data-help='render.table.manualStar']").count() >= 1, "manual star hint missing")

    # Prompt diff against the starred take ("why?").
    trow("s_03").locator(".rw-why").click()
    page.wait_for_timeout(250)
    box = page.locator(".rw-diff-box")
    check(box.count() == 1 and box.locator(".rw-diff-line.del").count() >= 1 and "reads the letter" in box.locator(".rw-diff-line.del").first.inner_text()
          and box.locator(".rw-diff-line.add").count() >= 1, "prompt diff not shown")
    page.screenshot(path=str(shots / "v060_render_diff.png"))
    trow("s_03").locator(".rw-why").click()

    # Pass retake (long scene with a starred take): the request names the scene and the pass.
    page.evaluate("""() => { const e = window.__editor; const t = structuredClone(e.eph.takes);
      t.scenes.s_07 = { starred: 'v1', takes: [{ id: 'v1', created: 1793560000, quality: 'final', seconds: 32, frames: 768, files: {} }] };
      e.store.setEph({ takes: t, openTakes: { s_07: true } }); }""")
    page.wait_for_timeout(250)
    btns = page.locator(".rw-pass-retake button")
    check(btns.count() == 3, f"pass retake buttons: {btns.count()}")
    if btns.count() == 3:
        btns.nth(1).click()
        page.wait_for_timeout(300)
        lq = queued()[-1]
        check(lq["action"] == "pass_retake" and lq["scene_id"] == "s_07" and lq["pass"] == 2, f"pass retake request: {lq}")

    # Variants: n takes of the selected scene; its take list opens for the A/B compare.
    page.evaluate("window.__editor.actions.select('s_05')")
    page.wait_for_timeout(200)
    nf = page.locator("input[data-help='render.variants.n']")
    nf.fill("4")
    nf.press("Tab")
    page.wait_for_timeout(200)
    page.click("button[data-help='render.variants']")
    page.wait_for_timeout(300)
    lq = queued()[-1]
    check(lq["action"] == "variants" and lq["scene_ids"] == ["s_05"] and lq["n"] == 4, f"variants request: {lq}")
    check(page.evaluate("!!window.__editor.eph.openTakes?.s_05"), "variants did not open the take list")
    emit("reelwright.run", {"slug": S, "phase": "end", "targets": [], "reused": [], "rendered": []})
    page.wait_for_timeout(300)

    # Progress updates the banner in place (same element); a pass from the pass cache reads "from cache".
    emit("reelwright.run", {"slug": S, "run_id": "rf", "phase": "start", "targets": ["s_07"], "reused": []})
    prog("s_07", "sample", step=1)
    page.wait_for_timeout(300)
    # the step is written into the same element during the event itself (a full re-render would only come later)
    st = page.evaluate("""() => { const run = document.querySelector('.rw-run'); if (run) run.__mark = 1;
      window.__host.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_07', pass: 1, passes: 3, step: 5, steps: 28, phase: 'sample', message: '' });
      const now = document.querySelector('.rw-run');
      return { same: !!now && now.__mark === 1, text: document.querySelector('.rw-run-detail')?.textContent || '' }; }""")
    check(st["same"] and "step 5/28" in st["text"], f"banner not updated in place: {st}")
    prog("s_07", "reuse", pass_=2, message="pass 2 from the pass cache")
    page.wait_for_timeout(300)
    det = page.evaluate("document.querySelector('.rw-run-detail')?.textContent || ''")
    check("from cache" in det and "reuse" not in det, f"reuse phase: {det!r}")

    # A/B compare videos are the same elements after progress events and re-renders.
    page.evaluate("window.__editor.store.setEph({ openTakes: { s_02: true } })")
    page.wait_for_timeout(200)
    page.locator(".rw-take").nth(0).locator("button[data-help='render.take.compareA']").click()
    page.wait_for_timeout(150)
    check(page.evaluate("window.__editor.eph.compare?.a?.scene") == "s_02", "A button did not fill the compare")
    # the mock serves no video files (empty URLs), so the two panes get blob URLs of their own
    page.evaluate("""() => { const u = () => URL.createObjectURL(new Blob([new Uint8Array(16)], { type: 'video/mp4' }));
      window.__editor.store.setEph({ compare: { a: { scene: 's_02', take: 'v1', url: u() }, b: { scene: 's_02', take: 'v2', url: u() } } }); }""")
    page.wait_for_timeout(200)
    n_vid = page.evaluate("(() => { const v = [...document.querySelectorAll('.rw-ab video')]; v.forEach(x => { x.__mark = 1; }); return v.length; })()")
    for k in range(6, 10):
        prog("s_07", "sample", pass_=3, step=k)
    prog("s_07", "decode", pass_=3)
    prog("s_07", "done", pass_=3, message="v2")
    page.wait_for_timeout(500)
    kept = page.evaluate("[...document.querySelectorAll('.rw-ab video')].map(v => v.__mark === 1)")
    check(n_vid == 2 and kept == [True, True], f"A/B videos rebuilt: {n_vid} {kept}")
    emit("reelwright.run", {"slug": S, "run_id": "rf", "phase": "end", "targets": ["s_07"], "reused": [], "rendered": ["s_07"]})
    page.wait_for_timeout(300)

    # Last run: failed and skipped scenes per scene, with a retry.
    emit("reelwright.run", {"slug": S, "run_id": "rg", "phase": "start", "targets": ["s_02", "s_03"], "reused": []})
    emit("reelwright.run", {"slug": S, "run_id": "rg", "phase": "end", "targets": ["s_02", "s_03"], "reused": [], "rendered": [],
                            "failed": [{"scene_id": "s_02", "error": "CUDA out of memory"}], "skipped": [{"scene_id": "s_03", "reason": "it continues from 02, which failed"}], "interrupted": False})
    page.wait_for_timeout(400)
    lr = page.locator("[data-help='render.lastRun']")
    check(lr.count() == 1 and "CUDA out of memory" in lr.inner_text() and "skipped" in lr.inner_text(), "last run note missing")
    check(trow("s_02").locator(".rw-runres.failed").count() == 1 and trow("s_03").locator(".rw-runres.skipped").count() == 1, "per-scene run result missing")
    lr.locator("button[data-help='render.lastRun.retry']").click()
    page.wait_for_timeout(300)
    lq = queued()[-1]
    check(lq["action"] == "selected" and lq["scenes"] == ["s_02", "s_03"], f"retry request: {lq}")
    emit("reelwright.run", {"slug": S, "phase": "end", "targets": [], "reused": [], "rendered": []})
    page.wait_for_timeout(300)
    page.screenshot(path=str(shots / "v060_render_tab.png"))
    # a run refused before it started says why
    emit("reelwright.run", {"slug": S, "phase": "rejected", "error": "Fix these first: 03 The letter: P9 file is missing"})
    page.wait_for_timeout(300)
    lr = page.locator("[data-help='render.lastRun']")
    check(lr.count() == 1 and "Render not started" in lr.inner_text() and "P9 file is missing" in lr.inner_text(), "rejected run not shown")
    lr.locator("button[data-help='common.close']").click()
    page.wait_for_timeout(200)
    check(page.locator("[data-help='render.lastRun']").count() == 0, "last run note did not close")

    # Dialogs instead of inline bars: Everything, a take's delete (survives a progress event).
    page.click("button[data-help='render.scope.all']")
    page.wait_for_timeout(200)
    check(page.locator(".rw-modal").count() == 1 and page.locator(".rw-confirm").count() == 0, "Everything did not open a dialog")
    q0 = len(queued())
    page.locator(".rw-modal button:has-text('Cancel')").click()
    page.wait_for_timeout(200)
    check(len(queued()) == q0, "Cancel queued a render")
    page.locator(".rw-take").nth(0).locator("button[data-help='render.take.delete']").click()
    page.wait_for_timeout(150)
    prog("s_07", "done", pass_=3, message="v2")
    page.wait_for_timeout(300)
    check(page.locator(".rw-modal").count() == 1 and page.locator(".rw-confirm").count() == 0, "take delete dialog vanished after a progress event")
    page.locator(".rw-modal button:has-text('Cancel')").click()
    page.wait_for_timeout(200)

    # Merge options: draft, range and stems reach the request; the loudness report shows; Stop cancels a merge.
    page.evaluate("window.__editor.actions.select('s_05'); window.__mockFlags.merges.length = 0")
    page.wait_for_timeout(150)
    page.click("button[data-help='render.merge.draft.on']")
    page.click("button[data-help='render.merge.range.some']")
    page.click("button[data-help='render.merge.stems']")
    page.wait_for_timeout(200)
    page.locator(".rw-merge .rw-btn-primary").click()
    page.wait_for_timeout(600)
    mb = page.evaluate("window.__mockFlags.merges.at(-1)")
    check(mb and mb["draft"] is True and mb["stems"] is True and mb["range"] == ["s_05", order[-1]], f"merge request: {mb}")
    loud = page.locator(".rw-merge .rw-loudness")
    check(loud.count() == 1 and "-16.2 LUFS" in loud.inner_text() and "dBTP" in loud.inner_text(), "loudness report missing")
    for _ in range(5):  # a re-render (toast expiring) can replace the element while it scrolls
        try:
            page.locator(".rw-merge .rw-loudness").scroll_into_view_if_needed(timeout=2000)
            break
        except Exception:  # noqa: BLE001
            page.wait_for_timeout(200)
    page.screenshot(path=str(shots / "v060_merge_options.png"))
    page.evaluate("window.__mockFlags.mergeMs = 2000")
    page.locator(".rw-merge .rw-btn-primary").click()
    page.wait_for_timeout(300)
    stop = page.locator(".rw-merge button[data-help='render.merge.stop']")
    check(stop.count() == 1, "no Stop while merging")
    if stop.count():
        stop.click()
        page.wait_for_timeout(600)
    check(page.evaluate("window.__editor.eph.merge?.phase") == "cancelled" and "Merge stopped" in page.locator(".rw-merge").inner_text(), f"merge Stop: {page.evaluate('window.__editor.eph.merge?.phase')}")
    page.evaluate("window.__mockFlags.mergeMs = 0; window.__editor.store.setEph({ mergeOpts: null })")

    # Version diff before a restore: the dialog says what changes; Cancel keeps the project, Restore replaces it.
    page.evaluate("""() => { window.__mockFlags.versionEdits = vp => {
        const cur = JSON.parse(JSON.stringify(window.__editor.project));
        for (const k of Object.keys(vp)) delete vp[k];
        Object.assign(vp, cur);
        vp.scenes = vp.scenes.filter(s => s.id !== 's_08');
        const s = vp.scenes.find(x => x.id === 's_03'); s.duration = 9.5; s.prompt.sections.summary = 'An older summary of the letter scene.';
        vp.global.quality = vp.global.quality === 'draft' ? 'final' : 'draft'; };
      window.__editor.store.setEph({ versions: [{ name: 'project_20261103_090000.json', created: 1793696400, size: 21000 }] }); }""")
    page.wait_for_timeout(200)
    page.locator(".rw-version button[data-help='render.versions.restore']").click()
    page.wait_for_timeout(500)
    msg = page.locator(".rw-modal .rw-vdiff").inner_text() if page.locator(".rw-modal .rw-vdiff").count() else ""
    check("Removes 1 scene" in msg and "9.50 s" in msg and "summary" in msg and "quality" in msg, f"version diff: {msg!r}")
    page.screenshot(path=str(shots / "v060_version_diff.png"))
    page.locator(".rw-modal button:has-text('Cancel')").click()
    page.wait_for_timeout(200)
    check("s_08" in [s["id"] for s in live()["scenes"]], "Cancel restored the version")
    page.locator(".rw-version button[data-help='render.versions.restore']").click()
    page.wait_for_timeout(500)
    page.locator(".rw-modal button:has-text('Restore')").click()
    page.wait_for_timeout(300)
    pj = live()
    check("s_08" not in [s["id"] for s in pj["scenes"]] and [s for s in pj["scenes"] if s["id"] == "s_03"][0]["duration"] == 9.5, "Restore did not replace the project")
    check(labels()[-1].startswith("Restore version"), f"restore label: {labels()[-1:]}")
    undo()
    check("s_08" in [s["id"] for s in live()["scenes"]], "undo of the restore")
    page.evaluate("window.__mockFlags.versionEdits = null; window.__editor.store.setEph({ versions: null })")

    # Global: a rename keeps the folder while its takes were not read; a new node's untitled-xxxx folder follows the name.
    page.click(".rw-tab:has-text('Global')")
    page.wait_for_timeout(300)
    slug0 = live()["slug"]
    page.evaluate("window.__editor.store.setEph({ takes: null, takesSlug: null })")
    name = page.locator("input[data-help='global.project.name']")
    name.fill(live()["name"] + " at night")
    name.press("Enter")
    page.wait_for_timeout(300)
    check(live()["slug"] == slug0, f"rename moved the folder although its takes were not read: {live()['slug']}")
    check(labels()[-1] == "Rename project", f"rename label: {labels()[-1:]}")
    undo()
    page.evaluate("window.__editor.store.update(p => { p.slug = 'untitled-ab12'; p.name = 'Untitled'; }, { label: 'test' })")
    page.wait_for_timeout(500)
    page.evaluate("window.__editor.store.setEph({ takes: { scenes: {} }, takesSlug: 'untitled-ab12' })")
    page.wait_for_timeout(100)
    name.fill("Night Ferry")
    name.press("Enter")
    page.wait_for_timeout(300)
    want_slug = page.evaluate("import('../web/rw/model.js').then(m => m.slugify('Night Ferry'))")
    check(live()["slug"] == want_slug, f"untitled folder did not follow the name: {live()['slug']}")
    undo()
    undo()
    check(live()["slug"] == slug0, f"undo of the rename: {live()['slug']}")

    # Global: profiles are read once even while progress events re-render the tab.
    page.evaluate("""() => { const h = window.__host, f = window.__fetch0; window.__profileCalls = 0;
      h.fetchApi = async (path, opts) => { if (path === '/reelwright/profiles') { window.__profileCalls++; await new Promise(r => setTimeout(r, 900)); } return f(path, opts); };
      window.__editor.eph.profiles = undefined; window.__editor.store.notify(); }""")
    page.evaluate("""async () => { for (let k = 0; k < 6; k++) { window.__host.emit('reelwright.progress', { slug: 'harbor_lights', scene_id: 's_07', pass: 1, passes: 3, step: k, steps: 28, phase: k % 2 ? 'encode' : 'sample' }); await new Promise(r => setTimeout(r, 100)); } }""")
    page.wait_for_timeout(1200)
    check(page.evaluate("window.__profileCalls") == 1, f"profile GETs while one was on its way: {page.evaluate('window.__profileCalls')}")
    page.evaluate("window.__host.fetchApi = window.__fetch0")
    prog("s_07", "done", pass_=3)

    # Script import: each new scene gets its own seed number; the answer's warnings are listed.
    page.evaluate("""() => { const h = window.__host, f = window.__fetch0;
      h.fetchApi = async (path, opts) => { const r = await f(path, opts); if (path !== '/reelwright/llm/script') return r;
        const j = await r.json(); j.warnings = ['scene 2: "shots" was text, not a list; it became one shot', 'cast 3 has no name, so it was left out'];
        return new Response(JSON.stringify(j), { status: r.status, headers: { 'Content-Type': 'application/json' } }); };
      window.__editor.store.setEph({ scriptDraft: null }); }""")
    page.wait_for_timeout(200)
    page.fill("textarea[data-help='global.script.text']", "| 01 | 00:01:00 | 8.00 | Verse | Ada lights a candle |\n| 02 | 00:02:00 | 6.00 | Verse | Ada opens the crypt |")
    page.click("button[data-help='global.script.run']")
    for _ in range(40):
        page.wait_for_timeout(250)
        if page.evaluate("!!window.__editor.eph.scriptDraft && !window.__editor.eph.scriptDraft.busy"):
            break
    wn = page.locator("[data-help='global.script.warnings']")
    check(wn.count() == 1 and "left out" in wn.inner_text(), "import warnings not shown")
    seeds0 = [s.get("seed_n") for s in live()["scenes"]]
    n0 = len(seeds0)
    page.locator("[data-help='global.script.mode'] button").filter(has_text="At the end").first.click()
    page.click("button[data-help='global.script.apply']")
    page.wait_for_timeout(400)
    new = [s.get("seed_n") for s in live()["scenes"][n0:]]
    check(len(new) == 2 and len(set(new)) == 2 and not set(new) & set(seeds0), f"imported seed numbers: {new} (existing {seeds0})")
    check(labels()[-1] == "Import script", f"import label: {labels()[-1:]}")
    undo()
    page.evaluate("window.__host.fetchApi = window.__fetch0; window.__editor.store.setEph({ scriptDraft: null })")

    # Files: Repair shows its result; new flags have labels; the pass cache has its own pick and "Not in the project"
    # leaves another project's scene alone; refused deletes show the server's reason; an asset file's delete also
    # removes its soundtrack track.
    page.click(".rw-tab:has-text('Files')")
    page.wait_for_selector(".rw-ftree-row")
    base = "o:reelwright/harbor_lights"
    page.evaluate("""b => window.__editor.store.setEph({ filesSel: {}, filesOpen: { 'p:harbor_lights': true, [b + '/scenes']: true, [b + '/scenes/s_05']: true,
      [b + '/cuts']: true, 'i:reelwright/harbor_lights': true } })""", base)
    page.wait_for_timeout(300)
    page.click("button[data-help='files.repair']")
    page.wait_for_timeout(600)
    rep = page.locator("[data-help='files.repair.result']")
    check(rep.count() == 1 and "14 takes found" in rep.inner_text() and "03 · " in rep.inner_text(), f"repair result: {rep.inner_text() if rep.count() else None}")
    flags = page.evaluate("[...document.querySelectorAll('.rw-ftree-flag')].map(e => e.textContent)")
    check("pass cache" in flags and "another project" in flags and "draft" in flags, f"flag labels: {sorted(set(flags))}")
    row = lambda rid: f".rw-ftree-row[data-id='{rid}']"
    checked = lambda rid: page.evaluate("id => !!document.querySelector(`.rw-ftree-row[data-id=\"${id}\"] .rw-ftree-check`)?.checked", rid)
    page.click("button[data-help='files.pick.cache']")
    page.wait_for_timeout(200)
    check(checked(base + "/scenes/s_05/passes"), "Pass cache pick did not select the pass cache")
    page.click("button[data-help='files.clear']")
    page.click("button[data-help='files.pick.orphans']")
    page.wait_for_timeout(200)
    check(page.locator(row(base + "/scenes/s_lk1")).count() == 1 and not checked(base + "/scenes/s_lk1"), "Not in the project picked another project's scene")
    page.click("button[data-help='files.clear']")
    page.evaluate("window.__mockFlags.filesBusy = 'a merge of this project is running; delete this when it ends'")
    cut = page.evaluate("[...document.querySelectorAll('.rw-ftree-row.k-cut')].find(r => r.querySelector(\"button[data-help='files.delete']\"))?.dataset.id")
    page.click(row(cut) + " button[data-help='files.delete']")
    page.wait_for_timeout(200)
    page.locator(".rw-modal button:has-text('Delete from disk')").click()
    page.wait_for_timeout(600)
    ref = page.locator("[data-help='files.refused']")
    check(ref.count() == 1 and "a merge of this project is running" in ref.inner_text() and "not deleted" in toasts(), f"refused delete: {ref.inner_text() if ref.count() else None} / {toasts()}")
    page.evaluate("window.__mockFlags.filesBusy = ''")
    page.screenshot(path=str(shots / "v060_files_repair.png"))
    track = [t for t in live()["soundtrack"] if t.get("asset")]
    aid = track[0]["asset"] if track else None
    afile = next((a["file"] for a in live()["assets"] if a["id"] == aid), None)
    if afile and page.locator(row("i:" + afile)).count():
        page.click(row("i:" + afile) + " button[data-help='files.delete']")
        page.wait_for_timeout(200)
        msg = page.locator(".rw-modal-msg").inner_text()
        check("soundtrack track" in msg, f"asset delete note: {msg!r}")
        page.locator(".rw-modal button:has-text('Delete from disk')").click()
        page.wait_for_timeout(700)
        pj = live()
        check(not any(t["asset"] == aid for t in pj["soundtrack"]) and not any(a["id"] == aid for a in pj["assets"]), "Files delete left the soundtrack track")
        undo()
        check(any(t["asset"] == aid for t in live()["soundtrack"]), "undo did not bring the track back")
    else:
        check(False, f"no asset row for the soundtrack asset {aid}")

    # Cast: deleting an outfit moves the scenes that wore it to the default outfit; deleting an entry asks in a dialog.
    page.click(".rw-tab:has-text('Cast')")
    page.evaluate("window.__editor.store.setEph({ selectedCast: 'c_mara' })")
    page.wait_for_timeout(300)
    wore = [s["id"] for s in live()["scenes"] if any(c["id"] == "c_mara" and c.get("outfit") == "o_oil" for c in s["cast"])]
    check(len(wore) >= 1, f"no scene wears o_oil: {wore}")
    out = page.locator(".rw-outfit", has=page.locator("input[data-key='outfit-o_oil']"))
    out.locator("button[data-help='cast.outfits.remove']").click()
    page.wait_for_timeout(300)
    pj = live()
    left = [s["id"] for s in pj["scenes"] if any(c.get("outfit") == "o_oil" for c in s["cast"])]
    now = [c.get("outfit") for s in pj["scenes"] if s["id"] in wore for c in s["cast"] if c["id"] == "c_mara"]
    check(not left and all(o == "" for o in now) and "o_oil" not in [o["id"] for o in pj["cast"][0]["outfits"]], f"outfit refs after delete: {left} {now}")
    check(labels()[-1].startswith("Delete outfit"), f"outfit label: {labels()[-1:]}")
    undo()
    check([s["id"] for s in live()["scenes"] if any(c.get("outfit") == "o_oil" for c in s["cast"])] == wore, "undo of the outfit delete")
    page.click("button[data-help='cast.delete']")
    page.wait_for_timeout(200)
    check(page.locator(".rw-modal").count() == 1 and page.locator(".rw-confirm").count() == 0 and "dialogue line" in page.locator(".rw-modal-msg").inner_text(), "cast delete dialog")
    page.locator(".rw-modal button:has-text('Cancel')").click()
    page.wait_for_timeout(200)

    # Assets: the preview stays the same element across re-renders; "From ComfyUI" closed during an import stays closed.
    page.click(".rw-tab:has-text('Assets')")
    page.evaluate("window.__editor.store.setEph({ selectedAsset: 'a_v1' })")
    page.wait_for_timeout(300)
    page.evaluate("document.querySelector('.rw-asset-preview').__mark = 1")
    for ph in ("encode", "sample", "decode", "done"):
        prog("s_07", ph, pass_=3)
    page.wait_for_timeout(400)
    check(page.evaluate("document.querySelector('.rw-asset-preview')?.__mark === 1"), "asset preview rebuilt by a re-render")
    page.evaluate("""() => { const h = window.__host, f = window.__fetch0;
      h.fetchApi = async (path, opts) => { if (path.startsWith('/reelwright/import')) await new Promise(r => setTimeout(r, 600)); return f(path, opts); }; }""")
    page.evaluate("window.__editor.store.setEph({ browse: null })")  # the button toggles; an earlier test may have left it open
    page.wait_for_timeout(150)
    page.click("button[data-help='assets.browse']")
    page.wait_for_timeout(400)
    page.click("button[data-help='assets.browse.root'] >> text=Output")  # output files are never "added" already
    page.wait_for_timeout(400)
    page.locator(".rw-browse-tile:not([disabled])").first.click()
    page.locator(".rw-browse button[data-help='assets.browse.add']").click()
    page.wait_for_timeout(100)
    page.locator(".rw-browse button[data-help='common.close']").click()
    page.wait_for_timeout(1000)
    check(page.locator(".rw-browse").count() == 0 and page.evaluate("window.__editor.eph.browse") is None, "From ComfyUI came back after closing it")
    page.evaluate("window.__host.fetchApi = window.__fetch0")
    page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
    page.wait_for_timeout(300)



# ---- added 2026-11-03 v0.6.0 review (second review, frontend fixes) ----
def review_checks(page, check, saved, shots):
    """v0.6.0 review: a renamed copy keeps its folder (separateProjectId), no folder dialog from a background autosave,
    the lanes after a big zoom-out, Auto-roll keeps the later scenes with capped tail overlaps, focus and text of a
    field across re-renders, variants progress counts takes, run warnings, typed text survives re-renders."""
    live = lambda: page.evaluate("JSON.parse(JSON.stringify(window.__editor.project))")
    emit = lambda ev, d: page.evaluate("([e, d]) => window.__host.emit(e, d)", [ev, d])
    queued = lambda: page.evaluate("window.__host.queued")
    toasts = lambda: page.locator(".rw-toast").all_inner_texts()
    active_key = lambda: page.evaluate("document.activeElement?.dataset?.key || document.activeElement?.className || ''")
    notify = lambda: (page.evaluate("window.__editor.store.notify()"), page.wait_for_timeout(150))
    S = "harbor_lights"

    def load():
        page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
        page.wait_for_timeout(300)

    def tab(name):
        page.click(f".rw-tab:has-text('{name}')")
        page.wait_for_timeout(300)

    if page.evaluate("window.__editor.eph.running"):
        emit("reelwright.run", {"slug": S, "phase": "end", "targets": [], "reused": [], "rendered": []})
    page.evaluate("window.__editor.store.setEph({ progress: {}, lastRun: null, toasts: [] })")
    load()

    # 1. A copy that has its own folder (renamed before v0.6.0) only gets a project id of its own: folder and scene ids
    # stay, nothing is announced, and the id is the same on every load of the same workflow.
    r = page.evaluate("""async () => { const ed = window.__editor; const before = JSON.parse(JSON.stringify(ed.project));
      const id1 = ed.separateProjectId(); ed.load(JSON.stringify(before)); const id2 = ed.separateProjectId();
      await new Promise(r => setTimeout(r, 400));
      return { before, id1, id2, after: JSON.parse(JSON.stringify(ed.project)), widget: JSON.parse(window.__host.getProject()).project_id }; }""")
    b0, a1 = r["before"], r["after"]
    check(r["id1"] == r["id2"] and r["id1"] != b0["project_id"] and a1["project_id"] == r["id1"] and r["widget"] == r["id1"]
          and a1["slug"] == b0["slug"] and [x["id"] for x in a1["scenes"]] == [x["id"] for x in b0["scenes"]]
          and not any("copy of another" in t for t in toasts()), f"separateProjectId: {r['id1']} {r['id2']} {b0['project_id']} {a1['slug']}")
    load()

    # 2. Output width/height have keys: typing the width's value into the height keeps focus in the height across a
    # re-render, and the next digit lands there too. A committed value shows as stored (1000 -> 992).
    tab("Global")
    width = live()["global"]["output"]["width"]
    hf = page.locator("input[data-key='out-height']")
    check(page.locator("input[data-key='out-width']").count() == 1 and hf.count() == 1, "output size fields have no keys")
    hf.click()
    hf.press("Control+a")
    page.keyboard.type(str(width), delay=20)
    notify()
    k1 = active_key()
    page.keyboard.type("0", delay=20)
    page.keyboard.press("Tab")
    page.wait_for_timeout(300)
    o = live()["global"]["output"]
    check(k1 == "out-height" and o["width"] == width and o["height"] == width * 10, f"focus jumped between the size fields: {k1} {o}")
    wf = page.locator("input[data-key='out-width']")
    wf.click()
    wf.press("Control+a")
    page.keyboard.type("1000", delay=20)
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    shown = page.evaluate("document.querySelector(\"input[data-key='out-width']\").value")
    check(live()["global"]["output"]["width"] == 992 and shown == "992" and active_key() == "out-width", f"stale text after a commit: stored {live()['global']['output']['width']}, shows {shown}")
    page.keyboard.press("Tab")
    page.wait_for_timeout(300)
    check(live()["global"]["output"]["width"] == 992, "width changed by leaving the field")
    # Tab into the next number field selects its text; the commit's re-render keeps it selected, so typing replaces it
    wf = page.locator("input[data-key='out-width']")
    wf.click()
    wf.press("Control+a")
    page.keyboard.type("1024", delay=20)
    page.keyboard.press("Tab")
    page.wait_for_timeout(300)
    page.keyboard.type("512", delay=20)
    page.keyboard.press("Tab")
    page.wait_for_timeout(300)
    o = live()["global"]["output"]
    check((o["width"], o["height"]) == (1024, 512), f"Tab into a number field: {o['width']} x {o['height']}")
    load()

    # 3. Typed text survives re-renders (the flaky 'inspector edits'): a "-" typed into a number field, a select-all
    # before typing, Playwright's fill (focus + select, then insert) with a render in between. The body is not rebuilt
    # while the field holds unsaved typing (the footer still is), and is rebuilt after Enter.
    tab("Timeline")
    page.evaluate("() => window.__editor.store.setEph({ selectedTrack: window.__editor.project.soundtrack[0].id, selectedMarker: null })")
    page.wait_for_timeout(300)
    lvl = ".rw-track-insp input[data-key^='trk-volume_db']"

    def reset_level():
        page.evaluate("() => window.__editor.store.update(p => { p.soundtrack[0].volume_db = 0; }, { label: 'reset' })")
        page.wait_for_timeout(700)

    vol = lambda: page.evaluate("window.__editor.project.soundtrack[0].volume_db")
    reset_level()
    f = page.locator(lvl)
    f.click()
    f.press("Control+a")
    page.keyboard.type("-", delay=20)
    page.evaluate(f"document.querySelector(\"{lvl}\").__mark = 1")
    page.evaluate("window.__editor.store.setEph({ saveState: 'offline', saveError: 'test' })")
    page.wait_for_timeout(150)
    kept = page.evaluate(f"document.querySelector(\"{lvl}\").__mark === 1")
    foot = page.inner_text(".rw-footer")
    page.keyboard.type("6", delay=20)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    rebuilt = page.evaluate(f"document.querySelector(\"{lvl}\").__mark !== 1")
    check(kept and "Autosave offline" in foot and vol() == -6 and rebuilt, f"typing across a render: kept {kept}, footer {foot[-40:]!r}, stored {vol()}, rebuilt {rebuilt}")
    page.evaluate("window.__editor.store.setEph({ saveState: 'saved', saveError: '' })")
    reset_level()
    page.locator(".rw-root").focus()  # fill() starts from a field that is not focused (as in 'inspector edits')
    page.wait_for_timeout(100)
    page.evaluate("""async () => { const el = document.querySelector(".rw-track-insp input[data-key^='trk-volume_db']");
      el.focus(); el.select(); window.__editor.store.notify(); await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }""")
    page.keyboard.insert_text("-6")
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    check(vol() == -6, f"fill with a render between focus and insert: stored {vol()}")
    reset_level()
    f = page.locator(lvl)
    f.click()
    f.press("Control+a")
    notify()
    page.keyboard.type("-9", delay=20)
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    check(vol() == -9, f"select-all, a render, typing: stored {vol()}")
    # a field that stores as it is typed (asset search) still re-renders its list while typing
    tab("Assets")
    n_all = page.locator(".rw-asset-card").count()
    page.locator("input[data-key='asset-q']").click()
    page.keyboard.type("zzzz-none", delay=10)
    page.wait_for_timeout(300)
    n_q = page.locator(".rw-asset-card").count()
    check(n_all > 0 and n_q < n_all, f"asset search did not filter while typing: {n_all} -> {n_q}")
    page.evaluate("window.__editor.store.setEph({ assetQuery: '' })")
    page.locator(".rw-root").focus()
    load()

    # 4. A folder conflict found by the background autosave opens no dialog while typing: the footer shows "Folder
    # in use" and one toast says so. Render (an explicit action) opens the dialog first, with "Decide later" focused.
    page.evaluate("window.__mockFlags.slugConflict = 'harbor_lights'; window.__mockFlags.autosaves.length = 0")
    page.evaluate("window.__editor.store.setEph({ toasts: [] })")
    tab("Scene")
    ta = page.locator(".rw-psec").nth(1).locator("textarea")
    ta.click()
    ta.press("End")
    page.keyboard.type(" The candle", delay=25)
    page.wait_for_timeout(4800)
    mid = page.evaluate("() => ({ dialog: !!document.querySelector('.rw-modal'), foot: !!document.querySelector(\".rw-footer [data-help='footer.saveConflict']\") })")
    page.keyboard.type(" flickers", delay=25)
    page.wait_for_timeout(600)
    summ = page.evaluate("window.__editor.project.scenes.find(s => s.id === window.__editor.project.ui.selected).prompt.sections.summary")
    notes = [t for t in toasts() if "Autosave paused" in t]
    check(not mid["dialog"] and mid["foot"] and page.locator(".rw-modal").count() == 0 and live()["slug"] == S
          and summ.endswith("The candle flickers") and len(notes) == 1, f"background folder conflict: {mid} {summ[-30:]!r} {notes}")
    n_q0 = len(queued())
    page.locator(".rw-root").focus()
    page.click("button[data-help='app.renderPending']")
    page.wait_for_timeout(300)
    check(page.locator(".rw-modal").count() == 1 and page.evaluate("document.activeElement.textContent") == "Decide later", "Render did not ask about the folder first")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    check(len(queued()) == n_q0 and page.locator(".rw-modal").count() == 0, "a render was queued into a folder in use")
    page.locator(".rw-footer [data-help='footer.saveConflict']").click()
    page.wait_for_timeout(300)
    page.locator(".rw-modal button:has-text('Use a separate project')").click()
    page.wait_for_timeout(500)
    check(live()["slug"] == "harbor_lights-2" and page.evaluate("window.__editor.eph.saveState") == "saved", f"footer -> separate project: {live()['slug']}")
    page.evaluate("window.__mockFlags.slugConflict = ''")
    load()

    # 5. A big zoom-out (the zoom slider from 160 to 8 px/s in one change) shows every scene, not empty lanes.
    tab("Timeline")
    page.evaluate("() => window.__editor.store.update(p => { p.ui.zoom = 160; }, { history: false, plan: false })")
    page.wait_for_timeout(400)
    page.evaluate("() => { const el = document.querySelector('.rw-lanes'); el.scrollLeft = el.scrollWidth; }")
    page.wait_for_timeout(500)
    page.evaluate("""() => { const s = document.querySelector("input.rw-range[data-help='timeline.zoom']"); s.value = 8; s.dispatchEvent(new Event('change', { bubbles: true })); }""")
    page.wait_for_timeout(800)
    zv = page.evaluate("""() => { const el = document.querySelector('.rw-lanes'); const r = el.getBoundingClientRect();
      const vis = [...document.querySelectorAll('.rw-scene')].filter(b => { const q = b.getBoundingClientRect(); return q.right > r.left + 150 && q.left < r.right; });
      return { visible: vis.length, scenes: window.__editor.project.scenes.length }; }""")
    check(zv["visible"] == zv["scenes"], f"lanes empty after a big zoom-out: {zv}")
    page.evaluate("() => window.__editor.store.update(p => { p.ui.zoom = 22; }, { history: false, plan: false })")
    page.wait_for_timeout(300)

    # 6. Auto-roll keeps every later scene where it is when the tail overlap at a seam is capped by a short scene;
    # a roll that cannot keep them is clamped (the later scenes still stay).
    r = page.evaluate("""async () => {
      const M = await import('../web/rw/model.js'), T = await import('../web/rw/tabs/timeline.js');
      const ed = window.__editor;
      ed.store.update(p => { p.scenes[1].duration = 1.5; }, { label: 'setup' });
      const ctx = { get p() { return ed.project; }, actions: ed.actions };
      const at = () => { const t = M.sceneStarts(ed.project); return ed.project.scenes.map(s => t.starts[s.id]); };
      const auto = T.autoRollOn(ed.project), before = at(), t0 = performance.now();
      T.setSceneDuration(ctx, 's_02', 2.5);
      const ms = performance.now() - t0, after = at(), d2 = ed.project.scenes[1].duration;
      T.setSceneDuration(ctx, 's_02', 400);
      const far = at(), d2far = ed.project.scenes[1].duration;
      return { auto, before, after, far, d2, d2far, ms }; }""")
    same = lambda a, b: all(abs(x - y) < 1e-6 for x, y in zip(a[3:], b[3:]))
    check(r["auto"] and abs(r["d2"] - 2.5) < 1e-9 and same(r["before"], r["after"]) and same(r["before"], r["far"]) and r["d2far"] < 400,
          f"auto-roll moved later scenes: {r}")
    check(r["ms"] < 50, f"auto-roll took {r['ms']:.1f} ms")
    load()

    # 7. Variants (n takes of one scene, a "done" after every take): the title and the banner count takes, the scene
    # is not done between takes; the end event's warnings show in the toast and the Render tab's last-run banner.
    page.evaluate("() => window.__editor.actions.run('variants', [], { scene_ids: ['s_07'], n: 3 })")
    page.wait_for_timeout(200)
    page.evaluate("window.__host.titles.length = 0")
    vp = lambda ph, pass_=1, step=0: emit("reelwright.progress", {"slug": S, "scene_id": "s_07", "pass": pass_, "passes": 3, "phase": ph, "step": step, "steps": 20 if step else 0})
    emit("reelwright.run", {"slug": S, "run_id": "rv", "phase": "start", "targets": ["s_07"], "reused": []})
    vp("encode")
    vp("sample", step=10)
    vp("done", pass_=3)
    vp("encode")
    vp("sample", step=5)
    page.wait_for_timeout(300)
    t1 = page.evaluate("window.__host.titles.at(-1)")
    tab("Render")
    head = page.evaluate("document.querySelector('.rw-run-head')?.textContent || ''")
    vp("done", pass_=3)
    page.wait_for_timeout(200)
    between = page.evaluate("[window.__editor.eph.progress.s_07.phase, window.__host.titles.at(-1)]")
    check(t1.startswith("rendering 2/3") and "100%" not in t1 and head == "Take 2 of 3" and between[0] != "done" and between[1].startswith("rendering 3/3"),
          f"variants progress: {t1!r} {head!r} {between}")
    vp("encode")
    vp("done", pass_=3)
    emit("reelwright.run", {"slug": S, "run_id": "rv", "phase": "end", "targets": ["s_07"], "rendered": ["s_07"], "failed": [], "skipped": [], "reused": [],
                            "warnings": [{"scene_id": "s_07", "message": "variant 3 of 3 failed: out of memory"}], "interrupted": False})
    page.wait_for_timeout(400)
    note = page.locator("[data-help='render.lastRun']")
    check(any("1 warning" in t and "variant 3 of 3 failed" in t for t in toasts()) and note.count() == 1 and "1 warning" in note.inner_text()
          and "variant 3 of 3 failed" in note.inner_text() and note.locator("button[data-help='render.lastRun.retry']").count() == 0,
          f"run warnings: {toasts()} {note.count()}")
    page.screenshot(path=str(shots / "v060_review_warnings.png"))
    page.evaluate("window.__editor.store.setEph({ lastRun: null, progress: {} })")
    load()


# ---- added 2026-11-04 v0.6.1 (third review, frontend) ----
# The mock's fetchApi is wrapped: each /autosave waits a chosen delay before the "server" handles it (so requests that
# overlap would land out of order) and the project name of every handled request is recorded (the disk).
AUTOSAVE_WRAP = """() => {
  const h = window.__host;
  if (!h.__realFetch) h.__realFetch = h.fetchApi;
  const real = h.__realFetch.bind(h);
  window.__as = { disk: [], sent: [], inflight: 0, maxIn: 0, delays: [], fails: [] };
  h.fetchApi = async (path, opts) => {
    if (path !== '/reelwright/autosave') return real(path, opts);
    const t = window.__as, body = JSON.parse(opts.body);
    t.sent.push(body.project.name);
    const d = t.delays.length ? t.delays.shift() : 0, fail = t.fails.length ? t.fails.shift() : false;
    t.inflight++; t.maxIn = Math.max(t.maxIn, t.inflight);
    await new Promise(r => setTimeout(r, d));
    t.inflight--;
    t.disk.push(body.project.name);
    if (fail) return new Response(JSON.stringify({ error: 'Disk full' }), { status: 500 });
    return real(path, opts);
  };
}"""
AUTOSAVE_UNWRAP = "() => { const h = window.__host; if (h.__realFetch) { h.fetchApi = h.__realFetch; delete h.__realFetch; } }"


def v061_checks(page, check, saved, shots):
    """v0.6.1 (third review): autosaves one at a time (F1), shortcuts ignore Ctrl/Cmd/Alt and Shift+letter (F2), a
    split keeps the frame count (F3), an unknown afterId appends (F4), a throwing edit is rolled back and promoting a
    frame of a deleted cast member (F5), Propose scenes starts once (F7), the asset browser's filter timer and the
    autocomplete highlight (minor)."""
    live = lambda: page.evaluate("JSON.parse(JSON.stringify(window.__editor.project))")
    S = "harbor_lights"

    def load():
        page.evaluate("window.__editor.load(%s)" % json.dumps(saved))
        page.wait_for_timeout(300)

    def tab(name):
        page.click(f".rw-tab:has-text('{name}')")
        page.wait_for_timeout(300)

    def saves(js):
        return page.evaluate("async () => { const ed = window.__editor, st = ed.store, t = window.__as; t.disk = []; t.sent = []; t.maxIn = 0;"
                             " const name = n => st.update(p => { p.name = n; }, { label: 'Rename' }); const wait = ms => new Promise(r => setTimeout(r, ms));"
                             + js + " }")

    page.evaluate("window.__editor.store.setEph({ toasts: [], saveState: 'saved', saveError: '', conflict: null })")
    load()

    # F1. Autosaves never overlap: a save asked for while one is on its way follows it with the latest state, so the
    # disk ends with the newest project; a late failure of the older request does not mark a newer success offline.
    page.evaluate(AUTOSAVE_WRAP)
    r = saves("""t.delays = [600, 40];
      name('A'); const p1 = st.saveNow(); await wait(30); name('B'); const p2 = st.saveNow();
      const [r1, r2] = await Promise.all([p1, p2]); await wait(80);
      return { sent: t.sent, disk: t.disk, maxIn: t.maxIn, r1, r2, state: ed.eph.saveState };""")
    check(r["maxIn"] == 1 and r["disk"] == ["A", "B"] and r["r1"]["ok"] and r["r2"]["ok"] and r["state"] == "saved", f"Ctrl+S on top of a running save: {r}")
    r = saves("""t.delays = [600, 40, 40, 40]; t.fails = [true, false];
      name('E'); const p1 = st.saveNow(); await wait(30); name('F'); const p2 = st.saveNow(); await wait(20); const p3 = st.saveNow(); const p4 = st.saveNow();
      const [r1, r2, r3, r4] = await Promise.all([p1, p2, p3, p4]); await wait(80);
      return { sent: t.sent, disk: t.disk, maxIn: t.maxIn, r1, r2, r3, r4, state: ed.eph.saveState, err: ed.eph.saveError };""")
    check(r["maxIn"] == 1 and r["sent"] == ["E", "F"] and not r["r1"]["ok"] and r["r2"]["ok"] and r["r3"]["ok"] and r["r4"]["ok"]
          and r["state"] == "saved" and r["err"] == "", f"late error of an older save / waiting saves merged: {r}")
    # the 4 s debounce fires while a slow save runs: it waits for it
    r = saves("""t.delays = [4400, 40];
      name('C'); const p1 = st.saveNow(); await wait(30); name('D'); const mid = ed.eph.saveState;
      await p1; const after1 = ed.eph.saveState; await wait(300);
      return { sent: t.sent, disk: t.disk, maxIn: t.maxIn, mid, after1, state: ed.eph.saveState };""")
    check(r["maxIn"] == 1 and r["disk"] == ["C", "D"] and r["after1"] == "pending" and r["state"] == "saved", f"debounce during a slow save: {r}")
    # 409 slug_conflict still opens one dialog for Ctrl+S (also when it waited for another save) and pauses autosaving
    page.evaluate("window.__mockFlags.slugConflict = 'harbor_lights'; window.__editor.store.setEph({ toasts: [] })")
    r = saves("""t.delays = [400, 20];
      name('G'); const p1 = st.saveNow(); await wait(20); name('H'); const p2 = st.saveNow();
      const [r1, r2] = await Promise.all([p1, p2]); await wait(200);
      return { disk: t.disk, maxIn: t.maxIn, r1, r2, state: ed.eph.saveState, slug: ed.eph.conflict?.slug, modals: document.querySelectorAll('.rw-modal').length };""")
    check(r["maxIn"] == 1 and r["r1"].get("conflict") and r["r2"].get("conflict") and r["state"] == "conflict" and r["slug"] == S and r["modals"] == 1,
          f"folder conflict with queued saves: {r}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.evaluate("window.__mockFlags.slugConflict = ''")
    # dispose: the last edit goes after the save on its way
    r = page.evaluate("""async () => {
      const { mountEditor } = await import('../web/rw/editor.js');
      const h = window.__host, t = window.__as;
      let json = JSON.stringify(JSON.parse(h.getProject()));
      const h2 = Object.create(h); h2.getProject = () => json; h2.setProject = j => { json = j; };
      const div = document.createElement('div'); div.style.cssText = 'position:absolute;left:-4000px;top:0;width:1200px;height:800px';
      document.body.appendChild(div);
      const ed = mountEditor(div, h2);
      await new Promise(r => setTimeout(r, 100));
      t.disk = []; t.maxIn = 0; t.delays = [500, 20];
      ed.store.update(p => { p.name = 'T1'; }, { label: 'Rename' }); ed.store.saveNow();
      await new Promise(r => setTimeout(r, 30));
      ed.store.update(p => { p.name = 'T2'; }, { label: 'Rename' }); ed.destroy();
      await new Promise(r => setTimeout(r, 800));
      div.remove();
      return { disk: t.disk, maxIn: t.maxIn }; }""")
    check(r["disk"] == ["T1", "T2"] and r["maxIn"] == 1, f"dispose sent its last edit on top of a running save: {r}")
    page.evaluate(AUTOSAVE_UNWRAP)
    page.evaluate("window.__editor.store.setEph({ toasts: [], saveState: 'saved', saveError: '', conflict: null })")
    load()

    # F2. Ctrl/Cmd/Alt + a shortcut key reaches the browser, not the timeline; Shift+letter is not the letter. The
    # plain keys, Shift+arrow (1 s), + (Shift+=) and a Caps Lock letter still work.
    tab("Timeline")
    look = "() => { const ed = window.__editor, p = ed.project; return { n: p.scenes.length, playhead: p.ui.playhead, playing: !!ed.eph.playing, markers: (p.markers || []).length, zoom: p.ui.zoom, loop: ed.eph.loop || null, sel: p.ui.selected }; }"

    def ready():
        page.evaluate("() => { window.__editor.store.update(p => { p.ui.tab = 'timeline'; p.ui.selected = 's_03'; p.ui.playhead = 21.375; p.ui.zoom = 13; }, { history: false, plan: false }); window.__editor.store.setEph({ loop: null }); }")
        page.wait_for_timeout(150)
        page.locator(".rw-root").focus()
        return page.evaluate(look)

    before = ready()
    combos = ["Control+d", "Meta+d", "Alt+d", "Shift+D", "Control+j", "Control+l", "Shift+J", "Control+k", "Control+ArrowLeft", "Meta+ArrowLeft",
              "Alt+ArrowRight", "Control+Home", "Control+End", "Shift+S", "Control+s", "Shift+N", "Control+n", "Control+m", "Shift+M", "Control+i", "Shift+O",
              "Control+Minus", "Control+Equal", "Alt+Delete"]
    moved = []
    for c in combos:
        page.keyboard.press(c)
        page.wait_for_timeout(60)
        now = page.evaluate(look)
        if now != before:
            moved.append((c, {k: (before[k], now[k]) for k in now if now[k] != before[k]}))
            before = ready()
    page.wait_for_timeout(300)
    check(not moved and page.locator(".rw-modal").count() == 0, f"modifier combos reached the shortcuts: {moved}")
    effects = {}
    for c in ["d", "j", "Shift+ArrowLeft", "ArrowLeft", "Shift+Equal", "m", "i"]:
        b0 = ready()
        page.keyboard.press(c)
        page.wait_for_timeout(150)
        a0 = page.evaluate(look)
        effects[c] = {k: (b0[k], a0[k]) for k in a0 if a0[k] != b0[k]}
        load()
    b0 = ready()
    page.evaluate("() => document.querySelector('.rw-keys').dispatchEvent(new KeyboardEvent('keydown', { key: 'S', code: 'KeyS', bubbles: true, cancelable: true }))")
    page.wait_for_timeout(150)
    effects["CapsLock S"] = {"n": (b0["n"], page.evaluate(look)["n"])}  # e.key "S" without Shift
    load()
    after = lambda c, k: effects[c].get(k, (None, None))
    near = lambda v, want: v is not None and abs(v - want) < 1e-9
    plus1 = lambda c, k: after(c, k)[0] is not None and after(c, k)[1] == after(c, k)[0] + 1
    ok = (plus1("d", "n") and near(after("j", "playhead")[1], 20.375) and near(after("Shift+ArrowLeft", "playhead")[1], 20.375)
          and near(after("ArrowLeft", "playhead")[1], 21.375 - 1 / 24) and (after("Shift+Equal", "zoom")[1] or 0) > 13
          and plus1("m", "markers") and after("i", "loop")[1] and plus1("CapsLock S", "n"))
    check(ok, f"plain shortcuts: {effects}")

    # F3. Splitting a scene of exactly n + 1/2 frames (n even: the model counts n) keeps n frames in the film.
    r = page.evaluate("""async () => {
      const M = await import('../web/rw/model.js'); const ed = window.__editor; const out = [];
      for (const d of [1.9375, 0.6875, 4.0625]) {
        ed.store.update(p => { const s = p.scenes.find(x => x.id === 's_03'); s.duration = d; s.shots = []; s.dialogue = []; }, { label: 'setup' });
        ed.actions.splitScene('s_03', d / 2);
        const i = ed.project.scenes.findIndex(x => x.id === 's_03'), a = ed.project.scenes[i], b = ed.project.scenes[i + 1];
        out.push([M.framesOf(d), M.framesOf(a.duration) + M.framesOf(b.duration) - 1]);
        ed.store.undo(); ed.store.undo();
      }
      return out; }""")
    check(all(x == y for x, y in r), f"split changed the frame count (want, got): {r}")
    load()

    # F4. addScene / insertScenes after an id that is no longer in the project put the scene at the end.
    r = page.evaluate("""() => { const ed = window.__editor, n = ed.project.scenes.length;
      ed.actions.addScene('s_gone'); const a = ed.project.scenes.findIndex(s => s.id === ed.project.ui.selected); ed.store.undo();
      const ids = ed.actions.insertScenes([JSON.parse(JSON.stringify(ed.project.scenes[2]))], 's_gone'); const b = ed.project.scenes.findIndex(s => s.id === ids[0]); ed.store.undo();
      ed.actions.addScene('s_02'); const c = ed.project.scenes.findIndex(s => s.id === ed.project.ui.selected); ed.store.undo();
      return { n, a, b, c }; }""")
    check(r["a"] == r["n"] and r["b"] == r["n"] and r["c"] == 2, f"stale afterId: {r}")
    load()

    # F5. A mutator that throws changes nothing (state, undo and redo lists); the error reaches the caller.
    r = page.evaluate("""() => { const ed = window.__editor, st = ed.store;
      st.update(p => { p.name = 'one'; }, { label: 'one' }); st.update(p => { p.name = 'two'; }, { label: 'two' }); st.undo();
      const h0 = JSON.stringify(st.history()), v0 = ed.project.__rwv;
      let threw = '';
      try { st.update(p => { p.name = 'half'; p.scenes.pop(); throw new Error('boom'); }, { label: 'bad' }); } catch (e) { threw = e.message; }
      return { threw, name: ed.project.name, scenes: ed.project.scenes.length, same: JSON.stringify(st.history()) === h0, canRedo: st.canRedo(), stamped: ed.project.__rwv !== v0 }; }""")
    check(r["threw"] == "boom" and r["name"] == "one" and r["scenes"] == len(json.loads(saved)["scenes"]) and r["same"] and r["canRedo"] and r["stamped"],
          f"throwing edit not rolled back: {r}")
    load()
    # Cast: promote a frame while the cast member is deleted: the frame joins the assets (saved), no anchor, a warning
    page.evaluate("""() => { const h = window.__host; if (!h.__realFetch) h.__realFetch = h.fetchApi; const real = h.__realFetch.bind(h);
      h.fetchApi = async (path, opts) => { if (path === '/reelwright/promote_frame') await new Promise(r => setTimeout(r, 400)); return real(path, opts); }; }""")
    tab("Cast")
    cid = page.evaluate("window.__editor.project.cast[0].id")
    page.evaluate("id => window.__editor.store.setEph({ selectedCast: id, toasts: [] })", cid)
    page.wait_for_timeout(300)
    n_assets = len(live()["assets"])
    page.locator("button[data-help='cast.promote']").first.click()
    page.wait_for_timeout(80)
    page.evaluate("id => window.__editor.store.update(p => { p.cast = p.cast.filter(c => c.id !== id); }, { label: 'Delete cast' })", cid)
    page.wait_for_timeout(800)
    toast = [t["message"] for t in page.evaluate("window.__editor.eph.toasts")]
    widget = json.loads(page.evaluate("window.__host.getProject()"))
    check(len(live()["assets"]) == n_assets + 1 and len(widget["assets"]) == n_assets + 1 and any("not an anchor" in t for t in toast)
          and not any("Could not promote" in t for t in toast), f"promote after the cast member was deleted: {toast}")
    page.evaluate(AUTOSAVE_UNWRAP)
    load()

    # F7. "Propose scenes" starts once: the button is disabled while the script is cut into parts.
    page.evaluate("""() => { const h = window.__host; if (!h.__realFetch) h.__realFetch = h.fetchApi; const real = h.__realFetch.bind(h); window.__llm = [];
      h.fetchApi = async (path, opts) => { if (path.startsWith('/reelwright/llm/script')) window.__llm.push(path);
        if (path === '/reelwright/llm/script/parts') await new Promise(r => setTimeout(r, 400)); return real(path, opts); }; }""")
    tab("Global")
    page.evaluate("window.__editor.store.setEph({ scriptDraft: null })")
    page.wait_for_timeout(200)
    rows = "\n".join(f"| {i:02d} | 00:{i:02d}:00 | 8.00 | Verse | Ada walks past grave number {i} |" for i in range(1, 4))
    page.fill("textarea[data-help='global.script.text']", "Ada sings.\n\n" + rows)
    run = page.locator("button[data-help='global.script.run']")
    run.click()
    page.wait_for_timeout(120)
    disabled = run.is_disabled()
    run.click(force=True)
    for _ in range(60):
        page.wait_for_timeout(200)
        if page.evaluate("!!window.__editor.eph.scriptDraft && !window.__editor.eph.scriptDraft.busy"):
            break
    calls = page.evaluate("window.__llm")
    check(disabled and calls.count("/reelwright/llm/script/parts") == 1 and calls.count("/reelwright/llm/script") == 1, f"Propose scenes twice: disabled {disabled}, {calls}")
    page.evaluate(AUTOSAVE_UNWRAP)
    page.evaluate("window.__editor.store.setEph({ scriptDraft: null, scriptText: '' })")
    load()

    # Minor: the asset browser's filter timer never reopens a closed card, and survives a re-render (one request)
    page.evaluate("""() => { const h = window.__host; if (!h.__realFetch) h.__realFetch = h.fetchApi; const real = h.__realFetch.bind(h); window.__fq = [];
      h.fetchApi = async (path, opts) => { if (path.startsWith('/reelwright/files?')) window.__fq.push(new URL(path, 'http://x').searchParams.get('q')); return real(path, opts); }; }""")
    tab("Assets")
    page.click("button[data-help='assets.browse']")
    page.wait_for_timeout(400)
    page.locator("input[data-help='assets.browse.search']").click()
    page.keyboard.type("ab", delay=20)
    page.locator(".rw-browse button[data-help='common.close']").first.click()
    page.wait_for_timeout(600)
    reopened = page.evaluate("!!window.__editor.eph.browse")
    page.click("button[data-help='assets.browse']")
    page.wait_for_timeout(400)
    page.evaluate("window.__fq.length = 0")
    page.locator("input[data-help='assets.browse.search']").click()
    page.keyboard.type("x", delay=10)
    page.evaluate("window.__editor.store.notify()")
    page.wait_for_timeout(60)
    page.keyboard.type("y", delay=10)
    page.wait_for_timeout(700)
    fq = page.evaluate("window.__fq")
    check(not reopened and fq == ["xy"], f"asset browser filter timer: reopened {reopened}, requests {fq}")
    page.evaluate(AUTOSAVE_UNWRAP)
    page.evaluate("window.__editor.store.setEph({ browse: null })")
    page.locator(".rw-root").focus()

    # Minor: the autocomplete highlight goes back to the best match when the query changes and in the next list
    tab("Scene")
    ta = page.locator(".rw-psec").nth(1).locator("textarea")
    ta.click()
    ta.press("End")
    t0 = page.evaluate("document.querySelectorAll('.rw-psec')[1].querySelector('textarea').value")
    ta.type(" @", delay=30)
    page.wait_for_timeout(150)
    hi = lambda: page.evaluate("[...document.querySelectorAll('.rw-ac.on .rw-ac-item')].findIndex(e => e.classList.contains('on'))")
    for _ in range(3):
        page.keyboard.press("ArrowDown")
    down = hi()
    ta.type("P", delay=30)
    page.wait_for_timeout(150)
    narrowed, first = hi(), page.locator(".rw-ac.on .rw-ac-item b").first.inner_text()
    page.keyboard.press("Enter")
    page.wait_for_timeout(150)
    ta.type(" @", delay=30)
    page.wait_for_timeout(150)
    nxt = hi()
    page.keyboard.press("Escape")
    text = page.evaluate("document.querySelectorAll('.rw-psec')[1].querySelector('textarea').value")
    check(down == 3 and narrowed == 0 and nxt == 0 and text == f"{t0} {first}  @", f"autocomplete highlight: {down} {narrowed} {nxt} {first!r} {text[-20:]!r}")
    page.locator(".rw-root").focus()
    load()


if __name__ == "__main__":
    sys.exit(main())
