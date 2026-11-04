// added 2026-11-03 v0.4.0: a mock of /reelwright/storage and /reelwright/storage/delete for the harness.
// It builds the same node shape as reelwright/files.py from the mock's takes, versions and assets, plus a few
// leftovers (an orphan scene, an unlisted take, pass videos, cuts, a stray asset) and a second project.

const MB = 1048576;

export function createMockStorage({ slug, takes, titles, versions, setVersions, assets }) {
  const state = {
    cuts: [1, 2, 3, 4], partialCut: 5,
    passes: new Set(["s_04/v1", "s_05/v1"]),
    unlisted: new Set(["s_03/v4"]),
    orphanScene: { id: "s_old", takes: ["v1", "v2"] },
    cast: true,
    strayAssets: new Set(["old_test.png", "from_output/render_0007.png"]),
    goneAssets: new Set(),
    other: true,
    // added 2026-11-03 v0.6.0 (S): a scene's pass cache, a scene folder of another project that shared the folder,
    // a draft cut with stems, the cut counter
    passCache: new Set(["s_05"]),
    foreignScene: { id: "s_lk1", takes: ["v1"], name: "Lighthouse Keeper" },
    draftCut: 6,
  };
  const ts = 1793560000;
  const node = (id, label, kind, extra = {}) => ({ id, label, kind, size: 0, count: 0, mtime: 0, note: "", flags: [], children: [], del: true, ...extra });
  const file = (id, label, size, mtime, extra = {}) => node(id, label, "file", { size, count: 1, mtime, view: id.slice(2), type: id[0] === "o" ? "output" : "input", ...extra });
  const add = (parent, child) => {
    parent.children.push(child);
    parent.size += child.size; parent.count += child.count; parent.mtime = Math.max(parent.mtime, child.mtime);
    return child;
  };
  const base = s => `o:reelwright/${s}`;

  function takeNode(s, sid, t, starred, unlisted) {
    const dir = `${base(s)}/scenes/${sid}/takes/${t.id}`;
    const secs = t.seconds || 8;
    const n = node(dir, t.id, "take", { take: t.id, scene: sid });
    const kept = { del: false, why: "part of the take; delete the take" };
    const when = t.created || ts;
    add(n, file(`${dir}/${s}_${sid.slice(2)}_${t.id}.mp4`, `${s}_${sid.slice(2)}_${t.id}.mp4`, Math.round(secs * 2.4 * MB), when, kept));
    add(n, file(`${dir}/first.png`, "first.png", 1.6 * MB, when, kept));
    add(n, file(`${dir}/last.png`, "last.png", 1.6 * MB, when, kept));
    add(n, file(`${dir}/tail.mp4`, "tail.mp4", 0.9 * MB, when, kept));
    add(n, file(`${dir}/meta.json`, "meta.json", 6200, when, kept));
    if (state.passes.has(`${sid}/${t.id}`)) {
      const p = node(`${dir}/passes`, "passes", "passes", { note: "intermediate pass videos; the take's video is already assembled", flags: ["intermediate"] });
      for (let k = 1; k <= 2; k++) add(p, file(`${dir}/passes/p${k}.mp4`, `p${k}.mp4`, Math.round(secs * 1.6 * MB), when, { del: false, why: "part of the take; delete the take" }));
      add(n, p);
    }
    if (unlisted) { n.flags.push("unlisted"); n.note = "not in the take list (an unfinished or older render)"; }
    else {
      if (starred) n.flags.push("starred");
      n.note = [t.quality || "final", secs.toFixed(1) + " s", new Date(when * 1000).toISOString().slice(0, 16).replace("T", " ")].filter(Boolean).join(" · ");
    }
    return n;
  }

  function current() {
    const p = node("p:" + slug, "Harbor Lights", "project", { slug, flags: ["current"], note: "open in this node", del: false, why: "the project open in this node; delete its parts instead" });
    const scenes = node(`${base(slug)}/scenes`, "Scenes and takes", "group");
    Object.keys(takes).sort().forEach((sid, i) => {
      const entry = takes[sid];
      const extra = [...state.unlisted].filter(x => x.startsWith(sid + "/")).map(x => x.split("/")[1]);
      if (!entry.takes.length && !extra.length) return;
      const sn = node(`${base(slug)}/scenes/${sid}`, `${String(i + 1).padStart(2, "0")} · ${titles[sid] || sid}`, "scene", { sid });
      for (const id of extra) add(sn, takeNode(slug, sid, { id, created: ts + 9500 }, false, true));
      for (const t of [...entry.takes].sort((a, b) => b.created - a.created)) add(sn, takeNode(slug, sid, t, entry.starred === t.id, false));
      if (state.passCache.has(sid)) { // added 2026-11-03 v0.6.0 (S): <scene>/passes, the pass cache
        const pc = node(`${base(slug)}/scenes/${sid}/passes`, "Pass cache", "passes", { flags: ["cache"], note: "finished passes kept for re-use (after Stop, a retake of one pass, a moved keep window); made again when needed" });
        for (const k of ["3f9a1c0d2b", "77e01a9c4f"]) { add(pc, file(`${base(slug)}/scenes/${sid}/passes/${k}.mp4`, `${k}.mp4`, 14 * MB, ts + 9000)); add(pc, file(`${base(slug)}/scenes/${sid}/passes/${k}.json`, `${k}.json`, 900, ts + 9000)); }
        add(sn, pc);
      }
      add(sn, file(`${base(slug)}/scenes/${sid}/index.json`, "index.json", 900, ts, { del: false, why: "the scene's take list; delete the scene instead" }));
      add(scenes, sn);
    });
    if (state.orphanScene) {
      const o = state.orphanScene;
      const sn = node(`${base(slug)}/scenes/${o.id}`, o.id, "scene", { sid: o.id, flags: ["orphan"], note: "not in the project any more" });
      for (const id of o.takes) add(sn, takeNode(slug, o.id, { id, created: ts - 86400 }, id === o.takes[o.takes.length - 1], false));
      add(scenes, sn);
    }
    if (state.foreignScene) { // added 2026-11-03 v0.6.0 (S): not an orphan: it belongs to another project
      const o = state.foreignScene;
      const sn = node(`${base(slug)}/scenes/${o.id}`, o.id, "scene", { sid: o.id, flags: ["other_project"], note: `belongs to another project that used this folder (${o.name})` });
      for (const id of o.takes) add(sn, takeNode(slug, o.id, { id, created: ts - 172800 }, true, false));
      add(scenes, sn);
    }
    add(p, scenes);
    if (state.cuts.length || state.partialCut) {
      const cuts = node(`${base(slug)}/cuts`, "Merged cuts", "group");
      const newest = Math.max(...state.cuts, state.partialCut || 0);
      if (state.partialCut) {
        const g = node(`cut:${slug}:${slug}_cut_v${state.partialCut}`, `cut v${state.partialCut}`, "cut", { flags: ["newest"], note: "newest" });
        add(g, file(`${base(slug)}/cuts/${slug}_cut_v${state.partialCut}.partial.mp4`, `${slug}_cut_v${state.partialCut}.partial.mp4`, 41 * MB, ts + 9800, { flags: ["unfinished"], note: "left over from a merge that didn't finish" }));
        add(cuts, g);
      }
      for (const n of [...state.cuts].sort((a, b) => b - a)) {
        const g = node(`cut:${slug}:${slug}_cut_v${n}`, `cut v${n}`, "cut", { flags: n === newest ? ["newest"] : [], note: n === newest ? "newest" : "" });
        const stem = `${base(slug)}/cuts/${slug}_cut_v${n}`;
        add(g, file(stem + ".mp4", `${slug}_cut_v${n}.mp4`, (130 + n * 4) * MB, ts + n * 1000));
        add(g, file(stem + ".srt", `${slug}_cut_v${n}.srt`, 2100, ts + n * 1000));
        add(g, file(stem + ".otio", `${slug}_cut_v${n}.otio`, 14200, ts + n * 1000));
        add(cuts, g);
      }
      if (state.draftCut) { // added 2026-11-03 v0.6.0 (S): a draft cut with stems and its loudness report
        const n = state.draftCut, stem = `${slug}_cut_v${n}_draft`;
        const g = node(`cut:${slug}:${stem}`, `cut v${n} draft`, "cut", { stem, flags: ["draft"], note: "" });
        add(g, file(`${base(slug)}/cuts/${stem}.mp4`, `${stem}.mp4`, 31 * MB, ts + 9950));
        const st = node(`${base(slug)}/cuts/${stem}_stems`, "stems", "dir");
        for (const w of ["mix.wav", "scenes.wav", "track_t_song.wav"]) add(st, file(`${base(slug)}/cuts/${stem}_stems/${w}`, w, 11 * MB, ts + 9950));
        add(g, st);
        add(g, file(`${base(slug)}/cuts/${stem}_loudness.json`, `${stem}_loudness.json`, 600, ts + 9950));
        add(cuts, g); // after the other cuts, so the harness's cut rows keep their order
      }
      add(cuts, file(`${base(slug)}/cuts/.next`, "next cut number", 2, ts + 9950, { del: false, why: "the next cut number; numbers are never reused" }));
      add(p, cuts);
    }
    const vs = versions();
    if (vs.length) {
      const vg = node(`${base(slug)}/versions`, "Autosaved versions", "group");
      for (const v of vs) add(vg, file(`${base(slug)}/versions/${v.name}`, v.name, v.size, v.created, { kind: "version" }));
      add(p, vg);
    }
    if (state.cast) {
      const cg = node(`${base(slug)}/cast`, "Cast training sets", "group");
      const c = node(`${base(slug)}/cast/c_mara`, "Mara", "dir");
      const tr = node(`${base(slug)}/cast/c_mara/training`, "training", "dir");
      for (let k = 1; k <= 4; k++) add(tr, file(`${base(slug)}/cast/c_mara/training/anchor_0${k}.png`, `anchor_0${k}.png`, 1.4 * MB, ts + 5000));
      add(c, tr);
      add(cg, c);
      add(p, cg);
    }
    add(p, file(`${base(slug)}/project.json`, "project.json", 18400, ts + 9900, { del: false, why: "the project file (delete the whole project instead)", note: "the project file (delete the whole project instead)" }));
    const ag = node(`i:reelwright/${slug}`, "Assets", "group", { note: "input/reelwright/" + slug });
    const seen = new Set();
    for (const a of assets()) {
      if (!a.file?.startsWith(`reelwright/${slug}/`) || seen.has(a.file) || state.goneAssets.has(a.file)) continue;
      seen.add(a.file);
      const size = a.kind === "video" ? 22 * MB : a.kind === "audio" ? 2.1 * MB : 1.9 * MB;
      add(ag, file("i:" + a.file, a.file.split("/").pop(), size, ts - 3600, { kind: "asset", asset_ids: [a.id], flags: ["used"], note: `${a.code} ${a.name}` }));
    }
    for (const name of state.strayAssets) {
      const rel = `reelwright/${slug}/${name}`;
      add(ag, file("i:" + rel, name, 2.3 * MB, ts - 7200, { kind: "asset", asset_ids: [], flags: name.startsWith("from_output") ? ["orphan", "linked"] : ["orphan"],
        note: "not in the project" + (name.startsWith("from_output") ? " · hard link: frees no space while the original exists" : "") }));
    }
    add(p, ag);
    return p;
  }

  function other() {
    const s = "lighthouse_test";
    const p = node("p:" + s, "Lighthouse test", "project", { slug: s });
    const scenes = node(`${base(s)}/scenes`, "Scenes and takes", "group");
    ["s_a", "s_b"].forEach((sid, i) => {
      const sn = node(`${base(s)}/scenes/${sid}`, `0${i + 1} · Test ${i + 1}`, "scene", { sid });
      add(sn, takeNode(s, sid, { id: "v1", created: ts - 400000, seconds: 6 }, true, false));
      add(scenes, sn);
    });
    add(p, scenes);
    add(p, file(`${base(s)}/project.json`, "project.json", 9000, ts - 400000, { del: false, why: "the project file (delete the whole project instead)" }));
    return p;
  }

  function tree() {
    const projects = [current()];
    if (state.other) projects.push(other());
    return { projects, size: projects.reduce((a, p) => a + p.size, 0), current: slug };
  }

  function remove(ids, cur) {
    const t = tree();
    const all = new Map();
    const walk = n => { all.set(n.id, n); n.children.forEach(walk); };
    t.projects.forEach(walk);
    const out = { removed: 0, freed: 0, errors: [], deleted: [] };
    const covered = id => ids.some(a => a !== id && (id.startsWith(a + "/") || (a.startsWith("p:") && id.includes("/" + a.slice(2) + "/"))));
    for (const id of ids.filter(x => !covered(x))) {
      const n = all.get(id);
      if (!n) { out.errors.push({ id, error: "already gone" }); continue; }
      if (!n.del) { out.errors.push({ id, error: n.why || "kept" }); continue; }
      if (id === "p:" + cur) { out.errors.push({ id, error: "the project open in this node can't be deleted as a whole" }); continue; }
      let m;
      if (id === "p:lighthouse_test") state.other = false;
      else if ((m = /^o:reelwright\/[^/]+\/scenes\/([^/]+)\/takes\/([^/]+)$/.exec(id))) {
        const [, sid, tid] = m;
        if (state.unlisted.delete(`${sid}/${tid}`)) { /* gone */ }
        else if (sid === state.orphanScene?.id) state.orphanScene.takes = state.orphanScene.takes.filter(x => x !== tid);
        else if (takes[sid]) {
          takes[sid].takes = takes[sid].takes.filter(x => x.id !== tid);
          if (takes[sid].starred === tid) takes[sid].starred = takes[sid].takes.at(-1)?.id || null;
        }
        state.passes.delete(`${sid}/${tid}`);
      } else if ((m = /\/takes\/([^/]+)\/passes$/.exec(id))) {
        state.passes.delete(`${id.split("/")[3]}/${m[1]}`);
      } else if ((m = /^o:reelwright\/[^/]+\/scenes\/([^/]+)\/passes(\/.*)?$/.exec(id))) { // added 2026-11-03 v0.6.0 (S)
        if (!m[2]) state.passCache.delete(m[1]);
      } else if ((m = /^cut:[^:]+:.+_cut_v(\d+)_draft$/.exec(id))) { // added 2026-11-03 v0.6.0 (S)
        state.draftCut = 0;
      } else if ((m = /^o:reelwright\/[^/]+\/scenes\/([^/]+)$/.exec(id))) {
        if (m[1] === state.foreignScene?.id) state.foreignScene = null; // added 2026-11-03 v0.6.0 (S)
        if (m[1] === state.orphanScene?.id) state.orphanScene = null;
        else if (takes[m[1]]) { takes[m[1]] = { starred: null, takes: [] }; for (const k of [...state.unlisted]) if (k.startsWith(m[1] + "/")) state.unlisted.delete(k); }
      } else if (id.endsWith("/scenes")) {
        for (const k of Object.keys(takes)) takes[k] = { starred: null, takes: [] };
        state.orphanScene = null; state.unlisted.clear();
        state.foreignScene = null; state.passCache.clear(); // added 2026-11-03 v0.6.0 (S)
      } else if ((m = /^cut:[^:]+:.+_cut_v(\d+)$/.exec(id))) {
        if (+m[1] === state.partialCut) state.partialCut = 0;
        state.cuts = state.cuts.filter(x => x !== +m[1]);
      } else if (id.endsWith("/cuts")) { state.cuts = []; state.partialCut = 0; state.draftCut = 0; }
      else if (id.endsWith("/versions")) setVersions([]);
      else if (id.includes("/versions/")) setVersions(versions().filter(v => !id.endsWith("/" + v.name)));
      else if (id.includes("/cast")) state.cast = false;
      else if (id.startsWith("i:")) {
        const rel = id.slice(2);
        if (rel === `reelwright/${slug}`) { state.strayAssets.clear(); for (const a of assets()) state.goneAssets.add(a.file); }
        else { state.strayAssets.delete(rel.split("/").slice(2).join("/")); state.goneAssets.add(rel); }
      } else { out.errors.push({ id, error: "no mock for this id" }); continue; }
      out.removed++; out.freed += n.flags.includes("linked") ? 0 : n.size; out.deleted.push(id);
    }
    return out;
  }

  return { tree, remove };
}
