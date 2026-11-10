// Soundtrack on the timeline.
// Audio files laid on the finished cut: a song a music video is cut to, a score, a sound bed. Each track has its own
// lane with its waveform: drag the clip to move it, drag its edges to trim it, click it to edit the rest in the
// inspector. Tracks marked "Send to H3" give every pass the part of the song it covers (soundtrack.py); tracks
// marked "In the cut" play unchanged in the merge and in the monitor.

import { h, icon, button, toggle, segmented, select, number, contextMenu } from "../ui.js";
import { rw, viewURL } from "../api.js";
import {
  FPS, fmtTime, findAsset, newId, normalizeTrack, trackLength, playingTracks, sceneStarts, AUDIO_RETENTION,
  sceneHasSong, planScene, passSoundtrack, assetGroupName,
} from "../model.js";

const WAVE_H = 30;
const TILE = 1024; // canvas tiles (browsers refuse very wide canvases), small so only what is seen is painted

export function dbGain(db) {
  return Math.pow(10, (Number(db) || 0) / 20);
}

function lengthOf(p, t) {
  return trackLength(t, findAsset(p, t.asset));
}

// ---- waveforms -------------------------------------------------------------------------------------------------------

// per-file data (waveform peaks, beat grid) fetched once and shared by every editor (it is the
// file's data, not a player). Every editor that waits for a file is redrawn when it arrives. A failed fetch is tried
// again after RETRY_MS, or at once with the Retry button on the clip.
const RETRY_MS = 20000;
const waveData = new Map(); // input file -> { state: "loading"|"ok"|"error", peaks, perSecond, top, at, waiters }
const beatData = new Map(); // input file -> { state, bpm, beats: [s], downbeats: [s], at, waiters }
let beatGen = 0; // bumped when a beat grid arrives (beatTimes() is kept per project version and this)

function fetchOnce(cache, file, load, ctx) {
  let w = cache.get(file);
  if (w && w.state === "error" && Date.now() - w.at > RETRY_MS) { cache.delete(file); w = null; }
  if (!w) {
    const entry = w = { state: "loading", waiters: new Set() };
    cache.set(file, entry);
    const done = () => {
      const list = [...entry.waiters];
      entry.waiters.clear();
      for (const c of list) c.store?.notify?.();
    };
    load(file)
      .then(r => { Object.assign(entry, r, { state: "ok" }); done(); })
      .catch(err => { entry.state = "error"; entry.at = Date.now(); entry.error = String(err?.message || err); done(); });
  }
  if (w.state === "loading" && ctx) w.waiters.add(ctx);
  return w;
}

function waveOf(ctx, file) {
  return fetchOnce(waveData, file, f => rw.waveform(f).then(r => {
    // the loudest moment fills the lane, so a quiet file still shows its shape
    let top = 16;
    for (const v of r.peaks) if (v > top) top = v;
    return { ...r, top };
  }), ctx);
}

// The beat grid of an input audio file (S: /reelwright/beats), fetched on first use.
export function beatsOf(ctx, file) {
  return fetchOnce(beatData, file, f => rw.beats(f).then(r => {
    beatGen++;
    const list = x => (Array.isArray(x) ? x.map(Number).filter(Number.isFinite).sort((a, b) => a - b) : []);
    return { bpm: Number(r?.bpm) || 0, beats: list(r?.beats), downbeats: list(r?.downbeats) };
  }), ctx);
}

// Forget a failed waveform or beat fetch, so the next render asks again.
function retryFile(file) {
  if (waveData.get(file)?.state === "error") waveData.delete(file);
  if (beatData.get(file)?.state === "error") beatData.delete(file);
}

// The beat ticks are shown (the toolbar's Beats toggle; on unless turned off) and whether edges snap to beats.
export function showBeats(p) {
  return p.ui.beats !== false;
}
export function beatSnapOn(p) {
  return !!p.ui.beatSnap;
}

