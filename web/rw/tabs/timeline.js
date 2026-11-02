// Timeline tab: asset bin, monitor with transport, quick inspector, and the
// multi-lane timeline (scenes, pictures, video, audio, dialogue, camera, LoRAs).

// [OLD 2026-11-02 v0.2.2->v0.3.0] import { h, icon, button, toggle, segmented, chip, dot, slider } from "../ui.js";
import { h, icon, button, toggle, segmented, chip, dot, slider, select } from "../ui.js";
import { viewURL } from "../api.js";
import { highlightHTML } from "../prompttext.js";
import {
  FPS, sceneStarts, fmtTime, framesOf, nearestGridFrames, estimatePasses, findAsset, findCast,
  effectiveLoras, overrideCount, sceneIndex, newId, assembledDuration, MIN_PASS_FRAMES,
  effective, // added 2026-11-02 v0.3.0
} from "../model.js";
import { uploadFiles } from "./assets.js";

const HEAD_W = 150;
const STATUS_LABEL = {
  cached: "On disk", stale: "Stale", pending: "Not rendered", missing: "Not rendered", queued: "Queued",
  rendering: "Rendering", locked: "Locked", error: "Failed", unknown: "Status unknown",
};

function zoomOf(ctx) {
  return ctx.p.ui.zoom || 22;
}

function sceneAt(ctx, t) {
  const { starts } = sceneStarts(ctx.p);
  for (const s of ctx.p.scenes) if (t >= starts[s.id] && t < starts[s.id] + s.duration) return s;
  return ctx.p.scenes[ctx.p.scenes.length - 1];
}

function storyboardImage(ctx, scene) {
  const p = ctx.p;
  const ref = scene.refs.find(r => findAsset(p, r.asset)?.kind === "image" && r.role !== "last_frame");
  if (ref) return viewURL(findAsset(p, ref.asset).file, "input");
  for (const sc of scene.cast) {
    const c = findCast(p, sc.id);
    const a = c && findAsset(p, c.anchors[0]);
    if (a) return viewURL(a.file, "input");
  }
  return "";
}

// ---- Monitor (persistent across re-renders so playback is not interrupted) ----

function monitorOf(ctx) {
  if (ctx.monitor) return ctx.monitor;
  const video = h("video", { class: "rw-mon-video", playsinline: true, preload: "auto" });
  const img = h("img", { class: "rw-mon-img", alt: "" });
  const empty = h("div", { class: "rw-mon-empty" });
  const badgeTL = h("span", { class: "rw-mon-badge tl" });
  const badgeTR = h("span", { class: "rw-mon-badge tr mono", help: "timeline.monitor.format" });
  const badgeBL = h("span", { class: "rw-mon-badge bl mono" });
  const badgeBR = h("span", { class: "rw-mon-badge br" });
  const el = h("div", { class: "rw-mon", help: "timeline.monitor" }, video, img, empty, h("div", { class: "rw-mon-safe" }), badgeTL, badgeTR, badgeBL, badgeBR);
  const m = ctx.monitor = { el, video, img, empty, badgeTL, badgeTR, badgeBL, badgeBR, sceneId: null, src: "" };

  m.show = (scene, local) => {
    const take = ctx.starredTake(scene.id);
    const src = take?.files?.video ? viewURL(take.files.video) : "";
    if (m.sceneId !== scene.id || m.src !== src) {
      m.sceneId = scene.id;
      m.src = src;
      if (src) { video.src = src; video.style.display = ""; img.style.display = "none"; empty.style.display = "none"; }
      else {
        video.removeAttribute("src"); video.load(); video.style.display = "none";
        const sb = storyboardImage(ctx, scene);
        img.style.display = sb ? "" : "none";
        if (sb) img.src = sb;
        empty.style.display = sb ? "none" : "";
        empty.textContent = sb ? "" : scene.title;
      }
    }
    if (src && Math.abs(video.currentTime - local) > 0.08 && !ctx.eph.playing) {
      try { video.currentTime = Math.max(0, local); } catch { /* not loaded yet */ }
    }
    const status = ctx.statusOf(scene.id);
    badgeTL.textContent = src ? (status === "stale" ? "STALE · last take " + (take.id || "") : "TAKE " + (take.id || "")) : "STORYBOARD";
    badgeTL.className = "rw-mon-badge tl " + (src ? (status === "stale" ? "warn" : "ok") : "");
    badgeTL.dataset.help = src ? "timeline.monitor.take" : "timeline.monitor.storyboard";
    const g = ctx.p.global.output;
    badgeTR.textContent = `${g.width}×${g.height} · 24 fps`;
    const idx = sceneIndex(ctx.p, scene.id) + 1;
    badgeBL.textContent = `${String(idx).padStart(2, "0")} · f ${Math.min(framesOf(local), framesOf(scene.duration))} / ${framesOf(scene.duration)}`;
    const line = scene.dialogue.find(d => local >= d.t && local < d.t + 3.5);
    const sp = line && findCast(ctx.p, line.speaker);
    // [OLD 2026-11-02 v0.1.0->v0.2.0] badgeBR.textContent = line ? `${sp?.name || "?"} (${sp?.speaker || "S?"}): “${line.text}”` : "";  (speaker IDs are per clip now)
    badgeBR.textContent = line ? `${sp?.name || "?"}: “${line.text}”` : "";
    badgeBR.style.display = line ? "" : "none";
  };
  return m;
}

function setPlayhead(ctx, t, { seekVideo = true } = {}) {
  const { total } = sceneStarts(ctx.p);
  t = Math.max(0, Math.min(total, t));
  ctx.store.update(p => { p.ui.playhead = t; }, { history: false, plan: false, render: false, autosave: false });
  const refs = ctx.tl;
  const z = zoomOf(ctx);
  if (refs?.playhead) {
    refs.playhead.style.left = (HEAD_W + t * z) + "px";
    refs.playheadLabel.textContent = fmtTime(t);
    refs.timecode.textContent = fmtTime(t);
  }
  const s = sceneAt(ctx, t);
  const local = t - sceneStarts(ctx.p).starts[s.id];
  const m = monitorOf(ctx);
  if (seekVideo) m.show(s, local);
  return { scene: s, local };
}

let raf = 0;
export function stopPlayback(ctx) {
  cancelAnimationFrame(raf);
  raf = 0;
  ctx.eph.playing = false;
  if (ctx.monitor) ctx.monitor.video.pause();
}

