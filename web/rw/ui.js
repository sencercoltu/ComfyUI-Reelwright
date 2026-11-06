// Minimal DOM builder and the editor's controls. Every interactive control takes
// a `help` id that the tooltip layer resolves against help.js.

const SVG_NS = "http://www.w3.org/2000/svg";
const SVG_TAGS = new Set(["svg", "path", "rect", "circle", "line", "polyline", "polygon", "g", "text", "defs", "pattern", "ellipse"]);

export function h(tag, props, ...children) {
  const svg = SVG_TAGS.has(tag);
  const el = svg ? document.createElementNS(SVG_NS, tag) : document.createElement(tag);
  let value;
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "value") value = v;
      else if (k === "class") el.setAttribute("class", Array.isArray(v) ? v.filter(Boolean).join(" ") : v);
      else if (k === "style") {
        if (typeof v === "string") el.setAttribute("style", v);
        else for (const [sk, sv] of Object.entries(v)) if (sv !== undefined && sv !== null) el.style.setProperty(sk, String(sv));
      } else if (k === "help") el.dataset.help = v;
      // added 2026-11-02 v0.2.2: right-click menu and wheel handlers are routed by editor.js (see installEventGuards)
      else if (k === "menu") el.__rwMenu = v;
      else if (k === "wheel") el.__rwWheel = v;
      else if (k === "key") el.dataset.key = v;
      else if (k === "dataset") Object.assign(el.dataset, v);
      // [OLD 2026-11-03 v0.6.0 review] else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
      // added 2026-11-03 v0.6.0 review: a field with an onInput handler stores (or shows) what is typed as it is typed;
      // editor.js render() treats only the other text fields as holding unsaved typing (__rwLive marks the live ones)
      else if (k.startsWith("on") && typeof v === "function") { el.addEventListener(k.slice(2).toLowerCase(), v); if (k === "onInput") el.__rwLive = true; }
      else if (k === "html") el.innerHTML = v;
      else if (!svg && k in el && typeof v !== "string") el[k] = v;
      else el.setAttribute(k, v === true ? "" : String(v));
    }
  }
  append(el, children);
  if (value !== undefined) el.value = value;
  return el;
}

function append(el, children) {
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else if (c instanceof Node) el.appendChild(c);
    else el.appendChild(document.createTextNode(String(c)));
  }
}