function lowerBound(arr, x) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < x) lo = mid + 1; else hi = mid; }
  return lo;
}

// Film times of the beats of every playing track, loop repeats included, sorted: {times: Float64Array, down:
// Uint8Array (1 = the first beat of a bar)}. Tracks whose grid is still loading are left out until it arrives.
const beatMemo = new WeakMap(); // project -> { key, value }
export function beatTimes(ctx) {
  const p = ctx.p;
  const key = `${p.__rwv}|${beatGen}`;
  const m = beatMemo.get(p);
  if (m && m.key === key && typeof p.__rwv === "number") return m.value;
  const { total } = sceneStarts(p);
  const all = [];
  for (const { t, a } of playingTracks(p)) {
    const b = beatsOf(ctx, a.file);
    if (b.state !== "ok") continue;
    const len = trackLength(t, a);
    const downs = new Set(b.downbeats.map(x => Math.round(x * 1000)));
    const inside = b.beats.filter(x => x >= t.in - 1e-6 && x < t.in + len);
    const reps = t.loop && len > 0.1 ? Math.min(5000, Math.max(1, Math.ceil((total - t.start) / len))) : 1;
    for (let r = 0; r < reps; r++) {
      for (const x of inside) {
        const ft = t.start + r * len + (x - t.in);
        if (ft >= 0 && (!t.loop || ft <= total + 1e-6)) all.push([ft, downs.has(Math.round(x * 1000)) ? 1 : 0]);
      }
    }
  }
  all.sort((x, y) => x[0] - y[0]);
  const value = { times: Float64Array.from(all, x => x[0]), down: Uint8Array.from(all, x => x[1]) };
  if (typeof p.__rwv === "number") beatMemo.set(p, { key, value });
  return value;
}

// The beat (film time) nearest to t within lim seconds, or null.
export function nearestBeat(ctx, t, lim) {
  const { times } = beatTimes(ctx);
  const i = lowerBound(times, t);
  let best = null;
  for (const j of [i - 1, i]) {
    if (j < 0 || j >= times.length) continue;
    if (Math.abs(times[j] - t) <= lim && (best === null || Math.abs(times[j] - t) < Math.abs(best - t))) best = times[j];
  }
  return best;
}

// Canvas tiles drawing `seconds` of the file from `srcIn` at z px/s, with the beat ticks when they are shown. Only
// tiles near the view are built (helpers.window, in lane pixels; the clip starts at originX); they are painted when
// they scroll into view (helpers.lazy, set up by the timeline) and kept across renders while nothing they show
// changes. `period` (seconds): a loop pattern, every `period` seconds repeats the same part of the file.
function waveTiles(ctx, a, t, srcIn, seconds, z, helpers = {}, { originX = 0, period = 0, kind = "clip" } = {}) {
  const w = waveOf(ctx, a.file);
  if (w.state === "error") {
    return [h("button", {
      type: "button", class: "rw-wave-retry", help: "timeline.track.waveRetry", title: w.error || "",
      onPointerdown: e => e.stopPropagation(),
      onClick: e => { e.stopPropagation(); retryFile(a.file); ctx.store.notify(); },
    }, icon("refresh", 10), "Retry waveform")];
  }
  if (w.state !== "ok") return [];
  const width = Math.max(1, Math.round(seconds * z));
  const bt = showBeats(ctx.p) ? beatsOf(ctx, a.file) : null;
  const beats = bt?.state === "ok" ? bt : null;
  const win = helpers.window || { from: -Infinity, to: Infinity };
  const cache = ctx.__waveTiles || (ctx.__waveTiles = new Map());
  if (cache.size > 600) cache.clear();
  const out = [];
  for (let x0 = 0; x0 < width; x0 += TILE) {
    const tw = Math.min(TILE, width - x0);
    if (originX + x0 + tw < win.from || originX + x0 > win.to) continue;
    const key = [kind, t.id, a.file, srcIn, z, x0, tw, period, beats ? "b" : "-"].join("|");
    let c = cache.get(key);
    if (!c) {
      c = h("canvas", { class: "rw-wave", width: tw, height: WAVE_H, style: { left: x0 + "px", width: tw + "px" } });
      c.__paint = () => paintTile(c, w, srcIn, z, x0, tw, period, beats);
      cache.set(key, c);
    }
    if (!c.__painted) { if (helpers.lazy) helpers.lazy(c); else c.__paint(); }
    out.push(c);
  }
  return out;
}

