// Cast tab: the story bible (characters, locations, props) and the rules that
// keep a subject consistent across distant scenes.

import { h, icon, button, toggle, segmented, select, number, text, textarea, section, field, keepChips, slider, confirmInline, chip } from "../ui.js";
import { rw, viewURL } from "../api.js";
import { STABLE_LANGUAGES, VISUAL_RETENTION, newId, findAsset, findCast, assignCodes } from "../model.js";

const KINDS = [["character", "Characters"], ["location", "Locations"], ["prop", "Props"]];

function nextSpeaker(p) {
  const used = new Set(p.cast.map(c => c.speaker));
  let n = 1;
  while (used.has("S" + n)) n++;
  return "S" + n;
}

function addEntry(ctx, kind) {
  const id = newId("c");
  ctx.actions.edit(p => {
    p.cast.push({
      id, kind, name: kind === "character" ? "New character" : kind === "location" ? "New location" : "New prop",
      speaker: kind === "character" ? nextSpeaker(p) : "", description: "", anchors: [], pack_sheet: true,
      outfits: [], default_outfit: "", voice: "", language: p.global.defaults.language, lora: { name: "", strength: 0.8 },
    });
  });
  ctx.store.setEph({ selectedCast: id });
}

function list(ctx, sel) {
  const p = ctx.p;
  return h("div", { class: "rw-col narrow" }, section({
    title: "Story bible", help: "cast.bible",
    children: KINDS.map(([kind, label]) => h("div", { class: "rw-bible-group" },
      h("div", { class: "rw-bible-label" }, label,
        button({ icon: "plus", small: true, variant: "ghost", help: "cast.add." + kind, onClick: () => addEntry(ctx, kind) })),
      p.cast.filter(c => c.kind === kind).map(c => {
        const anchor = findAsset(p, c.anchors[0]);
        const scenes = p.scenes.filter(s => s.cast.some(x => x.id === c.id)).length;
        return h("button", {
          type: "button", class: ["rw-bible-item", sel === c.id && "on"], help: "cast.item",
          onClick: () => ctx.store.setEph({ selectedCast: c.id }),
        }, anchor ? h("img", { class: "rw-avatar", src: viewURL(anchor.file, "input"), alt: "" }) : h("span", { class: "rw-avatar empty" }, icon("cast", 14)),
        h("span", { class: "grow" }, h("b", null, c.name), h("span", { class: "rw-dim small" }, `${c.speaker ? c.speaker + " · " : ""}${scenes} scene${scenes === 1 ? "" : "s"} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}`)));
      }),
      p.cast.every(c => c.kind !== kind) && h("div", { class: "rw-dim small" }, "None yet."))),
  }), h("div", { class: "rw-dim small", help: "cast.bible" }, "Tag an entry in any scene and its anchors, description, voice and LoRA come with it."));
}

