// The crop window: cut one or more parts out of a picture into pictures of their own, such as the person on the left
// of a group photo as an anchor. Draw a box, or let Find draw them: faces (insightface, or the object finder) or
// anything named ("person, dog, tea cup", the object finder: Grounding DINO in ComfyUI, downloaded on request). Each
// ticked box becomes a new picture asset (crop_of: {asset, box}) and can go straight into a cast member's anchors.
// Opened from an asset (Assets tab), from an anchor (Cast tab: the crop can take the original's place) or from a crop
// itself (Adjust crop: the same asset gets the new cut).

import { h, icon, button, choiceDialog } from "./ui.js";
import { rw, viewURL } from "./api.js";
import { newId, assignCodes, findAsset, findCast } from "./model.js";

const SMALL_SIDE = 400; // detect.SMALL_SIDE: a crop whose short side is smaller reaches H3 blurry
const MIN = 0.02;      // a drawn box smaller than this (part of the picture) is a click, not a box
const clamp01 = v => Math.max(0, Math.min(1, v));

// The pixel size a box cuts out of a w×h picture
export function boxPixels(box, w, h) {
  return [Math.round(box[2] * (w || 0)), Math.round(box[3] * (h || 0))];
}

// A box moved or resized by a drag: mode "move", "draw" or a corner ("nw", "ne", "sw", "se"); start = the box when
// the drag began, from / to = the pointer in parts of the picture. Always inside the picture, never inside out.
export function dragBox(mode, start, from, to) {
  const dx = to[0] - from[0], dy = to[1] - from[1];
  if (mode === "move") {
    const x = clamp01(Math.min(1 - start[2], start[0] + dx)), y = clamp01(Math.min(1 - start[3], start[1] + dy));
    return [x, y, start[2], start[3]];
  }
  let x1, y1, x2, y2;
  if (mode === "draw") [x1, y1, x2, y2] = [from[0], from[1], to[0], to[1]];
  else {
    [x1, y1, x2, y2] = [start[0], start[1], start[0] + start[2], start[1] + start[3]];
    if (mode.includes("w")) x1 += dx; else x2 += dx;
    if (mode.includes("n")) y1 += dy; else y2 += dy;
  }
  [x1, x2] = [clamp01(Math.min(x1, x2)), clamp01(Math.max(x1, x2))];
  [y1, y2] = [clamp01(Math.min(y1, y2)), clamp01(Math.max(y1, y2))];
  return [x1, y1, x2 - x1, y2 - y1];
}