function paintTile(c, w, srcIn, z, x0, tw, period, beats) {
  if (c.__painted) return;
  c.__painted = true;
  const g = c.getContext("2d");
  if (!g) return;
  const mid = WAVE_H / 2, per = w.perSecond, peaks = w.peaks, n = peaks.length;
  g.clearRect(0, 0, tw, WAVE_H);
  g.fillStyle = "rgba(110, 231, 183, 0.8)";
  for (let x = 0; x < tw; x++) {
    let off = (x0 + x) / z;
    if (period > 0) off %= period;
    const t0 = srcIn + off, t1 = t0 + 1 / z;
    const i0 = Math.floor(t0 * per), i1 = Math.max(i0 + 1, Math.ceil(t1 * per));
    let m = 0;
    for (let i = i0; i < i1 && i < n; i++) if (peaks[i] > m) m = peaks[i];
    const hh = Math.max(0.5, Math.min(1, m / w.top) * (mid - 1));
    g.fillRect(x, mid - hh, 1, hh * 2);
  }
  if (!beats) return;
  // beat ticks: the first beat of a bar full height, the others short ticks at the top and bottom
  const downs = new Set(beats.downbeats.map(b => Math.round(b * 1000)));
  for (const b of beats.beats) {
    const off = b - srcIn;
    if (off < 0 || (period > 0 && off >= period)) continue;
    let r = period > 0 ? Math.max(0, Math.floor((x0 / z - off) / period)) : 0;
    for (;; r++) {
      const x = Math.round((off + r * period) * z - x0);
      if (x >= tw) break;
      if (x >= 0) {
        const down = downs.has(Math.round(b * 1000));
        g.fillStyle = down ? "rgba(251, 191, 36, 0.9)" : "rgba(236, 238, 242, 0.5)";
        if (down) g.fillRect(x, 0, 1, WAVE_H);
        else { g.fillRect(x, 0, 1, 6); g.fillRect(x, WAVE_H - 6, 1, 6); }
      }
      if (!(period > 0)) break;
    }
  }
}

// ---- editing --------------------------------------------------------------------------------------------------------

// label: the step's name in the History menu
function editTrack(ctx, id, fn, label = "Edit track") {
  ctx.actions.edit(q => { const t = q.soundtrack.find(x => x.id === id); if (t) fn(t, q); }, { label });
}

export function addTrack(ctx, assetId, start = 0) {
  const a = findAsset(ctx.p, assetId);
  if (!a || a.kind !== "audio") { ctx.actions.toast("Only audio files can go on the soundtrack.", "warn"); return; }
  const id = newId("t");
  ctx.actions.edit(q => { q.soundtrack.push(normalizeTrack({ id, asset: assetId, start: Math.round(start * FPS) / FPS })); }, { label: `Add ${a.code} to the soundtrack` });
  ctx.store.setEph({ selectedTrack: id, selectedMarker: null });
  ctx.actions.toast(`${a.code} is on the soundtrack at ${fmtTime(start)}.`, "ok");
}

