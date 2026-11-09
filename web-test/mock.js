// Mock host for the editor harness: a demo "Harbor Lights" project, canned
// /reelwright/* responses, generated preview images and fake progress events.

import { createMockStorage } from "./mock_files.js"; // added 2026-11-03 v0.4.0
// added 2026-11-05 v0.8.0: the passes of a scene as the editor (and the backend planner) make them
import { planScene as modelPlanScene, SECTION_KEYS } from "../web/rw/model.js";

const SLUG = "harbor_lights";
const listeners = {};
const art = {};
let projectJSON = "";
let storage = null; // added 2026-11-03 v0.4.0: mock of the Files tab's routes
const queued = [];
// added 2026-11-03 v0.6.0: switches for tests (window.__mockFlags): slugConflict (/autosave answers 409 slug_conflict
// for that slug unless force), mergeBusy (/merge answers 409 busy), mergeMs (a merge that takes this long and can be
// cancelled), autosaveFail (/autosave answers 500); autosaves records each autosave body
// added 2026-11-03 v0.6.0 (F2b): plan ({scene_id: plan fields}), estimate (top-level plan estimate), filesBusy (a
// reason: /storage/delete refuses everything with it, as the server does while a render or merge runs), merges (the
// body of each /merge request), versionEdits (a function (project, name) that changes what /version returns)
// [OLD 2026-11-05 v0.6.1->v0.7.0] export const mockFlags = { slugConflict: "", mergeBusy: false, mergeMs: 0, autosaveFail: false, autosaves: [], queueMs: 0,
// [OLD 2026-11-05 v0.6.1->v0.7.0]   plan: {}, estimate: null, filesBusy: "", merges: [], versionEdits: null };
// added 2026-11-05 v0.7.0: filmstrips (the file of each /filmstrip request), filmstripFail (a substring of the video
// paths whose filmstrip answers 404, or true for all), sprites (how many filmstrip sprites were drawn)
// [OLD 2026-11-05 v0.7.0->v0.8.0] export const mockFlags = { slugConflict: "", mergeBusy: false, mergeMs: 0, autosaveFail: false, autosaves: [], queueMs: 0,
// [OLD 2026-11-05 v0.7.0->v0.8.0]   plan: {}, estimate: null, filesBusy: "", merges: [], versionEdits: null, filmstrips: [], filmstripFail: "", sprites: 0 };
// added 2026-11-05 v0.8.0: passCalls (the body of each /llm/passes request), passesMs (time per pass), passesFail (a
// scene id whose /llm/passes fails)
export const mockFlags = { slugConflict: "", mergeBusy: false, mergeMs: 0, autosaveFail: false, autosaves: [], queueMs: 0,
  plan: {}, estimate: null, filesBusy: "", merges: [], versionEdits: null, filmstrips: [], filmstripFail: "", sprites: 0,
  passCalls: [], passesMs: 0, passesFail: "",
  // [OLD 2026-11-06 v0.10.0] voiceCuts added below
  // speechCalls: [], speechShift: 0.6 }; // added 2026-11-06 v0.10.0: /speech requests and how late the mock hears the lines
  // [/OLD]
  // [OLD 2026-11-09 v0.14.1->v0.14.2] speechCalls: [], speechShift: 0.6, voiceCuts: [] }; // added 2026-11-06 v0.10.0: /speech requests, how late the mock hears the lines, /voice_from_take bodies
  speechCalls: [], speechShift: 0.6, voiceCuts: [], // added 2026-11-06 v0.10.0: /speech requests, how late the mock hears the lines, /voice_from_take bodies
  writeText: {} }; // added 2026-11-09 v0.14.2: scene id -> the detailed description /llm/passes and /llm/rewrite write
if (typeof window !== "undefined") window.__mockFlags = mockFlags;
const mergeJobs = {};

// ---------- Generated pictures ----------

function canvas(w, h, draw) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const g = c.getContext("2d");
  draw(g, w, h);
  return c.toDataURL("image/png");
}

const PAINT = {
  portrait: (hair, coat, bg) => (g, w, h) => {
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    g.fillStyle = coat; g.beginPath(); g.ellipse(w / 2, h * 1.02, w * 0.36, h * 0.33, 0, Math.PI, 0); g.fill();
    g.fillStyle = "#c9a68a"; g.beginPath(); g.arc(w / 2, h * 0.42, w * 0.17, 0, Math.PI * 2); g.fill();
    g.fillStyle = hair; g.beginPath(); g.arc(w / 2, h * 0.38, w * 0.19, Math.PI, 0); g.fill();
    g.fillRect(w / 2 - w * 0.19, h * 0.38, w * 0.06, h * 0.16); g.fillRect(w / 2 + w * 0.13, h * 0.38, w * 0.06, h * 0.16);
  },
  harbor: (g, w, h) => {
    g.fillStyle = "#2e3358"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#f4a06b"; g.beginPath(); g.arc(w * 0.7, h * 0.45, h * 0.12, 0, 7); g.fill();
    g.fillStyle = "#1b2340"; g.fillRect(0, h * 0.6, w, h * 0.4);
    g.fillStyle = "#0f1424"; g.beginPath(); g.moveTo(w * 0.15, h * 0.66); g.lineTo(w * 0.42, h * 0.66); g.lineTo(w * 0.37, h * 0.76); g.lineTo(w * 0.2, h * 0.76); g.fill();
    g.fillRect(w * 0.28, h * 0.36, 3, h * 0.3);
  },
  pier: (g, w, h) => {
    g.fillStyle = "#3c4560"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#222b44"; g.fillRect(0, h * 0.66, w, h);
    g.fillStyle = "#151a28"; g.fillRect(0, h * 0.6, w, h * 0.06);
    g.fillStyle = "#0e121d"; g.fillRect(w * 0.58, h * 0.3, w * 0.07, h * 0.3); g.beginPath(); g.arc(w * 0.615, h * 0.25, h * 0.06, 0, 7); g.fill();
  },
  letter: (g, w, h) => {
    g.fillStyle = "#33261f"; g.fillRect(0, 0, w, h);
    g.fillStyle = "rgba(247,185,85,0.25)"; g.beginPath(); g.arc(w * 0.82, h * 0.2, h * 0.4, 0, 7); g.fill();
    g.save(); g.translate(w * 0.42, h * 0.55); g.rotate(-0.12);
    g.fillStyle = "#d8c7a6"; g.fillRect(-w * 0.25, -h * 0.32, w * 0.5, h * 0.62);
    g.strokeStyle = "#6e5b3e"; g.lineWidth = 2;
    for (let i = 0; i < 5; i++) { g.beginPath(); g.moveTo(-w * 0.2, -h * 0.2 + i * h * 0.1); g.lineTo(w * 0.18, -h * 0.2 + i * h * 0.1); g.stroke(); }
    g.restore();
  },
  lighthouse: (g, w, h) => {
    g.fillStyle = "#5b4935"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#3e3122"; g.fillRect(0, h * 0.76, w, h);
    g.fillStyle = "#e8d9bc"; g.beginPath(); g.moveTo(w * 0.4, h * 0.76); g.lineTo(w * 0.58, h * 0.76); g.lineTo(w * 0.54, h * 0.28); g.lineTo(w * 0.44, h * 0.28); g.fill();
    g.fillStyle = "#f6c76a"; g.fillRect(w * 0.43, h * 0.18, w * 0.12, h * 0.1);
    g.fillStyle = "rgba(246,199,106,0.3)"; g.beginPath(); g.moveTo(w * 0.55, h * 0.2); g.lineTo(w, h * 0.06); g.lineTo(w, h * 0.36); g.fill();
  },
  storm: (g, w, h) => {
    g.fillStyle = "#1a2130"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#2a3346"; g.fillRect(0, 0, w, h * 0.32);
    g.fillStyle = "#121826"; g.fillRect(0, h * 0.74, w, h);
    g.strokeStyle = "#e2e8f0"; g.lineWidth = 3; g.beginPath(); g.moveTo(w * 0.56, h * 0.18); g.lineTo(w * 0.46, h * 0.45); g.lineTo(w * 0.58, h * 0.45); g.lineTo(w * 0.48, h * 0.74); g.stroke();
  },
  lights: (g, w, h) => {
    g.fillStyle = "#121a2c"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#0a0f1e";
    [[0.08, 0.45, 0.25], [0.4, 0.3, 0.2], [0.68, 0.5, 0.27]].forEach(([x, y, ww]) => g.fillRect(w * x, h * y, w * ww, h));
    g.fillStyle = "#fcd34d";
    for (let i = 0; i < 14; i++) g.fillRect(w * (0.1 + (i * 0.061) % 0.82), h * (0.55 + ((i * 0.37) % 0.35)), 4, 4);
  },
  walk: (g, w, h) => {
    g.fillStyle = "#26304a"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#1a2236"; g.fillRect(0, h * 0.68, w, h);
    g.fillStyle = "#3a4560"; g.fillRect(0, h * 0.64, w, h * 0.04);
    g.fillStyle = "#e7b53c"; g.fillRect(w * 0.62, h * 0.34, w * 0.07, h * 0.3);
    g.fillStyle = "#0e121d"; g.beginPath(); g.arc(w * 0.655, h * 0.29, h * 0.05, 0, 7); g.fill();
  },
  door: (g, w, h) => {
    g.fillStyle = "#2b231e"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#4a3a2c"; g.fillRect(w * 0.18, 0, w * 0.45, h);
    g.fillStyle = "#c9a15a"; g.beginPath(); g.arc(w * 0.54, h * 0.52, h * 0.06, 0, 7); g.fill();
    g.fillStyle = "#b88a6e"; g.beginPath(); g.ellipse(w * 0.66, h * 0.62, w * 0.12, h * 0.12, -0.5, 0, 7); g.fill();
  },
};

function makeArt() {
  const p = (key, fn, w = 320, h = 180) => { art[key] = canvas(w, h, fn); };
  p("mara", PAINT.portrait("#8a3b22", "#1e2a4a", "#4a5a7a"), 240, 320);
  p("mara_profile", PAINT.portrait("#8a3b22", "#1e2a4a", "#465676"), 240, 320);
  p("mara_full", PAINT.portrait("#8a3b22", "#1e2a4a", "#425272"), 240, 320);
  p("keeper", PAINT.portrait("#d9d4cc", "#3b3020", "#3f4a3a"), 240, 320);
  p("harbor", PAINT.harbor); p("pier", PAINT.pier); p("letter", PAINT.letter); p("lighthouse", PAINT.lighthouse);
  p("storm", PAINT.storm); p("lights", PAINT.lights); p("walk", PAINT.walk); p("door", PAINT.door);
}

const SCENE_ART = { s_01: "harbor", s_02: "pier", s_03: "letter", s_04: "lighthouse", s_05: "storm", s_06: "lights", s_07: "walk", s_08: "door" };
const FILE_ART = { "mara.png": "mara", "mara_profile.png": "mara_profile", "mara_full.png": "mara_full", "keeper.png": "keeper", "harbor.jpg": "harbor", "letter.png": "letter", "lighthouse_1962.jpg": "lighthouse", "storm_sky.jpg": "storm" };

