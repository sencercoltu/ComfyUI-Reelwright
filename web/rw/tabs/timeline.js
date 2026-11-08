// [OLD 2026-11-06 v0.8.0->v0.9.0] the asset bin is gone (the Assets tab has all of it)
// // Timeline tab: asset bin, monitor with transport, quick inspector, and the
// // multi-lane timeline (scenes, pictures, video, audio, dialogue, camera, LoRAs).
// [/OLD]
// Timeline tab (v0.9.0): three panels with bars between them to resize: the monitor with its transport (top left), the
// scene inspector and summary (top right), and the multi-lane timeline (scenes, pictures, video, audio, dialogue,
// camera, LoRAs) below.

// [OLD 2026-11-02 v0.2.2->v0.3.0] import { h, icon, button, toggle, segmented, chip, dot, slider } from "../ui.js";
// [OLD 2026-11-06 v0.8.0->v0.9.0] import { h, icon, button, toggle, segmented, chip, dot, slider, select } from "../ui.js";
import { h, icon, button, toggle, segmented, chip, dot, slider, select, splitter, uiNum, rootScale } from "../ui.js"; // added 2026-11-06 v0.9.0: panel bars
// [OLD 2026-11-05 v0.6.1->v0.7.0] import { viewURL } from "../api.js";
import { rw, viewURL } from "../api.js"; // added 2026-11-05 v0.7.0: rw.filmstrip
import { joinOf, TRANSITION, DIRECTED, DIRECTIONS, transitionLabel } from "../cut.js"; // added 2026-11-05 v0.7.0: cut marks
import { highlightHTML } from "../prompttext.js";
import {
  FPS, sceneStarts, fmtTime, framesOf, nearestGridFrames, estimatePasses, findAsset, findCast,
  effectiveLoras, overrideCount, sceneIndex, newId, assembledDuration, MIN_PASS_FRAMES,
  effective, // added 2026-11-02 v0.3.0
  // [OLD 2026-11-03 v0.5.1->v0.6.0] overlapSeconds, sceneHasSong, trackLength, // added 2026-11-03 v0.5.0  (overlapSeconds is deprecated)
  sceneHasSong, trackLength, // added 2026-11-03 v0.5.0
  // added 2026-11-03 v0.6.0: visible starts (Next/Prev/Loop), the real overlap of a continuing scene, locked timing
  sceneAt, sceneOverlapAt, tailOverlapFrames, soundtrackLocked,
  effectiveStart, MAX_SCENE_SECONDS, // added 2026-11-03 v0.6.0 review: rollLengths
  dialogueSeconds, SECTION_KEYS, // added 2026-11-06 v0.9.0: captions and the inspector's summary
} from "../model.js";
import { passLayout, passTextsOf } from "../passes.js"; // added 2026-11-06 v0.9.0: the pass at the playhead
// [OLD 2026-11-06 v0.8.0->v0.9.0] import { uploadFiles } from "./assets.js";  (only the asset bin used it)
import { addGroup } from "./assets.js"; // added 2026-11-06 v0.9.0: the asset menu's "New group"
// [OLD 2026-11-03 v0.5.1->v0.6.0] import { trackLanes, trackInspector, syncAudio, stopAudio, sceneVolume } from "./soundtrack.js"; // added 2026-11-03 v0.5.0
import {
  trackLanes, trackInspector, syncAudio, stopAudio, sceneVolume, // added 2026-11-03 v0.5.0
  deleteTrack, nearestBeat, showBeats, beatSnapOn, // added 2026-11-03 v0.6.0
  monitorGain, // added 2026-11-06 v0.9.0: the monitor's volume and mute
} from "./soundtrack.js";

const HEAD_W = 150;
const STATUS_LABEL = {
  cached: "On disk", stale: "Stale", pending: "Not rendered", missing: "Not rendered", queued: "Queued",
  rendering: "Rendering", locked: "Locked", error: "Failed", unknown: "Status unknown",
};

// added 2026-11-03 v0.5.0
function trackLengthOf(p, t) {
  return trackLength(t, findAsset(p, t.asset));
}

