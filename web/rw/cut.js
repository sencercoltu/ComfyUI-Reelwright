// added 2026-11-05 v0.7.0: per-scene cut settings (scene.merge) for the Scene tab's "In the cut" card, the timeline's
// marks and the Render tab. The schema, defaults and normalisation live in model.js / model.py (contract B); this file
// only reads them, with a fallback for a scene that has no merge object yet.

import * as model from "./model.js";
import { effectiveStart, tailOverlapFrames, soundtrackLocked } from "./model.js";

// how a fresh scene joins the one before (merge.py maps them to ffmpeg xfade; "dip" goes through `color`)
export const TRANSITIONS = [
  { value: "cut", label: "Cut", short: "cut" },
  { value: "crossfade", label: "Crossfade", short: "xfade" },
  { value: "dip", label: "Dip to colour", short: "dip" },
  { value: "dissolve", label: "Dissolve", short: "dissolve" },
  { value: "wipe", label: "Wipe", short: "wipe" },
  { value: "slide", label: "Slide", short: "slide" },
  { value: "circle", label: "Circle open", short: "circle" },
  { value: "pixelize", label: "Pixelize", short: "pixel" },
  { value: "radial", label: "Radial", short: "radial" },
  { value: "zoom", label: "Zoom in", short: "zoom" },
];
export const TRANSITION = Object.fromEntries(TRANSITIONS.map(t => [t.value, t]));
export const DIRECTIONS = [
  { value: "left", label: "←", word: "left" }, { value: "right", label: "→", word: "right" },
  { value: "up", label: "↑", word: "up" }, { value: "down", label: "↓", word: "down" },
];
export const DIRECTED = new Set(["wipe", "slide"]);

// contract B's defaults (model.js has the authoritative copy once it defines one)
const FALLBACK = {
  transition: "cut", direction: "left", frames: 12, color: "#000000", audio_frames: 6,
  fade_in: { frames: 0, color: "#000000" }, fade_out: { frames: 0, color: "#000000" },
  audio_fade_in: 0, audio_fade_out: 0, volume_db: 0, mute: false,
  color_match: "off", color_ref: "", brightness: 0, contrast: 1, saturation: 1,
};
const HEX = /^#[0-9a-f]{6}$/i;

// A fresh copy of the default merge settings of a new scene.
export function mergeDefaults() {
  const fromModel = typeof model.defaultMerge === "function" ? model.defaultMerge()
    : model.MERGE_DEFAULTS && typeof model.MERGE_DEFAULTS === "object" ? model.MERGE_DEFAULTS : null;
  return structuredClone(fromModel && typeof fromModel === "object" ? fromModel : FALLBACK);
}

function fillFrom(target, defaults) {
  for (const [k, v] of Object.entries(defaults)) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      if (!target[k] || typeof target[k] !== "object" || Array.isArray(target[k])) target[k] = {};
      fillFrom(target[k], v);
    } else if (target[k] === undefined || target[k] === null || typeof target[k] !== typeof v) target[k] = v;
  }
  return target;
}

// The scene's merge settings, complete (a copy: reading only).
export function mergeOf(scene) {
  const m = scene?.merge && typeof scene.merge === "object" ? structuredClone(scene.merge) : {};
  fillFrom(m, mergeDefaults());
  for (const c of [m, m.fade_in, m.fade_out]) if (!HEX.test(c.color)) c.color = "#000000";
  return m;
}

// The scene's merge object for an edit: completed in place (an older project may not have one yet).
export function ensureMerge(scene) {
  if (!scene.merge || typeof scene.merge !== "object" || Array.isArray(scene.merge)) scene.merge = {};
  return fillFrom(scene.merge, mergeDefaults());
}

// How scene i joins the one before in the cut:
//   kind "first" (nothing before it), "continuation" (tail / last-frame start: its own transition is not used),
//   "cut" (a fresh start with a plain cut) or "transition" (a fresh start with an overlapping transition).
//   asDip: a soundtrack sets the timing, so the transition plays as a dip through `color` inside both scenes.
export function joinOf(p, i, scene = null) {
  const s = scene || p.scenes[i];
  const m = mergeOf(s);
  if (i <= 0) return { kind: "first", mode: "fresh", m };
  const mode = effectiveStart(p, i);
  if (mode !== "fresh") {
    return { kind: "continuation", mode, m, overlap: mode === "tail" ? tailOverlapFrames(p, i) : 1,
      crossfade: mode === "tail" ? Math.max(0, Math.trunc(Number(p.global?.long?.crossfade_frames) || 0)) : 0 };
  }
  if (m.transition === "cut") return { kind: "cut", mode, m };
  const asDip = soundtrackLocked(p);
  return { kind: "transition", mode, m, asDip, color: m.color };
}

// The label of a transition, with its direction ("Wipe →").
export function transitionLabel(m) {
  const t = TRANSITION[m.transition] || { label: m.transition };
  const d = DIRECTED.has(m.transition) ? DIRECTIONS.find(x => x.value === m.direction) : null;
  return d ? `${t.label} ${d.label}` : t.label;
}
