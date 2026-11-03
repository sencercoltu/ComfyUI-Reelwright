// Soundtrack on the timeline (added 2026-11-03 v0.5.0).
// Audio files laid on the finished cut: a song a music video is cut to, a score, a sound bed. Each track has its own
// lane with its waveform: drag the clip to move it, drag its edges to trim it, click it to edit the rest in the
// inspector. Tracks marked "Send to H3" give every pass the part of the song it covers (soundtrack.py); tracks
// marked "In the cut" play unchanged in the merge and in the monitor.

import { h, icon, button, toggle, segmented, select, number, contextMenu } from "../ui.js";
import { rw, viewURL } from "../api.js";
import {
  FPS, fmtTime, findAsset, newId, normalizeTrack, trackLength, playingTracks, sceneStarts, overlapSeconds,
  AUDIO_RETENTION, sceneHasSong,
} from "../model.js";

const WAVE_H = 30;
const TILE = 4096; // canvas tiles: browsers refuse very wide canvases

export function dbGain(db) {
  return Math.pow(10, (Number(db) || 0) / 20);
}

function lengthOf(p, t) {
  return trackLength(t, findAsset(p, t.asset));
}

// ---- waveforms -------------------------------------------------------------------------------------------------------

const waves = new Map(); // input file -> { state, peaks, perSecond, duration }

function waveOf(ctx, file) {
  let w = waves.get(file);
  if (!w) {
    w = { state: "loading" };
    waves.set(file, w);
    rw.waveform(file)
      // the loudest moment fills the lane, so a quiet file still shows its shape
      .then(r => {
        let top = 16;
        for (const v of r.peaks) if (v > top) top = v;
        Object.assign(w, r, { state: "ok", top });
        ctx.render();
      })
      .catch(() => { w.state = "error"; });
  }
  return w;
}

// Canvases (one per 4096 px) drawing `seconds` of the file from `srcIn` at z px/s.
function waveTiles(ctx, a, srcIn, seconds, z) {
  const w = waveOf(ctx, a.file);
  const width = Math.max(1, Math.round(seconds * z));
  if (w.state !== "ok") return [];
  const out = [];
  const mid = WAVE_H / 2;
  for (let x0 = 0; x0 < width; x0 += TILE) {
    const tw = Math.min(TILE, width - x0);
    const c = h("canvas", { class: "rw-wave", width: tw, height: WAVE_H, style: { left: x0 + "px", width: tw + "px" } });
    const g = c.getContext("2d");
    if (!g) break;
    g.fillStyle = "rgba(110, 231, 183, 0.8)";
    for (let x = 0; x < tw; x++) {
      const t0 = srcIn + (x0 + x) / z, t1 = srcIn + (x0 + x + 1) / z;
      const i0 = Math.floor(t0 * w.perSecond), i1 = Math.max(i0 + 1, Math.ceil(t1 * w.perSecond));
      let m = 0;
      for (let i = i0; i < i1 && i < w.peaks.length; i++) if (w.peaks[i] > m) m = w.peaks[i];
      const hh = Math.max(0.5, Math.min(1, m / w.top) * (mid - 1));
      g.fillRect(x, mid - hh, 1, hh * 2);
    }
    out.push(c);
  }
  return out;
}

// ---- editing --------------------------------------------------------------------------------------------------------

function editTrack(ctx, id, fn) {
  ctx.actions.edit(q => { const t = q.soundtrack.find(x => x.id === id); if (t) fn(t, q); });
}

export function addTrack(ctx, assetId, start = 0) {
  const a = findAsset(ctx.p, assetId);
  if (!a || a.kind !== "audio") { ctx.actions.toast("Only audio files can go on the soundtrack.", "warn"); return; }
  const id = newId("t");
  ctx.actions.edit(q => { q.soundtrack.push(normalizeTrack({ id, asset: assetId, start: Math.round(start * FPS) / FPS })); });
  ctx.store.setEph({ selectedTrack: id, selectedMarker: null });
  ctx.actions.toast(`${a.code} is on the soundtrack at ${fmtTime(start)}.`, "ok");
}

function addMenu(ctx, e, start) {
  const audio = ctx.p.assets.filter(a => a.kind === "audio");
  const items = audio.length
    ? audio.map(a => ({ label: `${a.code} · ${a.name || a.file.split("/").pop()}${a.duration ? " · " + fmtTime(a.duration, false) : ""}`, icon: "audio",
      help: "timeline.track.add", onClick: () => addTrack(ctx, a.id, start) }))
    : [{ label: "Upload an audio file to the Asset bin first", icon: "upload", help: "timeline.track.add", disabled: true }];
  contextMenu(ctx.root, e.clientX, e.clientY, items);
}

