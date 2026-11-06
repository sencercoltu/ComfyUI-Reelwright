// HTTP wrappers for the /reelwright routes. The host decides how requests are
// sent: ComfyUI's api.fetchApi inside the app, a mock in the test harness.

let host = null;

export function setHost(h) {
  host = h;
}

async function req(method, route, body, form) {
  const opts = { method };
  if (form) opts.body = form;
  else if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await host.fetchApi(route, opts);
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  // [OLD 2026-11-03 v0.4.1->v0.4.2] if (!res.ok) throw new Error(data?.error || data?.message || `${res.status} ${res.statusText}`);
  if (!res.ok) {
    // added 2026-11-03 v0.4.2: LLM failures carry a reason (stall, gave_up, cut, …); the import splits a "cut" part
    const err = new Error(data?.error || data?.message || `${res.status} ${res.statusText}`);
    err.reason = data?.reason || "";
    err.status = res.status;
    err.data = data; // added 2026-11-03 v0.6.0: the whole answer (e.g. {reason: "slug_conflict", other} from /autosave)
    throw err;
  }
  return data;
}

const q = v => encodeURIComponent(v ?? "");

export const rw = {
  info: () => req("GET", "/reelwright/info"),
  models: () => req("GET", "/reelwright/models"),
  plan: project => req("POST", "/reelwright/plan", { project }),
  upload(file, slug) {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("slug", slug);
    return req("POST", "/reelwright/upload", undefined, form);
  },
  takes: slug => req("GET", "/reelwright/takes?slug=" + q(slug)),
  star: (slug, scene_id, take_id) => req("POST", "/reelwright/takes/star", { slug, scene_id, take_id }),
  deleteTake: (slug, scene_id, take_id) => req("POST", "/reelwright/takes/delete", { slug, scene_id, take_id }),
  // [OLD 2026-11-03 v0.5.1->v0.6.0] merge: project => req("POST", "/reelwright/merge", { project }),
  // [OLD 2026-11-03 v0.5.1->v0.6.0] autosave: project => req("POST", "/reelwright/autosave", { project }),
  // added 2026-11-03 v0.6.0: merge options {draft, range: [from_sid, to_sid] | null, stems, job}; 409 {error: "busy"}
  // while another merge of the project runs (err.status 409)
  merge: (project, opts = {}) => req("POST", "/reelwright/merge", { project, ...opts }),
  mergeCancel: job => req("POST", "/reelwright/merge/cancel", { job }),
  // added 2026-11-03 v0.6.0: {force: true} takes over a folder that holds another project (409 slug_conflict)
  autosave: (project, opts = {}) => req("POST", "/reelwright/autosave", { project, ...opts }),
  versions: slug => req("GET", "/reelwright/versions?slug=" + q(slug)),
  // added 2026-11-02 v0.3.6
  deleteVersions: (slug, names) => req("POST", "/reelwright/versions/delete", { slug, names }),
  deleteAllVersions: slug => req("POST", "/reelwright/versions/delete", { slug, all: true }),
  version: (slug, name) => req("GET", "/reelwright/version?slug=" + q(slug) + "&name=" + q(name)),
  llmSettings: () => req("GET", "/reelwright/llm/settings"),
  saveLlmSettings: s => req("POST", "/reelwright/llm/settings", s),
  llmModels: base_url => req("POST", "/reelwright/llm/models", { base_url }),
  llmTest: () => req("POST", "/reelwright/llm/test", {}),
  // [OLD 2026-11-03 v0.4.1->v0.4.2] rewrite: (project, scene_id, instruction) => req("POST", "/reelwright/llm/rewrite", { project, scene_id, instruction }),
  // [OLD 2026-11-03 v0.4.1->v0.4.2] split: (project, scene_id) => req("POST", "/reelwright/llm/split", { project, scene_id }),
  // job: added 2026-11-03 v0.4.2, so progress events can be matched and the request cancelled
  rewrite: (project, scene_id, instruction, job) => req("POST", "/reelwright/llm/rewrite", { project, scene_id, instruction, job }),
  split: (project, scene_id, job) => req("POST", "/reelwright/llm/split", { project, scene_id, job }),
  script: (project, script) => req("POST", "/reelwright/llm/script", { project, script }),
  // added 2026-11-03 v0.4.2: script import in parts, and stopping a running LLM request
  scriptParts: (script, part_chars) => req("POST", "/reelwright/llm/script/parts", { script, part_chars }),
  scriptPart: (project, body) => req("POST", "/reelwright/llm/script", { project, ...body }),
  llmCancel: job => req("POST", "/reelwright/llm/cancel", { job }),
  // added 2026-11-05 v0.8.0: write the sections of a scene's passes (null = all), one LLM request per pass, with
  // reelwright.llm progress events for `job` and Stop (llmCancel) -> {passes: [{index, start, end, sections}], warnings}
  llmPasses: (project, scene_id, passes, job, instruction = "") => req("POST", "/reelwright/llm/passes",
    instruction ? { project, scene_id, passes: passes || null, instruction, job } : { project, scene_id, passes: passes || null, job }),
  promoteFrame: (slug, scene_id, take_id, which, t) => req("POST", "/reelwright/promote_frame", { slug, scene_id, take_id, which, t }),
  // added 2026-11-06 v0.10.0: a character's lines cut from a take into a voice reference WAV {asset, used, seconds}
  voiceFromTake: (slug, scene_id, take_id, cast_id, lines) => req("POST", "/reelwright/voice_from_take", { slug, scene_id, take_id, cast_id, lines }),
  castExport: (project, cast_id) => req("POST", "/reelwright/cast/export", { project, cast_id }),
  continuityCheck: (project, scene_id) => req("POST", "/reelwright/continuity/check", { project, scene_id }),
  // added 2026-11-02 v0.2.0: official H3 guides, vision descriptions, ComfyUI input/output browser
  llmGuides: () => req("POST", "/reelwright/llm/guides", {}),
  describe: (project, asset_ids, prompt) => req("POST", "/reelwright/llm/describe", { project, asset_ids, prompt }),
  files: (root, query, kind, limit = 400) => req("GET", `/reelwright/files?root=${q(root)}&q=${q(query)}&kind=${q(kind)}&limit=${limit}`),
  importFile: (slug, root, rel) => req("POST", "/reelwright/import", { slug, root, rel }),
  // added 2026-11-02 v0.3.0: Global profiles; the LLM test sends the project's LLM fields
  profiles: () => req("GET", "/reelwright/profiles"),
  saveProfile: (name, global, id, isDefault) => req("POST", "/reelwright/profiles/save", { name, global, id, default: isDefault }),
  deleteProfile: id => req("POST", "/reelwright/profiles/delete", { id }),
  defaultProfile: id => req("POST", "/reelwright/profiles/default", { id }),
  llmTestProject: project => req("POST", "/reelwright/llm/test", { project }),
  // added 2026-11-03 v0.4.0: disk use of every project, and deleting parts of it
  storage: current => req("GET", "/reelwright/storage?current=" + q(current)),
  deleteStorage: (ids, current) => req("POST", "/reelwright/storage/delete", { ids, current }),
  // added 2026-11-03 v0.5.0: peak levels (0-255) of an input audio file, perSecond values a second, for the soundtrack lanes
  // added 2026-11-03 v0.6.0: beat grid of an input audio file {bpm, beats, downbeats}; the WAV a pass of a scene
  // gets from the soundtrack {url}; rebuild a project's take lists from the takes' meta.json {repaired, takes_found}
  beats: file => req("GET", "/reelwright/beats?file=" + q(file)),
  // [OLD 2026-11-03 v0.6.0 review] soundtrackExcerpt: (slug, scene_id, pass) => req("POST", "/reelwright/soundtrack/excerpt", { slug, scene_id, pass }),
  // added 2026-11-03 v0.6.0: the unsaved project may go along, so the excerpt matches what the editor shows
  soundtrackExcerpt: (slug, scene_id, pass, project) => req("POST", "/reelwright/soundtrack/excerpt", project ? { slug, scene_id, pass, project } : { slug, scene_id, pass }),
  storageRepair: slug => req("POST", "/reelwright/storage/repair", { slug }),
  // added 2026-11-05 v0.7.0: the timeline's filmstrip of a take's video (output-relative): a sprite of one row of
  // frames every `interval` seconds, {file, interval, count, tile_w, tile_h, duration}; h is the tile height in pixels
  filmstrip: (file, h = 54) => req("GET", `/reelwright/filmstrip?file=${q(file)}&h=${Math.max(16, Math.round(Number(h) || 54))}`),
  // added 2026-11-06 v0.10.0: spoken lines timed to the speech in a take (output-relative video):
  // lines [{id, t, duration}] -> {lines: [{id, t, end, matched, planned}], segments}
  speech: (file, lines, start, end) => req("POST", "/reelwright/speech", { file, lines, ...(start !== undefined ? { start } : {}), ...(end !== undefined ? { end } : {}) }),
  async waveform(file, per_second = 50) {
    const res = await host.fetchApi(`/reelwright/waveform?file=${q(file)}&per_second=${per_second}`, { method: "GET" });
    if (!res.ok) throw new Error(`waveform ${res.status}`);
    return { peaks: new Uint8Array(await res.arrayBuffer()), perSecond: Number(res.headers.get("X-Per-Second")) || per_second,
      duration: Number(res.headers.get("X-Duration")) || 0 };
  },
};

// `rel` is a path relative to ComfyUI's input or output folder.
/* [OLD 2026-11-05 v0.6.1->v0.7.0] no way to tell the browser that a file at the same path was written again
export function viewURL(rel, type = "output") {
  if (!rel) return "";
  const i = rel.lastIndexOf("/");
  const subfolder = i >= 0 ? rel.slice(0, i) : "";
  const filename = i >= 0 ? rel.slice(i + 1) : rel;
  return host.apiURL(`/view?filename=${q(filename)}&subfolder=${q(subfolder)}&type=${type}`);
}
[/OLD] */
// added 2026-11-05 v0.7.0: `version` (optional) goes into the query, so a file rewritten at the same path (a filmstrip
// of a take that was rendered again) is not taken from the browser's cache
export function viewURL(rel, type = "output", version = "") {
  if (!rel) return "";
  const i = rel.lastIndexOf("/");
  const subfolder = i >= 0 ? rel.slice(0, i) : "";
  const filename = i >= 0 ? rel.slice(i + 1) : rel;
  return host.apiURL(`/view?filename=${q(filename)}&subfolder=${q(subfolder)}&type=${type}${version ? "&rwv=" + q(version) : ""}`);
}