// added 2026-11-05 v0.7.0: the filmstrip of a take (GET /reelwright/filmstrip, as reelwright/routes.py answers it) and
// its sprite. Tile k is the scene's picture with a coloured band on top (hue k * 47°), a dot that moves across the
// tiles and the tile number, so the harness can tell the tiles apart. `dir` is the take folder (output-relative).
function filmInfo(dir, h) {
  const m = /scenes\/([^/]+)\/takes\/([^/]+)$/.exec(dir || "");
  const tk = m && takes[m[1]]?.takes?.find(t => t.id === m[2]);
  const duration = Number(tk?.seconds) > 0 ? Number(tk.seconds) : 8;
  const interval = duration <= 150 ? 0.25 : duration / 600;
  const count = Math.max(1, Math.ceil(duration / interval - 1e-9));
  return { file: `${dir}/filmstrip_${h}.jpg`, interval, count, tile_w: Math.round(h * 16 / 9), tile_h: h, duration, scene: m ? m[1] : "" };
}
function filmSprite(dir, h) {
  const k = `film:${dir}:${h}`;
  if (art[k]) return art[k];
  const f = filmInfo(dir, h);
  const paint = PAINT[SCENE_ART[f.scene]];
  const c = document.createElement("canvas");
  c.width = f.count * f.tile_w; c.height = f.tile_h;
  const g = c.getContext("2d");
  for (let i = 0; i < f.count; i++) {
    g.save();
    g.translate(i * f.tile_w, 0);
    g.beginPath(); g.rect(0, 0, f.tile_w, f.tile_h); g.clip();
    if (paint) paint(g, f.tile_w, f.tile_h); else { g.fillStyle = "#2b303b"; g.fillRect(0, 0, f.tile_w, f.tile_h); }
    g.fillStyle = `hsl(${(i * 47) % 360}, 85%, 55%)`;
    g.fillRect(0, 0, f.tile_w, 6);
    g.beginPath(); g.arc(6 + (f.tile_w - 12) * (i / Math.max(1, f.count - 1)), f.tile_h * 0.55, 4, 0, 7); g.fill();
    g.fillStyle = "rgba(11, 12, 15, 0.75)"; g.fillRect(f.tile_w - 24, f.tile_h - 15, 22, 13);
    g.fillStyle = "#fff"; g.font = "bold 10px sans-serif"; g.textAlign = "right"; g.fillText(String(i), f.tile_w - 4, f.tile_h - 5);
    g.restore();
  }
  mockFlags.sprites++;
  return (art[k] = c.toDataURL("image/jpeg", 0.85));
}

// ---------- Demo project ----------