function zoomOf(ctx) {
  return ctx.p.ui.zoom || 22;
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] found scenes by [start, start + duration): a continuing scene's first frames lie inside
   the scene before, so Next/Prev/Loop stayed on the old scene (review #7). model.sceneAt(project, t) uses the visible
   ranges [visibleStart, start + duration) instead.
function sceneAt(ctx, t) {
  const { starts } = sceneStarts(ctx.p);
  for (const s of ctx.p.scenes) if (t >= starts[s.id] && t < starts[s.id] + s.duration) return s;
  return ctx.p.scenes[ctx.p.scenes.length - 1];
}
[/OLD] */

// added 2026-11-03 v0.6.0: Roll instead of Ripple while a soundtrack sets the timing (Auto-roll, on unless turned off):
// lengthening a scene takes the time from the next one, so every later scene (and its passes) stays on the song.
export function autoRollOn(p) {
  return soundtrackLocked(p) && p.ui.autoRoll !== false;
}
function rolls(p) {
  return !p.ui.ripple || autoRollOn(p);
}

/* [OLD 2026-11-03 v0.6.0 review] kept d_i + d_(i+1): a tail overlap is capped by the lengths of the scenes on both
   sides of its seam, so the overlaps changed and every later scene moved on the soundtrack
// added 2026-11-03 v0.6.0: set a scene's length (Scene tab, timeline). When it rolls (Roll, or Auto-roll), the next
// scene gives or takes the difference and keeps at least one frame. Returns the length set.
export function setSceneDuration(ctx, id, d, { label = "Scene length", roll = rolls(ctx.p) } = {}) {
  const p = ctx.p;
  const i = sceneIndex(p, id);
  if (i < 0) return 0;
  const s = p.scenes[i], next = p.scenes[i + 1];
  let frames = Math.max(1, framesOf(d));
  if (roll && next) frames = Math.min(frames, framesOf(s.duration + next.duration) - 1);
  const d1 = frames / FPS;
  const d0 = s.duration, nextD0 = next?.duration;
  ctx.actions.edit(q => {
    const sc = q.scenes.find(x => x.id === id);
    if (!sc) return;
    sc.duration = d1;
    if (roll && next) q.scenes.find(x => x.id === next.id).duration = Math.max(1 / FPS, Math.round((d0 + nextD0 - d1) * FPS) / FPS);
  }, { label });
  return d1;
}
[/OLD] */
// added 2026-11-03 v0.6.0 review: Roll keeps every later scene where it is. Scene i gets `frames`; the next scene gets
// the length that keeps the start of the scene after it (sceneStarts; the film's end when the next scene is the last)
// and, if it can, where that scene becomes visible. Tail overlaps are capped by the lengths on both sides of their
// seam, so keeping the sum of the two lengths is not enough. Of the lengths that work, the one closest to keeping the
// sum wins. When none works, scene i's length is clamped to the nearest one (towards its current length) that does.
// Returns {frames, next, nextDuration}: frames of scene i and of the next scene (next: null without a next scene), and
// the next scene's length in seconds: next / FPS, plus the part of a frame that keeps the later scenes exactly where
// they were when the two lengths were not whole frames.
export function rollLengths(p, i, frames) {
  const s = p.scenes[i], next = p.scenes[i + 1];
  frames = Math.max(1, Math.round(frames));
  if (!s || !next) return { frames, next: null, nextDuration: null };
  const after = p.scenes[i + 2];
  // How scenes i, i+1, i+2 start does not depend on lengths except through the tail caps: read the mode once with
  // lengths no cap reaches ("fresh", "last_frame": re-anchored or not a tail, "tail"), then a tail's overlap is
  // measured on a two-scene project (the scene before and the scene), so a long chain of continuing scenes is not
  // walked again for every length tried.
  const BIG = 1e4;
  const modeAt = k => {
    if (k <= 0 || !p.scenes[k]) return "fresh";
    const sc = p.scenes.slice();
    sc[k] = { ...sc[k], duration: BIG };
    sc[k - 1] = { ...sc[k - 1], duration: BIG };
    return effectiveStart({ ...p, scenes: sc }, k);
  };
  const modes = { [i]: modeAt(i), [i + 1]: modeAt(i + 1), [i + 2]: after ? modeAt(i + 2) : "fresh" };
  // overlap frames of scene k with lengths (frames) `own` and `prev` for it and the scene before
  const ovF = (k, own, prev) => {
    const m = modes[k];
    if (m === "fresh") return 0;
    if (m !== "tail") return 1;
    const two = [{ ...p.scenes[k - 1], duration: prev / FPS, start: { mode: "fresh", overlap_frames: 0 } }, { ...p.scenes[k], duration: own / FPS }];
    return Math.round(sceneOverlapAt({ ...p, scenes: two }, 1) * FPS);
  };
  const prevF = i > 0 ? p.scenes[i - 1].duration * FPS : 0;
  const afterF = after ? after.duration * FPS : 0;
  // frames from where scene i becomes visible to the start of scene i+2 (keep; the end of i+1 without one), and to
  // where scene i+2 becomes visible (vis)
  const span = (dF, nF, ovI = ovF(i, dF, prevF)) => {
    const ovA = after ? ovF(i + 2, afterF, nF) : 0;
    const keep = -ovI + dF - ovF(i + 1, nF, dF) + nF - ovA;
    return { keep, vis: keep + ovA };
  };
  const d0F = s.duration * FPS, n0F = next.duration * FPS;
  const target = span(d0F, n0F);
  const near = (a, b) => Math.abs(a - b) <= 0.5 + 1e-6; // within half a frame (lengths off the frame grid)
  // the exact length for nF frames: the rest of the half frame goes into it (lengths off the frame grid); null when
  // that length is not one a scene can have (it must round to nF frames and be 1 frame .. MAX_SCENE_SECONDS)
  const exact = (nF, r) => {
    const sec = (nF + (target.keep - r.keep)) / FPS;
    return framesOf(sec) === nF && sec >= 1 / FPS - 1e-12 && sec <= MAX_SCENE_SECONDS ? Math.max(1 / FPS, sec) : null;
  };
  const SLACK = 2 * MIN_PASS_FRAMES + 2; // the two overlaps the next scene's length changes are at most 124 frames each
  // the next scene's length for scene i's dF frames, or null; `strict`: only one that keeps the later scenes exactly
  const solve = (dF, strict) => {
    const ovI = ovF(i, dF, prevF);
    const base = target.keep + ovI - dF; // nF without the two overlaps it changes
    const lo = Math.max(1, Math.floor(base) - 1), hi = Math.min(Math.round(MAX_SCENE_SECONDS * FPS), Math.ceil(base) + SLACK);
    if (hi < lo) return null;
    const guess = Math.min(hi, Math.max(lo, Math.round(d0F + n0F - dF)));
    for (let dist = 0; guess - dist >= lo || guess + dist <= hi; dist++) {
      let keepOnly = null;
      for (const nF of dist ? [guess + dist, guess - dist] : [guess]) {
        if (nF < lo || nF > hi) continue;
        const r = span(dF, nF, ovI);
        if (!near(r.keep, target.keep)) continue;
        const sec = exact(nF, r);
        if (sec === null && strict) continue;
        const got = { nF, sec: sec ?? nF / FPS };
        if (near(r.vis, target.vis)) return got;
        if (keepOnly === null) keepOnly = got;
      }
      if (keepOnly !== null) return keepOnly;
    }
    return null;
  };
  const cur = Math.max(1, Math.round(d0F));
  // no longer than the two scenes plus the three overlaps that can change (the next scene keeps at least 1 frame)
  frames = Math.min(frames, Math.round(MAX_SCENE_SECONDS * FPS), Math.ceil(d0F + n0F) + 3 * MIN_PASS_FRAMES + 3);
  // an exact solution as close to the asked length as there is, else one within half a frame
  for (const strict of [true, false]) {
    for (let dF = frames, n = 0; n < 100000; n++) {
      const got = solve(dF, strict);
      if (got) return { frames: dF, next: got.nF, nextDuration: got.sec };
      if (dF === cur) break;
      dF += dF > cur ? -1 : 1;
    }
  }
  // nothing else keeps the later scenes: both stay as they are
  return { frames: cur, next: Math.max(1, Math.round(n0F)), nextDuration: next.duration, unchanged: true };
}

// added 2026-11-03 v0.6.0: set a scene's length (Scene tab, timeline). When it rolls (Roll, or Auto-roll), the next
// scene gives or takes the difference and keeps at least one frame. Returns the length set.
// added 2026-11-03 v0.6.0 review: rolling uses rollLengths (every later scene keeps its start)
export function setSceneDuration(ctx, id, d, { label = "Scene length", roll = rolls(ctx.p) } = {}) {
  const p = ctx.p;
  const i = sceneIndex(p, id);
  if (i < 0) return 0;
  const next = p.scenes[i + 1];
  let frames = Math.max(1, framesOf(d));
  let nextD = null, same = false;
  if (roll && next) ({ frames, nextDuration: nextD, unchanged: same } = rollLengths(p, i, frames));
  // scene i keeps its own length when the roll could not move (its length is not a whole number of frames)
  const d1 = same ? p.scenes[i].duration : frames / FPS;
  ctx.actions.edit(q => {
    const sc = q.scenes.find(x => x.id === id);
    if (!sc) return;
    sc.duration = d1;
    if (nextD !== null) q.scenes.find(x => x.id === next.id).duration = nextD;
  }, { label });
  return d1;
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
  // [OLD 2026-11-06 v0.8.0->v0.9.0] const el = h("div", { class: "rw-mon", help: "timeline.monitor" }, video, img, empty, h("div", { class: "rw-mon-safe" }), badgeTL, badgeTR, badgeBL, badgeBR);
  // [OLD 2026-11-06 v0.8.0->v0.9.0] const m = ctx.monitor = { el, video, img, empty, badgeTL, badgeTR, badgeBL, badgeBR, sceneId: null, src: "" };
  // added 2026-11-06 v0.9.0: the spoken line is a caption at the bottom (it was the bottom-right badge), timed like the
  // merge's .srt, and it follows the playhead while the film plays (m.overlay, called on every frame)
  const caption = h("div", { class: "rw-mon-cap", help: "timeline.monitor.caption" });
  badgeBR.style.display = "none";
  const el = h("div", { class: "rw-mon", help: "timeline.monitor" }, video, img, empty, h("div", { class: "rw-mon-safe" }), badgeTL, badgeTR, badgeBL, badgeBR, caption);
  const m = ctx.monitor = { el, video, img, empty, badgeTL, badgeTR, badgeBL, badgeBR, caption, capKey: null, sceneId: null, src: "" };
  // added 2026-11-12 v0.13.0: full screen (Sencer: "add option to go full screen for preview video"). The monitor moves
  // into m.fs, a box in the editor's root that re-renders never replace (the tab's own panels are rebuilt on every
  // render, which would end full screen), with a bar: play/pause, time, scene, exit. Double-click or F toggles it;
  // in full screen a click plays or pauses and Esc comes back.
  m.fsPlay = h("button", { type: "button", class: "rw-mon-fsbtn", help: "timeline.fullscreen.play", onClick: e => { e.stopPropagation(); togglePlay(ctx); } });
  m.fsTime = h("span", { class: "mono rw-mon-fstime" });
  m.fsTitle = h("span", { class: "rw-mon-fstitle rw-ellipsis" });
  m.fsBar = h("div", { class: "rw-mon-fsbar" }, m.fsPlay, m.fsTime, m.fsTitle, h("span", { class: "rw-flex" }),
    h("button", { type: "button", class: "rw-mon-fsbtn", help: "timeline.fullscreen.exit", onClick: e => { e.stopPropagation(); exitFull(ctx); } }, icon("close", 16)));
  m.fs = h("div", { class: "rw-mon-fs", tabindex: "-1", help: "timeline.fullscreen" });
  m.fsPlaying = null;
  el.addEventListener("dblclick", e => { e.preventDefault(); toggleFull(ctx); });
  el.addEventListener("click", () => { if (ctx.monFull) togglePlay(ctx); });
  const onFs = () => {
    if (!ctx.root.isConnected) { document.removeEventListener("fullscreenchange", onFs); document.removeEventListener("webkitfullscreenchange", onFs); return; }
    if ((document.fullscreenElement || document.webkitFullscreenElement) === m.fs) return;
    if (ctx.monFull) { ctx.monFull = false; ctx.render(); } // the next render puts the monitor back in its panel
  };
  document.addEventListener("fullscreenchange", onFs);
  document.addEventListener("webkitfullscreenchange", onFs);

  m.show = (scene, local) => {
    const take = ctx.starredTake(scene.id);
    const src = take?.files?.video ? viewURL(take.files.video) : "";
    if (m.sceneId !== scene.id || m.src !== src) {
      // added 2026-11-12 v0.13.0: a new take of the scene that is playing (a render finished while the film played):
      // it takes over at the same moment and keeps playing (before, the monitor stopped on its first frame)
      const resume = ctx.eph.playing && m.sceneId === scene.id && !!src;
      m.sceneId = scene.id;
      m.src = src;
      // [OLD 2026-11-12 v0.12.0->v0.13.0] if (src) { video.src = src; video.style.display = ""; img.style.display = "none"; empty.style.display = "none"; }
      if (src) {
        video.src = src; video.style.display = ""; img.style.display = "none"; empty.style.display = "none";
        if (resume) {
          const go = () => {
            if (!ctx.eph.playing || m.src !== src) return;
            const st = sceneStarts(ctx.p).starts[scene.id];
            const at = st === undefined ? local : ctx.p.ui.playhead - st;
            try { video.currentTime = Math.max(0, Math.min(at, scene.duration)); } catch { /* not seekable yet */ }
            applyVolume(ctx);
            video.play().catch(() => {});
          };
          if (video.readyState >= 1) go(); else video.addEventListener("loadedmetadata", go, { once: true });
        }
      }
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
    /* [OLD 2026-11-06 v0.8.0->v0.9.0] set only when the monitor's scene was shown again (render, seek, a new scene), so
       the line and the frame count stood still while the film played; the line was shown for 3.5 s whatever its length
    const idx = sceneIndex(ctx.p, scene.id) + 1;
    badgeBL.textContent = `${String(idx).padStart(2, "0")} · f ${Math.min(framesOf(local), framesOf(scene.duration))} / ${framesOf(scene.duration)}`;
    const line = scene.dialogue.find(d => local >= d.t && local < d.t + 3.5);
    const sp = line && findCast(ctx.p, line.speaker);
    // [OLD 2026-11-02 v0.1.0->v0.2.0] badgeBR.textContent = line ? `${sp?.name || "?"} (${sp?.speaker || "S?"}): “${line.text}”` : "";  (speaker IDs are per clip now)
    badgeBR.textContent = line ? `${sp?.name || "?"}: “${line.text}”` : "";
    badgeBR.style.display = line ? "" : "none";
    [/OLD] */
    m.overlay(scene, local); // added 2026-11-06 v0.9.0
  };
  // added 2026-11-06 v0.9.0: the frame count and the caption at `local` (scene time). Cheap: the DOM is touched only
  // when the text changes. Off with the transport's CC button (ui.captions).
  m.overlay = (scene, local) => {
    if (ctx.monFull) fullBar(ctx, scene); // added 2026-11-12 v0.13.0
    const idx = sceneIndex(ctx.p, scene.id) + 1;
    const bl = `${String(idx).padStart(2, "0")} · f ${Math.min(framesOf(local), framesOf(scene.duration))} / ${framesOf(scene.duration)}`;
    if (badgeBL.textContent !== bl) badgeBL.textContent = bl;
    // [OLD 2026-11-06 v0.9.0->v0.10.0] const line = ctx.p.ui.captions === false ? null : captionAt(ctx.p, scene, local);
    const line = ctx.p.ui.captions === false ? null : captionAt(ctx.p, scene, local, speechOf(ctx, scene)); // added 2026-11-06 v0.10.0: timed to the speech
    const key = line ? `${scene.id}|${line.id}|${line.speaker}|${line.text}` : "";
    if (key === m.capKey) return;
    m.capKey = key;
    if (!line) { caption.replaceChildren(); caption.style.display = "none"; return; }
    const sp = findCast(ctx.p, line.speaker);
    // (replaceChildren writes null as the word "null": only real nodes go in)
    caption.replaceChildren(...[sp?.name ? h("b", null, sp.name + ": ") : null, cueText(line)].filter(x => x !== null));
    caption.style.display = "";
  };
  return m;
}

// added 2026-11-12 v0.13.0: the monitor full screen (see monitorOf)
function enterFull(ctx) {
  const m = monitorOf(ctx);
  if (ctx.monFull) return;
  const req = m.fs.requestFullscreen || m.fs.webkitRequestFullscreen;
  if (!req) { ctx.actions.toast("This browser cannot show the monitor full screen.", "warn"); return; }
  if (!m.fs.isConnected) ctx.root.appendChild(m.fs);
  m.fs.replaceChildren(m.el, m.fsBar);
  ctx.monFull = true;
  m.fsPlaying = null;
  let res;
  try { res = req.call(m.fs); } catch (err) { res = Promise.reject(err); }
  Promise.resolve(res).then(() => { m.fs.focus({ preventScroll: true }); }, () => {
    if (!ctx.monFull) return;
    ctx.monFull = false;
    ctx.actions.toast("The browser did not allow full screen.", "warn");
    ctx.render();
  });
  fullBar(ctx, sceneAt(ctx.p, ctx.p.ui.playhead));
  ctx.render();
}
function exitFull(ctx) {
  const m = ctx.monitor;
  if (!m) return;
  const exit = document.exitFullscreen || document.webkitExitFullscreen;
  if ((document.fullscreenElement || document.webkitFullscreenElement) === m.fs && exit) exit.call(document);
  else if (ctx.monFull) { ctx.monFull = false; ctx.render(); }
}
export function toggleFull(ctx) {
  if (ctx.monFull) exitFull(ctx); else enterFull(ctx);
}
function fullBar(ctx, scene) {
  const m = ctx.monitor;
  if (m.fsPlaying !== !!ctx.eph.playing) {
    m.fsPlaying = !!ctx.eph.playing;
    m.fsPlay.replaceChildren(icon(m.fsPlaying ? "pause" : "play", 16));
  }
  const t = `${fmtTime(ctx.p.ui.playhead)} / ${fmtTime(sceneStarts(ctx.p).total)}`;
  if (m.fsTime.textContent !== t) m.fsTime.textContent = t;
  const title = `${String(sceneIndex(ctx.p, scene.id) + 1).padStart(2, "0")} · ${scene.title}`;
  if (m.fsTitle.textContent !== title) m.fsTitle.textContent = title;
}

// added 2026-11-06 v0.10.0: the lines of a scene timed to the speech of its starred take (POST /reelwright/speech, the
// same timing as the merge's subtitles), cached per take and lines; null while it loads, without a take or speech, or
// when Render -> Merge -> Subtitles is set to the planned times. When the answer comes, the captions use it.
const speechCache = new WeakMap(); // ctx -> Map(key -> {state, byId})
function speechOf(ctx, scene) {
  if (ctx.p.global.merge?.subtitle_timing === "planned") return null;
  const take = ctx.starredTake(scene.id);
  const file = take?.files?.video;
  if (!file) return null;
  const lines = scene.dialogue.filter(d => cueText(d)).map(d => ({ id: d.id, t: d.t, duration: dialogueSeconds(d) }));
  if (!lines.length) return null;
  const map = speechCache.get(ctx) || new Map();
  speechCache.set(ctx, map);
  const key = `${file}|${take.created ?? ""}|${JSON.stringify(lines)}`;
  let e = map.get(key);
  if (!e) {
    e = { state: "loading", byId: null };
    map.set(key, e);
    if (map.size > 200) map.delete(map.keys().next().value);
    rw.speech(file, lines).then(r => {
      e.state = "ok";
      e.byId = new Map((r.lines || []).map(x => [x.id, x]));
      const m = ctx.monitor;
      if (m && m.sceneId === scene.id) { m.capKey = null; const st = sceneStarts(ctx.p).starts[scene.id] ?? 0; m.overlay(scene, ctx.p.ui.playhead - st); }
    }).catch(() => { e.state = "error"; });
  }
  return e.state === "ok" ? e.byId : null;
}

// added 2026-11-06 v0.9.0: a dialogue line as a caption, the way merge.py's subtitle_cues times the .srt: from its time
// for its own length (Scene tab), or for its reading time (0.6 s + 0.07 s a character, at least 1.2 s); never past the
// next line's start or the scene's end. Empty lines are not captions.
function cueText(d) {
  return String(d.text || "").replace(/\r\n?/g, "\n").split("\n").map(x => x.trim()).filter(Boolean).join("\n");
}
// added 2026-11-06 v0.10.0: with `timed` (speechOf: line id -> {t, end} in the take), a line is shown while its speech
// lasts; lines the take's speech did not match keep their planned time
function captionAt(p, scene, local, timed = null) {
  if (timed) {
    for (const d of scene.dialogue) {
      const x = timed.get(d.id);
      if (x && cueText(d) && x.t <= local && local < x.end) return d;
    }
    return null;
  }
  const lines = scene.dialogue.filter(d => cueText(d)).slice().sort((a, b) => a.t - b.t);
  for (let i = lines.length - 1; i >= 0; i--) {
    const d = lines[i];
    if (d.t > local) continue;
    const name = findCast(p, d.speaker)?.name || "";
    const chars = (name ? name.length + 2 : 0) + cueText(d).length; // the .srt cue is "Name: text"
    const dur = typeof d.duration === "number" && d.duration > 0 ? Math.max(0.3, d.duration) : Math.max(1.2, 0.6 + 0.07 * chars);
    let end = d.t + dur;
    if (i + 1 < lines.length) end = Math.min(end, lines[i + 1].t - 0.05);
    end = Math.max(Math.min(end, scene.duration), d.t + 0.3);
    return local < end ? d : null;
  }
  return null;
}

function setPlayhead(ctx, t, { seekVideo = true } = {}) {
  const { total } = sceneStarts(ctx.p);
  // [OLD 2026-11-03 v0.5.1->v0.6.0] t = Math.max(0, Math.min(total, t));
  t = Number.isFinite(t) ? Math.max(0, Math.min(total, t)) : 0; // added 2026-11-03 v0.6.0: never NaN
  ctx.store.update(p => { p.ui.playhead = t; }, { history: false, plan: false, render: false, autosave: false });
  const refs = ctx.tl;
  const z = zoomOf(ctx);
  if (refs?.playhead) {
    refs.playhead.style.left = (HEAD_W + t * z) + "px";
    refs.playheadLabel.textContent = fmtTime(t);
    refs.timecode.textContent = fmtTime(t);
  }
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const s = sceneAt(ctx, t);
  const s = sceneAt(ctx.p, t);
  const local = t - sceneStarts(ctx.p).starts[s.id];
  const m = monitorOf(ctx);
  // [OLD 2026-11-06 v0.8.0->v0.9.0] if (seekVideo) m.show(s, local);
  if (seekVideo) m.show(s, local); else m.overlay(s, local); // added 2026-11-06 v0.9.0: the caption and frame count follow
  nowAt(ctx, s, local); // added 2026-11-06 v0.9.0: the inspector's "at the playhead" line
  return { scene: s, local };
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] one animation frame for every editor on the page
let raf = 0;
export function stopPlayback(ctx) {
  cancelAnimationFrame(raf);
  raf = 0;
  ctx.eph.playing = false;
  if (ctx.monitor) ctx.monitor.video.pause();
  stopAudio(); // added 2026-11-03 v0.5.0
}
[/OLD] */
// added 2026-11-03 v0.6.0: each editor has its own playback frame (ctx.play) and its own audio players
function playOf(ctx) {
  return ctx.play || (ctx.play = { raf: 0 });
}

export function stopPlayback(ctx) {
  const pl = playOf(ctx);
  cancelAnimationFrame(pl.raf);
  pl.raf = 0;
  ctx.eph.playing = false;
  if (ctx.monitor) ctx.monitor.video.pause();
  stopAudio(ctx);
  pauseExcerpts(ctx);
}

// The Scene tab's song excerpts (scene.js) stop when the film plays or the editor closes.
function pauseExcerpts(ctx) {
  for (const el of ctx.excerptPlayers || []) if (!el.paused) el.pause();
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] a loop over a rendered take wrapped the playhead but never seeked the video (so the
   next frame jumped back); a deleted or undone playing scene gave a NaN playhead; one rAF for every editor
function startPlayback(ctx) {
  if (ctx.eph.playing) return;
  const { total } = sceneStarts(ctx.p);
  if (ctx.p.ui.playhead >= total - 1 / FPS) setPlayhead(ctx, 0);
  ctx.eph.playing = true;
  const m = monitorOf(ctx);
  let last = performance.now();
  let current = setPlayhead(ctx, ctx.p.ui.playhead);
  m.video.volume = sceneVolume(ctx.p); // added 2026-11-03 v0.5.0: the scene level under the soundtrack
  if (m.src) { m.video.currentTime = current.local; m.video.play().catch(() => {}); }
  syncAudio(ctx, ctx.p.ui.playhead, true); // added 2026-11-03 v0.5.0
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
    // added 2026-11-03 v0.5.0: soundtrack tracks follow the playhead; the take plays at the scene level
    m.video.volume = sceneVolume(ctx.p);
    syncAudio(ctx, t, true);
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);
  ctx.render();
}
[/OLD] */
// added 2026-11-03 v0.6.0
function startPlayback(ctx) {
  if (ctx.eph.playing) return;
  const pl = playOf(ctx);
  const { total } = sceneStarts(ctx.p);
  if (!(ctx.p.ui.playhead < total - 1 / FPS)) setPlayhead(ctx, 0);
  pauseExcerpts(ctx);
  ctx.eph.playing = true;
  const m = monitorOf(ctx);
  let last = performance.now();
  let current = setPlayhead(ctx, ctx.p.ui.playhead);
  // [OLD 2026-11-06 v0.8.0->v0.9.0] m.video.volume = sceneVolume(ctx.p); // the scene level under the soundtrack
  applyVolume(ctx); // added 2026-11-06 v0.9.0: the scene level under the soundtrack, times the monitor's volume
  if (m.src) { m.video.currentTime = current.local; m.video.play().catch(() => {}); }
  syncAudio(ctx, ctx.p.ui.playhead, true);
  const loop = now => {
    if (!ctx.eph.playing) return;
    const dt = (now - last) / 1000;
    last = now;
    const { starts, total: tot } = sceneStarts(ctx.p);
    // the scene that was playing was deleted (or undone away): go on from the playhead in the scene there now
    if (starts[current.scene.id] === undefined) current = setPlayhead(ctx, ctx.p.ui.playhead);
    let t;
    if (m.src && !m.video.paused && m.sceneId === current.scene.id) t = starts[current.scene.id] + Math.min(m.video.currentTime, current.scene.duration);
    else t = ctx.p.ui.playhead + dt;
    if (!Number.isFinite(t)) t = 0;
    // a loop wraps the playhead; the take and the soundtrack are seeked to it (they would carry on otherwise)
    let jump = false;
    const loopR = ctx.eph.loop;
    if (loopR && t >= loopR.out) { t = loopR.in; jump = true; }
    if (t >= tot) { setPlayhead(ctx, tot); stopPlayback(ctx); ctx.render(); return; }
    const before = current.scene.id;
    const localEnd = t - starts[current.scene.id] >= current.scene.duration;
    const there = sceneAt(ctx.p, t);
    current = setPlayhead(ctx, t, { seekVideo: jump || localEnd || current.scene.id !== there.id || !m.src });
    if (current.scene.id !== before || localEnd || jump) {
      if (m.src) { m.video.currentTime = current.local; m.video.play().catch(() => {}); }
    }
    // soundtrack tracks follow the playhead; the take plays at the scene level
    // [OLD 2026-11-06 v0.8.0->v0.9.0] m.video.volume = sceneVolume(ctx.p);
    applyVolume(ctx); // added 2026-11-06 v0.9.0: times the monitor's volume
    syncAudio(ctx, t, true, jump);
    followPlayhead(ctx, t); // added 2026-11-05 v0.8.0
    pl.raf = requestAnimationFrame(loop);
  };
  // added 2026-11-05 v0.8.0: pressing play follows the playhead again (see followPlayhead)
  Object.assign(pl, { follow: true, sl: null, prevPx: null });
  pl.raf = requestAnimationFrame(loop);
  ctx.render();
}

// added 2026-11-06 v0.9.0: the take's volume in the monitor: the scene level under the soundtrack times the monitor's own
// volume (transport); the tracks get the monitor's volume in syncAudio
function applyVolume(ctx) {
  const m = ctx.monitor;
  if (m) m.video.volume = Math.max(0, Math.min(1, sceneVolume(ctx.p) * monitorGain(ctx.p)));
}

// added 2026-11-05 v0.8.0: while the film plays, the lanes scroll so the playhead stays in the middle of the view
// (the browser clamps it at the film's start and end). A manual scroll, wheel or drag pauses following (pl.follow =
// false) until play is pressed again or the playhead reaches the middle of the view again. Only scrollLeft is set,
// so a long film is rebuilt only when the view nears the edge of the lanes that were built (lanesScroll).
function followPlayhead(ctx, t) {
  const pl = playOf(ctx);
  const el = ctx.root.querySelector(".rw-lanes");
  if (!el) return;
  const z = zoomOf(ctx);
  const half = Math.max(0, (el.clientWidth - HEAD_W) / 2);
  const x = t * z; // the playhead, in lane-body pixels
  if (!pl.follow) {
    const px = x - el.scrollLeft; // where it is in the view
    const back = pl.prevPx !== null && pl.prevPx < half - 0.5 && px >= half - 0.5;
    pl.prevPx = px;
    if (!back) return;
    pl.follow = true; // it came back to the middle
    ctx.store.notify(); // the transport's Follow button goes away
  }
  const max = Math.max(0, el.scrollWidth - el.clientWidth);
  const sl = Math.round(Math.max(0, Math.min(max, x - half)));
  // the view moves in steps of a few pixels (the playhead stays within FOLLOW_STEP of the middle): every scroll repaints
  // the lanes, which cost a long film (300 scenes) frames when it happened on every frame at a high zoom
  if (Math.abs(el.scrollLeft - sl) >= FOLLOW_STEP || ((sl === 0 || sl === max) && el.scrollLeft !== sl)) el.scrollLeft = sl;
  pl.sl = el.scrollLeft;
  pl.prevPx = x - pl.sl;
}
const FOLLOW_STEP = 4;

// a manual scroll (scrollbar, wheel, drag) while following: pause it. `el` scrolled to somewhere followPlayhead did not
// put it (re-renders restore the same position; a zoom resets pl.sl first)
function pauseFollow(ctx) {
  const pl = ctx.play;
  if (!pl?.follow || !ctx.eph.playing) return;
  pl.follow = false;
  pl.prevPx = null;
  ctx.store.notify(); // shows the transport's Follow button
}
function followScrolled(ctx, el) {
  const pl = ctx.play;
  // a lanes element a render replaced still gets its last scroll event (and reads 0): not a manual scroll
  if (!pl?.follow || !ctx.eph.playing || typeof pl.sl !== "number" || !el.isConnected) return;
  if (Math.abs(el.scrollLeft - pl.sl) > 2) pauseFollow(ctx);
}
function resumeFollow(ctx) {
  const pl = playOf(ctx);
  Object.assign(pl, { follow: true, sl: null, prevPx: null });
  followPlayhead(ctx, ctx.p.ui.playhead);
  ctx.store.notify();
}

function togglePlay(ctx) {
  if (ctx.eph.playing) { stopPlayback(ctx); ctx.render(); } else startPlayback(ctx);
}

// ---- Keyboard ----

// added 2026-11-04 v0.6.1: a letter shortcut is the letter key without Shift (Shift+S is not S; Caps Lock does not
// matter). The editor has already kept Ctrl/Cmd/Alt combinations away (editor.js plainKey).
const letter = (e, ch) => !e.shiftKey && e.key.length === 1 && e.key.toLowerCase() === ch;

export function onKey(ctx, e) {
  const p = ctx.p;
  const k = e.key;
  if (k === " ") { togglePlay(ctx); return true; }
  /* [OLD 2026-11-04 v0.6.0->v0.6.1] Shift+letter (and Ctrl/Cmd/Alt+letter) acted like the letter
  if (k === "k" || k === "K") { stopPlayback(ctx); ctx.render(); return true; }
  if (k === "l" || k === "L") { startPlayback(ctx); return true; }
  if (k === "j" || k === "J") { setPlayhead(ctx, p.ui.playhead - 1); return true; }
  [/OLD] */
  if (letter(e, "k")) { stopPlayback(ctx); ctx.render(); return true; } // added 2026-11-04 v0.6.1: letter()
  if (letter(e, "l")) { startPlayback(ctx); return true; } // added 2026-11-04 v0.6.1
  if (letter(e, "j")) { setPlayhead(ctx, p.ui.playhead - 1); return true; } // added 2026-11-04 v0.6.1
  if (k === "ArrowLeft") { setPlayhead(ctx, p.ui.playhead - (e.shiftKey ? 1 : 1 / FPS)); return true; }
  if (k === "ArrowRight") { setPlayhead(ctx, p.ui.playhead + (e.shiftKey ? 1 : 1 / FPS)); return true; }
  if (k === "Home") { setPlayhead(ctx, 0); return true; }
  if (k === "End") { setPlayhead(ctx, sceneStarts(p).total); return true; }
  /* [OLD 2026-11-04 v0.6.0->v0.6.1] Shift+letter acted like the letter
  if (k === "i" || k === "I") { ctx.store.setEph({ loop: { in: p.ui.playhead, out: Math.max(p.ui.playhead + 0.5, ctx.eph.loop?.out ?? sceneStarts(p).total) } }); return true; }
  if (k === "o" || k === "O") { ctx.store.setEph({ loop: { in: Math.min(ctx.eph.loop?.in ?? 0, p.ui.playhead - 0.5), out: p.ui.playhead } }); return true; }
  if (k === "m" || k === "M") { addMarker(ctx); return true; }
  [/OLD] */
  if (letter(e, "i")) { ctx.store.setEph({ loop: { in: p.ui.playhead, out: Math.max(p.ui.playhead + 0.5, ctx.eph.loop?.out ?? sceneStarts(p).total) } }); return true; } // added 2026-11-04 v0.6.1
  if (letter(e, "o")) { ctx.store.setEph({ loop: { in: Math.min(ctx.eph.loop?.in ?? 0, p.ui.playhead - 0.5), out: p.ui.playhead } }); return true; } // added 2026-11-04 v0.6.1
  if (letter(e, "m")) { addMarker(ctx); return true; } // added 2026-11-04 v0.6.1
  if (letter(e, "f")) { toggleFull(ctx); return true; } // added 2026-11-12 v0.13.0: the monitor full screen
  if (k === "+" || k === "=") { setZoom(ctx, zoomOf(ctx) * 1.25); return true; }
  if (k === "-") { setZoom(ctx, zoomOf(ctx) / 1.25); return true; }
  // added 2026-11-03 v0.6.0: Delete removes what the inspector shows: a marker, a soundtrack track, else the scene
  // (sceneKeys, which asks first)
  if (k === "Delete" || k === "Backspace") {
    const mk = ctx.eph.selectedMarker && p.markers.find(m => m.id === ctx.eph.selectedMarker);
    if (mk) { deleteMarker(ctx, mk); return true; }
    const tr = ctx.eph.selectedTrack && p.soundtrack.find(t => t.id === ctx.eph.selectedTrack);
    if (tr) { deleteTrack(ctx, tr); return true; }
  }
  return false;
}

// added 2026-11-03 v0.6.0
function deleteMarker(ctx, marker) {
  ctx.actions.edit(q => { q.markers = q.markers.filter(m => m.id !== marker.id); }, { label: "Delete marker" });
  ctx.store.setEph({ selectedMarker: null });
  ctx.actions.toast("Marker removed. Ctrl+Z brings it back.", "info");
}

// Scene shortcuts that work from any tab.
export function sceneKeys(ctx, e) {
  const s = ctx.scene;
  if (!s) return false;
  const k = e.key;
  /* [OLD 2026-11-04 v0.6.0->v0.6.1] Shift+S / Shift+D / Shift+N (and Ctrl/Cmd/Alt with them) split, duplicated, added
  if (k === "s" || k === "S") {
    const { starts } = sceneStarts(ctx.p);
    ctx.actions.splitScene(s.id, ctx.p.ui.playhead - starts[s.id]);
    return true;
  }
  if (k === "d" || k === "D") { ctx.actions.duplicateScene(s.id); return true; }
  if (k === "Delete" || k === "Backspace") { ctx.actions.deleteScene(s.id); return true; }
  if (k === "n" || k === "N") { ctx.actions.addScene(s.id); return true; }
  return false;
  [/OLD] */
  // added 2026-11-04 v0.6.1: letters without Shift only (letter())
  if (letter(e, "s")) {
    const { starts } = sceneStarts(ctx.p);
    ctx.actions.splitScene(s.id, ctx.p.ui.playhead - starts[s.id]);
    return true;
  }
  if (letter(e, "d")) { ctx.actions.duplicateScene(s.id); return true; }
  if (k === "Delete" || k === "Backspace") { ctx.actions.deleteScene(s.id); return true; }
  if (letter(e, "n")) { ctx.actions.addScene(s.id); return true; }
  return false;
}

function setZoom(ctx, z) {
  z = Math.max(4, Math.min(160, z));
  if (ctx.play) ctx.play.sl = null; // added 2026-11-05 v0.8.0: a zoom moves the view; that is not a manual scroll
  ctx.store.update(p => { p.ui.zoom = Math.round(z * 10) / 10; }, { history: false, plan: false, autosave: false });
}

function addMarker(ctx) {
  const id = newId("m");
  // [OLD 2026-11-03 v0.5.1->v0.6.0] ctx.store.update(p => { p.markers.push({ id, t: p.ui.playhead, text: "Marker", color: "amber" }); });
  ctx.store.update(p => { p.markers.push({ id, t: p.ui.playhead, text: "Marker", color: "amber" }); }, { label: "Add marker" });
  // [OLD 2026-11-03 v0.5.1->v0.6.0] ctx.store.setEph({ selectedMarker: id });
  ctx.store.setEph({ selectedMarker: id, selectedTrack: null }); // v0.6.0: the marker is what Delete removes now
}

// ---- Asset bin ----
// [OLD 2026-11-06 v0.8.0->v0.9.0] the asset bin was removed from the Timeline tab (the Assets tab has all of it)
// function renderBin(ctx) {
//   const p = ctx.p;
//   const groups = [["image", "Pictures", "pic"], ["video", "Videos", "vid"], ["audio", "Audio", "aud"]];
//   const fileInput = h("input", {
//     type: "file", multiple: true, accept: "image/*,video/*,audio/*", style: { display: "none" },
//     onChange: e => uploadFiles(ctx, [...e.target.files]),
//   });
//   return h("div", { class: "rw-bin rw-panel" },
//     h("div", { class: "rw-panel-head" }, h("b", null, "Asset bin"), h("span", { class: "mono rw-dim" }, p.assets.length),
//       h("button", { type: "button", class: "rw-q", dataset: { more: "timeline.bin" }, help: "timeline.bin", "aria-label": "Help" }, "?"),
//       h("span", { class: "rw-flex" }),
//       button({ icon: "upload", help: "timeline.bin.upload", small: true, onClick: () => fileInput.click() }), fileInput),
//     h("div", { class: "rw-bin-list", dataset: { scroll: "bin" } },
//       p.assets.length === 0 && h("div", { class: "rw-empty sm", help: "timeline.bin" }, "Drop images, video or audio here, then drag them onto a scene."),
//       groups.map(([kind, label, cls]) => {
//         const items = p.assets.filter(a => a.kind === kind);
//         if (!items.length) return null;
//         return h("div", { class: "rw-bin-group" },
//           h("div", { class: "rw-bin-label rw-c-" + cls }, icon(kind, 12), label, h("span", { class: "mono rw-dim" }, items.length)),
//           items.map(a => h("div", {
//             class: ["rw-bin-item", ctx.eph.selectedAsset === a.id && "on"], draggable: "true", help: "timeline.bin.item",
//             onDragstart: e => { e.dataTransfer.setData("application/x-rw-asset", a.id); e.dataTransfer.effectAllowed = "copy"; },
//             onClick: () => ctx.store.setEph({ selectedAsset: a.id }),
//             onDblclick: () => { ctx.store.setEph({ selectedAsset: a.id }); ctx.actions.setTab("assets"); },
//             menu: () => assetMenu(ctx, a), // added 2026-11-02 v0.3.0
//           },
//           kind === "image" ? h("img", { class: "rw-bin-thumb", src: viewURL(a.file, "input"), alt: "", loading: "lazy" }) : h("span", { class: "rw-bin-thumb rw-bg-" + cls + "-soft" }, icon(kind, 12)),
//           h("b", { class: "mono rw-c-" + cls }, a.code), h("span", { class: "rw-ellipsis" }, a.name || a.file.split("/").pop()),
//           a.duration ? h("span", { class: "mono rw-dim" }, a.duration.toFixed(1) + "s") : null)));
//       })),
//     h("div", {
//       class: "rw-bin-drop", help: "timeline.bin.upload",
//       onDragover: e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); e.currentTarget.classList.add("over"); } },
//       onDragleave: e => e.currentTarget.classList.remove("over"),
//       onDrop: e => { e.preventDefault(); e.currentTarget.classList.remove("over"); uploadFiles(ctx, [...e.dataTransfer.files]); },
//     }, icon("upload", 12), "Drop files to upload"));
// }
// [/OLD]

// ---- Inspector ----

function renderInspector(ctx) {
  const p = ctx.p;
  // added 2026-11-03 v0.5.0: a soundtrack track selected on its lane
  const track = !ctx.eph.selectedMarker && p.soundtrack.find(t => t.id === ctx.eph.selectedTrack);
  if (track) return trackInspector(ctx, track, { playFrom: t => { stopPlayback(ctx); setPlayhead(ctx, t); startPlayback(ctx); } });
  const marker = p.markers.find(m => m.id === ctx.eph.selectedMarker);
  if (marker) {
    return h("div", { class: "rw-insp rw-panel" },
      h("div", { class: "rw-panel-head" }, icon("marker", 14), h("b", null, "Marker"), h("span", { class: "mono rw-dim" }, fmtTime(marker.t)),
        h("span", { class: "rw-flex" }),
        button({ icon: "close", help: "common.close", variant: "ghost", small: true, onClick: () => ctx.store.setEph({ selectedMarker: null }) })),
      h("div", { class: "rw-form" },
        h("label", { class: "rw-field" }, h("span", { class: "rw-field-label", help: "timeline.marker.text" }, "Text"),
          /* [OLD 2026-11-03 v0.5.1->v0.6.0] no history labels; the key was the same for every marker
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
          [/OLD] */
          // added 2026-11-03 v0.6.0
          h("input", { class: "rw-input", key: "marker-text-" + marker.id, value: marker.text, help: "timeline.marker.text",
            onChange: e => ctx.actions.edit(q => { const m = q.markers.find(x => x.id === marker.id); if (m) m.text = e.target.value; }, { label: "Marker text" }) })),
        h("div", { class: "rw-field" }, h("span", { class: "rw-field-label", help: "timeline.marker.color" }, "Colour"),
          segmented({ options: ["amber", "coral", "blue", "green", "pink"], value: marker.color, help: "timeline.marker.color", small: true,
            onChange: v => ctx.actions.edit(q => { const m = q.markers.find(x => x.id === marker.id); if (m) m.color = v; }, { label: "Marker colour" }) })),
        h("div", { class: "rw-row" },
          button({ label: "Jump to marker", icon: "marker", help: "timeline.marker.jump", onClick: () => setPlayhead(ctx, marker.t) }),
          button({ label: "Delete marker", icon: "trash", help: "timeline.marker.delete", variant: "danger-ghost", onClick: () => deleteMarker(ctx, marker) }))));
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
    summaryBlock(ctx, s), // added 2026-11-06 v0.9.0: the scene's summary and what is on screen at the playhead
    h("div", { class: "rw-chips" }, refChips(ctx, s)),
    h("pre", { class: "rw-prompt-preview mono", help: "timeline.inspector.prompt", html: prompt ? highlightHTML(prompt) : "" },
      prompt ? null : h("span", { class: "rw-dim" }, ctx.eph.backend === "online" ? "The prompt preview appears once the scene has a prompt." : "Prompt preview needs the Reelwright backend (start ComfyUI with the node installed).")),
    h("div", { class: "rw-row" },
      button({ label: "Render scene", icon: "play", help: "timeline.inspector.render", onClick: () => ctx.actions.run("selected", [s.id]) }),
      button({ label: "New take", icon: "refresh", help: "timeline.inspector.take", onClick: () => ctx.actions.run("take", [s.id]) }),
      h("span", { class: "rw-flex" }),
      toggle({ value: s.lock, label: "Lock take", help: "scene.lock", onChange: v => ctx.actions.editScene(s.id, sc => { sc.lock = v; }) })));
}

// added 2026-11-06 v0.9.0: the inspector's summary: the scene's summary (in a scene of several passes, the whole-scene
// note), then the pass, shot and spoken line at the playhead, which follow the playhead while the film plays (nowAt)
function summaryBlock(ctx, s) {
  const p = ctx.p;
  const plan = passLayout(p, s);
  const multi = plan.passes.length > 1;
  const raw = s.prompt.mode === "raw";
  const txt = (raw ? s.prompt.raw : s.prompt.sections.summary || "").trim();
  const now = h("div", { class: "rw-insp-now", help: "timeline.inspector.now" });
  ctx.tl = ctx.tl || {};
  Object.assign(ctx.tl, { now, nowScene: s.id, nowPlan: plan, nowTexts: multi ? passTextsOf(p, s, plan).texts : null, nowKey: null });
  const { starts } = sceneStarts(p);
  nowAt(ctx, sceneAt(p, p.ui.playhead), p.ui.playhead - (starts[sceneAt(p, p.ui.playhead).id] ?? 0));
  return h("div", { class: "rw-insp-sum" },
    h("div", { class: "rw-insp-label", help: multi && !raw ? "scene.prompt.sceneNote" : "timeline.inspector.summary" },
      raw ? "Raw prompt" : multi ? `Scene note · ${plan.passes.length} passes` : "Summary"),
    txt ? h("div", { class: "rw-insp-text", help: "timeline.inspector.summary" }, txt)
      : h("div", { class: "rw-insp-text rw-dim", help: "timeline.inspector.summary" }, raw ? "No raw prompt yet." : "No summary yet: write one in the Scene tab, or let Write prompts do it."),
    now);
}

// added 2026-11-06 v0.9.0: fill the inspector's "at the playhead" line (called by setPlayhead on every frame while
// playing, so the DOM is touched only when what it shows changes)
function nowAt(ctx, scene, local) {
  const tl = ctx.tl;
  const el = tl?.now;
  if (!el || !el.isConnected && tl.nowKey !== null) return;
  const p = ctx.p;
  const s = p.scenes.find(x => x.id === tl.nowScene);
  if (!s) return;
  if (scene.id !== s.id) {
    const key = "other|" + scene.id;
    if (key === tl.nowKey) return;
    tl.nowKey = key;
    el.replaceChildren(h("span", { class: "rw-dim" }, `The playhead is in scene ${String(sceneIndex(p, scene.id) + 1).padStart(2, "0")} · ${scene.title}.`));
    return;
  }
  const plan = tl.nowPlan;
  const k = plan && plan.passes.length > 1 ? Math.max(0, plan.passes.findIndex((ps, i) => local < ps.end || i === plan.passes.length - 1)) : -1;
  let shot = null, n = 0;
  for (let i = 0; i < s.shots.length; i++) if (s.shots[i].t <= local + 1e-6) { shot = s.shots[i]; n = i + 1; }
  // [OLD 2026-11-06 v0.9.0->v0.10.0] const line = captionAt(p, s, local);
  const line = captionAt(p, s, local, speechOf(ctx, s)); // added 2026-11-06 v0.10.0: timed to the speech
  const key = [k, shot?.id, shot?.text, shot?.camera, line?.id, line?.text].join("|");
  if (key === tl.nowKey) return;
  tl.nowKey = key;
  const clip = (x, len) => { x = String(x || "").replace(/\s+/g, " ").trim(); return x.length > len ? x.slice(0, len - 1).trimEnd() + "…" : x; };
  const rows = [];
  if (k >= 0) {
    const ps = plan.passes[k];
    const own = tl.nowTexts?.[k]?.summary?.trim();
    rows.push(h("div", null, h("b", null, `Pass ${k + 1} of ${plan.passes.length}`), h("span", { class: "mono rw-dim" }, ` ${fmtTime(ps.start, false)}–${fmtTime(ps.end, false)}`),
      own ? h("span", null, " · " + clip(own, 160)) : h("span", { class: "rw-dim" }, " · summary made from its shots")));
  }
  if (shot) rows.push(h("div", null, h("b", null, `Shot ${n}`), shot.camera ? h("span", { class: "rw-dim" }, ` · ${clip(shot.camera, 40)}`) : null, shot.text ? " · " + clip(shot.text, 180) : ""));
  if (line) rows.push(h("div", null, h("b", null, (findCast(p, line.speaker)?.name || "Line") + ": "), "“" + clip(line.text, 180) + "”"));
  if (!rows.length) rows.push(h("span", { class: "rw-dim" }, "Nothing written for this moment yet."));
  el.replaceChildren(h("div", { class: "rw-insp-label" }, "At the playhead"), ...rows);
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
  // [OLD 2026-11-03 v0.5.1->v0.6.0] if (s.start.mode === "tail") out.push(chip({ code: "TAIL", label: `${s.start.overlap_frames} f of previous`, kind: "vid", help: "scene.start.tail" }));
  // added 2026-11-03 v0.6.0: the overlap it really gets (capped by both scenes' lengths), or that it is re-anchored
  const si = sceneIndex(p, s.id);
  if (si > 0 && s.start.mode === "tail") {
    const f = tailOverlapFrames(p, si);
    out.push(f > 0 ? chip({ code: "TAIL", label: `${f} f of previous`, kind: "vid", help: "scene.start.tail" })
      : chip({ code: "TAIL", label: "last frame only (re-anchored)", kind: "vid", help: "scene.start.effective" }));
  }
  // added 2026-11-03 v0.5.0: the part of the soundtrack each pass covers
  if (sceneHasSong(p, s)) out.push(chip({ code: "SONG", label: "soundtrack · lips and cuts follow it", kind: "aud", help: "timeline.chip.song" }));
  // [OLD 2026-11-06 v0.8.0->v0.9.0] if (!out.length) out.push(h("span", { class: "rw-dim", help: "timeline.chip.none" }, "No references yet: drag assets from the bin onto the scene."));
  if (!out.length) out.push(h("span", { class: "rw-dim", help: "timeline.chip.none" }, "No references yet: add them in the Scene tab.")); // added 2026-11-06 v0.9.0: no asset bin
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
    /* [OLD 2026-11-03 v0.5.1->v0.6.0] by frame 0 of each scene: a continuing scene's frame 0 lies inside the scene before,
       so Next/Prev/Loop stayed there (review #7)
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
    [/OLD] */
    // added 2026-11-03 v0.6.0: every jump goes to where a scene first shows new content (its visible start)
    button({ icon: "prev", help: "timeline.transport.prev", variant: "ghost", onClick: () => {
      const q = ctx.p;
      const { visible } = sceneStarts(q);
      const s = sceneAt(q, q.ui.playhead);
      const i = sceneIndex(q, s.id);
      setPlayhead(ctx, q.ui.playhead - visible[s.id] > 0.25 || i === 0 ? visible[s.id] : visible[q.scenes[i - 1].id]);
    } }),
    button({ icon: ctx.eph.playing ? "pause" : "play", help: "timeline.transport.play", variant: "solid", onClick: () => togglePlay(ctx) }),
    button({ icon: "next", help: "timeline.transport.next", variant: "ghost", onClick: () => {
      const q = ctx.p;
      const { visible, total: end } = sceneStarts(q);
      const n = q.scenes[sceneIndex(q, sceneAt(q, q.ui.playhead).id) + 1];
      setPlayhead(ctx, n ? visible[n.id] : end);
    } }),
    button({ icon: "refresh", help: "timeline.transport.loop", variant: loop ? "accent-ghost" : "ghost", onClick: () => {
      const q = ctx.p;
      const s = sceneAt(q, q.ui.playhead);
      const { starts, visible } = sceneStarts(q);
      ctx.store.setEph({ loop: loop ? null : { in: visible[s.id], out: starts[s.id] + s.duration } });
    } }),
    timecode, h("span", { class: "mono rw-dim" }, "/ " + fmtTime(total)),
    loop && h("span", { class: "mono rw-loop-label", help: "timeline.transport.loop" }, `loop ${fmtTime(loop.in, false)}–${fmtTime(loop.out, false)}`),
    // added 2026-11-05 v0.8.0: following the playhead was paused by a scroll or drag; click to follow again
    ctx.eph.playing && ctx.play && ctx.play.follow === false && button({ label: "Follow", icon: "eye", small: true, variant: "accent-ghost", key: "tl-follow",
      help: "timeline.follow", extra: null, onClick: () => resumeFollow(ctx) }),
    h("span", { class: "rw-flex" }),
    // added 2026-11-12 v0.13.0: the monitor full screen (also: double-click it, or F)
    button({ icon: "expand", small: true, variant: ctx.monFull ? "accent-ghost" : "ghost", key: "tl-full", help: "timeline.fullscreen", onClick: () => toggleFull(ctx) }),
    // added 2026-11-06 v0.9.0: captions on/off, and the monitor's volume (the merge never reads either)
    button({ label: "CC", small: true, variant: p.ui.captions === false ? "ghost" : "accent-ghost", key: "tl-cc", help: "timeline.captions",
      onClick: () => { ctx.store.update(q => { q.ui.captions = q.ui.captions === false; }, { history: false, plan: false, autosave: false }); } }),
    volumeControl(ctx),
    h("span", { class: "rw-dim", help: "timeline.transport.cut" }, "cut " + fmtTime(assembledDuration(p))));
}