// opts: { cast: the cast member whose Anchors opened it, adjust: the crop asset to cut again }
export async function openCrop(ctx, src, opts = {}) {
  const p = ctx.p;
  const target = opts.adjust ? findAsset(p, opts.adjust) : null;
  const fromCast = opts.cast ? findCast(p, opts.cast) : null;
  const W = src.width || 0, H = src.height || 0;
  const st = { items: [], active: null, mode: "faces", queries: "person", busy: false, error: "", note: "", status: null,
    replace: !!(fromCast && fromCast.anchors.includes(src.id)), poll: 0, seq: 0, closed: false };
  const castOptions = [{ value: "", label: "— not an anchor" }, ...p.cast.map(c => ({ value: c.id, label: `${c.name} · ${c.kind}` }))];
  const add = (box, label, score, source, extra = {}) => {
    const it = { id: "b" + (++st.seq), box, label, score, source, picked: false, cast: "", name: `${src.name || src.code} · ${label}`, ...extra };
    st.items.push(it);
    return it;
  };
  const pick = (it, on) => {
    it.picked = on;
    // the first picked box goes to the cast member whose anchors opened the window
    if (on && fromCast && !it.target && !st.items.some(x => x !== it && x.picked && x.cast === fromCast.id)) it.cast = fromCast.id;
  };
  if (target?.crop_of) {
    const it = add(target.crop_of.box.slice(), target.name || target.code, null, "crop", { target: target.id, name: target.name });
    it.picked = true;
    st.active = it.id;
  }

  // ---- the picture and its boxes
  const img = h("img", { src: viewURL(src.file, "input"), alt: src.name || src.code, draggable: "false" });
  const layer = h("div", { class: "rw-crop-layer" });
  const stage = h("div", { class: "rw-crop-stage", help: "crop.box" }, img, layer);
  const at = e => { const r = stage.getBoundingClientRect(); return [clamp01((e.clientX - r.left) / r.width), clamp01((e.clientY - r.top) / r.height)]; };
  let drag = null;
  stage.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    e.preventDefault();
    const hit = e.target.closest?.("[data-item]");
    const it = hit && st.items.find(x => x.id === hit.dataset.item);
    const from = at(e);
    if (it && e.target.dataset.corner) drag = { mode: e.target.dataset.corner, it, start: it.box.slice(), from };
    else if (it) {
      if (st.active !== it.id) { st.active = it.id; if (!it.picked) pick(it, true); }
      drag = { mode: "move", it, start: it.box.slice(), from };
    } else {
      const nb = add([from[0], from[1], 0, 0], `box ${st.items.filter(x => x.source === "drawn").length + 1}`, null, "drawn");
      pick(nb, true);
      st.active = nb.id;
      drag = { mode: "draw", it: nb, start: nb.box.slice(), from, fresh: true };
    }
    stage.setPointerCapture?.(e.pointerId);
    paint();
  });
  stage.addEventListener("pointermove", e => {
    if (!drag) return;
    drag.it.box = dragBox(drag.mode, drag.start, drag.from, at(e));
    paint();
  });
  const end = () => {
    if (!drag) return;
    const { it, fresh } = drag;
    drag = null;
    if (fresh && (it.box[2] < MIN || it.box[3] < MIN)) { st.items = st.items.filter(x => x !== it); st.active = null; }
    paint();
  };
  stage.addEventListener("pointerup", end);
  stage.addEventListener("pointercancel", end);

  // ---- Find
  const query = h("input", { class: "rw-input grow", value: st.queries, placeholder: "person, dog, tea cup", help: "crop.find.query",
    onInput: e => { st.queries = e.target.value; } });
  const findBar = h("div", { class: "rw-row wrap rw-crop-find" });
  const list = h("div", { class: "rw-crop-list" });
  const note = h("div", { class: "small" });
  const replaceRow = h("label", { class: "rw-row small rw-crop-replace", help: "crop.replace" });

  const find = async () => {
    if (st.busy) return;
    st.busy = true; st.error = ""; st.note = "";
    paint();
    try {
      const queries = st.queries.split(/[,;\n]/).map(s => s.trim()).filter(Boolean);
      const r = await rw.detect(p.slug, src.file, st.mode, st.mode === "objects" ? queries : []);
      st.items = st.items.filter(x => x.source !== "found" || x.picked);
      const n = new Map();
      for (const b of r.boxes || []) {
        n.set(b.label, (n.get(b.label) || 0) + 1);
        add(b.box, `${b.label} ${n.get(b.label)}`, b.score, "found");
      }
      st.note = (r.boxes || []).length ? `Found ${(r.boxes || []).length} with ${r.engine === "insightface" ? "insightface" : "the object finder"} in ${((r.ms || 0) / 1000).toFixed(1)} s: click a box, or tick it below.`
        : `Nothing found${st.mode === "objects" ? " for “" + queries.join(", ") + "”" : ""}. Draw a box instead, or name it differently.`;
    } catch (err) { st.error = err.message; }
    st.busy = false;
    paint();
  };
  const refreshStatus = async () => {
    try { st.status = await rw.detectStatus(); } catch (err) { st.status = { error: err.message }; }
    if (st.closed) return;
    clearTimeout(st.poll);
    if (st.status?.objects?.state === "downloading") st.poll = setTimeout(refreshStatus, 1500);
    paint();
  };
  const download = async () => {
    try { st.status = await rw.detectDownload(); } catch (err) { st.error = err.message; }
    refreshStatus();
  };

  const mb = n => Math.round((n || 0) / 1e6);
  function paintFind() {
    const s = st.status, obj = s?.objects, faces = s?.faces;
    const objReady = !!obj?.ready;
    const canFind = st.mode === "faces" ? !!(faces?.ready || objReady) : objReady;
    const engine = !s ? "checking…" : st.mode === "faces"
      ? (faces?.ready ? "insightface" : objReady ? "the object finder" : "needs insightface or the object finder")
      : objReady ? "the object finder (Grounding DINO)" : "";
    const dl = obj && !objReady && (st.mode === "objects" || !faces?.ready);
    fill(findBar, [
      h("span", { class: "rw-dim small" }, "Find"),
      h("div", { class: "rw-seg rw-seg-sm", role: "radiogroup", help: "crop.find" },
        [["faces", "Faces", "crop.find.faces"], ["objects", "Things", "crop.find.objects"]].map(([v, label, help]) =>
          h("button", { type: "button", role: "radio", "aria-checked": st.mode === v ? "true" : "false", class: ["rw-seg-btn", st.mode === v && "on"], help,
            onClick: () => { st.mode = v; paint(); } }, label))),
      st.mode === "objects" ? query : null,
      button({ label: st.busy ? "Looking…" : "Find", icon: "search", small: true, variant: "accent-ghost", help: "crop.find.run", disabled: st.busy || !canFind, onClick: find }),
      h("span", { class: "rw-dim small" }, engine),
      dl ? (obj.state === "downloading"
        ? h("span", { class: "small rw-c-vid", help: "crop.download" }, `Downloading the object finder… ${mb(obj.done)} / ${mb(obj.bytes)} MB`)
        : button({ label: `Download the object finder (${mb(obj.bytes)} MB)`, icon: "download", small: true, help: "crop.download", onClick: download })) : null,
      !objReady && obj?.state === "error" && obj.error ? h("span", { class: "small rw-c-err" }, `Download failed: ${obj.error}`) : null]);
  }
  // replaceChildren() would print a null as "null"
  const fill = (el, kids) => el.replaceChildren(...kids.flat().filter(Boolean));
  function paintBoxes() {
    fill(layer, st.items.map(it => {
      const [x, y, w, hh] = it.box;
      const on = st.active === it.id;
      const [pw, ph] = boxPixels(it.box, W, H);
      return h("div", { class: ["rw-crop-box", it.source, it.picked && "picked", on && "active", W && Math.min(pw, ph) < SMALL_SIDE && "small"], dataset: { item: it.id },
        style: { left: x * 100 + "%", top: y * 100 + "%", width: w * 100 + "%", height: hh * 100 + "%" } },
        h("span", { class: "rw-crop-tag" }, it.label + (it.score != null ? ` ${Number(it.score).toFixed(2)}` : "")),
        on ? ["nw", "ne", "sw", "se"].map(c => h("span", { class: ["rw-crop-handle", c], dataset: { corner: c, item: it.id } })) : null);
    }));
  }
  function paintList() {
    const shown = st.items.filter(it => it.picked || it.source !== "found" || st.active === it.id);
    const rest = st.items.length - shown.length;
    fill(list, [...shown.map(it => {
      const [pw, ph] = boxPixels(it.box, W, H);
      const small = W && Math.min(pw, ph) < SMALL_SIDE;
      const sel = h("select", { class: "rw-select rw-crop-cast", help: "crop.item.cast", disabled: !!it.target, onChange: e => { it.cast = e.target.value; paint(); } },
        castOptions.map(o => h("option", { value: o.value, selected: o.value === (it.cast || "") ? "selected" : null }, o.label)));
      return h("div", { class: ["rw-crop-row", st.active === it.id && "on"] },
        h("input", { type: "checkbox", checked: it.picked ? "checked" : null, help: "crop.item.pick", onChange: e => { pick(it, e.target.checked); paint(); } }),
        h("input", { class: "rw-input grow", value: it.name, help: "crop.item.name", onInput: e => { it.name = e.target.value; },
          onFocus: () => { if (st.active !== it.id) { st.active = it.id; paintBoxes(); } } }),
        h("span", { class: ["mono small", small ? "rw-c-warn" : "rw-dim"], help: "crop.item.size", title: small ? "Under 400 px on its short side: H3 gets it blurry. A bigger picture of the same thing works better." : null },
          W ? `${pw}×${ph}${small ? " small" : ""}` : ""),
        it.target ? h("span", { class: "rw-dim small" }, "cuts this crop again") : sel,
        it.source !== "crop" ? h("button", { type: "button", class: "rw-anchor-x rw-crop-x", "aria-label": "Remove box", help: "crop.item.remove",
          onClick: () => { st.items = st.items.filter(x => x !== it); if (st.active === it.id) st.active = null; paint(); } }, icon("close", 11)) : null);
    }), rest ? h("div", { class: "rw-dim small" }, `${rest} more found: click ${rest === 1 ? "it" : "them"} on the picture to use ${rest === 1 ? "it" : "them"}.`) : null]);
    const firstForCast = fromCast && st.items.find(it => it.picked && !it.target && it.cast === fromCast.id);
    fill(replaceRow, (fromCast && fromCast.anchors.includes(src.id) && !target ? [
      h("input", { type: "checkbox", checked: st.replace ? "checked" : null, disabled: !firstForCast, onChange: e => { st.replace = e.target.checked; } }),
      h("span", { class: firstForCast ? "" : "rw-dim" }, `Put ${firstForCast ? "“" + firstForCast.name + "”" : "the crop"} in place of ${src.code} in ${fromCast.name}'s anchors (${src.code} stays in the assets)`)] : []));
  }
  function paintButtons() {
    const save = box.querySelector("[data-choice='save']");
    if (!save) return;
    const n = st.items.filter(it => it.picked).length;
    save.disabled = !n;
    save.querySelector("span:last-child").textContent = target && n === 1 && st.items.find(it => it.picked)?.target ? "Cut again"
      : n > 1 ? `Save ${n} pictures` : "Save the crop";
  }
  function paint() {
    if (st.closed) return;
    paintFind(); paintBoxes(); paintList(); paintButtons();
    note.className = ["small", st.error ? "rw-c-err" : "rw-dim"].join(" ");
    note.textContent = st.error || st.note || "Drag on the picture to draw a box; drag a box to move it, its corners to resize it.";
  }

  const body = h("div", { class: "rw-crop" },
    h("div", { class: "rw-crop-wrap" }, stage),
    findBar, note, list, replaceRow);
  const pending = choiceDialog(ctx.root, {
    title: target ? `Adjust the crop ${target.code} of ${src.code}` : `Crop ${src.code}${src.name ? " · " + src.name : ""}`, message: body, help: "crop", cls: "crop",
    cancelValue: "cancel", focus: "cancel",
    choices: [{ value: "cancel", label: "Cancel" }, { value: "save", label: "Save the crop", variant: "primary", help: "crop.save" }],
  });
  const box = body.closest(".rw-modal-box");
  box.querySelector(".rw-modal-actions button:last-child").dataset.choice = "save";
  paint();
  refreshStatus();
  const choice = await pending;
  st.closed = true;
  clearTimeout(st.poll);
  if (choice !== "save") return null;
  return saveCrops(ctx, src, st.items.filter(it => it.picked), { fromCast, replace: st.replace });
}