const ICONS = {
  timeline: '<rect x="2" y="2.5" width="12" height="11" rx="1.5"/><path d="M2 6.5h12M6 6.5v7"/>',
  scene: '<rect x="2" y="2.5" width="12" height="11" rx="1.5"/><path d="M5 2.5v11M11 2.5v11"/>',
  assets: '<rect x="2" y="3" width="12" height="10" rx="1.5"/><circle cx="6" cy="6.5" r="1.2"/><path d="m2.5 12 3.5-3.5 2.5 2.5 2-2 3 3"/>',
  cast: '<circle cx="8" cy="5.5" r="2.6"/><path d="M3 14a5 5 0 0 1 10 0"/>',
  render: '<rect x="2" y="2.5" width="12" height="9" rx="1.5"/><path d="M6.8 5.2v3.6L9.8 7z"/><path d="M4 14h8"/>',
  global: '<circle cx="8" cy="8" r="2.2"/><path d="M8 1.8v2M8 12.2v2M1.8 8h2M12.2 8h2M3.6 3.6l1.4 1.4M11 11l1.4 1.4M12.4 3.6 11 5M5 11l-1.4 1.4"/>',
  image: '<rect x="2" y="3" width="12" height="10" rx="1.5"/><circle cx="6" cy="6.5" r="1.2"/><path d="m2.5 12 3.5-3.5 2.5 2.5 2-2 3 3"/>',
  video: '<rect x="1.5" y="4" width="9" height="8" rx="1.5"/><path d="m10.5 7 4-2v6l-4-2"/>',
  audio: '<path d="M2 8h1.5M5 5v6M8 3v10M11 5.5v5M14 8h-1"/>',
  // added 2026-11-03 v0.5.0: soundtrack lanes
  music: '<path d="M6 12V3.5l7-1.5v8.5"/><circle cx="4.3" cy="12" r="1.8"/><circle cx="11.3" cy="10.5" r="1.8"/>',
  speaker: '<path d="M2.5 6h2.5l3.5-3v10L5 10H2.5z"/><path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.8 3.8a6 6 0 0 1 0 8.4"/>',
  mute: '<path d="M2.5 6h2.5l3.5-3v10L5 10H2.5z"/><path d="m11 6 3.5 4M14.5 6 11 10"/>',
  dialogue: '<path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/>',
  camera: '<rect x="1.5" y="5" width="13" height="8.5" rx="1.5"/><circle cx="8" cy="9.2" r="2.4"/><path d="M5.5 5l1-1.8h3l1 1.8"/>',
  lora: '<path d="m8 2 6 3-6 3-6-3z"/><path d="m2 8 6 3 6-3M2 11l6 3 6-3"/>',
  film: '<rect x="2" y="2.5" width="12" height="11" rx="1.5"/><path d="M5 2.5v11M11 2.5v11M2 6h3M2 10h3M11 6h3M11 10h3"/>',
  play: '<path d="M4.5 2.8v10.4L13 8z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M5 3v10M11 3v10" stroke-width="2.4"/>',
  stop: '<rect x="3.5" y="3.5" width="9" height="9" rx="1.5" fill="currentColor" stroke="none"/>',
  prev: '<path d="M4 3.5v9M12 3.5v9L6 8z"/>',
  next: '<path d="M12 3.5v9M4 3.5v9L10 8z"/>',
  plus: '<path d="M8 3v10M3 8h10"/>',
  minus: '<path d="M3 8h10"/>',
  close: '<path d="m4 4 8 8M12 4l-8 8"/>',
  undo: '<path d="M5 3.5 2 6.5l3 3M2 6.5h7.5a3.5 3.5 0 0 1 0 7H7"/>',
  redo: '<path d="m11 3.5 3 3-3 3M14 6.5H6.5a3.5 3.5 0 0 0 0 7H9"/>',
  check: '<path d="M3 8.5 6.5 12 13 4.5"/>',
  warn: '<path d="M8 2.5 14.5 13.5h-13z"/><path d="M8 6.5v3.2M8 11.6v.1"/>',
  info: '<circle cx="8" cy="8" r="6"/><path d="M8 7.2v4M8 4.9v.1"/>',
  link: '<path d="M7 9.5a2.5 2.5 0 0 0 3.5 0l2-2a2.5 2.5 0 0 0-3.5-3.5l-.8.8M9 6.5a2.5 2.5 0 0 0-3.5 0l-2 2a2.5 2.5 0 0 0 3.5 3.5l.8-.8"/>',
  tail: '<rect x="1.5" y="4" width="8" height="8" rx="1"/><path d="M11 8h3.5M12.5 6l2 2-2 2"/>',
  cut: '<circle cx="4" cy="4.5" r="2"/><circle cx="4" cy="11.5" r="2"/><path d="M5.6 5.8 13 12M5.6 10.2 13 4"/>',
  star: '<path d="m8 2 1.8 3.8 4.2.5-3.1 2.9.8 4.1L8 11.3l-3.7 2 .8-4.1L2 6.3l4.2-.5z"/>',
  starFill: '<path d="m8 2 1.8 3.8 4.2.5-3.1 2.9.8 4.1L8 11.3l-3.7 2 .8-4.1L2 6.3l4.2-.5z" fill="currentColor"/>',
  trash: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 9h5.6l.7-9"/>',
  copy: '<rect x="5" y="5" width="8.5" height="8.5" rx="1.5"/><path d="M3 10.5V3.5A1 1 0 0 1 4 2.5h6.5"/>',
  wand: '<path d="m2.5 13.5 7-7M10 2v2.5M10 8.5V11M6.5 5H4M15 5h-2.5M12.3 2.7l-1.2 1.2M8.9 6.1 7.7 7.3"/>',
  merge: '<path d="M2 4h5l2 4-2 4H2M14 4H9.5M14 12H9.5"/>',
  lock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1.2"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>',
  unlock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1.2"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0"/>',
  upload: '<path d="M8 11V3M4.5 6.5 8 3l3.5 3.5M3 13h10"/>',
  refresh: '<path d="M3 4v3.5h3.5M3.5 7.5A5 5 0 1 1 5 12"/>',
  marker: '<path d="M4 14V2.5h8l-2 3 2 3H4"/>',
  split: '<path d="M8 2v12M5 5h6M5 11h6"/>',
  pointer: '<path d="M4 2.5 12.5 8l-3.8.9 2.1 4.2-1.6.8-2.1-4.3L4 12.5z"/>',
  magnet: '<path d="M4 2.5v5.5a4 4 0 0 0 8 0V2.5M4 5.5h2.5M9.5 5.5H12"/>',
  ripple: '<path d="M2 8h4M10 8h4M6 5v6M10 5v6"/>',
  chevDown: '<path d="m4 6 4 4 4-4"/>',
  chevRight: '<path d="m6 4 4 4-4 4"/>',
  chevLeft: '<path d="m10 4-4 4 4 4"/>',
  eye: '<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/>',
  download: '<path d="M8 3v8M4.5 7.5 8 11l3.5-3.5M3 13h10"/>',
  compare: '<rect x="2" y="3" width="5" height="10" rx="1"/><rect x="9" y="3" width="5" height="10" rx="1"/>',
  zoomIn: '<circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3M5 7h4M7 5v4"/>',
  zoomOut: '<circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3M5 7h4"/>',
  search: '<circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/>',
  grip: '<circle cx="6" cy="4" r=".9"/><circle cx="10" cy="4" r=".9"/><circle cx="6" cy="8" r=".9"/><circle cx="10" cy="8" r=".9"/><circle cx="6" cy="12" r=".9"/><circle cx="10" cy="12" r=".9"/>',
  clapper: '<rect x="2" y="6" width="12" height="8" rx="1.5"/><path d="M2 6 3.5 2.5h9L14 6M6.5 2.5 5.3 6M10.5 2.5 9.3 6"/>',
  sheet: '<rect x="2" y="2" width="5.5" height="5.5" rx="1"/><rect x="8.5" y="2" width="5.5" height="5.5" rx="1"/><rect x="2" y="8.5" width="5.5" height="5.5" rx="1"/><rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1"/>',
  // added 2026-11-03 v0.4.0: Files tab
  disk: '<rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M2 9.5h12"/><path d="M11 11.3h.8"/>',
  folder: '<path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h2.8l1.5 1.5h4.7A1.5 1.5 0 0 1 14 6v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z"/>',
  file: '<path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/>',
  history: '<path d="M2.5 8a5.5 5.5 0 1 0 1.6-3.9"/><path d="M2.3 2.6v2.6h2.6M8 5v3.2l2.2 1.4"/>', // added 2026-11-03 v0.6.0
};

