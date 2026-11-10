// Project schema 1: defaults, normalization and the small amount of H3 math the
// editor needs for instant feedback. The backend planner stays authoritative.

export const FPS = 24;
export const MIN_PASS_FRAMES = 124;
export const MAX_PASS_FRAMES = 362;

export const STABLE_LANGUAGES = ["Arabic", "Chinese", "English", "French", "German", "Italian",
  "Japanese", "Korean", "Portuguese", "Russian", "Spanish"];
export const VISUAL_RETENTION = ["fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"];
export const AUDIO_RETENTION = ["fully_copy", "partially_copy", "reference", "weak_reference"];
// [OLD 2026-11-08 v0.11.0->v0.12.0] export const ROLES = ["reference", "first_frame", "last_frame", "keyframe"];
export const ROLES = ["reference", "first_frame", "last_frame", "keyframe", "pose"]; // v0.12.0: pose (poseRefs)
export const START_MODES = ["fresh", "last_frame", "tail"];
// added 2026-11-05 v0.8.0: Global -> Long scenes -> hand-off and pass cache (model.py LONG_HANDOFF / LONG_PASS_CACHE)
export const LONG_HANDOFF = ["pixels", "latent"];
export const LONG_PASS_CACHE = ["near_lossless", "lossless"];
export const SUBTITLE_TIMING = ["speech", "planned"]; // added 2026-11-06 v0.10.0: global.merge.subtitle_timing
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
/* [OLD 2026-11-10 v0.18.0->v0.19.0] no hires overrides
export const OVERRIDE_KEYS = ["seed", "steps", "sampler", "scheduler", "width", "height",
  "diffusion", "text_encoder", "video_vae", "audio_vae", "quality"];
[/OLD] */
// added 2026-11-10 v0.19.0: hires ("off"), refine_steps, refine_denoise (model.py the same)
export const OVERRIDE_KEYS = ["seed", "steps", "sampler", "scheduler", "width", "height",
  "diffusion", "text_encoder", "video_vae", "audio_vae", "quality", "hires", "refine_steps", "refine_denoise"];
export const TRANSITIONS = ["cut", "crossfade", "dip"]; // added 2026-11-02 v0.3.0
// added 2026-11-05 v0.7.0: scene.merge (same values as reelwright/model.py). TRANSITIONS stays for the deprecated
// scene.transition (read once, by the migration in normMerge)
export const MERGE_TRANSITIONS = ["cut", "crossfade", "dip", "wipe", "slide", "circle", "dissolve", "pixelize", "radial", "zoom"];
export const MERGE_DIRECTIONS = ["left", "right", "up", "down"];
export const COLOR_MATCH_MODES = ["off", "previous", "scene"];
export const MERGE_MAX_FRAMES = 14400; // frame counts in scene.merge: 0 .. 600 s
const COLOR_RE = /^#[0-9a-fA-F]{6}$/;

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
    // [OLD 2026-11-10 v0.18.0->v0.19.0] draft: { scale: 0.5, steps: 8, lora: "", lora_strength: 1.0 },
    draft: { scale: 0.5, steps: 8, lora: "", lora_strength: 1.0, hires: false }, // hires: added 2026-11-10 v0.19.0
    // added 2026-11-10 v0.19.0: Global → Hires, the latent upscaler (see reelwright/model.py default_global)
    hires: { enabled: false, scale: 2.0, refine_steps: 0, refine_denoise: 0.35 },
    defaults: { duration: 8.0, start_mode: "last_frame", overlap_frames: 39, language: "English" },
    // [OLD 2026-11-05 v0.7.0->v0.8.0] long: { max_pass_frames: 362, overlap_frames: 39, crossfade_frames: 12, seam_mode: "auto", cut_snap_seconds: 2.0 },
    // added 2026-11-05 v0.8.0: long-scene continuity switches (see reelwright/model.py default_global); the defaults keep
    // v0.7.0's behaviour and cache keys
    long: { max_pass_frames: 362, overlap_frames: 39, crossfade_frames: 12, seam_mode: "auto", cut_snap_seconds: 2.0,
      guide_vae: "", carry_audio: true, seam_video_ref: true, handoff: "pixels", pass_cache: "near_lossless" },
    memory: { policy: "free_cache", encode_first: true, group_by_lora: true },
    // [OLD 2026-11-05 v0.6.1->v0.7.0] continuity: { reanchor_after: 2, face_check: false, face_threshold: 0.8, on_drift: "flag" },
    // added 2026-11-05 v0.7.0: name_continuation: the frame or clip a continuing scene (or a pass after an overlap seam)
    // starts from is also sent as <Picture 1> / <Video 1> and named in the prompt (false: anchored only, as v0.6.1)
    // [OLD 2026-11-06 v0.9.0->v0.10.0] continuity: { reanchor_after: 2, face_check: false, face_threshold: 0.8, on_drift: "flag", name_continuation: true },
    // added 2026-11-06 v0.10.0: describe_voices: a speaker's voice description (cast voice_desc) goes into every pass
    continuity: { reanchor_after: 2, face_check: false, face_threshold: 0.8, on_drift: "flag", name_continuation: true, describe_voices: true },
    /* [OLD 2026-11-02 v0.1.0->v0.2.0] no switch for sending MiniMax's prompt guides
    llm: { base_url: "", model: "", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va" },
    [/OLD] */
    // [OLD 2026-11-02 v0.3.1->v0.3.2] llm: { base_url: "", model: "", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va", include_guides: true },
    // [OLD 2026-11-03 v0.4.1->v0.4.2] llm: { base_url: "", model: "", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va", include_guides: true, thinking: "auto" },
    llm: { base_url: "", model: "", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va", include_guides: true, thinking: "auto",
      // added 2026-11-03 v0.4.2: limits (see reelwright/model.py)
      timeout_s: 120, max_wait_s: 900, retries: 2, context_tokens: 0,
      // [OLD 2026-11-05 v0.7.0->v0.8.0] import_part_chars: 3000, import_max_tokens: 16384, import_thinking: "same", import_guides: false },
      // added 2026-11-05 v0.8.0: import_max_tokens 24576 (llm.IMPORT_MAX_TOKENS): shots are 2-4 sentences now
      import_part_chars: 3000, import_max_tokens: 24576, import_thinking: "same", import_guides: false },
    merge: { use: "starred", missing: "skip", hard_cut: "cut", transition_frames: 12, audio_fade_frames: 6,
      loudness: -16.0, normalize: true, score: { asset: "", volume_db: -12.0, duck: true }, // v0.5.0: score moves to p.soundtrack on load
      scene_audio: { mix: false, volume_db: -12.0 }, // added 2026-11-03 v0.5.0: the scenes' own sound under a soundtrack
      color_match: false, color_ref_scene: "", codec: "h264", crf: 16,
      // [OLD 2026-11-06 v0.9.0->v0.10.0] subtitles: true, chapters: true, otio: true, fcpxml: true, bundle: false, auto_after_render: true },
      // added 2026-11-06 v0.10.0: subtitle_timing "speech" (timed to each take's speech) or "planned"
      subtitles: true, subtitle_timing: "speech", chapters: true, otio: true, fcpxml: true, bundle: false, auto_after_render: true },
  };
}

/* [OLD 2026-11-05 v0.7.0->v0.8.0] six presets of our own; new projects now start with H3's 20 official moves
const DEFAULT_CAMERA = [
  ["Slow push-in", "slow push-in toward the subject"],
  ["Locked-off", "static locked-off camera"],
  ["Crane up", "slow crane up revealing the scene"],
  ["Handheld pan →", "handheld camera panning right"],
  ["Rack focus", "rack focus from foreground to background"],
  ["Macro", "macro close-up, shallow depth of field"],
];
[/OLD] */
// added 2026-11-05 v0.8.0: the camera moves of MiniMax's H3 guide (base-en.txt 4.3), same as model.py DEFAULT_CAMERA:
// [name = the guide's label, text = the phrase written into the shot line]. Older projects get the missing ones
// appended once (camera_version 2, migrateCamera); their own presets stay.
export const DEFAULT_CAMERA = [
  ["Zoom In", "the camera zooms in"], ["Zoom Out", "the camera zooms out"],
  ["Push In", "the camera pushes in"], ["Pull Out", "the camera pulls out"],
  ["Pan Left", "the camera pans left"], ["Pan Right", "the camera pans right"],
  ["Truck Left", "the camera trucks left"], ["Truck Right", "the camera trucks right"],
  ["Tilt Up", "the camera tilts up"], ["Tilt Down", "the camera tilts down"],
  ["Pedestal Up", "the camera pedestals up"], ["Pedestal Down", "the camera pedestals down"],
  ["Arc Shot", "the camera arcs around the subject"],
  ["Tracking Shot", "the camera tracks the moving subject"],
  ["Static Shot", "the camera holds a static shot"],
  ["Shake Slightly", "the camera shakes slightly"], ["Shake Strongly", "the camera shakes strongly"],
  ["POV", "the camera takes the subject's point of view"],
  ["Roll Clockwise", "the camera rolls clockwise"],
  ["Roll Counterclockwise", "the camera rolls counterclockwise"],
];
export const CAMERA_VERSION = 2; // added 2026-11-05 v0.8.0: project.camera_version (model.py)
// added 2026-11-05 v0.8.0: shot fields camera_amp / camera_speed / framing ("" = not said), as model.py
export const CAMERA_AMPS = ["", "small", "large"];
export const CAMERA_SPEEDS = ["", "slow", "fast"];
export const FRAMINGS = ["", "extreme wide", "wide", "medium wide", "medium", "medium close-up", "close-up", "extreme close-up",
  "over-the-shoulder", "two-shot", "insert", "low angle", "high angle", "overhead", "dutch angle"];