function demoProject() {
  const img = (id, code, name, file, category, w = 1024, h = 1365, extra = {}) => ({ id, code, kind: "image", name, file: `reelwright/${SLUG}/${file}`, duration: 0, width: w, height: h, category, defaults: { role: "reference", retention: "fully_preserved", keep: [], soundtrack: false }, notes: "", ...extra });
  const media = (id, code, kind, name, file, duration, category, retention) => ({ id, code, kind, name, file: `reelwright/${SLUG}/${file}`, duration, width: kind === "video" ? 1344 : 0, height: kind === "video" ? 768 : 0, category, defaults: { role: "reference", retention, keep: [], soundtrack: false }, notes: "" });
  const sections = (o = {}) => ({ subject_definitions: "", summary: "", retention_analysis: "", detailed_description: "", overall_soundscape: "", non_diegetic_music: "", ...o });
  /* [OLD 2026-11-05 v0.7.0->v0.8.0] no pass texts
  const scene = (id, title, duration, mode, { sections: sec, ...rest } = {}) => ({
    id, title, duration, color: "", start: { mode, overlap_frames: 39 }, trim: { keep: "start", in: 0 }, refs: [], cast: [], shots: [], dialogue: [],
    prompt: { mode: "structured", auto: { subjects: true, retention: true, shots: true }, sections: sections(sec), raw: "", pass_prompts: {} },
    overrides: {}, lock: false, notes: "", ...rest,
  });
  [/OLD] */
  // added 2026-11-05 v0.8.0: prompt_passes -> scene.prompt.passes (each pass's own sections)
  const scene = (id, title, duration, mode, { sections: sec, prompt_passes: pp = [], ...rest } = {}) => ({
    id, title, duration, color: "", start: { mode, overlap_frames: 39 }, trim: { keep: "start", in: 0 }, refs: [], cast: [], shots: [], dialogue: [],
    prompt: { mode: "structured", auto: { subjects: true, retention: true, shots: true }, sections: sections(sec), raw: "", pass_prompts: {}, passes: pp },
    overrides: {}, lock: false, notes: "", ...rest,
  });
  // added 2026-11-05 v0.7.0: scene.merge (In the cut), complete; the demo scenes get varied values below
  const merge = (o = {}) => ({ transition: "cut", direction: "left", frames: 12, color: "#000000", audio_frames: 6,
    fade_in: { frames: 0, color: "#000000" }, fade_out: { frames: 0, color: "#000000" }, audio_fade_in: 0, audio_fade_out: 0,
    volume_db: 0, mute: false, color_match: "off", color_ref: "", brightness: 0, contrast: 1, saturation: 1, ...o });
  const p = {
    schema: 1, id: "p_harbor", name: "Harbor Lights", slug: SLUG,
    global: {
      models: { diffusion: "minimax_h3_ref2va_pruned_int8_convrot.safetensors", weight_dtype: "default", text_encoder: "qwen3vl_32b_minimax_h3_int8_convrot.safetensors", clip_device: "default", video_vae: "minimax_h3_video_vae_int8_convrot.safetensors", audio_vae: "minimax_h3_audio_vae_fp32.safetensors", latent_upscaler: "" },
      loras: [{ id: "l_style", name: "harbor_lights_style_v1.safetensors", strength: 0.8, enabled: true }, { id: "l_grain", name: "film_grain_v2.safetensors", strength: 0.6, enabled: true }],
      output: { aspect: "16:9", width: 1344, height: 768, ref_image_size: "match" },
      sampling: { steps: 20, sampler: "res_multistep", scheduler: "simple", seed: 104729, seed_mode: "increment", sigma_shift: false, shift_video: 12, shift_audio: 3 },
      quality: "final", draft: { scale: 0.5, steps: 8, lora: "minimax_h3_turbo_8step.safetensors", lora_strength: 1 },
      defaults: { duration: 8, start_mode: "last_frame", overlap_frames: 39, language: "English" },
      long: { max_pass_frames: 362, overlap_frames: 39, crossfade_frames: 12, seam_mode: "auto", cut_snap_seconds: 2 },
      memory: { policy: "free_cache", encode_first: true, group_by_lora: true },
      continuity: { reanchor_after: 2, face_check: true, face_threshold: 0.8, on_drift: "flag" },
      llm: { base_url: "http://llm.local:30000/v1", model: "qwen3-32b-instruct", temperature: 0.4, max_tokens: 2048, preset: "h3_ref2va" },
      merge: { use: "starred", missing: "skip", hard_cut: "cut", transition_frames: 12, audio_fade_frames: 6, loudness: -16, normalize: true, score: { asset: "a_a5", volume_db: -12, duck: true }, color_match: false, color_ref_scene: "", codec: "h264", crf: 16, subtitles: true, chapters: true, otio: true, fcpxml: true, bundle: false, auto_after_render: true },
    },
    assets: [
      img("a_p1", "P1", "Mara — portrait", "mara.png", "subject"),
      img("a_p2", "P2", "Harbor plate", "harbor.jpg", "location", 1920, 1080, { defaults: { role: "reference", retention: "weak_reference", keep: ["boats", "lamp posts"], soundtrack: false } }),
      img("a_p3", "P3", "Letter prop", "letter.png", "prop", 1200, 900, { defaults: { role: "reference", retention: "fully_preserved", keep: ["paper", "handwriting"], soundtrack: false } }),
      img("a_p4", "P4", "Lighthouse 1962", "lighthouse_1962.jpg", "keyframe", 1600, 900),
      img("a_p5", "P5", "Storm sky", "storm_sky.jpg", "style", 1920, 1080, { defaults: { role: "reference", retention: "attribute_transfer", keep: ["cloud colour"], soundtrack: false } }),
      img("a_p6", "P6", "Mara — profile", "mara_profile.png", "subject"),
      img("a_p7", "P7", "Mara — full body", "mara_full.png", "subject"),
      img("a_p8", "P8", "Keeper — portrait", "keeper.png", "subject"),
      media("a_v1", "V1", "video", "dolly_in", "dolly_in.mp4", 4.2, "camera", "fully_preserved"),
      media("a_v2", "V2", "video", "waves_ref", "waves_ref.mp4", 6.0, "motion", "partially_preserved"),
      media("a_a1", "A1", "audio", "harbor_ambience", "harbor_ambience.wav", 12.0, "ambience", "weak_reference"),
      media("a_a2", "A2", "audio", "mara_voice", "mara_voice.wav", 4.2, "voice", "reference"),
      media("a_a3", "A3", "audio", "music_box", "music_box.wav", 9.5, "music", "partially_copy"),
      media("a_a4", "A4", "audio", "thunder", "thunder.wav", 3.1, "sfx", "reference"),
      media("a_a5", "A5", "audio", "harbor_theme", "harbor_theme.wav", 96.0, "music", "reference"),
    ],
    cast: [
      { id: "c_mara", kind: "character", name: "Mara", speaker: "S1", description: "Woman, early 30s, short auburn hair, navy pea coat with brass buttons.", anchors: ["a_p1", "a_p6", "a_p7"], pack_sheet: true,
        outfits: [{ id: "o_navy", name: "Navy pea coat", retention: "fully_preserved", keep: ["face", "hair", "coat"], assets: [] }, { id: "o_oil", name: "Yellow oilskin", retention: "partially_preserved", keep: ["face", "hair"], assets: [] }],
        default_outfit: "o_navy", voice: "a_a2", language: "English", lora: { name: "mara_identity_v1.safetensors", strength: 0.8 } },
      { id: "c_keeper", kind: "character", name: "The Keeper", speaker: "S2", description: "Old lighthouse keeper, white beard, wool cap, oilskin coat.", anchors: ["a_p8"], pack_sheet: true, outfits: [], default_outfit: "", voice: "", language: "English", lora: { name: "", strength: 0.8 } },
      { id: "c_harbor", kind: "location", name: "Harbor", speaker: "", description: "Small fishing harbor at dusk, wooden pier, lamp posts.", anchors: ["a_p2"], pack_sheet: false, outfits: [], default_outfit: "", voice: "", language: "English", lora: { name: "", strength: 0.8 } },
      { id: "c_letter", kind: "prop", name: "The letter", speaker: "", description: "Folded handwritten letter, yellowed paper.", anchors: ["a_p3"], pack_sheet: false, outfits: [], default_outfit: "", voice: "", language: "English", lora: { name: "", strength: 0.8 } },
    ],
    camera_presets: [
      { id: "k_1", name: "Slow push-in", text: "slow push-in toward the subject" }, { id: "k_2", name: "Locked-off", text: "static locked-off camera" },
      { id: "k_3", name: "Crane up", text: "slow crane up revealing the scene" }, { id: "k_4", name: "Handheld pan →", text: "handheld camera panning right" },
      { id: "k_5", name: "Rack focus", text: "rack focus from foreground to background" }, { id: "k_6", name: "Macro", text: "macro close-up, shallow depth of field" },
    ],
    scenes: [
      scene("s_01", "Harbor at dusk", 8.0, "fresh", { merge: merge({ fade_in: { frames: 24, color: "#000000" }, audio_fade_in: 12 }), cast: [{ id: "c_harbor", outfit: "" }], refs: [{ id: "r_1", asset: "a_v1", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }, { id: "r_2", asset: "a_a1", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_1", t: 0, camera: "Wide · slow push-in", text: "The harbor at dusk, boats rocking, the first lamps flicker on." }], sections: { summary: "Establishing shot of the harbor at dusk.", overall_soundscape: "Gulls, rigging creaks, water lapping." } }),
      scene("s_02", "Mara on the pier", 10.125, "last_frame", { merge: merge({ volume_db: -3 }), cast: [{ id: "c_mara", outfit: "o_navy" }, { id: "c_harbor", outfit: "" }], refs: [{ id: "r_3", asset: "a_a1", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_2", t: 0, camera: "Medium · static", text: "@Mara walks to the end of the pier and looks out to sea." }],
        dialogue: [{ id: "d_1", speaker: "c_mara", t: 3.5, language: "English", delivery: "calls out", text: "Is anyone still out there?" }], sections: { summary: "Mara waits at the end of the pier." } }),
      scene("s_03", "The letter", 8.708, "tail", { merge: merge({ transition: "crossfade", color_match: "previous" }), cast: [{ id: "c_mara", outfit: "o_navy" }, { id: "c_letter", outfit: "" }], refs: [{ id: "r_4", asset: "a_p3", role: "keyframe", time: 3.0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_3", t: 0, camera: "Macro · static", text: "Her hands unfold @P3 by candlelight; the paper trembles." }, { id: "h_4", t: 5.0, camera: "Close-up · rack focus", text: "Cut to @Mara's face, rack focus from the candle to her eyes." }],
        dialogue: [{ id: "d_2", speaker: "c_mara", t: 5.2, language: "English", delivery: "whispers", text: "He promised he'd come back." }],
        sections: { summary: "Continuing @tail, Mara opens the letter at the kitchen table.", overall_soundscape: "Kitchen room tone, paper rustle, candle flicker, a far harbor bell.", non_diegetic_music: "N/A" },
        overrides: { seed: 551203, loras: { mode: "add", items: [{ id: "l_candle", name: "candlelight_interiors.safetensors", strength: 0.7, enabled: true }], strengths: { l_grain: 0.35 } } } }),
      scene("s_04", "Flashback: the lighthouse, 1962", 14.375, "fresh", { merge: merge({ transition: "dissolve", frames: 18, brightness: 0.04, contrast: 1.1, saturation: 0.55, fade_out: { frames: 12, color: "#ffffff" } }), refs: [{ id: "r_5", asset: "a_p4", role: "first_frame", time: 0, retention: "", keep: [], soundtrack: false }, { id: "r_6", asset: "a_a3", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_5", t: 0, camera: "Wide · slow crane up", text: "The lighthouse in 1962, sepia light sweeping the rocks." }], sections: { summary: "A memory of the lighthouse.", non_diegetic_music: "Music box melody, slow, slightly detuned." },
        overrides: { steps: 28, loras: { mode: "add", items: [{ id: "l_vint", name: "vintage_1960s.safetensors", strength: 0.85, enabled: true }], strengths: {} } } }),
      scene("s_05", "Storm rolls in", 12.25, "fresh", { merge: merge({ transition: "dip", frames: 10, color: "#ffffff", color_match: "scene", color_ref: "s_02" }), cast: [{ id: "c_mara", outfit: "o_oil" }, { id: "c_keeper", outfit: "" }],
        refs: [{ id: "r_7", asset: "a_p5", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }, { id: "r_8", asset: "a_v2", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }, { id: "r_9", asset: "a_a4", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_6", t: 0, camera: "Handheld · pan right", text: "Waves crash over the pier as the storm arrives." }, { id: "h_7", t: 5.5, camera: "Medium · handheld", text: "@{The Keeper} waves @Mara toward the door." }],
        dialogue: [{ id: "d_3", speaker: "c_keeper", t: 6.0, language: "English", delivery: "shouts", text: "Get inside — the storm's turning!" }], sections: { summary: "The storm hits the harbor." },
        overrides: { loras: { mode: "add", items: [{ id: "l_storm", name: "storm_fx.safetensors", strength: 0.7, enabled: true }], strengths: {} } } }),
      scene("s_06", "Lights come on", 7.292, "last_frame", { cast: [{ id: "c_mara", outfit: "o_oil" }], shots: [{ id: "h_8", t: 0, camera: "Wide · locked-off", text: "One by one the harbor windows light up." }], sections: { summary: "Calm after the storm." } }),
      // [OLD 2026-11-05 v0.7.0->v0.8.0] camera words only, no dialogue, no pass texts
      // scene("s_07", "The long walk home", 32.0, "fresh", { merge: merge({ transition: "wipe", direction: "right", frames: 16, audio_frames: 12 }), cast: [{ id: "c_mara", outfit: "o_navy" }],
      //   shots: [{ id: "h_9", t: 0, camera: "Wide", text: "@Mara leaves the pier." }, { id: "h_10", t: 6.0, camera: "Tracking", text: "Along the seawall." }, { id: "h_11", t: 14.375, camera: "Medium", text: "The rain starts." }, { id: "h_12", t: 22.0, camera: "Wide · one take", text: "She reaches the door." }],
      //   sections: { summary: "Mara walks home along the seawall as the rain begins." } }),
      // added 2026-11-05 v0.8.0: H3 camera moves with amplitude, speed and framing; a line that runs past the seam at
      // 22 s; pass texts of its own for passes 1 and 2 (pass 3 uses the shared and automatic text)
      scene("s_07", "The long walk home", 32.0, "fresh", { merge: merge({ transition: "wipe", direction: "right", frames: 16, audio_frames: 12 }), cast: [{ id: "c_mara", outfit: "o_navy" }],
        shots: [{ id: "h_9", t: 0, camera: "the camera pulls out", camera_amp: "large", camera_speed: "slow", framing: "wide", text: "@Mara leaves the pier, collar up against the wind, and turns towards the seawall." },
          { id: "h_10", t: 6.0, camera: "the camera tracks the moving subject", camera_amp: "", camera_speed: "", framing: "medium wide", text: "Along the seawall: waves slap the stones below as she walks, lamps flickering on one by one." },
          { id: "h_11", t: 14.375, camera: "the camera holds a static shot", camera_amp: "", camera_speed: "", framing: "medium", text: "The rain starts. She stops under a lamp and pulls her scarf tighter." },
          { id: "h_12", t: 22.0, camera: "the camera pushes in", camera_amp: "small", camera_speed: "slow", framing: "wide", text: "She reaches the door of the cottage, soaked, and looks back at the harbor once." }],
        dialogue: [{ id: "d_4", speaker: "c_mara", t: 20.75, duration: null, language: "English", delivery: "murmurs", text: "Just a little further now, almost home." }],
        sections: { summary: "Mara walks home along the seawall as the rain begins.", overall_soundscape: "Wind, waves against the seawall, her footsteps; rain on stone later." },
        prompt_passes: [
          { start: 0, end: 14.375, sections: { summary: "Mara leaves the pier at dusk and walks along the seawall while the harbor lamps come on.", subject_definitions: "", retention_analysis: "",
            detailed_description: "[Shot 1] Live-action, cinematic, a wide shot of the pier at dusk. The camera pulls out with large amplitude at slow speed as <Subject 1> leaves the pier, collar up against the wind.\n[Shot 2] At 00:06.000, the camera cuts to a medium-wide shot tracking her along the seawall; waves slap the stones below and the lamps flicker on one by one.",
            overall_soundscape: "", non_diegetic_music: "" } },
          { start: 14.375, end: 22.0, sections: { summary: "The rain starts; Mara stops under a lamp and pulls her scarf tighter.", subject_definitions: "", retention_analysis: "", detailed_description: "", overall_soundscape: "First heavy drops on stone, wind gusts, a far harbor bell.", non_diegetic_music: "" } },
        ] }),
      scene("s_08", "Insert: hand on the door", 2.5, "fresh", { merge: merge({ transition: "crossfade", frames: 8, fade_out: { frames: 24, color: "#000000" }, audio_fade_out: 24 }), trim: { keep: "custom", in: 1.208 }, shots: [{ id: "h_13", t: 0, camera: "Macro", text: "Her hand grips the brass handle." }], sections: { summary: "Close insert of the door handle." } }),
    ],
    markers: [{ id: "m_1", t: 12.0, text: "music swell", color: "amber" }, { id: "m_2", t: 41.2, text: "storm peak", color: "coral" }],
    ui: { tab: "timeline", selected: "s_03", zoom: 13, playhead: 21.375, snap: true, ripple: true },
  };
  // added 2026-11-06 v0.9.0: asset groups (with descriptions) and tags for the Assets tab
  p.asset_groups = [
    { id: "g_mara", name: "Mara", description: "Every picture of Mara and her voice." },
    { id: "g_harbor", name: "Harbor set", description: "Night exteriors of the harbor: pier, lamps, boats, weather." },
    { id: "g_sound", name: "Music & sound", description: "" },
  ];
  const grp = { a_p1: "g_mara", a_p6: "g_mara", a_p7: "g_mara", a_a2: "g_mara", a_p2: "g_harbor", a_p5: "g_harbor", a_v2: "g_harbor", a_a1: "g_harbor", a_a3: "g_sound", a_a5: "g_sound" };
  const tags = { a_p1: ["identity", "face"], a_p6: ["identity"], a_p7: ["identity", "costume"], a_p2: ["night", "exterior"], a_p5: ["night", "weather"], a_v2: ["water"], a_a5: ["score"] };
  for (const a of p.assets) { a.group = grp[a.id] || ""; a.tags = tags[a.id] || []; }
  return p;
}

// added 2026-11-05 v0.8.0: the demo project as the mock defines it, for tests that need it unchanged
if (typeof window !== "undefined") window.__mockDemo = () => demoProject();

// ---------- Render state ----------

const takes = {};
if (typeof window !== "undefined") window.__mockTakes = takes; // added 2026-11-05 v0.7.0: tests add takes (300-scene filmstrips)
// added 2026-11-02 v0.2.0: titles for the per-take file names (render.py: slug_NN_title_take.mp4)
const SCENE_TITLES = { s_01: "Harbor at dusk", s_02: "Mara on the pier", s_03: "The letter", s_04: "Flashback: the lighthouse, 1962", s_05: "Storm rolls in", s_06: "Lights come on", s_07: "The long walk home", s_08: "Insert: hand on the door" };
const status = { s_01: "cached", s_02: "cached", s_03: "stale", s_04: "cached", s_05: "cached", s_06: "cached", s_07: "pending", s_08: "pending" };
function take(scene, id, extra = {}) {
  const base = `reelwright/${SLUG}/scenes/${scene}/takes/${id}`;
  return { id, key: "k" + scene + id + "9f3ac2", created: 1793560000 + Math.floor(Math.random() * 9000), quality: "final", seconds: 8, frames: 192, face: {},
    // [OLD 2026-11-02 v0.1.0->v0.2.0] files: { video: base + "/video.mp4", first: base + "/first.png", last: base + "/last.png", tail: base + "/tail.mp4" }, ...extra };
    files: { video: `${base}/${SLUG}_${scene.slice(2)}_${(SCENE_TITLES[scene] || "scene").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40)}_${id}.mp4`, first: base + "/first.png", last: base + "/last.png", tail: base + "/tail.mp4" }, ...extra };
}
function initTakes() {
  const add = (s, list, starred) => { takes[s] = { starred, takes: list }; };
  add("s_01", [take("s_01", "v1", { seconds: 8, frames: 192 })], "v1");
  add("s_02", [take("s_02", "v1", { seconds: 10.13, frames: 243, face: { c_mara: 0.89 } }), take("s_02", "v2", { seconds: 10.13, frames: 243, face: { c_mara: 0.94 } })], "v2");
  // [OLD 2026-11-05 v0.7.0->v0.8.0] add("s_03", [take("s_03", "v1", { seconds: 8.71, frames: 209 }), take("s_03", "v2", { seconds: 8.71, frames: 209, face: { c_mara: 0.91 } }), take("s_03", "v3", { seconds: 8.71, frames: 209, face: { c_mara: 0.93 } })], "v3");
  // added 2026-11-05 v0.8.0: drift of the pass that continues the tail (render.py measures it per take)
  const drift = (anchor_diff, color_shift, rgb_shift, sharpness, level) => [{ pass: 1, source: "prev_scene_tail", frames: 39, anchor_diff, color_shift, rgb_shift, sharpness, level }];
  add("s_03", [take("s_03", "v1", { seconds: 8.71, frames: 209, drift: drift(17.2, 6.1, [5.2, -1.4, -2.9], 0.66, "bad") }),
    take("s_03", "v2", { seconds: 8.71, frames: 209, face: { c_mara: 0.91 }, drift: drift(9.5, 2.9, [2.1, 0.4, -1.9], 0.88, "warn") }),
    take("s_03", "v3", { seconds: 8.71, frames: 209, face: { c_mara: 0.93 }, drift: drift(3.1, 1.2, [0.8, -0.3, -0.8], 0.97, "ok"),
      long: { guide_vae: "minimax_h3_video_vae_fp16.safetensors", carry_audio: true, seam_video_ref: true, handoff: "pixels", pass_cache: "lossless" } })], "v3");
  add("s_04", [take("s_04", "v1", { seconds: 14.38, frames: 345 })], "v1");
  add("s_05", [take("s_05", "v1", { seconds: 12.25, frames: 294, face: { c_mara: 0.88, c_keeper: 0.9 } })], "v1");
  add("s_06", [take("s_06", "v1", { seconds: 7.29, frames: 175, face: { c_mara: 0.72 } })], "v1");
  add("s_07", [], null);
  add("s_08", [], null);
}

function align(n) { n = Math.max(5, Math.round(n)); while (n % 17 !== 5) n++; return n; }

function planScene(p, s) {
  const frames = Math.round(s.duration * 24);
  if (frames <= 362) {
    const gen = align(Math.max(124, frames));
    return [{ index: 1, start: 0, end: s.duration, gen_frames: gen, keep_in: s.duration < 124 / 24 ? (s.trim.keep === "custom" ? s.trim.in : 0) : 0, keep_out: s.duration, seam_before: "none", overlap_frames: 0, seed: 0 }];
  }
  return [
    { index: 1, start: 0, end: 14.375, gen_frames: 345, keep_in: 0, keep_out: 14.375, seam_before: "none", overlap_frames: 0 },
    { index: 2, start: 14.375, end: 26.625, gen_frames: 294, keep_in: 0, keep_out: 12.25, seam_before: "cut", overlap_frames: 0 },
    { index: 3, start: 25.0, end: 32.0, gen_frames: 192, keep_in: 0, keep_out: 7.0, seam_before: "overlap", overlap_frames: 39 },
  ];
}

function promptFor(p, s, pass) {
  const pics = [], auds = [], vids = [];
  const subj = [];
  for (const c of s.cast) {
    const cc = p.cast.find(x => x.id === c.id);
    if (!cc) continue;
    pics.push("cast:" + cc.id);
    subj.push(cc);
    if (cc.voice && s.dialogue.some(d => d.speaker === cc.id)) auds.push(cc.voice);
  }
  for (const r of s.refs) {
    const a = p.assets.find(x => x.id === r.asset);
    if (!a || r.role !== "reference") continue;
    (a.kind === "image" ? pics : a.kind === "video" ? vids : auds).push(a.id);
  }
  const sub = text => text.replace(/@\{([^}]+)\}|@([A-Za-z][\w-]*)/g, (m, a, b) => {
    const name = (a || b);
    const asset = p.assets.find(x => x.code.toLowerCase() === name.toLowerCase());
    if (asset) {
      if (asset.kind === "image") { const k = pics.indexOf(asset.id); return k >= 0 ? `<Picture ${k + 1}>` : "<Picture ?>"; }
      if (asset.kind === "video") return `<Video ${vids.indexOf(asset.id) + 1}>`;
      return `<Audio ${auds.indexOf(asset.id) + 1}>`;
    }
    const c = subj.findIndex(x => x.name.toLowerCase() === name.toLowerCase());
    if (c >= 0) return `<Subject ${c + 1}>`;
    if (name === "tail") return "the previous clip";
    return m;
  });
  const tags = [];
  if (pics.length || vids.length) tags.push("reference generation");
  if (s.refs.some(r => r.role !== "reference") || s.start.mode === "last_frame") tags.push("keyframe completion");
  if (s.start.mode === "tail" || pass.seam_before === "overlap") tags.push("video continuation");
  if (auds.length) tags.push("audio reference");
  /* [OLD 2026-11-02 v0.1.0->v0.2.0] mock prompt used the pre-guide layout; the block below mirrors prompt.py's six sections
  const lines = [];
  if (tags.length) lines.push(`[${tags.join(" + ")}] ${sub(s.prompt.sections.summary || "")}`.trim());
  subj.forEach((c, i) => lines.push(`<Subject ${i + 1}>: <Picture ${i + 1}> — ${c.description}`));
  for (const r of s.refs) {
    const a = p.assets.find(x => x.id === r.asset);
    if (a && r.role === "reference") lines.push(`${sub("@" + a.code)}: ${r.retention || a.defaults.retention} - ${(r.keep.length ? r.keep : a.defaults.keep).join(", ") || "overall look"}`);
  }
  const shots = s.shots.filter(x => x.t >= pass.start - 0.001 && x.t < pass.end);
  shots.forEach((x, i) => lines.push(`[Shot${i + 1}]${i ? ` At ${fmt(x.t - pass.start)},` : ""} ${x.camera ? x.camera + ": " : ""}${sub(x.text)}`));
  for (const d of s.dialogue.filter(x => x.t >= pass.start && x.t < pass.end)) {
    const c = subj.findIndex(x => x.id === d.speaker);
    const cc = p.cast.find(x => x.id === d.speaker);
    lines.push(`<Subject ${c + 1}> (${cc?.speaker || "S?"}) ${d.delivery || "says"} <d>[${d.language}] ${d.text}</d>`);
  }
  if (s.prompt.sections.overall_soundscape) lines.push("Soundscape: " + s.prompt.sections.overall_soundscape);
  if (s.prompt.sections.non_diegetic_music) lines.push("Music: " + s.prompt.sections.non_diegetic_music);
  return lines.join("\n");
  [/OLD] */
  // [OLD 2026-11-05 v0.7.0->v0.8.0] const sec = s.prompt.sections;
  // added 2026-11-05 v0.8.0: a pass's own text wins; a multi-pass scene's summary is the pass's own or one made from
  // its shots (the scene summary is a note); the stored pass is the one that overlaps this pass most (passTexts)
  const multi = modelPlanScene(p, s, p.scenes.indexOf(s)).passes.length > 1;
  let own = null, best = 0;
  for (const st of Array.isArray(s.prompt.passes) ? s.prompt.passes : []) {
    const ov = Math.min(pass.end, Number(st?.end) || 0) - Math.max(pass.start, Number(st?.start) || 0);
    if (ov > best + 1e-9) { best = ov; own = st.sections || null; }
  }
  const sec = Object.fromEntries(SECTION_KEYS.map(k => [k, (own?.[k] || "").trim() ? own[k] : s.prompt.sections[k]]));
  if (multi && !(own?.summary || "").trim()) sec.summary = (pass.shots || []).map(x => x.text).filter(Boolean).join(" ") || `Pass ${pass.index} of ${s.title}.`;
  const spk = [];
  const inPass = s.dialogue.filter(x => x.t >= pass.start && x.t < pass.end);
  for (const d of inPass) if (!spk.includes(d.speaker)) spk.push(d.speaker);
  const sid = id => "S" + (spk.indexOf(id) + 1);
  const defs = subj.map((c, i) => `<Subject ${i + 1}> is ${c.name}, ${c.description.replace(/\.$/, "")}, shown in <Picture ${i + 1}>.`);
  auds.forEach((id, i) => { const c = subj.find(x => x.voice === id); if (c) defs.push(`<Audio ${i + 1}> is the voice-timbre reference for <Subject ${subj.indexOf(c) + 1}> (${sid(c.id)}).`); });
  const ret = subj.map((c, i) => `<Subject ${i + 1}> (appears in [Shot 1]): fully_preserved - identity and appearance are retained.`);
  const shots = s.shots.filter(x => x.t >= pass.start - 0.001 && x.t < pass.end);
  // [OLD 2026-11-05 v0.7.0->v0.8.0] const cam = c => c ? "a " + c.toLowerCase().replace(/ shot$/, "") + " shot: " : "";
  // added 2026-11-05 v0.8.0: framing + the camera move as one sentence (prompt.py writes the real one)
  const cam = x => {
    const fr = x.framing ? `${/^[aeiou]/.test(x.framing) ? "an" : "a"} ${x.framing} shot. ` : "";
    const mv = x.camera ? x.camera.charAt(0).toUpperCase() + x.camera.slice(1) + (x.camera_amp ? ` with ${x.camera_amp} amplitude` : "") + (x.camera_speed ? ` at ${x.camera_speed} speed` : "") + ". " : "";
    return fr + mv;
  };
  // [OLD 2026-11-05 v0.7.0->v0.8.0] const desc = shots.map((x, i) => i ? `[Shot ${i + 1}] At ${fmt(x.t - pass.start)}, the shot cuts to ${cam(x.camera)}${sub(x.text)}.` : `[Shot 1] ${cam(x.camera).replace(/^a/, "A")}${sub(x.text)}.`);
  const desc = shots.map((x, i) => (i ? `[Shot ${i + 1}] At ${fmt(x.t - pass.start)}, the shot cuts to ${cam(x)}` : `[Shot 1] ${cam(x).replace(/^a/, "A")}`) + sub(x.text).replace(/\.?$/, ".")); // added 2026-11-05 v0.8.0
  for (const d of inPass) {
    const c = subj.findIndex(x => x.id === d.speaker);
    desc.push(`<Subject ${c + 1}> (${sid(d.speaker)}) ${d.delivery || "says"}, <d>[${d.language}] ${d.text}</d>`);
  }
  const body = {
    subject_definitions: defs.join("\n"),
    summary: `${tags.length ? `[${tags.join(" + ")}] ` : ""}${sub(sec.summary || "")}`.trim(),
    retention_analysis: ret.join("\n"),
    detailed_description: [sub(sec.detailed_description || ""), ...desc].filter(Boolean).join("\n"),
    overall_soundscape: sec.overall_soundscape || "",
    non_diegetic_music: sec.non_diegetic_music || "",
  };
  return Object.entries(body).map(([k, v]) => `${k}:\n${v.trim() || "N/A"}`).join("\n\n");
}

function fmt(t) {
  const m = Math.floor(t / 60);
  return String(m).padStart(2, "0") + ":" + (t - m * 60).toFixed(3).padStart(6, "0");
}

function plan(p) {
  const out = { scenes: {}, issues: [], timeline: { starts: {}, total: 0 } };
  let t = 0;
  for (const s of p.scenes) {
    out.timeline.starts[s.id] = t;
    t += s.duration;
    // [OLD 2026-11-05 v0.7.0->v0.8.0] const passes = planScene(p, s);  (fixed demo passes for s_07; the Prompt card's pass tabs use model.js)
    const passes = modelPlanScene(p, s, p.scenes.indexOf(s)).passes; // added 2026-11-05 v0.8.0: the same passes as the editor
    const issues = [];
    if (s.dialogue.some(d => !d.speaker)) issues.push({ level: "warn", message: `${s.title}: a dialogue line has no speaker.` });
    out.scenes[s.id] = {
      passes, status: status[s.id] || "pending", key: "9f3ac2" + s.id.replace("_", "") + "e1d07b44c1", starred: takes[s.id]?.starred || null,
      takes: takes[s.id]?.takes || [], issues, prompts: passes.map(ps => promptFor(p, s, ps)),
    };
    Object.assign(out.scenes[s.id], planExtras(s, out.scenes[s.id])); // added 2026-11-03 v0.6.0 (F2b)
  }
  out.timeline.total = t;
  out.issues.push({ level: "info", scene_id: "s_08", message: "Insert: hand on the door is shorter than one pass; it renders 124 frames and keeps 2.50 s." });
  // added 2026-11-03 v0.6.0 (F2b): top-level estimate of the pending queue, as analysis.plan_response
  const pend = Object.values(out.scenes).filter(x => ["stale", "missing", "pending"].includes(x.status));
  const known = pend.filter(x => typeof x.estimate_seconds === "number");
  out.estimate = mockFlags.estimate || { seconds: known.length ? known.reduce((a, x) => a + x.estimate_seconds, 0) : null, scenes: pend.length, unknown: pend.length - known.length };
  return out;
}

// added 2026-11-03 v0.6.0 (F2b): the v0.6.0 per-scene plan fields (R: upstream_take, upstream_changed, manual_star,
// estimate_seconds, starred_prompts, cached_passes) with demo values; window.__mockFlags.plan = {scene_id: {...}}
// overrides them per scene. s_03's starred take had another summary line, so its "why?" diff shows a change.
const DEMO_EXTRAS = {
  s_02: { manual_star: true },
  s_03: { upstream_changed: true, upstream_take: "v2", estimate_seconds: 255 },
  s_07: { estimate_seconds: 940, cached_passes: 1 },
};
function planExtras(s, entry) {
  const starred = entry.starred ? entry.prompts.slice() : null;
  if (starred && s.id === "s_03") for (let k = 0; k < starred.length; k++) starred[k] = starred[k].replace(/(summary:\n)[^\n]*/, "$1[video continuation] Continuing the previous shot, Mara reads the letter by the window.");
  const base = { upstream_take: null, upstream_changed: false, manual_star: false, estimate_seconds: null, starred_prompts: starred, cached_passes: 0 };
  return { ...base, ...(DEMO_EXTRAS[s.id] || {}), ...(mockFlags.plan?.[s.id] || {}) };
}

// ---------- Routes ----------

// added 2026-11-03 v0.6.0 (S): merge results, beats, the pass excerpt and storage repair, shaped like the real routes
let mockCutN = 4;
function mergeEvent(body, d) {
  for (const cb of listeners["reelwright.merge"] || []) cb({ slug: body.project?.slug || SLUG, job: body.job || "", ...d });
}
function mockMergeResult(body) {
  const slug = body.project?.slug || SLUG, n = mockCutN++;
  const scenes = body.project?.scenes || [];
  const ix = id => scenes.findIndex(s => s.id === id);
  let range = null, suffix = body.draft ? "_draft" : "";
  if (Array.isArray(body.range) && body.range.length === 2) {
    const [a, b] = [ix(body.range[0]), ix(body.range[1])].sort((x, y) => x - y);
    range = [scenes[a]?.id, scenes[b]?.id];
    suffix += `_s${String(a + 1).padStart(2, "0")}-${String(b + 1).padStart(2, "0")}`;
  }
  const base = `reelwright/${slug}/cuts/${slug}_cut_v${n}${suffix}`;
  const files = { video: base + ".mp4", chapters: base + ".chapters.txt", srt: base + ".srt", otio: base + ".otio", fcpxml: base + ".fcpxml" };
  const out = { ok: true, duration: range ? 21.5 : 58.75, files, skipped: [], created: Math.floor(Date.now() / 1000), soundtrack: 1,
    job: body.job || "merge-mock", draft: !!body.draft, range };
  if (body.stems) {
    files.stems = base + "_stems";
    files.loudness = base + "_loudness.json";
    const m = { integrated: -16.2, lra: 6.4, true_peak: -1.7 };
    out.loudness = { target: -16, ...m, mix: m, scenes: { integrated: -17.9, lra: 5.1, true_peak: -3.2 }, track_t_song: { integrated: -14.8, lra: 4.0, true_peak: -1.1 } };
  }
  mergeEvent(body, { phase: "start", draft: !!body.draft, range, stems: !!body.stems });
  for (const pc of [25, 60, 100]) mergeEvent(body, { phase: "progress", percent: pc });
  mergeEvent(body, { phase: "end", files, duration: out.duration, loudness: out.loudness || null, draft: out.draft, range });
  return out;
}
function mockBeats(file) {
  const seed = [...(file || "")].reduce((a, c) => a + c.charCodeAt(0), 0);
  const bpm = 120 + (seed % 3) * 4, step = 60 / bpm, beats = [];
  for (let t = 0.48; t < 120; t += step) beats.push(Math.round(t * 1e4) / 1e4);
  return { bpm, beats, downbeats: beats.filter((_, i) => i % 4 === 0), duration: 120, file };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

// added 2026-11-02 v0.2.0: fake ComfyUI input/output listings
let guidesHave = {};
const MEDIA = {
  input: [
    { rel: "reelwright/harbor_lights/mara_front.png", kind: "image", bytes: 812000, mtime: 1793600000 },
    { rel: "portraits/old_keeper.png", kind: "image", bytes: 640000, mtime: 1793500000 },
    { rel: "portraits/mara_window.jpg", kind: "image", bytes: 420000, mtime: 1793400000 },
    { rel: "locations/pier_dusk.png", kind: "image", bytes: 910000, mtime: 1793300000 },
    { rel: "clips/waves_loop.mp4", kind: "video", bytes: 5200000, mtime: 1793200000 },
    { rel: "audio/gulls.wav", kind: "audio", bytes: 1400000, mtime: 1793100000 },
  ],
  output: [
    { rel: "ComfyUI_00412_.png", kind: "image", bytes: 1200000, mtime: 1793650000 },
    { rel: "ComfyUI_00411_.png", kind: "image", bytes: 1180000, mtime: 1793640000 },
    { rel: "flux/mara_portrait_00007_.png", kind: "image", bytes: 1500000, mtime: 1793630000 },
    { rel: "flux/lighthouse_00003_.png", kind: "image", bytes: 1460000, mtime: 1793620000 },
    { rel: "reelwright/harbor_lights/scenes/s_02/takes/v2/harbor_lights_02_mara_walks_home_v2.mp4", kind: "video", bytes: 9100000, mtime: 1793610000 },
  ],
};

// added 2026-11-02 v0.3.0: profiles for the mock server (tests can seed them through window.__mockProfiles)
// added 2026-11-02 v0.3.6: autosaved versions the mock can delete
let mockVersions = [
  { name: "project_20261102_101500.json", created: 1793614500, size: 18400 }, { name: "project_20261102_094012.json", created: 1793612412, size: 17200 },
  { name: "project_20261102_090029.json", created: 1793610029, size: 17100 }, { name: "project_20261102_085404.json", created: 1793609644, size: 16900 },
];
let profileSeq = 0;
const profileStore = { profiles: [], default: "" };
if (typeof window !== "undefined") window.__mockProfiles = profileStore;

// added 2026-11-03 v0.4.2: a fake LLM request that sends reelwright.llm progress events and can be cancelled
const llmLive = {};
const llmCancelled = new Set();
const chatCalls = []; // added 2026-11-08 v0.13.0: what /reelwright/llm/chat was sent
if (typeof window !== "undefined") window.__mockChat = chatCalls;
const failedOnce = new Set();
export const scriptCalls = [];
// [OLD 2026-11-05 v0.7.0->v0.8.0] async function llmWork(job, ms, tokens) {
// [OLD 2026-11-05 v0.7.0->v0.8.0]   llmLive[job] = true;
// [OLD 2026-11-05 v0.7.0->v0.8.0]   const send = d => { for (const cb of listeners["reelwright.llm"] || []) cb({ job, budget: 16384, input: 2400, context: 32768, ...d }); };
// added 2026-11-05 v0.8.0: sendWith (the event sender of /llm/passes, which adds the pass)
async function llmWork(job, ms, tokens, sendWith = null) {
  llmLive[job] = true;
  const send = sendWith || (d => { for (const cb of listeners["reelwright.llm"] || []) cb({ job, budget: 16384, input: 2400, context: 32768, ...d }); });
  send({ phase: "waiting", elapsed: 0, tokens: 0, reasoning: 0 });
  const steps = 6;
  // added 2026-11-09 v0.15.0: the reasoning (first half) and the answer (second half) as they come, like llm.py chat
  const think = ["The user wants ", "the scene written. ", "Shots first, then the sound."], answer = ["{\"summary\": ", "\"Mara at the pier\", ", "\"detailed_description\": \"...\"}"];
  const at = { think: 0, text: 0 };
  for (let i = 1; i <= steps; i++) {
    await new Promise(r => setTimeout(r, ms / steps));
    if (llmCancelled.has(job)) { delete llmLive[job]; llmCancelled.delete(job); return true; }
    // [OLD 2026-11-09 v0.14.4->v0.15.0] send({ phase: "writing", elapsed: (ms / 1000) * (i / steps), tokens: Math.round(tokens * i / steps), reasoning: 0 });
    const k = i <= 3 ? "think" : "text", add = (k === "think" ? think : answer)[(i - 1) % 3];
    send({ phase: "writing", elapsed: (ms / 1000) * (i / steps), tokens: Math.round(tokens * i / steps), reasoning: 0, [k + "_at"]: at[k], [k + "_add"]: add });
    at[k] += add.length;
  }
  delete llmLive[job];
  return false;
}
function mockSplit(script, size) {
  const text = script.replace(/\r\n?/g, "\n").replace(/^\n+|\n+$/g, "");
  if (!size || text.length <= size) return { notes: "", parts: text.trim() ? [[text]] : [], chars: text.length, blocks: 1 };
  const lines = text.split("\n");
  const first = lines.findIndex(l => l.trim().startsWith("|"));
  const notes = first > 0 ? lines.slice(0, first).join("\n").trim() : "";
  const blocks = lines.slice(Math.max(0, first)).filter(l => l.trim());
  const parts = [];
  let cur = [], n = 0;
  for (const b of blocks) { if (cur.length && n + b.length + 1 > size) { parts.push(cur); cur = []; n = 0; } cur.push(b); n += b.length + 1; }
  if (cur.length) parts.push(cur);
  return { notes, parts, chars: text.length, blocks: blocks.length };
}

async function route(path, opts = {}) {
  const url = new URL(path, "http://mock");
  const body = opts.body && typeof opts.body === "string" ? JSON.parse(opts.body) : null;
  await new Promise(r => setTimeout(r, 20));
  switch (url.pathname) {
    // [OLD 2026-11-02 v0.2.2->v0.3.0] case "/reelwright/info": return json({ version: "0.2.0", ffmpeg: "ffmpeg 7.1", insightface: true, h3_nodes: true });
    // [OLD 2026-11-02 v0.3.0->v0.3.1] case "/reelwright/info": return json({ version: "0.3.0", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-02 v0.3.1->v0.3.2] case "/reelwright/info": return json({ version: "0.3.1", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-02 v0.3.2->v0.3.3] case "/reelwright/info": return json({ version: "0.3.2", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-02 v0.3.3->v0.3.4] case "/reelwright/info": return json({ version: "0.3.3", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-02 v0.3.4->v0.3.5] case "/reelwright/info": return json({ version: "0.3.4", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-02 v0.3.5->v0.3.6] case "/reelwright/info": return json({ version: "0.3.5", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-02 v0.3.6->v0.3.7] case "/reelwright/info": return json({ version: "0.3.6", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-02 v0.3.7->v0.3.8] case "/reelwright/info": return json({ version: "0.3.7", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-02 v0.3.8->v0.3.9] case "/reelwright/info": return json({ version: "0.3.8", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-03 v0.3.9->v0.4.0] case "/reelwright/info": return json({ version: "0.3.9", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-03 v0.4.0->v0.4.1] case "/reelwright/info": return json({ version: "0.4.0", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
    // [OLD 2026-11-03 v0.4.1->v0.4.2] case "/reelwright/info": return json({ version: "0.4.1", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true });
    // [OLD 2026-11-03 v0.4.2->v0.4.3] case "/reelwright/info": return json({ version: "0.4.2", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true });
    // [OLD 2026-11-03 v0.4.3->v0.5.0] case "/reelwright/info": return json({ version: "0.4.3", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true });
    // [OLD 2026-11-03 v0.5.0->v0.5.1] case "/reelwright/info": return json({ version: "0.5.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true });
    // [OLD 2026-11-03 v0.5.1->v0.6.0] case "/reelwright/info": return json({ version: "0.5.1", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true });
    // [OLD 2026-11-04 v0.6.0->v0.6.1] case "/reelwright/info": return json({ version: "0.6.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-05 v0.6.1->v0.7.0] case "/reelwright/info": return json({ version: "0.6.1", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-06 v0.7.0->v0.8.0] case "/reelwright/info": return json({ version: "0.7.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-06 v0.8.0->v0.9.0] case "/reelwright/info": return json({ version: "0.8.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-06 v0.9.0->v0.10.0] case "/reelwright/info": return json({ version: "0.9.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-06 v0.10.0->v0.10.1] case "/reelwright/info": return json({ version: "0.10.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-06 v0.10.1->v0.10.2] case "/reelwright/info": return json({ version: "0.10.1", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-07 v0.10.2->v0.10.3] case "/reelwright/info": return json({ version: "0.10.2", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-08 v0.10.3->v0.11.0] case "/reelwright/info": return json({ version: "0.10.3", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-08 v0.11.0->v0.12.0] case "/reelwright/info": return json({ version: "0.11.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-08 v0.12.0->v0.13.0] case "/reelwright/info": return json({ version: "0.12.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-08 v0.13.0->v0.13.1] case "/reelwright/info": return json({ version: "0.13.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-08 v0.13.1->v0.14.0] case "/reelwright/info": return json({ version: "0.13.1", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.14.0->v0.14.1] case "/reelwright/info": return json({ version: "0.14.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.14.1->v0.14.2] case "/reelwright/info": return json({ version: "0.14.1", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.14.2->v0.14.3] case "/reelwright/info": return json({ version: "0.14.2", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.14.3->v0.14.4] case "/reelwright/info": return json({ version: "0.14.3", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.14.4->v0.15.0] case "/reelwright/info": return json({ version: "0.14.4", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.15.0->v0.15.1] case "/reelwright/info": return json({ version: "0.15.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.15.1->v0.16.0] case "/reelwright/info": return json({ version: "0.15.1", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.16.0->v0.16.1] case "/reelwright/info": return json({ version: "0.16.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.16.1->v0.17.0] case "/reelwright/info": return json({ version: "0.16.1", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.17.0->v0.17.1] case "/reelwright/info": return json({ version: "0.17.0", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.17.1->v0.17.2] case "/reelwright/info": return json({ version: "0.17.1", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // [OLD 2026-11-09 v0.17.2->v0.17.3] case "/reelwright/info": return json({ version: "0.17.2", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    case "/reelwright/info": return json({ version: "0.17.3", ffmpeg: "ffmpeg 8.0", insightface: true, insightface_error: "", h3_nodes: true, h3_error: "" });
    // added 2026-11-02 v0.3.0: saved Global profiles kept in memory
    case "/reelwright/profiles": return json(profileStore);
    case "/reelwright/profiles/save": {
      if (!body.name) return json({ error: "Give the profile a name" }, 400);
      let hit = profileStore.profiles.find(x => x.id === body.id);
      if (!hit) { hit = { id: "g_" + (++profileSeq), created: 1793650000 }; profileStore.profiles.push(hit); }
      Object.assign(hit, { name: body.name, updated: 1793650000 + profileSeq, global: body.global });
      if (body.default === true) profileStore.default = hit.id;
      else if (body.default === false && profileStore.default === hit.id) profileStore.default = "";
      return json({ profile: hit, ...profileStore });
    }
    case "/reelwright/profiles/delete":
      profileStore.profiles = profileStore.profiles.filter(x => x.id !== body.id);
      if (profileStore.default === body.id) profileStore.default = "";
      return json(profileStore);
    case "/reelwright/profiles/default": profileStore.default = body.id || ""; return json(profileStore);
    case "/reelwright/models": return json({
      diffusion_models: ["minimax_h3_ref2va_pruned_int8_convrot.safetensors", "minimax_h3_fl2va_pruned_int8_convrot.safetensors"],
      text_encoders: ["qwen3vl_32b_minimax_h3_int8_convrot.safetensors", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"],
      vae: ["minimax_h3_video_vae_int8_convrot.safetensors", "minimax_h3_video_vae_fp16.safetensors", "minimax_h3_audio_vae_fp32.safetensors"],
      loras: ["harbor_lights_style_v1.safetensors", "film_grain_v2.safetensors", "candlelight_interiors.safetensors", "vintage_1960s.safetensors", "storm_fx.safetensors", "mara_identity_v1.safetensors", "minimax_h3_turbo_8step.safetensors"],
      latent_upscale_models: ["minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"],
      samplers: ["res_multistep", "euler", "euler_ancestral", "dpmpp_2m", "uni_pc"], schedulers: ["simple", "normal", "karras", "beta", "sgm_uniform"],
    });
    case "/reelwright/plan": return json(plan(body.project));
    case "/reelwright/takes": return json({ scenes: takes });
    case "/reelwright/takes/star": takes[body.scene_id].starred = body.take_id; return json({ ok: true });
    case "/reelwright/takes/delete": takes[body.scene_id].takes = takes[body.scene_id].takes.filter(t => t.id !== body.take_id); return json({ ok: true });
    // added 2026-11-03 v0.6.0: one merge at a time (mergeBusy), cancel by job
    case "/reelwright/merge/cancel": { const live = !!mergeJobs[body.job]; if (live) mergeJobs[body.job] = "cancel"; return json({ ok: true, cancelled: live }); }
    case "/reelwright/merge":
      mockFlags.merges.push({ draft: body.draft, range: body.range ?? null, stems: body.stems, job: body.job }); // added 2026-11-03 v0.6.0 (F2b)
      if (mockFlags.mergeBusy) return json({ error: "busy" }, 409);
      if (mockFlags.mergeMs) {
        mergeJobs[body.job] = "run";
        for (let t = 0; t < mockFlags.mergeMs; t += 50) { await new Promise(r => setTimeout(r, 50)); if (mergeJobs[body.job] === "cancel") break; }
        const stopped = mergeJobs[body.job] === "cancel";
        delete mergeJobs[body.job];
        // S: the real route answers 200 {ok: false, cancelled: true, job} and sends reelwright.merge {phase: "end", cancelled: true}
        if (stopped) { mergeEvent(body, { phase: "end", cancelled: true }); return json({ ok: false, cancelled: true, job: body.job }); }
      }
      // S (v0.6.0): the real response shape: draft / range file names, job, loudness with stems; reelwright.merge events
      return json(mockMergeResult(body));
    // [OLD 2026-11-03 v0.5.1->v0.6.0] case "/reelwright/autosave": return json({ ok: true, version: "project_20261102_101500.json" });
    case "/reelwright/autosave":
      mockFlags.autosaves.push({ slug: body.project?.slug, force: !!body.force, project_id: body.project?.project_id });
      if (mockFlags.autosaveFail) return json({ error: "Disk full" }, 500);
      if (mockFlags.slugConflict && body.project?.slug === mockFlags.slugConflict && !body.force) return json({ reason: "slug_conflict", error: "slug_conflict", other: { id: "p_other", name: "Lighthouse Keeper" } }, 409);
      return json({ ok: true, version: "project_20261102_101500.json" });
    // [OLD 2026-11-02 v0.3.5->v0.3.6] case "/reelwright/versions": return json({ versions: [{ name: "project_20261102_101500.json", created: 1793614500, size: 18400 }, { name: "project_20261102_094012.json", created: 1793612412, size: 17200 }] });
    case "/reelwright/versions": return json({ versions: mockVersions });
    // added 2026-11-02 v0.3.6
    case "/reelwright/versions/delete": {
      const kill = body.all ? mockVersions.map(v => v.name) : body.names || [];
      const before = mockVersions.length;
      mockVersions = mockVersions.filter(v => !kill.includes(v.name));
      return json({ removed: before - mockVersions.length, versions: mockVersions });
    }
    // [OLD 2026-11-03 v0.5.1->v0.6.0] case "/reelwright/version": return json({ project: demoProject() });
    case "/reelwright/version": { // added 2026-11-03 v0.6.0 (F2b): tests can make a version differ (mockFlags.versionEdits)
      const vp = demoProject();
      if (typeof mockFlags.versionEdits === "function") mockFlags.versionEdits(vp, url.searchParams.get("name") || "");
      return json({ project: vp });
    }
    // added 2026-11-03 v0.4.0: Files tab
    case "/reelwright/storage": return json(storage.tree());
    // added 2026-11-03 v0.5.0: a fake song: beats every half second over a slow swell, 120 s
    case "/reelwright/waveform": {
      const ps = Number(url.searchParams.get("per_second")) || 50;
      const seed = [...(url.searchParams.get("file") || "")].reduce((a, c) => a + c.charCodeAt(0), 0);
      const n = 120 * ps;
      const peaks = new Uint8Array(n);
      for (let i = 0; i < n; i++) {
        const t = i / ps;
        const beat = Math.exp(-((t * 2) % 1) * 6);
        const swell = 0.75 + 0.2 * Math.sin(t / 7 + seed);
        peaks[i] = Math.min(255, Math.round(255 * (swell * (0.55 + 0.45 * beat)) * (0.85 + 0.15 * Math.sin(i * 12.9898 + seed))));
      }
      return new Response(peaks, { status: 200, headers: { "X-Per-Second": String(ps), "X-Duration": "120" } });
    }
    // [OLD 2026-11-03 v0.5.1->v0.6.0] case "/reelwright/storage/delete": return json(storage.remove(body.ids || [], body.current));
    case "/reelwright/storage/delete": // added 2026-11-03 v0.6.0 (F2b): mockFlags.filesBusy refuses every id with that reason
      if (mockFlags.filesBusy) return json({ removed: 0, freed: 0, deleted: [], errors: (body.ids || []).map(id => ({ id, error: mockFlags.filesBusy })) });
      return json(storage.remove(body.ids || [], body.current));
    // added 2026-11-03 v0.6.0 (S): Files repair, beat markers, the soundtrack excerpt of one pass
    case "/reelwright/storage/repair": return json({ ok: true, repaired: ["s_03"], takes_found: 14, added: 1, dropped: 0, project: "ok" });
    // added 2026-11-06 v0.10.0: lines timed to a take's speech (routes.py speech_timing); the mock hears every line
    // speechShift seconds late and as long as asked
    case "/reelwright/speech": {
      if (!body?.file || !Array.isArray(body.lines)) return json({ error: "file and lines" }, 400);
      mockFlags.speechCalls.push(body.file);
      const sh = mockFlags.speechShift;
      const lines = body.lines.map(x => ({ id: x.id, t: x.t + sh, end: x.t + sh + (x.duration || 1.2), matched: true, planned: x.t }));
      return json({ lines, segments: lines.map(x => [x.t, x.end]) });
    }
    // added 2026-11-06 v0.10.0: a voice sample cut from a take (routes.py voice_from_take): 400 under 2 s of lines
    case "/reelwright/voice_from_take": {
      if (!body?.slug || !body.scene_id || !body.take_id || !body.cast_id || !Array.isArray(body.lines) || !body.lines.length)
        return json({ error: "slug, scene_id, take_id, cast_id and lines" }, 400);
      mockFlags.voiceCuts.push(body);
      let total = 0;
      const used = [];
      for (const x of body.lines) { if (total >= 15) break; total = Math.min(15, total + (used.length ? 0.25 : 0) + (x.duration || 1.2) + 0.2); used.push(x.id); }
      if (total < 2) return json({ error: `the lines give ${total.toFixed(1)} s of speech; a voice reference needs at least 2 s (render a scene where the character says more)` }, 400);
      const file = `reelwright/${body.slug}/voice_${body.cast_id}_${body.scene_id}_${body.take_id}.wav`;
      return json({ asset: { file, kind: "audio", duration: +total.toFixed(3), name: "voice from take", category: "voice" }, used, seconds: +total.toFixed(3) });
    }
    // added 2026-11-05 v0.7.0 (C): the timeline's filmstrip (routes.py: 400 without a file, 404 for a missing one)
    case "/reelwright/filmstrip": {
      const file = url.searchParams.get("file") || "";
      const h = Math.max(16, Math.min(256, Number(url.searchParams.get("h")) || 54));
      mockFlags.filmstrips.push(file);
      if (!file || !/\.(mp4|webm|mov)$/.test(file)) return json({ error: "file: an output video" }, 400);
      const fail = mockFlags.filmstripFail;
      if (fail === true || (fail && file.includes(fail))) return json({ error: "missing: " + file }, 404);
      const info = filmInfo(file.slice(0, file.lastIndexOf("/")), h);
      delete info.scene;
      return json(info);
    }
    case "/reelwright/beats": {
      const file = url.searchParams.get("file") || "";
      if (!file) return json({ error: "missing: " }, 400);
      return json(mockBeats(file));
    }
    case "/reelwright/soundtrack/excerpt": {
      const p = body.project, slug = p?.slug || body.slug || SLUG;
      const has = (p?.soundtrack || []).some(t => !t.mute && t.sync !== false);
      if (p && !has) return json({ url: null, file: null, reason: "This pass gets no soundtrack (less than 2 s of it plays here)." });
      const file = `reelwright/${slug}/soundtrack/${(body.scene_id || "s").replace(/\W/g, "")}_p${body.pass || 1}_3f9a1c.wav`;
      return json({ url: `/view?filename=${encodeURIComponent(file.split("/").pop())}&subfolder=${encodeURIComponent(file.slice(0, file.lastIndexOf("/")))}&type=output`,
        file, start: 12.5, length: 15.0, codes: ["A3"], marker: "fully_copy",
        pieces: [{ asset: "a_song", src_in: 42.5, src_out: 57.5, at: 0 }] });
    }
    // [OLD 2026-11-02 v0.1.0->v0.2.0] case "/reelwright/llm/settings": return json({ base_url: "http://llm.local:30000/v1", model: "qwen3-32b-instruct", has_key: true, ok: true });
    case "/reelwright/llm/settings": return json({ base_url: "http://llm.local:30000/v1", model: "qwen3-32b-instruct", has_key: true, ok: true,
      guides: guidesHave, guide_urls: { "ref-en.txt": "https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/h3-prompt-writing/references/ref-en.txt", "base-en.txt": "https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/h3-prompt-writing/references/base-en.txt" } });
    // [OLD 2026-11-02 v0.1.0->v0.2.0] case "/reelwright/llm/models": return json({ models: ["qwen3-32b-instruct", "qwen3.8-flash-next", "llama-4-70b"] });
    case "/reelwright/llm/models": return json({ models: ["qwen3-32b-instruct", "qwen3-vl-32b-instruct", "qwen3.8-flash-next", "llama-4-70b", "MiniMax-M2.5", "MiniMax-VL-02", "minimax-text-01"] });
    // added 2026-11-02 v0.2.0: guides, describe, ComfyUI file browser
    case "/reelwright/llm/guides": guidesHave = { "ref-en.txt": { bytes: 23553, fetched: 1793620000 }, "base-en.txt": { bytes: 15773, fetched: 1793620000 } }; return json({ guides: guidesHave });
    case "/reelwright/llm/describe": return json({ text: "the young woman with shoulder-length auburn hair, a navy pea coat with brass buttons and a grey knitted scarf", ms: 1840, model: "qwen3-vl-32b-instruct" });
    case "/reelwright/files": {
      const all = MEDIA[url.searchParams.get("root") || "input"] || [];
      const kind = url.searchParams.get("kind"), terms = (url.searchParams.get("q") || "").toLowerCase().split(/\s+/).filter(Boolean);
      const files = all.filter(f => (!kind || f.kind === kind) && terms.every(t => f.rel.toLowerCase().includes(t)));
      return json({ files, total: files.length, truncated: false });
    }
    case "/reelwright/import": return json({ asset: { kind: /\.(mp4|webm)$/.test(body.rel) ? "video" : "image", name: body.rel.split("/").pop().replace(/\.[^.]+$/, ""),
      file: body.root === "input" ? body.rel : `reelwright/${SLUG}/from_output/${body.rel.split("/").pop()}`, width: 1344, height: 768, category: "subject" } });
    // [OLD 2026-11-02 v0.2.2->v0.3.0] case "/reelwright/llm/test": return json({ ok: true, ms: 412, model: "qwen3-32b-instruct" });
    case "/reelwright/llm/test": return body?.project?.global?.llm?.base_url?.includes("down")
      ? json({ error: "Cannot connect to " + body.project.global.llm.base_url }, 502)
      // [OLD 2026-11-02 v0.3.1->v0.3.2] : json({ ok: true, ms: 412, model: body?.project?.global?.llm?.model || "qwen3-32b-instruct", base_url: body?.project?.global?.llm?.base_url || "http://llm.local:30000/v1", reply: "OK" });
      : json({ ok: true, ms: 412, model: body?.project?.global?.llm?.model || "qwen3-32b-instruct", base_url: body?.project?.global?.llm?.base_url || "http://llm.local:30000/v1", reply: "OK",
        thinking: body?.project?.global?.llm?.thinking !== "off", note: body?.project?.global?.llm?.thinking !== "off" ? "This model thinks before it answers, so Describe, Rewrite, Split and Import get a bigger token budget. Set Thinking to Off for faster answers." : "" });
    case "/reelwright/llm/rewrite": {
      const s = body.project.scenes.find(x => x.id === body.scene_id);
      // added 2026-11-03 v0.4.2: progress events and Stop
      if (body.job && await llmWork(body.job, 600, 900)) return json({ cancelled: true });
      // [OLD 2026-11-09 v0.14.1->v0.14.2] return json({ sections: { ...s.prompt.sections, summary: (s.prompt.sections.summary || "") + " The candle gutters as she reads.", detailed_description: "Extreme close-ups, warm key light from the candle, shallow depth of field." }, warnings: [] });
      // added 2026-11-09 v0.14.2: mockFlags.writeText[scene id] is the detailed description the LLM writes
      return json({ sections: { ...s.prompt.sections, summary: (s.prompt.sections.summary || "") + " The candle gutters as she reads.", detailed_description: mockFlags.writeText?.[s.id] || "Extreme close-ups, warm key light from the candle, shallow depth of field." }, warnings: [] });
    }
    // added 2026-11-05 v0.8.0: write the sections of a scene's passes, one fake request per pass, each with progress
    // events (phase + pass) and Stop. window.__mockFlags.passesMs: time per pass; passesFail: a scene id that fails
    case "/reelwright/llm/passes": {
      const p = body.project, i = p.scenes.findIndex(x => x.id === body.scene_id), s = p.scenes[i];
      if (!s) return json({ error: "Unknown scene " + body.scene_id }, 400);
      // [OLD 2026-11-06 v0.9.0->v0.10.0] mockFlags.passCalls.push({ scene_id: body.scene_id, passes: body.passes, job: body.job });
      // [OLD 2026-11-09 v0.14.4->v0.15.0] mockFlags.passCalls.push({ scene_id: body.scene_id, passes: body.passes, job: body.job, instruction: body.instruction || "" }); // added 2026-11-06 v0.10.0: the rewriter on a pass tab sends one
      mockFlags.passCalls.push({ scene_id: body.scene_id, passes: body.passes, job: body.job, instruction: body.instruction || "", brief: s?.prompt?.brief ?? null }); // v0.10.0: instruction; v0.15.0: the scene's Write prompts brief
      if (mockFlags.passesFail === body.scene_id) return json({ error: "No answer from http://llm.local:30000/v1 for 120 s. (tried 3 times)", reason: "stall" }, 502);
      const plan = modelPlanScene(p, s, i).passes;
      const want = Array.isArray(body.passes) && body.passes.length ? body.passes.filter(k => k >= 1 && k <= plan.length) : plan.map(x => x.index);
      const out = [];
      for (const [j, k] of want.entries()) {
        const ps = plan[k - 1];
        // the events and answers of llm.write_passes (notes_L): pass / passes (the scene's), item / items (this batch)
        const send = d => { for (const cb of listeners["reelwright.llm"] || []) cb({ job: body.job, scene_id: s.id, budget: 4096, input: 6100, context: 32768, pass: k, passes: plan.length, item: j + 1, items: want.length, completed: out.length, ...d }); };
        if (body.job && await llmWork(body.job, mockFlags.passesMs || 600, 700, send)) return json({ cancelled: true, scene_id: s.id, pass_count: plan.length, passes: out, warnings: [], tokens: 700 * out.length, ms: 900 });
        const shots = (ps.shots || []).map((x, j) => (j ? `[Shot ${j + 1}] At ${fmt(x.t)}, the camera cuts to ` : "[Shot 1] Live-action, cinematic, ") + `${x.text || "the scene continues"}`);
        out.push({ index: k, start: ps.start, end: ps.end, sections: {
          subject_definitions: "", summary: `Pass ${k} of ${s.title}: ${(ps.shots || []).map(x => x.text).filter(Boolean).join(" ") || s.prompt.sections.summary || "the action continues."}`.slice(0, 220),
          // [OLD 2026-11-09 v0.14.1->v0.14.2] retention_analysis: "", detailed_description: (shots.join("\n") || "[Shot 1] Live-action, cinematic, one continuous take.") + "\nThe light stays low and blue; rain beads on her coat as the wind pulls at her scarf.",
          // [OLD 2026-11-09 v0.14.2->v0.14.3] retention_analysis: "", detailed_description: mockFlags.writeText?.[s.id] || (shots.join("\n") || "[Shot 1] Live-action, cinematic, one continuous take.") + "\nThe light stays low and blue; rain beads on her coat as the wind pulls at her scarf.", // added 2026-11-09 v0.14.2: writeText
          // added 2026-11-09 v0.14.4: writeText[scene id] may be a list, one text per pass
          retention_analysis: "", detailed_description: (Array.isArray(mockFlags.writeText?.[s.id]) ? mockFlags.writeText[s.id][k - 1] : mockFlags.writeText?.[s.id]) || (shots.join("\n") || "[Shot 1] Live-action, cinematic, one continuous take.") + "\nThe light stays low and blue; rain beads on her coat as the wind pulls at her scarf.",
          overall_soundscape: s.prompt.sections.overall_soundscape || "Wind and distant surf.", non_diegetic_music: "N/A" } });
      }
      return json({ scene_id: s.id, pass_count: plan.length, passes: out, warnings: [], tokens: 700 * out.length, ms: 900 * out.length });
    }
    case "/reelwright/llm/split": return json({ pass_prompts: { 1: "[reference generation] Wide: <Subject 1> leaves the pier…", 2: "[reference generation] Medium: the rain starts…", 3: "[video continuation] Wide, one take: she reaches the door." } });
    // [OLD 2026-11-03 v0.4.1->v0.4.2] case "/reelwright/llm/script": return json({ cast: [{ name: "Mara", kind: "character" }, { name: "Postman", kind: "character", description: "Young postman in a red cap." }], scenes: [{ title: "The postman arrives", duration: 9, summary: "A postman cycles up to the door.", shots: [{ t: 0, camera: "Wide", text: "He cycles along the seawall." }], dialogue: [{ speaker: "Postman", t: 4, text: "Letter for Mara!" }], cast: ["Postman"] }] });
    // added 2026-11-03 v0.4.2: script import in parts. Table rows become one scene each; a part containing CUT is
    // "cut off" while it can still be split; a part containing FAILONCE fails the first time it is sent.
    case "/reelwright/llm/script/parts": return json(mockSplit(body.script || "", body.part_chars || 0));
    // added 2026-11-08 v0.13.0: Chat tab: the answer streams in reelwright.llm events ("text"); "FAIL" in the question fails
    case "/reelwright/llm/chat": {
      const msgs = body.messages || [];
      const q = String(msgs[msgs.length - 1]?.content || "");
      chatCalls.push({ n: msgs.length, roles: msgs.map(m => m.role), q });
      if (q.includes("FAIL")) return json({ error: "No answer from http://llm.local:30000/v1 for 120 s.", reason: "stall" }, 502);
      const answer = `**Answer** to “${q}” (turn ${Math.ceil(msgs.length / 2)}):\n\n- first point\n- second point\n\n\`\`\`js\nconsole.log("hi");\n\`\`\``;
      const job = body.job;
      const send = d => { for (const cb of listeners["reelwright.llm"] || []) cb({ job, budget: 2048, input: 120, ...d }); };
      llmLive[job] = true;
      send({ phase: "waiting", elapsed: 0, tokens: 0, reasoning: 0, text: "" });
      const steps = q.includes("SLOW") ? 12 : 4;
      for (let i = 1; i <= steps; i++) {
        await new Promise(r => setTimeout(r, q.includes("SLOW") ? 250 : 60));
        if (llmCancelled.has(job)) { delete llmLive[job]; llmCancelled.delete(job); return json({ cancelled: true }); }
        send({ phase: "writing", elapsed: i * 0.1, tokens: i * 5, reasoning: 0, text: answer.slice(0, Math.round(answer.length * i / steps)) });
      }
      delete llmLive[job];
      return json({ reply: answer, ms: 240, model: "qwen3-32b-instruct", tokens: 20, reasoning: false });
    }
    case "/reelwright/llm/cancel": { const live = !!llmLive[body.job]; if (live) llmCancelled.add(body.job); return json({ ok: true, cancelled: live }); }
    case "/reelwright/llm/script": {
      const text = body.script || "";
      const rows = text.split("\n").filter(l => l.trim().startsWith("|"));
      if (!rows.length) return json({ cast: [{ name: "Mara", kind: "character" }, { name: "Postman", kind: "character", description: "Young postman in a red cap." }], scenes: [{ title: "The postman arrives", duration: 9, summary: "A postman cycles up to the door.", shots: [{ t: 0, camera: "Wide", text: "He cycles along the seawall." }], dialogue: [{ speaker: "Postman", t: 4, text: "Letter for Mara!" }], cast: ["Postman"] }] });
      scriptCalls.push({ part: body.part, parts: body.parts, rows: rows.length, notes: body.notes || "", known: (body.known_cast || []).map(c => c.name) });
      if (body.job && await llmWork(body.job, 500, 40 * rows.length)) return json({ cancelled: true });
      if (text.includes("CUT") && body.can_split) return json({ error: "The answer for part " + body.part + " was cut off at 16,384 tokens before its JSON was complete.", reason: "cut" }, 502);
      if (text.includes("FAILONCE") && !failedOnce.has(text)) { failedOnce.add(text); return json({ error: "No answer from http://llm.local:30000/v1 for 120 s. Raise “Stall timeout”. (tried 3 times)", reason: "stall" }, 502); }
      const scenes = rows.map(r => { const c = r.split("|").map(x => x.trim()).filter(Boolean); return { title: c[c.length - 1].slice(0, 40), duration: Number(c[2]) || 8, summary: c[c.length - 1], shots: [{ t: 0, camera: "Static", text: c[c.length - 1] }], dialogue: [], cast: ["Ada"] }; });
      return json({ scenes, cast: [{ name: "Ada", kind: "character", description: body.part === 1 ? "" : "A young necromancer." }, { name: "Crypt " + body.part, kind: "location" }], tokens: 300 * rows.length, ms: 900, attempts: 1 });
    }
    case "/reelwright/promote_frame": return json({ asset: { id: "a_new", name: "Mara frame", file: `reelwright/${SLUG}/frames/s_02_last.png`, width: 1344, height: 768 } });
    case "/reelwright/cast/export": return json({ folder: `output/reelwright/${SLUG}/cast/${body.cast_id}/training`, files: ["a.png", "b.png", "c.png"] });
    case "/reelwright/continuity/check": return json({ available: true, scores: { c_mara: 0.91 } });
    case "/reelwright/upload": return json({ asset: { kind: "image", name: "upload", file: `reelwright/${SLUG}/upload.png`, width: 512, height: 512 } });
    default: return json({ error: "no mock for " + url.pathname }, 404);
  }
}

export function createMockHost() {
  makeArt();
  initTakes();
  projectJSON = JSON.stringify(demoProject());
  storage = createMockStorage({ slug: SLUG, takes, titles: SCENE_TITLES, versions: () => mockVersions, setVersions: v => { mockVersions = v; },
    assets: () => { try { return JSON.parse(projectJSON).assets || []; } catch { return []; } } }); // added 2026-11-03 v0.4.0
  return {
    getProject: () => projectJSON,
    setProject: json => { projectJSON = json; },
    fetchApi: (path, opts) => route(path, opts),
    apiURL(path) {
      const u = new URL(path, "http://mock");
      const file = u.searchParams.get("filename") || "";
      const sub = u.searchParams.get("subfolder") || "";
      if (/\.(mp4|wav|webm)$/.test(file)) return "";
      // added 2026-11-05 v0.7.0: a take's filmstrip sprite (numbered tiles)
      const fm = /^filmstrip_(\d+)\.jpg$/.exec(file);
      if (fm && /\/takes\/[^/]+$/.test(sub)) return filmSprite(sub, Number(fm[1]));
      // added 2026-11-03 v0.4.1: text files come back as text so the Files preview shows real content
      if (/\.(srt|json|otio|fcpxml|txt|log)$/.test(file)) return "data:text/plain;charset=utf-8," + encodeURIComponent(
        file.endsWith(".srt") ? "1\n00:00:01,000 --> 00:00:03,500\nMara: You came back.\n" : `{"file": ${JSON.stringify(file)}}\n`);
      const sceneId = (sub.match(/scenes\/(s_\d+)/) || [])[1];
      const key = sceneId ? SCENE_ART[sceneId] : FILE_ART[file] || (file.includes("mara") ? "mara" : "pier");
      return art[key] || "";
    },
    // [OLD 2026-11-03 v0.5.1->v0.6.0] on(type, cb) { (listeners[type] ||= []).push(cb); },
    // added 2026-11-03 v0.6.0: returns an unsubscribe function, like the real host
    on(type, cb) {
      (listeners[type] ||= []).push(cb);
      return () => { const l = listeners[type] || []; const i = l.indexOf(cb); if (i >= 0) l.splice(i, 1); };
    },
    listenerCount: () => Object.values(listeners).reduce((n, l) => n + l.length, 0), // added 2026-11-03 v0.6.0
    // [OLD 2026-11-03 v0.5.1->v0.6.0] emit(type, detail) { for (const cb of listeners[type] || []) cb(detail); },
    emit(type, detail) { for (const cb of [...(listeners[type] || [])]) cb(detail); },
    isOwnNode: id => String(id) === "7", // added 2026-11-03 v0.6.0: the harness node is node 7
    changes: 0, // added 2026-11-03 v0.6.0: ChangeTracker notices
    changed() { this.changes++; },
    scriptCalls, // added 2026-11-03 v0.4.2: what each script-import request carried
    // [OLD 2026-11-03 v0.5.1->v0.6.0] async queue(request) { queued.push(request); },
    async queue(request) { queued.push(request); if (mockFlags.queueMs) await new Promise(r => setTimeout(r, mockFlags.queueMs)); },
    interrupt() { queued.push({ action: "interrupt" }); },
    // added 2026-11-02 v0.3.0: title and canvas-zoom hooks the real host provides
    titles: [],
    setTitle(status) { this.titles.push(status); },
    wheels: [],
    forwardWheel(e) { this.wheels.push({ deltaY: e.deltaY, ctrl: e.ctrlKey }); },
    isInputLinked: name => name === "model" || name === "clip",
    queued,
    get project() { return JSON.parse(projectJSON); },
  };
}
