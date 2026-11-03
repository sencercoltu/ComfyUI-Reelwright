"""Screenshot every editor tab in the mock harness and check help coverage.

Run from anywhere: python3 web-test/shoot.py
Writes PNGs to web-test/shots/ and prints console errors, missing help ids and
controls without a tooltip.
"""

import functools
import http.server
import pathlib
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = ROOT / "web-test" / "shots"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


AUDIT = """async () => {
  const { HELP } = await import('/web/rw/help.js');
  const root = document.querySelector('.rw-root');
  const ids = [...root.querySelectorAll('[data-help]')].map(e => e.dataset.help);
  const more = [...root.querySelectorAll('[data-more]')].map(e => e.dataset.more);
  const missing = [...new Set(ids.filter(i => !HELP[i]))];
  const noMore = [...new Set(more.filter(i => !HELP[i] || !HELP[i].more))];
  const bare = [...root.querySelectorAll('button, input, select, textarea')]
    .filter(e => !e.closest('[data-help]') && e.offsetParent !== null)
    .map(e => e.outerHTML.slice(0, 120));
  return { missing, noMore, bare };
}"""


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    httpd = serve()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/web-test/harness.html"
    errors, problems = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_selector(".rw-root")
        page.wait_for_timeout(900)

        def audit(name):
            r = page.evaluate(AUDIT)
            for k in ("missing", "noMore", "bare"):
                for item in r[k]:
                    problems.append(f"{name}: {k}: {item}")

        # [OLD 2026-11-03 v0.3.9->v0.4.0] for tab in ["Timeline", "Scene", "Assets", "Cast", "Render", "Global"]:
        for tab in ["Timeline", "Scene", "Assets", "Cast", "Render", "Files", "Global"]:  # Files added 2026-11-03 v0.4.0
            page.click(f".rw-tab:has-text('{tab}')")
            page.mouse.move(1590, 990)
            page.wait_for_timeout(500)
            page.screenshot(path=str(SHOTS / f"{tab.lower()}.png"))
            audit(tab)

        page.click(".rw-tab:has-text('Timeline')")
        page.click(".rw-scene:has-text('The long walk home')")
        page.click(".rw-tab:has-text('Scene')")
        page.mouse.move(1590, 990)
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOTS / "scene_long.png"))
        audit("Scene long")

        page.click(".rw-tab:has-text('Timeline')")
        page.click(".rw-scene:has-text('Insert')")
        page.click(".rw-tab:has-text('Scene')")
        page.mouse.move(1590, 990)
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOTS / "scene_short.png"))

        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        page.hover(".rw-tl-toolbar .rw-toggle-row >> nth=0")
        page.wait_for_timeout(700)
        page.screenshot(path=str(SHOTS / "tooltip.png"))
        page.mouse.move(5, 5)
        page.click(".rw-tl-toolbar .rw-q")
        page.wait_for_timeout(300)
        page.screenshot(path=str(SHOTS / "popover.png"))
        page.keyboard.press("Escape")

        page.click(".rw-tab:has-text('Scene')")
        page.wait_for_timeout(300)
        page.click(".rw-card-dlg .rw-btn-pink")
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOTS / "rewrite.png"), full_page=False)

        page.click(".rw-tab:has-text('Render')")
        page.wait_for_timeout(300)
        page.click(".rw-trow:has-text('Mara on the pier') .link.mono")
        page.wait_for_timeout(300)
        page.click(".rw-merge .rw-btn-primary")
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOTS / "render_open.png"))

        page.click(".rw-tab:has-text('Timeline')")
        page.wait_for_timeout(300)
        page.click(".rw-tabbar button:has-text('issue')")
        page.wait_for_timeout(300)
        page.screenshot(path=str(SHOTS / "issues.png"))
        browser.close()
    httpd.shutdown()

    print("console errors:", len(errors))
    for e in errors:
        print("  ", e)
    print("help problems:", len(problems))
    for pr in problems[:80]:
        print("  ", pr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