export function icon(name, size = 14) {
  const el = document.createElementNS(SVG_NS, "svg");
  el.setAttribute("width", size);
  el.setAttribute("height", size);
  el.setAttribute("viewBox", "0 0 16 16");
  el.setAttribute("fill", "none");
  el.setAttribute("stroke", "currentColor");
  el.setAttribute("stroke-width", "1.6");
  el.setAttribute("stroke-linecap", "round");
  el.setAttribute("stroke-linejoin", "round");
  el.setAttribute("aria-hidden", "true");
  el.innerHTML = ICONS[name] || "";
  return el;
}

// added 2026-11-03 v0.6.0: the one focus helper. ComfyUI runs its workflow undo (a graph reload) on Ctrl+Z unless
// the focused element is an INPUT, TEXTAREA or contenteditable, so keyboard focus must never rest on the page body,
// a button pressed with the mouse, a <video controls> or a dialog button while the editor is in use.
// - isTextField(el): fields where Ctrl+Z belongs to the browser (text, number, textarea, contenteditable).
// - keepFocus(el): focus the hidden key field of the editor that contains `el` (or is `el`); false when outside.
// - focusGuard(root, keys): installed once per editor by editor.js; returns a function that removes it.
const TEXT_INPUT = /^(?:text|search|email|url|tel|password|number|)$/;
export function isTextField(el) {
  if (!el || !(el instanceof Element)) return false;
  if (el.isContentEditable || el.tagName === "TEXTAREA" || el.tagName === "SELECT") return true;
  return el.tagName === "INPUT" && !el.classList.contains("rw-keys") && TEXT_INPUT.test((el.getAttribute("type") || "").toLowerCase());
}
export function keepFocus(el) {
  const root = el?.closest?.(".rw-root");
  if (!root || !root.isConnected) return false;
  root.focus({ preventScroll: true }); // editor.js points root.focus at its key field
  return true;
}
export function focusGuard(root, keys) {
  let outsideAt = -1e9;
  const now = () => performance.now();
  const toKeys = () => { if (root.isConnected) keys.focus({ preventScroll: true }); };
  // a press outside the editor may take focus away (canvas, another node, ComfyUI's menus): that is allowed
  const outside = e => { if (!root.contains(e.target)) outsideAt = now(); };
  // focus leaving to nowhere (an element removed by a re-render, a list closed with Escape) comes back
  const focusout = e => {
    if (e.relatedTarget) return;
    setTimeout(() => {
      const a = document.activeElement;
      if (!root.isConnected || (a && a !== document.body && a !== document.documentElement)) return;
      if (now() - outsideAt < 600 || !document.hasFocus()) return;
      toKeys();
    }, 0);
  };
  // <video controls> and <audio controls> take focus when clicked; it moves on to the key field
  const focusin = e => {
    if (e.target instanceof HTMLMediaElement) setTimeout(() => { if (document.activeElement === e.target) toKeys(); }, 0);
  };
  // Ctrl/Cmd is pressed before Z: while a button, a media element or the root has focus, the key field takes it,
  // so ComfyUI's capture listener sees an INPUT when Z follows
  const keydown = e => {
    if ((e.key === "Control" || e.key === "Meta") && document.activeElement !== keys && !isTextField(document.activeElement)) toKeys();
  };
  window.addEventListener("pointerdown", outside, true);
  root.addEventListener("focusout", focusout);
  root.addEventListener("focusin", focusin);
  root.addEventListener("keydown", keydown, true);
  return () => {
    window.removeEventListener("pointerdown", outside, true);
    root.removeEventListener("focusout", focusout);
    root.removeEventListener("focusin", focusin);
    root.removeEventListener("keydown", keydown, true);
  };
}

export function button({ label, icon: ic, help, onClick, variant = "default", small = false, disabled = false, ariaLabel, key, extra }) {
  return h("button", {
    type: "button", class: ["rw-btn", "rw-btn-" + variant, small && "rw-btn-sm", !label && "rw-btn-icon"],
    help, key, disabled, "aria-label": ariaLabel || (!label ? help : undefined),
    onClick: e => { e.stopPropagation(); if (!disabled) onClick?.(e); },
  }, ic && icon(ic, small ? 12 : 14), label && h("span", null, label), extra);
}

export function toggle({ value, onChange, help, label, key, disabled }) {
  const btn = h("button", {
    type: "button", class: ["rw-toggle", value && "on"], role: "switch", "aria-checked": value ? "true" : "false",
    "aria-label": label || help, help, key, disabled,
    onClick: e => { e.stopPropagation(); if (!disabled) onChange(!value); },
  }, h("span", { class: "rw-toggle-knob" }));
  return label ? h("label", { class: "rw-toggle-row", help }, btn, h("span", null, label)) : btn;
}

export function segmented({ options, value, onChange, help, key, small }) {
  return h("div", { class: ["rw-seg", small && "rw-seg-sm"], role: "radiogroup", help, key },
    options.map(o => {
      const opt = typeof o === "string" ? { value: o, label: o } : o;
      return h("button", {
        type: "button", role: "radio", "aria-checked": opt.value === value ? "true" : "false",
        class: ["rw-seg-btn", opt.value === value && "on"], help: opt.help || help,
        onClick: e => { e.stopPropagation(); if (opt.value !== value) onChange(opt.value); },
      }, opt.icon && icon(opt.icon, 12), opt.label);
    }));
}

