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

  function place(box, target, prefer = "below") {
    const r = target.getBoundingClientRect();
    const rr = root.getBoundingClientRect();
    box.style.left = "0px";
    box.style.top = "0px";
    const bw = box.offsetWidth, bh = box.offsetHeight;
    let x = r.left - rr.left + r.width / 2 - bw / 2;
    x = Math.max(8, Math.min(rr.width - bw - 8, x));
    let y = prefer === "below" ? r.bottom - rr.top + 8 : r.top - rr.top - bh - 8;
    if (y + bh > rr.height - 4) y = r.top - rr.top - bh - 8;
    if (y < 4) y = r.bottom - rr.top + 8;
    box.style.left = x + "px";
    box.style.top = y + "px";
  }

  function show(target) {
    const id = target.dataset.help;
    const entry = HELP[id];
    if (!entry) return;
    tip.textContent = entry.tip;
    tip.classList.add("on");
    place(tip, target);
    current = target;
  }

  function hide() {
    clearTimeout(timer);
    tip.classList.remove("on");
    current = null;
  }

  function openPopover(id, target) {
    const entry = HELP[id];
    if (!entry) return;
    pop.replaceChildren(
      h("div", { class: "rw-pop-head" }, h("b", null, entry.title || "Help"),
        h("button", { type: "button", class: "rw-pop-x", "aria-label": "Close help", help: "common.close", onClick: closePopover }, "×")),
      ...(entry.more || entry.tip).split("\n\n").map(p => h("p", null, p)));
    pop.classList.add("on");
    place(pop, target);
    hide();
  }

  function closePopover() {
    pop.classList.remove("on");
  }

  root.addEventListener("pointerover", e => {
    const t = e.target.closest?.("[data-help]");
    if (!t || !root.contains(t) || t === current) return;
    clearTimeout(timer);
    tip.classList.remove("on");
    timer = setTimeout(() => show(t), DELAY);
  });
  root.addEventListener("pointerout", e => {
    const t = e.target.closest?.("[data-help]");
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

  return { openPopover, closePopover, hide, isOpen: () => pop.classList.contains("on") };
}
