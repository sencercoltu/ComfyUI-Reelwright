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
      else if (k === "key") el.dataset.key = v;
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
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
      list = h("div", { class: ["rw-combo-list", mono && "mono"], role: "listbox" });
      root.appendChild(list);
      comboState.open++;
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
      e.preventDefault();
      const q = input.value === shown ? "" : input.value;
      if (active >= 0 && active < items.length) choose(items[active]);
      else if (free && q.trim()) choose({ value: q.trim(), label: q.trim() });
      input.blur();
    } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); revert(); close(); input.blur(); }
  });
  input.addEventListener("blur", () => {
    setTimeout(() => {
      if (done) return;
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

export function number({ value, onChange, help, key, min, max, step = 1, width = "84px", unit, mono = true }) {
  const input = h("input", {
    type: "number", class: ["rw-input", mono && "mono"], help, key, value: value ?? "", min, max, step,
    style: { width },
    onChange: e => {
      if (e.target.value === "") { onChange(null); return; }
      let v = Number(e.target.value);
      if (Number.isNaN(v)) return;
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

export function field(label, control, { help, dot: dotState, reset, wide } = {}) {
  return h("div", { class: ["rw-field", wide && "wide"] },
    h("span", { class: "rw-field-label", help }, label),
    h("span", { class: "rw-field-ctl" }, control),
    dotState && dot(dotState),
    reset !== undefined && (reset
      ? button({ icon: "refresh", help: "common.reset", onClick: reset, small: true, variant: "ghost" })
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

export function keepChips({ values, onChange, help, placeholder = "+ feature" }) {
  const input = h("input", {
    class: "rw-chip-input", placeholder, help,
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

export function confirmInline(host, message, onYes) {
  const bar = h("div", { class: "rw-confirm" },
    h("span", null, message),
    button({ label: "Cancel", help: "common.cancel", small: true, onClick: () => bar.remove() }),
    button({ label: "Confirm", help: "common.confirm", small: true, variant: "danger", onClick: () => { bar.remove(); onYes(); } }));
  host.appendChild(bar);
}