/* [OLD 2026-11-02 v0.1.0->v0.2.0] native <select> could not be searched; replaced by the combobox below
export function select({ options, value, onChange, help, key, placeholder, mono, width }) {
  const opts = options.map(o => (typeof o === "string" ? { value: o, label: o } : o));
  const known = opts.some(o => o.value === value);
  const sel = h("select", {
    class: ["rw-select", mono && "mono"], help, key, style: width ? { width } : null,
    onChange: e => onChange(e.target.value),
  },
  placeholder !== undefined && h("option", { value: "" }, placeholder),
  !known && value && h("option", { value }, value + " (missing)"),
  opts.map(o => h("option", { value: o.value }, o.label)));
  sel.value = value ?? "";
  return sel;
}
[/OLD] */

// added 2026-11-02 v0.2.0: type-to-filter combobox with the same API as the old select().
// Typing narrows the list (every word must match, e.g. "minimax int8"); arrows + Enter pick.
// `free: true` also accepts a typed value that is not in the list (languages, LLM model ids).
// The list lives in the editor root so cards with overflow cannot clip it.
export const comboState = { open: 0, onClose: null, restoring: false };

export function select({ options, value, onChange, help, key, placeholder, mono, width, free = false }) {
  const given = options.map(o => (typeof o === "string" ? { value: o, label: o } : o));
  // the old <select> turned the placeholder into an empty first option ("none", "no voice reference"),
  // so keep it pickable; "+ Add…" placeholders are prompts, not values
  const noneOpt = placeholder !== undefined && !String(placeholder).startsWith("+") && !given.some(o => o.value === "");
  const opts = noneOpt ? [{ value: "", label: placeholder }, ...given] : given;
  const cur = opts.find(o => o.value === value);
  const missing = !cur && !!value && !free;
  const shown = cur ? (cur.value === "" ? "" : cur.label) : (value || "");
  const input = h("input", {
    type: "text", class: ["rw-combo-input", mono && "mono", missing && "missing"], help, key,
    placeholder: placeholder ?? (free ? "type or pick…" : "type to filter…"),
    autocomplete: "off", spellcheck: "false", role: "combobox", "aria-expanded": "false", "aria-autocomplete": "list",
  });
  input.value = missing ? value + " (missing)" : shown;
  const wrap = h("span", { class: ["rw-select", "rw-combo", mono && "mono"], style: width ? { width } : null });
  let list = null, items = [], active = -1, done = false;
  let listRoot = null; // added 2026-11-03 v0.6.0

  const matches = q => {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    return opts.filter(o => { const s = (o.label + " " + o.value).toLowerCase(); return terms.every(t => s.includes(t)); });
  };
  const mark = (label, q) => {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return label;
    const re = new RegExp("(" + terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "gi");
    return label.split(re).map((part, i) => (i % 2 ? h("mark", null, part) : part));
  };
  function position() {
    const root = wrap.closest(".rw-root");
    if (!root || !list) return;
    const rr = root.getBoundingClientRect(), r = wrap.getBoundingClientRect();
    const sc = rr.width / (root.offsetWidth || rr.width) || 1;
    const below = (rr.bottom - r.bottom) / sc - 10, above = (r.top - rr.top) / sc - 10;
    const up = below < 160 && above > below;
    const w = Math.max(r.width / sc, 200);
    let left = (r.left - rr.left) / sc;
    left = Math.max(6, Math.min(root.offsetWidth - w - 6, left));
    list.style.left = left + "px";
    list.style.minWidth = w + "px";
    list.style.maxWidth = Math.max(w, Math.min(520, root.offsetWidth - 12)) + "px";
    list.style.maxHeight = Math.max(120, Math.min(300, up ? above : below)) + "px";
    list.style.top = up ? "" : ((r.bottom - rr.top) / sc + 3) + "px";
    list.style.bottom = up ? ((rr.bottom - r.top) / sc + 3) + "px" : "";
  }
  function paint(q) {
    items = matches(q);
    const typed = q.trim();
    const freeItem = free && typed && !opts.some(o => o.value.toLowerCase() === typed.toLowerCase());
    if (active >= items.length + (freeItem ? 1 : 0)) active = items.length - 1;
    // falsy extras are filtered out: replaceChildren() would print them as "null"
    list.replaceChildren(...[
      ...items.map((o, i) => h("button", {
        type: "button", class: ["rw-combo-opt", i === active && "active", o.value === value && "cur", o.value === "" && "none"], role: "option",
        onPointerdown: e => { e.preventDefault(); choose(o); },
      }, mark(o.label, q))),
      freeItem ? h("button", { type: "button", class: ["rw-combo-opt free", active === items.length && "active"],
        onPointerdown: e => { e.preventDefault(); choose({ value: typed, label: typed }); } }, "Use “" + typed + "”") : null,
      !items.length && !freeItem ? h("div", { class: "rw-combo-empty" }, opts.length ? "No match" : "Nothing to pick yet") : null].filter(Boolean));
    list.querySelector(".active")?.scrollIntoView({ block: "nearest" });
  }
  function open(q) {
    const root = wrap.closest(".rw-root");
    if (!root) return;
    if (!list) {
      /* [OLD 2026-11-02 v0.2.1->v0.2.2] pressing the list's scrollbar moved focus out of the input, which closed the list
      list = h("div", { class: ["rw-combo-list", mono && "mono"], role: "listbox" });
      [/OLD] */
      // keep focus in the input while the list is pressed; the scrollbar gutter is left alone so dragging works
      list = h("div", { class: ["rw-combo-list", mono && "mono"], role: "listbox",
        onPointerdown: () => { pressed = true; document.addEventListener("pointerup", () => { pressed = false; }, { capture: true, once: true }); },
        onMousedown: e => { if (e.target !== e.currentTarget || e.offsetX < e.currentTarget.clientWidth) e.preventDefault(); } });
      root.appendChild(list);
      comboState.open++;
      listRoot = root; // added 2026-11-03 v0.6.0: open lists are counted per editor (root.__rwCombo)
      root.__rwCombo = (root.__rwCombo || 0) + 1;
      input.setAttribute("aria-expanded", "true");
    }
    if (q === "" && active < 0) active = Math.max(0, opts.findIndex(o => o.value === value));
    paint(q);
    position();
  }
  function close() {
    if (!list) return;
    list.remove();
    list = null;
    active = -1;
    input.setAttribute("aria-expanded", "false");
    comboState.open = Math.max(0, comboState.open - 1);
    if (!comboState.open && comboState.onClose) { const f = comboState.onClose; comboState.onClose = null; f(); }
    // added 2026-11-03 v0.6.0: the editor that owns the list re-renders once its last list closes
    if (listRoot) {
      const r = listRoot;
      listRoot = null;
      r.__rwCombo = Math.max(0, (r.__rwCombo || 0) - 1);
      if (!r.__rwCombo && r.__rwComboClosed) { const f = r.__rwComboClosed; r.__rwComboClosed = null; f(); }
    }
  }
  function choose(o) {
    done = true;
    input.value = o.value === "" ? "" : o.label;
    close();
    if (o.value !== value) onChange(o.value);
  }
  function revert() { input.value = missing ? value + " (missing)" : shown; }

  // the editor re-focuses keyed fields after each render; that must not pop the list open again
  input.addEventListener("focus", () => { done = false; if (comboState.restoring) return; input.select(); open(""); });
  input.addEventListener("pointerdown", () => { if (document.activeElement === input && !list) open(""); });
  input.addEventListener("input", () => { active = 0; open(input.value); });
  input.addEventListener("keydown", e => {
    const n = items.length + (list?.querySelector(".free") ? 1 : 0);
    if (e.key === "ArrowDown") { e.preventDefault(); if (!list) open(""); else { active = Math.min(n - 1, active + 1); paint(input.value === shown ? "" : input.value); } }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(0, active - 1); if (list) paint(input.value === shown ? "" : input.value); }
    else if (e.key === "Enter") {
      if (e.isComposing) return; // added 2026-11-03 v0.6.0: Enter that confirms an IME candidate
      e.preventDefault();
      const q = input.value === shown ? "" : input.value;
      if (active >= 0 && active < items.length) choose(items[active]);
      else if (free && q.trim()) choose({ value: q.trim(), label: q.trim() });
      // [OLD 2026-11-03 v0.5.1->v0.6.0] input.blur();  (focus fell to the page, so the next Ctrl+Z undid the workflow)
      done = true;
      if (!keepFocus(input)) input.blur();
    // [OLD 2026-11-03 v0.5.1->v0.6.0] } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); revert(); close(); input.blur(); }
    } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done = true; revert(); close(); if (!keepFocus(input)) input.blur(); }
  });
  // added 2026-11-02 v0.2.2: a press inside the list (scrollbar included) never closes it
  let pressed = false;
  input.addEventListener("blur", () => {
    const inList = pressed; // read now: the button may be released before the timeout runs
    setTimeout(() => {
      if (done) return;
      if (inList && list) {
        comboState.restoring = true; // refocus without resetting the typed filter
        try { input.focus({ preventScroll: true }); } finally { comboState.restoring = false; }
        return;
      }
      const typed = input.value.trim();
      if (free && typed && typed !== shown) { choose({ value: typed, label: typed }); return; }
      revert();
      close();
    }, 0);
  });
  wrap.append(input, h("button", {
    type: "button", class: "rw-combo-btn", tabindex: "-1", "aria-label": "Show options", help,
    onPointerdown: e => { e.preventDefault(); if (list) close(); else input.focus(); },
  }, icon("chevDown", 11)));
  return wrap;
}