// Cut each picked box on the server, then add the pictures (one undo step): a new asset per box, in the cast
// member's anchors it was given to; a re-cut crop keeps its id and gets the new file.
async function saveCrops(ctx, src, items, { fromCast, replace }) {
  const cut = [];
  for (const it of items) {
    try {
      const box = it.box.map(v => Math.round(v * 10000) / 10000);
      const r = await rw.crop(ctx.p.slug, src.file, box, (it.name || "").trim() || src.name || "crop");
      cut.push({ it, box, a: r.asset, small: r.small });
    } catch (err) {
      ctx.actions.toast(`Could not crop “${it.name}”: ${err.message}`, "error");
      return null;
    }
  }
  if (!cut.length) return null;
  const made = [], recut = [];
  let replaced = "";
  ctx.actions.edit(q => {
    for (const { it, box, a } of cut) {
      const crop_of = { asset: src.id, box };
      if (it.target) {
        const t = q.assets.find(x => x.id === it.target);
        if (t) { Object.assign(t, { file: a.file, width: a.width, height: a.height, crop_of, name: (it.name || "").trim() || t.name }); recut.push(t.code); }
        continue;
      }
      const s = q.assets.find(x => x.id === src.id);
      const na = { id: newId("a"), code: "", kind: "image", name: (it.name || "").trim() || a.name, file: a.file, duration: 0, width: a.width, height: a.height,
        category: s?.category || "subject", defaults: { role: "reference", retention: "fully_preserved", keep: [], soundtrack: false },
        notes: "", description: "", group: s?.group || "", tags: [], crop_of };
      q.assets.push(na);
      made.push(na);
      const c = it.cast && q.cast.find(x => x.id === it.cast);
      if (!c) continue;
      const k = c.anchors.indexOf(src.id);
      if (replace && fromCast && c.id === fromCast.id && k >= 0 && !replaced) { c.anchors[k] = na.id; replaced = c.name; }
      else if (!c.anchors.includes(na.id)) c.anchors.push(na.id);
    }
    assignCodes(q.assets);
  }, { label: `Crop ${src.code}` });
  const codes = made.map(a => a.code).filter(Boolean);
  const small = cut.filter(x => x.small).map(x => `${x.it.name} (${x.a.width}×${x.a.height})`);
  ctx.actions.toast([codes.length ? `${codes.join(", ")} cut from ${src.code}.` : "", recut.length ? `${recut.join(", ")} cut again from ${src.code}.` : "",
    replaced ? `It took ${src.code}'s place in ${replaced}'s anchors.` : "",
    small.length ? `Small: ${small.join(", ")}; H3 gets ${small.length === 1 ? "it" : "them"} blurry.` : ""].filter(Boolean).join(" "), small.length ? "warn" : "ok");
  return made;
}
