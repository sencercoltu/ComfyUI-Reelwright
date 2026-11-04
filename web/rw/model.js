// Project schema 1: defaults, normalization and the small amount of H3 math the
// editor needs for instant feedback. The backend planner stays authoritative.

export const FPS = 24;
export const MIN_PASS_FRAMES = 124;
export const MAX_PASS_FRAMES = 362;

export const STABLE_LANGUAGES = ["Arabic", "Chinese", "English", "French", "German", "Italian",
  "Japanese", "Korean", "Portuguese", "Russian", "Spanish"];
export const VISUAL_RETENTION = ["fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"];
export const AUDIO_RETENTION = ["fully_copy", "partially_copy", "reference", "weak_reference"];
export const ROLES = ["reference", "first_frame", "last_frame", "keyframe"];
export const START_MODES = ["fresh", "last_frame", "tail"];
export const ASPECTS = { "21:9": [21, 9], "16:9": [16, 9], "4:3": [4, 3], "1:1": [1, 1], "3:4": [3, 4], "9:16": [9, 16] };
export const ASSET_CATEGORIES = {
  image: ["subject", "location", "prop", "style", "keyframe"],
  video: ["motion", "camera", "edit_source", "style"],
  audio: ["voice", "ambience", "music", "sfx"],
};
export const SECTION_KEYS = ["subject_definitions", "summary", "retention_analysis",
  "detailed_description", "overall_soundscape", "non_diegetic_music"];
/* [OLD 2026-11-02 v0.2.2->v0.3.0] quality became a per-scene override
export const OVERRIDE_KEYS = ["seed", "steps", "sampler", "scheduler", "width", "height",
  "diffusion", "text_encoder", "video_vae", "audio_vae"];
[/OLD] */
export const OVERRIDE_KEYS = ["seed", "steps", "sampler", "scheduler", "width", "height",
  "diffusion", "text_encoder", "video_vae", "audio_vae", "quality"];
export const TRANSITIONS = ["cut", "crossfade", "dip"]; // added 2026-11-02 v0.3.0

const CODE_PREFIX = { image: "P", video: "V", audio: "A" };
// added 2026-11-03 v0.6.0: what normalizeProject enforces (same values as reelwright/model.py)
export const MIN_SCENE_SECONDS = 1 / FPS;
export const MAX_SCENE_SECONDS = 600;
export const ASSET_KINDS = ["image", "video", "audio"];
export const CAST_KINDS = ["character", "location", "prop"];
export const TRIM_KEEPS = ["start", "middle", "end", "custom"];
const PROMPT_MODES = ["structured", "raw"];
const SLUG_MAX = 64;
export const SLUG_RE = /^[a-z0-9_][a-z0-9_-]{0,63}$/; // storage.SLUG_RE
const ID_RE = /^[A-Za-z0-9_-]{1,64}$/; // storage.ID_RE: scene ids are folder names
const SEED_N_LIMIT = 2 ** 31;
const MAX_REF_IMAGES = 9;
const REF_MEDIA_MIN_SECONDS = 2;
const REF_MEDIA_MAX_SECONDS = 15;

// ---- value coercion (added 2026-11-03 v0.6.0, same as reelwright/spec.py num / flag / text) ----
const NUM_TEXT = /^[ \t\n\r]*[-+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?[ \t\n\r]*$/;
// v as a finite number (numbers, or text such as "12.5"), else dflt. true/false are not numbers.
function num(v, dflt = 0) {
  if (typeof v === "number") return Number.isFinite(v) ? v : dflt;
  if (typeof v === "string" && NUM_TEXT.test(v)) {
    const x = Number(v);
    return Number.isFinite(x) ? x : dflt;
  }
  return dflt;
}
// v as a bool: booleans as they are, numbers are true unless 0, anything else is dflt.
function flag(v, dflt = false) {
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return Number.isFinite(v) ? v !== 0 : dflt;
  return dflt;
}
// v as a string: strings as they are, finite numbers as String(v), anything else is dflt.
function text(v, dflt = "") {
  if (typeof v === "string") return v;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return dflt;
}
// exported under other names: ui.js already has text() and number() widgets
export { num as asNum, flag as asFlag, text as asText };

export function newId(prefix) {
  return prefix + "_" + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-3);
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] no length cap, differed from Python, accents kept as combining marks then dropped
export function slugify(name) {
  const s = String(name || "").toLowerCase().normalize("NFKD").replace(/[^\w\s-]/g, "")
    .trim().replace(/[\s-]+/g, "_").replace(/^_+|_+$/g, "");
  return s || "untitled";
}
[/OLD] */
// Folder name for a project name (same as model.py slugify): lower-case ASCII letters, digits and _, at most 64
// characters. Accents are transliterated ("Ömer" -> "omer"); a name without any ASCII letter gives "untitled".
export function slugify(name) {
  let s = text(name).normalize("NFKD").toLowerCase();
  s = s.replace(/[^a-z0-9_ \t\n\r\f\v-]/g, "").replace(/^[ \t\n\r\f\v]+|[ \t\n\r\f\v]+$/g, "");
  s = s.replace(/[ \t\n\r\f\v-]+/g, "_").replace(/^_+|_+$/g, "");
  s = s.slice(0, SLUG_MAX).replace(/^_+|_+$/g, "");
  return /[a-z]/.test(s) ? s : "untitled";
}

// added 2026-11-03 v0.6.0: the project's folder: its slug when that is a valid folder name (kept as typed, so
// "untitled-x7k2" stays), else slugify(slug or name). Same as model.py project_slug.
export function projectSlug(p) {
  const s = text(p.slug);
  return SLUG_RE.test(s) ? s : slugify(s || p.name);
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] looped forever on NaN / Infinity (a non-numeric duration hung the browser)
export function alignFramesUp(n) {
  n = Math.max(5, Math.round(n));
  while (n % 17 !== 5) n++;
  return n;
}

// added 2026-11-03 v0.5.0: largest 17k+5 frame count <= n (spec.align_frames_down)
export function alignFramesDown(n) {
  n = Math.floor(n);
  if (n < 5) return 5;
  while (n % 17 !== 5) n--;
  return n;
}
[/OLD] */
// Smallest 17k+5 frame count >= n (and >= 5); not a finite number -> 5 (spec.align_frames_up).
export function alignFramesUp(n) {
  n = Math.max(5, roundHalfEven(num(n, 0)));
  return n + ((((5 - n) % 17) + 17) % 17);
}

// Largest 17k+5 frame count <= n, never below 5 (spec.align_frames_down).
export function alignFramesDown(n) {
  n = Math.trunc(num(n, 0));
  if (n < 5) return 5;
  return n - ((n - 5) % 17);
}

export function nearestGridFrames(n) {
  const k = Math.max(0, Math.round((n - 5) / 17));
  return k * 17 + 5;
}

export function framesOf(seconds) {
  // [OLD 2026-11-03 v0.5.1->v0.6.0] return Math.round(seconds * FPS);  (Python rounds halves to even)
  return roundHalfEven(seconds * FPS);
}

export function fmtTime(t, ms = true) {
  const neg = t < 0;
  t = Math.abs(t);
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  const ss = ms ? s.toFixed(3).padStart(6, "0") : String(Math.floor(s)).padStart(2, "0");
  return (neg ? "-" : "") + String(m).padStart(2, "0") + ":" + ss;
}

export function fmtSec(t) {
  return (Math.round(t * 100) / 100).toFixed(2) + " s";
}

