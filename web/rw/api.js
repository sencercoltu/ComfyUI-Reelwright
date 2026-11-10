// HTTP wrappers for the /reelwright routes. The host decides how requests are
// sent: ComfyUI's api.fetchApi inside the app, a mock in the test harness.

let host = null;

export function setHost(h) {
  host = h;
}

// ComfyUI's api.fetchApi (newer frontends) aborts a request after 60 s ("Fetch timeout")
// unless it is given timeoutMs: null. That cut LLM answers off while their tokens were still arriving, whatever
// Global → Limits said. These routes do long work whose limits live on the server (the LLM stall timeout and give-up,
// ffmpeg, face checks), so they wait for the answer; the other routes keep ComfyUI's timeout. Older frontends and the
// test harness ignore the option.
export const LONG_ROUTE = /^\/reelwright\/(llm\/(?!cancel\b)|merge(?!\/cancel)|upload|import|continuity\/|cast\/export|beats|soundtrack\/excerpt|speech|voice_from_take|waveform|filmstrip|storage\/repair|promote_frame|anchor_frame)/;

async function req(method, route, body, form) {
  const opts = { method };
  if (form) opts.body = form;
  else if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  if (LONG_ROUTE.test(route)) opts.timeoutMs = null;
  // A request the browser gives up on (a timeout, a dropped connection) may go on on the
  // server; an LLM request then kept sending progress events for nobody until it ended. Stop it there, and say what
  // happened instead of a bare "Failed to fetch" / "Fetch timeout".
  let res;
  try { res = await host.fetchApi(route, opts); }
  catch (err) {
    const llm = route.startsWith("/reelwright/llm/") && route !== "/reelwright/llm/cancel" && body?.job;
    if (llm) req("POST", "/reelwright/llm/cancel", { job: body.job }).catch(() => {});
    const why = err?.message || String(err);
    const lost = new Error((err?.name === "TimeoutError" ? `the browser stopped waiting for the answer (${why})` : `the connection to ComfyUI was lost before the answer came (${why})`) +
      (llm ? ". The request was stopped on the server too; try again." : ""));
    lost.reason = "lost";
    lost.cause = err;
    throw lost;
  }
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  if (!res.ok) {
    const err = new Error(data?.error || data?.message || `${res.status} ${res.statusText}`);
    err.reason = data?.reason || "";
    err.status = res.status;
    err.data = data;
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
  merge: (project, opts = {}) => req("POST", "/reelwright/merge", { project, ...opts }),
  mergeCancel: job => req("POST", "/reelwright/merge/cancel", { job }),
  autosave: (project, opts = {}) => req("POST", "/reelwright/autosave", { project, ...opts }),
  versions: slug => req("GET", "/reelwright/versions?slug=" + q(slug)),
  deleteVersions: (slug, names) => req("POST", "/reelwright/versions/delete", { slug, names }),
  deleteAllVersions: slug => req("POST", "/reelwright/versions/delete", { slug, all: true }),
  version: (slug, name) => req("GET", "/reelwright/version?slug=" + q(slug) + "&name=" + q(name)),
  llmSettings: () => req("GET", "/reelwright/llm/settings"),
  saveLlmSettings: s => req("POST", "/reelwright/llm/settings", s),
  llmModels: base_url => req("POST", "/reelwright/llm/models", { base_url }),
  llmTest: () => req("POST", "/reelwright/llm/test", {}),
  rewrite: (project, scene_id, instruction, job) => req("POST", "/reelwright/llm/rewrite", { project, scene_id, instruction, job }),
  split: (project, scene_id, job) => req("POST", "/reelwright/llm/split", { project, scene_id, job }),
  script: (project, script) => req("POST", "/reelwright/llm/script", { project, script }),
  scriptParts: (script, part_chars) => req("POST", "/reelwright/llm/script/parts", { script, part_chars }),
  scriptPart: (project, body) => req("POST", "/reelwright/llm/script", { project, ...body }),
  llmCancel: job => req("POST", "/reelwright/llm/cancel", { job }),
  llmChat: (project, messages, job) => req("POST", "/reelwright/llm/chat", { project, messages, job }),
  llmPasses: (project, scene_id, passes, job, instruction = "") => req("POST", "/reelwright/llm/passes",
    instruction ? { project, scene_id, passes: passes || null, instruction, job } : { project, scene_id, passes: passes || null, job }),
  promoteFrame: (slug, scene_id, take_id, which, t) => req("POST", "/reelwright/promote_frame", { slug, scene_id, take_id, which, t }),
  anchorFrame: (slug, file, t, cast_id, anchor_id) => req("POST", "/reelwright/anchor_frame", { slug, file, t, cast_id, anchor_id }),
  crop: (slug, file, box, name) => req("POST", "/reelwright/crop", { slug, file, box, name }),
  detectStatus: () => req("GET", "/reelwright/detect/status"),
  detectDownload: () => req("POST", "/reelwright/detect/download", {}),
  detect: (slug, file, mode, queries = []) => req("POST", "/reelwright/detect", { slug, file, mode, queries }),
  voiceFromTake: (slug, scene_id, take_id, cast_id, lines) => req("POST", "/reelwright/voice_from_take", { slug, scene_id, take_id, cast_id, lines }),
  castExport: (project, cast_id) => req("POST", "/reelwright/cast/export", { project, cast_id }),
  continuityCheck: (project, scene_id) => req("POST", "/reelwright/continuity/check", { project, scene_id }),
  llmGuides: () => req("POST", "/reelwright/llm/guides", {}),
  describe: (project, asset_ids, prompt, clips = []) => req("POST", "/reelwright/llm/describe", { project, asset_ids, prompt, clips }),
  files: (root, query, kind, limit = 400) => req("GET", `/reelwright/files?root=${q(root)}&q=${q(query)}&kind=${q(kind)}&limit=${limit}`),
  importFile: (slug, root, rel) => req("POST", "/reelwright/import", { slug, root, rel }),
  profiles: () => req("GET", "/reelwright/profiles"),
  saveProfile: (name, global, id, isDefault) => req("POST", "/reelwright/profiles/save", { name, global, id, default: isDefault }),
  deleteProfile: id => req("POST", "/reelwright/profiles/delete", { id }),
  defaultProfile: id => req("POST", "/reelwright/profiles/default", { id }),
  llmTestProject: project => req("POST", "/reelwright/llm/test", { project }),
  storage: current => req("GET", "/reelwright/storage?current=" + q(current)),
  deleteStorage: (ids, current) => req("POST", "/reelwright/storage/delete", { ids, current }),
  beats: file => req("GET", "/reelwright/beats?file=" + q(file)),
  soundtrackExcerpt: (slug, scene_id, pass, project) => req("POST", "/reelwright/soundtrack/excerpt", project ? { slug, scene_id, pass, project } : { slug, scene_id, pass }),
  storageRepair: slug => req("POST", "/reelwright/storage/repair", { slug }),
  filmstrip: (file, h = 54) => req("GET", `/reelwright/filmstrip?file=${q(file)}&h=${Math.max(16, Math.round(Number(h) || 54))}`),
  speech: (file, lines, start, end) => req("POST", "/reelwright/speech", { file, lines, ...(start !== undefined ? { start } : {}), ...(end !== undefined ? { end } : {}) }),
  async waveform(file, per_second = 50) {
    const res = await host.fetchApi(`/reelwright/waveform?file=${q(file)}&per_second=${per_second}`, { method: "GET", timeoutMs: null });
    if (!res.ok) throw new Error(`waveform ${res.status}`);
    return { peaks: new Uint8Array(await res.arrayBuffer()), perSecond: Number(res.headers.get("X-Per-Second")) || per_second,
      duration: Number(res.headers.get("X-Duration")) || 0 };
  },
};

// `rel` is a path relative to ComfyUI's input or output folder.
// `version` (optional) goes into the query, so a file rewritten at the same path (a filmstrip
// of a take that was rendered again) is not taken from the browser's cache
export function viewURL(rel, type = "output", version = "") {
  if (!rel) return "";
  const i = rel.lastIndexOf("/");
  const subfolder = i >= 0 ? rel.slice(0, i) : "";
  const filename = i >= 0 ? rel.slice(i + 1) : rel;
  return host.apiURL(`/view?filename=${q(filename)}&subfolder=${q(subfolder)}&type=${type}${version ? "&rwv=" + q(version) : ""}`);
}