// Edges a dragged clip edge sticks to: film start, playhead, scene cuts, markers (within 8 screen pixels).
function snapPoints(ctx) {
  const p = ctx.p;
  const { starts, total } = sceneStarts(p);
  const pts = [0, total, p.ui.playhead, ...p.markers.map(m => m.t)];
  p.scenes.forEach((s, i) => pts.push(starts[s.id] + (i > 0 ? overlapSeconds(s) : 0)));
  return pts;
}

function snap(ctx, t, z, sc, free) {
  if (free) return Math.round(t * FPS) / FPS;
  const lim = 8 / z;
  let best = null;
  for (const x of snapPoints(ctx)) if (Math.abs(x - t) <= lim && (best === null || Math.abs(x - t) < Math.abs(best - t))) best = x;
  return Math.round((best ?? t) * FPS) / FPS;
}

// Drag a clip (mode "move") or one of its edges ("in", "out").
function clipDrag(ctx, e, t, mode, clip, tip, helpers) {
  if (e.button !== 0) return;
  e.stopPropagation();
  e.preventDefault();
  const p = ctx.p;
  const a = findAsset(p, t.asset);
  const z = helpers.zoom(), sc = helpers.scaleOf();
  const x0 = e.clientX;
  const start0 = t.start, in0 = t.in, len0 = trackLength(t, a);
  const fileLen = Number(a?.duration) || 0;
  let next = null;
  ctx.store.setEph({ selectedTrack: t.id, selectedMarker: null }, false);
  clip.classList.add("drag");
  helpers.trackDrag(ev => {
    const d = (ev.clientX - x0) / sc / z;
    if (mode === "move") {
      const s = snap(ctx, start0 + d, z, sc, ev.altKey);
      next = { start: s };
      clip.style.left = s * z + "px";
      tip.textContent = `starts ${fmtTime(s)}`;
    } else if (mode === "in") {
      // the left edge: the audio stays where it is in the film, the clip starts later or earlier in the file
      let s = snap(ctx, start0 + d, z, sc, ev.altKey);
      let inn = in0 + (s - start0);
      if (inn < 0) { s -= inn; inn = 0; }
      if (inn > in0 + len0 - 0.1) { inn = in0 + len0 - 0.1; s = start0 + (inn - in0); }
      next = { start: s, in: Math.round(inn * 1000) / 1000 };
      clip.style.left = s * z + "px";
      clip.style.width = Math.max(4, (len0 - (inn - in0)) * z) + "px";
      tip.textContent = `from ${fmtTime(inn)} of ${a?.code || "the file"} · at ${fmtTime(s)}`;
    } else {
      let end = snap(ctx, start0 + len0 + d, z, sc, ev.altKey) - start0;
      end = Math.max(0.1, fileLen ? Math.min(fileLen - in0, end) : end);
      next = { out: Math.round((in0 + end) * 1000) / 1000 };
      clip.style.width = Math.max(4, end * z) + "px";
      tip.textContent = `to ${fmtTime(in0 + end)} of ${a?.code || "the file"} · ${end.toFixed(2)} s`;
    }
    tip.style.display = "";
  }, () => {
    clip.classList.remove("drag");
    tip.style.display = "none";
    if (!next) { ctx.render(); return; } // a click: show it in the inspector
    editTrack(ctx, t.id, x => Object.assign(x, next));
  });
}

// ---- lanes ----------------------------------------------------------------------------------------------------------