// Python's round(): halves go to the even neighbour (48.5 -> 48).
function roundHalfEven(x) {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

// added 2026-11-03 v0.6.0: Python's round(x, nd) (exact ties go to the even digit), for soundtrack.py parity
function pyRound(x, nd) {
  if (!Number.isFinite(x)) return x;
  const ax = Math.abs(x);
  const up = ax.toFixed(nd); // ties go up here
  const exact = ax.toFixed(nd + 16);
  let v = Number(up);
  if (exact.slice(-16) === "5" + "0".repeat(15)) { // a true tie
    const down = exact.slice(0, exact.length - 16);
    if (Number(down[down.length - 1]) % 2 === 0) v = Number(down);
  }
  return x < 0 ? -v : v;
}

// added 2026-11-03 v0.6.0: Python's float a // b (CPython float_floor_div), for soundtrack.py parity
function pyFloorDiv(vx, wx) {
  let mod = vx % wx;
  let div = (vx - mod) / wx;
  if (mod && (wx < 0) !== (mod < 0)) div -= 1;
  if (!div) return 0;
  let fl = Math.floor(div);
  if (div - fl > 0.5) fl += 1;
  return fl;
}

// Port of comfy_extras.nodes_minimax_h3.adapt_canvas.
export function adaptCanvas(width, height) {
  const BASE = 768, MAX = 768 * 1344, M = 32;
  const ratio = width / height;
  let w, hgt;
  if (ratio >= 1) { w = BASE * ratio; hgt = BASE; } else { w = BASE; hgt = BASE / ratio; }
  if (w * hgt > MAX) {
    const s = Math.sqrt(MAX / (w * hgt));
    w *= s; hgt *= s;
  }
  return [Math.max(M, roundHalfEven(w / M) * M), Math.max(M, roundHalfEven(hgt / M) * M)];
}

// Display estimate of how a scene of `duration` seconds is split into passes.
export function estimatePasses(duration, longCfg) {
  const frames = framesOf(duration);
  if (frames <= MAX_PASS_FRAMES) {
    const gen = alignFramesUp(Math.max(MIN_PASS_FRAMES, frames));
    return { count: 1, genFrames: gen, trimmed: gen !== frames, short: frames < MIN_PASS_FRAMES };
  }
  const max = Math.min(MAX_PASS_FRAMES, longCfg?.max_pass_frames || MAX_PASS_FRAMES);
  const overlap = longCfg?.overlap_frames ?? 39;
  const count = 1 + Math.ceil((frames - max) / Math.max(1, max - overlap));
  return { count, genFrames: max, trimmed: true, short: false };
}

function defaultGlobal() {
  return {
    models: {
      diffusion: "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
      weight_dtype: "default",
      text_encoder: "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
      clip_device: "default",
      video_vae: "minimax_h3_video_vae_int8_convrot.safetensors",
      audio_vae: "minimax_h3_audio_vae_fp32.safetensors",
      latent_upscaler: "",
    },
    loras: [],
    output: { aspect: "16:9", width: 1344, height: 768, ref_image_size: "match" },
    sampling: { steps: 20, sampler: "res_multistep", scheduler: "simple", seed: 104729,
      seed_mode: "increment", sigma_shift: false, shift_video: 12.0, shift_audio: 3.0 },
    quality: "final",
    draft: { scale: 0.5, steps: 8, lora: "", lora_strength: 1.0 },
    defaults: { duration: 8.0, start_mode: "last_frame", overlap_frames: 39, language: "English" },
    long: { max_pass_frames: 362, overlap_frames: 39, crossfade_frames: 12, seam_mode: "auto", cut_snap_seconds: 2.0 },
    memory: { policy: "free_cache", encode_first: true, group_by_lora: true },
    continuity: { reanchor_after: 2, face_check: false, face_threshold: 0.8, on_drift: "flag" },
    /* [OLD 2026-11-02 v0.1.0->v0.2.0] no switch for sending MiniMax's prompt guides
    llm: { base_url: "", model: "", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va" },
    [/OLD] */
    // [OLD 2026-11-02 v0.3.1->v0.3.2] llm: { base_url: "", model: "", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va", include_guides: true },
    // [OLD 2026-11-03 v0.4.1->v0.4.2] llm: { base_url: "", model: "", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va", include_guides: true, thinking: "auto" },
    llm: { base_url: "", model: "", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va", include_guides: true, thinking: "auto",
      // added 2026-11-03 v0.4.2: limits (see reelwright/model.py)
      timeout_s: 120, max_wait_s: 900, retries: 2, context_tokens: 0,
      import_part_chars: 3000, import_max_tokens: 16384, import_thinking: "same", import_guides: false },
    merge: { use: "starred", missing: "skip", hard_cut: "cut", transition_frames: 12, audio_fade_frames: 6,
      loudness: -16.0, normalize: true, score: { asset: "", volume_db: -12.0, duck: true }, // v0.5.0: score moves to p.soundtrack on load
      scene_audio: { mix: false, volume_db: -12.0 }, // added 2026-11-03 v0.5.0: the scenes' own sound under a soundtrack
      color_match: false, color_ref_scene: "", codec: "h264", crf: 16,
      subtitles: true, chapters: true, otio: true, fcpxml: true, bundle: false, auto_after_render: true },
  };
}

const DEFAULT_CAMERA = [
  ["Slow push-in", "slow push-in toward the subject"],
  ["Locked-off", "static locked-off camera"],
  ["Crane up", "slow crane up revealing the scene"],
  ["Handheld pan →", "handheld camera panning right"],
  ["Rack focus", "rack focus from foreground to background"],
  ["Macro", "macro close-up, shallow depth of field"],
];

export function defaultPrompt() {
  const sections = {};
  for (const k of SECTION_KEYS) sections[k] = "";
  return { mode: "structured", auto: { subjects: true, retention: true, shots: true }, sections, raw: "", pass_prompts: {} };
}

export function defaultScene(project, patch = {}) {
  const d = project?.global?.defaults || defaultGlobal().defaults;
  const first = !project || !project.scenes || project.scenes.length === 0;
  return {
    id: newId("s"),
    title: "New scene",
    duration: d.duration,
    color: "",
    start: { mode: first ? "fresh" : d.start_mode, overlap_frames: d.overlap_frames },
    trim: { keep: "start", in: 0.0 },
    refs: [], cast: [], shots: [], dialogue: [],
    prompt: defaultPrompt(),
    overrides: {},
    lock: false, notes: "",
    // added 2026-11-02 v0.3.0: the cut into this scene; empty/null follow Global -> Merge
    transition: { mode: "", frames: null, audio_fade_frames: null },
    // added 2026-11-03 v0.6.0: the scene's number in "+1 per scene" seed mode, fixed at creation
    seed_n: nextSeedN(project),
    ...patch,
  };
}

export function defaultProject(name = "Untitled") {
  const p = {
    // [OLD 2026-11-03 v0.5.1->v0.6.0] schema: 1, id: newId("p"), name, slug: slugify(name),
    // project_id (added 2026-11-03 v0.6.0): who owns the folder; /autosave refuses another project's folder
    schema: 1, id: newId("p"), project_id: newId("p"), name, slug: slugify(name),
    global: defaultGlobal(), assets: [], cast: [],
    camera_presets: DEFAULT_CAMERA.map(([n, t]) => ({ id: newId("k"), name: n, text: t })),
    scenes: [], markers: [],
    soundtrack: [], // added 2026-11-03 v0.5.0: audio laid on the film (see reelwright/soundtrack.py)
    ui: { tab: "timeline", selected: "", zoom: 22, playhead: 0, snap: true, ripple: true },
  };
  p.scenes.push(defaultScene(p, { title: "Scene 1", start: { mode: "fresh", overlap_frames: 39 } }));
  p.ui.selected = p.scenes[0].id;
  return p;
}

function isObj(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

// added 2026-11-02 v0.3.0: a profile's Global settings, completed with today's defaults
export function normalizeGlobal(g, p = null) {
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const out = fill(isObj(g) ? structuredClone(g) : {}, defaultGlobal());  (no type checks)
  // v0.6.0: coerced to the defaults' types, same as model.py normalize_global
  const out = like(isObj(g) ? structuredClone(g) : {}, defaultGlobal());
  const d = out.defaults;
  if (!START_MODES.includes(d.start_mode)) d.start_mode = "last_frame";
  d.duration = Math.min(MAX_SCENE_SECONDS, Math.max(MIN_SCENE_SECONDS, d.duration));
  d.overlap_frames = Math.max(0, Math.trunc(d.overlap_frames));
  out.continuity.reanchor_after = Math.max(0, Math.trunc(out.continuity.reanchor_after));
  out.loras = objects(out.loras);
  for (const l of out.loras) normLora(l);
  // a profile saved in another project may name a score asset or colour scene this project lacks
  if (p) {
    const m = out.merge;
    if (m.score?.asset && !p.assets.some(a => a.id === m.score.asset)) m.score.asset = "";
    if (m.color_ref_scene && !p.scenes.some(s => s.id === m.color_ref_scene)) m.color_ref_scene = "";
  }
  return out;
}

function fill(target, defaults) {
  for (const [k, v] of Object.entries(defaults)) {
    if (!(k in target) || target[k] === undefined || target[k] === null) target[k] = structuredClone(v);
    else if (isObj(v) && isObj(target[k])) fill(target[k], v);
  }
  return target;
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] codes were unique per kind only; tags look them up across kinds, ignoring case
export function assignCodes(assets) {
  const used = { image: new Set(), video: new Set(), audio: new Set() };
  for (const a of assets) if (a.code && used[a.kind]) used[a.kind].add(a.code);
  for (const a of assets) {
    if (a.code || !used[a.kind]) continue;
    let n = 1;
    while (used[a.kind].has(CODE_PREFIX[a.kind] + n)) n++;
    a.code = CODE_PREFIX[a.kind] + n;
    used[a.kind].add(a.code);
  }
  return assets;
}
[/OLD] */
// Give every asset without a code the next free P/V/A number; codes are unique across kinds, ignoring case.
export function assignCodes(assets) {
  const used = new Set(assets.filter(a => a.code).map(a => text(a.code).toUpperCase()));
  for (const a of assets) {
    if (a.code || !Object.hasOwn(CODE_PREFIX, a.kind)) continue;
    let n = 1;
    while (used.has((CODE_PREFIX[a.kind] + n).toUpperCase())) n++;
    a.code = CODE_PREFIX[a.kind] + n;
    used.add(a.code.toUpperCase());
  }
  return assets;
}

// [OLD 2026-11-03 v0.5.1->v0.6.0] crashed on malformed JSON, did not sort shots/dialogue, fill cast entries or
// outfits, re-slugify, repair duplicate ids or coerce types, and differed from model.py in places
// export function normalizeProject(raw) {
//   let p = raw;
//   if (typeof p === "string") {
//     try { p = p.trim() ? JSON.parse(p) : null; } catch { p = null; }
//   }
//   if (!isObj(p) || !Array.isArray(p.scenes)) return defaultProject();
//   const base = defaultProject(p.name || "Untitled");
//   base.scenes = [];
//   fill(p, base);
//   if (!p.slug) p.slug = slugify(p.name);
//   p.schema = 1;
//   for (const s of p.scenes) {
//     fill(s, defaultScene(p, { id: s.id || newId("s") }));
//     fill(s.prompt, defaultPrompt());
//     s.refs.forEach(r => fill(r, { id: newId("r"), role: "reference", time: 0, retention: "", keep: [], soundtrack: false }));
//     s.shots.forEach(x => fill(x, { id: newId("h"), t: 0, camera: "", text: "" }));
//     s.dialogue.forEach(x => fill(x, { id: newId("d"), speaker: "", t: 0, language: p.global.defaults.language, delivery: "", text: "" }));
//   }
//   for (const a of p.assets) {
//     fill(a, { id: newId("a"), code: "", kind: "image", name: "", file: "", duration: 0, width: 0, height: 0, category: "",
//       /* [OLD 2026-11-02 v0.1.0->v0.2.0] assets had no description
//       defaults: { role: "reference", retention: a.kind === "audio" ? "reference" : "fully_preserved", keep: [], soundtrack: false }, notes: "" });
//       [/OLD] */
//       defaults: { role: "reference", retention: a.kind === "audio" ? "reference" : "fully_preserved", keep: [], soundtrack: false }, notes: "",
//       description: "" }); // added 2026-11-02 v0.2.0: description feeds subject_definitions
//   }
//   assignCodes(p.assets);
//   for (const c of p.cast) {
//     fill(c, { id: newId("c"), kind: "character", name: "", speaker: "", description: "", anchors: [], pack_sheet: true,
//       outfits: [], default_outfit: "", voice: "", language: p.global.defaults.language, lora: { name: "", strength: 0.8 } });
//     if (![true, false, "auto"].includes(c.pack_sheet)) c.pack_sheet = true; // added 2026-11-03 v0.4.1 (see prompt.py)
//   }
//   if (!p.scenes.length) p.scenes.push(defaultScene(p, { title: "Scene 1" }));
//   if (!p.scenes.some(s => s.id === p.ui.selected)) p.ui.selected = p.scenes[0].id;
//   // added 2026-11-03 v0.5.0: soundtrack tracks; the old merge score becomes one (same as soundtrack.py)
//   p.soundtrack = p.soundtrack.filter(isObj);
//   p.soundtrack.forEach(t => normalizeTrack(t));
//   const score = p.global.merge.score;
//   if (score?.asset) {
//     p.soundtrack.push(normalizeTrack({ id: "t_score", asset: score.asset, volume_db: Number(score.volume_db ?? -12), sync: false, mix: true, duck: score.duck !== false, loop: true }));
//     score.asset = "";
//     p.global.merge.scene_audio = { mix: true, volume_db: 0 };
//   }
//   return p;
// }
// [/OLD]
// added 2026-11-03 v0.6.0: the hardened normaliser, the same as model.py normalize_project (tests/test_model_parity.py
// runs both on the same JSON). Only difference: a project without a project_id gets one here (the editor owns it).
// Never throws on bad input: wrong types become defaults, lists keep their objects, shots and dialogue are sorted by
// time, scene lengths clamped to 1/24 .. 600 s, duplicate ids get _2, _3 ..., duplicate asset codes are re-assigned,
// every scene gets a seed_n. Mutates and returns the parsed object.
export function normalizeProject(raw) {
  let p = raw;
  if (typeof p === "string") {
    try { p = p.trim() ? JSON.parse(p) : null; } catch { p = null; }
  }
  if (!isObj(p) || !Array.isArray(p.scenes)) return defaultProject();
  p.schema = 1;
  p.id = text(p.id) || newId("p");
  p.project_id = text(p.project_id) || newId("p");
  p.name = p.name === undefined || p.name === null ? "Untitled" : text(p.name, "Untitled");
  p.slug = projectSlug(p);
  const g = p.global = normalizeGlobal(p.global);
  const lang = g.defaults.language;

  const assets = p.assets = objects(p.assets);
  const seenCodes = new Set();
  for (const a of assets) {
    normAsset(a);
    const code = a.code.toUpperCase();
    if (seenCodes.has(code)) a.code = ""; // a duplicate gets the next free code below
    else if (code) seenCodes.add(code);
  }
  assignCodes(assets);

  p.cast = objects(p.cast);
  for (const c of p.cast) normCast(c, lang);

  const used = new Set();
  p.scenes = objects(p.scenes);
  for (const s of p.scenes) normScene(s, g.defaults, lang, used);
  if (!p.scenes.length) p.scenes.push(defaultScene(p, { title: "Scene 1" }));
  repairSeedNs(p.scenes);

  p.markers = objects(p.markers);
  for (const m of p.markers) {
    m.id = text(m.id) || newId("m");
    m.t = num(m.t, 0);
    textField(m, "text", "");
    textField(m, "color", "amber");
  }
  p.camera_presets = Array.isArray(p.camera_presets) ? objects(p.camera_presets) : defaultCameraPresets();
  for (const k of p.camera_presets) {
    k.id = text(k.id) || newId("k");
    textField(k, "name", "");
    textField(k, "text", "");
  }

  // v0.5.0 soundtrack tracks; the old merge score becomes one (migrateScore, as soundtrack.migrate_score)
  p.soundtrack = objects(p.soundtrack);
  for (const t of p.soundtrack) normalizeTrack(t);
  migrateScore(p);
  const usedT = new Set();
  for (const t of p.soundtrack) t.id = uniqueId(t.id, "t", usedT);

  const ui = p.ui = isObj(p.ui) ? p.ui : {};
  textField(ui, "tab", "timeline");
  textField(ui, "selected", "");
  ui.zoom = num(ui.zoom, 22);
  ui.playhead = num(ui.playhead, 0);
  ui.snap = flag(ui.snap, true);
  ui.ripple = flag(ui.ripple, true);
  if (!p.scenes.some(s => s.id === ui.selected)) ui.selected = p.scenes[0].id;
  return p;
}

function defaultCameraPresets() {
  return DEFAULT_CAMERA.map(([n, t]) => ({ id: newId("k"), name: n, text: t }));
}

// the object items of a list (anything else gives [])
function objects(v) {
  return Array.isArray(v) ? v.filter(isObj) : [];
}

// the strings (and numbers, as text) of a list
function texts(v) {
  return Array.isArray(v) ? v.filter(x => text(x, null) !== null).map(x => text(x)) : [];
}

function textField(o, key, dflt) {
  o[key] = o[key] === undefined || o[key] === null ? dflt : text(o[key], dflt);
}

function blank(s) {
  return !/[^ \t\n\r\f\v]/.test(s);
}

// v when it is a free id; a taken one gets _2, _3 ...; a missing one a new id. With `pattern`, characters it does not
// allow become "_" (scene ids are folder names).
function uniqueId(v, prefix, used, pattern = null) {
  let s = text(v);
  if (pattern && s && !pattern.test(s)) s = s.replace(/[^A-Za-z0-9_-]/gu, "_").slice(0, 64);
  if (!s) {
    s = newId(prefix);
    while (used.has(s)) s = newId(prefix);
  } else if (used.has(s)) {
    const base = Array.from(s).slice(0, 56).join("");
    let n = 2;
    while (used.has(`${base}_${n}`)) n++;
    s = `${base}_${n}`;
  }
  used.add(s);
  return s;
}

// v in the shape of the default d (model.py _like): objects key by key (extra keys kept), arrays must be arrays,
// numbers / booleans / strings coerced, a null default takes anything.
function like(v, d) {
  if (isObj(d)) {
    const out = isObj(v) ? v : {};
    for (const [k, dv] of Object.entries(d)) out[k] = like(out[k], dv);
    return out;
  }
  if (Array.isArray(d)) return Array.isArray(v) ? v : structuredClone(d);
  if (typeof d === "boolean") return flag(v, d);
  if (typeof d === "number") return num(v, d);
  if (typeof d === "string") return v === undefined || v === null ? d : text(v, d);
  return v === undefined ? null : v;
}

function normLora(l) {
  l.id = text(l.id) || newId("l");
  textField(l, "name", "");
  l.strength = num(l.strength, 1);
  l.enabled = flag(l.enabled, true);
}

function normAsset(a) {
  a.kind = ASSET_KINDS.includes(a.kind) ? a.kind : "image";
  a.id = text(a.id) || newId("a");
  for (const k of ["code", "name", "file", "category", "notes", "description"]) textField(a, k, "");
  for (const k of ["duration", "width", "height"]) a[k] = Math.max(0, num(a[k], 0));
  const df = a.defaults = isObj(a.defaults) ? a.defaults : {};
  df.role = ROLES.includes(df.role) ? df.role : "reference";
  textField(df, "retention", a.kind === "audio" ? "reference" : "fully_preserved");
  df.keep = texts(df.keep);
  df.soundtrack = flag(df.soundtrack, false);
}

function normCast(c, lang) {
  c.id = text(c.id) || newId("c");
  c.kind = CAST_KINDS.includes(c.kind) ? c.kind : "character";
  for (const k of ["name", "speaker", "description", "default_outfit", "voice"]) textField(c, k, "");
  textField(c, "language", lang);
  c.anchors = texts(c.anchors);
  // v0.4.1: true (one sheet), false (separate pictures) or "auto" (see prompt.py)
  if (!(typeof c.pack_sheet === "boolean" || c.pack_sheet === "auto")) c.pack_sheet = true;
  c.outfits = objects(c.outfits);
  for (const o of c.outfits) {
    o.id = text(o.id) || newId("o");
    textField(o, "name", "");
    textField(o, "retention", "fully_preserved");
    o.keep = texts(o.keep);
    o.assets = texts(o.assets);
  }
  const lora = c.lora = isObj(c.lora) ? c.lora : {};
  textField(lora, "name", "");
  lora.strength = num(lora.strength, 0.8);
}

// One scene in place. d: Global -> New-scene defaults; usedIds: scene ids taken so far.
function normScene(s, d, lang, usedIds) {
  s.id = uniqueId(s.id, "s", usedIds, ID_RE);
  textField(s, "title", "New scene");
  s.duration = Math.min(MAX_SCENE_SECONDS, Math.max(MIN_SCENE_SECONDS, num(s.duration, d.duration)));
  textField(s, "color", "");
  let st = s.start;
  st = typeof st === "string" ? { mode: st } : isObj(st) ? st : {};
  st.mode = START_MODES.includes(st.mode) ? st.mode : d.start_mode;
  st.overlap_frames = Math.max(0, Math.trunc(num(st.overlap_frames, d.overlap_frames)));
  s.start = st;
  const tr = s.trim = isObj(s.trim) ? s.trim : {};
  tr.keep = TRIM_KEEPS.includes(tr.keep) ? tr.keep : "start";
  tr.in = Math.max(0, num(tr.in, 0));

  let used = new Set();
  s.refs = objects(s.refs);
  for (const r of s.refs) {
    r.id = uniqueId(r.id, "r", used);
    textField(r, "asset", "");
    r.role = ROLES.includes(r.role) ? r.role : "reference";
    r.time = num(r.time, 0);
    textField(r, "retention", "");
    r.keep = texts(r.keep);
    r.soundtrack = flag(r.soundtrack, false);
  }
  const cast = [];
  for (let e of Array.isArray(s.cast) ? s.cast : []) {
    if (typeof e === "string") e = { id: e, outfit: "" };
    if (!isObj(e)) continue;
    textField(e, "id", "");
    textField(e, "outfit", "");
    cast.push(e);
  }
  s.cast = cast;
  used = new Set();
  s.shots = objects(s.shots);
  for (const x of s.shots) {
    x.id = uniqueId(x.id, "h", used);
    x.t = num(x.t, 0);
    textField(x, "camera", "");
    textField(x, "text", "");
  }
  s.shots.sort((a, b) => a.t - b.t);
  used = new Set();
  s.dialogue = objects(s.dialogue);
  for (const x of s.dialogue) {
    x.id = uniqueId(x.id, "d", used);
    x.t = num(x.t, 0);
    for (const k of ["speaker", "delivery", "text"]) textField(x, k, "");
    textField(x, "language", lang);
  }
  s.dialogue.sort((a, b) => a.t - b.t);

  let pr = s.prompt;
  if (typeof pr === "string") pr = { mode: blank(pr) ? "structured" : "raw", raw: pr }; // a bare text is a raw prompt
  pr = s.prompt = isObj(pr) ? pr : {};
  pr.mode = PROMPT_MODES.includes(pr.mode) ? pr.mode : "structured";
  const auto = pr.auto = isObj(pr.auto) ? pr.auto : {};
  for (const k of ["subjects", "retention", "shots"]) auto[k] = flag(auto[k], true);
  const sec = pr.sections = isObj(pr.sections) ? pr.sections : {};
  for (const k of SECTION_KEYS) textField(sec, k, "");
  textField(pr, "raw", "");
  const pp = isObj(pr.pass_prompts) ? pr.pass_prompts : {};
  pr.pass_prompts = Object.fromEntries(Object.entries(pp).filter(([, v]) => text(v, null) !== null).map(([k, v]) => [k, text(v)]));

  const o = s.overrides = isObj(s.overrides) ? s.overrides : {};
  for (const k of ["seed", "steps", "width", "height"]) {
    if (!Object.hasOwn(o, k)) continue;
    const v = num(o[k], null);
    if (v === null) delete o[k]; // "" or junk: follow Global
    else o[k] = Math.trunc(v);
  }
  for (const k of ["sampler", "scheduler", "diffusion", "text_encoder", "video_vae", "audio_vae", "quality"]) {
    if (Object.hasOwn(o, k) && typeof o[k] !== "string") delete o[k];
  }
  if (Object.hasOwn(o, "loras")) {
    const lo = o.loras;
    if (!isObj(lo)) delete o.loras;
    else {
      lo.mode = ["add", "replace"].includes(lo.mode) ? lo.mode : "add";
      lo.items = objects(lo.items);
      for (const l of lo.items) normLora(l);
      const sts = isObj(lo.strengths) ? lo.strengths : {};
      lo.strengths = Object.fromEntries(Object.entries(sts).filter(([, v]) => num(v, null) !== null).map(([k, v]) => [k, num(v)]));
    }
  }
  s.lock = flag(s.lock, false);
  textField(s, "notes", "");
  const tn = s.transition = isObj(s.transition) ? s.transition : {};
  tn.mode = ["", ...TRANSITIONS].includes(tn.mode) ? tn.mode : "";
  for (const k of ["frames", "audio_fade_frames"]) tn[k] = num(tn[k], null);
}

// ---- stable seeds (added 2026-11-03 v0.6.0, same as model.py) ----
// "+1 per scene" seeds used the scene's position, so inserting or moving a scene changed every later seed. Each
// scene keeps the number it got when it was made: seed = Global seed + seed_n.
function seedNValue(v) {
  return typeof v === "number" && Number.isInteger(v) && v >= 0 && v < SEED_N_LIMIT ? v + 0 : null;
}

// A valid seed_n stays unless an earlier scene has it; a scene without one gets its list index (its seed before
// seed_n existed), or the next number above the highest when that is taken.
function repairSeedNs(scenes) {
  const used = new Set();
  const pending = [];
  scenes.forEach((s, i) => {
    const n = seedNValue(s.seed_n);
    if (n !== null && !used.has(n)) { used.add(n); s.seed_n = n; } else pending.push([i, s, n === null]);
  });
  for (const [i, s, missing] of pending) {
    const n = missing && !used.has(i) ? i : Math.max(-1, ...used) + 1;
    used.add(n);
    s.seed_n = n;
  }
}

// seed_n for a new scene (split, duplicate, paste, add): one above the highest in the project, 0 for the first.
export function nextSeedN(project) {
  const scenes = Array.isArray(project?.scenes) ? project.scenes : [];
  const vals = scenes.map((s, i) => { const n = isObj(s) ? seedNValue(s.seed_n) : null; return n === null ? i : n; });
  return vals.length ? Math.max(...vals) + 1 : 0;
}

// The scene's seed number: its seed_n, or its index for a scene that has none.
export function sceneSeedN(scene, index) {
  const n = seedNValue(scene?.seed_n);
  return n === null ? index : n;
}

// The scene's base seed (model.scene_seed); null in "random" mode (the backend hashes the scene id).
export function sceneSeed(project, scene, index, take = 0) {
  const o = scene.overrides || {};
  let base;
  if (o.seed !== undefined && o.seed !== null && o.seed !== "") base = Math.trunc(Number(o.seed));
  else {
    const sm = project.global.sampling;
    if (sm.seed_mode === "fixed") base = Math.trunc(sm.seed);
    else if (sm.seed_mode === "random") return null;
    else base = Math.trunc(sm.seed) + sceneSeedN(scene, index);
  }
  const v = base + take * 1000003;
  if (v >= 0 && v < 2 ** 53) return v;
  // Python's (base + take * 1000003) % 2**63, exact in BigInt; a Number above 2**53 is only close (display only)
  const M = 2n ** 63n;
  return Number((((BigInt(base) + BigInt(take) * 1000003n) % M) + M) % M);
}

// added 2026-11-03 v0.6.0: Python parity, the v0.4 merge score becomes a looping soundtrack track (soundtrack.py
// migrate_score). normalizeProject calls it; call it after applying a profile that names a score.
export function migrateScore(project) {
  const m = project.global?.merge || {};
  const score = m.score || {};
  if (!score.asset) return false;
  if (!Array.isArray(project.soundtrack)) project.soundtrack = [];
  // added 2026-11-03 v0.6.0: a unique id (an old profile applied twice gave two "t_score" tracks), as soundtrack.py
  const used = new Set(project.soundtrack.map(t => t && t.id));
  let tid = "t_score";
  for (let k = 2; used.has(tid); k++) tid = `t_score_${k}`;
  // [OLD 2026-11-03 v0.5.1->v0.6.0] project.soundtrack.push(normalizeTrack({ id: "t_score", asset: score.asset, ... (fixed id)
  project.soundtrack.push(normalizeTrack({ id: tid, asset: score.asset, volume_db: num(score.volume_db, -12), sync: false, mix: true, duck: flag(score.duck, true), loop: true }));
  score.asset = "";
  m.scene_audio = { mix: true, volume_db: 0 };
  return true;
}

/* [OLD 2026-11-03 v0.4.3->v0.5.0] scenes end to end, and only the raw tail overlap: the finished cut was shorter, so a soundtrack drifted
export function sceneStarts(project) {
  const starts = {};
  let t = 0;
  for (const s of project.scenes) { starts[s.id] = t; t += s.duration; }
  return { starts, total: t };
}

export function overlapSeconds(scene) {
  return scene.start.mode === "tail" ? scene.start.overlap_frames / FPS : 0;
}
[/OLD] */
// ---- memo (added 2026-11-03 v0.6.0) ----
// The store sets a non-enumerable number project.__rwv and bumps it on every change; results that walk the whole
// project (scene starts, songs, plans) are kept per version. Without __rwv (a copy, a test) everything is computed
// fresh. Callers must not change what these return.
const MEMO = new WeakMap();
function memo(project, key, fn) {
  const v = project?.__rwv;
  if (typeof v !== "number") return fn();
  let m = MEMO.get(project);
  if (!m || m.v !== v) {
    m = { v, vals: new Map() };
    MEMO.set(project, m);
  }
  if (!m.vals.has(key)) m.vals.set(key, fn());
  return m.vals.get(key);
}

// ---- how scenes join (added 2026-11-03 v0.6.0, same as model.py; tests/test_model_parity.py) ----
// How many continuation links lead into each scene (model.continuation_depth).
export function continuationDepth(project) {
  const depth = {};
  let prev = 0;
  project.scenes.forEach((s, i) => {
    prev = i > 0 && (s.start.mode === "last_frame" || s.start.mode === "tail") ? prev + 1 : 0;
    depth[s.id] = prev;
  });
  return depth;
}

function depthAt(project, i, scene) {
  let d = 0, j = i, cur = scene;
  while (j > 0 && (cur.start.mode === "last_frame" || cur.start.mode === "tail")) {
    d++;
    j--;
    cur = project.scenes[j];
  }
  return d;
}

// Frames of a scene in the cut (at least 1).
export function sceneFrames(scene) {
  return Math.max(1, framesOf(Math.max(1 / FPS, scene.duration)));
}

// [effective start, tail overlap frames] of scene i (model._start_info); `scene` replaces project.scenes[i].
function startInfo(project, i, scene = null, depth = null) {
  const s = scene || project.scenes[i];
  const mode = i > 0 ? s.start.mode : "fresh";
  if (mode === "last_frame") return ["last_frame", 0];
  if (mode !== "tail") return ["fresh", 0];
  if (depth === null) depth = depthAt(project, i, s);
  if (depth > Math.trunc(project.global.continuity.reanchor_after)) return ["last_frame", 0]; // re-anchored
  const down = n => (n >= 5 ? alignFramesDown(n) : 0);
  // at most 124 frames: render keeps the last 124 frames of a scene as its tail clip
  const n = Math.min(alignFramesDown(Math.max(5, Math.trunc(s.start.overlap_frames))), MIN_PASS_FRAMES, down(sceneFrames(s)),
    down(sceneFrames(project.scenes[i - 1])));
  return n >= 5 ? ["tail", n] : ["last_frame", 0];
}

// How scene i really starts: "fresh", "last_frame" or "tail". The first scene is fresh; a tail past Global ->
// Continuity -> re-anchor after, or next to a scene shorter than 5 frames, is a last-frame start everywhere.
export function effectiveStart(project, i) {
  return startInfo(project, i)[0];
}

// Frames of the tail clip scene i starts with (17k+5, >= 5), 0 unless effectiveStart is "tail". Capped by the
// scene's own length, the length of the scene before and 124 frames (the tail clip render keeps).
export function tailOverlapFrames(project, i) {
  return startInfo(project, i)[1];
}

function overlapOf(mode, frames) {
  return mode === "tail" ? frames / FPS : mode === "last_frame" ? 1 / FPS : 0;
}

// Seconds at the start of scene i that repeat the end of the scene before (tail clip, one frame, or 0).
export function sceneOverlapAt(project, i) {
  return overlapOf(...startInfo(project, i));
}

// One pass over the scenes: [{id, start, overlap, visible, end}] and the cut's length. Memoised per version.
function timing(project) {
  return memo(project, "timing", () => {
    const rows = [];
    let t = 0, depth = 0;
    project.scenes.forEach((s, i) => {
      depth = i > 0 && (s.start.mode === "last_frame" || s.start.mode === "tail") ? depth + 1 : 0;
      const ov = overlapOf(...startInfo(project, i, s, depth));
      t = Math.max(0, t - ov);
      rows.push({ id: s.id, start: t, overlap: ov, visible: t + ov, end: t + s.duration });
      t += s.duration;
    });
    const starts = {}, visible = {}, index = {};
    rows.forEach((r, i) => { starts[r.id] = r.start; visible[r.id] = r.visible; index[r.id] = i; });
    return { rows, total: t, starts, visible, index };
  });
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] used overlapSeconds (no cap by the scene before, no re-anchor rule), not memoised
// added 2026-11-03 v0.5.0: start of every scene in the finished cut (model.scene_starts). A scene's time t plays at
// starts[id] + t; a scene that continues the one before begins inside it by overlapSeconds.
export function sceneStarts(project) {
  const starts = {};
  let t = 0;
  project.scenes.forEach((s, i) => {
    t = Math.max(0, t - (i > 0 ? overlapSeconds(s) : 0));
    starts[s.id] = t;
    t += s.duration;
  });
  return { starts, total: t };
}
[/OLD] */
// Start of every scene in the finished cut (model.scene_starts), the cut's length, and where each scene first shows
// new content (visible = start + overlap). A scene's time t plays at starts[id] + t.
export function sceneStarts(project) {
  const { starts, total, visible } = timing(project);
  return { starts, total, visible };
}

// Film time where scene `id` first shows new content (start + the overlap it repeats); undefined for an unknown id.
export function visibleStart(project, id) {
  return timing(project).visible[id];
}

// The scene on screen at film time t: scenes own [visibleStart, start + duration). Before the first scene (or t not
// a number): the first scene; after the end: the last.
export function sceneAt(project, t) {
  const { rows } = timing(project);
  for (let k = rows.length - 1; k > 0; k--) if (rows[k].visible <= t) return project.scenes[k];
  return project.scenes[0];
}

// DEPRECATED (2026-11-03 v0.6.0): use sceneOverlapAt(project, i), which knows the scene before (a tail is capped by
// its length) and the re-anchor rule. Kept unchanged for callers that have not switched yet.
// Seconds at the start of a scene that repeat the end of the one before (callers check that it is not the first):
// the tail clip (the planner's 17k+5 frames) or the one last frame.
export function overlapSeconds(scene) {
  if (scene.start.mode === "tail") {
    const total = Math.max(1, framesOf(Math.max(1 / FPS, scene.duration)));
    return Math.min(alignFramesDown(Math.max(5, scene.start.overlap_frames)), alignFramesDown(total)) / FPS;
  }
  return scene.start.mode === "last_frame" ? 1 / FPS : 0;
}

// ---- soundtrack (added 2026-11-03 v0.5.0, mirrors reelwright/soundtrack.py) ----
export const TRACK_DEFAULTS = { id: "", asset: "", start: 0, in: 0, out: 0, volume_db: 0, fade_in: 0, fade_out: 0, mute: false,
  sync: true, marker: "fully_copy", mix: true, duck: false, loop: false };

export function normalizeTrack(t) {
  fill(t, TRACK_DEFAULTS);
  // [OLD 2026-11-03 v0.5.1->v0.6.0] if (!t.id) t.id = newId("t");  (moved below, after the id is made a string)
  // [OLD 2026-11-03 v0.5.1->v0.6.0] for (const k of ["start", "in", "out", "volume_db", "fade_in", "fade_out"]) t[k] = Number.isFinite(Number(t[k])) ? Number(t[k]) : 0;
  for (const k of ["start", "in", "out", "volume_db", "fade_in", "fade_out"]) t[k] = num(t[k], 0); // v0.6.0: same as soundtrack.py
  t.in = Math.max(0, t.in);
  t.fade_in = Math.max(0, t.fade_in);
  t.fade_out = Math.max(0, t.fade_out);
  for (const k of ["mute", "sync", "mix", "duck", "loop"]) t[k] = flag(t[k], TRACK_DEFAULTS[k]); // added 2026-11-03 v0.6.0
  for (const k of ["id", "asset"]) t[k] = text(t[k]); // added 2026-11-03 v0.6.0
  if (!t.id) t.id = newId("t");
  if (!AUDIO_RETENTION.includes(t.marker)) t.marker = "fully_copy";
  return t;
}

// The source seconds a track plays: in..out, or in..end of the file when out is not set.
export function trackLength(t, asset) {
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const out = t.out > t.in ? t.out : Number(asset?.duration) || 0;
  const out = t.out > t.in ? t.out : num(asset?.duration, 0);
  return Math.max(0, out - t.in);
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] a track whose asset had no file counted as playing (soundtrack.resolved skips it)
// Tracks that play: not muted, an audio asset, some length.
export function playingTracks(project) {
  return project.soundtrack.map(t => ({ t, a: findAsset(project, t.asset) }))
    .filter(({ t, a }) => !t.mute && a?.kind === "audio" && trackLength(t, a) > 0);
}
[/OLD] */
// Tracks that play (soundtrack.resolved): not muted, an audio asset with a file, some length. [{t, a}]
export function playingTracks(project) {
  return memo(project, "playing", () => {
    const byId = new Map(project.assets.map(a => [a.id, a]));
    return project.soundtrack.map(t => ({ t, a: byId.get(t.asset) }))
      .filter(({ t, a }) => !t.mute && a?.kind === "audio" && a.file && trackLength(t, a) > 0);
  });
}

// added 2026-11-03 v0.6.0: soundtrack.resolved: copies of the playing tracks with the asset's file, code and length
export function resolvedTracks(project) {
  return memo(project, "resolved", () => playingTracks(project).map(({ t, a }) => ({ ...t, file: a.file, code: a.code || "", length: trackLength(t, a) })));
}

// added 2026-11-03 v0.6.0: soundtrack.pieces: what `tracks` play in film time t0..t0+length,
// [{asset, file, src_in, src_out, at}] (at: offset inside the window). Looping tracks repeat.
export function soundtrackPieces(tracks, t0, length) {
  const out = [];
  for (const t of tracks) {
    let reps = [0];
    if (t.loop) {
      if (t.length <= 1e-3) continue; // no repeat could last over 1 ms
      const first = Math.trunc(pyFloorDiv(Math.max(0, t0 - t.start), t.length));
      const n = Math.trunc(pyFloorDiv(length, t.length)) + 2;
      reps = Array.from({ length: n }, (_, k) => first + k);
    }
    for (const r of reps) {
      const begin = t.start + r * t.length;
      const a = Math.max(t0, begin), b = Math.min(t0 + length, begin + t.length);
      if (b - a > 1e-3) out.push({ asset: t.asset, file: t.file, src_in: pyRound(t.in + (a - begin), 4), src_out: pyRound(t.in + (b - begin), 4), at: pyRound(a - t0, 4) });
    }
  }
  return out;
}

// added 2026-11-03 v0.6.0: soundtrack.pass_soundtrack: the song for one pass, or null. sceneStart: the scene's start
// in the cut (sceneStarts); pass: a planScene pass. Left out when less than 2 s of it has sound.
export function passSoundtrack(project, sceneStart, pass) {
  const tracks = resolvedTracks(project).filter(t => t.sync);
  if (!tracks.length) return null;
  const t0 = sceneStart + pass.start, length = Math.min(REF_MEDIA_MAX_SECONDS, pass.gen_frames / FPS);
  const ps = soundtrackPieces(tracks, t0, length);
  if (ps.reduce((s, x) => s + (x.src_out - x.src_in), 0) < REF_MEDIA_MIN_SECONDS) return null;
  const heard = tracks.filter(t => ps.some(x => x.asset === t.asset));
  return { start: pyRound(t0, 4), length: pyRound(length, 4), pieces: ps, marker: heard[0].marker,
    codes: [...new Set(heard.map(t => t.code))].sort() };
}

// A soundtrack sets the timing: transitions keep their place and missing scenes keep their length in the cut.
export function soundtrackLocked(project) {
  return playingTracks(project).some(({ t }) => t.mix || t.sync);
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] guessed from the scene's span; H3 gets the song only for passes with 2 s of it
// Whether the song is sent to H3 for this scene (any sync track sounds during it).
export function sceneHasSong(project, scene) {
  const { starts } = sceneStarts(project);
  const a = starts[scene.id], b = a + scene.duration;
  return playingTracks(project).some(({ t, a: asset }) => t.sync && (t.loop ? t.start < b : t.start < b && t.start + trackLength(t, asset) > a));
}
[/OLD] */
// Whether the song is sent to H3 for this scene: some pass of it gets soundtrack.pass_soundtrack. Memoised.
export function sceneHasSong(project, scene) {
  const i = timing(project).index[scene.id];
  const run = () => {
    if (!resolvedTracks(project).some(t => t.sync)) return false;
    const start = timing(project).starts[scene.id] ?? 0;
    return planScene(project, scene, i ?? 0).passes.some(x => passSoundtrack(project, start, x));
  };
  return project.scenes[i] === scene ? memo(project, "song:" + scene.id, run) : run();
}

// ---- scene length vs shots (added 2026-11-03 v0.4.3) ----
// A shot lasts until the next one starts; the last one until the scene ends.
export function shotLengths(scene) {
  return scene.shots.map((sh, i) => {
    const next = i + 1 < scene.shots.length ? scene.shots[i + 1].t : scene.duration;
    return { length: Math.max(0, Math.min(next, scene.duration) - sh.t), last: i === scene.shots.length - 1, past: sh.t >= scene.duration };
  });
}

// Median gap between shot starts (1–15 s), the length given to a last shot that starts after the end.
export function typicalShot(scene) {
  const gaps = scene.shots.slice(1).map((sh, i) => sh.t - scene.shots[i].t).filter(g => g > 0).sort((a, b) => a - b);
  return gaps.length ? Math.max(1, Math.min(15, gaps[Math.floor(gaps.length / 2)])) : 4;
}

// Shots and dialogue lines that start at or after the scene's end (the same rule as validate.py).
export function overruns(scene) {
  const shots = scene.shots.filter(x => x.t >= scene.duration).length;
  const lines = scene.dialogue.filter(x => x.t >= scene.duration).length;
  return shots + lines ? { shots, lines } : null;
}

// The length a scene needs so every shot and line fits: the last shot gets a typical shot length, a line 2 s.
export function fitLength(scene) {
  let need = scene.duration;
  const lastShot = scene.shots.length ? Math.max(...scene.shots.map(x => x.t)) : -1;
  if (lastShot >= scene.duration) need = Math.max(need, lastShot + typicalShot(scene));
  const lastLine = scene.dialogue.length ? Math.max(...scene.dialogue.map(x => x.t)) : -1;
  if (lastLine >= scene.duration) need = Math.max(need, lastLine + 2);
  return Math.ceil(need * FPS - 1e-6) / FPS;
}

export function lengthenToFit(scene) {
  scene.duration = fitLength(scene);
}

// Keep the length and move every shot and line closer together, in proportion.
export function squeezeToFit(scene) {
  const k = scene.duration / fitLength(scene);
  for (const x of [...scene.shots, ...scene.dialogue]) x.t = Math.round(x.t * k * FPS) / FPS;
}

export function assembledDuration(project) {
  // [OLD 2026-11-03 v0.5.1->v0.6.0] return project.scenes.reduce((t, s, i) => t + s.duration - (i > 0 ? overlapSeconds(s) : 0), 0);
  return timing(project).rows.reduce((t, r, i) => t + project.scenes[i].duration - r.overlap, 0);
}

export function sceneIndex(project, id) {
  return project.scenes.findIndex(s => s.id === id);
}

export function findAsset(project, id) {
  return project.assets.find(a => a.id === id);
}

export function findCast(project, id) {
  return project.cast.find(c => c.id === id);
}

const GLOBAL_PATH = {
  seed: g => g.sampling.seed, steps: g => g.sampling.steps, sampler: g => g.sampling.sampler,
  scheduler: g => g.sampling.scheduler, width: g => g.output.width, height: g => g.output.height,
  diffusion: g => g.models.diffusion, text_encoder: g => g.models.text_encoder,
  video_vae: g => g.models.video_vae, audio_vae: g => g.models.audio_vae,
  quality: g => g.quality, // added 2026-11-02 v0.3.0
};

export function effective(project, scene, key) {
  const o = scene.overrides || {};
  if (o[key] !== undefined && o[key] !== null && o[key] !== "") return { value: o[key], overridden: true };
  let value = GLOBAL_PATH[key](project.global);
  // [OLD 2026-11-03 v0.5.1->v0.6.0] if (key === "seed" && project.global.sampling.seed_mode === "increment") value += sceneIndex(project, scene.id);
  if (key === "seed" && project.global.sampling.seed_mode === "increment") value += sceneSeedN(scene, sceneIndex(project, scene.id));
  return { value, overridden: false };
}

export function overrideCount(scene) {
  const o = scene.overrides || {};
  let n = OVERRIDE_KEYS.filter(k => o[k] !== undefined && o[k] !== null && o[k] !== "").length;
  if (o.loras) {
    n += (o.loras.items || []).length + Object.keys(o.loras.strengths || {}).length + (o.loras.mode === "replace" ? 1 : 0);
  }
  return n;
}

// LoRAs a scene ends up with, in application order, for display.
export function effectiveLoras(project, scene) {
  const o = scene.overrides?.loras;
  const out = [];
  if (!o || o.mode !== "replace") {
    for (const l of project.global.loras) {
      if (!l.enabled) continue;
      const s = o?.strengths?.[l.id];
      out.push({ name: l.name, strength: s ?? l.strength, source: s !== undefined ? "override" : "global", id: l.id });
    }
  }
  for (const l of o?.items || []) if (l.enabled !== false) out.push({ name: l.name, strength: l.strength, source: "scene", id: l.id });
  for (const sc of scene.cast) {
    const c = findCast(project, sc.id);
    if (c?.lora?.name) out.push({ name: c.lora.name, strength: c.lora.strength, source: "cast", castName: c.name, id: c.id });
  }
  return out;
}

export function retentionOptions(kind) {
  return kind === "audio" ? AUDIO_RETENTION : VISUAL_RETENTION;
}

// added 2026-11-03 v0.4.1: anchor sheets, matching prompt.collect_refs and media.sheet_image.
// pack_sheet: true (one sheet), false (separate pictures), "auto" (a sheet only when the scene's pictures don't fit
// H3's 9 slots otherwise). Outfit pictures are left out here; the backend adds them to the anchors.
/* [OLD 2026-11-03 v0.5.1->v0.6.0] left out outfit pictures and speakers missing from the cast list (prompt.py counts them)
export function sceneAutoPacks(project, scene) {
  const anchors = new Set();
  for (const sc of scene.cast) for (const id of findCast(project, sc.id)?.anchors || []) if (findAsset(project, id)?.kind === "image") anchors.add(id);
  const refs = new Set(scene.refs.filter(r => r.role === "reference" && findAsset(project, r.asset)?.kind === "image" && !anchors.has(r.asset)).map(r => r.asset));
  return anchors.size + refs.size > 9;
}
[/OLD] */
export function sceneAutoPacks(project, scene) {
  return scenePeople(project, scene).autoPack;
}

// added 2026-11-03 v0.6.0: the cast a scene sends, as prompt.collect_refs / model.scene_media_counts: its cast list
// plus speakers missing from it, each with its anchor pictures and outfit pictures; autoPack: "auto" sheets pack.
function scenePeople(project, scene) {
  const assets = new Map(project.assets.map(a => [a.id, a]));
  const cast = new Map(project.cast.map(c => [c.id, c]));
  const entries = [...scene.cast];
  for (const d of scene.dialogue) if (cast.has(d.speaker) && !entries.some(e => e.id === d.speaker)) entries.push({ id: d.speaker, outfit: "" });
  const people = [];
  for (const e of entries) {
    const c = cast.get(e.id);
    if (!c) continue;
    const outfit = c.outfits.find(o => o.id === (e.outfit || c.default_outfit));
    const ids = c.anchors.filter(a => assets.get(a)?.kind === "image");
    if (outfit) ids.push(...outfit.assets.filter(a => assets.get(a)?.kind === "image" && !ids.includes(a)));
    people.push({ c, ids });
  }
  const anchors = new Set(people.flatMap(x => x.ids));
  const refPics = new Set(scene.refs.filter(r => r.role === "reference" && assets.get(r.asset)?.kind === "image").map(r => r.asset));
  const autoPack = anchors.size + [...refPics].filter(a => !anchors.has(a)).length > MAX_REF_IMAGES;
  return { people, autoPack, assets };
}
export function castPacks(project, scene, c) {
  const n = c.anchors.filter(id => findAsset(project, id)?.kind === "image").length;
  if (n < 2) return false;
  return c.pack_sheet === "auto" ? (scene ? sceneAutoPacks(project, scene) : false) : !!c.pack_sheet;
}
export function sheetGrid(n) {
  const cols = Math.max(1, Math.ceil(Math.sqrt(n)));
  return [cols, Math.max(1, Math.ceil(n / cols))];
}
// about how many pixels wide one anchor reaches H3, packed or alone, at the given output size
export function anchorPixels(project, c, packed, width, height) {
  const pics = c.anchors.map(id => findAsset(project, id)).filter(a => a?.kind === "image");
  if (!pics.length) return 0;
  const area = width * height;
  const max = project.global.output.ref_image_size === "max";
  const ratios = pics.map(a => Math.max(0.5, Math.min(2, (a.width || 1) / (a.height || 1)))).sort((x, y) => x - y);
  const r = ratios[Math.floor(ratios.length / 2)];
  if (!packed) {
    const a = pics[0], w = a.width || 1024, hgt = a.height || 1024;
    const s = max ? Math.min(1, 2048 / Math.min(w, hgt)) : Math.min(1, Math.sqrt(area / (w * hgt)));
    return Math.round(Math.min(w, hgt) * s);
  }
  const [cols, rows] = sheetGrid(pics.length);
  const cw = 768 * Math.sqrt(r), ch = 768 / Math.sqrt(r);
  const W = cols * cw, H = rows * ch;
  const s = max ? Math.min(1, 2048 / Math.min(W, H)) : Math.min(1, Math.sqrt(area / (W * H)));
  return Math.round(Math.min(cw, ch) * s);
}
export function sheetURL(project, c, cell = 192) {
  const files = c.anchors.map(id => findAsset(project, id)).filter(a => a?.kind === "image" && a.file).map(a => a.file);
  return files.length ? "/reelwright/sheet?cell=" + cell + "&files=" + encodeURIComponent(JSON.stringify(files)) : "";
}

// Reference budget, the same numbers as model.scene_media_counts (added 2026-11-03 v0.6.0): a video whose sound is used
// takes an audio slot, a voice counts only in passes where its character speaks (and not with the song), the song
// only where passSoundtrack gives one, files = pictures + videos + audio files. With a pass (from planScene): that
// pass; without: the most any pass of the scene uses (song: any pass).
// {pictures, videos, videoSeconds, audio, audioSeconds, files, song}
export function sceneBudget(project, scene, pass = null) {
  if (!pass) {
    const outs = planScene(project, scene).passes.map(x => sceneBudget(project, scene, x));
    const b = {};
    for (const k of ["pictures", "videos", "videoSeconds", "audio", "audioSeconds", "files"]) b[k] = Math.max(...outs.map(o => o[k]));
    b.song = outs.some(o => o.song);
    return b;
  }
  const { people, autoPack, assets } = scenePeople(project, scene);
  const song = passSoundtrack(project, timing(project).starts[scene.id] ?? 0, pass);
  const speaking = new Set((pass.dialogue || []).map(d => d.speaker));
  const b = { pictures: 0, videos: 0, videoSeconds: 0, audio: 0, audioSeconds: 0, files: 0, song: !!song };
  const sent = new Set(), sounds = [];
  for (const { c, ids } of people) {
    const pack = c.pack_sheet === "auto" ? autoPack : !!(c.pack_sheet ?? true);
    b.pictures += ids.length && pack && ids.length > 1 ? 1 : ids.length;
    for (const a of ids) sent.add(a);
    const v = assets.get(c.voice);
    if (v && v.kind === "audio" && !song && speaking.has(c.id)) sounds.push(v);
  }
  for (const r of scene.refs) {
    const a = assets.get(r.asset);
    if (!a || r.role !== "reference") continue;
    const dur = Number(a.duration) || 0;
    if (a.kind === "image") {
      if (!sent.has(a.id)) { sent.add(a.id); b.pictures++; }
    } else if (a.kind === "video") {
      b.videos++;
      b.videoSeconds += dur;
      if (r.soundtrack) { b.audio++; b.audioSeconds += dur; } // the video's sound takes an <Audio j> slot
    } else if (a.kind === "audio" && !sounds.some(x => x.id === a.id)) sounds.push(a);
  }
  b.audio += sounds.length + (song ? 1 : 0);
  for (const a of sounds) b.audioSeconds += Number(a.duration) || 0;
  if (song) b.audioSeconds += song.length;
  b.files = b.pictures + b.videos + sounds.length + (song ? 1 : 0);
  return b;
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] counted per scene with a guessed song length; voices of non-speakers in other passes
// Reference budget for one pass of a scene, matching how the backend presents refs.
export function sceneBudget(project, scene) {
  const b = { pictures: 0, videos: 0, videoSeconds: 0, audio: 0, audioSeconds: 0, files: 0 };
  for (const r of scene.refs) {
    const a = findAsset(project, r.asset);
    if (!a || r.role !== "reference") continue;
    if (a.kind === "image") b.pictures++;
    if (a.kind === "video") {
      b.videos++; b.videoSeconds += a.duration || 0;
      if (r.soundtrack) { b.audio++; b.audioSeconds += a.duration || 0; }
    }
    if (a.kind === "audio") { b.audio++; b.audioSeconds += a.duration || 0; }
  }
  const song = sceneHasSong(project, scene); // added 2026-11-03 v0.5.0: the song replaces the cast voices
  for (const sc of scene.cast) {
    const c = findCast(project, sc.id);
    if (!c) continue;
    // [OLD 2026-11-03 v0.4.0->v0.4.1] if (c.anchors.length) b.pictures += c.pack_sheet ? 1 : c.anchors.length;
    if (c.anchors.length) b.pictures += castPacks(project, scene, c) ? 1 : c.anchors.length;
    const voice = findAsset(project, c.voice);
    const speaks = scene.dialogue.some(d => d.speaker === c.id);
    // [OLD 2026-11-03 v0.4.3->v0.5.0] if (voice && speaks) { b.audio++; b.audioSeconds += voice.duration || 0; }
    if (voice && speaks && !song) { b.audio++; b.audioSeconds += voice.duration || 0; }
  }
  if (song) { // one song segment per pass, at most 15 s
    b.audio++;
    b.audioSeconds += Math.min(15, estimatePasses(scene.duration, project.global.long).count > 1 ? (project.global.long.max_pass_frames || MAX_PASS_FRAMES) / FPS : Math.max(scene.duration, MIN_PASS_FRAMES / FPS));
    b.song = true;
  }
  b.files = b.pictures + b.videos + b.audio;
  return b;
}
[/OLD] */

// ---- passes (added 2026-11-03 v0.6.0): a port of reelwright/planner.py plan_scene, so the editor knows each pass's
// window, shots, lines and guides without asking the backend (tests/test_model_parity.py keeps them equal). ----
function clampPassFrames(n) {
  return Math.min(MAX_PASS_FRAMES, alignFramesUp(Math.max(MIN_PASS_FRAMES, n)));
}

function cutFrames(scene, total) {
  const cuts = new Set();
  for (const sh of scene.shots.slice(1)) {
    const f = framesOf(sh.t);
    if (f > 0 && f < total) cuts.add(f);
  }
  return [...cuts].sort((a, b) => a - b);
}

function passesNeeded(frames, maxF, ov) {
  return frames <= maxF ? 1 : 1 + Math.ceil((frames - maxF) / (maxF - ov));
}

// [[start_frame, gen_frames, keep_frames, seam_before, overlap_in]] covering 0..total (planner._segments)
function segmentsOf(scene, total, maxF, ov, seamMode, snapF, firstOverlap) {
  const cuts = cutFrames(scene, total);
  const out = [];
  let s = 0, seam = "none", ovIn = firstOverlap;
  for (;;) {
    const remaining = total - s;
    if (remaining <= maxF) {
      out.push([s, clampPassFrames(remaining), remaining, seam, ovIn]);
      return out;
    }
    const limit = s + maxF;
    let cut = null;
    if (seamMode !== "overlap") {
      let cands = cuts.filter(c => s + MIN_PASS_FRAMES <= c && c <= limit);
      if (seamMode === "auto") {
        const baseline = passesNeeded(remaining, maxF, ov);
        cands = cands.filter(c => c >= limit - snapF || 1 + passesNeeded(total - c, maxF, ov) <= baseline);
      }
      if (cands.length) cut = Math.max(...cands);
    }
    if (cut !== null) {
      const length = cut - s;
      out.push([s, clampPassFrames(length), length, seam, ovIn]);
      s = cut; seam = "cut"; ovIn = 0;
      continue;
    }
    let gen = maxF;
    const leftAfter = remaining - (gen - ov);
    if (leftAfter > 0 && leftAfter < MIN_PASS_FRAMES) gen = Math.min(maxF, Math.max(MIN_PASS_FRAMES, alignFramesUp(Math.floor((remaining + ov) / 2))));
    out.push([s, gen, gen, seam, ovIn]);
    s = s + gen - ov; seam = "overlap"; ovIn = ov;
  }
}

// Scene frame of time t kept inside the scene (0 .. total-1); null at or after the scene's end (planner._clamp_frame).
function clampFrame(t, duration, total) {
  if (t >= duration) return null;
  return Math.min(Math.max(framesOf(t), 0), total - 1);
}

function shotRangesOf(scene, total, duration) {
  const shots = scene.shots;
  const starts = shots.map(sh => clampFrame(sh.t, duration, total) ?? total);
  return shots.map((sh, i) => {
    const a = starts[i], b = i + 1 < shots.length ? starts[i + 1] : total;
    return [i + 1, sh, a, Math.max(a, b)];
  });
}

// The passes of scene `index` (planner.plan_scene, same output). Memoised per version for scenes of the project.
export function planScene(project, scene, index) {
  if (index === undefined || index === null) index = timing(project).index[scene.id] ?? 0;
  index = Math.max(0, index);
  const run = () => planSceneNow(project, scene, index);
  return project.scenes[index] === scene ? memo(project, "plan:" + scene.id, run) : run();
}

function planSceneNow(project, scene, index) {
  const lg = project.global.long;
  const duration = Math.max(1 / FPS, scene.duration);
  const total = Math.max(1, framesOf(duration));
  const seed = sceneSeed(project, scene, index);
  const declared = index > 0 ? scene.start.mode : "fresh";
  const [mode, firstOverlap] = startInfo(project, index, scene);
  let keepIn = 0, kind, segs;
  if (total < MIN_PASS_FRAMES) {
    kind = "short";
    const gen = MIN_PASS_FRAMES, spare = gen - total;
    const keep = mode === "fresh" ? scene.trim.keep : "start";
    if (keep === "middle") keepIn = Math.floor(spare / 2);
    else if (keep === "end") keepIn = spare;
    else if (keep === "custom") keepIn = Math.min(spare, Math.max(0, framesOf(scene.trim.in)));
    segs = [[0, gen, total, "none", firstOverlap]];
  } else {
    const maxF = Math.max(MIN_PASS_FRAMES, alignFramesDown(Math.min(MAX_PASS_FRAMES, Math.trunc(lg.max_pass_frames))));
    const ov = Math.min(alignFramesDown(Math.max(5, Math.trunc(lg.overlap_frames))), alignFramesDown(Math.floor(maxF / 2)));
    segs = segmentsOf(scene, total, maxF, ov, lg.seam_mode, framesOf(lg.cut_snap_seconds), firstOverlap);
    kind = segs.length === 1 ? "single" : "long";
  }
  const ranges = shotRangesOf(scene, total, duration);
  const passes = segs.map(([s, gen, keepFrames, seam, ovIn], i) => {
    const end = s + keepFrames;
    const freshFrom = i > 0 ? s + ovIn : s;
    const shots = [];
    for (const [number, sh, a, b] of ranges) {
      if (b <= s || a >= end) continue;
      shots.push({ id: sh.id, number, continuing: a < s, t: (Math.max(a, s) - s + keepIn) / FPS, camera: sh.camera, text: sh.text });
    }
    const dialogue = [];
    for (const d of scene.dialogue) {
      const f = clampFrame(d.t, duration, total);
      if (f !== null && freshFrom <= f && f < end) dialogue.push({ ...d, t: (f - s + keepIn) / FPS });
    }
    const keyframes = [], firsts = [], lasts = [];
    for (const r of scene.refs) {
      if (r.role === "keyframe") {
        const f = clampFrame(r.time, duration, total);
        if (f !== null && freshFrom <= f && f < end) keyframes.push({ ref: r.id, frame_idx: f - s + keepIn });
      } else if (r.role === "first_frame" && i === 0) firsts.push({ ref: r.id, frame_idx: keepIn });
      else if (r.role === "last_frame" && i === segs.length - 1) lasts.push({ ref: r.id, frame_idx: keepIn + keepFrames - 1 });
    }
    return {
      index: i + 1, start: (s - keepIn) / FPS, end: end / FPS, gen_frames: gen,
      keep_in: keepIn / FPS, keep_out: (keepIn + keepFrames) / FPS, keep_in_frames: keepIn, keep_out_frames: keepIn + keepFrames,
      seam_before: seam, overlap_frames: ovIn, seed: seed === null ? null : seed + i,
      shots, dialogue, keyframes, first_frame: firsts, last_frame: lasts,
    };
  });
  return { scene_id: scene.id, kind, duration, frames: total, start_mode: mode, declared_start_mode: declared, seed, passes,
    generated_frames: passes.reduce((t, x) => t + x.gen_frames, 0) };
}

export function budgetIssues(b) {
  const out = [];
  if (b.pictures > 9) out.push(`${b.pictures} pictures (max 9)`);
  if (b.videos > 3) out.push(`${b.videos} videos (max 3)`);
  if (b.videoSeconds > 15.0001) out.push(`video refs ${b.videoSeconds.toFixed(1)} s (max 15 s)`);
  if (b.audio > 3) out.push(`${b.audio} audio refs (max 3)`);
  if (b.audioSeconds > 15.0001) out.push(`audio refs ${b.audioSeconds.toFixed(1)} s (max 15 s)`);
  if (b.files > 12) out.push(`${b.files} files (max 12)`);
  return out;
}

export function assetUsage(project, assetId) {
  const out = [];
  project.scenes.forEach((s, i) => {
    for (const r of s.refs) if (r.asset === assetId) out.push({ scene: s, index: i, ref: r });
  });
  return out;
}

export function assetCastUse(project, assetId) {
  const out = [];
  for (const c of project.cast) {
    const scenes = project.scenes.filter(s => s.cast.some(x => x.id === c.id)).length;
    if (c.anchors.includes(assetId)) out.push({ cast: c, as: "anchor", scenes });
    if (c.voice === assetId) out.push({ cast: c, as: "voice", scenes });
  }
  return out;
}

// added 2026-11-02 v0.3.4: mirrors cast_description in reelwright/model.py. A cast member without its own
// description uses the description of its first anchor picture that has one.
const tidy = t => (t || "").trim().replace(/\.+$/, "");
export function castDescription(project, c) {
  const own = tidy(c.description);
  if (own) return { text: own, asset: null };
  for (const id of c.anchors || []) {
    const a = findAsset(project, id);
    if (a && a.kind === "image" && tidy(a.description)) return { text: tidy(a.description), asset: a };
  }
  return { text: "", asset: null };
}

// added 2026-11-02 v0.3.4: every place an asset's description ends up (or why it doesn't)
export function descriptionUses(project, assetId) {
  const out = [];
  project.scenes.forEach((s, i) => {
    for (const r of s.refs) if (r.asset === assetId) out.push({ how: r.role === "reference" ? "ref" : "guide", scene: s, index: i });
  });
  for (const c of project.cast) {
    const scenes = project.scenes.filter(s => s.cast.some(x => x.id === c.id) || s.dialogue.some(d => d.speaker === c.id)).length;
    if (c.anchors.includes(assetId)) {
      const d = castDescription(project, c);
      out.push({ how: d.asset?.id === assetId ? "cast" : d.asset ? "castOther" : d.text ? "castOwn" : "castNone", cast: c, scenes, by: d.asset });
    }
    if (c.outfits.some(o => (o.assets || []).includes(assetId))) out.push({ how: "outfit", cast: c, scenes });
  }
  return out;
}

// Chains of scenes linked by continuation (last frame or tail).
export function continuityChains(project) {
  const chains = [];
  for (const s of project.scenes) {
    if (s.start.mode === "fresh" || !chains.length) chains.push([s]);
    else chains[chains.length - 1].push(s);
  }
  return chains;
}

// ---- tags (added 2026-11-03 v0.6.0, PLAN "Tag syntax"; prompt.py TAG_RE and prompttext.js use the same rule) ----
// A tag is @ + a name of letters, digits and _ runs joined by single ' ’ - or . (a trailing one is not part of it:
// "@Anna." is Anna). Not a tag after a letter, digit, _ or @ (e-mail addresses stay text); @@ is a literal @.
const TAG_NAME = "[\\p{L}\\p{N}\\p{M}_]+(?:['\u2019.\\-][\\p{L}\\p{N}\\p{M}_]+)*";
// A fresh global regex for tags (group 1 = the name); new each call because /g regexes keep lastIndex.
export function tagRegex() {
  return new RegExp("(?<![\\p{L}\\p{N}\\p{M}_@])@(?!@)(" + TAG_NAME + ")", "gu");
}
const TAG_NAME_RE = new RegExp("^" + TAG_NAME + "$", "u");
// Whether `name` can be written as @name (otherwise @{name}).
export function isTagName(name) {
  return TAG_NAME_RE.test(text(name));
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] \w is ASCII-only in JS ("@Ömer" became "@{Ömer}"), "O'Brien" needed braces, empty
// names gave "@{}", a muted-asset or missing-file track still offered @soundtrack
export function tagCandidates(project) {
  const out = project.assets.map(a => ({ tag: "@" + a.code, label: a.name || a.code, kind: a.kind }));
  for (const c of project.cast) {
    const tag = /^[\w-]+$/.test(c.name) ? "@" + c.name : "@{" + c.name + "}";
    out.push({ tag, label: c.kind, kind: "cast" });
  }
  out.push({ tag: "@tail", label: "previous scene's tail clip", kind: "video" });
  // added 2026-11-03 v0.5.0: the part of the soundtrack a pass is sent
  if (project.soundtrack?.some(t => t.sync && !t.mute)) out.push({ tag: "@soundtrack", label: "the song this part is cut to", kind: "audio" });
  return out;
}
[/OLD] */
export function tagCandidates(project) {
  const out = project.assets.filter(a => a.code).map(a => ({ tag: "@" + a.code, label: a.name || a.code, kind: a.kind }));
  for (const c of project.cast) {
    if (!c.name) continue;
    out.push({ tag: isTagName(c.name) ? "@" + c.name : "@{" + c.name + "}", label: c.kind, kind: "cast" });
  }
  out.push({ tag: "@tail", label: "previous scene's tail clip", kind: "video" });
  // the part of the soundtrack a pass is sent (v0.5.0); a pass without the song writes it as plain text
  if (playingTracks(project).some(({ t }) => t.sync)) out.push({ tag: "@soundtrack", label: "the song this part is cut to", kind: "audio" });
  return out;
}