function startPlayback(ctx) {
  if (ctx.eph.playing) return;
  const { total } = sceneStarts(ctx.p);
  if (ctx.p.ui.playhead >= total - 1 / FPS) setPlayhead(ctx, 0);
  ctx.eph.playing = true;
  const m = monitorOf(ctx);
  let last = performance.now();
  let current = setPlayhead(ctx, ctx.p.ui.playhead);
  if (m.src) { m.video.currentTime = current.local; m.video.play().catch(() => {}); }
  const loop = now => {
    if (!ctx.eph.playing) return;
    const dt = (now - last) / 1000;
    last = now;
    const { starts, total: tot } = sceneStarts(ctx.p);
    let t;
    if (m.src && !m.video.paused && m.sceneId === current.scene.id) t = starts[current.scene.id] + Math.min(m.video.currentTime, current.scene.duration);
    else t = ctx.p.ui.playhead + dt;
    const loopR = ctx.eph.loop;
    if (loopR && t >= loopR.out) t = loopR.in;
    if (t >= tot) { setPlayhead(ctx, tot); stopPlayback(ctx); ctx.render(); return; }
    const before = current.scene.id;
    const localEnd = t - starts[current.scene.id] >= current.scene.duration;
    current = setPlayhead(ctx, t, { seekVideo: localEnd || current.scene.id !== sceneAt(ctx, t).id || !m.src });
    if (current.scene.id !== before || localEnd) {
      if (m.src) { m.video.currentTime = current.local; m.video.play().catch(() => {}); }
    }
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);
  ctx.render();
}

function togglePlay(ctx) {
  if (ctx.eph.playing) { stopPlayback(ctx); ctx.render(); } else startPlayback(ctx);
}

// ---- Keyboard ----

export function onKey(ctx, e) {
  const p = ctx.p;
  const k = e.key;
  if (k === " ") { togglePlay(ctx); return true; }
  if (k === "k" || k === "K") { stopPlayback(ctx); ctx.render(); return true; }
  if (k === "l" || k === "L") { startPlayback(ctx); return true; }
  if (k === "j" || k === "J") { setPlayhead(ctx, p.ui.playhead - 1); return true; }
  if (k === "ArrowLeft") { setPlayhead(ctx, p.ui.playhead - (e.shiftKey ? 1 : 1 / FPS)); return true; }
  if (k === "ArrowRight") { setPlayhead(ctx, p.ui.playhead + (e.shiftKey ? 1 : 1 / FPS)); return true; }
  if (k === "Home") { setPlayhead(ctx, 0); return true; }
  if (k === "End") { setPlayhead(ctx, sceneStarts(p).total); return true; }
  if (k === "i" || k === "I") { ctx.store.setEph({ loop: { in: p.ui.playhead, out: Math.max(p.ui.playhead + 0.5, ctx.eph.loop?.out ?? sceneStarts(p).total) } }); return true; }
  if (k === "o" || k === "O") { ctx.store.setEph({ loop: { in: Math.min(ctx.eph.loop?.in ?? 0, p.ui.playhead - 0.5), out: p.ui.playhead } }); return true; }
  if (k === "m" || k === "M") { addMarker(ctx); return true; }
  if (k === "+" || k === "=") { setZoom(ctx, zoomOf(ctx) * 1.25); return true; }
  if (k === "-") { setZoom(ctx, zoomOf(ctx) / 1.25); return true; }
  return false;
}

// Scene shortcuts that work from any tab.
export function sceneKeys(ctx, e) {
  const s = ctx.scene;
  if (!s) return false;
  const k = e.key;
  if (k === "s" || k === "S") {
    const { starts } = sceneStarts(ctx.p);
    ctx.actions.splitScene(s.id, ctx.p.ui.playhead - starts[s.id]);
    return true;
  }
  if (k === "d" || k === "D") { ctx.actions.duplicateScene(s.id); return true; }
  if (k === "Delete" || k === "Backspace") { ctx.actions.deleteScene(s.id); return true; }
  if (k === "n" || k === "N") { ctx.actions.addScene(s.id); return true; }
  return false;
}

function setZoom(ctx, z) {
  z = Math.max(4, Math.min(160, z));
  ctx.store.update(p => { p.ui.zoom = Math.round(z * 10) / 10; }, { history: false, plan: false, autosave: false });
}

function addMarker(ctx) {
  const id = newId("m");
  ctx.store.update(p => { p.markers.push({ id, t: p.ui.playhead, text: "Marker", color: "amber" }); });
  ctx.store.setEph({ selectedMarker: id });
}

// ---- Asset bin ----

function renderBin(ctx) {
  const p = ctx.p;
  const groups = [["image", "Pictures", "pic"], ["video", "Videos", "vid"], ["audio", "Audio", "aud"]];
  const fileInput = h("input", {
    type: "file", multiple: true, accept: "image/*,video/*,audio/*", style: { display: "none" },
    onChange: e => uploadFiles(ctx, [...e.target.files]),
  });
  return h("div", { class: "rw-bin rw-panel" },
    h("div", { class: "rw-panel-head" }, h("b", null, "Asset bin"), h("span", { class: "mono rw-dim" }, p.assets.length),
      h("button", { type: "button", class: "rw-q", dataset: { more: "timeline.bin" }, help: "timeline.bin", "aria-label": "Help" }, "?"),
      h("span", { class: "rw-flex" }),
      button({ icon: "upload", help: "timeline.bin.upload", small: true, onClick: () => fileInput.click() }), fileInput),
    h("div", { class: "rw-bin-list", dataset: { scroll: "bin" } },
      p.assets.length === 0 && h("div", { class: "rw-empty sm", help: "timeline.bin" }, "Drop images, video or audio here, then drag them onto a scene."),
      groups.map(([kind, label, cls]) => {
        const items = p.assets.filter(a => a.kind === kind);
        if (!items.length) return null;
        return h("div", { class: "rw-bin-group" },
          h("div", { class: "rw-bin-label rw-c-" + cls }, icon(kind, 12), label, h("span", { class: "mono rw-dim" }, items.length)),
          items.map(a => h("div", {
            class: ["rw-bin-item", ctx.eph.selectedAsset === a.id && "on"], draggable: "true", help: "timeline.bin.item",
            onDragstart: e => { e.dataTransfer.setData("application/x-rw-asset", a.id); e.dataTransfer.effectAllowed = "copy"; },
            onClick: () => ctx.store.setEph({ selectedAsset: a.id }),
            onDblclick: () => { ctx.store.setEph({ selectedAsset: a.id }); ctx.actions.setTab("assets"); },
            menu: () => assetMenu(ctx, a), // added 2026-11-02 v0.3.0
          },
          kind === "image" ? h("img", { class: "rw-bin-thumb", src: viewURL(a.file, "input"), alt: "", loading: "lazy" }) : h("span", { class: "rw-bin-thumb rw-bg-" + cls + "-soft" }, icon(kind, 12)),
          h("b", { class: "mono rw-c-" + cls }, a.code), h("span", { class: "rw-ellipsis" }, a.name || a.file.split("/").pop()),
          a.duration ? h("span", { class: "mono rw-dim" }, a.duration.toFixed(1) + "s") : null)));
      })),
    h("div", {
      class: "rw-bin-drop", help: "timeline.bin.upload",
      onDragover: e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); e.currentTarget.classList.add("over"); } },
      onDragleave: e => e.currentTarget.classList.remove("over"),
      onDrop: e => { e.preventDefault(); e.currentTarget.classList.remove("over"); uploadFiles(ctx, [...e.dataTransfer.files]); },
    }, icon("upload", 12), "Drop files to upload"));
}

