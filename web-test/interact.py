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