// added 2026-11-06 v0.9.0: mute button and volume slider of the monitor (ui.mon_muted, ui.mon_volume 0–1). Dragging the
// slider changes the sound at once without redrawing the tab (a redraw would take the slider from under the pointer).
function volumeControl(ctx) {
  const p = ctx.p;
  const muted = p.ui.mon_muted === true;
  const vol = uiNum(p, "mon_volume", 1, 0, 1);
  const set = (fn, render) => {
    ctx.store.update(fn, { history: false, plan: false, autosave: false, render });
    applyVolume(ctx);
    if (ctx.eph.playing) syncAudio(ctx, ctx.p.ui.playhead, true);
  };
  return h("span", { class: "rw-vol", help: "timeline.volume" },
    button({ icon: muted || vol === 0 ? "mute" : "speaker", small: true, variant: "ghost", key: "tl-mute", help: "timeline.volume.mute",
      ariaLabel: muted ? "Unmute" : "Mute",
      onClick: () => set(q => { q.ui.mon_muted = !muted; if (muted && !(uiNum(q, "mon_volume", 1, 0, 1) > 0)) q.ui.mon_volume = 0.5; }, true) }),
    slider({ value: Math.round((muted ? 0 : vol) * 100), min: 0, max: 100, step: 1, key: "tl-volume", help: "timeline.volume", format: v => v + "%",
      onInput: v => set(q => { q.ui.mon_volume = v / 100; q.ui.mon_muted = false; }, false),
      onChange: v => set(q => { q.ui.mon_volume = v / 100; q.ui.mon_muted = false; }, true) }));
}