// ---- Inspector ----

function renderInspector(ctx) {
  const p = ctx.p;
  const marker = p.markers.find(m => m.id === ctx.eph.selectedMarker);
  if (marker) {
    return h("div", { class: "rw-insp rw-panel" },
      h("div", { class: "rw-panel-head" }, icon("marker", 14), h("b", null, "Marker"), h("span", { class: "mono rw-dim" }, fmtTime(marker.t)),
        h("span", { class: "rw-flex" }),
        button({ icon: "close", help: "common.close", variant: "ghost", small: true, onClick: () => ctx.store.setEph({ selectedMarker: null }) })),
      h("div", { class: "rw-form" },
        h("label", { class: "rw-field" }, h("span", { class: "rw-field-label", help: "timeline.marker.text" }, "Text"),
          h("input", { class: "rw-input", key: "marker-text", value: marker.text, help: "timeline.marker.text",
            onChange: e => ctx.actions.edit(q => { q.markers.find(m => m.id === marker.id).text = e.target.value; }) })),
        h("div", { class: "rw-field" }, h("span", { class: "rw-field-label", help: "timeline.marker.color" }, "Colour"),
          segmented({ options: ["amber", "coral", "blue", "green", "pink"], value: marker.color, help: "timeline.marker.color", small: true,
            onChange: v => ctx.actions.edit(q => { q.markers.find(m => m.id === marker.id).color = v; }) })),
        h("div", { class: "rw-row" },
          button({ label: "Jump to marker", icon: "marker", help: "timeline.marker.jump", onClick: () => setPlayhead(ctx, marker.t) }),
          button({ label: "Delete marker", icon: "trash", help: "timeline.marker.delete", variant: "danger-ghost", onClick: () => {
            ctx.actions.edit(q => { q.markers = q.markers.filter(m => m.id !== marker.id); });
            ctx.store.setEph({ selectedMarker: null });
          } }))));
  }
  const s = ctx.scene;
  const idx = sceneIndex(p, s.id) + 1;
  const status = ctx.statusOf(s.id);
  const plan = ctx.planFor(s.id);
  const est = estimatePasses(s.duration, p.global.long);
  const passes = plan?.passes?.length || est.count;
  const prompt = plan?.prompts?.[0];
  const prev = p.scenes[idx - 2];
  return h("div", { class: "rw-insp rw-panel" },
    h("div", { class: "rw-insp-head" },
      h("span", { class: "rw-idx mono", help: "timeline.inspector.index" }, String(idx).padStart(2, "0")),
      h("input", { class: "rw-title-input", key: "insp-title-" + s.id, value: s.title, help: "scene.title", "aria-label": "Scene title",
        onChange: e => ctx.actions.editScene(s.id, sc => { sc.title = e.target.value; }) }),
      h("span", { class: ["rw-status", "st-" + status], help: "status." + status }, h("span", { class: "rw-led" }), STATUS_LABEL[status] || status),
      h("span", { class: "rw-flex" }),
      button({ label: "Open in Scene tab", icon: "chevRight", help: "timeline.inspector.open", variant: "link", small: true, onClick: () => ctx.actions.setTab("scene") })),
    h("div", { class: "rw-kv-grid" },
      h("div", { class: "rw-kv", help: "timeline.inspector.duration" }, h("span", null, "Duration"),
        h("b", { class: "mono" }, s.duration.toFixed(2) + " s ", h("small", null, framesOf(s.duration) + " f"))),
      h("div", { class: "rw-kv", help: "timeline.inspector.passes" }, h("span", null, "Generation"),
        h("b", null, passes > 1 ? `${passes} passes` : est.short ? `1 pass · trimmed from ${(MIN_PASS_FRAMES / FPS).toFixed(2)} s` : "1 pass")),
      h("div", { class: "rw-kv", help: "timeline.inspector.overrides" }, h("span", null, "Overrides"),
        h("b", null, overrideCount(s) ? h("span", { class: "rw-c-accent" }, "● " + overrideCount(s)) : h("span", { class: "rw-dim" }, "none")))),
    h("div", { class: "rw-field", help: "scene.start" }, h("span", { class: "rw-field-label" }, "Starts from"),
      segmented({
        small: true, value: s.start.mode, help: "scene.start",
        options: [
          { value: "fresh", label: "Fresh", icon: "cut", help: "scene.start.fresh" },
          { value: "last_frame", label: "Last frame", icon: "link", help: "scene.start.last_frame" },
          { value: "tail", label: "Tail clip", icon: "tail", help: "scene.start.tail" },
        ],
        onChange: v => {
          if (v !== "fresh" && !prev) { ctx.actions.toast("The first scene has nothing to continue from.", "warn"); return; }
          ctx.actions.editScene(s.id, sc => { sc.start.mode = v; });
        },
      })),
    h("div", { class: "rw-chips" }, refChips(ctx, s)),
    h("pre", { class: "rw-prompt-preview mono", help: "timeline.inspector.prompt", html: prompt ? highlightHTML(prompt) : "" },
      prompt ? null : h("span", { class: "rw-dim" }, ctx.eph.backend === "online" ? "The prompt preview appears once the scene has a prompt." : "Prompt preview needs the Reelwright backend (start ComfyUI with the node installed).")),
    h("div", { class: "rw-row" },
      button({ label: "Render scene", icon: "play", help: "timeline.inspector.render", onClick: () => ctx.actions.run("selected", [s.id]) }),
      button({ label: "New take", icon: "refresh", help: "timeline.inspector.take", onClick: () => ctx.actions.run("take", [s.id]) }),
      h("span", { class: "rw-flex" }),
      toggle({ value: s.lock, label: "Lock take", help: "scene.lock", onChange: v => ctx.actions.editScene(s.id, sc => { sc.lock = v; }) })));
}

