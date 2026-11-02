// Prompt editor: a textarea over a highlighted <pre>, with @tag autocomplete.

import { h } from "./ui.js";
import { highlightHTML } from "./prompttext.js";

export function codeEditor({ value, onInput, onChange, key, help, candidates, placeholder, minRows = 3, maxHeight = 220 }) {
  const pre = h("pre", { class: "rw-code-hl mono", "aria-hidden": "true", html: highlightHTML(value) });
  const list = h("div", { class: "rw-ac", role: "listbox" });
  const ta = h("textarea", {
    class: "rw-code-ta mono", key, help, placeholder, spellcheck: "false", rows: minRows, value: value ?? "",
    dataset: { scroll: key },
  });
  const wrap = h("div", { class: "rw-code", style: { "max-height": maxHeight + "px" } }, pre, ta, list);
  let matches = [];
  let active = 0;
  let token = null;

  function fit() {
    ta.style.height = "auto";
    const hgt = Math.min(maxHeight, Math.max(ta.scrollHeight, minRows * 18 + 16));
    ta.style.height = hgt + "px";
    pre.style.height = hgt + "px";
  }

  function closeList() {
    list.classList.remove("on");
    matches = [];
    token = null;
  }

  function openList() {
    const before = ta.value.slice(0, ta.selectionStart);
    const m = before.match(/@(\{[^}\n]*|[\w-]*)$/);
    if (!m) { closeList(); return; }
    const q = m[0].toLowerCase();
    matches = candidates.filter(c => c.tag.toLowerCase().startsWith(q) || c.label.toLowerCase().includes(q.slice(1))).slice(0, 8);
    if (!matches.length) { closeList(); return; }
    token = { start: ta.selectionStart - m[0].length, end: ta.selectionStart };
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

  ta.addEventListener("input", () => { sync(); openList(); });
  ta.addEventListener("scroll", () => { pre.scrollTop = ta.scrollTop; });
  ta.addEventListener("change", () => onChange?.(ta.value));
  ta.addEventListener("blur", () => setTimeout(closeList, 120));
  ta.addEventListener("keydown", e => {
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
  requestAnimationFrame(fit);
  return wrap;
}
