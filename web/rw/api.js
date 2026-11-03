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
  merge: project => req("POST", "/reelwright/merge", { project }),
  autosave: project => req("POST", "/reelwright/autosave", { project }),
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
  promoteFrame: (slug, scene_id, take_id, which, t) => req("POST", "/reelwright/promote_frame", { slug, scene_id, take_id, which, t }),
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
};

// `rel` is a path relative to ComfyUI's input or output folder.
export function viewURL(rel, type = "output") {
  if (!rel) return "";
  const i = rel.lastIndexOf("/");
  const subfolder = i >= 0 ? rel.slice(0, i) : "";
  const filename = i >= 0 ? rel.slice(i + 1) : rel;
  return host.apiURL(`/view?filename=${q(filename)}&subfolder=${q(subfolder)}&type=${type}`);
}