function addMenu(ctx, e, start) {
  const audio = ctx.p.assets.filter(a => a.kind === "audio");
  const items = audio.length
    ? audio.map(a => ({ label: `${assetGroupName(ctx.p, a) ? assetGroupName(ctx.p, a) + " · " : ""}${a.code} · ${a.name || a.file.split("/").pop()}${a.duration ? " · " + fmtTime(a.duration, false) : ""}`, icon: "audio",
      help: "timeline.track.add", onClick: () => addTrack(ctx, a.id, start) }))
    : [{ label: "Upload an audio file in the Assets tab first", icon: "upload", help: "timeline.track.add", disabled: true }];
  contextMenu(ctx.root, e.clientX, e.clientY, items);
}

// Edges a dragged clip edge sticks to: film start and end, playhead, markers, and every cut (where a scene first shows
// new content: sceneStarts().visible), within 8 screen pixels.
function snapPoints(ctx) {
  const p = ctx.p;
  const { total, visible } = sceneStarts(p);
  const pts = [0, total, p.ui.playhead, ...p.markers.map(m => m.t)];
  p.scenes.forEach((s, i) => { if (i > 0) pts.push(visible[s.id]); });
  return pts;
}

// With Snap to beats on: `offsets` (sorted seconds after the clip start) are the clip's own beats, so a moved track
// also sticks when one of its beats meets a cut, the playhead or a marker; `extra` (sorted film times) are more points
// to stick to (the file's beats, for a trimmed edge).
function snap(ctx, t, z, sc, free, { offsets = null, extra = null } = {}) {
  if (free) return Math.round(t * FPS) / FPS;
  const lim = 8 / z;
  let best = null;
  const take = x => { if (Math.abs(x - t) <= lim && (best === null || Math.abs(x - t) < Math.abs(best - t))) best = x; };
  const pts = snapPoints(ctx);
  for (const x of pts) take(x);
  if (offsets?.length) {
    for (const x of pts) {
      const j = lowerBound(offsets, x - t);
      if (j > 0) take(x - offsets[j - 1]);
      if (j < offsets.length) take(x - offsets[j]);
    }
  }
  if (extra?.length) {
    const j = lowerBound(extra, t);
    if (j > 0) take(extra[j - 1]);
    if (j < extra.length) take(extra[j]);
  }
  return Math.round((best ?? t) * FPS) / FPS;
}

// "what goes stale" while a synced track is dragged. Before the drop, the scenes and passes
// whose part of the song would change (so they render again) are outlined on the Scenes lane, and the drag tip counts
// them. Worked out in the browser with the backend's rules (model.passSoundtrack) from the passes' song parts before
// and after the move.
let staleSeq = 0;
function stalePreview(ctx, t, tip, z) {
  const p = ctx.p;
  const { starts, visible } = sceneStarts(p);
  const sig = song => (song ? JSON.stringify([song.pieces, song.marker, song.codes]) : "");
  const passesOf = p.scenes.map((s, i) => planScene(p, s, i).passes);
  const before = p.scenes.map((s, i) => passesOf[i].map(ps => sig(passSoundtrack(p, starts[s.id], ps))));
  let pending = null, label = "", text = "", frame = 0, marked = [];
  const unmark = () => {
    for (const el of marked) {
      el.classList.remove("rw-stale-preview");
      for (const x of el.querySelectorAll(".rw-stale-pass")) x.remove();
    }
    marked = [];
  };
  const compute = () => {
    frame = 0;
    if (!pending) return;
    const q = { ...p, soundtrack: p.soundtrack.map(x => (x.id === t.id ? { ...x, ...pending } : x)) };
    Object.defineProperty(q, "__rwv", { value: -(++staleSeq), enumerable: false }); // its own memo (model.js)
    unmark();
    let scenes = 0, passes = 0;
    p.scenes.forEach((s, i) => {
      const changed = passesOf[i].filter((ps, k) => sig(passSoundtrack(q, starts[s.id], ps)) !== before[i][k]);
      if (!changed.length) return;
      scenes++;
      passes += changed.length;
      const block = ctx.root.querySelector(`.rw-scene[data-sid="${CSS.escape(s.id)}"]`);
      if (!block) return; // not built (far from the view)
      block.classList.add("rw-stale-preview");
      const ov = visible[s.id] - starts[s.id];
      for (const ps of changed) {
        const a = Math.max(ps.start, ov), b = Math.min(ps.end, s.duration);
        if (b > a) block.append(h("span", { class: "rw-stale-pass", help: "timeline.track.stale", style: { left: (a - ov) * z + "px", width: (b - a) * z + "px" } }));
      }
      marked.push(block);
    });
    text = scenes ? ` · ${scenes} scene${scenes === 1 ? "" : "s"} (${passes} pass${passes === 1 ? "" : "es"}) render again` : " · no scene renders again";
    tip.textContent = label + text;
  };
  return {
    update(next, lbl) {
      pending = next;
      label = lbl;
      if (!frame) frame = requestAnimationFrame(compute);
      return label + text;
    },
    clear() { cancelAnimationFrame(frame); frame = 0; unmark(); },
  };
}