function anchorsCard(ctx, c) {
  const p = ctx.p;
  const edit = fn => ctx.actions.edit(q => { const x = findCast(q, c.id); if (x) fn(x, q); });
  const images = p.assets.filter(a => a.kind === "image" && !c.anchors.includes(a.id)).map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file}` }));
  const scenesWithTakes = p.scenes.filter(s => ctx.starredTake(s.id)).map(s => ({ value: s.id, label: s.title }));
  const promote = async which => {
    const sid = ctx.eph.promoteScene || scenesWithTakes[0]?.value;
    const take = sid && ctx.starredTake(sid);
    if (!take) { ctx.actions.toast("Render a scene first; its frames can then become anchors.", "warn"); return; }
    try {
      const res = await rw.promoteFrame(p.slug, sid, take.id, which);
      const a = res.asset;
      ctx.actions.edit(q => {
        q.assets.push({ id: a.id || newId("a"), code: "", kind: "image", name: a.name || `${c.name} frame`, file: a.file, duration: 0, width: a.width || 0, height: a.height || 0,
          category: "subject", defaults: { role: "reference", retention: "fully_preserved", keep: [], soundtrack: false }, notes: "" });
        assignCodes(q.assets);
        findCast(q, c.id).anchors.push(q.assets[q.assets.length - 1].id);
      });
      ctx.actions.toast("Frame added as an anchor.", "ok");
    } catch (err) { ctx.actions.toast("Could not promote the frame: " + err.message, "error"); }
  };
  const anchors = c.anchors.map(id => findAsset(p, id)).filter(Boolean);
  const sheetN = anchors.length <= 4 ? 2 : 3;
  return section({
    title: "Anchors", help: "cast.anchors",
    actions: [
      images.length > 0 && select({ options: images, value: "", placeholder: "+ Add anchor…", help: "cast.anchors.add", onChange: v => edit(x => { x.anchors.push(v); }) }),
    ],
    children: [
      anchors.length ? h("div", { class: "rw-anchor-grid" }, anchors.map(a => h("div", { class: "rw-anchor" },
        h("img", { src: viewURL(a.file, "input"), alt: a.name }),
        h("span", { class: "rw-anchor-label" }, h("b", { class: "mono rw-c-pic" }, a.code), " ", a.name),
        h("button", { type: "button", class: "rw-anchor-x", "aria-label": "Remove anchor", help: "cast.anchors.remove", onClick: () => edit(x => { x.anchors = x.anchors.filter(y => y !== a.id); }) }, icon("close", 11)))))
        : h("div", { class: "rw-empty sm", help: "cast.anchors" }, "No anchors yet. Add front, ¾, profile and full-body pictures for the strongest identity."),
      h("div", { class: "rw-sheet-row" },
        h("div", { class: "grow" },
          toggle({ value: c.pack_sheet, label: "Pack into one sheet", help: "cast.anchors.sheet", onChange: v => edit(x => { x.pack_sheet = v; }) }),
          h("div", { class: "rw-dim small" }, c.pack_sheet ? `Sent as one ${sheetN}×${sheetN} image: 1 picture slot instead of ${anchors.length || "N"}.` : `Sent as ${anchors.length} separate pictures.`)),
        c.pack_sheet && anchors.length > 0 && h("div", { class: "rw-sheet", style: { "grid-template-columns": `repeat(${sheetN}, 1fr)` }, help: "cast.anchors.sheet" },
          anchors.slice(0, sheetN * sheetN).map(a => h("img", { src: viewURL(a.file, "input"), alt: "" })))),
      h("div", { class: "rw-row wrap", help: "cast.promote" },
        h("span", { class: "rw-dim small" }, "Promote a rendered frame:"),
        select({ options: scenesWithTakes, value: ctx.eph.promoteScene || scenesWithTakes[0]?.value || "", placeholder: scenesWithTakes.length ? undefined : "no renders yet", help: "cast.promote.scene",
          onChange: v => { ctx.eph.promoteScene = v; } }),
        button({ label: "First frame", small: true, help: "cast.promote", onClick: () => promote("first") }),
        button({ label: "Last frame", small: true, help: "cast.promote", onClick: () => promote("last") })),
    ],
  });
}

function profileCard(ctx, c) {
  const p = ctx.p;
  const edit = fn => ctx.actions.edit(q => { const x = findCast(q, c.id); if (x) fn(x, q); });
  const audio = p.assets.filter(a => a.kind === "audio").map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file}` }));
  const loras = ctx.eph.models?.loras || [];
  return section({
    title: c.kind === "character" ? "Character" : c.kind === "location" ? "Location" : "Prop", help: "cast.profile",
    actions: button({ icon: "trash", small: true, variant: "danger-ghost", label: "Delete", help: "cast.delete", onClick: e => {
      confirmInline(e.currentTarget.closest(".rw-card"), `Delete ${c.name}? Scenes keep their other references.`, () => {
        ctx.actions.edit(q => { q.cast = q.cast.filter(x => x.id !== c.id); for (const s of q.scenes) { s.cast = s.cast.filter(x => x.id !== c.id); for (const d of s.dialogue) if (d.speaker === c.id) d.speaker = ""; } });
        ctx.store.setEph({ selectedCast: "" });
      });
    } }),
    children: [
      field("Name", text({ value: c.name, key: "cast-name-" + c.id, help: "cast.name", onChange: v => edit(x => { x.name = v; }) }), { help: "cast.name" }),
      field("Kind", segmented({ small: true, value: c.kind, help: "cast.kind", options: KINDS.map(([k]) => k), onChange: v => edit(x => { x.kind = v; }) }), { help: "cast.kind" }),
      c.kind === "character" && field("Speaker ID", text({ value: c.speaker, key: "cast-spk-" + c.id, mono: true, width: "70px", help: "cast.speaker", onChange: v => edit(x => { x.speaker = v.toUpperCase(); }) }), { help: "cast.speaker" }),
      h("div", { class: "rw-field wide" }, h("span", { class: "rw-field-label", help: "cast.description" }, "Description"),
        textarea({ value: c.description, rows: 3, key: "cast-desc-" + c.id, help: "cast.description", placeholder: "Woman, early 30s, short auburn hair, navy pea coat with brass buttons.", onChange: v => edit(x => { x.description = v; }) })),
      c.kind === "character" && field("Voice", select({ options: audio, value: c.voice, placeholder: "no voice reference", help: "cast.voice", onChange: v => edit(x => { x.voice = v; }) }), { help: "cast.voice" }),
      c.kind === "character" && field("Language", select({ options: STABLE_LANGUAGES, value: c.language, help: "cast.language", onChange: v => edit(x => { x.language = v; }) }), { help: "cast.language" }),
      field("Identity LoRA", h("span", { class: "rw-row" },
        select({ options: loras, value: c.lora.name, placeholder: "none", mono: true, help: "cast.lora", onChange: v => edit(x => { x.lora.name = v; }) }),
        number({ value: c.lora.strength, min: -4, max: 4, step: 0.05, width: "74px", help: "cast.lora.strength", onChange: v => edit(x => { x.lora.strength = v ?? 0.8; }) })), { help: "cast.lora" }),
      h("div", { class: "rw-row" },
        button({ label: "Export training set", icon: "download", small: true, help: "cast.export", onClick: async () => {
          try { const r = await rw.castExport(p, c.id); ctx.actions.toast(`Exported ${r.files?.length ?? 0} files to ${r.folder}.`, "ok"); }
          catch (err) { ctx.actions.toast("Export failed: " + err.message, "error"); }
        } })),
    ],
  });
}