// One lane per track, then an empty lane to add tracks (drop an audio asset on it). Returns renderLanes entries:
// [label, icon, colour class, help, body, lane class, head extra, head click].
export function trackLanes(ctx, z, width, helpers) {
  const p = ctx.p;
  const { total } = sceneStarts(p);
  const lanes = [];
  p.soundtrack.forEach((t, k) => {
    const a = findAsset(p, t.asset);
    const len = trackLength(t, a);
    const on = ctx.eph.selectedTrack === t.id;
    const body = h("div", { class: "rw-lane-body track", style: { width: width + "px" } });
    const tip = h("div", { class: "rw-drag-tip mono", style: { display: "none" } });
    const flags = [t.sync && "H3", t.mix && "cut", t.loop && "loop", t.duck && "duck"].filter(Boolean).join(" · ");
    const clip = h("div", {
      class: ["rw-track-clip", on && "on", (t.mute || !a) && "muted", !t.mix && !t.sync && "muted"],
      style: { left: t.start * z + "px", width: Math.max(4, len * z) + "px" },
      help: "timeline.track.clip",
      menu: () => trackMenu(ctx, t),
      onPointerdown: e => clipDrag(ctx, e, t, "move", clip, tip, helpers),
    },
    a ? waveTiles(ctx, a, t.in, len, z) : null,
    h("span", { class: "rw-track-label" }, h("b", { class: "mono" }, a?.code || "?"), " ", a ? (a.name || a.file.split("/").pop()) : "missing asset",
      flags && h("span", { class: "rw-track-flags mono" }, flags)),
    t.fade_in > 0 && h("span", { class: "rw-track-fade in", style: { width: t.fade_in * z + "px" } }),
    t.fade_out > 0 && h("span", { class: "rw-track-fade out", style: { width: t.fade_out * z + "px" } }),
    h("span", { class: "rw-track-trim l", help: "timeline.track.trimIn", onPointerdown: e => clipDrag(ctx, e, t, "in", clip, tip, helpers) }),
    h("span", { class: "rw-track-trim r", help: "timeline.track.trimOut", onPointerdown: e => clipDrag(ctx, e, t, "out", clip, tip, helpers) }),
    tip);
    body.append(clip);
    if (t.loop && len > 0.1) { // the repeats, up to the end of the film
      for (let s = t.start + len, n = 0; s < total && n < 200; s += len, n++) {
        body.append(h("div", { class: ["rw-track-clip", "ghost", t.mute && "muted"], style: { left: s * z + "px", width: Math.max(4, Math.min(len, total - s + len) * z) + "px" },
          help: "timeline.track.loop", onClick: () => ctx.store.setEph({ selectedTrack: t.id, selectedMarker: null }) },
        a ? waveTiles(ctx, a, t.in, Math.min(len, Math.max(0.1, total - s)), z) : null));
      }
    }
    const mute = h("button", {
      type: "button", class: ["rw-track-mute", t.mute && "on"], help: "timeline.track.mute", "aria-label": t.mute ? "Unmute track" : "Mute track",
      onClick: e => { e.stopPropagation(); editTrack(ctx, t.id, x => { x.mute = !x.mute; }); },
    }, icon(t.mute ? "mute" : "speaker", 12));
    lanes.push({
      label: (a?.code || "Track") + (p.soundtrack.length > 1 ? ` · ${k + 1}` : ""), ic: "music", cls: "aud", help: "timeline.lane.track",
      body, kind: ["track", on && "on"], extra: mute, onHead: () => ctx.store.setEph({ selectedTrack: t.id, selectedMarker: null }),
    });
  });
  const add = h("div", {
    class: "rw-lane-body track add", style: { width: width + "px" }, help: "timeline.lane.addTrack",
    onDragover: e => { if (e.dataTransfer.types.includes("application/x-rw-asset")) { e.preventDefault(); e.currentTarget.classList.add("drop"); } },
    onDragleave: e => e.currentTarget.classList.remove("drop"),
    onDrop: e => {
      e.preventDefault();
      e.currentTarget.classList.remove("drop");
      const rect = e.currentTarget.getBoundingClientRect();
      addTrack(ctx, e.dataTransfer.getData("application/x-rw-asset"), Math.max(0, (e.clientX - rect.left) / helpers.scaleOf() / z));
    },
  }, !p.soundtrack.length && h("span", { class: "rw-track-hint" }, "Drop a song or any audio file here to lay it on the film; it can drive the picture (lip sync, cuts) and plays unchanged in the cut."));
  lanes.push({
    label: "Soundtrack", ic: "music", cls: "aud", help: "timeline.lane.addTrack", body: add, kind: ["track", "add"],
    extra: h("button", { type: "button", class: "rw-track-add", help: "timeline.track.add", "aria-label": "Add a soundtrack track",
      onClick: e => { e.stopPropagation(); addMenu(ctx, e, 0); } }, icon("plus", 12)),
  });
  return lanes;
}

function trackMenu(ctx, t) {
  const p = ctx.p;
  return [
    { label: "Start at playhead", icon: "pointer", help: "timeline.track.toPlayhead", onClick: () => editTrack(ctx, t.id, x => { x.start = Math.round(p.ui.playhead * FPS) / FPS; }) },
    { label: "Trim start to playhead", icon: "cut", help: "timeline.track.trimHere", onClick: () => trimAt(ctx, t, "in") },
    { label: "Trim end to playhead", icon: "cut", help: "timeline.track.trimHere", onClick: () => trimAt(ctx, t, "out") },
    { sep: true },
    { label: t.mute ? "Unmute" : "Mute", icon: t.mute ? "speaker" : "mute", help: "timeline.track.mute", onClick: () => editTrack(ctx, t.id, x => { x.mute = !x.mute; }) },
    { label: "Delete track", icon: "trash", danger: true, help: "timeline.track.delete", onClick: () => deleteTrack(ctx, t) },
  ];
}