// [OLD 2026-11-05 v0.7.0->v0.8.0] export function number({ value, onChange, help, key, min, max, step = 1, width = "84px", unit, mono = true }) {
// [OLD 2026-11-05 v0.7.0->v0.8.0]   const input = h("input", {
// [OLD 2026-11-05 v0.7.0->v0.8.0]     type: "number", class: ["rw-input", mono && "mono"], help, key, value: value ?? "", min, max, step,
// added 2026-11-05 v0.8.0: placeholder (an empty field shows it, e.g. a dialogue line's estimated length)
export function number({ value, onChange, help, key, min, max, step = 1, width = "84px", unit, mono = true, placeholder }) {
  const input = h("input", {
    type: "number", class: ["rw-input", mono && "mono"], help, key, value: value ?? "", min, max, step, placeholder,
    style: { width },
    /* [OLD 2026-11-03 v0.5.1->v0.6.0] a typo ("1e", "-", ".") reads as "" in a number field and was stored as null (the default; a seed became 0)
    onChange: e => {
      if (e.target.value === "") { onChange(null); return; }
      let v = Number(e.target.value);
      if (Number.isNaN(v)) return;
      if (min !== undefined) v = Math.max(min, v);
      if (max !== undefined) v = Math.min(max, v);
      onChange(v);
    },
    [/OLD] */
    // added 2026-11-03 v0.6.0: only an emptied field means "no value"; text the browser cannot read as a number puts
    // the stored value back
    onChange: e => {
      const el = e.target;
      const back = () => { el.value = value ?? ""; };
      if (el.validity?.badInput) { back(); return; }
      if (el.value === "") { onChange(null); return; }
      let v = Number(el.value);
      if (!Number.isFinite(v)) { back(); return; }
      if (min !== undefined) v = Math.max(min, v);
      if (max !== undefined) v = Math.min(max, v);
      onChange(v);
    },
  });
  return unit ? h("span", { class: "rw-unit-wrap" }, input, h("span", { class: "rw-unit" }, unit)) : input;
}