export const FRAMING_PHRASE = {
  "extreme wide": "an extreme wide shot", wide: "a wide shot", "medium wide": "a medium-wide shot",
  medium: "a medium shot", "medium close-up": "a medium close-up", "close-up": "a close-up",
  "extreme close-up": "an extreme close-up", "over-the-shoulder": "an over-the-shoulder shot",
  "two-shot": "a two-shot", insert: "an insert shot", "low angle": "a low-angle shot",
  "high angle": "a high-angle shot", overhead: "an overhead shot", "dutch angle": "a Dutch-angle shot",
};
export const DIALOGUE_MAX_SECONDS = 600; // added 2026-11-05 v0.8.0

/* [OLD 2026-11-05 v0.7.0->v0.8.0] no "passes" (each pass's own sections)
export function defaultPrompt() {
  const sections = {};
  for (const k of SECTION_KEYS) sections[k] = "";
  return { mode: "structured", auto: { subjects: true, retention: true, shots: true }, sections, raw: "", pass_prompts: {} };
}
[/OLD] */
export function defaultPrompt() {
  const sections = {};
  for (const k of SECTION_KEYS) sections[k] = "";
  // passes: added 2026-11-05 v0.8.0 (see passTexts)
  // [OLD 2026-11-09 v0.14.4->v0.15.0] no brief field
  // return { mode: "structured", auto: { subjects: true, retention: true, shots: true }, sections, raw: "", pass_prompts: {}, passes: [] };
  // [/OLD]
  // brief: added 2026-11-09 v0.15.0, the author's own words for Write prompts; never overwritten by what the LLM
  // writes (model.py default_prompt)
  return { mode: "structured", auto: { subjects: true, retention: true, shots: true }, sections, raw: "", pass_prompts: {}, passes: [], brief: "" };
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
    // added 2026-11-05 v0.7.0: how the scene sits in the cut (replaces "transition" and Global -> Merge's transition
    // and colour-match settings)
    merge: defaultMerge(),
    pass_names: {}, // added 2026-11-10 v0.19.0: names of the scene's passes (passNames)
    ...patch,
  };
}

// added 2026-11-05 v0.7.0: scene.merge of a new scene (model.py default_merge): how it sits in the cut. transition:
// how a fresh start joins the scene before (MERGE_TRANSITIONS), direction for wipe / slide, frames its length, color
// the dip colour; audio_frames: the sound's fade out / in at a cut; fade_in / fade_out: the picture from / to a colour
// at the scene's first / last frame; audio_fade_in / _out (frames); volume_db and mute: the scene's own sound;
// color_match: off | previous | scene (color_ref: that scene's id); brightness, contrast, saturation: ffmpeg eq.
export function defaultMerge() {
  return { transition: "cut", direction: "left", frames: 12, color: "#000000", audio_frames: 6,
    fade_in: { frames: 0, color: "#000000" }, fade_out: { frames: 0, color: "#000000" },
    audio_fade_in: 0, audio_fade_out: 0, volume_db: 0.0, mute: false,
    color_match: "off", color_ref: "", brightness: 0.0, contrast: 1.0, saturation: 1.0 };
}