// ---- Timeline lanes ----

function pickStep(z) {
  for (const s of [1, 2, 5, 10, 15, 30, 60, 120]) if (s * z >= 70) return s;
  return 300;
}

// [OLD 2026-11-03 v0.4.3->v0.5.0] function laneHead(label, ic, cls, help, extra) {
// [OLD 2026-11-03 v0.4.3->v0.5.0]   return h("div", { class: "rw-lane-head", help }, icon(ic, 13), h("span", { class: "rw-lane-name rw-c-" + cls }, label), h("span", { class: "rw-flex" }), extra);
// [OLD 2026-11-03 v0.4.3->v0.5.0] }
// onClick: added 2026-11-03 v0.5.0 (a soundtrack lane's head selects its track)
function laneHead(label, ic, cls, help, extra, onClick) {
  return h("div", { class: ["rw-lane-head", onClick && "click"], help, onClick }, icon(ic, 13), h("span", { class: "rw-lane-name rw-c-" + cls }, label), h("span", { class: "rw-flex" }), extra);
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
  // [OLD 2026-11-03 v0.4.3->v0.5.0] const width = Math.max(total * z + 160, 600);
  // added 2026-11-03 v0.5.0: a soundtrack can run past the last scene; the lanes show it all
  const trackEnd = Math.max(0, ...p.soundtrack.map(t => t.loop ? 0 : t.start + trackLengthOf(p, t)));
  const width = Math.max(Math.max(total, trackEnd) * z + 160, 600);
  // added 2026-11-03 v0.5.0: a continuing scene begins inside the one before (the repeated tail or last frame);
  // its block and lane bars start where it becomes visible
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const ov = (s, i) => (i > 0 ? overlapSeconds(s) : 0);
  // added 2026-11-03 v0.6.0: the real overlap (model.sceneOverlapAt: capped by the scene before, re-anchored tails
  // repeat one frame), read from the memoised timing in O(1)
  const { visible } = sceneStarts(p);
  const ov = s => visible[s.id] - starts[s.id];
  // added 2026-11-03 v0.6.0: only what is near the view is built (a long film has thousands of bars; building and
  // laying them all out cost 200+ ms per render at 300 scenes). Scrolling past the built part renders again.
  const vis = laneWindow(ctx, width);
  const near = (left, w = 0) => left + w >= vis.from && left <= vis.to;
  const lazyTiles = []; // waveform tiles, painted when they scroll into view
  const camNames = new Map((p.camera_presets || []).map(c => [c.text, c.name])); // added 2026-11-05 v0.8.0: camera lane labels
  const step = pickStep(z);
  const selectScene = id => () => ctx.actions.select(id);

  // Ruler
  /* [OLD 2026-11-02 v0.3.2->v0.3.3] press-and-drag scrubbed the playhead with window listeners; when ComfyUI swallowed the
     pointerup the listener stayed and the playhead followed the mouse over the node
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
  [/OLD] */
  // added 2026-11-02 v0.3.3: clicks and drags on the ruler are handled by lanesPointerdown (click = playhead, drag = pan)
  const ruler = h("div", { class: "rw-ruler-lane", style: { width: width + "px", "background-size": `${z}px 6px` }, help: "timeline.ruler" });
  // [OLD 2026-11-03 v0.4.3->v0.5.0] for (let t = 0; t <= total + step; t += step) {
  // [OLD 2026-11-03 v0.5.1->v0.6.0] for (let t = 0; t <= Math.max(total, trackEnd) + step; t += step) {
  for (let t = Math.max(0, Math.floor(vis.from / z / step) * step); t <= Math.min(Math.max(total, trackEnd) + step, vis.to / z + step); t += step) {
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
  // [OLD 2026-11-03 v0.4.3->v0.5.0] p.scenes.forEach((s, i) => scenesLane.append(sceneBlock(ctx, s, i, starts[s.id], z)));
  // [OLD 2026-11-03 v0.5.1->v0.6.0] p.scenes.forEach((s, i) => scenesLane.append(sceneBlock(ctx, s, i, starts[s.id], z, ov(s, i))));
  p.scenes.forEach((s, i) => { if (near(starts[s.id] * z, s.duration * z)) scenesLane.append(sceneBlock(ctx, s, i, starts[s.id], z, ov(s, i))); });
  p.scenes.forEach((s, i) => {
    if (i === 0) return;
    if (!near(visible[s.id] * z - 12, 24)) return; // added 2026-11-03 v0.6.0
    const mode = s.start.mode;
    const ic = mode === "fresh" ? "cut" : mode === "tail" ? "tail" : "link";
    scenesLane.append(h("button", {
      // [OLD 2026-11-03 v0.4.3->v0.5.0] type: "button", class: ["rw-join", "j-" + mode], style: { left: starts[s.id] * z - 11 + "px" }, help: "timeline.join." + mode,
      type: "button", class: ["rw-join", "j-" + mode], style: { left: (starts[s.id] + ov(s, i)) * z - 11 + "px" }, help: "timeline.join." + mode,
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
    const next = allLines[k + 1]?.x ?? Infinity;
    if (!near(it.x, Math.min(Math.max(28, next - it.x), 2000))) return; // added 2026-11-03 v0.6.0: far from the view
    const c = findCast(p, it.d.speaker);
    // [OLD 2026-11-03 v0.5.1->v0.6.0] const c = findCast(p, it.d.speaker);  (moved after the view check)
    // [OLD 2026-11-03 v0.5.1->v0.6.0] const next = allLines[k + 1]?.x ?? Infinity;  (moved up)
    dlg.append(h("span", {
      class: "rw-dlg", style: { left: it.x + "px", "max-width": Math.max(28, next - it.x - 4) + "px" }, help: "timeline.lane.dialogue", onClick: selectScene(it.s.id),
    /* [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are per clip now
    }, h("b", { class: "mono" }, (it.d.language || "").slice(0, 2).toUpperCase()), ` ${c?.name || "?"} (${c?.speaker || "S?"}) “${it.d.text}”`));
    [/OLD] */
    /* [OLD 2026-11-06 v0.9.0->v0.10.0] a cut-off line had no way to read it in full
    }, h("b", { class: "mono" }, (it.d.language || "").slice(0, 2).toUpperCase()), ` ${c?.name || "?"} “${it.d.text}”`));
    [/OLD] */
    // added 2026-11-06 v0.10.0: the whole line, who says it, how and when, in the tooltip (and right-click → Copy text)
      detail: `${c?.name || "?"}${it.d.delivery ? ` (${it.d.delivery})` : ""}: “${String(it.d.text || "").trim()}”\n${it.s.title} · ${fmtTime(it.d.t)}${it.d.language ? " · " + it.d.language : ""}`,
      dataset: { copy: String(it.d.text || "").trim() },
    }, h("b", { class: "mono" }, (it.d.language || "").slice(0, 2).toUpperCase()), ` ${c?.name || "?"} “${it.d.text}”`));
  });

  // [OLD 2026-11-03 v0.4.3->v0.5.0] for (const s of p.scenes) {
  // [OLD 2026-11-03 v0.4.3->v0.5.0]   const x0 = starts[s.id] * z;
  // [OLD 2026-11-03 v0.4.3->v0.5.0]   const w = s.duration * z;
  p.scenes.forEach((s, si) => {
    // added 2026-11-03 v0.5.0: x0 is the scene's frame 0 (times inside the scene count from it); bars that span the
    // scene start at vx0, where it becomes visible in the cut, and are w wide
    const x00 = starts[s.id] * z;
    const x0 = x00 + ov(s, si) * z;
    const w = (s.duration - ov(s, si)) * z;
    if (!near(x00, s.duration * z)) return; // added 2026-11-03 v0.6.0: far from the view
    // added 2026-11-03 v0.6.0: how it really starts (a re-anchored tail continues from the last frame only)
    const eff = si === 0 ? "fresh" : ov(s, si) * FPS > 1.5 ? "tail" : ov(s, si) > 0 ? "last_frame" : "fresh";
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
          // [OLD 2026-11-03 v0.4.3->v0.5.0] pics.append(diamond(x0 + t * z, "pic", "timeline.lane.keyframe." + r.role));
          // [OLD 2026-11-03 v0.4.3->v0.5.0] const left = Math.min(x0 + t * z + 8, x0 + w - 40);
          pics.append(diamond(x00 + t * z, "pic", "timeline.lane.keyframe." + r.role));
          const left = Math.min(x00 + t * z + 8, x0 + w - 40);
          picItems.push({ left, width: Math.max(34, Math.min(110, x0 + w - 3 - left)), cls: "pic", code: a.code, label: r.role === "keyframe" ? "@ " + fmtTime(r.time) : r.role.replace("_", " "), help: "timeline.lane.keyframe." + r.role, onClick: selectScene(s.id) });
        }
      } else if (a.kind === "video") {
        vids.append(bar({ left: x0 + 3, width: Math.min(w - 6, (a.duration || 2) * z), cls: "vid", code: a.code, label: `${a.name || ""} · ${a.category || r.role}`, help: "timeline.lane.vidRef", onClick: selectScene(s.id) }));
        if (r.soundtrack) audItems.push({ left: x0 + 3, width: Math.min(w - 6, (a.duration || 2) * z), cls: "aud soft", code: a.code, label: "soundtrack", help: "timeline.lane.soundtrack", onClick: selectScene(s.id) });
      } else {
        audItems.push({ left: x0 + 3, width: Math.min(w - 6, (a.duration || 2) * z), cls: "aud", code: a.code, label: `${a.name || ""} · ${ret}`, help: "timeline.lane.audRef", onClick: selectScene(s.id) });
      }
    }
    // [OLD 2026-11-03 v0.5.1->v0.6.0] if (s.start.mode === "last_frame") pics.append(diamond(x0, "pic", "timeline.lane.lastFrameAuto", true));
    if (eff === "last_frame") pics.append(diamond(x0, "pic", "timeline.lane.lastFrameAuto", true));
    // [OLD 2026-11-03 v0.4.3->v0.5.0] if (s.start.mode === "tail") vids.append(bar({ left: x0, width: (s.start.overlap_frames / FPS) * z, cls: "vid", label: "tail", hatch: true, help: "scene.start.tail" }));
    // added 2026-11-03 v0.5.0: the tail clip is the end of the scene before, so it sits under that scene's end
    // [OLD 2026-11-03 v0.5.1->v0.6.0] if (s.start.mode === "tail" && si > 0) vids.append(bar({ left: x00, width: ov(s, si) * z, cls: "vid", label: "tail", hatch: true, help: "scene.start.tail" }));
    if (eff === "tail") vids.append(bar({ left: x00, width: ov(s, si) * z, cls: "vid", label: "tail", hatch: true, help: "scene.start.tail" }));
    placeRows(picItems, 2).forEach(it => pics.append(bar({ ...it, rows: 2 })));
    placeRows(audItems, 2).forEach(it => auds.append(bar({ ...it, rows: 2 })));
    s.shots.forEach((sh, k) => {
      // [OLD 2026-11-05 v0.7.0->v0.8.0] if (!sh.camera) return;
      if (!sh.camera && !sh.framing) return; // added 2026-11-05 v0.8.0: a framing alone is shown too
      const end = s.shots[k + 1]?.t ?? s.duration;
      // [OLD 2026-11-03 v0.4.3->v0.5.0] cam.append(h("span", { class: "rw-cam", style: { left: x0 + sh.t * z + 3 + "px", "max-width": Math.max(24, (end - sh.t) * z - 6) + "px" }, help: "timeline.lane.camera", onClick: selectScene(s.id) }, sh.camera));
      const from = Math.max(sh.t, ov(s, si)); // added 2026-11-03 v0.5.0
      // [OLD 2026-11-05 v0.7.0->v0.8.0] cam.append(h("span", { class: "rw-cam", style: { left: x00 + from * z + 3 + "px", "max-width": Math.max(24, (end - from) * z - 6) + "px" }, help: "timeline.lane.camera", onClick: selectScene(s.id) }, sh.camera));
      // added 2026-11-05 v0.8.0: framing · move (the preset's name for a preset's words) · amplitude and speed
      const word = camNames.get(sh.camera) || sh.camera || "";
      const label = [sh.framing && sh.framing[0].toUpperCase() + sh.framing.slice(1), word, [sh.camera_amp, sh.camera_speed].filter(Boolean).join(" ")].filter(Boolean).join(" · ");
      // [OLD 2026-11-06 v0.9.0->v0.10.0] cam.append(h("span", { class: "rw-cam", style: { left: x00 + from * z + 3 + "px", "max-width": Math.max(24, (end - from) * z - 6) + "px" }, help: "timeline.lane.camera", title: label, onClick: selectScene(s.id) }, label));
      // added 2026-11-06 v0.10.0: the whole camera direction in the tooltip: the label, the words H3 gets and the shot
      const camDetail = [`Shot ${k + 1}: ${label}`, sh.camera && sh.camera !== word ? `“${sh.camera}”` : "", sh.text ? sh.text.trim() : "", `${s.title} · ${fmtTime(sh.t)}–${fmtTime(end)}`].filter(Boolean).join("\n");
      cam.append(h("span", { class: "rw-cam", style: { left: x00 + from * z + 3 + "px", "max-width": Math.max(24, (end - from) * z - 6) + "px" }, help: "timeline.lane.camera", detail: camDetail,
        dataset: { copy: [label, sh.camera && sh.camera !== word ? sh.camera : ""].filter(Boolean).join(" · ") }, onClick: selectScene(s.id) }, label));
    });
    const own = effectiveLoras(p, s).filter(l => l.source !== "global");
    if (own.length) {
      const src = own.some(l => l.source === "override") ? "override" : own.some(l => l.source === "scene") ? "scene" : "cast";
      lora.append(h("div", {
        class: ["rw-bar lora", src === "override" ? "over" : src === "cast" && "cast"], help: "timeline.lane.lora." + src, onClick: selectScene(s.id),
        style: { left: x0 + 2 + "px", width: Math.max(6, w - 4) + "px", top: "20px", height: "17px" },
      }, own.map(l => `${l.name.replace(/\.safetensors$/, "")} ${Number(l.strength).toFixed(2)}${l.source === "override" ? "*" : ""}`).join(" · ")));
    }
  // [OLD 2026-11-03 v0.4.3->v0.5.0] }
  });
  const globals = p.global.loras.filter(l => l.enabled);
  if (globals.length) {
    lora.append(h("div", { class: "rw-bar lora global", help: "timeline.lane.lora.global", style: { left: "0px", width: total * z + "px", top: "4px", height: "12px" } },
      globals.map(l => `${l.name.replace(/\.safetensors$/, "")} ${Number(l.strength).toFixed(2)}`).join(" · ") + " · global"));
  }

  const lanes = [
    ["Scenes", "film", "text", "timeline.lane.scenes", scenesLane, "scenes", h("span", { class: "mono rw-dim" }, `${p.scenes.length} / ∞`)],
    // added 2026-11-03 v0.5.0: soundtrack tracks under the scenes, then a lane to add one
    // [OLD 2026-11-03 v0.5.1->v0.6.0] ...trackLanes(ctx, z, width, { trackDrag, scaleOf: () => scaleOf(ctx), zoom: () => zoomOf(ctx) })
    // window, lazy: added 2026-11-03 v0.6.0 (waveform tiles near the view only, painted when seen)
    ...trackLanes(ctx, z, width, { trackDrag, scaleOf: () => scaleOf(ctx), zoom: () => zoomOf(ctx), window: vis, lazy: c => lazyTiles.push(c) })
      .map(l => [l.label, l.ic, l.cls, l.help, l.body, l.kind.filter(Boolean).join(" "), l.extra, l.onHead]),
    ["Pictures", "image", "pic", "timeline.lane.pictures", pics, "two"],
    ["Video refs", "video", "vid", "timeline.lane.video", vids, ""],
    ["Audio refs", "audio", "aud", "timeline.lane.audio", auds, "two"],
    ["Dialogue", "dialogue", "dlg", "timeline.lane.dialogueLane", dlg, ""],
    ["Camera", "camera", "cam", "timeline.lane.cameraLane", cam, ""],
    ["LoRAs", "lora", "lora", "timeline.lane.loras", lora, "two"],
  ];

  const playhead = h("div", { class: "rw-playhead", style: { left: HEAD_W + p.ui.playhead * z + "px" } });
  // [OLD 2026-11-02 v0.3.2->v0.3.3] const playheadLabel = h("span", { class: "rw-playhead-label mono" }, fmtTime(p.ui.playhead));
  // added 2026-11-02 v0.3.3: drag the playhead's label to scrub
  const playheadLabel = h("span", { class: "rw-playhead-label mono", help: "timeline.playhead", onPointerdown: e => {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    const rulerLeft = () => (ctx.root.querySelector(".rw-ruler-lane") || ruler).getBoundingClientRect().left;
    trackDrag(ev => setPlayhead(ctx, (ev.clientX - rulerLeft()) / scaleOf(ctx) / zoomOf(ctx)));
  } }, fmtTime(p.ui.playhead));
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
  /* [OLD 2026-11-02 v0.3.2->v0.3.3] plain wheel only scrolled up and down, so a long film could not be scrolled sideways with the mouse
  return h("div", { class: "rw-lanes", dataset: { scroll: "lanes" }, wheel: e => {
    if (e.altKey) { e.preventDefault(); setZoom(ctx, zoomOf(ctx) * (e.deltaY < 0 ? 1.15 : 1 / 1.15)); }
  } },
  [/OLD] */
  // added 2026-11-02 v0.3.3: wheel scrolls sideways when the film is wider than the lanes; Shift + wheel scrolls
  // up and down; Alt + wheel zooms. Click = playhead, drag = pan (see lanesPointerdown).
  // [OLD 2026-11-03 v0.5.1->v0.6.0] return h("div", { class: "rw-lanes", dataset: { scroll: "lanes" }, onPointerdown: e => lanesPointerdown(ctx, e), wheel: e => {
  // added 2026-11-03 v0.6.0: onScroll renders again when the view leaves the part that was built
  /* [OLD 2026-11-05 v0.7.0->v0.8.0] no follow-playback: a scroll or sideways wheel did not pause it
  const lanesEl = h("div", { class: "rw-lanes", dataset: { scroll: "lanes" }, onPointerdown: e => lanesPointerdown(ctx, e), onScroll: e => lanesScroll(ctx, e.currentTarget), wheel: e => {
    if (e.altKey) { e.preventDefault(); setZoom(ctx, zoomOf(ctx) * (e.deltaY < 0 ? 1.15 : 1 / 1.15)); return; }
    const el = ctx.root.querySelector(".rw-lanes");
    if (!el) return;
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? el.clientWidth : 1;
    if (e.shiftKey) {
      if (el.scrollHeight > el.clientHeight + 1) { e.preventDefault(); el.scrollTop += (e.deltaY || e.deltaX) * unit; }
      return;
    }
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && el.scrollWidth > el.clientWidth + 1) { e.preventDefault(); el.scrollLeft += e.deltaY * unit; }
  } },
  [/OLD] */
  // added 2026-11-05 v0.8.0: a manual scroll (scrollbar or sideways wheel) pauses following the playhead
  const lanesEl = h("div", { class: "rw-lanes", dataset: { scroll: "lanes" }, onPointerdown: e => lanesPointerdown(ctx, e),
    // a lanes element a render replaced still gets the scroll event of its last scroll (and reads 0 when detached):
    // it rebuilt the lanes on every frame while the view followed the playhead, so only the lanes on the page count
    onScroll: e => { if (!e.currentTarget.isConnected) return; followScrolled(ctx, e.currentTarget); lanesScroll(ctx, e.currentTarget); }, wheel: e => {
      if (e.altKey) { e.preventDefault(); setZoom(ctx, zoomOf(ctx) * (e.deltaY < 0 ? 1.15 : 1 / 1.15)); return; }
      const el = ctx.root.querySelector(".rw-lanes");
      if (!el) return;
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? el.clientWidth : 1;
      if (e.shiftKey) {
        if (el.scrollHeight > el.clientHeight + 1) { e.preventDefault(); el.scrollTop += (e.deltaY || e.deltaX) * unit; }
        return;
      }
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && el.scrollWidth > el.clientWidth + 1) { e.preventDefault(); pauseFollow(ctx); el.scrollLeft += e.deltaY * unit; }
      else if (Math.abs(e.deltaX) > 0) pauseFollow(ctx);
    } },
  h("div", { class: "rw-lanes-inner", style: { width: HEAD_W + width + "px" } },
    h("div", { class: "rw-lane ruler" }, h("div", { class: "rw-lane-head mono rw-dim", help: "timeline.ruler" }, "24 fps"), ruler),
    // [OLD 2026-11-03 v0.4.3->v0.5.0] lanes.map(([label, ic, cls, help, el, kind, extra]) => h("div", { class: ["rw-lane", kind] }, laneHead(label, ic, cls, help, extra), el)),
    lanes.map(([label, ic, cls, help, el, kind, extra, onHead]) => h("div", { class: ["rw-lane", kind] }, laneHead(label, ic, cls, help, extra, onHead), el)),
    playhead));
  // added 2026-11-03 v0.6.0: waveform tiles are painted when they come near the view (one observer per render)
  ctx.tl.io?.disconnect();
  ctx.tl.io = null;
  if (lazyTiles.length) {
    if (typeof IntersectionObserver === "function") {
      const io = ctx.tl.io = new IntersectionObserver(entries => {
        for (const en of entries) if (en.isIntersecting) { io.unobserve(en.target); en.target.__paint?.(); }
      }, { root: lanesEl, rootMargin: "0px 400px" });
      for (const c of lazyTiles) io.observe(c);
    } else for (const c of lazyTiles) c.__paint?.();
  }
  return lanesEl;
}