function trimAt(ctx, t, edge) {
  const p = ctx.p;
  const len = lengthOf(p, t);
  const local = p.ui.playhead - t.start;
  if (local <= 0.05 || local >= len - 0.05) { ctx.actions.toast("Put the playhead over the track first.", "warn"); return; }
  editTrack(ctx, t.id, x => {
    if (edge === "in") { x.in = Math.round((x.in + local) * 1000) / 1000; x.start = Math.round(p.ui.playhead * FPS) / FPS; }
    else x.out = Math.round((x.in + local) * 1000) / 1000;
  });
}

function deleteTrack(ctx, t) {
  ctx.actions.edit(q => { q.soundtrack = q.soundtrack.filter(x => x.id !== t.id); });
  ctx.store.setEph({ selectedTrack: null });
  ctx.actions.toast("Track removed. Ctrl+Z brings it back.", "info");
}

// ---- inspector ------------------------------------------------------------------------------------------------------

export function trackInspector(ctx, t, helpers) {
  const p = ctx.p;
  const a = findAsset(p, t.asset);
  const len = trackLength(t, a);
  const set = fn => editTrack(ctx, t.id, fn);
  const audio = p.assets.filter(x => x.kind === "audio").map(x => ({ value: x.id, label: `${x.code} · ${x.name || x.file.split("/").pop()}` }));
  const scenes = t.sync ? p.scenes.filter(s => sceneHasSong(p, s)).length : 0;
  const end = t.loop ? sceneStarts(p).total : t.start + len;
  const num = (label, key, opts, helpId) => h("label", { class: "rw-field" }, h("span", { class: "rw-field-label", help: helpId }, label),
    number({ value: t[key], help: helpId, key: "trk-" + key + "-" + t.id, step: 0.01, width: "92px", ...opts, onChange: v => set(x => { x[key] = v ?? 0; }) }));
  return h("div", { class: "rw-insp rw-panel rw-track-insp" },
    h("div", { class: "rw-panel-head" }, icon("music", 14), h("b", null, "Soundtrack"), h("span", { class: "mono rw-c-aud" }, a?.code || "?"),
      h("span", { class: "mono rw-dim" }, `${fmtTime(Math.max(0, t.start))} – ${fmtTime(end)}`),
      h("span", { class: "rw-flex" }),
      button({ icon: "close", help: "common.close", variant: "ghost", small: true, onClick: () => ctx.store.setEph({ selectedTrack: null }) })),
    h("div", { class: "rw-form" },
      h("div", { class: "rw-field" }, h("span", { class: "rw-field-label", help: "timeline.track.asset" }, "Audio"),
        select({ options: audio, value: t.asset, help: "timeline.track.asset", width: "100%", onChange: v => set(x => { x.asset = v; x.in = 0; x.out = 0; }) })),
      h("div", { class: "rw-track-grid" },
        num("Starts at", "start", { unit: "s" }, "timeline.track.start"),
        num("From (in)", "in", { min: 0, unit: "s" }, "timeline.track.in"),
        num("To (out)", "out", { min: 0, unit: "s" }, "timeline.track.out"),
        num("Level", "volume_db", { min: -60, max: 12, step: 0.5, unit: "dB" }, "timeline.track.volume"),
        num("Fade in", "fade_in", { min: 0, max: 30, step: 0.1, unit: "s" }, "timeline.track.fades"),
        num("Fade out", "fade_out", { min: 0, max: 30, step: 0.1, unit: "s" }, "timeline.track.fades")),
      h("div", { class: "rw-dim small", help: "timeline.track.length" },
        a ? `${len.toFixed(2)} s of ${a.code}${a.duration ? ` (${fmtTime(a.duration, false)} long)` : ""}${t.loop ? ", looping" : ""}` : "The audio asset was deleted."),
      h("div", { class: "rw-toggle-grid" },
        toggle({ value: t.mix, label: "In the cut", help: "timeline.track.mix", onChange: v => set(x => { x.mix = v; }) }),
        toggle({ value: t.sync, label: "Send to H3", help: "timeline.track.sync", onChange: v => set(x => { x.sync = v; }) }),
        toggle({ value: t.duck, label: "Duck under scene sound", help: "timeline.track.duck", onChange: v => set(x => { x.duck = v; }) }),
        toggle({ value: t.loop, label: "Loop to the end", help: "timeline.track.loopToggle", onChange: v => set(x => { x.loop = v; }) }),
        toggle({ value: t.mute, label: "Mute", help: "timeline.track.mute", onChange: v => set(x => { x.mute = v; }) })),
      t.sync && h("div", { class: "rw-field" }, h("span", { class: "rw-field-label", help: "timeline.track.marker" }, "H3 marker"),
        segmented({ small: true, value: t.marker, help: "timeline.track.marker", options: AUDIO_RETENTION.map(v => ({ value: v, label: v.replace("_", " ") })),
          onChange: v => set(x => { x.marker = v; }) })),
      t.sync && h("div", { class: "rw-dim small", help: "timeline.track.sync" },
        scenes ? `Sent to ${scenes} scene${scenes > 1 ? "s" : ""}: every pass gets the part it covers (up to 15 s). Moving or trimming the track re-renders those passes.`
          : "No scene plays while this track sounds."),
      h("div", { class: "rw-row wrap" },
        button({ label: "Start at playhead", icon: "pointer", small: true, help: "timeline.track.toPlayhead", onClick: () => set(x => { x.start = Math.round(p.ui.playhead * FPS) / FPS; }) }),
        button({ label: "Trim start here", icon: "cut", small: true, help: "timeline.track.trimHere", onClick: () => trimAt(ctx, t, "in") }),
        button({ label: "Trim end here", icon: "cut", small: true, help: "timeline.track.trimHere", onClick: () => trimAt(ctx, t, "out") }),
        button({ label: "Play from start", icon: "play", small: true, help: "timeline.track.audition", onClick: () => helpers.playFrom(Math.max(0, t.start)) }),
        h("span", { class: "rw-flex" }),
        button({ icon: "trash", small: true, variant: "danger-ghost", help: "timeline.track.delete", onClick: () => deleteTrack(ctx, t) }))));
}