export function slider({ value, onChange, onInput, help, key, min = 0, max = 1, step = 0.01, format }) {
  const out = h("span", { class: "rw-slider-val mono" }, format ? format(value) : String(value));
  const input = h("input", {
    type: "range", class: "rw-range", help, key, min, max, step, value,
    onInput: e => { const v = Number(e.target.value); out.textContent = format ? format(v) : String(v); onInput?.(v); },
    onChange: e => onChange(Number(e.target.value)),
  });
  return h("span", { class: "rw-slider" }, input, out);
}

export function text({ value, onChange, onInput, help, key, placeholder, mono, width, type = "text" }) {
  return h("input", {
    type, class: ["rw-input", mono && "mono"], help, key, placeholder, value: value ?? "",
    style: width ? { width } : null,
    onInput: onInput ? e => onInput(e.target.value) : null,
    onChange: e => onChange?.(e.target.value),
  });
}

export function textarea({ value, onChange, onInput, help, key, placeholder, rows = 3, mono }) {
  return h("textarea", {
    class: ["rw-textarea", mono && "mono"], help, key, placeholder, rows,
    value: value ?? "",
    onInput: onInput ? e => onInput(e.target.value) : null,
    onChange: e => onChange?.(e.target.value),
  });
}

export function chip({ label, code, kind = "neutral", help, onRemove, onClick, title }) {
  return h("span", { class: ["rw-chip", "rw-chip-" + kind, onClick && "clickable"], help, title, onClick },
    code && h("b", { class: "mono" }, code), label,
    onRemove && h("button", {
      type: "button", class: "rw-chip-x", "aria-label": "Remove", help: "common.remove",
      onClick: e => { e.stopPropagation(); onRemove(); },
    }, icon("close", 10)));
}

export function dot(state, help) {
  return h("span", { class: ["rw-dot", "rw-dot-" + state], help: help || "common.dot." + state });
}

export function helpButton(id) {
  return h("button", { type: "button", class: "rw-q", "aria-label": "Help", dataset: { more: id }, help: id }, "?");
}

export function section({ title, help, actions, children, cls, tint }) {
  return h("section", { class: ["rw-card", cls, tint && "rw-card-" + tint] },
    h("div", { class: "rw-card-head" },
      h("span", { class: "rw-card-title" }, title),
      help && helpButton(help),
      h("span", { class: "rw-flex" }),
      actions),
    children);
}

/* [OLD 2026-11-05 v0.6.1->v0.7.0] the reset button always said "inherited from the Global tab"
export function field(label, control, { help, dot: dotState, reset, wide } = {}) {
  return h("div", { class: ["rw-field", wide && "wide"] },
    h("span", { class: "rw-field-label", help }, label),
    h("span", { class: "rw-field-ctl" }, control),
    dotState && dot(dotState),
    reset !== undefined && (reset
      ? button({ icon: "refresh", help: "common.reset", onClick: reset, small: true, variant: "ghost" })
      : h("span", { class: "rw-reset-ph" })));
}
[/OLD] */
// added 2026-11-05 v0.7.0: resetHelp (the reset button's help id, for values that go back to a default rather than to
// the Global tab) and cls (an extra class on the row)
export function field(label, control, { help, dot: dotState, reset, wide, resetHelp, cls } = {}) {
  return h("div", { class: ["rw-field", wide && "wide", cls] },
    h("span", { class: "rw-field-label", help }, label),
    h("span", { class: "rw-field-ctl" }, control),
    dotState && dot(dotState),
    reset !== undefined && (reset
      ? button({ icon: "refresh", help: resetHelp || "common.reset", onClick: reset, small: true, variant: "ghost" })
      : h("span", { class: "rw-reset-ph" })));
}

export function meter({ label, value, max, text: t, kind, help }) {
  const pct = Math.min(100, (value / max) * 100);
  return h("div", { class: "rw-meter", help },
    h("span", { class: "rw-meter-label rw-c-" + kind }, label),
    h("span", { class: "rw-meter-bar" }, h("span", { class: ["rw-meter-fill", "rw-bg-" + kind, value > max && "over"], style: { width: pct + "%" } })),
    h("span", { class: ["rw-meter-text mono", value > max && "rw-c-warn"] }, t));
}

export function empty(textContent, help) {
  return h("div", { class: "rw-empty", help }, textContent);
}

// [OLD 2026-11-03 v0.6.0 review] export function keepChips({ values, onChange, help, placeholder = "+ feature" }) {
// added 2026-11-03 v0.6.0 review: `key` (lists of chip fields share a help id; render() puts focus back by key)
export function keepChips({ values, onChange, help, placeholder = "+ feature", key }) {
  const input = h("input", {
    // [OLD 2026-11-03 v0.6.0 review] class: "rw-chip-input", placeholder, help,
    class: "rw-chip-input", placeholder, help, key, // added 2026-11-03 v0.6.0 review: key
    onKeydown: e => {
      if (e.key === "Enter" && e.target.value.trim()) {
        e.preventDefault();
        onChange([...values, e.target.value.trim()]);
      }
    },
  });
  return h("span", { class: "rw-chips" },
    values.map((v, i) => chip({ label: v, help, onRemove: () => onChange(values.filter((_, j) => j !== i)) })),
    input);
}