// added 2026-11-03 v0.6.0: the part of the lanes (lane pixels, 0 = film start) that a render builds: the view and
// one and a half views on either side, read from the lanes being replaced (the editor restores their scroll).
/* [OLD 2026-11-03 v0.6.0 review] used the old scroll position as it was: after a big zoom-out it lay past the end of
   the new lanes, so nothing near the view was built and the restored scrollLeft (clamped to the new end, no scroll
   event) showed empty lanes
function laneWindow(ctx, width) {
  const el = ctx.root.querySelector(".rw-lanes");
  const vw = Math.max(400, (el?.clientWidth || ctx.root.clientWidth || 1600) - HEAD_W);
  const sl = el ? el.scrollLeft : 0;
  const win = { from: sl - vw * 1.5, to: sl + vw * 2.5, width, vw };
  ctx.tl = ctx.tl || {};
  ctx.tl.window = win;
  return win;
}
[/OLD] */
// added 2026-11-03 v0.6.0 review: the old scroll position is clamped to the new lanes' end first (where the browser
// will put it when the editor restores it); `sl` is kept so afterRender can check what the view really shows
function laneWindow(ctx, width) {
  const el = ctx.root.querySelector(".rw-lanes");
  const vw = Math.max(400, (el?.clientWidth || ctx.root.clientWidth || 1600) - HEAD_W);
  const max = el ? Math.max(0, HEAD_W + width - el.clientWidth) : 0;
  const sl = el ? Math.max(0, Math.min(el.scrollLeft, max)) : 0;
  const win = { from: sl - vw * 1.5, to: sl + vw * 2.5, width, vw, sl };
  ctx.tl = ctx.tl || {};
  ctx.tl.window = win;
  return win;
}