function refChips(ctx, s) {
  const p = ctx.p;
  const out = [];
  for (const sc of s.cast) {
    const c = findCast(p, sc.id);
    if (c) out.push(chip({ label: c.name + " · anchors", kind: "pic", help: "timeline.chip.cast" }));
  }
  for (const r of s.refs) {
    const a = findAsset(p, r.asset);
    if (!a) continue;
    const kind = a.kind === "image" ? "pic" : a.kind === "video" ? "vid" : "aud";
    const what = r.role === "keyframe" ? `keyframe @ ${fmtTime(r.time)}` : r.role === "reference" ? (r.retention || a.defaults.retention) : r.role;
    out.push(chip({ code: a.code, label: (a.name || "").slice(0, 18) + " · " + what, kind, help: "timeline.chip.ref" }));
  }
  if (s.start.mode === "tail") out.push(chip({ code: "TAIL", label: `${s.start.overlap_frames} f of previous`, kind: "vid", help: "scene.start.tail" }));
  if (!out.length) out.push(h("span", { class: "rw-dim", help: "timeline.chip.none" }, "No references yet: drag assets from the bin onto the scene."));
  return out;
}

// ---- Transport ----

function renderTransport(ctx) {
  const p = ctx.p;
  const { total } = sceneStarts(p);
  const timecode = h("span", { class: "mono rw-tc", help: "timeline.timecode" }, fmtTime(p.ui.playhead));
  ctx.tl = ctx.tl || {};
  ctx.tl.timecode = timecode;
  const loop = ctx.eph.loop;
  return h("div", { class: "rw-transport rw-panel" },
    button({ icon: "prev", help: "timeline.transport.prev", variant: "ghost", onClick: () => {
      const { starts } = sceneStarts(p);
      const s = sceneAt(ctx, p.ui.playhead);
      const i = sceneIndex(p, s.id);
      const t = p.ui.playhead - starts[s.id] > 0.25 || i === 0 ? starts[s.id] : starts[p.scenes[i - 1].id];
      setPlayhead(ctx, t);
    } }),
    button({ icon: ctx.eph.playing ? "pause" : "play", help: "timeline.transport.play", variant: "solid", onClick: () => togglePlay(ctx) }),
    button({ icon: "next", help: "timeline.transport.next", variant: "ghost", onClick: () => {
      const { starts } = sceneStarts(p);
      const i = sceneIndex(p, sceneAt(ctx, p.ui.playhead).id);
      const n = p.scenes[i + 1];
      setPlayhead(ctx, n ? starts[n.id] : total);
    } }),
    button({ icon: "refresh", help: "timeline.transport.loop", variant: loop ? "accent-ghost" : "ghost", onClick: () => {
      ctx.store.setEph({ loop: loop ? null : (() => { const s = sceneAt(ctx, p.ui.playhead); const st = sceneStarts(p).starts[s.id]; return { in: st, out: st + s.duration }; })() });
    } }),
    timecode, h("span", { class: "mono rw-dim" }, "/ " + fmtTime(total)),
    loop && h("span", { class: "mono rw-loop-label", help: "timeline.transport.loop" }, `loop ${fmtTime(loop.in, false)}–${fmtTime(loop.out, false)}`),
    h("span", { class: "rw-flex" }),
    h("span", { class: "rw-dim", help: "timeline.transport.cut" }, "cut " + fmtTime(assembledDuration(p))));
}

// ---- Timeline lanes ----

function pickStep(z) {
  for (const s of [1, 2, 5, 10, 15, 30, 60, 120]) if (s * z >= 70) return s;
  return 300;
}

function laneHead(label, ic, cls, help, extra) {
  return h("div", { class: "rw-lane-head", help }, icon(ic, 13), h("span", { class: "rw-lane-name rw-c-" + cls }, label), h("span", { class: "rw-flex" }), extra);
}

function bar({ left, width, row = 0, cls, label, code, help, title, hatch, onClick, rows = 1 }) {
  const top = rows === 1 ? 7 : 4 + row * 20;
  return h("div", {
    class: ["rw-bar", cls, hatch && "hatch"], help, title,
    style: { left: left + "px", width: Math.max(6, width) + "px", top: top + "px", height: (rows === 1 ? 20 : 17) + "px" },
    onClick,
  }, code && h("b", { class: "mono" }, code), label);
}

function diamond(left, cls, help, hollow, row = 0, rows = 1) {
  const top = rows === 1 ? 12 : 8 + row * 20;
  return h("span", { class: ["rw-diamond", cls, hollow && "hollow"], help, style: { left: left - 5 + "px", top: top + "px" } });
}

function placeRows(items, rowsMax) {
  const ends = new Array(rowsMax).fill(-Infinity);
  for (const it of items) {
    let r = ends.findIndex(e => e <= it.left - 2);
    if (r < 0) r = rowsMax - 1;
    it.row = r;
    ends[r] = it.left + it.width;
  }
  return items;
}

