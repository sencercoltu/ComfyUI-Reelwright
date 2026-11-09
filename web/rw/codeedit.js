// Prompt editor: a textarea over a highlighted <pre>, with @tag autocomplete.

import { h } from "./ui.js";
import { highlightHTML } from "./prompttext.js";

/* [OLD 2026-11-05 v0.7.0->v0.8.0] one look (mono); shot and dialogue texts use it now in a text font
export function codeEditor({ value, onInput, onChange, key, help, candidates, placeholder, minRows = 3, maxHeight = 220 }) {
  const pre = h("pre", { class: "rw-code-hl mono", "aria-hidden": "true", html: highlightHTML(value) });
  const list = h("div", { class: "rw-ac", role: "listbox" });
  const ta = h("textarea", {
    class: "rw-code-ta mono", key, help, placeholder, spellcheck: "false", rows: minRows, value: value ?? "",
    dataset: { scroll: key },
  });
  const wrap = h("div", { class: "rw-code", style: { "max-height": maxHeight + "px" } }, pre, ta, list);
[/OLD] */
// added 2026-11-05 v0.8.0: cls (an extra class on the box: "sans" for shot and dialogue texts), spellcheck
export function codeEditor({ value, onInput, onChange, key, help, candidates, placeholder, minRows = 3, maxHeight = 220, cls, spellcheck = false }) {
  const pre = h("pre", { class: "rw-code-hl mono", "aria-hidden": "true", html: highlightHTML(value) });
  const list = h("div", { class: "rw-ac", role: "listbox" });
  const ta = h("textarea", {
    class: "rw-code-ta mono", key, help, placeholder, spellcheck: spellcheck ? "true" : "false", rows: minRows, value: value ?? "",
    dataset: { scroll: key },
  });
  const wrap = h("div", { class: ["rw-code", cls], style: { "max-height": maxHeight + "px" } }, pre, ta, list);
  let matches = [];
  let active = 0;
  let token = null;

  /* [OLD 2026-11-09 v0.17.2->v0.17.3] the overlay wrapped wider than the textarea once its scrollbar showed (a text taller
     than maxHeight), so the caret stood where the user clicked but typing went in a few words earlier (Sencer: "when
     editing shot text, the cursor is at correct position, but typing and deleting is in wrong position")
  function fit() {
    ta.style.height = "auto";
    const hgt = Math.min(maxHeight, Math.max(ta.scrollHeight, minRows * 18 + 16));
    ta.style.height = hgt + "px";
    pre.style.height = hgt + "px";
  }
  [/OLD] */
  // added 2026-11-09 v0.17.3: the overlay has the textarea's text width (its scrollbar's room on the right as padding) and
  // its scroll position, so every line wraps at the same word
  function align() {
    if (!ta.isConnected) return;
    const gutter = Math.max(0, ta.offsetWidth - ta.clientWidth);
    const pad = getComputedStyle(ta).paddingRight;
    const want = gutter ? `calc(${pad} + ${gutter}px)` : "";
    if (pre.style.paddingRight !== want) pre.style.paddingRight = want;
    if (pre.scrollTop !== ta.scrollTop) pre.scrollTop = ta.scrollTop;
  }
  function fit() {
    const keep = ta.scrollTop; // added 2026-11-09 v0.17.3: "auto" for a moment reset the scroll position
    ta.style.height = "auto";
    const hgt = Math.min(maxHeight, Math.max(ta.scrollHeight, minRows * 18 + 16));
    ta.style.height = hgt + "px";
    pre.style.height = hgt + "px";
    ta.scrollTop = keep;
    // added 2026-11-09 v0.17.3: a rebuilt editor whose textarea got the typed text (editor.js render) shows that text
    if (pre.textContent !== ta.value + "\n") pre.innerHTML = highlightHTML(ta.value);
    align();
  }

  let lastQ = null; // added 2026-11-04 v0.6.1: the query the list was opened for (openList)

  function closeList() {
    list.classList.remove("on");
    matches = [];
    token = null;
    lastQ = null; // added 2026-11-04 v0.6.1: the next list starts on its first row
  }

  function openList() {
    const before = ta.value.slice(0, ta.selectionStart);
    // [OLD 2026-11-03 v0.5.1->v0.6.0] const m = before.match(/@(\{[^}\n]*|[\w-]*)$/);
    // added 2026-11-03 v0.6.0: the tag rule: no list after a letter or digit (an e-mail address) or after @@
    const m = before.match(/(?<![\p{L}\p{N}\p{M}_@])@(?!@)(\{[^}\n]*|[\p{L}\p{N}\p{M}_'’.\-]*)$/u);
    if (!m) { closeList(); return; }
    const q = m[0].toLowerCase();
    matches = candidates.filter(c => c.tag.toLowerCase().startsWith(q) || c.label.toLowerCase().includes(q.slice(1))).slice(0, 8);
    if (!matches.length) { closeList(); return; }
    token = { start: ta.selectionStart - m[0].length, end: ta.selectionStart };
    // [OLD 2026-11-04 v0.6.0->v0.6.1] active = Math.min(active, matches.length - 1);  (the highlight stayed on row n when the query narrowed and in the next list, so Enter inserted another tag than the best match)
    if (q !== lastQ) active = 0; // added 2026-11-04 v0.6.1: a new or changed query starts on the best match
    lastQ = q;
    active = Math.min(active, matches.length - 1);
    list.replaceChildren(...matches.map((c, i) => h("div", {
      class: ["rw-ac-item", i === active && "on"], role: "option",
      onPointerdown: e => { e.preventDefault(); insert(c); },
    }, h("b", { class: "mono rw-c-" + ({ image: "pic", video: "vid", audio: "aud", cast: "pic" }[c.kind] || "text") }, c.tag), h("span", { class: "rw-dim" }, c.label))));
    list.classList.add("on");
  }

  function insert(c) {
    const v = ta.value;
    ta.value = v.slice(0, token.start) + c.tag + " " + v.slice(token.end);
    const pos = token.start + c.tag.length + 1;
    ta.setSelectionRange(pos, pos);
    closeList();
    sync();
  }

  function sync() {
    pre.innerHTML = highlightHTML(ta.value);
    fit();
    onInput?.(ta.value);
  }

  // [OLD 2026-11-03 v0.5.1->v0.6.0] ta.addEventListener("input", () => { sync(); openList(); });
  // added 2026-11-03 v0.6.0: IME. While a composition runs only the highlight follows; the value is reported (and
  // the list opened) when it ends, so no re-render replaces the textarea mid-composition.
  let composing = false;
  ta.addEventListener("compositionstart", () => { composing = true; closeList(); });
  ta.addEventListener("compositionend", () => { composing = false; sync(); openList(); });
  ta.addEventListener("input", e => {
    if (composing || e.isComposing) { pre.innerHTML = highlightHTML(ta.value); fit(); return; }
    sync();
    openList();
  });
  // [OLD 2026-11-09 v0.17.2->v0.17.3] ta.addEventListener("scroll", () => { pre.scrollTop = ta.scrollTop; });
  ta.addEventListener("scroll", align); // added 2026-11-09 v0.17.3: also the scrollbar's room
  ta.addEventListener("focus", align); // added 2026-11-09 v0.17.3: the box may have been resized since (a node resized)
  ta.addEventListener("change", () => onChange?.(ta.value));
  ta.addEventListener("blur", () => setTimeout(closeList, 120));
  ta.addEventListener("keydown", e => {
    if (composing || e.isComposing) return; // added 2026-11-03 v0.6.0: Enter/arrows that belong to the IME
    if (!list.classList.contains("on")) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length;
      openList();
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      insert(matches[active]);
    } else if (e.key === "Escape") {
      e.stopPropagation();
      closeList();
    }
  });
  /* [OLD 2026-11-09 v0.17.2->v0.17.3] the size came a frame later: every re-render of a tab (autosave, progress, a plan
     refresh) showed each prompt editor at its first rows for a frame, so the shot cards jumped (Sencer: "the shot
     cards flicker randomly")
  requestAnimationFrame(fit);
  [/OLD] */
  // added 2026-11-09 v0.17.3: sized before the page is painted: right after the render that puts it in the page (a microtask
  // runs before the frame is drawn), else on the next frame
  queueMicrotask(() => (ta.isConnected ? fit() : requestAnimationFrame(fit)));
  return wrap;
}