function outfitsCard(ctx, c) {
  const edit = fn => ctx.actions.edit(q => { const x = findCast(q, c.id); if (x) fn(x); });
  const editO = (id, fn) => edit(x => { const o = x.outfits.find(y => y.id === id); if (o) fn(o); });
  return section({
    title: c.kind === "character" ? "Outfits" : "Variants", help: "cast.outfits",
    actions: button({ label: "Add", icon: "plus", small: true, help: "cast.outfits.add", onClick: () => edit(x => {
      const o = { id: newId("o"), name: x.outfits.length ? "Outfit " + (x.outfits.length + 1) : "Default", retention: "fully_preserved", keep: [], assets: [] };
      x.outfits.push(o);
      if (!x.default_outfit) x.default_outfit = o.id;
    }) }),
    children: c.outfits.length ? c.outfits.map(o => h("div", { class: "rw-outfit" },
      h("div", { class: "rw-row" },
        h("button", { type: "button", class: ["rw-radio-btn", c.default_outfit === o.id && "on"], help: "cast.outfits.default", "aria-label": "Default outfit", onClick: () => edit(x => { x.default_outfit = o.id; }) }),
        text({ value: o.name, key: "outfit-" + o.id, help: "cast.outfits.name", onChange: v => editO(o.id, y => { y.name = v; }) }),
        select({ options: VISUAL_RETENTION, value: o.retention, mono: true, help: "cast.outfits.retention", onChange: v => editO(o.id, y => { y.retention = v; }) }),
        button({ icon: "trash", small: true, variant: "ghost", help: "cast.outfits.remove", onClick: () => edit(x => { x.outfits = x.outfits.filter(y => y.id !== o.id); if (x.default_outfit === o.id) x.default_outfit = x.outfits[0]?.id || ""; }) })),
      keepChips({ values: o.keep, help: "cast.outfits.keep", onChange: v => editO(o.id, y => { y.keep = v; }) })))
      : h("div", { class: "rw-empty sm", help: "cast.outfits" }, "One look everywhere. Add outfits when the character changes clothes."),
  });
}

function appearances(ctx, c) {
  const p = ctx.p;
  const g = p.global.continuity;
  const scenes = p.scenes.map((s, i) => ({ s, i })).filter(({ s }) => s.cast.some(x => x.id === c.id));
  const faceOK = !!ctx.eph.info?.insightface;
  return section({
    title: "Appearances", help: "cast.appearances",
    actions: h("span", { class: "rw-dim small" }, faceOK ? `face match vs anchors · threshold ${g.face_threshold.toFixed(2)}` : "face match needs the insightface package"),
    children: scenes.length ? h("div", { class: "rw-appear-grid" }, scenes.map(({ s, i }) => {
      const take = ctx.starredTake(s.id);
      const checked = ctx.eph.faceChecks?.[s.id]?.[c.id];
      const score = checked ?? take?.face?.[c.id];
      const drift = typeof score === "number" && score < g.face_threshold;
      return h("div", { class: ["rw-appear", drift && "drift"] },
        h("button", { type: "button", class: "rw-appear-thumb", help: "cast.appearances.open", style: take?.files?.first ? { "background-image": `url("${viewURL(take.files.first)}")` } : null,
          onClick: () => ctx.actions.select(s.id, "scene") }, h("span", { class: "mono" }, String(i + 1).padStart(2, "0"))),
        h("span", { class: "rw-ellipsis small" }, s.title),
        typeof score === "number"
          ? [h("span", { class: "rw-meter-bar" }, h("span", { class: ["rw-meter-fill", drift ? "rw-bg-warn" : "rw-bg-aud"], style: { width: Math.round(score * 100) + "%" } })),
            h("span", { class: ["mono small", drift ? "rw-c-warn" : "rw-c-aud"], help: "cast.appearances.score" }, score.toFixed(2) + (drift ? " drift" : ""))]
          : h("span", { class: "rw-dim small" }, take ? "not checked" : "not rendered"),
        h("div", { class: "rw-row" },
          take && faceOK && button({ label: "Check", small: true, help: "cast.appearances.check", onClick: async () => {
            try {
              const r = await rw.continuityCheck(p, s.id);
              ctx.store.setEph({ faceChecks: { ...(ctx.eph.faceChecks || {}), [s.id]: r.scores || {} } });
            } catch (err) { ctx.actions.toast("Face check failed: " + err.message, "error"); }
          } }),
          drift && button({ label: "Re-render", small: true, variant: "warn-ghost", help: "cast.appearances.retake", onClick: () => ctx.actions.run("take", [s.id]) })));
    })) : h("div", { class: "rw-empty sm" }, `${c.name} is not in any scene yet. Add them from a scene's “Cast in this scene” card.`),
  });
}

