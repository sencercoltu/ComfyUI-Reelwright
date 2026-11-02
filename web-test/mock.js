// Mock host for the editor harness: a demo "Harbor Lights" project, canned
// /reelwright/* responses, generated preview images and fake progress events.

const SLUG = "harbor_lights";
const listeners = {};
const art = {};
let projectJSON = "";
const queued = [];

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

// ---------- Demo project ----------

function demoProject() {
  const img = (id, code, name, file, category, w = 1024, h = 1365, extra = {}) => ({ id, code, kind: "image", name, file: `reelwright/${SLUG}/${file}`, duration: 0, width: w, height: h, category, defaults: { role: "reference", retention: "fully_preserved", keep: [], soundtrack: false }, notes: "", ...extra });
  const media = (id, code, kind, name, file, duration, category, retention) => ({ id, code, kind, name, file: `reelwright/${SLUG}/${file}`, duration, width: kind === "video" ? 1344 : 0, height: kind === "video" ? 768 : 0, category, defaults: { role: "reference", retention, keep: [], soundtrack: false }, notes: "" });
  const sections = (o = {}) => ({ subject_definitions: "", summary: "", retention_analysis: "", detailed_description: "", overall_soundscape: "", non_diegetic_music: "", ...o });
  const scene = (id, title, duration, mode, { sections: sec, ...rest } = {}) => ({
    id, title, duration, color: "", start: { mode, overlap_frames: 39 }, trim: { keep: "start", in: 0 }, refs: [], cast: [], shots: [], dialogue: [],
    prompt: { mode: "structured", auto: { subjects: true, retention: true, shots: true }, sections: sections(sec), raw: "", pass_prompts: {} },
    overrides: {}, lock: false, notes: "", ...rest,
  });
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
      scene("s_01", "Harbor at dusk", 8.0, "fresh", { cast: [{ id: "c_harbor", outfit: "" }], refs: [{ id: "r_1", asset: "a_v1", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }, { id: "r_2", asset: "a_a1", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_1", t: 0, camera: "Wide · slow push-in", text: "The harbor at dusk, boats rocking, the first lamps flicker on." }], sections: { summary: "Establishing shot of the harbor at dusk.", overall_soundscape: "Gulls, rigging creaks, water lapping." } }),
      scene("s_02", "Mara on the pier", 10.125, "last_frame", { cast: [{ id: "c_mara", outfit: "o_navy" }, { id: "c_harbor", outfit: "" }], refs: [{ id: "r_3", asset: "a_a1", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_2", t: 0, camera: "Medium · static", text: "@Mara walks to the end of the pier and looks out to sea." }],
        dialogue: [{ id: "d_1", speaker: "c_mara", t: 3.5, language: "English", delivery: "calls out", text: "Is anyone still out there?" }], sections: { summary: "Mara waits at the end of the pier." } }),
      scene("s_03", "The letter", 8.708, "tail", { cast: [{ id: "c_mara", outfit: "o_navy" }, { id: "c_letter", outfit: "" }], refs: [{ id: "r_4", asset: "a_p3", role: "keyframe", time: 3.0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_3", t: 0, camera: "Macro · static", text: "Her hands unfold @P3 by candlelight; the paper trembles." }, { id: "h_4", t: 5.0, camera: "Close-up · rack focus", text: "Cut to @Mara's face, rack focus from the candle to her eyes." }],
        dialogue: [{ id: "d_2", speaker: "c_mara", t: 5.2, language: "English", delivery: "whispers", text: "He promised he'd come back." }],
        sections: { summary: "Continuing @tail, Mara opens the letter at the kitchen table.", overall_soundscape: "Kitchen room tone, paper rustle, candle flicker, a far harbor bell.", non_diegetic_music: "N/A" },
        overrides: { seed: 551203, loras: { mode: "add", items: [{ id: "l_candle", name: "candlelight_interiors.safetensors", strength: 0.7, enabled: true }], strengths: { l_grain: 0.35 } } } }),
      scene("s_04", "Flashback: the lighthouse, 1962", 14.375, "fresh", { refs: [{ id: "r_5", asset: "a_p4", role: "first_frame", time: 0, retention: "", keep: [], soundtrack: false }, { id: "r_6", asset: "a_a3", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_5", t: 0, camera: "Wide · slow crane up", text: "The lighthouse in 1962, sepia light sweeping the rocks." }], sections: { summary: "A memory of the lighthouse.", non_diegetic_music: "Music box melody, slow, slightly detuned." },
        overrides: { steps: 28, loras: { mode: "add", items: [{ id: "l_vint", name: "vintage_1960s.safetensors", strength: 0.85, enabled: true }], strengths: {} } } }),
      scene("s_05", "Storm rolls in", 12.25, "fresh", { cast: [{ id: "c_mara", outfit: "o_oil" }, { id: "c_keeper", outfit: "" }],
        refs: [{ id: "r_7", asset: "a_p5", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }, { id: "r_8", asset: "a_v2", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }, { id: "r_9", asset: "a_a4", role: "reference", time: 0, retention: "", keep: [], soundtrack: false }],
        shots: [{ id: "h_6", t: 0, camera: "Handheld · pan right", text: "Waves crash over the pier as the storm arrives." }, { id: "h_7", t: 5.5, camera: "Medium · handheld", text: "@{The Keeper} waves @Mara toward the door." }],
        dialogue: [{ id: "d_3", speaker: "c_keeper", t: 6.0, language: "English", delivery: "shouts", text: "Get inside — the storm's turning!" }], sections: { summary: "The storm hits the harbor." },
        overrides: { loras: { mode: "add", items: [{ id: "l_storm", name: "storm_fx.safetensors", strength: 0.7, enabled: true }], strengths: {} } } }),
      scene("s_06", "Lights come on", 7.292, "last_frame", { cast: [{ id: "c_mara", outfit: "o_oil" }], shots: [{ id: "h_8", t: 0, camera: "Wide · locked-off", text: "One by one the harbor windows light up." }], sections: { summary: "Calm after the storm." } }),
      scene("s_07", "The long walk home", 32.0, "fresh", { cast: [{ id: "c_mara", outfit: "o_navy" }],
        shots: [{ id: "h_9", t: 0, camera: "Wide", text: "@Mara leaves the pier." }, { id: "h_10", t: 6.0, camera: "Tracking", text: "Along the seawall." }, { id: "h_11", t: 14.375, camera: "Medium", text: "The rain starts." }, { id: "h_12", t: 22.0, camera: "Wide · one take", text: "She reaches the door." }],
        sections: { summary: "Mara walks home along the seawall as the rain begins." } }),
      scene("s_08", "Insert: hand on the door", 2.5, "fresh", { trim: { keep: "custom", in: 1.208 }, shots: [{ id: "h_13", t: 0, camera: "Macro", text: "Her hand grips the brass handle." }], sections: { summary: "Close insert of the door handle." } }),
    ],
    markers: [{ id: "m_1", t: 12.0, text: "music swell", color: "amber" }, { id: "m_2", t: 41.2, text: "storm peak", color: "coral" }],
    ui: { tab: "timeline", selected: "s_03", zoom: 13, playhead: 21.375, snap: true, ripple: true },
  };
  return p;
}

// ---------- Render state ----------

const takes = {};
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
  add("s_03", [take("s_03", "v1", { seconds: 8.71, frames: 209 }), take("s_03", "v2", { seconds: 8.71, frames: 209, face: { c_mara: 0.91 } }), take("s_03", "v3", { seconds: 8.71, frames: 209, face: { c_mara: 0.93 } })], "v3");
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
  const sec = s.prompt.sections;
  const spk = [];
  const inPass = s.dialogue.filter(x => x.t >= pass.start && x.t < pass.end);
  for (const d of inPass) if (!spk.includes(d.speaker)) spk.push(d.speaker);
  const sid = id => "S" + (spk.indexOf(id) + 1);
  const defs = subj.map((c, i) => `<Subject ${i + 1}> is ${c.name}, ${c.description.replace(/\.$/, "")}, shown in <Picture ${i + 1}>.`);
  auds.forEach((id, i) => { const c = subj.find(x => x.voice === id); if (c) defs.push(`<Audio ${i + 1}> is the voice-timbre reference for <Subject ${subj.indexOf(c) + 1}> (${sid(c.id)}).`); });
  const ret = subj.map((c, i) => `<Subject ${i + 1}> (appears in [Shot 1]): fully_preserved - identity and appearance are retained.`);
  const shots = s.shots.filter(x => x.t >= pass.start - 0.001 && x.t < pass.end);
  const cam = c => c ? "a " + c.toLowerCase().replace(/ shot$/, "") + " shot: " : "";
  const desc = shots.map((x, i) => i ? `[Shot ${i + 1}] At ${fmt(x.t - pass.start)}, the shot cuts to ${cam(x.camera)}${sub(x.text)}.` : `[Shot 1] ${cam(x.camera).replace(/^a/, "A")}${sub(x.text)}.`);
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
    const passes = planScene(p, s);
    const issues = [];
    if (s.dialogue.some(d => !d.speaker)) issues.push({ level: "warn", message: `${s.title}: a dialogue line has no speaker.` });
    out.scenes[s.id] = {
      passes, status: status[s.id] || "pending", key: "9f3ac2" + s.id.replace("_", "") + "e1d07b44c1", starred: takes[s.id]?.starred || null,
      takes: takes[s.id]?.takes || [], issues, prompts: passes.map(ps => promptFor(p, s, ps)),
    };
  }
  out.timeline.total = t;
  out.issues.push({ level: "info", scene_id: "s_08", message: "Insert: hand on the door is shorter than one pass; it renders 124 frames and keeps 2.50 s." });
  return out;
}

// ---------- Routes ----------

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
    case "/reelwright/info": return json({ version: "0.3.7", ffmpeg: "ffmpeg 8.0", insightface: true, h3_nodes: true });
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
    case "/reelwright/merge": return json({ ok: true, duration: 58.75, files: { video: `reelwright/${SLUG}/cuts/${SLUG}_cut_v4.mp4`, srt: `reelwright/${SLUG}/cuts/${SLUG}_cut_v4.srt`, otio: `reelwright/${SLUG}/cuts/${SLUG}_cut_v4.otio`, fcpxml: `reelwright/${SLUG}/cuts/${SLUG}_cut_v4.fcpxml`, chapters: `reelwright/${SLUG}/cuts/${SLUG}_cut_v4.chapters.txt` } });
    case "/reelwright/autosave": return json({ ok: true, version: "project_20261102_101500.json" });
    // [OLD 2026-11-02 v0.3.5->v0.3.6] case "/reelwright/versions": return json({ versions: [{ name: "project_20261102_101500.json", created: 1793614500, size: 18400 }, { name: "project_20261102_094012.json", created: 1793612412, size: 17200 }] });
    case "/reelwright/versions": return json({ versions: mockVersions });
    // added 2026-11-02 v0.3.6
    case "/reelwright/versions/delete": {
      const kill = body.all ? mockVersions.map(v => v.name) : body.names || [];
      const before = mockVersions.length;
      mockVersions = mockVersions.filter(v => !kill.includes(v.name));
      return json({ removed: before - mockVersions.length, versions: mockVersions });
    }
    case "/reelwright/version": return json({ project: demoProject() });
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
      return json({ sections: { ...s.prompt.sections, summary: (s.prompt.sections.summary || "") + " The candle gutters as she reads.", detailed_description: "Extreme close-ups, warm key light from the candle, shallow depth of field." }, warnings: [] });
    }
    case "/reelwright/llm/split": return json({ pass_prompts: { 1: "[reference generation] Wide: <Subject 1> leaves the pier…", 2: "[reference generation] Medium: the rain starts…", 3: "[video continuation] Wide, one take: she reaches the door." } });
    case "/reelwright/llm/script": return json({ cast: [{ name: "Mara", kind: "character" }, { name: "Postman", kind: "character", description: "Young postman in a red cap." }], scenes: [{ title: "The postman arrives", duration: 9, summary: "A postman cycles up to the door.", shots: [{ t: 0, camera: "Wide", text: "He cycles along the seawall." }], dialogue: [{ speaker: "Postman", t: 4, text: "Letter for Mara!" }], cast: ["Postman"] }] });
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
  return {
    getProject: () => projectJSON,
    setProject: json => { projectJSON = json; },
    fetchApi: (path, opts) => route(path, opts),
    apiURL(path) {
      const u = new URL(path, "http://mock");
      const file = u.searchParams.get("filename") || "";
      const sub = u.searchParams.get("subfolder") || "";
      if (/\.(mp4|wav|webm)$/.test(file)) return "";
      const sceneId = (sub.match(/scenes\/(s_\d+)/) || [])[1];
      const key = sceneId ? SCENE_ART[sceneId] : FILE_ART[file] || (file.includes("mara") ? "mara" : "pier");
      return art[key] || "";
    },
    on(type, cb) { (listeners[type] ||= []).push(cb); },
    emit(type, detail) { for (const cb of listeners[type] || []) cb(detail); },
    async queue(request) { queued.push(request); },
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