// Drag a clip (mode "move") or one of its edges ("in", "out"). Snap to beats adds the file's
// beats; a synced track shows what would render again before the drop.
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
  const bt = beatSnapOn(p) && a?.file ? beatsOf(ctx, a.file) : null;
  const fileBeats = bt?.state === "ok" ? bt.beats : [];
  const offsets = mode === "move" ? Float64Array.from(fileBeats.filter(x => x >= in0 && x < in0 + len0), x => x - in0) : null;
  const extra = mode !== "move" ? Float64Array.from(fileBeats, x => start0 + x - in0) : null;
  const stale = t.sync && !t.mute && a?.file ? stalePreview(ctx, t, tip, z) : null;
  let next = null;
  ctx.store.setEph({ selectedTrack: t.id, selectedMarker: null }, false);
  clip.classList.add("drag");
  helpers.trackDrag(ev => {
    const d = (ev.clientX - x0) / sc / z;
    let label;
    if (mode === "move") {
      const s = snap(ctx, start0 + d, z, sc, ev.altKey, { offsets });
      next = { start: s };
      clip.style.left = s * z + "px";
      label = `starts ${fmtTime(s)}`;
    } else if (mode === "in") {
      // the left edge: the audio stays where it is in the film, the clip starts later or earlier in the file
      let s = snap(ctx, start0 + d, z, sc, ev.altKey, { extra });
      let inn = in0 + (s - start0);
      if (inn < 0) { s -= inn; inn = 0; }
      if (inn > in0 + len0 - 0.1) { inn = in0 + len0 - 0.1; s = start0 + (inn - in0); }
      next = { start: s, in: Math.round(inn * 1000) / 1000 };
      clip.style.left = s * z + "px";
      clip.style.width = Math.max(4, (len0 - (inn - in0)) * z) + "px";
      label = `from ${fmtTime(inn)} of ${a?.code || "the file"} · at ${fmtTime(s)}`;
    } else {
      let end = snap(ctx, start0 + len0 + d, z, sc, ev.altKey, { extra }) - start0;
      end = Math.max(0.1, fileLen ? Math.min(fileLen - in0, end) : end);
      next = { out: Math.round((in0 + end) * 1000) / 1000 };
      clip.style.width = Math.max(4, end * z) + "px";
      label = `to ${fmtTime(in0 + end)} of ${a?.code || "the file"} · ${end.toFixed(2)} s`;
    }
    tip.textContent = stale ? stale.update(next, label) : label;
    tip.style.display = "";
  }, () => {
    stale?.clear();
    clip.classList.remove("drag");
    tip.style.display = "none";
    if (!next) { ctx.render(); return; } // a click: show it in the inspector
    editTrack(ctx, t.id, x => Object.assign(x, next), mode === "move" ? "Move track" : "Trim track");
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
    const bt = a?.file && (showBeats(p) || beatSnapOn(p)) ? beatsOf(ctx, a.file) : null;
    const flags = [t.sync && "H3", t.mix && "cut", t.loop && "loop", t.duck && "duck", bt?.state === "ok" && bt.bpm > 0 && `${Math.round(bt.bpm)} BPM`].filter(Boolean).join(" · ");
    const clip = h("div", {
      class: ["rw-track-clip", on && "on", (t.mute || !a) && "muted", !t.mix && !t.sync && "muted"],
      style: { left: t.start * z + "px", width: Math.max(4, len * z) + "px" },
      help: "timeline.track.clip",
      dataset: { tid: t.id },
      menu: () => trackMenu(ctx, t),
      onPointerdown: e => clipDrag(ctx, e, t, "move", clip, tip, helpers),
    },
    a ? waveTiles(ctx, a, t, t.in, len, z, helpers, { originX: t.start * z }) : null,
    h("span", { class: "rw-track-label" }, h("b", { class: "mono" }, a?.code || "?"), " ", a ? (a.name || a.file.split("/").pop()) : "missing asset",
      flags && h("span", { class: "rw-track-flags mono" }, flags)),
    t.fade_in > 0 && h("span", { class: "rw-track-fade in", style: { width: t.fade_in * z + "px" } }),
    t.fade_out > 0 && h("span", { class: "rw-track-fade out", style: { width: t.fade_out * z + "px" } }),
    h("span", { class: "rw-track-trim l", help: "timeline.track.trimIn", onPointerdown: e => clipDrag(ctx, e, t, "in", clip, tip, helpers) }),
    h("span", { class: "rw-track-trim r", help: "timeline.track.trimOut", onPointerdown: e => clipDrag(ctx, e, t, "out", clip, tip, helpers) }),
    tip);
    body.append(clip);
    if (t.loop && len > 0.1 && t.start + len < total) {
      const from = t.start + len;
      body.append(h("div", {
        class: ["rw-track-clip", "ghost", "pattern", t.mute && "muted"],
        dataset: { tid: t.id, repeats: String(Math.ceil((total - from) / len - 1e-9)) },
        style: { left: from * z + "px", width: Math.max(1, (total - from) * z) + "px", "--rep": len * z + "px" },
        help: "timeline.track.loop", onClick: () => ctx.store.setEph({ selectedTrack: t.id, selectedMarker: null }),
      }, a ? waveTiles(ctx, a, t, t.in, total - from, z, helpers, { originX: from * z, period: len, kind: "loop" }) : null));
    }
    const mute = h("button", {
      type: "button", class: ["rw-track-mute", t.mute && "on"], help: "timeline.track.mute", "aria-label": t.mute ? "Unmute track" : "Mute track",
      onClick: e => { e.stopPropagation(); editTrack(ctx, t.id, x => { x.mute = !x.mute; }, t.mute ? "Unmute track" : "Mute track"); },
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

// Every edit has a name in the History menu; Delete (the key) removes the selected track
function trackMenu(ctx, t) {
  const p = ctx.p;
  return [
    { label: "Start at playhead", icon: "pointer", help: "timeline.track.toPlayhead", onClick: () => editTrack(ctx, t.id, x => { x.start = Math.round(p.ui.playhead * FPS) / FPS; }, "Move track") },
    { label: "Trim start to playhead", icon: "cut", help: "timeline.track.trimHere", onClick: () => trimAt(ctx, t, "in") },
    { label: "Trim end to playhead", icon: "cut", help: "timeline.track.trimHere", onClick: () => trimAt(ctx, t, "out") },
    { sep: true },
    { label: t.mute ? "Unmute" : "Mute", icon: t.mute ? "speaker" : "mute", help: "timeline.track.mute", onClick: () => editTrack(ctx, t.id, x => { x.mute = !x.mute; }, t.mute ? "Unmute track" : "Mute track") },
    { label: "Delete track", icon: "trash", hint: "Del", danger: true, help: "timeline.track.delete", onClick: () => deleteTrack(ctx, t) },
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
  }, "Trim track");
}

export function deleteTrack(ctx, t) {
  const a = findAsset(ctx.p, t.asset);
  ctx.actions.edit(q => { q.soundtrack = q.soundtrack.filter(x => x.id !== t.id); }, { label: `Delete track ${a?.code || ""}`.trim() });
  ctx.store.setEph({ selectedTrack: null });
  ctx.actions.toast("Track removed. Ctrl+Z brings it back.", "info");
}

// ---- inspector ------------------------------------------------------------------------------------------------------

export function trackInspector(ctx, t, helpers) {
  const p = ctx.p;
  const a = findAsset(p, t.asset);
  const len = trackLength(t, a);
  const set = (fn, label = "Edit track") => editTrack(ctx, t.id, fn, label);
  const audio = p.assets.filter(x => x.kind === "audio").map(x => ({ value: x.id, label: `${x.code} · ${x.name || x.file.split("/").pop()}`, pre: assetGroupName(p, x) }));
  const scenes = t.sync ? p.scenes.filter(s => sceneHasSong(p, s)).length : 0;
  const bt = a?.file ? beatsOf(ctx, a.file) : null;
  const beatLine = !bt ? null : h("div", { class: "rw-dim small rw-row", help: "timeline.track.beats" },
    bt.state === "ok" ? (bt.bpm > 0 ? `Tempo ${Math.round(bt.bpm)} BPM · ${bt.beats.length} beats, ${bt.downbeats.length} bars` : "No steady beat found in this file.")
      : bt.state === "error" ? ["Beats unavailable.", button({ label: "Retry", small: true, variant: "link", help: "timeline.track.waveRetry", onClick: () => { retryFile(a.file); ctx.store.notify(); } })]
        : "Finding the beats…");
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
      beatLine,
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

// Each editor has its own players (ctx.audioPlayers: track id -> { el, seekAt, src })
function playersOf(ctx) {
  return ctx.audioPlayers || (ctx.audioPlayers = new Map());
}

// jump: the playhead jumped (a loop wrapped): seek at once
export function syncAudio(ctx, time, playing, jump = false) {
  const p = ctx.p;
  const players = playersOf(ctx);
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
      pl.el.volume = Math.max(0, Math.min(1, gain * monitorGain(p)));
      const want = t.in + local;
      const now = performance.now();
      if (Math.abs(pl.el.currentTime - want) > 0.2 && (jump || now - pl.seekAt > 500)) {
        pl.seekAt = now;
        try { pl.el.currentTime = want; } catch { /* not loaded yet */ }
      }
      if (pl.el.paused) pl.el.play().catch(() => {});
    }
  }
  for (const [id, pl] of players) if (!live.has(id) && !pl.el.paused) pl.el.pause();
}

// The players of one editor
// For the test harness: the tracks this editor's monitor is playing right now.
export function audioState(ctx) {
  return [...playersOf(ctx).entries()].map(([id, pl]) => ({ id, playing: !pl.el.paused, volume: pl.el.volume, src: pl.src }));
}

export function stopAudio(ctx) {
  if (!ctx?.audioPlayers) return;
  for (const pl of ctx.audioPlayers.values()) pl.el.pause();
}

// The monitor's own volume (Timeline transport): 0 when muted, else ui.mon_volume (0–1, 1 by
// default). It scales the take and every soundtrack track the monitor plays; the merge never reads it.
export function monitorGain(p) {
  if (p?.ui?.mon_muted === true) return 0;
  const v = p?.ui?.mon_volume;
  return typeof v === "number" && Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 1;
}

// The take's own sound while tracks play: the Merge card's scene level, or silent when scene sound is off.
export function sceneVolume(p) {
  if (!playingTracks(p).some(({ t }) => t.mix)) return 1;
  const sa = p.global.merge.scene_audio || { mix: false, volume_db: -12 };
  return sa.mix ? Math.min(1, dbGain(sa.volume_db)) : 0;
}
