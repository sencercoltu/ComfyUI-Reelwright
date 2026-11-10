// Prompt editor: a textarea over a highlighted <pre>, with @tag autocomplete.

import { h, rootScale } from "./ui.js";
import { highlightHTML } from "./prompttext.js";

// The editor (by its key) whose @ list was open, so its copy after a re-render opens it again
const OPEN_LIST = { key: null, active: 0 };
const LIST_MAX = 60;
// the tag being typed before the caret: no list after a letter or digit (an e-mail address) or after @@
const TAG_AT = /(?<![\p{L}\p{N}\p{M}_@])@(?!@)(\{[^}\n]*|[\p{L}\p{N}\p{M}_'’.\-]*)$/u;

// cls (an extra class on the box: "sans" for shot and dialogue texts), spellcheck
export function codeEditor({ value, onInput, onChange, key, help, candidates, placeholder, minRows = 3, maxHeight = 220, cls, spellcheck = false }) {
  const pre = h("pre", { class: "rw-code-hl mono", "aria-hidden": "true", html: highlightHTML(value) });
  const list = h("div", { class: "rw-ac", role: "listbox" });
  const ta = h("textarea", {
    class: "rw-code-ta mono", key, help, placeholder, spellcheck: spellcheck ? "true" : "false", rows: minRows, value: value ?? "",
    dataset: { scroll: key },
  });
  list.classList.add("floating");
  const wrap = h("div", { class: ["rw-code", cls], style: { "max-height": maxHeight + "px" } }, pre, ta);
  let matches = [];
  let active = 0;
  let token = null;

  // The overlay has the textarea's text width (its scrollbar's room on the right as padding) and
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
    const keep = ta.scrollTop;
    ta.style.height = "auto";
    const hgt = Math.min(maxHeight, Math.max(ta.scrollHeight, minRows * 18 + 16));
    ta.style.height = hgt + "px";
    pre.style.height = hgt + "px";
    ta.scrollTop = keep;
    if (pre.textContent !== ta.value + "\n") pre.innerHTML = highlightHTML(ta.value);
    align();
  }

  let lastQ = null;

  function closeList(byUser = true) { // byUser: false when the editor left the page (a re-render)
    list.classList.remove("on");
    list.remove();
    matches = [];
    token = null;
    lastQ = null;
    if (byUser && OPEN_LIST.key === key) OPEN_LIST.key = null;
  }

  // The candidates for a query ("@ma", "@{old"), best first: a tag that starts with it (cast members
  // first), then a name with a word that starts with it, then a name that holds it
  function ranked(q) {
    const word = q.replace(/^@\{?/, "");
    const out = [];
    for (const c of candidates) {
      const tag = c.tag.toLowerCase(), label = c.label.toLowerCase();
      let s = -1;
      if (tag.startsWith(q) || tag.startsWith("@{" + word)) s = c.kind === "cast" ? 0 : 1;
      else if (word && label.split(/[\s·—\-_,.()]+/).some(w => w.startsWith(word))) s = 2;
      else if (word && (label.includes(word) || tag.includes(word))) s = 3;
      else if (!word) s = c.kind === "cast" ? 0 : 1;
      if (s >= 0) out.push([s, out.length, c]);
    }
    return out.sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, LIST_MAX).map(x => x[2]);
  }

  // The list under the caret's line (above it when there is no room below), inside the root
  function placeList() {
    const root = ta.closest(".rw-root");
    if (!root) return;
    if (list.parentElement !== root) root.appendChild(list);
    const sc = rootScale(root) || 1;
    const rr = root.getBoundingClientRect(), tr = ta.getBoundingClientRect();
    let line = null;
    try { // the caret's place in the overlay (it wraps as the textarea does)
      const walker = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
      let n, pos = 0;
      const at = ta.selectionStart;
      while ((n = walker.nextNode())) { if (pos + n.length >= at) break; pos += n.length; }
      if (n) {
        const r = document.createRange();
        r.setStart(n, Math.max(0, Math.min(n.length, at - pos)));
        r.collapse(true);
        const rects = r.getClientRects();
        line = rects.length ? rects[rects.length - 1] : r.getBoundingClientRect();
      }
    } catch { line = null; }
    const lineTop = line && line.height ? Math.max(tr.top, Math.min(tr.bottom, line.top)) : tr.bottom;
    const lineBottom = line && line.height ? Math.max(tr.top, Math.min(tr.bottom, line.bottom)) : tr.bottom;
    const left = Math.max(rr.left, Math.min(line && line.height ? line.left : tr.left, rr.right - list.offsetWidth * sc));
    const h = list.offsetHeight * sc;
    const room = Math.min(rr.bottom, window.innerHeight) - lineBottom;
    const top = room >= h + 4 * sc || lineTop - Math.max(rr.top, 0) < h + 4 * sc ? lineBottom + 4 * sc : lineTop - h - 4 * sc;
    list.style.left = Math.round((left - rr.left) / sc) + "px";
    list.style.top = Math.round((top - rr.top) / sc) + "px";
  }

  function openList() {
    const before = ta.value.slice(0, ta.selectionStart);
    const m = before.match(TAG_AT);
    if (!m) { closeList(); return; }
    const q = m[0].toLowerCase();
    matches = ranked(q);
    if (!matches.length) { closeList(); return; }
    token = { start: ta.selectionStart - m[0].length, end: ta.selectionStart };
    if (q !== lastQ) active = 0;
    lastQ = q;
    active = Math.min(active, matches.length - 1);
    list.replaceChildren(...matches.map((c, i) => h("div", {
      class: ["rw-ac-item", i === active && "on"], role: "option",
      onPointerdown: e => { e.preventDefault(); insert(c); },
    }, h("b", { class: "mono rw-c-" + ({ image: "pic", video: "vid", audio: "aud", cast: "pic" }[c.kind] || "text") }, c.tag), h("span", { class: "rw-dim" }, c.label))));
    list.classList.add("on");
    OPEN_LIST.key = key;
    OPEN_LIST.active = active;
    list.closest(".rw-root")?.querySelectorAll(".rw-ac.floating").forEach(x => { if (x !== list) x.remove(); });
    placeList();
    list.children[active]?.scrollIntoView?.({ block: "nearest" });
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

  let composing = false;
  ta.addEventListener("compositionstart", () => { composing = true; closeList(); });
  ta.addEventListener("compositionend", () => { composing = false; sync(); openList(); });
  ta.addEventListener("input", e => {
    if (composing || e.isComposing) { pre.innerHTML = highlightHTML(ta.value); fit(); return; }
    sync();
    openList();
  });
  ta.addEventListener("scroll", align);
  ta.addEventListener("focus", align);
  ta.addEventListener("change", () => onChange?.(ta.value));
  ta.addEventListener("blur", () => setTimeout(() => closeList(ta.isConnected), 120));
  ta.addEventListener("click", () => { if (list.classList.contains("on")) openList(); }); // the caret moved
  ta.addEventListener("keydown", e => {
    if (composing || e.isComposing) return;
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
  queueMicrotask(() => (ta.isConnected ? fit() : requestAnimationFrame(fit)));
  queueMicrotask(() => {
    if (!key || OPEN_LIST.key !== key || !ta.isConnected || document.activeElement !== ta) return;
    const m = ta.value.slice(0, ta.selectionStart).match(TAG_AT);
    lastQ = m ? m[0].toLowerCase() : null; // the same query keeps its row
    active = OPEN_LIST.active;
    openList();
  });
  return wrap;
}