// deprecated 2026-11-03 v0.6.0: use confirmDialog (the bar vanished on any re-render); kept until the tabs move over
export function confirmInline(host, message, onYes) {
  const bar = h("div", { class: "rw-confirm" },
    h("span", null, message),
    button({ label: "Cancel", help: "common.cancel", small: true, onClick: () => bar.remove() }),
    button({ label: "Confirm", help: "common.confirm", small: true, variant: "danger", onClick: () => { bar.remove(); onYes(); } }));
  host.appendChild(bar);
}

// added 2026-11-02 v0.2.2: the editor's own right-click menu. Items: {label, icon, help, onClick, danger, disabled}
// or {sep: true}. Positioned in the root's unscaled pixels and kept inside the node.
/* [OLD 2026-11-03 v0.5.1->v0.6.0] no menu class, item class or heading rows
export function contextMenu(root, clientX, clientY, items) {
  root.querySelectorAll(".rw-ctx").forEach(m => m.remove());
  const close = () => { menu.remove(); document.removeEventListener("pointerdown", outside, true); document.removeEventListener("keydown", esc, true); };
  const outside = e => { if (!menu.contains(e.target)) close(); };
  const esc = e => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  const menu = h("div", { class: "rw-ctx", role: "menu" }, items.filter(Boolean).map(it => it.sep
    ? h("div", { class: "rw-ctx-sep" })
    : h("button", {
      type: "button", role: "menuitem", class: ["rw-ctx-item", it.danger && "danger"], help: it.help, disabled: !!it.disabled,
      onClick: e => { e.stopPropagation(); close(); it.onClick?.(); },
    }, it.icon ? icon(it.icon, 13) : h("span", { class: "rw-ctx-ic" }), h("span", null, it.label), it.hint ? h("span", { class: "rw-ctx-hint mono" }, it.hint) : null)));
[/OLD] */
// added 2026-11-03 v0.6.0: opts.cls (class of the menu), items may carry `cls` (extra class) and {head: "text"}
// (a heading row); a menu that is still open is closed first (its listeners too)
export function contextMenu(root, clientX, clientY, items, opts = {}) {
  root.__rwMenuClose?.();
  root.querySelectorAll(".rw-ctx").forEach(m => m.remove());
  const close = () => {
    menu.remove(); document.removeEventListener("pointerdown", outside, true); document.removeEventListener("keydown", esc, true);
    if (root.__rwMenuClose === close) root.__rwMenuClose = null;
  };
  const outside = e => { if (!menu.contains(e.target)) close(); };
  const esc = e => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  const menu = h("div", { class: ["rw-ctx", opts.cls], role: "menu" }, items.filter(Boolean).map(it => it.sep
    ? h("div", { class: "rw-ctx-sep" })
    : it.head ? h("div", { class: "rw-ctx-head" }, it.head)
    : h("button", {
      type: "button", role: "menuitem", class: ["rw-ctx-item", it.danger && "danger", it.cls], help: it.help, disabled: !!it.disabled,
      onClick: e => { e.stopPropagation(); close(); it.onClick?.(); },
    }, it.icon ? icon(it.icon, 13) : h("span", { class: "rw-ctx-ic" }), h("span", null, it.label), it.hint ? h("span", { class: "rw-ctx-hint mono" }, it.hint) : null)));
  root.__rwMenuClose = close;
  root.appendChild(menu);
  const rr = root.getBoundingClientRect();
  const sc = (rr.width / (root.offsetWidth || rr.width)) || 1;
  const x = (clientX - rr.left) / sc, y = (clientY - rr.top) / sc;
  menu.style.left = Math.max(4, Math.min(root.offsetWidth - menu.offsetWidth - 4, x)) + "px";
  menu.style.top = Math.max(4, Math.min(root.offsetHeight - menu.offsetHeight - 4, y)) + "px";
  setTimeout(() => { document.addEventListener("pointerdown", outside, true); document.addEventListener("keydown", esc, true); }, 0);
  return close;
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] Enter confirmed even with Cancel focused; Tab left the dialog; OK had focus, so Ctrl+Z went to ComfyUI
// added 2026-11-02 v0.3.0: a modal confirmation inside the editor. Resolves true/false.
// Enter confirms, Escape or a click outside cancels.
export function confirmDialog(root, { title, message, confirmLabel = "Delete", danger = true, cancelLabel = "Cancel" }) {
  return new Promise(resolve => {
    root.querySelectorAll(".rw-modal").forEach(m => m.remove());
    const key = e => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done(false); }
      else if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); done(true); }
    };
    // focus goes back to the editor so its shortcuts (Ctrl+Z) work right after the dialog closes
    const prev = document.activeElement;
    const done = v => {
      overlay.remove(); document.removeEventListener("keydown", key, true);
      const back = prev && prev.isConnected && root.contains(prev) ? prev : root;
      back.focus?.({ preventScroll: true });
      resolve(v);
    };
    const ok = button({ label: confirmLabel, variant: danger ? "danger" : "primary", help: "common.confirm", onClick: () => done(true) });
    const overlay = h("div", { class: "rw-modal", onPointerdown: e => { if (e.target === overlay) done(false); } },
      h("div", { class: "rw-modal-box", role: "alertdialog", "aria-modal": "true" },
        h("div", { class: "rw-modal-title" }, danger ? icon("warn", 15) : null, h("span", null, title)),
        message ? h("div", { class: "rw-modal-msg" }, message) : null,
        h("div", { class: "rw-modal-actions" }, button({ label: cancelLabel, help: "common.cancel", onClick: () => done(false) }), ok)));
    root.appendChild(overlay);
    document.addEventListener("keydown", key, true);
    ok.focus({ preventScroll: true });
  });
}
[/OLD] */