// ---- playback -------------------------------------------------------------------------------------------------------
// The monitor plays the tracks marked "In the cut" with <audio> elements kept in step with the playhead. Browsers cap
// an element's volume at 1, so levels above 0 dB play at 0 dB here (the merge applies them).

const players = new Map(); // track id -> { el, seekAt }

export function syncAudio(ctx, time, playing) {
  const p = ctx.p;
  const live = new Set();
  if (playing) {
    const total = sceneStarts(p).total;
    for (const { t, a } of playingTracks(p)) {
      if (!t.mix) continue;
      const len = trackLength(t, a);
      let local = time - t.start;
      if (local < 0 || (!t.loop && local >= len)) continue;
      const played = local;
      if (t.loop) local %= len;
      const src = viewURL(a.file, "input");
      if (!src) continue;
      live.add(t.id);
      let pl = players.get(t.id);
      if (!pl) { pl = { el: new Audio(), seekAt: 0 }; pl.el.preload = "auto"; players.set(t.id, pl); }
      if (pl.src !== src) { pl.el.src = src; pl.src = src; }
      const end = t.loop ? total - t.start : len;
      let gain = dbGain(t.volume_db);
      if (t.fade_in > 0) gain *= Math.min(1, played / t.fade_in);
      if (t.fade_out > 0) gain *= Math.min(1, Math.max(0, end - played) / t.fade_out);
      pl.el.volume = Math.max(0, Math.min(1, gain));
      const want = t.in + local;
      const now = performance.now();
      if (Math.abs(pl.el.currentTime - want) > 0.2 && now - pl.seekAt > 500) {
        pl.seekAt = now;
        try { pl.el.currentTime = want; } catch { /* not loaded yet */ }
      }
      if (pl.el.paused) pl.el.play().catch(() => {});
    }
  }
  for (const [id, pl] of players) if (!live.has(id) && !pl.el.paused) pl.el.pause();
}

// For the test harness: the tracks the monitor is playing right now.
export function audioState() {
  return [...players.entries()].map(([id, pl]) => ({ id, playing: !pl.el.paused, volume: pl.el.volume, src: pl.src }));
}

export function stopAudio() {
  for (const pl of players.values()) pl.el.pause();
}

// The take's own sound while tracks play: the Merge card's scene level, or silent when scene sound is off.
export function sceneVolume(p) {
  if (!playingTracks(p).some(({ t }) => t.mix)) return 1;
  const sa = p.global.merge.scene_audio || { mix: false, volume_db: -12 };
  return sa.mix ? Math.min(1, dbGain(sa.volume_db)) : 0;
}