function renderLanes(ctx) {
  const p = ctx.p;
  const z = zoomOf(ctx);
  const { starts, total } = sceneStarts(p);
  const width = Math.max(total * z + 160, 600);
  const step = pickStep(z);
  const selectScene = id => () => ctx.actions.select(id);

  // Ruler
  const ruler = h("div", {
    class: "rw-ruler-lane", style: { width: width + "px", "background-size": `${z}px 6px` }, help: "timeline.ruler",
    onPointerdown: e => {
      const rect = e.currentTarget.getBoundingClientRect();
      const go = ev => setPlayhead(ctx, (ev.clientX - rect.left) / z);
      go(e);
      const move = ev => go(ev);
      const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
  });
  for (let t = 0; t <= total + step; t += step) {
    ruler.append(h("span", { class: "rw-tick", style: { left: t * z + "px" } }), h("span", { class: "rw-tick-label mono", style: { left: t * z + 4 + "px" } }, fmtTime(t, false)));
  }
  const loop = ctx.eph.loop;
  if (loop) ruler.append(h("span", { class: "rw-loop-range", style: { left: loop.in * z + "px", width: (loop.out - loop.in) * z + "px" }, help: "timeline.transport.loop" }));
  for (const m of p.markers) {
    ruler.append(h("span", {
      class: ["rw-marker", "mk-" + m.color, ctx.eph.selectedMarker === m.id && "on"], style: { left: m.t * z + "px" }, help: "timeline.marker",
      title: m.text, onPointerdown: e => { e.stopPropagation(); ctx.store.setEph({ selectedMarker: m.id }); },
    }, icon("marker", 11), h("span", null, m.text)));
  }

  // Scenes
  const scenesLane = h("div", { class: "rw-lane-body scenes", style: { width: width + "px" } });
  p.scenes.forEach((s, i) => scenesLane.append(sceneBlock(ctx, s, i, starts[s.id], z)));
  p.scenes.forEach((s, i) => {
    if (i === 0) return;
    const mode = s.start.mode;
    const ic = mode === "fresh" ? "cut" : mode === "tail" ? "tail" : "link";
    scenesLane.append(h("button", {
      type: "button", class: ["rw-join", "j-" + mode], style: { left: starts[s.id] * z - 11 + "px" }, help: "timeline.join." + mode,
      "aria-label": "Change how this scene starts",
      onClick: e => {
        e.stopPropagation();
        const next = { fresh: "last_frame", last_frame: "tail", tail: "fresh" }[mode];
        ctx.actions.editScene(s.id, sc => { sc.start.mode = next; });
      },
    }, icon(ic, 12)));
  });
  scenesLane.append(h("button", {
    type: "button", class: "rw-add-ghost", style: { left: total * z + 8 + "px" }, help: "timeline.addScene",
    onClick: () => ctx.actions.addScene(p.scenes[p.scenes.length - 1].id),
  }, icon("plus", 14), "Scene"));

  // Pictures
  const pics = h("div", { class: "rw-lane-body", style: { width: width + "px" } });
  const vids = h("div", { class: "rw-lane-body", style: { width: width + "px" } });
  const auds = h("div", { class: "rw-lane-body", style: { width: width + "px" } });
  const dlg = h("div", { class: "rw-lane-body", style: { width: width + "px" } });
  const cam = h("div", { class: "rw-lane-body", style: { width: width + "px" } });
  const lora = h("div", { class: "rw-lane-body", style: { width: width + "px" } });

  const allLines = p.scenes.flatMap(s => s.dialogue.map(d => ({ s, d, x: (starts[s.id] + d.t) * z }))).sort((a, b) => a.x - b.x);
  allLines.forEach((it, k) => {
    const c = findCast(p, it.d.speaker);
    const next = allLines[k + 1]?.x ?? Infinity;
    dlg.append(h("span", {
      class: "rw-dlg", style: { left: it.x + "px", "max-width": Math.max(28, next - it.x - 4) + "px" }, help: "timeline.lane.dialogue", onClick: selectScene(it.s.id),
    /* [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are per clip now
    }, h("b", { class: "mono" }, (it.d.language || "").slice(0, 2).toUpperCase()), ` ${c?.name || "?"} (${c?.speaker || "S?"}) “${it.d.text}”`));
    [/OLD] */
    }, h("b", { class: "mono" }, (it.d.language || "").slice(0, 2).toUpperCase()), ` ${c?.name || "?"} “${it.d.text}”`));
  });

  for (const s of p.scenes) {
    const x0 = starts[s.id] * z;
    const w = s.duration * z;
    const picItems = [], audItems = [];
    const anchored = s.cast.map(sc => findCast(p, sc.id)).filter(c => c?.anchors.length);
    if (anchored.length) picItems.push({ left: x0 + 3, width: w - 6, cls: "pic soft", label: anchored.map(c => c.name).join(" · ") + " · anchors", help: "timeline.lane.castAnchors", onClick: selectScene(s.id) });
    for (const sc of s.cast) {
      const c = findCast(p, sc.id);
      const voice = findAsset(p, c?.voice);
      if (voice && s.dialogue.some(d => d.speaker === c.id)) audItems.push({ left: x0 + 3, width: Math.min(w - 6, (voice.duration || 3) * z), cls: "aud soft", code: voice.code, label: `${c.name} voice`, help: "timeline.lane.voice", onClick: selectScene(s.id) });
    }
    for (const r of s.refs) {
      const a = findAsset(p, r.asset);
      if (!a) continue;
      const ret = r.retention || a.defaults.retention;
      if (a.kind === "image") {
        if (r.role === "reference") picItems.push({ left: x0 + 3, width: w - 6, cls: "pic", code: a.code, label: `${a.name || ""} · ${ret}`, help: "timeline.lane.picRef", onClick: selectScene(s.id) });
        else {
          const t = r.role === "first_frame" ? 0 : r.role === "last_frame" ? s.duration : Math.min(r.time, s.duration);
          pics.append(diamond(x0 + t * z, "pic", "timeline.lane.keyframe." + r.role));
          const left = Math.min(x0 + t * z + 8, x0 + w - 40);
          picItems.push({ left, width: Math.max(34, Math.min(110, x0 + w - 3 - left)), cls: "pic", code: a.code, label: r.role === "keyframe" ? "@ " + fmtTime(r.time) : r.role.replace("_", " "), help: "timeline.lane.keyframe." + r.role, onClick: selectScene(s.id) });
        }
      } else if (a.kind === "video") {
        vids.append(bar({ left: x0 + 3, width: Math.min(w - 6, (a.duration || 2) * z), cls: "vid", code: a.code, label: `${a.name || ""} · ${a.category || r.role}`, help: "timeline.lane.vidRef", onClick: selectScene(s.id) }));
        if (r.soundtrack) audItems.push({ left: x0 + 3, width: Math.min(w - 6, (a.duration || 2) * z), cls: "aud soft", code: a.code, label: "soundtrack", help: "timeline.lane.soundtrack", onClick: selectScene(s.id) });
      } else {
        audItems.push({ left: x0 + 3, width: Math.min(w - 6, (a.duration || 2) * z), cls: "aud", code: a.code, label: `${a.name || ""} · ${ret}`, help: "timeline.lane.audRef", onClick: selectScene(s.id) });
      }
    }
    if (s.start.mode === "last_frame") pics.append(diamond(x0, "pic", "timeline.lane.lastFrameAuto", true));
    if (s.start.mode === "tail") vids.append(bar({ left: x0, width: (s.start.overlap_frames / FPS) * z, cls: "vid", label: "tail", hatch: true, help: "scene.start.tail" }));
    placeRows(picItems, 2).forEach(it => pics.append(bar({ ...it, rows: 2 })));
    placeRows(audItems, 2).forEach(it => auds.append(bar({ ...it, rows: 2 })));
    s.shots.forEach((sh, k) => {
      if (!sh.camera) return;
      const end = s.shots[k + 1]?.t ?? s.duration;
      cam.append(h("span", { class: "rw-cam", style: { left: x0 + sh.t * z + 3 + "px", "max-width": Math.max(24, (end - sh.t) * z - 6) + "px" }, help: "timeline.lane.camera", onClick: selectScene(s.id) }, sh.camera));
    });
    const own = effectiveLoras(p, s).filter(l => l.source !== "global");
    if (own.length) {
      const src = own.some(l => l.source === "override") ? "override" : own.some(l => l.source === "scene") ? "scene" : "cast";
      lora.append(h("div", {
        class: ["rw-bar lora", src === "override" ? "over" : src === "cast" && "cast"], help: "timeline.lane.lora." + src, onClick: selectScene(s.id),
        style: { left: x0 + 2 + "px", width: Math.max(6, w - 4) + "px", top: "20px", height: "17px" },
      }, own.map(l => `${l.name.replace(/\.safetensors$/, "")} ${Number(l.strength).toFixed(2)}${l.source === "override" ? "*" : ""}`).join(" · ")));
    }
  }
  const globals = p.global.loras.filter(l => l.enabled);
  if (globals.length) {
    lora.append(h("div", { class: "rw-bar lora global", help: "timeline.lane.lora.global", style: { left: "0px", width: total * z + "px", top: "4px", height: "12px" } },
      globals.map(l => `${l.name.replace(/\.safetensors$/, "")} ${Number(l.strength).toFixed(2)}`).join(" · ") + " · global"));
  }

  const lanes = [
    ["Scenes", "film", "text", "timeline.lane.scenes", scenesLane, "scenes", h("span", { class: "mono rw-dim" }, `${p.scenes.length} / ∞`)],
    ["Pictures", "image", "pic", "timeline.lane.pictures", pics, "two"],
    ["Video refs", "video", "vid", "timeline.lane.video", vids, ""],
    ["Audio refs", "audio", "aud", "timeline.lane.audio", auds, "two"],
    ["Dialogue", "dialogue", "dlg", "timeline.lane.dialogueLane", dlg, ""],
    ["Camera", "camera", "cam", "timeline.lane.cameraLane", cam, ""],
    ["LoRAs", "lora", "lora", "timeline.lane.loras", lora, "two"],
  ];

  const playhead = h("div", { class: "rw-playhead", style: { left: HEAD_W + p.ui.playhead * z + "px" } });
  const playheadLabel = h("span", { class: "rw-playhead-label mono" }, fmtTime(p.ui.playhead));
  playhead.append(playheadLabel);
  ctx.tl = ctx.tl || {};
  ctx.tl.playhead = playhead;
  ctx.tl.playheadLabel = playheadLabel;

  /* [OLD 2026-11-02 v0.2.1->v0.2.2] wheel events are now routed by editor.js, so a DOM listener here never fires
  return h("div", { class: "rw-lanes", dataset: { scroll: "lanes" }, onWheel: e => {
    if (e.ctrlKey || e.altKey) { e.preventDefault(); setZoom(ctx, zoomOf(ctx) * (e.deltaY < 0 ? 1.15 : 1 / 1.15)); }
  } },
  [/OLD] */
  /* [OLD 2026-11-02 v0.2.2->v0.3.0] Ctrl + wheel now zooms ComfyUI's canvas (editor.js), so only Alt zooms the timeline
  return h("div", { class: "rw-lanes", dataset: { scroll: "lanes" }, wheel: e => {
    if (e.ctrlKey || e.altKey) { e.preventDefault(); setZoom(ctx, zoomOf(ctx) * (e.deltaY < 0 ? 1.15 : 1 / 1.15)); }
  } },
  [/OLD] */
  return h("div", { class: "rw-lanes", dataset: { scroll: "lanes" }, wheel: e => {
    if (e.altKey) { e.preventDefault(); setZoom(ctx, zoomOf(ctx) * (e.deltaY < 0 ? 1.15 : 1 / 1.15)); }
  } },
  h("div", { class: "rw-lanes-inner", style: { width: HEAD_W + width + "px" } },
    h("div", { class: "rw-lane ruler" }, h("div", { class: "rw-lane-head mono rw-dim", help: "timeline.ruler" }, "24 fps"), ruler),
    lanes.map(([label, ic, cls, help, el, kind, extra]) => h("div", { class: ["rw-lane", kind] }, laneHead(label, ic, cls, help, extra), el)),
    playhead));
}

// added 2026-11-02 v0.3.0: right-click menu for an asset (timeline bin and Assets tab)
export function assetMenu(ctx, a) {
  const s = ctx.scene;
  return [
    { label: "Open in Assets tab", icon: "assets", help: "timeline.bin.item", onClick: () => { ctx.store.setEph({ selectedAsset: a.id }); ctx.actions.setTab("assets"); } },
    { label: `Add to ${s.title}`, icon: "plus", help: "assets.addToScene", onClick: () => {
      ctx.actions.editScene(s.id, sc => { sc.refs.push({ id: newId("r"), asset: a.id, role: a.defaults.role, time: 0, retention: "", keep: [], soundtrack: !!a.defaults.soundtrack }); });
      ctx.actions.toast(`Added ${a.code} to ${s.title}.`, "ok");
    } },
    { sep: true },
    { label: "Delete asset", icon: "trash", help: "assets.delete", danger: true, onClick: () => ctx.actions.deleteAsset(a.id) },
  ];
}

// added 2026-11-02 v0.3.0: offered once on a freshly added node when saved profiles exist
export function profileBanner(ctx) {
  const pr = ctx.eph.profiles;
  if (!ctx.eph.fresh || !pr?.profiles?.length) return null;
  const sel = ctx.eph.profileSel && pr.profiles.some(x => x.id === ctx.eph.profileSel) ? ctx.eph.profileSel : pr.profiles[0].id;
  return h("div", { class: "rw-profile-banner", help: "global.profiles.banner" },
    icon("global", 14), h("b", null, "New project"), h("span", { class: "rw-dim" }, "Start from a saved Global profile:"),
    select({ options: pr.profiles.map(x => ({ value: x.id, label: x.name + (x.id === pr.default ? " · default" : "") })), value: sel, width: "240px",
      help: "global.profiles.pick", onChange: v => ctx.store.setEph({ profileSel: v }) }),
    button({ label: "Apply", small: true, variant: "primary", help: "global.profiles.apply", onClick: () => ctx.actions.applyProfile(pr.profiles.find(x => x.id === sel)) }),
    h("span", { class: "rw-flex" }),
    button({ icon: "close", small: true, variant: "ghost", help: "common.close", onClick: () => ctx.store.setEph({ fresh: false }) }));
}

// added 2026-11-02 v0.2.2: right-click menu for a scene (timeline block and the Scene tab strip)
export function sceneMenu(ctx, s) {
  const p = ctx.p;
  const i = sceneIndex(p, s.id);
  const local = p.ui.playhead - sceneStarts(p).starts[s.id];
  return [
    { label: "Open in Scene tab", icon: "scene", help: "timeline.inspector.open", onClick: () => ctx.actions.select(s.id, "scene") },
    { label: "Render this scene", icon: "play", help: "timeline.inspector.render", onClick: () => ctx.actions.run("selected", [s.id]) },
    { label: "New take", icon: "refresh", help: "render.scope.take", onClick: () => ctx.actions.run("take", [s.id]) },
    { sep: true },
    { label: "Split at playhead", icon: "cut", hint: "S", help: "timeline.split", disabled: !(local > 0 && local < s.duration), onClick: () => ctx.actions.splitScene(s.id, local) },
    { label: "Duplicate", icon: "copy", hint: "D", help: "timeline.duplicate", onClick: () => ctx.actions.duplicateScene(s.id) },
    { label: "Move left", icon: "chevLeft", help: "timeline.moveLeft", disabled: i === 0, onClick: () => ctx.actions.moveScene(s.id, -1) },
    { label: "Move right", icon: "chevRight", help: "timeline.moveRight", disabled: i === p.scenes.length - 1, onClick: () => ctx.actions.moveScene(s.id, 1) },
    { label: s.lock ? "Unlock take" : "Lock take", icon: s.lock ? "unlock" : "lock", help: "scene.lock", onClick: () => ctx.actions.editScene(s.id, sc => { sc.lock = !sc.lock; }) },
    // added 2026-11-02 v0.3.0: draft or final per scene
    { sep: true },
    ...[["", `Quality: follow Global (${p.global.quality})`], ["draft", "Quality: draft"], ["final", "Quality: final"]].map(([v, label]) => ({
      label, icon: (s.overrides.quality || "") === v ? "check" : null, help: "scene.override.quality",
      onClick: () => ctx.actions.editScene(s.id, sc => { if (v) sc.overrides.quality = v; else delete sc.overrides.quality; }),
    })),
    { sep: true },
    /* [OLD 2026-11-02 v0.2.2->v0.3.0] no confirmation, and the only scene could not be deleted
    { label: "Delete scene", icon: "trash", hint: "Del", help: "timeline.delete", danger: true, disabled: p.scenes.length <= 1,
      onClick: () => { ctx.actions.deleteScene(s.id); ctx.actions.toast(`Deleted ${s.title}. Ctrl+Z brings it back.`, "info"); } },
    [/OLD] */
    { label: p.scenes.length <= 1 ? "Reset scene" : "Delete scene", icon: "trash", hint: "Del", help: "timeline.delete", danger: true,
      onClick: async () => { if (await ctx.actions.deleteScene(s.id)) ctx.actions.toast(p.scenes.length <= 1 ? "Scene reset." : `Deleted ${s.title}.`, "info"); } },
  ];
}

function sceneBlock(ctx, s, i, start, z) {
  const p = ctx.p;
  const status = ctx.statusOf(s.id);
  const prog = ctx.eph.progress[s.id];
  const plan = ctx.planFor(s.id);
  const est = estimatePasses(s.duration, p.global.long);
  const take = ctx.starredTake(s.id);
  const thumb = take?.files?.first ? viewURL(take.files.first) : storyboardImage(ctx, s);
  const selected = s.id === ctx.scene.id;
  const w = s.duration * z - 2;
  const block = h("div", {
    class: ["rw-scene", selected && "on", "st-" + status, s.lock && "locked"],
    style: { left: start * z + 1 + "px", width: w + "px", "--tint": s.color || null },
    help: "timeline.scene",
    onClick: () => ctx.actions.select(s.id),
    onDblclick: () => ctx.actions.select(s.id, "scene"),
    menu: () => { ctx.actions.select(s.id); return sceneMenu(ctx, s); }, // added 2026-11-02 v0.2.2
    onDragover: e => { if (e.dataTransfer.types.includes("application/x-rw-asset")) { e.preventDefault(); e.currentTarget.classList.add("drop"); } },
    onDragleave: e => e.currentTarget.classList.remove("drop"),
    onDrop: e => {
      e.preventDefault();
      e.currentTarget.classList.remove("drop");
      const id = e.dataTransfer.getData("application/x-rw-asset");
      const a = findAsset(p, id);
      if (!a) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const t = Math.max(0, Math.min(s.duration, (e.clientX - rect.left) / z));
      ctx.actions.editScene(s.id, sc => {
        sc.refs.push({ id: newId("r"), asset: id, role: a.defaults.role, time: Math.round(t * FPS) / FPS, retention: "", keep: [], soundtrack: !!a.defaults.soundtrack });
      });
      ctx.actions.toast(`Added ${a.code} to ${s.title}.`, "ok");
    },
  });
  const head = h("div", { class: "rw-scene-head" },
    h("span", { class: "mono rw-scene-idx" }, String(i + 1).padStart(2, "0")),
    h("span", { class: "rw-scene-title" }, s.title),
    s.lock && icon("lock", 11),
    // added 2026-11-02 v0.3.0: show draft scenes
    effective(p, s, "quality").value === "draft" && h("span", { class: "rw-qtag", help: "scene.override.quality" }, "draft"),
    est.count > 1 && h("span", { class: "rw-badge vid", help: "timeline.scene.passes" }, `${plan?.passes?.length || est.count} passes`),
    est.short && h("span", { class: "rw-badge", help: "timeline.scene.short" }, "trim"),
    dot(status === "cached" || status === "locked" ? "ok" : status === "stale" ? "warn" : status === "rendering" ? "busy" : "empty", "status." + status));
  const strip = h("div", { class: "rw-scene-strip", style: thumb ? { "background-image": `url("${thumb}")` } : null });
  block.append(head, strip);
  if (s.start.mode === "tail" && i > 0) strip.append(h("span", { class: "rw-hatch", style: { width: (s.start.overlap_frames / FPS) * z + "px" }, help: "scene.start.tail" }, "tail"));
  const passes = plan?.passes;
  if (passes?.length > 1) {
    for (const ps of passes.slice(1)) {
      strip.append(h("span", { class: ["rw-pass-tick", ps.seam_before === "cut" ? "cut" : "overlap"], style: { left: ps.start * z + "px" }, help: "timeline.scene.seam." + (ps.seam_before === "cut" ? "cut" : "overlap") }));
      if (ps.seam_before !== "cut" && ps.overlap_frames) strip.append(h("span", { class: "rw-hatch thin", style: { left: ps.start * z + "px", width: (ps.overlap_frames / FPS) * z + "px" } }));
    }
  } else if (est.count > 1) {
    const span = s.duration / est.count;
    for (let k = 1; k < est.count; k++) strip.append(h("span", { class: "rw-pass-tick overlap", style: { left: k * span * z + "px" }, help: "timeline.scene.seam.overlap" }));
  }
  for (const sh of s.shots) {
    if (sh.t <= 0) continue;
    strip.append(shotTick(ctx, s, sh, z));
  }
  block.append(h("span", { class: "rw-scene-dur mono" }, `${s.duration.toFixed(2)}s · ${framesOf(s.duration)}f`));
  if (prog && !["done", "cached", "error"].includes(prog.phase)) {
    const passPart = prog.passes ? (prog.pass - 1 + (prog.steps ? prog.step / prog.steps : 0)) / prog.passes : 0;
    block.append(h("div", { class: "rw-scene-prog", help: "timeline.scene.progress" }, h("span", { style: { width: Math.round(passPart * 100) + "%" } })),
      h("span", { class: "rw-scene-prog-label mono" }, `${prog.phase} ${prog.pass}/${prog.passes}${prog.steps ? " · " + prog.step + "/" + prog.steps : ""}`));
  }
  block.append(resizeHandle(ctx, s, z, block));
  return block;
}

function shotTick(ctx, s, sh, z) {
  const tick = h("span", { class: "rw-shot-tick", style: { left: sh.t * z + "px" }, help: "timeline.scene.shot", title: sh.camera || sh.text });
  tick.addEventListener("pointerdown", e => {
    e.stopPropagation();
    e.preventDefault();
    const x0 = e.clientX, t0 = sh.t;
    let t = t0;
    tick.setPointerCapture(e.pointerId);
    const move = ev => {
      t = Math.max(1 / FPS, Math.min(s.duration - 1 / FPS, t0 + (ev.clientX - x0) / z));
      t = Math.round(t * FPS) / FPS;
      tick.style.left = t * z + "px";
      tick.dataset.label = fmtTime(t);
    };
    const up = () => {
      tick.removeEventListener("pointermove", move);
      tick.removeEventListener("pointerup", up);
      if (t !== t0) ctx.actions.editScene(s.id, sc => { const x = sc.shots.find(q => q.id === sh.id); x.t = t; sc.shots.sort((a, b) => a.t - b.t); });
    };
    tick.addEventListener("pointermove", move);
    tick.addEventListener("pointerup", up);
  });
  return tick;
}

function resizeHandle(ctx, s, z, block) {
  const handle = h("span", { class: "rw-resize", help: "timeline.scene.resize" });
  handle.addEventListener("pointerdown", e => {
    e.stopPropagation();
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    const x0 = e.clientX, d0 = s.duration;
    const p = ctx.p;
    const i = sceneIndex(p, s.id);
    const next = p.scenes[i + 1];
    const nextD0 = next?.duration;
    const tip = h("div", { class: "rw-drag-tip mono" });
    block.append(tip);
    let d = d0;
    const move = ev => {
      let frames = framesOf(Math.max(1 / FPS, d0 + (ev.clientX - x0) / z));
      if (p.ui.snap) frames = Math.max(5, nearestGridFrames(frames));
      if (!p.ui.ripple && next) frames = Math.min(frames, framesOf(d0 + nextD0) - 1);
      d = frames / FPS;
      block.style.width = d * z - 2 + "px";
      const est = estimatePasses(d, p.global.long);
      tip.textContent = `${d.toFixed(2)} s · ${frames} f · ${est.count > 1 ? est.count + " passes" : est.short ? "trimmed" : "1 pass"}${p.ui.snap ? " · grid" : ""}`;
    };
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      tip.remove();
      if (d === d0) return;
      ctx.actions.edit(q => {
        const sc = q.scenes.find(x => x.id === s.id);
        sc.duration = d;
        if (!q.ui.ripple && next) q.scenes.find(x => x.id === next.id).duration = Math.max(1 / FPS, Math.round((d0 + nextD0 - d) * FPS) / FPS);
      });
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
  });
  return handle;
}

function renderToolbar(ctx) {
  const p = ctx.p;
  const z = zoomOf(ctx);
  const s = ctx.scene;
  return h("div", { class: "rw-tl-toolbar" },
    h("b", null, "Timeline"),
    h("button", { type: "button", class: "rw-q", dataset: { more: "tab.timeline" }, help: "tab.timeline", "aria-label": "Help" }, "?"),
    button({ label: "Add scene", icon: "plus", small: true, help: "timeline.addScene", onClick: () => ctx.actions.addScene(s.id) }),
    button({ label: "Split", icon: "cut", small: true, help: "timeline.split", onClick: () => ctx.actions.splitScene(s.id, p.ui.playhead - sceneStarts(p).starts[s.id]) }),
    button({ label: "Duplicate", icon: "copy", small: true, help: "timeline.duplicate", onClick: () => ctx.actions.duplicateScene(s.id) }),
    button({ icon: "chevLeft", small: true, help: "timeline.moveLeft", variant: "ghost", onClick: () => ctx.actions.moveScene(s.id, -1) }),
    button({ icon: "chevRight", small: true, help: "timeline.moveRight", variant: "ghost", onClick: () => ctx.actions.moveScene(s.id, 1) }),
    button({ icon: "trash", small: true, help: "timeline.delete", variant: "danger-ghost", onClick: () => ctx.actions.deleteScene(s.id) }),
    h("span", { class: "rw-sep" }),
    toggle({ value: p.ui.snap, label: "Snap to 17k+5", help: "timeline.snap", onChange: v => ctx.store.update(q => { q.ui.snap = v; }, { history: false, plan: false }) }),
    toggle({ value: p.ui.ripple, label: p.ui.ripple ? "Ripple" : "Roll", help: "timeline.ripple", onChange: v => ctx.store.update(q => { q.ui.ripple = v; }, { history: false, plan: false }) }),
    button({ label: "Marker", icon: "marker", small: true, help: "timeline.addMarker", onClick: () => addMarker(ctx) }),
    h("span", { class: "rw-flex" }),
    button({ icon: "zoomOut", small: true, variant: "ghost", help: "timeline.zoom", onClick: () => setZoom(ctx, z / 1.25) }),
    slider({ value: Math.round(z), min: 4, max: 160, step: 1, help: "timeline.zoom", format: v => v + " px/s", onChange: v => setZoom(ctx, v) }),
    button({ icon: "zoomIn", small: true, variant: "ghost", help: "timeline.zoom", onClick: () => setZoom(ctx, z * 1.25) }),
    button({ label: "Fit", small: true, help: "timeline.fit", onClick: () => {
      const w = ctx.root.querySelector(".rw-lanes")?.clientWidth || 1200;
      setZoom(ctx, (w - HEAD_W - 120) / Math.max(1, sceneStarts(p).total));
    } }));
}

export function render(ctx) {
  const p = ctx.p;
  const { starts } = sceneStarts(p);
  const s = sceneAt(ctx, p.ui.playhead);
  const m = monitorOf(ctx);
  m.show(s, p.ui.playhead - starts[s.id]);
  return h("div", { class: "rw-tl" },
    profileBanner(ctx), // added 2026-11-02 v0.3.0
    h("div", { class: "rw-tl-top" },
      renderBin(ctx),
      h("div", { class: "rw-mon-col" }, m.el, renderTransport(ctx)),
      renderInspector(ctx)),
    h("div", { class: "rw-tl-main rw-panel" }, renderToolbar(ctx), renderLanes(ctx)));
}
