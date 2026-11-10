// Hover/focus tooltips for every [data-help] element and click popovers for
// the "?" buttons. Both are positioned inside the editor root.

import { HELP } from "./help.js";
import { h } from "./ui.js";

const DELAY = 350;

export function installTooltips(root) {
  const tip = h("div", { class: "rw-tip", role: "tooltip" });
  const pop = h("div", { class: "rw-pop", role: "dialog" });
  root.append(tip, pop);
  let timer = 0;
  let current = null;

  // Positions are computed in the root's own (unscaled) pixels.
  // "right" anchors beside the target (used for ? icons) and flips left, then below, when there is no room;
  // the box is always clamped inside the node.
  const scale = () => { const rr = root.getBoundingClientRect(); return (rr.width / (root.offsetWidth || rr.width)) || 1; };
  function place(box, target, prefer = "below") {
    const sc = scale();
    const rr = root.getBoundingClientRect(), tr = target.getBoundingClientRect();
    const r = { left: (tr.left - rr.left) / sc, right: (tr.right - rr.left) / sc, top: (tr.top - rr.top) / sc, bottom: (tr.bottom - rr.top) / sc };
    r.width = r.right - r.left;
    const W = root.offsetWidth, H = root.offsetHeight, gap = 8;
    box.style.left = "0px";
    box.style.top = "0px";
    const bw = box.offsetWidth, bh = box.offsetHeight;
    let x, y;
    if (prefer === "right" && r.right + gap + bw <= W - gap) { x = r.right + gap; y = r.top - 6; }
    else if (prefer === "right" && r.left - gap - bw >= gap) { x = r.left - gap - bw; y = r.top - 6; }
    else {
      x = r.left + r.width / 2 - bw / 2;
      y = r.bottom + gap;
      if (y + bh > H - 4) y = r.top - bh - gap;
    }
    box.style.left = Math.max(gap, Math.min(W - bw - gap, x)) + "px";
    box.style.top = Math.max(4, Math.min(H - bh - 4, y)) + "px";
  }

  // Drag the help popover by its header
  function dragFrom(e) {
    if (e.button !== 0 || e.target.closest(".rw-pop-x")) return;
    e.preventDefault();
    e.stopPropagation();
    const sc = scale();
    const x0 = e.clientX, y0 = e.clientY, l0 = pop.offsetLeft, t0 = pop.offsetTop;
    const head = e.currentTarget;
    head.setPointerCapture?.(e.pointerId);
    pop.classList.add("dragging");
    const move = ev => {
      const W = root.offsetWidth, H = root.offsetHeight;
      pop.style.left = Math.max(0, Math.min(W - pop.offsetWidth, l0 + (ev.clientX - x0) / sc)) + "px";
      pop.style.top = Math.max(0, Math.min(H - 28, t0 + (ev.clientY - y0) / sc)) + "px";
    };
    const up = () => {
      pop.classList.remove("dragging");
      head.removeEventListener("pointermove", move);
      head.removeEventListener("pointerup", up);
      head.removeEventListener("pointercancel", up);
    };
    head.addEventListener("pointermove", move);
    head.addEventListener("pointerup", up);
    head.addEventListener("pointercancel", up);
  }

  // An element's data-detail (a spoken line or camera phrase in full, why a button is off)
  // is shown first, the help text under it
  function show(target) {
    const id = target.dataset.help;
    const entry = HELP[id];
    const detail = target.dataset.detail;
    if (!entry && !detail) return;
    tip.replaceChildren(detail ? h("div", { class: "rw-tip-detail" }, detail) : "", entry ? h("div", { class: detail ? "rw-tip-help" : null }, entry.tip) : "");
    tip.classList.add("on");
    place(tip, target, target.classList.contains("rw-q") ? "right" : "below");
    current = target;
  }

  function hide() {
    clearTimeout(timer);
    tip.classList.remove("on");
    current = null;
    waiting = null;
  }
  let waiting = null; // the element whose tooltip waits for DELAY
  const sameAs = (a, b) => !!a && !!b && a.dataset.help === b.dataset.help && a.dataset.key === b.dataset.key && a.dataset.detail === b.dataset.detail;

  function openPopover(id, target) {
    const entry = HELP[id];
    if (!entry) return;
    pop.replaceChildren(
      h("div", { class: "rw-pop-head", title: "Drag to move", onPointerdown: dragFrom }, h("b", null, entry.title || "Help"),
        h("button", { type: "button", class: "rw-pop-x", "aria-label": "Close help", help: "common.close", onClick: closePopover }, "×")),
      h("div", { class: "rw-pop-body" }, ...(entry.more || entry.tip).split("\n\n").map(p => h("p", null, p))));
    pop.classList.add("on");
    place(pop, target, "right");
    hide();
  }

  function closePopover() {
    pop.classList.remove("on");
  }

  root.addEventListener("pointerover", e => {
    const t = e.target.closest?.("[data-help], [data-detail]");
    if (!t || !root.contains(t) || t === current || t === waiting) return;
    if (current && !current.isConnected && sameAs(t, current) && tip.classList.contains("on")) {
      current = t;
      place(tip, t, t.classList.contains("rw-q") ? "right" : "below");
      return;
    }
    if (waiting && !waiting.isConnected && sameAs(t, waiting)) { waiting = t; return; }
    clearTimeout(timer);
    tip.classList.remove("on");
    current = null;
    waiting = t;
    timer = setTimeout(() => { const x = waiting; waiting = null; if (x?.isConnected) show(x); }, DELAY);
  });
  root.addEventListener("pointerout", e => {
    const t = e.target.closest?.("[data-help], [data-detail]");
    if (t && !t.contains(e.relatedTarget)) hide();
  });
  root.addEventListener("pointerdown", e => {
    hide();
    if (!pop.contains(e.target) && !e.target.closest?.(".rw-q")) closePopover();
  });
  root.addEventListener("focusin", e => {
    const t = e.target.closest?.("[data-help]");
    if (t && e.target.matches(":focus-visible")) { clearTimeout(timer); timer = setTimeout(() => show(t), DELAY); }
  });
  root.addEventListener("focusout", hide);
  root.addEventListener("click", e => {
    const q = e.target.closest?.(".rw-q");
    if (q) { e.stopPropagation(); openPopover(q.dataset.more, q); }
  });
  root.addEventListener("keydown", e => {
    if (e.key === "Escape") { hide(); closePopover(); }
  });

  return { openPopover, closePopover, hide, isOpen: () => pop.classList.contains("on"), destroy() { hide(); closePopover(); } };
}