// added 2026-11-03 v0.6.0 review: after the editor restored the lanes' scroll: when the view is not where the window
// was built for (more than a few pixels off), build again once for the real position
export function afterRender(ctx) {
  const el = ctx.root.querySelector(".rw-lanes");
  const win = ctx.tl?.window;
  if (!el || !win || typeof win.sl !== "number") return;
  if (Math.abs(el.scrollLeft - win.sl) <= 4) return;
  win.sl = el.scrollLeft; // once per render
  lanesScroll(ctx, el);
}

// Render again (next frame) when the view gets close to the edge of what was built.
function lanesScroll(ctx, el) {
  const win = ctx.tl?.window;
  if (!win) return;
  const sl = el.scrollLeft, vw = Math.max(400, el.clientWidth - HEAD_W);
  const short = (sl - vw * 0.5 < win.from && win.from > 0) || (sl + vw * 1.5 > win.to && win.to < win.width);
  if (short && !ctx.tl.rebuild) {
    ctx.tl.rebuild = requestAnimationFrame(() => { ctx.tl.rebuild = 0; ctx.store.notify(); });
  }
}

// added 2026-11-02 v0.3.3: screen pixels per editor pixel. ComfyUI scales the whole node with the canvas zoom, so
// mouse distances must be divided by this before they become seconds.
function scaleOf(ctx) {
  const r = ctx.root.getBoundingClientRect();
  return (r.width / (ctx.root.offsetWidth || r.width)) || 1;
}

// added 2026-11-02 v0.3.3: follow the pointer while the button is held. Capture-phase window listeners still see the
// release when ComfyUI stops it on the way up, and a move with no button pressed ends the drag, so the
// tracking can never outlive the press.
function trackDrag(onMove, onEnd) {
  let done = false;
  const stop = ev => {
    if (done) return;
    done = true;
    window.removeEventListener("pointermove", move, true);
    window.removeEventListener("pointerup", stop, true);
    window.removeEventListener("pointercancel", stop, true);
    window.removeEventListener("blur", stop);
    onEnd?.(ev);
  };
  const move = ev => { if (!(ev.buttons & 1)) stop(ev); else onMove(ev); };
  window.addEventListener("pointermove", move, true);
  window.addEventListener("pointerup", stop, true);
  window.addEventListener("pointercancel", stop, true);
  window.addEventListener("blur", stop);
}

// added 2026-11-02 v0.3.3: a press on the lanes. A drag pans the timeline (the playhead stays where it is); a click
// on the ruler or on an empty part of a lane moves the playhead there. Clicks on scenes and chips keep their own action.
// [OLD 2026-11-03 v0.4.3->v0.5.0] const LANE_CONTROLS = ".rw-lane-head, button, input, select, textarea, a, .rw-resize, .rw-shot-tick, .rw-marker, .rw-playhead-label";
const LANE_CONTROLS = ".rw-lane-head, button, input, select, textarea, a, .rw-resize, .rw-shot-tick, .rw-marker, .rw-playhead-label, .rw-track-clip";
function lanesPointerdown(ctx, e) {
  if (e.button !== 0 || !(e.target instanceof Element) || e.target.closest(LANE_CONTROLS)) return;
  e.rwOwned = true; // the editor root stops it there, so Nodes 2.0 doesn't start dragging the whole node
  const t = e.target;
  const empty = !!t.closest(".rw-ruler-lane") || t.matches(".rw-lane-body, .rw-lane, .rw-lanes-inner, .rw-lanes");
  const el0 = e.currentTarget;
  const x0 = e.clientX, y0 = e.clientY, sl0 = el0.scrollLeft, st0 = el0.scrollTop;
  const sc = scaleOf(ctx);
  let panning = false;
  trackDrag(ev => {
    if (!panning && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 4) return;
    // [OLD 2026-11-05 v0.7.0->v0.8.0] if (!panning) { panning = true; ctx.root.classList.add("rw-panning"); }
    if (!panning) { panning = true; ctx.root.classList.add("rw-panning"); pauseFollow(ctx); } // added 2026-11-05 v0.8.0: a drag pauses following
    const el = ctx.root.querySelector(".rw-lanes") || el0; // a re-render may have replaced the lanes
    el.scrollLeft = sl0 - (ev.clientX - x0) / sc;
    el.scrollTop = st0 - (ev.clientY - y0) / sc;
  }, ev => {
    ctx.root.classList.remove("rw-panning");
    if (panning) {
      // the release after a pan is not a click on whatever is under the pointer
      // (nor a double-click: two quick pans would otherwise open the scene under the pointer)
      const kill = ce => { ce.stopPropagation(); ce.preventDefault(); };
      for (const type of ["click", "dblclick"]) window.addEventListener(type, kill, { capture: true, once: true });
      setTimeout(() => { for (const type of ["click", "dblclick"]) window.removeEventListener(type, kill, true); }, 0);
    } else if (empty && ev?.type === "pointerup") {
      const ruler = ctx.root.querySelector(".rw-ruler-lane");
      if (ruler) setPlayhead(ctx, (ev.clientX - ruler.getBoundingClientRect().left) / sc / zoomOf(ctx));
    }
  });
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
    // added 2026-11-06 v0.9.0: move it to a group (the first 12), out of its group, or into a new one
    { sep: true },
    { head: "Move to group" },
    ...ctx.p.asset_groups.slice(0, 12).map(g => ({ label: g.name.trim() || "Unnamed group", icon: "folder", help: "assets.group.pick", disabled: a.group === g.id,
      onClick: () => ctx.actions.edit(q => { const x = q.assets.find(y => y.id === a.id); if (x) x.group = g.id; }, { label: `Move ${a.code} to ${g.name || "a group"}` }) })),
    a.group && { label: "No group", icon: "close", help: "assets.group.pick",
      onClick: () => ctx.actions.edit(q => { const x = q.assets.find(y => y.id === a.id); if (x) x.group = ""; }, { label: `Take ${a.code} out of its group` }) },
    { label: "New group…", icon: "plus", help: "assets.group.add", onClick: () => { const id = addGroup(ctx, "New group", a.id); ctx.store.setEph({ editGroup: id, selectedAsset: a.id }); ctx.actions.setTab("assets"); } },
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
    /* [OLD 2026-11-03 v0.5.1->v0.6.0] the count was read after the delete, so deleting one of two scenes said "Scene reset."
    { label: p.scenes.length <= 1 ? "Reset scene" : "Delete scene", icon: "trash", hint: "Del", help: "timeline.delete", danger: true,
      onClick: async () => { if (await ctx.actions.deleteScene(s.id)) ctx.actions.toast(p.scenes.length <= 1 ? "Scene reset." : `Deleted ${s.title}.`, "info"); } },
    [/OLD] */
    { label: p.scenes.length <= 1 ? "Reset scene" : "Delete scene", icon: "trash", hint: "Del", help: "timeline.delete", danger: true,
      onClick: async () => {
        const last = ctx.p.scenes.length <= 1; // added 2026-11-03 v0.6.0: before the delete
        if (await ctx.actions.deleteScene(s.id)) ctx.actions.toast(last ? "Scene reset." : `Deleted ${s.title}.`, "info");
      } },
  ];
}

