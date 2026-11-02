Mock harness for the editor: `harness.html` loads the real `web/rw` modules with a fake ComfyUI host and canned `/reelwright/*` responses from `mock.js`.

```
python3 web-test/shoot.py      # screenshots of every tab into web-test/shots/, fails on console errors or missing help texts
python3 web-test/interact.py   # clicks through editing, undo, rewrite and render flows
```
