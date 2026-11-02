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

export function newId(prefix) {
  return prefix + "_" + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-3);
}

export function slugify(name) {
  const s = String(name || "").toLowerCase().normalize("NFKD").replace(/[^\w\s-]/g, "")
    .trim().replace(/[\s-]+/g, "_").replace(/^_+|_+$/g, "");
  return s || "untitled";
}

export function alignFramesUp(n) {
  n = Math.max(5, Math.round(n));
  while (n % 17 !== 5) n++;
  return n;
}

export function nearestGridFrames(n) {
  const k = Math.max(0, Math.round((n - 5) / 17));
  return k * 17 + 5;
}

export function framesOf(seconds) {
  return Math.round(seconds * FPS);
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
    llm: { base_url: "", model: "", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va", include_guides: true, thinking: "auto" },
    merge: { use: "starred", missing: "skip", hard_cut: "cut", transition_frames: 12, audio_fade_frames: 6,
      loudness: -16.0, normalize: true, score: { asset: "", volume_db: -12.0, duck: true },
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
    ...patch,
  };
}

export function defaultProject(name = "Untitled") {
  const p = {
    schema: 1, id: newId("p"), name, slug: slugify(name),
    global: defaultGlobal(), assets: [], cast: [],
    camera_presets: DEFAULT_CAMERA.map(([n, t]) => ({ id: newId("k"), name: n, text: t })),
    scenes: [], markers: [],
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
  const out = fill(isObj(g) ? structuredClone(g) : {}, defaultGlobal());
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

export function normalizeProject(raw) {
  let p = raw;
  if (typeof p === "string") {
    try { p = p.trim() ? JSON.parse(p) : null; } catch { p = null; }
  }
  if (!isObj(p) || !Array.isArray(p.scenes)) return defaultProject();
  const base = defaultProject(p.name || "Untitled");
  base.scenes = [];
  fill(p, base);
  if (!p.slug) p.slug = slugify(p.name);
  p.schema = 1;
  for (const s of p.scenes) {
    fill(s, defaultScene(p, { id: s.id || newId("s") }));
    fill(s.prompt, defaultPrompt());
    s.refs.forEach(r => fill(r, { id: newId("r"), role: "reference", time: 0, retention: "", keep: [], soundtrack: false }));
    s.shots.forEach(x => fill(x, { id: newId("h"), t: 0, camera: "", text: "" }));
    s.dialogue.forEach(x => fill(x, { id: newId("d"), speaker: "", t: 0, language: p.global.defaults.language, delivery: "", text: "" }));
  }
  for (const a of p.assets) {
    fill(a, { id: newId("a"), code: "", kind: "image", name: "", file: "", duration: 0, width: 0, height: 0, category: "",
      /* [OLD 2026-11-02 v0.1.0->v0.2.0] assets had no description
      defaults: { role: "reference", retention: a.kind === "audio" ? "reference" : "fully_preserved", keep: [], soundtrack: false }, notes: "" });
      [/OLD] */
      defaults: { role: "reference", retention: a.kind === "audio" ? "reference" : "fully_preserved", keep: [], soundtrack: false }, notes: "",
      description: "" }); // added 2026-11-02 v0.2.0: description feeds subject_definitions
  }
  assignCodes(p.assets);
  for (const c of p.cast) {
    fill(c, { id: newId("c"), kind: "character", name: "", speaker: "", description: "", anchors: [], pack_sheet: true,
      outfits: [], default_outfit: "", voice: "", language: p.global.defaults.language, lora: { name: "", strength: 0.8 } });
  }
  if (!p.scenes.length) p.scenes.push(defaultScene(p, { title: "Scene 1" }));
  if (!p.scenes.some(s => s.id === p.ui.selected)) p.ui.selected = p.scenes[0].id;
  return p;
}

export function sceneStarts(project) {
  const starts = {};
  let t = 0;
  for (const s of project.scenes) { starts[s.id] = t; t += s.duration; }
  return { starts, total: t };
}

export function overlapSeconds(scene) {
  return scene.start.mode === "tail" ? scene.start.overlap_frames / FPS : 0;
}

export function assembledDuration(project) {
  return project.scenes.reduce((t, s, i) => t + s.duration - (i > 0 ? overlapSeconds(s) : 0), 0);
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
  if (key === "seed" && project.global.sampling.seed_mode === "increment") value += sceneIndex(project, scene.id);
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
  for (const sc of scene.cast) {
    const c = findCast(project, sc.id);
    if (!c) continue;
    if (c.anchors.length) b.pictures += c.pack_sheet ? 1 : c.anchors.length;
    const voice = findAsset(project, c.voice);
    const speaks = scene.dialogue.some(d => d.speaker === c.id);
    if (voice && speaks) { b.audio++; b.audioSeconds += voice.duration || 0; }
  }
  b.files = b.pictures + b.videos + b.audio;
  return b;
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

// Chains of scenes linked by continuation (last frame or tail).
export function continuityChains(project) {
  const chains = [];
  for (const s of project.scenes) {
    if (s.start.mode === "fresh" || !chains.length) chains.push([s]);
    else chains[chains.length - 1].push(s);
  }
  return chains;
}

export function tagCandidates(project) {
  const out = project.assets.map(a => ({ tag: "@" + a.code, label: a.name || a.code, kind: a.kind }));
  for (const c of project.cast) {
    const tag = /^[\w-]+$/.test(c.name) ? "@" + c.name : "@{" + c.name + "}";
    out.push({ tag, label: c.kind, kind: "cast" });
  }
  out.push({ tag: "@tail", label: "previous scene's tail clip", kind: "video" });
  return out;
}