// [OLD 2026-11-03 v0.4.3->v0.5.0] function sceneBlock(ctx, s, i, start, z) {
// ov: added 2026-11-03 v0.5.0, the seconds at the scene's start that repeat the scene before. The block starts after
// them; everything inside it is placed at (t - ov) * z.
function sceneBlock(ctx, s, i, start, z, ov = 0) {
  const p = ctx.p;
  const status = ctx.statusOf(s.id);
  const prog = ctx.eph.progress[s.id];
  const plan = ctx.planFor(s.id);
  const est = estimatePasses(s.duration, p.global.long);
  const take = ctx.starredTake(s.id);
  const thumb = take?.files?.first ? viewURL(take.files.first) : storyboardImage(ctx, s);
  const selected = s.id === ctx.scene.id;
  // [OLD 2026-11-03 v0.4.3->v0.5.0] const w = s.duration * z - 2;
  const w = (s.duration - ov) * z - 2;
  const block = h("div", {
    class: ["rw-scene", selected && "on", "st-" + status, s.lock && "locked"],
    // [OLD 2026-11-03 v0.4.3->v0.5.0] style: { left: start * z + 1 + "px", width: w + "px", "--tint": s.color || null },
    style: { left: (start + ov) * z + 1 + "px", width: w + "px", "--tint": s.color || null },
    help: "timeline.scene",
    dataset: { sid: s.id }, // added 2026-11-03 v0.6.0: found again by onProgress and the stale preview
    // [OLD 2026-11-03 v0.4.3->v0.5.0] onClick: () => ctx.actions.select(s.id),
    // [OLD 2026-11-03 v0.5.1->v0.6.0] onClick: () => { if (ctx.eph.selectedTrack) ctx.store.setEph({ selectedTrack: null }, false); ctx.actions.select(s.id); },
    // added 2026-11-03 v0.6.0: a click on a scene closes the marker inspector too (the scene is what Delete removes then)
    onClick: () => {
      if (ctx.eph.selectedTrack || ctx.eph.selectedMarker) ctx.store.setEph({ selectedTrack: null, selectedMarker: null }, false);
      ctx.actions.select(s.id);
    },
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
      // [OLD 2026-11-02 v0.3.2->v0.3.3] ignored ComfyUI's canvas zoom: const t = Math.max(0, Math.min(s.duration, (e.clientX - rect.left) / z));
      // [OLD 2026-11-03 v0.4.3->v0.5.0] const t = Math.max(0, Math.min(s.duration, (e.clientX - rect.left) / scaleOf(ctx) / z));
      const t = Math.max(0, Math.min(s.duration, ov + (e.clientX - rect.left) / scaleOf(ctx) / z));
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
  // added 2026-11-05 v0.7.0: the frame that is at each time, from the starred take's filmstrip (fetched once per video
  // file; the first frame above stays underneath until it is there, and when it fails), and marks for the join into
  // the scene and its fades
  const film = take?.files?.video ? filmstripOf(ctx, take) : null;
  if (film) filmCells(ctx, strip, film, (start + ov) * z + 1, w, ov, z);
  cutMarks(ctx, strip, s, i, z, w);
  /* [OLD 2026-11-03 v0.4.3->v0.5.0] the tail hatch sat inside the block; the block now starts after the repeated tail
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
  [/OLD] */
  // added 2026-11-03 v0.5.0: positions inside the block count from where it becomes visible (ov)
  const passes = plan?.passes;
  if (passes?.length > 1) {
    for (const ps of passes.slice(1)) {
      strip.append(h("span", { class: ["rw-pass-tick", ps.seam_before === "cut" ? "cut" : "overlap"], style: { left: (ps.start - ov) * z + "px" }, help: "timeline.scene.seam." + (ps.seam_before === "cut" ? "cut" : "overlap") }));
      if (ps.seam_before !== "cut" && ps.overlap_frames) strip.append(h("span", { class: "rw-hatch thin", style: { left: (ps.start - ov) * z + "px", width: (ps.overlap_frames / FPS) * z + "px" } }));
    }
  } else if (est.count > 1) {
    const span = s.duration / est.count;
    for (let k = 1; k < est.count; k++) strip.append(h("span", { class: "rw-pass-tick overlap", style: { left: (k * span - ov) * z + "px" }, help: "timeline.scene.seam.overlap" }));
  }
  for (const sh of s.shots) {
    if (sh.t <= ov) continue;
    strip.append(shotTick(ctx, s, sh, z, ov));
  }
  block.append(h("span", { class: "rw-scene-dur mono" }, `${s.duration.toFixed(2)}s · ${framesOf(s.duration)}f`));
  /* [OLD 2026-11-03 v0.5.1->v0.6.0] built on every render (now also updated in place by onProgress); "skipped" counted as running
  if (prog && !["done", "cached", "error"].includes(prog.phase)) {
    const passPart = prog.passes ? (prog.pass - 1 + (prog.steps ? prog.step / prog.steps : 0)) / prog.passes : 0;
    block.append(h("div", { class: "rw-scene-prog", help: "timeline.scene.progress" }, h("span", { style: { width: Math.round(passPart * 100) + "%" } })),
      h("span", { class: "rw-scene-prog-label mono" }, `${prog.phase} ${prog.pass}/${prog.passes}${prog.steps ? " · " + prog.step + "/" + prog.steps : ""}`));
  }
  [/OLD] */
  if (prog && !ctx.isFinal(prog.phase)) block.append(...progressParts(prog)); // added 2026-11-03 v0.6.0
  // [OLD 2026-11-03 v0.4.3->v0.5.0] block.append(resizeHandle(ctx, s, z, block));
  block.append(resizeHandle(ctx, s, z, block, i));
  return block;
}

// added 2026-11-03 v0.6.0: a scene's progress bar and label (sceneBlock; onProgress updates them in place)
function progressParts(prog) {
  const passPart = prog.passes ? (Math.max(1, prog.pass || 1) - 1 + (prog.steps ? prog.step / prog.steps : 0)) / prog.passes : 0;
  return [
    h("div", { class: "rw-scene-prog", help: "timeline.scene.progress" }, h("span", { style: { width: Math.round(Math.min(1, passPart) * 100) + "%" } })),
    h("span", { class: "rw-scene-prog-label mono" }, `${prog.phase} ${prog.pass}/${prog.passes}${prog.steps ? " · " + prog.step + "/" + prog.steps : ""}`),
  ];
}

// ---- filmstrip and cut marks (added 2026-11-05 v0.7.0) ----
// The scene strip shows the frame that is at each time: cells of the sprite's tile aspect, each showing the tile
// nearest the cell's middle time (scene time = where the block starts in the scene + x / zoom). The sprite comes from
// GET /reelwright/filmstrip for the starred take's video. It is asked for only when a block that needs it is built (the
// lane window builds the blocks near the view), at most FILM_LIVE at a time, and kept per editor and video file. When
// the takes change, an entry is forgotten if its take is no longer starred or was rendered again (`created` differs),
// and a failed one is tried again. Failures are quiet: the strip keeps the take's first frame (today's image).
const FILM_H = 54; // tile height asked for, in pixels
const STRIP_H = 44; // height of .rw-scene-strip: a 70 px block, 2 px of border and the 24 px head
const FILM_LIVE = 3; // filmstrip requests at a time
const films = new WeakMap(); // ctx -> { map: Map(key -> entry), takes, queue, live, timer }
const filmKey = take => `${take.files.video}|${take.created ?? ""}`;

function filmState(ctx) {
  let st = films.get(ctx);
  if (!st) films.set(ctx, st = { map: new Map(), takes: undefined, queue: [], live: 0, timer: 0 });
  // takes not read yet (null while a new folder's list is on its way) forget nothing
  if (ctx.eph.takes && st.takes !== ctx.eph.takes) {
    st.takes = ctx.eph.takes;
    const keep = new Set();
    for (const t of Object.values(st.takes?.scenes || {})) {
      const x = t?.takes?.find(k => k.id === t.starred);
      if (x?.files?.video) keep.add(filmKey(x));
    }
    for (const [k, e] of st.map) if (!keep.has(k) || e.state === "error") st.map.delete(k);
    st.queue = st.queue.filter(e => st.map.get(e.key) === e);
  }
  return st;
}

// The filmstrip entry of a take once its sprite has loaded, else null (and it is asked for when it is not yet).
function filmstripOf(ctx, take) {
  const st = filmState(ctx);
  const key = filmKey(take);
  let e = st.map.get(key);
  if (!e) {
    e = { key, file: take.files.video, version: String(take.created ?? ""), state: "queued" };
    st.map.set(key, e);
    st.queue.push(e);
    filmPump(ctx, st);
  }
  return e.state === "ok" ? e : null;
}

function filmPump(ctx, st) {
  while (st.live < FILM_LIVE && st.queue.length) {
    const e = st.queue.shift();
    if (st.map.get(e.key) !== e) continue; // forgotten while it waited
    st.live++;
    e.state = "loading";
    filmLoad(ctx, st, e).finally(() => { st.live--; filmPump(ctx, st); });
  }
}

async function filmLoad(ctx, st, e) {
  try {
    const r = await rw.filmstrip(e.file, FILM_H);
    const count = Math.trunc(Number(r?.count)), tw = Number(r?.tile_w), th = Number(r?.tile_h), interval = Number(r?.interval);
    if (!r?.file || !(count > 0) || !(tw > 0) || !(th > 0) || !(interval > 0)) throw new Error("no filmstrip");
    const url = viewURL(r.file, "output", e.version);
    if (!url) throw new Error("no filmstrip url");
    // the sprite is loaded before the strip uses it, so cells never show up empty
    await new Promise((ok, fail) => { const img = new Image(); img.onload = ok; img.onerror = fail; img.src = url; });
    Object.assign(e, { state: "ok", url, count, aspect: tw / th, interval, duration: Number(r.duration) > 0 ? Number(r.duration) : count * interval });
  } catch {
    e.state = "error";
    return;
  }
  if (st.map.get(e.key) !== e || st.timer) return;
  st.timer = setTimeout(() => { // one render for the sprites that arrive together
    st.timer = 0;
    if (ctx.root.isConnected && ctx.p.ui.tab === "timeline") ctx.store.notify();
  }, 40);
}

// Cells of the filmstrip in a scene's strip; only those near the view (ctx.tl.window) are built.
function filmCells(ctx, strip, film, blockLeft, w, ov, z) {
  const cw = Math.max(8, Math.round(STRIP_H * film.aspect));
  const n = Math.ceil(Math.max(0, w) / cw);
  const win = ctx.tl?.window;
  const k0 = win ? Math.max(0, Math.floor((win.from - blockLeft) / cw)) : 0;
  const k1 = win ? Math.min(n - 1, Math.ceil((win.to - blockLeft) / cw)) : n - 1;
  const last = film.count - 1;
  strip.classList.add("film");
  strip.dataset.help = "timeline.scene.film";
  strip.style.setProperty("--film", `url("${film.url}")`);
  strip.style.setProperty("--film-size", `${film.count * 100}% 100%`);
  for (let k = k0; k <= k1; k++) {
    const t = ov + ((k + 0.5) * cw) / z; // scene time at the middle of the cell
    const idx = Math.max(0, Math.min(last, Math.round(t / film.interval)));
    strip.append(h("span", { class: ["rw-film-cell", t > film.duration + 0.5 / FPS && "past"], dataset: { tile: String(idx) },
      style: { left: k * cw + "px", width: cw + "px", "background-position": `${last ? (idx / last) * 100 : 0}% 0` } }));
  }
}

// Marks on a scene block: the transition into it (a tag and its length at the left edge; under a soundtrack it is a
// dip) and its fades (a ramp and a gradient towards the fade colour at either edge).
function cutMarks(ctx, strip, s, i, z, w) {
  const j = joinOf(ctx.p, i, s);
  const m = j.m;
  if (j.kind === "transition") {
    const dip = j.asDip || m.transition === "dip";
    const dir = DIRECTED.has(m.transition) ? DIRECTIONS.find(d => d.value === m.direction)?.label || "" : "";
    const name = j.asDip ? "dip" : (TRANSITION[m.transition]?.short || m.transition) + (dir ? " " + dir : "");
    const help = j.asDip ? "timeline.scene.transitionDip" : "timeline.scene.transition";
    strip.append(
      h("span", { class: ["rw-cut-tr", dip && "dip"], style: { width: Math.min(Math.max(0, w), Math.max(4, (m.frames / FPS) * z)) + "px", "--fc": m.color }, help }),
      h("span", { class: "rw-cut-tag mono", help, "aria-label": `${transitionLabel(m)}, ${m.frames} frames` }, dip && h("i", { style: { background: m.color } }), `${name} ${m.frames}f`));
  }
  for (const [which, cls, help] of [["fade_in", "in", "timeline.scene.fadeIn"], ["fade_out", "out", "timeline.scene.fadeOut"]]) {
    const f = m[which];
    if (!(f.frames > 0)) continue;
    strip.append(h("span", { class: ["rw-cut-fade", cls], style: { width: Math.min(Math.max(0, w), Math.max(5, (f.frames / FPS) * z)) + "px", "--fc": f.color }, help }));
  }
}

// added 2026-11-03 v0.6.0: a render step (reelwright.progress) updates the scene's progress bar in place; the editor
// renders the whole tab only when a scene starts or ends or its phase or pass changes (it took 230+ ms at 300 scenes)
export function onProgress(ctx, d) {
  if (!d?.scene_id || ctx.isFinal(d.phase)) return;
  const block = ctx.root.querySelector(`.rw-scene[data-sid="${CSS.escape(d.scene_id)}"]`);
  if (!block) return; // far from the view, or not on screen
  const [bar, label] = progressParts(d);
  const oldBar = block.querySelector(":scope > .rw-scene-prog"), oldLabel = block.querySelector(":scope > .rw-scene-prog-label");
  if (oldBar && oldLabel) {
    oldBar.firstChild.style.width = bar.firstChild.style.width;
    oldLabel.textContent = label.textContent;
  } else {
    oldBar?.remove();
    oldLabel?.remove();
    block.querySelector(":scope > .rw-resize")?.before(bar, label);
  }
}

// added 2026-11-03 v0.6.0: a shot or resize drag that always ends. It follows the pointer with window listeners
// (trackDrag) instead of pointer capture on the element: a render in the middle of the drag (the plan or the autosave
// state arriving) replaces the element, which used to drop the capture and leave the drag dead. It ends on pointerup
// (seen in the capture phase even when ComfyUI stops it), on pointercancel, when the window loses focus, or on a move
// with no button pressed (a pointerup that never came). onEnd(commit): false after pointercancel (the drag is dropped).
function captureDrag(onMove, onEnd) {
  trackDrag(onMove, ev => onEnd(ev?.type !== "pointercancel"));
}

// added 2026-11-03 v0.6.0: the element on screen now: `el` itself, or what a render put in its place (`sel`)
function liveEl(ctx, el, sel) {
  return el.isConnected ? el : ctx.root.querySelector(sel) || el;
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] a lost pointerup left the drag running; the tick could be dragged into the hidden
   tail (trimmed from the cut); no beat snap, no history label
// [OLD 2026-11-03 v0.4.3->v0.5.0] function shotTick(ctx, s, sh, z) {
// [OLD 2026-11-03 v0.4.3->v0.5.0]   const tick = h("span", { class: "rw-shot-tick", style: { left: sh.t * z + "px" }, help: "timeline.scene.shot", title: sh.camera || sh.text });
function shotTick(ctx, s, sh, z, ov = 0) {
  const tick = h("span", { class: "rw-shot-tick", style: { left: (sh.t - ov) * z + "px" }, help: "timeline.scene.shot", title: sh.camera || sh.text });
  tick.addEventListener("pointerdown", e => {
    e.stopPropagation();
    e.preventDefault();
    const x0 = e.clientX, t0 = sh.t;
    let t = t0;
    tick.setPointerCapture(e.pointerId);
    const move = ev => {
      // [OLD 2026-11-02 v0.3.2->v0.3.3] ignored ComfyUI's canvas zoom: t = Math.max(1 / FPS, Math.min(s.duration - 1 / FPS, t0 + (ev.clientX - x0) / z));
      t = Math.max(1 / FPS, Math.min(s.duration - 1 / FPS, t0 + (ev.clientX - x0) / scaleOf(ctx) / z));
      t = Math.round(t * FPS) / FPS;
      // [OLD 2026-11-03 v0.4.3->v0.5.0] tick.style.left = t * z + "px";
      tick.style.left = (t - ov) * z + "px";
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
[/OLD] */
// added 2026-11-03 v0.6.0
function shotTick(ctx, s, sh, z, ov = 0) {
  // [OLD 2026-11-06 v0.9.0->v0.10.0] const tick = h("span", { class: "rw-shot-tick", style: { left: (sh.t - ov) * z + "px" }, help: "timeline.scene.shot", title: sh.camera || sh.text, dataset: { shot: sh.id } });
  // added 2026-11-06 v0.10.0: the shot's camera and text in full in the tooltip
  const tick = h("span", { class: "rw-shot-tick", style: { left: (sh.t - ov) * z + "px" }, help: "timeline.scene.shot", dataset: { shot: sh.id },
    detail: [`${fmtTime(sh.t)}${sh.camera ? " · " + sh.camera : ""}${sh.framing ? " · " + sh.framing : ""}`, (sh.text || "").trim()].filter(Boolean).join("\n") });
  tick.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    const p = ctx.p;
    const x0 = e.clientX, t0 = sh.t;
    // a cut stays after the scene's first visible frame: the repeated tail (or last frame) before it is not in the cut
    const minT = Math.max(1 / FPS, Math.round(ov * FPS) / FPS + 1 / FPS), maxT = s.duration - 1 / FPS;
    const start = sceneStarts(p).starts[s.id];
    const live = () => liveEl(ctx, tick, `.rw-scene[data-sid="${CSS.escape(s.id)}"] .rw-shot-tick[data-shot="${CSS.escape(sh.id)}"]`);
    let t = t0;
    captureDrag(ev => {
      if (minT > maxT) return;
      t = Math.max(minT, Math.min(maxT, t0 + (ev.clientX - x0) / scaleOf(ctx) / z));
      let beat = false;
      if (beatSnapOn(p) && !ev.altKey) { // Snap to beats (Alt: free)
        const b = nearestBeat(ctx, start + t, 8 / z);
        if (b !== null && b - start >= minT && b - start <= maxT) { t = b - start; beat = true; }
      }
      t = Math.round(t * FPS) / FPS;
      const el = live();
      el.style.left = (t - ov) * z + "px";
      el.dataset.label = fmtTime(t) + (beat ? " · beat" : "");
    }, commit => {
      const el = live();
      delete el.dataset.label;
      if (commit && t !== t0) {
        ctx.actions.editScene(s.id, sc => { const x = sc.shots.find(q => q.id === sh.id); if (x) { x.t = t; sc.shots.sort((a, b) => a.t - b.t); } }, { label: "Move shot cut" });
      } else el.style.left = (t0 - ov) * z + "px";
      if (ctx.p.ui.selected !== s.id) ctx.actions.select(s.id); // the scene being edited (the release is no click on it now)
    });
  });
  return tick;
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] a lost pointerup left the drag running; used the deprecated overlapSeconds; Ripple
   even while the soundtrack sets the timing; no beat snap, no history label
// [OLD 2026-11-03 v0.4.3->v0.5.0] function resizeHandle(ctx, s, z, block) {
function resizeHandle(ctx, s, z, block, index = 0) {
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
      // [OLD 2026-11-02 v0.3.2->v0.3.3] ignored ComfyUI's canvas zoom: let frames = framesOf(Math.max(1 / FPS, d0 + (ev.clientX - x0) / z));
      let frames = framesOf(Math.max(1 / FPS, d0 + (ev.clientX - x0) / scaleOf(ctx) / z));
      if (p.ui.snap) frames = Math.max(5, nearestGridFrames(frames));
      if (!p.ui.ripple && next) frames = Math.min(frames, framesOf(d0 + nextD0) - 1);
      d = frames / FPS;
      // [OLD 2026-11-03 v0.4.3->v0.5.0] block.style.width = d * z - 2 + "px";
      block.style.width = (d - (index > 0 ? overlapSeconds({ ...s, duration: d }) : 0)) * z - 2 + "px";
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
[/OLD] */
// added 2026-11-03 v0.6.0: Roll / Auto-roll take the time from the next scene; Snap to beats puts the cut on a beat
// (before the 17k+5 grid; Alt: free of beats)
function resizeHandle(ctx, s, z, block, index = 0) {
  const handle = h("span", { class: "rw-resize", help: "timeline.scene.resize" });
  handle.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    const x0 = e.clientX, d0 = s.duration;
    const p = ctx.p;
    const i = sceneIndex(p, s.id);
    const next = p.scenes[i + 1];
    const nextD0 = next?.duration;
    const roll = rolls(p) && !!next;
    const auto = roll && p.ui.ripple && autoRollOn(p);
    const start = sceneStarts(p).starts[s.id];
    const w0 = block.style.width;
    const live = () => liveEl(ctx, block, `.rw-scene[data-sid="${CSS.escape(s.id)}"]`);
    const tip = h("div", { class: "rw-drag-tip mono" });
    block.append(tip);
    let d = d0;
    let nextF = null; // added 2026-11-03 v0.6.0 review: the next scene's length (s) while rolling (rollLengths)
    captureDrag(ev => {
      const raw = Math.max(1 / FPS, d0 + (ev.clientX - x0) / scaleOf(ctx) / z);
      let frames = framesOf(raw), how = "";
      const b = beatSnapOn(p) && !ev.altKey ? nearestBeat(ctx, start + raw, 8 / z) : null;
      if (b !== null && b - start >= 1 / FPS) { frames = framesOf(b - start); how = " · beat"; }
      else if (p.ui.snap) { frames = Math.max(5, nearestGridFrames(frames)); how = " · grid"; }
      // [OLD 2026-11-03 v0.6.0 review] if (roll) frames = Math.min(frames, framesOf(d0 + nextD0) - 1);
      // [OLD 2026-11-03 v0.6.0 review] frames = Math.max(1, frames);
      // added 2026-11-03 v0.6.0 review: rolling keeps every later scene's start (rollLengths; may clamp the drag)
      frames = Math.max(1, frames);
      let same = false;
      if (roll) ({ frames, nextDuration: nextF, unchanged: same } = rollLengths(p, i, frames));
      // [OLD 2026-11-03 v0.6.0 review] d = frames / FPS;
      d = same ? d0 : frames / FPS; // added 2026-11-03 v0.6.0 review: a roll that cannot keep the later scenes keeps both lengths
      // the block starts where the scene becomes visible; a shorter scene can shorten its own tail overlap
      const q = { ...p, scenes: p.scenes.slice() };
      q.scenes[i] = { ...s, duration: d };
      const el = live();
      el.style.width = (d - (index > 0 ? sceneOverlapAt(q, i) : 0)) * z - 2 + "px";
      if (tip.parentNode !== el) el.append(tip); // a render replaced the block
      const est = estimatePasses(d, p.global.long);
      tip.textContent = `${d.toFixed(2)} s · ${frames} f · ${est.count > 1 ? est.count + " passes" : est.short ? "trimmed" : "1 pass"}${how}${auto ? " · auto-roll" : roll ? " · roll" : ""}`;
    }, commit => {
      tip.remove();
      if (ctx.p.ui.selected !== s.id) ctx.actions.select(s.id); // the scene being edited (the release is no click on it now)
      if (!commit || d === d0) { live().style.width = w0; return; }
      ctx.actions.edit(q => {
        const sc = q.scenes.find(x => x.id === s.id);
        if (!sc) return;
        sc.duration = d;
        const nx = roll && q.scenes.find(x => x.id === next.id);
        // [OLD 2026-11-03 v0.6.0 review] if (nx) nx.duration = Math.max(1 / FPS, Math.round((d0 + nextD0 - d) * FPS) / FPS);
        if (nx) nx.duration = nextF !== null ? nextF : Math.max(1 / FPS, Math.round((d0 + nextD0 - d) * FPS) / FPS); // added 2026-11-03 v0.6.0 review
      }, { label: roll ? "Roll scene edge" : "Scene length" });
    });
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
    // [OLD 2026-11-03 v0.5.1->v0.6.0] toggle({ value: p.ui.ripple, label: p.ui.ripple ? "Ripple" : "Roll", help: "timeline.ripple", onChange: v => ctx.store.update(q => { q.ui.ripple = v; }, { history: false, plan: false }) }),
    // added 2026-11-03 v0.6.0: Auto-roll (below) overrides Ripple while the soundtrack sets the timing
    toggle({ value: p.ui.ripple && !autoRollOn(p), label: autoRollOn(p) ? "Roll (auto)" : p.ui.ripple ? "Ripple" : "Roll", help: "timeline.ripple", disabled: autoRollOn(p),
      onChange: v => ctx.store.update(q => { q.ui.ripple = v; }, { history: false, plan: false }) }),
    button({ label: "Marker", icon: "marker", small: true, help: "timeline.addMarker", onClick: () => addMarker(ctx) }),
    // added 2026-11-03 v0.6.0: beat ticks on the soundtrack lanes, snapping to them, and Auto-roll (shown with a soundtrack)
    p.soundtrack.some(t => !t.mute) && h("span", { class: "rw-sep" }),
    p.soundtrack.some(t => !t.mute) && toggle({ value: showBeats(p), label: "Beats", help: "timeline.beats",
      onChange: v => ctx.store.update(q => { q.ui.beats = v; }, { history: false, plan: false, autosave: false }) }),
    p.soundtrack.some(t => !t.mute) && toggle({ value: beatSnapOn(p), label: "Snap to beats", help: "timeline.beatSnap",
      onChange: v => ctx.store.update(q => { q.ui.beatSnap = v; }, { history: false, plan: false, autosave: false }) }),
    soundtrackLocked(p) && toggle({ value: autoRollOn(p), label: "Auto-roll", help: "timeline.autoRoll",
      onChange: v => ctx.store.update(q => { q.ui.autoRoll = v; }, { history: false, plan: false, autosave: false }) }),
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
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const s = sceneAt(ctx, p.ui.playhead);
  const s = sceneAt(p, p.ui.playhead);
  const m = monitorOf(ctx);
  m.show(s, p.ui.playhead - starts[s.id]);
  /* [OLD 2026-11-06 v0.8.0->v0.9.0] asset bin | monitor | inspector at fixed sizes
  return h("div", { class: "rw-tl" },
    profileBanner(ctx), // added 2026-11-02 v0.3.0
    h("div", { class: "rw-tl-top" },
      renderBin(ctx),
      h("div", { class: "rw-mon-col" }, m.el, renderTransport(ctx)),
      renderInspector(ctx)),
    h("div", { class: "rw-tl-main rw-panel" }, renderToolbar(ctx), renderLanes(ctx)));
  [/OLD] */
  // added 2026-11-06 v0.9.0: three panels. The bar between the monitor and the inspector sets the monitor's share of
  // the width (ui.tl_mon, 0.15–0.85); the bar under them sets their height (ui.tl_top, px). Double-click a bar to
  // reset it. Sizes are kept in the project like the zoom (no undo step).
  // [OLD 2026-11-12 v0.12.0->v0.13.0] const monCol = h("div", { class: "rw-mon-col rw-panel", style: { width: (uiNum(p, "tl_mon", MON_SHARE, 0.15, 0.85) * 100).toFixed(2) + "%" } }, m.el, renderTransport(ctx));
  // added 2026-11-12 v0.13.0: while the monitor is full screen it stays in its full-screen box; the panel says so
  const monEl = ctx.monFull ? h("div", { class: "rw-mon rw-mon-away", help: "timeline.fullscreen", onClick: () => toggleFull(ctx) }, icon("expand", 18), h("span", null, "Full screen · Esc to come back")) : m.el;
  const monCol = h("div", { class: "rw-mon-col rw-panel", style: { width: (uiNum(p, "tl_mon", MON_SHARE, 0.15, 0.85) * 100).toFixed(2) + "%" } }, monEl, renderTransport(ctx));
  const top = h("div", { class: "rw-tl-top", style: { height: Math.round(uiNum(p, "tl_top", TOP_H, TOP_MIN, 4000)) + "px" } });
  // a redraw while dragging (a render's progress, an autosave) puts new panels on screen: the bars work on those
  const live = (el, sel) => (el.isConnected ? el : ctx.root.querySelector(sel)) || el;
  let topW = 1, tlH = 0; // measured when a drag starts
  const share = px => Math.max(0.15, Math.min(0.85, px / Math.max(1, topW)));
  const keep = (k, v) => ctx.store.update(q => { if (v === null) delete q.ui[k]; else q.ui[k] = v; }, { history: false, plan: false, autosave: false });
  top.append(monCol,
    splitter({ dir: "x", help: "timeline.split.monitor", key: "tl-split-mon",
      onStart: () => { const mc = live(monCol, ".rw-mon-col"); topW = live(top, ".rw-tl-top").clientWidth; return mc.getBoundingClientRect().width / rootScale(mc); },
      onMove: px => { live(monCol, ".rw-mon-col").style.width = (share(px) * 100).toFixed(2) + "%"; },
      onEnd: px => keep("tl_mon", Math.round(share(px) * 1000) / 1000),
      onReset: () => keep("tl_mon", null) }),
    renderInspector(ctx));
  const tlEl = h("div", { class: "rw-tl" });
  const topPx = px => Math.max(TOP_MIN, Math.min(Math.max(TOP_MIN, tlH - 190), px));
  const banner = profileBanner(ctx); // added 2026-11-02 v0.3.0
  if (banner) tlEl.append(banner);
  tlEl.append(
    top,
    splitter({ dir: "y", help: "timeline.split.height", key: "tl-split-top",
      onStart: () => { const tp = live(top, ".rw-tl-top"); tlH = live(tlEl, ".rw-tl").clientHeight; return tp.getBoundingClientRect().height / rootScale(tp); },
      onMove: px => { live(top, ".rw-tl-top").style.height = topPx(px) + "px"; },
      onEnd: px => keep("tl_top", Math.round(topPx(px))),
      onReset: () => keep("tl_top", null) }),
    h("div", { class: "rw-tl-main rw-panel" }, renderToolbar(ctx), renderLanes(ctx)));
  return tlEl;
}
// added 2026-11-06 v0.9.0: default panel sizes (ui.tl_top in px, ui.tl_mon as a share of the width)
const TOP_H = 340, TOP_MIN = 170, MON_SHARE = 0.42;