export function defaultProject(name = "Untitled") {
  const p = {
    // [OLD 2026-11-03 v0.5.1->v0.6.0] schema: 1, id: newId("p"), name, slug: slugify(name),
    // project_id (added 2026-11-03 v0.6.0): who owns the folder; /autosave refuses another project's folder
    schema: 1, id: newId("p"), project_id: newId("p"), name, slug: slugify(name),
    global: defaultGlobal(), assets: [], cast: [],
    asset_groups: [], // added 2026-11-06 v0.9.0: groups of assets (Assets tab)
    camera_presets: DEFAULT_CAMERA.map(([n, t]) => ({ id: newId("k"), name: n, text: t })),
    camera_version: CAMERA_VERSION, // added 2026-11-05 v0.8.0: the presets are H3's official moves
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
  // added 2026-11-05 v0.8.0: the long-scene continuity choices (model.py normalize_global the same)
  if (!LONG_HANDOFF.includes(out.long.handoff)) out.long.handoff = "pixels";
  if (!LONG_PASS_CACHE.includes(out.long.pass_cache)) out.long.pass_cache = "near_lossless";
  if (!SUBTITLE_TIMING.includes(out.merge.subtitle_timing)) out.merge.subtitle_timing = "speech"; // added 2026-11-06 v0.10.0
  // added 2026-11-10 v0.19.0: Global → Hires (model.py normalize_global the same)
  const hi = out.hires;
  hi.scale = Math.min(HIRES_MAX_SCALE, Math.max(1, hi.scale));
  hi.refine_steps = Math.min(100, Math.max(0, Math.trunc(hi.refine_steps)));
  hi.refine_denoise = Math.min(1, Math.max(0.01, hi.refine_denoise));
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
  normAssetGroups(p, assets); // added 2026-11-06 v0.9.0

  p.cast = objects(p.cast);
  for (const c of p.cast) normCast(c, lang);

  const used = new Set();
  p.scenes = objects(p.scenes);
  for (const s of p.scenes) normScene(s, g.defaults, lang, used);
  if (!p.scenes.length) p.scenes.push(defaultScene(p, { title: "Scene 1" }));
  repairSeedNs(p.scenes);
  // added 2026-11-05 v0.7.0: scene.merge; a scene without one gets it from its v0.6 transition and Global -> Merge
  const sceneIds = new Set(p.scenes.map(s => s.id));
  for (const s of p.scenes) normMerge(s, g.merge, p.scenes[0].id, sceneIds);

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
  migrateCamera(p); // added 2026-11-05 v0.8.0: H3's official camera moves, appended once (camera_version 2)

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

// added 2026-11-05 v0.8.0 (model.py _migrate_camera): a project saved before v0.8.0 (camera_version below 2) gets H3's
// official camera moves it does not have yet (by name, without case) appended once; its own presets stay.
const cameraKey = name => text(name).replace(/^[ \t\n\r]+|[ \t\n\r]+$/g, "").toLowerCase();
export function migrateCamera(p) {
  const cv = num(p.camera_version, 0);
  if (cv < CAMERA_VERSION) {
    const have = new Set(p.camera_presets.map(k => cameraKey(k.name)));
    for (const [name, txt] of DEFAULT_CAMERA) {
      if (!have.has(cameraKey(name))) p.camera_presets.push({ id: newId("k"), name, text: txt });
    }
    p.camera_version = CAMERA_VERSION;
  } else p.camera_version = Math.trunc(Math.min(cv, 1000000));
  return p;
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

// added 2026-11-05 v0.8.0 (model.py _norm_pass_text): one entry of scene.prompt.passes: {start, end (scene seconds of the
// pass when its text was written), sections: the six sections as text}; anything else becomes an empty entry (0, 0).
function normPassText(x) {
  x = isObj(x) ? x : {};
  x.start = num(x.start, 0);
  x.end = num(x.end, 0);
  const sec = x.sections = isObj(x.sections) ? x.sections : {};
  for (const k of SECTION_KEYS) textField(sec, k, "");
  return x;
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

// added 2026-11-06 v0.9.0 (model.py _norm_asset_groups): the asset groups, in their order: {id, name, description}
// with unique ids; each asset's group is one of their ids or "" (no group), and its tags are cleaned by assetTags.
// Groups and tags only sort the Assets tab: no prompt, plan or cache key reads them.
function normAssetGroups(p, assets) {
  const groups = p.asset_groups = objects(p.asset_groups);
  const ids = new Set();
  for (const gr of groups) {
    gr.id = uniqueId(gr.id, "g", ids);
    textField(gr, "name", "");
    textField(gr, "description", "");
  }
  for (const a of assets) {
    textField(a, "group", "");
    if (!ids.has(a.group)) a.group = "";
    a.tags = assetTags(a.tags);
  }
}

// added 2026-11-06 v0.9.0: the name of an asset's group ("" when it has none, or the group has no name); pickers show it
// before the asset (visual only)
export function assetGroupName(project, a) {
  if (!a?.group) return "";
  const g = (project?.asset_groups || []).find(x => x.id === a.group);
  return g ? String(g.name || "").trim() : "";
}

// added 2026-11-06 v0.9.0 (model.py asset_tags): the strings (and numbers) of a list with runs of spaces, tabs and line
// breaks made one space, cut to 60 characters and trimmed; empty and repeated tags (same spelling) are dropped
export const TAG_MAX = 60;
// added 2026-11-10 v0.19.0: scene.pass_names {"<pass number>": name} (model.py pass_names, the same rules)
export const PASS_NAME_MAX = 60;
export function passNames(v) {
  const out = {};
  if (!isObj(v)) return out;
  for (const [k, x] of Object.entries(v)) {
    const t = text(x, null);
    if (!/^[1-9][0-9]{0,2}$/.test(k) || t === null) continue;
    const name = Array.from(t.replace(/[ \t\n\r]+/g, " ")).slice(0, PASS_NAME_MAX).join("").replace(/^ +| +$/g, "");
    if (name) out[k] = name;
  }
  return out;
}
// "Pass 2 · Harbour", or "Pass 2" without a name (the number is always first); k is 1-based
// [OLD 2026-11-10 v0.19.0 bug search] passLabel had no count, so "Pass 3 of 3" became "Pass 3 (of 3)" where the count shows
// export function passLabel(scene, k) {
//   const name = scene?.pass_names?.[String(k)];
//   return name ? `Pass ${k} · ${name}` : `Pass ${k}`;
// }
// [/OLD]
// of: the number of passes, for "Pass 3 of 3 · Harbour" (added 2026-11-10 v0.19.0 bug search)
export function passLabel(scene, k, of = 0) {
  const name = scene?.pass_names?.[String(k)];
  const head = of ? `Pass ${k} of ${of}` : `Pass ${k}`;
  return name ? `${head} · ${name}` : head;
}

export function assetTags(v) {
  const out = [];
  for (const x of texts(v)) {
    const t = Array.from(x.replace(/[ \t\n\r]+/g, " ")).slice(0, TAG_MAX).join("").replace(/^ +| +$/g, "");
    if (t && !out.includes(t)) out.push(t);
  }
  return out;
}

function normCast(c, lang) {
  c.id = text(c.id) || newId("c");
  c.kind = CAST_KINDS.includes(c.kind) ? c.kind : "character";
  // [OLD 2026-11-06 v0.9.0->v0.10.0] for (const k of ["name", "speaker", "description", "default_outfit", "voice"]) textField(c, k, "");
  for (const k of ["name", "speaker", "description", "default_outfit", "voice", "voice_desc"]) textField(c, k, ""); // added 2026-11-06 v0.10.0: voice_desc
  textField(c, "part_of", ""); // added 2026-11-08 v0.11.0: a prop that is part of this character (see partOwner)
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
  // added 2026-11-09 v0.16.0: video anchors [{id, asset, in, out, soundtrack}] (model.py _norm_cast, pickVideoAnchors)
  c.video_anchors = objects(c.video_anchors);
  const used = new Set();
  for (const va of c.video_anchors) {
    va.id = uniqueId(va.id, "va", used);
    textField(va, "asset", "");
    va.in = snapFrame(Math.max(0, num(va.in, 0)));
    const o = num(va.out, null);
    va.out = o === null || o <= 0 ? null : snapFrame(o);
    va.soundtrack = flag(va.soundtrack, false);
    // added 2026-11-10 v0.18.0: a frame of the clip as a picture (model.py _norm_cast): frame = its time in the file
    // (whole frames, null = none), frame_asset = the image asset made from it (offered under Anchors → + Add anchor)
    const fr = num(va.frame, null);
    va.frame = fr === null || fr < 0 ? null : snapFrame(fr);
    textField(va, "frame_asset", "");
  }
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
    textField(r, "cast", ""); // added 2026-11-08 v0.12.0: the character a pose reference is for
    textField(r, "retention", "");
    r.keep = texts(r.keep);
    r.soundtrack = flag(r.soundtrack, false);
    // added 2026-11-08 v0.14.0: the part of a video or audio asset the reference sends (refClip), on whole frames
    r.in = snapFrame(Math.max(0, num(r.in, 0)));
    const o = num(r.out, null);
    r.out = o === null || o <= 0 ? null : snapFrame(o);
  }
  const cast = [];
  for (let e of Array.isArray(s.cast) ? s.cast : []) {
    if (typeof e === "string") e = { id: e, outfit: "" };
    if (!isObj(e)) continue;
    textField(e, "id", "");
    textField(e, "outfit", "");
    // added 2026-11-10 v0.18.0: the anchors this scene leaves out (picture asset ids, video anchor ids); [] = all
    e.skip = [...new Set(texts(e.skip))];
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
    // added 2026-11-05 v0.8.0: H3's camera amplitude and speed (base-en.txt 4.3) and the shot size / angle
    for (const [k, allowed] of [["camera_amp", CAMERA_AMPS], ["camera_speed", CAMERA_SPEEDS], ["framing", FRAMINGS]]) {
      x[k] = allowed.includes(x[k]) ? x[k] : "";
    }
  }
  s.shots.sort((a, b) => a.t - b.t);
  used = new Set();
  s.dialogue = objects(s.dialogue);
  for (const x of s.dialogue) {
    x.id = uniqueId(x.id, "d", used);
    x.t = num(x.t, 0);
    for (const k of ["speaker", "delivery", "text"]) textField(x, k, "");
    textField(x, "language", lang);
    // added 2026-11-05 v0.8.0: how long the line is spoken (seconds > 0), null = estimated (dialogueSeconds)
    const dur = num(x.duration, null);
    x.duration = dur !== null && dur > 0 ? Math.min(dur, DIALOGUE_MAX_SECONDS) : null;
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
  textField(pr, "brief", ""); // added 2026-11-09 v0.15.0: the Write prompts brief (defaultPrompt)
  const pp = isObj(pr.pass_prompts) ? pr.pass_prompts : {};
  pr.pass_prompts = Object.fromEntries(Object.entries(pp).filter(([, v]) => text(v, null) !== null).map(([k, v]) => [k, text(v)]));
  // added 2026-11-05 v0.8.0: each pass's own six sections (see passTexts); an item that is not an object becomes an
  // empty entry, so the pass numbers of the others stay
  pr.passes = Array.isArray(pr.passes) ? pr.passes.map(normPassText) : [];

  const o = s.overrides = isObj(s.overrides) ? s.overrides : {};
  // [OLD 2026-11-10 v0.18.0->v0.19.0] for (const k of ["seed", "steps", "width", "height"]) {
  for (const k of ["seed", "steps", "width", "height", "refine_steps"]) { // refine_steps: added 2026-11-10 v0.19.0
    if (!Object.hasOwn(o, k)) continue;
    const v = num(o[k], null);
    if (v === null) delete o[k]; // "" or junk: follow Global
    else o[k] = Math.trunc(v);
  }
  for (const k of ["sampler", "scheduler", "diffusion", "text_encoder", "video_vae", "audio_vae", "quality"]) {
    if (Object.hasOwn(o, k) && typeof o[k] !== "string") delete o[k];
  }
  // added 2026-11-10 v0.19.0: the hires overrides (model.py the same)
  if (Object.hasOwn(o, "refine_steps")) o.refine_steps = Math.min(100, Math.max(0, o.refine_steps));
  if (Object.hasOwn(o, "refine_denoise")) {
    const v = num(o.refine_denoise, null);
    if (v === null) delete o.refine_denoise;
    else o.refine_denoise = Math.min(1, Math.max(0.01, v));
  }
  if (Object.hasOwn(o, "hires") && o.hires !== "off") delete o.hires; // only "off" means something
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
  s.pass_names = passNames(s.pass_names); // added 2026-11-10 v0.19.0
  const tn = s.transition = isObj(s.transition) ? s.transition : {};
  tn.mode = ["", ...TRANSITIONS].includes(tn.mode) ? tn.mode : "";
  for (const k of ["frames", "audio_fade_frames"]) tn[k] = num(tn[k], null);
}

// ---- scene.merge (added 2026-11-05 v0.7.0; model.py _norm_merge / _migrated_merge are the same) ----
// a frame count of scene.merge: a whole number 0 .. MERGE_MAX_FRAMES (fractions are cut off)
function mergeFrames(v, dflt) {
  return Math.min(MERGE_MAX_FRAMES, Math.max(0, Math.trunc(num(v, dflt))));
}
// "#rrggbb" in lower case; anything else is black
function mergeColor(v) {
  return typeof v === "string" && COLOR_RE.test(v) ? v.toLowerCase() : "#000000";
}
function clampNum(v, dflt, lo, hi) {
  return Math.min(hi, Math.max(lo, num(v, dflt)));
}
// scene.merge for a scene saved before v0.7.0, built so it merges exactly as before: the scene's own transition mode or
// Global -> Merge -> hard cut (an unknown one was a cut), its own length and audio fade or the global ones; with Global
// colour match on, every scene but the reference matches the reference scene (Global's colour reference scene, or the
// first scene when that is empty or gone)
function migratedMerge(s, gm, firstId, sceneIds) {
  const tn = isObj(s.transition) ? s.transition : {};
  const hard = gm.hard_cut;
  const m = defaultMerge();
  m.transition = tn.mode || (TRANSITIONS.includes(hard) ? hard : "cut");
  m.frames = tn.frames !== undefined && tn.frames !== null ? tn.frames : gm.transition_frames;
  m.audio_frames = tn.audio_fade_frames !== undefined && tn.audio_fade_frames !== null ? tn.audio_fade_frames : gm.audio_fade_frames;
  if (gm.color_match === true) {
    const ref = sceneIds.has(gm.color_ref_scene) ? gm.color_ref_scene : firstId;
    if (s.id !== ref) { m.color_match = "scene"; m.color_ref = ref; }
  }
  return m;
}
// scene.merge in place (see defaultMerge). gm: the normalised Global -> Merge; firstId, sceneIds: the project's first
// scene id and every scene id (for the migration of a scene that has no merge object).
function normMerge(s, gm, firstId, sceneIds) {
  let m = s.merge;
  if (!isObj(m)) m = migratedMerge(s, gm, firstId, sceneIds);
  m.transition = MERGE_TRANSITIONS.includes(m.transition) ? m.transition : "cut";
  m.direction = MERGE_DIRECTIONS.includes(m.direction) ? m.direction : "left";
  m.frames = mergeFrames(m.frames, 12);
  m.color = mergeColor(m.color);
  m.audio_frames = mergeFrames(m.audio_frames, 6);
  for (const k of ["fade_in", "fade_out"]) {
    const f = m[k] = isObj(m[k]) ? m[k] : {};
    f.frames = mergeFrames(f.frames, 0);
    f.color = mergeColor(f.color);
  }
  for (const k of ["audio_fade_in", "audio_fade_out"]) m[k] = mergeFrames(m[k], 0);
  m.volume_db = clampNum(m.volume_db, 0, -60, 24);
  m.mute = flag(m.mute, false);
  m.color_match = COLOR_MATCH_MODES.includes(m.color_match) ? m.color_match : "off";
  textField(m, "color_ref", "");
  m.brightness = clampNum(m.brightness, 0, -1, 1);
  m.contrast = clampNum(m.contrast, 1, 0, 2);
  m.saturation = clampNum(m.saturation, 1, 0, 3);
  s.merge = m;
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
  // added 2026-11-10 v0.19.0: Global → Hires ("" = as Global; a scene can only turn it "off")
  hires: () => "", refine_steps: g => g.hires.refine_steps, refine_denoise: g => g.hires.refine_denoise,
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
/* [OLD 2026-11-05 v0.6.1->v0.7.0] did not count the continuation picture (<Picture 1> of a last-frame start)
export function sceneAutoPacks(project, scene) {
  return scenePeople(project, scene).autoPack;
}
[/OLD] */
// added 2026-11-05 v0.7.0: the first pass's continuation picture takes a slot too (as sceneBudget / prompt.collect_refs)
export function sceneAutoPacks(project, scene) {
  const sp = scenePeople(project, scene);
  if (sp.autoPack) return true;
  const i = sceneIndex(project, scene.id);
  if (i <= 0) return false;
  const first = planScene(project, scene, i).passes[0];
  return !!first && passContinuation(project, i, first) === "picture" && sp.unpacked + 1 > MAX_REF_IMAGES;
}

// added 2026-11-08 v0.11.0: a prop can be part of a character (Cast → Prop → Part of), as model.part_owner: its pictures
// and description go into that character's subject instead of a subject of its own. The character's id, or "".
export function partOwner(c, castById) {
  if (!c || c.kind !== "prop") return "";
  const owner = castById.get(c.part_of || "");
  return owner && owner.kind === "character" && owner.id !== c.id ? owner.id : "";
}

/* [OLD 2026-11-08 v0.10.3->v0.11.0] every cast member counted on its own (a prop that is part of a character now folds
   into that character, as model.scene_people)
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
[/OLD] */
// added 2026-11-03 v0.6.0: the cast a scene sends, as prompt.collect_refs / model.scene_media_counts: its cast list
// plus speakers missing from it, each with its anchor pictures and outfit pictures; autoPack: "auto" sheets pack.
// added 2026-11-08 v0.11.0: as model.scene_people: a part's pictures join its character's (after the character's own,
// each once); a part whose character is not in the scene is left out (leftOut: [{ part, owner }]).
// added 2026-11-10 v0.18.0: the anchors a scene's cast entry leaves out (model.py entry_skip), as a Set
export function entrySkip(entry) {
  return new Set(Array.isArray(entry?.skip) ? entry.skip : []);
}
export function scenePeople(project, scene) {
  const assets = new Map(project.assets.map(a => [a.id, a]));
  const cast = new Map(project.cast.map(c => [c.id, c]));
  const entries = [...scene.cast];
  for (const d of scene.dialogue) if (cast.has(d.speaker) && !entries.some(e => e.id === d.speaker)) entries.push({ id: d.speaker, outfit: "" });
  const present = new Set(entries.filter(e => cast.has(e.id)).map(e => e.id));
  const people = [], parts = new Map(), leftOut = [];
  for (const e of entries) {
    const c = cast.get(e.id);
    if (!c) continue;
    const outfit = c.outfits.find(o => o.id === (e.outfit || c.default_outfit));
    // [OLD 2026-11-10 v0.17.3->v0.18.0] const ids = c.anchors.filter(a => assets.get(a)?.kind === "image");  (every anchor in every scene)
    const skip = entrySkip(e); // added 2026-11-10 v0.18.0: the anchors the scene unticked stay out (model.cast_pictures)
    const ids = c.anchors.filter(a => assets.get(a)?.kind === "image" && !skip.has(a));
    if (outfit) ids.push(...outfit.assets.filter(a => assets.get(a)?.kind === "image" && !ids.includes(a)));
    const owner = partOwner(c, cast);
    if (owner) {
      if (present.has(owner)) { if (!parts.has(owner)) parts.set(owner, []); parts.get(owner).push({ c, outfit, ids }); }
      else leftOut.push({ part: c, owner: cast.get(owner) });
      continue;
    }
    // [OLD 2026-11-10 v0.17.3->v0.18.0] people.push({ c, ids, own: ids.slice(), parts: [] });
    people.push({ c, ids, own: ids.slice(), parts: [], entry: e }); // added 2026-11-10 v0.18.0: entry (its skip, for pickVideoAnchors)
  }
  for (const x of people) {
    for (const part of parts.get(x.c.id) || []) {
      x.parts.push(part);
      x.ids = x.ids.concat(part.ids.filter(a => !x.ids.includes(a)));
    }
  }
  const anchors = new Set(people.flatMap(x => x.ids));
  const refPics = new Set(scene.refs.filter(r => r.role === "reference" && assets.get(r.asset)?.kind === "image").map(r => r.asset));
  /* [OLD 2026-11-05 v0.6.1->v0.7.0] no unpacked count
  const autoPack = anchors.size + [...refPics].filter(a => !anchors.has(a)).length > MAX_REF_IMAGES;
  return { people, autoPack, assets };
  [/OLD] */
  // added 2026-11-05 v0.7.0: unpacked (pictures before packing) for sceneBudget's continuation picture
  const unpacked = anchors.size + [...refPics].filter(a => !anchors.has(a)).length;
  const autoPack = unpacked > MAX_REF_IMAGES;
  // [OLD 2026-11-08 v0.10.3->v0.11.0] return { people, autoPack, assets, unpacked };
  return { people, autoPack, assets, unpacked, leftOut }; // added 2026-11-08 v0.11.0: leftOut
}
// added 2026-11-08 v0.12.0: pose references, as model.pose_refs: a picture whose body pose one character of the scene
// takes in the shot at its time; it goes to the pass whose span holds that time. [{ r, a, c }]
// ---- added 2026-11-08 v0.14.0: clips of video and audio references (Sencer: "allow to select from-to timestamps/frames
// of source video. we should be able to use the same video/audio asset in a single scene multiple times, with different
// start/end timestamps/durations, with or without audio"). The same as model.py snap_frame, ref_trimmed, ref_clip,
// clip_key, media_ref_ids, ref_tokens (tests/test_model_parity.py compares them).

// t seconds on the nearest whole frame (half a frame rounds up).
export function snapFrame(t) {
  return Math.floor(Number(t) * FPS + 0.5) / FPS;
}
// Does reference r send only part of its asset (a From after 0 or a To)?
export function refTrimmed(r) {
  return !!r && typeof r === "object" && (num(r.in, 0) > 0 || num(r.out, 0) > 0);
}
// {start, end, seconds} of the part of video or audio asset a that reference r sends (end / seconds null when neither
// a To nor the asset's length is known).
export function refClip(r, a) {
  const start = Math.max(0, num(r?.in, 0));
  const o = num(r?.out, 0);
  const dur = num(a?.duration, 0);
  let end = o > 0 ? o : dur > 0 ? dur : null;
  if (end !== null && dur > 0) end = Math.min(end, dur);
  return { start, end, seconds: end === null ? null : Math.max(0, end - start) };
}
// What makes two references the same clip: [asset id, start, end] (end null when not trimmed, as a voice sample).
export function clipKey(r, a) {
  const c = refClip(r, a);
  return [a.id, c.start, refTrimmed(r) ? c.end : null];
}
const sameClip = (x, y) => x[0] === y[0] && x[1] === y[1] && x[2] === y[2];
// Ids of the scene's reference-role references on asset aid, in order (@V1 the first, @V1.2 the second ...).
export function mediaRefIds(scene, aid) {
  return (scene?.refs || []).filter(r => r && r.asset === aid && (r.role ?? "reference") === "reference").map(r => r.id);
}
// {ref id: "@V1" | "@V1.2"} for the scene's video and audio references.
export function refTokens(project, scene) {
  const out = {}, seen = new Map();
  for (const r of scene?.refs || []) {
    const a = findAsset(project, r.asset);
    if (!a || !["video", "audio"].includes(a.kind) || (r.role ?? "reference") !== "reference" || !a.code) continue;
    const n = (seen.get(a.id) || 0) + 1;
    seen.set(a.id, n);
    out[r.id] = "@" + a.code + (n === 1 ? "" : "." + n);
  }
  return out;
}

export function poseInPass(t, pass, duration) {
  const s = Number(pass.start), e = Number(pass.end);
  return (s <= t && t < e) || (t >= e && e >= Number(duration) - 1e-6);
}
export function poseTime(r, scene) {
  return Math.min(Math.max(Number(r.time) || 0, 0), Number(scene.duration));
}
export function poseRefs(project, scene, pass = null, people = null) {
  const assets = new Map(project.assets.map(a => [a.id, a]));
  if (!people) people = scenePeople(project, scene).people;
  const chars = new Map(people.filter(x => x.c.kind === "character").map(x => [x.c.id, x.c]));
  const out = [];
  for (const r of scene.refs) {
    if (r.role !== "pose") continue;
    const a = assets.get(r.asset), c = chars.get(r.cast || "");
    if (!a || a.kind !== "image" || !c) continue;
    if (pass && !poseInPass(poseTime(r, scene), pass, scene.duration)) continue;
    out.push({ r, a, c });
  }
  return out;
}
export function castPacks(project, scene, c) {
  // [OLD 2026-11-10 v0.17.3->v0.18.0] const n = c.anchors.filter(id => findAsset(project, id)?.kind === "image").length;  (every anchor, ticked or not)
  const n = sceneAnchorIds(project, scene, c).length; // added 2026-11-10 v0.18.0: the anchors the scene uses
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
// ---- added 2026-11-09 v0.16.0: video anchors (model.py video_anchors_of / pick_video_anchors, the same rules): sent to
// every pass of a scene the character is in, after everything else, while H3 takes 3 videos, 15 s of video in all and
// 12 files; a clip is shortened to the seconds left when at least 2 s are; its sound only when asked and a slot is free.
const REF_MEDIA_TOTAL_SECONDS = 15;
export function videoAnchorsOf(c, assets) {
  const get = id => (assets instanceof Map ? assets.get(id) : assets[id]);
  return (c.video_anchors || []).map(va => [va, get(va.asset)]).filter(([, a]) => a && a.kind === "video");
}
// people: scenePeople's records ({c}); n: {videos, videoSeconds, audio, audioSeconds, files}, updated
export function pickVideoAnchors(people, assets, n) {
  const picked = [], left = [];
  // [OLD 2026-11-10 v0.17.3->v0.18.0] for (const { c } of people) {
  for (const { c, entry } of people) {
    const skip = entrySkip(entry); // added 2026-11-10 v0.18.0: unticked in this scene: not sent, not counted
    for (const [va, a] of videoAnchorsOf(c, assets)) {
      if (skip.has(va.id)) continue;
      const clip = refClip(va, a);
      const full = Math.min(REF_MEDIA_MAX_SECONDS, clip.seconds !== null ? clip.seconds : REF_MEDIA_MAX_SECONDS);
      const room = REF_MEDIA_TOTAL_SECONDS - n.videoSeconds;
      const secs = full <= room + 1e-6 ? full : Math.floor(room * FPS + 1e-6) / FPS;
      const cut = secs < full - 1e-6;
      // [OLD 2026-11-09 v0.17.0->v0.17.1] const why = full <= 0 ? "clip" : n.videos >= MAX_REF_VIDEOS ? "videos" : n.files >= MAX_REF_FILES ? "files"
      // [OLD 2026-11-09 v0.17.0->v0.17.1]   : secs <= 0 || (cut && secs < REF_MEDIA_MIN_SECONDS - 1e-6) ? "seconds" : "";  (a clip under 2 s was sent)
      // added 2026-11-09 v0.17.1 (third review): a clip under 2 s is not sent ("short"), as model.py
      const why = full <= 0 ? "clip" : full < REF_MEDIA_MIN_SECONDS - 1e-6 ? "short" : n.videos >= MAX_REF_VIDEOS ? "videos"
        : n.files >= MAX_REF_FILES ? "files" : secs <= 0 || (cut && secs < REF_MEDIA_MIN_SECONDS - 1e-6) ? "seconds" : "";
      if (why) { left.push({ cast: c.id, anchor: va.id, asset: a.id, why }); continue; }
      const sound = !!va.soundtrack && n.audio < MAX_REF_AUDIOS && n.audioSeconds + secs <= REF_MEDIA_TOTAL_SECONDS + 1e-4;
      n.videos++; n.files++; n.videoSeconds += secs;
      if (sound) { n.audio++; n.audioSeconds += secs; }
      picked.push({ cast: c.id, anchor: va.id, asset: a.id, in: clip.start, seconds: secs, sound, cut, mute: !!va.soundtrack && !sound });
    }
  }
  return { picked, left };
}

// added 2026-11-09 v0.16.0 (model.py tile_pixels): about how many pixels the short side of one picture of a packed sheet
// of `pics` (assets) has when H3 gets it, at width x height and Global → Output → Reference images ("match" | "max")
export const SMALL_TILE_PX = 300;
export function tilePixels(pics, width, height, refSize = "match") {
  if (!pics.length) return 0;
  const ratios = pics.map(a => Math.max(0.5, Math.min(2, (num(a.width, 0) || 1) / (num(a.height, 0) || 1)))).sort((x, y) => x - y);
  const r = ratios[Math.floor(ratios.length / 2)];
  const [cols, rows] = sheetGrid(pics.length);
  const cw = 768 * Math.sqrt(r), ch = 768 / Math.sqrt(r);
  const W = cols * cw, H = rows * ch;
  const s = refSize === "max" ? Math.min(1, 2048 / Math.min(W, H)) : Math.min(1, Math.sqrt(width * height / (W * H)));
  return Math.floor(Math.min(cw, ch) * s + 0.5);
}

// ---- added 2026-11-10 v0.19.0: Global → Hires, the latent upscaler (model.py hires_size / scene_hires the same)
export const HIRES_MAX_SCALE = 4;
export const HIRES_SCALES = [1.25, 1.5, 1.75, 2];
// "draft" or "final": the scene's own choice, else Global (model.py scene_quality)
export function sceneQuality(project, scene) {
  const q = scene?.overrides?.quality;
  return q === "draft" || q === "final" ? q : project.global.quality;
}
// on H3's 32-pixel grid, half up (model.py _snap32)
export function snap32(v) {
  return Math.max(32, Math.floor(v / 32 + 0.5) * 32);
}
// the size every take of the project ends at: Global → Output × scale while Hires is on, else Global → Output
export function hiresSize(g) {
  const w = Math.trunc(g.output.width), h = Math.trunc(g.output.height);
  const hi = g.hires || {};
  if (!hi.enabled || !(Number(hi.scale) > 1)) return [w, h];
  return [snap32(w * hi.scale), snap32(h * hi.scale)];
}
// the merged film's size
export function projectOutputSize(project) {
  return hiresSize(project.global);
}
// the size a scene is sampled at, as model.py resolve_settings (its own size else Global; a draft at Draft → scale with
// spec.snap_canvas, which rounds half to even like Python's round)
export function sceneSampleSize(project, scene) {
  const g = project.global, o = scene?.overrides || {};
  let w = Math.trunc(num(o.width, 0)) || g.output.width, h = Math.trunc(num(o.height, 0)) || g.output.height;
  if (sceneQuality(project, scene) === "draft") {
    const r = x => { const f = Math.floor(x), d = x - f; return d > 0.5 || (d === 0.5 && f % 2 === 1) ? f + 1 : f; };
    const ds = g.draft.scale;
    w = Math.max(32, r(w * ds / 32) * 32);
    h = Math.max(32, r(h * ds / 32) * 32);
  }
  return [w, h];
}
// what the latent upscaler does to a scene (model.py scene_hires), or null
export function sceneHires(project, scene) {
  const g = project.global, hi = g.hires || {}, o = scene?.overrides || {};
  const quality = sceneQuality(project, scene);
  if (!hi.enabled || o.hires === "off" || (quality === "draft" && !g.draft.hires)) return null;
  const [w, h] = sceneSampleSize(project, scene);
  const [fw, fh] = hiresSize(g);
  const s = Math.min(fw / w, fh / h);
  if (s <= 1 + 1e-9) return null;
  const out = { model: g.models.latent_upscaler || "", width: Math.min(fw, snap32(w * s)), height: Math.min(fh, snap32(h * s)) };
  const steps = o.refine_steps !== undefined && o.refine_steps !== null ? Math.trunc(o.refine_steps) : Math.trunc(hi.refine_steps);
  if (quality !== "draft" && steps > 0) {
    const d = o.refine_denoise !== undefined && o.refine_denoise !== null ? o.refine_denoise : hi.refine_denoise;
    out.refine_steps = steps;
    out.refine_denoise = Math.round(d * 1e4) / 1e4;
  }
  return out;
}

// added 2026-11-09 v0.16.0: the output size a scene renders at (model.py resolve_settings: its own size, else Global;
// a draft scene at Global → Draft's scale)
export function sceneOutputSize(project, scene) {
  const g = project.global, o = scene?.overrides || {};
  let w = Math.trunc(num(o.width, 0)) || g.output.width, h = Math.trunc(num(o.height, 0)) || g.output.height;
  const q = o.quality === "draft" || o.quality === "final" ? o.quality : g.quality;
  if (q === "draft") { const ds = num(g.draft?.scale, 0.5); w = Math.round(w * ds); h = Math.round(h * ds); }
  return [w, h];
}

// added 2026-11-09 v0.16.0: the size of one picture of c's sheet in this scene (its anchors, outfit and parts' pictures,
// as scenePeople gives them), or 0 when c sends no sheet there
export function sceneTilePixels(project, scene, c) {
  if (!castPacks(project, scene, c)) return 0;
  const { people, assets } = scenePeople(project, scene);
  const x = people.find(y => y.c.id === c.id);
  if (!x || x.ids.length < 2) return 0;
  const [w, h] = sceneOutputSize(project, scene);
  return tilePixels(x.ids.map(a => assets.get(a)).filter(Boolean), w, h, project.global.output.ref_image_size);
}

// added 2026-11-10 v0.18.0: c's anchor pictures a scene uses (all of them without a scene, or when c is not in its
// cast list), in order
export function sceneAnchorIds(project, scene, c) {
  const skip = entrySkip(scene?.cast?.find(e => e.id === c.id));
  return c.anchors.filter(id => findAsset(project, id)?.kind === "image" && !skip.has(id));
}
// [OLD 2026-11-10 v0.17.3->v0.18.0] export function sheetURL(project, c, cell = 192) {
// [OLD 2026-11-10 v0.17.3->v0.18.0]   const files = c.anchors.map(id => findAsset(project, id)).filter(a => a?.kind === "image" && a.file).map(a => a.file);
export function sheetURL(project, c, cell = 192, scene = null) { // scene: added 2026-11-10 v0.18.0 (the pictures it uses)
  const files = sceneAnchorIds(project, scene, c).map(id => findAsset(project, id)).filter(a => a?.file).map(a => a.file);
  return files.length ? "/reelwright/sheet?cell=" + cell + "&files=" + encodeURIComponent(JSON.stringify(files)) : "";
}

// Reference budget, the same numbers as model.scene_media_counts (added 2026-11-03 v0.6.0): a video whose sound is used
// takes an audio slot, a voice counts only in passes where its character speaks (and not with the song), the song
// only where passSoundtrack gives one, files = pictures + videos + audio files. With a pass (from planScene): that
// pass; without: the most any pass of the scene uses (song: any pass).
// {pictures, videos, videoSeconds, audio, audioSeconds, files, song}
// added 2026-11-05 v0.7.0: + continuation: "picture" | "video" | "video_audio" (with its sound) | "" (see
// passContinuation; without a pass: the first pass that has one). A continuation picture counts for "auto" packing;
// one that still does not fit (pictures <= 9, videos <= 3, files <= 12) is left out. continuation=false: as v0.6.1.
const MAX_REF_VIDEOS = 3, MAX_REF_AUDIOS = 3, MAX_REF_FILES = 12; // added 2026-11-05 v0.7.0 (spec.py)

// added 2026-11-05 v0.7.0, same as model.pass_continuation: what a pass (from planScene) of scene i sends as reference 1
// for the footage it continues from when Global -> Continuity -> name_continuation is on: "picture" (pass 1 of a
// last-frame start, a re-anchored tail too), "video" (pass 1 of a tail start; a later pass after an overlap seam), "".
export function passContinuation(project, i, pass, mode = null) {
  if (!flag(project.global?.continuity?.name_continuation ?? true, true)) return "";
  // [OLD 2026-11-05 v0.7.0->v0.8.0] if (Math.trunc(num(pass.index, 1)) > 1) return pass.seam_before === "overlap" ? "video" : "";
  // added 2026-11-05 v0.8.0: Global -> Long scenes -> seam_video_ref off: anchored only after an overlap seam
  if (Math.trunc(num(pass.index, 1)) > 1) {
    return pass.seam_before === "overlap" && flag(project.global?.long?.seam_video_ref ?? true, true) ? "video" : "";
  }
  if (i === null || i === undefined || i <= 0) return "";
  if (mode === null) mode = effectiveStart(project, i);
  if (mode === "tail" && pass.overlap_frames) return "video";
  return mode === "last_frame" || mode === "tail" ? "picture" : "";
}

// added 2026-11-05 v0.7.0, same as model.continuation_frames: frames of the clip sent as <Video 1> (the tail clip of the
// scene before: its last 124 frames or fewer; the last 124 frames of the pass before), 0 for none.
export function continuationFrames(project, i, pass, mode = null) {
  if (passContinuation(project, i, pass, mode) !== "video") return 0;
  if (Math.trunc(num(pass.index, 1)) > 1) return MIN_PASS_FRAMES;
  return Math.min(MIN_PASS_FRAMES, sceneFrames(project.scenes[i - 1]));
}

// [OLD 2026-11-05 v0.6.1->v0.7.0] export function sceneBudget(project, scene, pass = null) {
// [OLD 2026-11-09 v0.15.1->v0.16.0] export function sceneBudget(project, scene, pass = null, continuation = true) {
export function sceneBudget(project, scene, pass = null, continuation = true, videoAnchors = true) { // videoAnchors: added 2026-11-09 v0.16.0
  if (!pass) {
    /* [OLD 2026-11-05 v0.6.1->v0.7.0] no continuation
    const outs = planScene(project, scene).passes.map(x => sceneBudget(project, scene, x));
    [/OLD] */
    // [OLD 2026-11-09 v0.15.1->v0.16.0] const outs = planScene(project, scene).passes.map(x => sceneBudget(project, scene, x, continuation));
    const outs = planScene(project, scene).passes.map(x => sceneBudget(project, scene, x, continuation, videoAnchors));
    const b = {};
    for (const k of ["pictures", "videos", "videoSeconds", "audio", "audioSeconds", "files"]) b[k] = Math.max(...outs.map(o => o[k]));
    b.song = outs.some(o => o.song);
    b.continuation = outs.find(o => o.continuation)?.continuation || ""; // added 2026-11-05 v0.7.0
    return b;
  }
  // [OLD 2026-11-05 v0.6.1->v0.7.0] const { people, autoPack, assets } = scenePeople(project, scene);
  // added 2026-11-05 v0.7.0: the continuation reference of this pass; a picture counts for "auto" packing
  const { people, assets, unpacked } = scenePeople(project, scene);
  const idx = project.scenes.findIndex(x => x.id === scene.id);
  const cont = continuation ? passContinuation(project, idx < 0 ? null : idx, pass) : "";
  // [OLD 2026-11-08 v0.11.0->v0.12.0] const autoPack = unpacked + (cont === "picture" ? 1 : 0) > MAX_REF_IMAGES;
  // added 2026-11-08 v0.12.0: the pose pictures of this pass count too (model.scene_media_counts)
  const posePics = [...new Set(poseRefs(project, scene, pass, people).map(x => x.a.id))];
  const anchorIds = new Set(people.flatMap(x => x.ids));
  const refPicIds = new Set(scene.refs.filter(r => r.role === "reference" && assets.get(r.asset)?.kind === "image").map(r => r.asset));
  const autoPack = unpacked + posePics.filter(a => !anchorIds.has(a) && !refPicIds.has(a)).length + (cont === "picture" ? 1 : 0) > MAX_REF_IMAGES;
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
  for (const a of posePics) if (!sent.has(a)) { sent.add(a); b.pictures++; } // added 2026-11-08 v0.12.0
  // added 2026-11-08 v0.14.0: the audio clips sent: each voice sample (the whole file), then the audio references' clips
  const clips = sounds.map(v => ({ key: [v.id, 0, null], seconds: Number(v.duration) || 0 }));
  for (const r of scene.refs) {
    const a = assets.get(r.asset);
    if (!a || r.role !== "reference") continue;
    // [OLD 2026-11-08 v0.13.1->v0.14.0] const dur = Number(a.duration) || 0;  (refClip gives each clip's length)
    if (a.kind === "image") {
      if (!sent.has(a.id)) { sent.add(a.id); b.pictures++; }
    /* [OLD 2026-11-08 v0.13.1->v0.14.0] a video counted its asset's whole length; an audio asset counted once
    } else if (a.kind === "video") {
      b.videos++;
      b.videoSeconds += dur;
      if (r.soundtrack) { b.audio++; b.audioSeconds += dur; } // the video's sound takes an <Audio j> slot
    } else if (a.kind === "audio" && !sounds.some(x => x.id === a.id)) sounds.push(a);
    [/OLD] */
    // added 2026-11-08 v0.14.0: each reference sends its clip (refClip): every video reference, an audio clip once
    } else if (a.kind === "video") {
      const secs = refClip(r, a).seconds || 0;
      b.videos++;
      b.videoSeconds += secs;
      if (r.soundtrack) { b.audio++; b.audioSeconds += secs; } // the video's sound takes an <Audio j> slot
    } else if (a.kind === "audio") {
      const key = clipKey(r, a);
      if (!clips.some(x => sameClip(x.key, key))) clips.push({ key, seconds: refClip(r, a).seconds || 0 });
    }
  }
  // [OLD 2026-11-08 v0.13.1->v0.14.0] b.audio += sounds.length + (song ? 1 : 0);
  // [OLD 2026-11-08 v0.13.1->v0.14.0] for (const a of sounds) b.audioSeconds += Number(a.duration) || 0;
  sounds.length = 0;
  for (const x of clips) sounds.push(x); // added 2026-11-08 v0.14.0: voice samples (whole files) and audio clips
  b.audio += sounds.length + (song ? 1 : 0);
  for (const x of sounds) b.audioSeconds += x.seconds;
  if (song) b.audioSeconds += song.length;
  b.files = b.pictures + b.videos + sounds.length + (song ? 1 : 0);
  // added 2026-11-05 v0.7.0: the continuation reference, when it fits (else the pass counts as in v0.6.1)
  b.continuation = "";
  if (cont === "picture") {
    // [OLD 2026-11-09 v0.15.1->v0.16.0] if (b.pictures + 1 > MAX_REF_IMAGES || b.files + 1 > MAX_REF_FILES) return sceneBudget(project, scene, pass, false);
    if (b.pictures + 1 > MAX_REF_IMAGES || b.files + 1 > MAX_REF_FILES) return sceneBudget(project, scene, pass, false, videoAnchors);
    b.pictures++;
    b.files++;
    b.continuation = "picture";
  } else if (cont === "video" && b.videos + 1 <= MAX_REF_VIDEOS && b.files + 1 <= MAX_REF_FILES) {
    const secs = continuationFrames(project, idx, pass) / FPS;
    b.videos++;
    b.files++;
    b.videoSeconds += secs;
    b.continuation = "video";
    if (b.audio < MAX_REF_AUDIOS) { b.audio++; b.audioSeconds += secs; b.continuation = "video_audio"; } // its sound
  }
  if (videoAnchors) pickVideoAnchors(people, assets, b); // added 2026-11-09 v0.16.0: the cast's video anchors, after everything else
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
      // [OLD 2026-11-05 v0.7.0->v0.8.0] shots.push({ id: sh.id, number, continuing: a < s, t: (Math.max(a, s) - s + keepIn) / FPS, camera: sh.camera, text: sh.text });
      // added 2026-11-05 v0.8.0: + the camera's amplitude and speed and the framing (as planner.py)
      shots.push({ id: sh.id, number, continuing: a < s, t: (Math.max(a, s) - s + keepIn) / FPS, camera: sh.camera, text: sh.text,
        camera_amp: sh.camera_amp ?? "", camera_speed: sh.camera_speed ?? "", framing: sh.framing ?? "" });
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

// ---- added 2026-11-10 v0.18.0: the anchors a scene uses (scene.cast[].skip) and a video anchor's frame picture
// (cast.video_anchors[].frame / frame_asset)
// forget an anchor (a picture asset id or a video anchor id) in the skip lists of cast member cid ("" = everyone)
export function unskipAnchor(project, cid, id) {
  for (const s of project.scenes) for (const e of s.cast) if ((!cid || e.id === cid) && Array.isArray(e.skip) && e.skip.includes(id)) e.skip = e.skip.filter(x => x !== id);
}
// is an asset used anywhere but as a frame picture of a video anchor (scene references, cast anchors, outfits and
// voices, the soundtrack, the old score)? ignoreAnchorsOf: a cast id whose anchors don't count
export function assetUsedElsewhere(project, assetId, ignoreAnchorsOf = "") {
  if (project.scenes.some(s => s.refs.some(r => r.asset === assetId))) return true;
  for (const c of project.cast) {
    if (c.id !== ignoreAnchorsOf && c.anchors.includes(assetId)) return true;
    if (c.voice === assetId || c.outfits.some(o => (o.assets || []).includes(assetId))) return true;
    if ((c.video_anchors || []).some(va => va.asset === assetId)) return true;
  }
  return project.soundtrack.some(t => t.asset === assetId) || project.global?.merge?.score?.asset === assetId;
}
// unset video anchor va's frame picture (Sencer: "when frame is unset later, remove from Anchor list and Anchors"): the
// picture leaves cast member c's anchors and the scenes' skip lists, and the project when nothing else uses it.
// Call inside an edit, with c and va from the project being edited. Returns {asset (its code or ""), kept}.
export function clearAnchorFrame(project, c, va) {
  const id = va.frame_asset;
  va.frame = null;
  va.frame_asset = "";
  const a = id && project.assets.find(x => x.id === id);
  if (!a) return { asset: "", kept: false };
  c.anchors = c.anchors.filter(x => x !== id);
  unskipAnchor(project, c.id, id);
  if (assetUsedElsewhere(project, id, c.id) || project.cast.some(x => (x.video_anchors || []).some(v => v.frame_asset === id))) return { asset: a.code, kept: true };
  project.assets = project.assets.filter(x => x.id !== id);
  return { asset: a.code, kept: false };
}

export function assetCastUse(project, assetId) {
  const out = [];
  for (const c of project.cast) {
    const scenes = project.scenes.filter(s => s.cast.some(x => x.id === c.id)).length;
    if (c.anchors.includes(assetId)) out.push({ cast: c, as: "anchor", scenes });
    if ((c.video_anchors || []).some(x => x.asset === assetId)) out.push({ cast: c, as: "video anchor", scenes }); // added 2026-11-09 v0.16.0
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
// added 2026-11-08 v0.14.0: `scene` adds its further clips of an asset (@V1.2 ...)
export function tagCandidates(project, scene = null) {
  // [OLD 2026-11-06 v0.8.0->v0.9.0] const out = project.assets.filter(a => a.code).map(a => ({ tag: "@" + a.code, label: a.name || a.code, kind: a.kind }));
  // added 2026-11-06 v0.9.0: the asset's group before its name in the @ list (shown and searched, never written)
  const out = project.assets.filter(a => a.code).map(a => ({ tag: "@" + a.code, label: (assetGroupName(project, a) ? assetGroupName(project, a) + " · " : "") + (a.name || a.code), kind: a.kind }));
  for (const c of project.cast) {
    if (!c.name) continue;
    out.push({ tag: isTagName(c.name) ? "@" + c.name : "@{" + c.name + "}", label: c.kind, kind: "cast" });
  }
  out.push({ tag: "@tail", label: "previous scene's tail clip", kind: "video" });
  // the part of the soundtrack a pass is sent (v0.5.0); a pass without the song writes it as plain text
  if (playingTracks(project).some(({ t }) => t.sync)) out.push({ tag: "@soundtrack", label: "the song this part is cut to", kind: "audio" });
  // added 2026-11-08 v0.14.0: the scene's second, third ... reference of a video or audio asset (its own clip)
  if (scene) {
    for (const r of scene.refs || []) {
      const tok = refTokens(project, scene)[r.id];
      if (!tok || !tok.includes(".")) continue;
      const a = findAsset(project, r.asset);
      const c = refClip(r, a);
      out.push({ tag: tok, label: `${a.name || a.code} · ${fmtTime(c.start)}–${c.end !== null ? fmtTime(c.end) : "end"}`, kind: a.kind });
    }
  }
  return out;
}

// ---- v0.8.0: camera wording, dialogue length, per-pass prompt sections (added 2026-11-05 v0.8.0; the same as
// model.py framing_phrase, camera_sentence, dialogue_seconds, dialogue_spans, pass_texts, relayout_pass_texts,
// pass_sections; tests/test_model_parity.py compares them) ----

// "close-up" -> "a close-up", "low angle" -> "a low-angle shot"; "" for no framing (FRAMINGS).
export function framingPhrase(framing) {
  return typeof framing === "string" && Object.hasOwn(FRAMING_PHRASE, framing) ? FRAMING_PHRASE[framing] : "";
}

// A shot's camera text as one sentence in the form of H3's guide (base-en.txt 4.3): "the camera pushes in", "small",
// "slow" -> "The camera pushes in with small amplitude at slow speed." Medium amplitude / normal speed ("") are not
// written; hand-written text works the same way. "" without camera text.
// added 2026-11-06 v0.8.0 (lead review): an official move's name ("Push In", "tracking shot", "POV") is written with
// its phrase ("the camera pushes in"), as model.official_camera
export function officialCamera(camera) {
  const t = text(camera);
  const k = t.replace(/^[ \t\n\r]+|[ \t\n\r]+$/g, "").replace(/\.+$/, "").trim().toLowerCase();
  const hit = DEFAULT_CAMERA.find(([n]) => n.toLowerCase() === k);
  return hit ? hit[1] : t;
}

export function cameraSentence(camera, amp = "", speed = "") {
  /* [OLD 2026-11-06 v0.8.0 lead review] an official name was written as the name
  let t = text(camera).replace(/^[ \t\n\r]+|[ \t\n\r]+$/g, "");
  [/OLD] */
  let t = officialCamera(camera).replace(/^[ \t\n\r]+|[ \t\n\r]+$/g, "");
  const extra = (amp === "small" || amp === "large" ? ` with ${amp} amplitude` : "") +
    (speed === "slow" || speed === "fast" ? ` at ${speed} speed` : "");
  if (extra) {
    t = t.replace(/[ \t\n\r.!?]+$/, "");
    t = t ? t + extra : "";
  }
  if (!t) return "";
  const first = String.fromCodePoint(t.codePointAt(0));
  t = first.toUpperCase() + t.slice(first.length);
  return '.!?"\''.includes(t.at(-1)) ? t : t + ".";
}

// a dialogue line's length when it has none: the words at 2.5 a second, CJK characters (Han, kana, Hangul) counting as
// a quarter word each; at least 1 s
const CJK_RANGES = [[0x1100, 0x11FF], [0x3040, 0x30FF], [0x3130, 0x318F], [0x31F0, 0x31FF], [0x3400, 0x4DBF],
  [0x4E00, 0x9FFF], [0xAC00, 0xD7AF], [0xF900, 0xFAFF], [0xFF66, 0xFF9F], [0x20000, 0x2FFFF]];
const WORDS_PER_SECOND = 2.5, CJK_PER_WORD = 4;
const SPACES_RE = /[ \t\n\r\f\v\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+/u;

// How long dialogue line d is spoken: its duration (seconds > 0), else max(1, words / 2.5), where words are the runs
// between spaces that hold a letter or digit, plus the CJK characters / 4.
export function dialogueSeconds(d) {
  d = isObj(d) ? d : {};
  const dur = num(d.duration, null);
  if (dur !== null && dur > 0) return Math.min(dur, DIALOGUE_MAX_SECONDS);
  let cjk = 0, rest = "";
  for (const ch of text(d.text)) {
    const cp = ch.codePointAt(0);
    if (CJK_RANGES.some(([a, b]) => a <= cp && cp <= b)) { cjk++; rest += " "; } else rest += ch;
  }
  const words = rest.split(SPACES_RE).filter(w => /[\p{L}\p{N}]/u.test(w)).length;
  return Math.max(1, (words + cjk / CJK_PER_WORD) / WORDS_PER_SECOND);
}

// Where each dialogue line of the scene is spoken, in the scene's order: [{id, pass (1-based; null when the line is in
// no pass), start, end (scene seconds; start is where the planner put it), seconds, estimated (no duration given),
// seam (scene time of the pass seam the line runs past, else null), past_end (it runs past the scene's end)}].
// plan: planScene(project, scene).
export function dialogueSpans(scene, plan) {
  const where = new Map();
  for (const x of plan.passes) for (const d of x.dialogue) if (!where.has(d.id)) where.set(d.id, [x, d]);
  const n = plan.passes.length;
  return scene.dialogue.map(d => {
    const seconds = dialogueSeconds(d);
    const given = num(d.duration, null);
    const hit = where.get(d.id);
    const start = hit ? hit[0].start + hit[1].t : num(d.t, 0);
    const end = start + seconds;
    const seam = hit && hit[0].index < n && end > hit[0].end + 1e-6 ? hit[0].end : null;
    return { id: d.id, pass: hit ? hit[0].index : null, start, end, seconds, estimated: !(given !== null && given > 0),
      seam, past_end: end > plan.duration + 1e-6 };
  });
}

const FRAME_SECONDS = 1 / FPS;
export function emptySections() {
  const o = {};
  for (const k of SECTION_KEYS) o[k] = "";
  return o;
}
function entrySections(x) {
  const sec = isObj(x) && isObj(x.sections) ? x.sections : {};
  const o = {};
  for (const k of SECTION_KEYS) o[k] = text(sec[k]);
  return o;
}
// two [start, end] ranges within a frame of each other
function closeRange(a, b) {
  return Math.abs(a[0] - b[0]) <= FRAME_SECONDS + 1e-9 && Math.abs(a[1] - b[1]) <= FRAME_SECONDS + 1e-9;
}

// The six sections written for each pass of the scene's CURRENT layout (scene.prompt.passes, stored with the start /
// end the pass had when they were written). When the stored ranges match the layout (within a frame; entries without
// text and a one-pass scene always match), entry k is pass k. Otherwise each pass gets the text of the stored entry
// it overlaps most in time, each entry used once (largest overlap first).
// {texts: [six sections per current pass], moved: [1-based passes whose text was written for another range],
//  unused: [1-based stored entries with text that no pass gets], same: the layout matches, stored: any entry has text,
//  entry: [per current pass, the 1-based stored entry its text comes from, or null]}
export function passTexts(project, scene, plan = null) {
  plan = plan || planScene(project, scene);
  const raw = scene.prompt?.passes;
  const stored = Array.isArray(raw) ? raw.map(x => (isObj(x) ? x : {})) : [];
  const secs = stored.map(entrySections);
  const has = secs.map(s => Object.values(s).some(v => !blank(v)));
  const ranges = stored.map(x => [num(x.start, 0), num(x.end, 0)]);
  const cur = plan.passes.map(x => [x.start, x.end]);
  const n = cur.length;
  const same = n === 1 ? !has.slice(1).some(Boolean)
    : stored.every((_, j) => !has[j] || (j < n && closeRange(ranges[j], cur[j])));
  if (same) {
    return { texts: cur.map((_, k) => (k < stored.length ? { ...secs[k] } : emptySections())), moved: [], unused: [],
      same: true, stored: has.some(Boolean), entry: cur.map((_, k) => (k < stored.length && has[k] ? k + 1 : null)) };
  }
  const pairs = [];
  cur.forEach(([a, b], k) => ranges.forEach(([c, d], j) => {
    if (!has[j]) return;
    const ov = Math.min(b, d) - Math.max(a, c);
    if (ov > 1e-9) pairs.push({ ov, k, j });
  }));
  pairs.sort((x, y) => (y.ov - x.ov) || (x.k - y.k) || (x.j - y.j));
  const take = new Map(), used = new Set();
  for (const { k, j } of pairs) {
    if (!take.has(k) && !used.has(j)) { take.set(k, j); used.add(j); }
  }
  const texts = cur.map((_, k) => (take.has(k) ? { ...secs[take.get(k)] } : emptySections()));
  const moved = cur.map((_, k) => k).filter(k => take.has(k) && !closeRange(ranges[take.get(k)], cur[k])).map(k => k + 1);
  const unused = stored.map((_, j) => j).filter(j => has[j] && !used.has(j)).map(j => j + 1);
  return { texts, moved, unused, same: false, stored: has.some(Boolean),
    entry: cur.map((_, k) => (take.has(k) ? take.get(k) + 1 : null)) };
}

// scene.prompt.passes for the current layout ("Use the new layout"): one entry per pass with its start / end and the
// text passTexts gives it (text no pass gets is dropped).
export function relayoutPassTexts(project, scene, plan = null) {
  plan = plan || planScene(project, scene);
  const texts = passTexts(project, scene, plan).texts;
  return plan.passes.map((x, k) => ({ start: x.start, end: x.end, sections: texts[k] }));
}

// What pass k (1-based) of a structured prompt is built from: {own: the six sections written for it (passTexts),
// used: the text each section is built from, source: {section: "pass" (its own) | "scene" (the scene's, shared by every
// pass) | "auto" (the summary: made by the prompt builder; a multi-pass scene never sends the scene summary) | "split"
// (detailed_description of a multi-pass scene: the scene's [Shot N] lines of this pass)}}. Same as model.pass_sections.
export function passSections(project, scene, plan, k) {
  plan = plan || planScene(project, scene);
  const n = plan.passes.length;
  const texts = passTexts(project, scene, plan).texts;
  const own = k >= 1 && k <= n ? texts[k - 1] : emptySections();
  const sec = entrySections(scene.prompt || {});
  const used = {}, source = {};
  for (const key of SECTION_KEYS) {
    if (!blank(own[key])) { used[key] = own[key]; source[key] = "pass"; }
    else if (key === "summary" && (n > 1 || blank(sec[key]))) { used[key] = ""; source[key] = "auto"; }
    else if (key === "detailed_description" && n > 1) { used[key] = sec[key]; source[key] = "split"; }
    else { used[key] = sec[key]; source[key] = "scene"; }
  }
  return { own, used, source };
}

// For edits (mutate scene, call inside ctx.actions.editScene): set one section of pass k (1-based). The stored list is
// first laid out for the current passes (relayoutPassTexts), so a text in passTexts(...).unused is dropped: offer
// "Use the new layout" before editing when there is one.
export function setPassSection(project, scene, plan, k, key, value) {
  plan = plan || planScene(project, scene);
  if (!SECTION_KEYS.includes(key) || !(k >= 1 && k <= plan.passes.length)) return scene;
  scene.prompt.passes = relayoutPassTexts(project, scene, plan);
  scene.prompt.passes[k - 1].sections[key] = text(value);
  return scene;
}

// For edits: write the sections of several passes at once, e.g. the /llm/passes answer. items: [{index (1-based),
// sections: {...}}]; the sections given (strings) replace the pass's, the others stay. Lays the list out for the
// current passes first, as setPassSection.
export function writePassTexts(project, scene, plan, items) {
  plan = plan || planScene(project, scene);
  scene.prompt.passes = relayoutPassTexts(project, scene, plan);
  for (const it of Array.isArray(items) ? items : []) {
    const k = Math.trunc(num(it?.index, 0));
    if (!(k >= 1 && k <= plan.passes.length) || !isObj(it.sections)) continue;
    for (const key of SECTION_KEYS) if (typeof it.sections[key] === "string") scene.prompt.passes[k - 1].sections[key] = it.sections[key];
  }
  return scene;
}