function rulesCard(ctx) {
  const g = ctx.p.global.continuity;
  const set = fn => ctx.actions.edit(q => fn(q.global.continuity));
  return section({
    title: "Continuity rules", help: "cast.rules",
    children: [
      h("div", { class: "rw-explain", help: "cast.rules.anchors" },
        h("div", { class: "rw-explain-row" }, h("span", { class: "rw-dim small" }, "Chained"),
          h("span", { class: "rw-chain" }, [1, 0.8, 0.6, 0.45, 0.3, 0.18].map((o, i) => h("span", { class: "rw-chain-dot", style: { opacity: o } }, i === 0 ? "01" : i === 5 ? "10" : "")))),
        h("div", { class: "rw-explain-row" }, h("span", { class: "rw-dim small" }, "Anchored"),
          h("span", { class: "rw-chain" }, h("span", { class: "rw-chain-src" }, "anchors"), ["02", "03", "06", "10"].map(n => h("span", { class: "rw-chain-dot" }, n)))),
        h("div", { class: "rw-dim small" }, "Reelwright always sends the anchors, so scene 10 gets the same identity input as scene 2.")),
      field("Re-anchor after", number({ value: g.reanchor_after, min: 0, max: 20, width: "64px", help: "cast.rules.reanchor", onChange: v => set(c => { c.reanchor_after = v ?? 2; }) }), { help: "cast.rules.reanchor" }),
      field("Face check", toggle({ value: g.face_check, help: "cast.rules.faceCheck", onChange: v => set(c => { c.face_check = v; }) }), { help: "cast.rules.faceCheck" }),
      field("Threshold", slider({ value: g.face_threshold, min: 0.5, max: 0.99, step: 0.01, help: "cast.rules.threshold", format: v => v.toFixed(2), onChange: v => set(c => { c.face_threshold = v; }) }), { help: "cast.rules.threshold" }),
      field("On drift", segmented({ small: true, value: g.on_drift, help: "cast.rules.onDrift", options: [
        { value: "flag", label: "Flag", help: "cast.rules.onDrift" }, { value: "retake", label: "Re-render", help: "cast.rules.onDrift" }],
      onChange: v => set(c => { c.on_drift = v; }) }), { help: "cast.rules.onDrift" }),
      h("div", { class: "rw-note", help: "cast.rules.vae" }, icon("info", 12), "Per-scene VAEs are safe: scenes hand over pixels (a frame or a clip), never latents."),
    ],
  });
}

export function render(ctx) {
  const p = ctx.p;
  const c = findCast(p, ctx.eph.selectedCast) || p.cast[0];
  return h("div", { class: "rw-cols", dataset: { scroll: "cast-cols" } },
    list(ctx, c?.id),
    c ? h("div", { class: "rw-col wide" },
      h("div", { class: "rw-cast-head" }, h("span", { class: "rw-cast-name" }, c.name),
        c.speaker && chip({ label: `<Subject> · ${c.speaker}`, kind: "pic", help: "cast.speaker" }),
        h("span", { class: "rw-flex" })),
      anchorsCard(ctx, c), profileCard(ctx, c), outfitsCard(ctx, c), appearances(ctx, c))
      : h("div", { class: "rw-col wide" }, section({ title: "Story bible", help: "cast.bible", children: [
        h("div", { class: "rw-empty" }, "Add a character, location or prop. Its anchors are sent to every scene it appears in, which keeps it looking the same."),
        h("div", { class: "rw-row" }, KINDS.map(([k, label]) => button({ label: "New " + label.slice(0, -1).toLowerCase(), icon: "plus", help: "cast.add." + k, onClick: () => addEntry(ctx, k) }))),
      ] })),
    h("div", { class: "rw-col mid" }, rulesCard(ctx)));
}