// added 2026-11-03 v0.6.0: a modal dialog inside the editor with any number of buttons. Resolves with the `value`
// of the button pressed, or `cancelValue` (Escape, a click outside the box, the editor closing, or another dialog
// opening). Keyboard: Tab / Shift+Tab stay on the dialog's buttons; Enter presses the focused button only (Enter
// with Cancel focused cancels); Space presses it as usual; Ctrl+Z / Ctrl+Y do nothing while it is open, and never
// reach ComfyUI (Ctrl moves focus to a hidden field first). Other keys don't reach the editor's shortcuts.
//   choices: [{value, label, variant?: "primary"|"danger"|"default", help?}] in display order
//   focus: the value whose button has focus at first (default: the cancel button when danger, else the last button)
export function choiceDialog(root, { title, message, choices, cancelValue = null, focus, danger = false, help } = {}) {
  return new Promise(resolve => {
    root.__rwModalClose?.(); // a dialog still open is cancelled, so its promise and listeners never leak
    root.querySelectorAll(".rw-modal").forEach(m => m.remove());
    const prev = document.activeElement;
    const sink = h("input", { class: "rw-keys", readonly: true, tabindex: "-1", "aria-hidden": "true", autocomplete: "off" });
    let closed = false;
    const inEditor = () => { const a = document.activeElement; return !a || a === document.body || root.contains(a); };
    const key = e => {
      if (!overlay.isConnected) { finish(cancelValue); return; }
      if (!inEditor()) return; // typing somewhere else in ComfyUI
      const mod = e.ctrlKey || e.metaKey;
      e.stopPropagation(); // the editor's shortcuts wait until the dialog is closed
      if (e.key === "Control" || e.key === "Meta") { if (!isTextField(document.activeElement)) sink.focus({ preventScroll: true }); return; }
      if (mod && /^[zy]$/i.test(e.key)) { e.preventDefault(); return; }
      if (e.key === "Escape") { e.preventDefault(); finish(cancelValue); return; }
      if (e.key === "Tab") {
        e.preventDefault();
        const live = btns.filter(b => !b.disabled);
        if (!live.length) return;
        const i = live.indexOf(document.activeElement);
        const j = i < 0 ? (e.shiftKey ? live.length - 1 : 0) : (i + (e.shiftKey ? -1 : 1) + live.length) % live.length;
        live[j].focus({ preventScroll: true });
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const i = btns.indexOf(document.activeElement);
        if (i >= 0 && !btns[i].disabled) finish(choices[i].value);
      }
    };
    const outside = e => { if (!root.contains(e.target)) finish(cancelValue); };
    const finish = v => {
      if (closed) return;
      closed = true;
      overlay.remove();
      document.removeEventListener("keydown", key, true);
      window.removeEventListener("pointerdown", outside, true);
      if (root.__rwModalClose === cancel) root.__rwModalClose = null;
      // focus goes back into the editor so its shortcuts (Ctrl+Z) work right after the dialog closes
      const back = prev && prev.isConnected && prev !== sink && root.contains(prev) ? prev : root;
      if (root.isConnected) back.focus?.({ preventScroll: true });
      resolve(v);
    };
    const cancel = () => finish(cancelValue);
    const btns = choices.map(c => button({ label: c.label, variant: c.variant || "default", help: c.help || (c.value === cancelValue ? "common.cancel" : "common.confirm"),
      onClick: () => finish(c.value) }));
    const overlay = h("div", { class: "rw-modal", onPointerdown: e => { if (e.target === overlay) finish(cancelValue); } },
      h("div", { class: ["rw-modal-box", choices.length > 2 && "wide"], role: "alertdialog", "aria-modal": "true", help },
        h("div", { class: "rw-modal-title" }, danger ? icon("warn", 15) : null, h("span", null, title)),
        message ? h("div", { class: "rw-modal-msg" }, message) : null,
        h("div", { class: "rw-modal-actions" }, btns),
        sink));
    root.appendChild(overlay);
    root.__rwModalClose = cancel;
    document.addEventListener("keydown", key, true);
    setTimeout(() => { if (!closed) window.addEventListener("pointerdown", outside, true); }, 0);
    let first = choices.findIndex(c => focus !== undefined && c.value === focus);
    if (first < 0) first = danger ? choices.findIndex(c => c.value === cancelValue) : -1;
    if (first < 0) first = choices.length - 1;
    btns[first]?.focus({ preventScroll: true });
  });
}

// A confirmation: Cancel and OK. Resolves true/false. Options: {title, message, confirmLabel | okLabel,
// cancelLabel, danger = true, help}. A dangerous one opens with Cancel focused, so Enter alone never deletes.
// added 2026-11-03 v0.6.0: built on choiceDialog
export function confirmDialog(root, { title, message, confirmLabel, okLabel, danger = true, cancelLabel = "Cancel", help } = {}) {
  return choiceDialog(root, {
    title, message, danger, help, cancelValue: false,
    choices: [
      { value: false, label: cancelLabel, help: "common.cancel" },
      { value: true, label: okLabel || confirmLabel || "Delete", variant: danger ? "danger" : "primary", help: "common.confirm" },
    ],
  });
}
