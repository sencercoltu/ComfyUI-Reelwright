// Cast tab: the story bible (characters, locations, props) and the rules that
// keep a subject consistent across distant scenes.

import {
  h, icon, button, toggle, segmented, select, number, text, textarea, section, field, keepChips, slider, chip,
  confirmDialog, choiceDialog, sortable, dragGrip, moveItem, kept, triggerInput,
} from "../ui.js";
import {
  dialogueSeconds, sceneIndex, STABLE_LANGUAGES, VISUAL_RETENTION, newId, findAsset, findCast, assignCodes,
  castDescription, sheetGrid, anchorPixels, sheetURL, castPacks, assetGroupName, partOwner, SMALL_TILE_PX, refClip,
  fmtTime, unskipAnchor, clearAnchorFrame, newCastMember, triggerText, refmodParts, refmodTokens, refmodSeconds,
  refmodFrames,
} from "../model.js";
import { rw, viewURL } from "../api.js";
import { clipEditor } from "./scene.js";
import { openCrop } from "../crop.js";
import { describeBox } from "./assets.js";

const KINDS = [["character", "Characters"], ["location", "Locations"], ["prop", "Props"]];

function addEntry(ctx, kind) {
  const m = newCastMember(ctx.p, kind);
  ctx.actions.edit(p => { p.cast.push(m); });
  ctx.store.setEph({ selectedCast: m.id });
}

// Voice from a take. The scenes whose starred take has lines of this character are offered;
// the server times them to the speech in the take, cuts them (up to 15 s) into a WAV in the project's input folder, and
// it becomes the character's voice reference (one undo step with the new asset).
async function voiceFromTake(ctx, c) {
  const p = ctx.p;
  const cands = p.scenes.map(s => ({ s, take: ctx.starredTake(s.id), lines: s.dialogue.filter(d => d.speaker === c.id && (d.text || "").trim()) }))
    .filter(x => x.take?.files?.video && x.lines.length);
  if (!cands.length) {
    ctx.actions.toast(`No rendered scene has lines of ${c.name} yet: render a scene where ${c.name} speaks first.`, "warn");
    return;
  }
  const secs = x => x.lines.reduce((n, d) => n + dialogueSeconds(d), 0);
  const pick = cands.length === 1 ? cands[0].s.id : await choiceDialog(ctx.root, {
    title: `${c.name}'s voice from a take`, help: "cast.voiceFromTake",
    message: `Cut ${c.name}'s lines from a scene's starred take (2–15 s) and use them as the voice reference. Pick the scene where ${c.name} sounds best and says the most.`,
    choices: cands.slice(0, 8).sort((a, b) => secs(b) - secs(a)).map(x => ({
      value: x.s.id, label: `${String(sceneIndex(p, x.s.id) + 1).padStart(2, "0")} ${x.s.title} · ${x.lines.length} line${x.lines.length === 1 ? "" : "s"}, about ${secs(x).toFixed(1)} s`, help: "cast.voiceFromTake" })),
    cancelValue: null,
  });
  const x = cands.find(q => q.s.id === pick);
  if (!x) return;
  ctx.store.setEph({ voiceCut: c.id });
  try {
    const res = await rw.voiceFromTake(p.slug, x.s.id, x.take.id, c.id, x.lines.map(d => ({ id: d.id, t: d.t, duration: dialogueSeconds(d) })));
    const a = res.asset;
    const id = newId("a");
    ctx.actions.edit(q => {
      q.assets.push({ id, code: "", kind: "audio", name: `${c.name} voice (scene ${String(sceneIndex(q, x.s.id) + 1).padStart(2, "0")})`, file: a.file,
        duration: a.duration || 0, width: 0, height: 0, category: "voice", defaults: { role: "reference", retention: "reference", keep: [], soundtrack: false },
        notes: `Cut from take ${x.take.id} of ${x.s.title}.`, description: "", group: "", tags: [] });
      assignCodes(q.assets);
      const m = findCast(q, c.id);
      if (m) m.voice = id;
    }, { label: `${c.name}'s voice from a take` });
    ctx.actions.toast(`${c.name}'s voice reference: ${res.seconds.toFixed(1)} s from ${res.used.length} line${res.used.length === 1 ? "" : "s"} of ${x.s.title}. Ctrl+Z undoes it.`, "ok");
  } catch (err) {
    ctx.actions.toast(`Couldn't cut the voice: ${err.message}`, "error");
  } finally {
    ctx.store.setEph({ voiceCut: null });
  }
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
        h("span", { class: "grow" }, h("b", null, c.name), h("span", { class: "rw-dim small" }, `${partOf(p, c) ? `part of ${partOf(p, c).name} · ` : ""}${scenes} scene${scenes === 1 ? "" : "s"} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}`)));
      }),
      p.cast.every(c => c.kind !== kind) && h("div", { class: "rw-dim small" }, "None yet."))),
  }), h("div", { class: "rw-dim small", help: "cast.bible" }, "Tag an entry in any scene and its anchors, description, voice and LoRA come with it."));
}

function anchorsCard(ctx, c) {
  const p = ctx.p;
  const edit = fn => ctx.actions.edit(q => { const x = findCast(q, c.id); if (x) fn(x, q); }, { label: `Edit ${c.name}` });
  const frames = (c.video_anchors || []).map(va => ({ va, fa: findAsset(p, va.frame_asset), v: findAsset(p, va.asset) }))
    .filter(x => x.fa?.kind === "image" && !c.anchors.includes(x.fa.id));
  const frameIds = new Set(frames.map(x => x.fa.id));
  const frameLabel = x => `${x.fa.code} · frame ${x.va.frame !== null && x.va.frame !== undefined ? fmtTime(x.va.frame) + " " : ""}of ${x.v?.code || "a video anchor"}`;
  const images = [...frames.map(x => ({ value: x.fa.id, label: frameLabel(x), pre: "video anchor frame" })),
    ...p.assets.filter(a => a.kind === "image" && !c.anchors.includes(a.id) && !frameIds.has(a.id)).map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file}`, pre: assetGroupName(p, a) }))];
  const scenesWithTakes = p.scenes.filter(s => ctx.starredTake(s.id)).map(s => ({ value: s.id, label: s.title }));
  const promote = async which => {
    const sid = ctx.eph.promoteScene || scenesWithTakes[0]?.value;
    const take = sid && ctx.starredTake(sid);
    if (!take) { ctx.actions.toast("Render a scene first; its frames can then become anchors.", "warn"); return; }
    try {
      const res = await rw.promoteFrame(p.slug, sid, take.id, which);
      const a = res.asset;
      let anchored = false;
      ctx.actions.edit(q => {
        q.assets.push({ id: a.id || newId("a"), code: "", kind: "image", name: a.name || `${c.name} frame`, file: a.file, duration: 0, width: a.width || 0, height: a.height || 0,
          category: "subject", defaults: { role: "reference", retention: "fully_preserved", keep: [], soundtrack: false }, notes: "",
          description: "", group: "", tags: [] });
        assignCodes(q.assets);
        const x = findCast(q, c.id);
        if (x) { x.anchors.push(q.assets[q.assets.length - 1].id); anchored = true; }
      });
      if (anchored) ctx.actions.toast("Frame added as an anchor.", "ok");
      else ctx.actions.toast(`Frame added to the assets. “${c.name}” was deleted meanwhile, so it is not an anchor.`, "warn");
    } catch (err) { ctx.actions.toast("Could not promote the frame: " + err.message, "error"); }
  };
  const anchors = c.anchors.map(id => findAsset(p, id)).filter(Boolean);
  const [cols, rows] = sheetGrid(anchors.filter(a => a.kind === "image").length);
  const scenesIn = p.scenes.filter(s => s.cast.some(e => e.id === c.id));
  const packedSomewhere = anchors.length > 1 && (c.pack_sheet === true || (c.pack_sheet === "auto" && scenesIn.some(s => castPacks(p, s, c))));
  const W = p.global.output.width, H = p.global.output.height, ds = p.global.draft.scale || 0.5;
  const px = packed => [anchorPixels(p, c, packed, W, H), anchorPixels(p, c, packed, Math.round(W * ds), Math.round(H * ds))];
  const [fullS, draftS] = px(true), [fullA, draftA] = px(false);
  const autoScenes = c.pack_sheet === "auto" ? scenesIn.filter(s => castPacks(p, s, c)).length : 0;
  const packNote = anchors.length < 2 ? "With one anchor there is nothing to pack."
    : c.pack_sheet === "auto" ? (autoScenes ? `One ${cols}×${rows} sheet in ${autoScenes} of ${scenesIn.length} scene${scenesIn.length === 1 ? "" : "s"} (they would go over 9 pictures); separate pictures elsewhere.`
      : `Separate pictures: every scene it is in fits within H3's 9 pictures. It switches to a ${cols}×${rows} sheet in a scene that would not.`)
    : c.pack_sheet ? `Sent as one ${cols}×${rows} image: 1 picture slot instead of ${anchors.length}.`
      : `Sent as ${anchors.length} separate pictures (${anchors.length} of the 9 slots).`;
  const sizeNote = anchors.length > 1 && `Each anchor reaches H3 at about ${fullS} px in a sheet (${draftS} px in drafts), ${fullA} px on its own (${draftA} px in drafts)` +
    (p.global.output.ref_image_size === "max" ? " (reference size: max)." : ". Global → Output → Reference size \"max\" sends them larger, but samples slower.");
  return section({
    title: "Anchors", help: "cast.anchors",
    actions: [
      images.length > 0 && select({ options: images, value: "", placeholder: "+ Add anchor…", help: "cast.anchors.add", onChange: v => edit(x => { x.anchors.push(v); }) }),
    ],
    children: [
      lookNote(c, "anchor pictures"),
      anchors.length ? h("div", { class: "rw-anchor-grid" }, anchors.map(a => h("div", { class: "rw-anchor" },
        h("img", { src: viewURL(a.file, "input"), alt: a.name }),
        h("span", { class: "rw-anchor-label" }, h("b", { class: "mono rw-c-pic" }, a.code), " ", a.name,
          (c.video_anchors || []).some(va => va.frame_asset === a.id) && h("span", { class: "rw-dim" }, " · video frame")),
        a.kind === "image" && h("button", { type: "button", class: "rw-anchor-crop", "aria-label": "Crop this anchor", help: "cast.anchors.crop", key: `anchor-crop-${c.id}-${a.id}`,
          onClick: () => openCrop(ctx, a, { cast: c.id }) }, icon("crop", 11)),
        h("button", { type: "button", class: "rw-anchor-x", "aria-label": "Remove anchor", help: "cast.anchors.remove", onClick: () => edit((x, q) => { x.anchors = x.anchors.filter(y => y !== a.id); unskipAnchor(q, x.id, a.id); }) }, icon("close", 11)))))
        : h("div", { class: "rw-empty sm", help: "cast.anchors" }, "No anchors yet. Add front, ¾, profile and full-body pictures for the strongest identity."),
      frames.length > 0 && h("div", { class: "rw-anchor-ready small", help: "cast.anchors.frames" },
        h("span", { class: "rw-dim" }, frames.length === 1 ? "A frame picture is ready:" : "Frame pictures are ready:"),
        frames.map(x => button({ label: "+ " + frameLabel(x), small: true, variant: "ghost", key: `anchor-frame-add-${x.fa.id}`, help: "cast.anchors.frames",
          onClick: () => edit(y => { if (!y.anchors.includes(x.fa.id)) y.anchors.push(x.fa.id); }) }))),
      h("div", { class: "rw-sheet-row" },
        h("div", { class: "grow rw-col-tight" },
          segmented({ small: true, value: c.pack_sheet === "auto" ? "auto" : c.pack_sheet ? "sheet" : "separate", help: "cast.anchors.sheet",
            onChange: v => edit(x => { x.pack_sheet = v === "auto" ? "auto" : v === "sheet"; }), options: [
              { value: "auto", label: "Auto", help: "cast.anchors.sheet.auto" },
              { value: "sheet", label: "One sheet", help: "cast.anchors.sheet.on" },
              { value: "separate", label: "Separate", help: "cast.anchors.sheet.off" }] }),
          h("div", { class: "rw-dim small" }, packNote),
          sizeNote && h("div", { class: ["small", (packedSomewhere ? draftS : draftA) < 200 ? "rw-c-warn" : "rw-dim"], help: "cast.anchors.size" }, sizeNote),
          packedSomewhere && fullS < SMALL_TILE_PX && h("div", { class: "rw-note warn small", help: "cast.anchors.small" }, icon("warn", 12),
            h("span", null, `In the ${cols}×${rows} sheet each picture reaches H3 at only about ${fullS} px, too small for a reliable identity. Keep a sheet to about 4 pictures (a clear face and a full body), pick Separate or Auto, or set Global → Output → Reference images to max.`))),
        packedSomewhere && kept(ctx, "sheet160-" + c.id, sheetURL(p, c, 160), () => h("img", { class: "rw-sheet-img", src: ctx.host.apiURL(sheetURL(p, c, 160)), alt: "", help: "cast.anchors.sheetPreview",
          onClick: () => window.open(ctx.host.apiURL(sheetURL(p, c, 768)), "_blank", "noopener") }))),
      h("div", { class: "rw-row wrap", help: "cast.promote" },
        h("span", { class: "rw-dim small" }, "Promote a rendered frame:"),
        select({ options: scenesWithTakes, value: ctx.eph.promoteScene || scenesWithTakes[0]?.value || "", placeholder: scenesWithTakes.length ? undefined : "no renders yet", help: "cast.promote.scene",
          onChange: v => { ctx.eph.promoteScene = v; } }),
        button({ label: "First frame", small: true, help: "cast.promote", onClick: () => promote("first") }),
        button({ label: "Last frame", small: true, help: "cast.promote", onClick: () => promote("last") })),
    ],
  });
}

// ---- video anchors: clips of the cast member that go with its pictures as part of its subject ("shown in <Picture 1> and in
// <Video 2>"), to every scene it is in, after the scene's own videos while H3's budget has room (3 videos, 15 s of
// video in all; model.pickVideoAnchors). Each has a From / To like a scene's video reference and sends its sound only
// when "with sound" is on. Drag the grip to reorder: the first ones go first when room is short.
// Help keys of a video anchor's clip editor (From / To / Length keep their v0.16.0 names)
const VA_HELP = name => ({ clipFrom: "cast.videoAnchors.from", clipTo: "cast.videoAnchors.to", clipLength: "cast.videoAnchors.length" })[name] || "cast.videoAnchors." + name;
function videoAnchorsCard(ctx, c) {
  const p = ctx.p;
  const edit = (fn, label = `Edit ${c.name}`) => ctx.actions.edit(q => { const x = findCast(q, c.id); if (x) fn(x, q); }, { label });
  const one = (id, fn) => edit(x => { const va = (x.video_anchors || []).find(y => y.id === id); if (va) fn(va); });
  const remove = id => edit((x, q) => {
    const va = (x.video_anchors || []).find(y => y.id === id);
    if (va) clearAnchorFrame(q, x, va);
    x.video_anchors = x.video_anchors.filter(y => y.id !== id);
    unskipAnchor(q, x.id, id);
  }, "Remove video anchor");
  // A frame of the clip as a picture for the character's identity. One picture per video anchor: taking
  // another frame replaces its file (an anchor it already is stays one); it is offered under Anchors → + Add anchor.
  const setFrame = async (va, a, t) => {
    let res;
    try { res = await rw.anchorFrame(p.slug, a.file, t, c.id, va.id); }
    catch (err) { ctx.actions.toast("Could not take the frame: " + err.message, "error"); return; }
    const f = res.asset || {}, at = Number.isFinite(Number(res.t)) ? Number(res.t) : t;
    let state = "gone", code = "";
    ctx.actions.edit(q => {
      const x = findCast(q, c.id), v = x && (x.video_anchors || []).find(y => y.id === va.id);
      if (!v) return;
      let fa = v.frame_asset && q.assets.find(z => z.id === v.frame_asset);
      if (fa) { Object.assign(fa, { file: f.file, width: f.width || 0, height: f.height || 0 }); state = x.anchors.includes(fa.id) ? "anchor" : "moved"; }
      else {
        fa = { id: newId("a"), code: "", kind: "image", name: `${x.name} · frame of ${a.code}`, file: f.file, duration: 0, width: f.width || 0, height: f.height || 0,
          category: "subject", defaults: { role: "reference", retention: "fully_preserved", keep: [], soundtrack: false }, notes: "", description: "", group: "", tags: [] };
        q.assets.push(fa);
        assignCodes(q.assets);
        state = "new";
      }
      v.frame = at;
      v.frame_asset = fa.id;
      code = fa.code;
    }, { label: `${c.name}: frame of ${a.code} as a picture` });
    if (state === "gone") ctx.actions.toast(`“${c.name}” or this video anchor was removed meanwhile; the frame was not kept.`, "warn");
    else if (state === "anchor") ctx.actions.toast(`${code} is now the frame at ${fmtTime(at)}; it stays one of ${c.name}'s anchors.`, "ok");
    else ctx.actions.toast(`${code} is the frame at ${fmtTime(at)}. Add it under Anchors → + Add anchor to use it.`, "ok");
  };
  const clearFrame = va => {
    let r = { asset: "", kept: false };
    edit((x, q) => { const v = (x.video_anchors || []).find(y => y.id === va.id); if (v) r = clearAnchorFrame(q, x, v); }, "Clear the frame picture");
    if (r.asset) ctx.actions.toast(r.kept ? `Frame cleared. ${r.asset} is used elsewhere too, so it stays in the assets.` : `Frame cleared: ${r.asset} is gone from the anchors and the assets.`, "ok");
  };
  const frameRow = (va, a) => {
    const fa = va.frame_asset && findAsset(p, va.frame_asset);
    if (!fa) return h("div", { class: "rw-dim small", help: "cast.videoAnchors.frame" }, "Optional: Preview → Use this frame as a picture makes a still of this clip, offered under Anchors.");
    const url = viewURL(fa.file, "input"), isAnchor = c.anchors.includes(fa.id);
    return h("div", { class: "rw-vanchor-frame", help: "cast.videoAnchors.frame" },
      kept(ctx, "vaframe-" + va.id, url, () => h("img", { src: url, alt: "" })),
      h("span", { class: "grow small" }, h("b", { class: "mono rw-c-pic" }, fa.code), ` frame at ${va.frame !== null && va.frame !== undefined ? fmtTime(va.frame) : "?"} · `,
        h("span", { class: isAnchor ? "rw-c-ok" : "rw-dim" }, isAnchor ? "one of the anchors" : "not an anchor yet")),
      !isAnchor && button({ label: "Add to Anchors", small: true, variant: "ghost", key: `va-frame-add-${va.id}`, help: "cast.videoAnchors.frame",
        onClick: () => edit(x => { if (!x.anchors.includes(fa.id)) x.anchors.push(fa.id); }, `${c.name}: add ${fa.code} to the anchors`) }),
      button({ label: "Clear frame", small: true, variant: "danger-ghost", key: `va-frame-clear-${va.id}`, help: "cast.videoAnchors.frameClear", onClick: () => clearFrame(va) }));
  };
  const videos = p.assets.filter(a => a.kind === "video").map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file}`, pre: assetGroupName(p, a) }));
  const list = c.video_anchors || [];
  const rows = list.map(va => {
    const a = findAsset(p, va.asset);
    if (!a || a.kind !== "video") {
      return h("div", { class: "rw-note warn rw-vanchor" }, dragGrip({ help: "cast.videoAnchors.order", key: `va-grip-${va.id}` }),
        h("span", { class: "grow" }, a ? `${a.code} is not a video, so it is not sent.` : "This video anchor's asset was deleted."),
        button({ icon: "trash", small: true, variant: "ghost", help: "cast.videoAnchors.remove", key: `va-del-${va.id}`, onClick: () => remove(va.id) }));
    }
    const dur = Number(a.duration) || 0;
    return h("div", { class: "rw-vanchor" },
      dragGrip({ help: "cast.videoAnchors.order", key: `va-grip-${va.id}` }),
      h("span", { class: "rw-vanchor-thumb rw-bg-vid-soft" }, icon("video", 16)),
      h("div", { class: "rw-vanchor-body" },
        h("div", { class: "rw-row" }, h("b", { class: "mono rw-c-vid" }, a.code), h("b", { class: "rw-ellipsis grow" }, a.name || a.file.split("/").pop()),
          h("span", { class: "rw-dim small mono" }, dur ? fmtTime(dur) : ""),
          button({ icon: "trash", small: true, variant: "ghost", help: "cast.videoAnchors.remove", key: `va-del-${va.id}`, onClick: () => remove(va.id) })),
        h("div", { class: "rw-row wrap" },
          toggle({ value: !!va.soundtrack, label: "with sound", help: "cast.videoAnchors.sound", key: `va-snd-${va.id}`, onChange: v => one(va.id, x => { x.soundtrack = v; }) })),
        clipEditor(ctx, null, va, a, one, { help: VA_HELP, key: "va", token: false, tok: a.code, short: "is under 2 s, so it is not sent (H3 takes 2–15 s)",
          frame: t => setFrame(va, a, t), frameAt: va.frame_asset && findAsset(p, va.frame_asset) ? va.frame : null }),
        frameRow(va, a)));
  });
  return section({
    title: "Video anchors", help: "cast.videoAnchors",
    actions: videos.length > 0 && select({ options: videos, value: "", placeholder: "+ Add a video anchor…", help: "cast.videoAnchors.add", key: `va-add-${c.id}`,
      onChange: v => edit(x => { (x.video_anchors = x.video_anchors || []).push({ id: newId("va"), asset: v, in: 0, out: null, soundtrack: false }); }, "Add video anchor") }),
    children: [
      lookNote(c, "video anchors"),
      list.length === 0 && h("div", { class: "rw-empty sm", help: "cast.videoAnchors" }, videos.length
        ? "No video anchors. A short clip of this " + (c.kind === "character" ? "character moving and talking" : c.kind) + " (2–15 s) shows H3 how it moves and looks from every side."
        : "Upload a video in the Assets tab to use a clip as an anchor."),
      list.length > 0 && sortable({ id: `va-${c.id}`, rows, onMove: (from, to) => edit(x => { moveItem(x.video_anchors, from, to); }, "Reorder video anchors") }),
      list.length > 0 && h("div", { class: "rw-dim small", help: "cast.videoAnchors" }, "Sent with the pictures to every scene this cast member is in, after the scene's own videos, while H3 takes 3 videos and 15 s of video in all; a clip is shortened to fit when 2 s or more are left. The issues list says when one is left out."),
    ],
  });
}

// ---- RefMods: saved MiniMax H3 references made with ComfyUI-MiniMaxH3Mod, files in models/refmods (one reference or a
// bundle). The look RefMod goes instead of the anchors (pictures and video anchors; outfit pictures still go) in every
// scene that does not untick it; the voice RefMod goes instead of the voice sample when the character speaks. The
// project keeps what the file held when it was picked (members); Update takes it from the file again.
function membersText(members) {
  const n = k => members.filter(m => m.kind === k).length;
  const pics = n("image"), vids = n("video"), auds = n("audio"), bad = n("");
  return [pics && `${pics} picture${pics === 1 ? "" : "s"}`, vids && `${vids} video${vids === 1 ? "" : "s"}`,
    auds && `${auds} audio`, bad && `${bad} it cannot send`].filter(Boolean).join(", ") || "nothing";
}
const sameMembers = (a, b) => a.length === b.length && a.every((m, i) => ["kind", "t", "h", "w"].every(k => m[k] === b[i][k]));
function lookNote(c, what) {
  if (!refmodParts(c.refmod, true).length) return null;
  return h("div", { class: "rw-note small", help: "cast.refmod" }, icon("info", 12),
    h("span", null, `Not sent while the RefMod ${c.refmod.name} is set: it goes instead of the ${what}, except in scenes that untick it (Scene → Cast in this scene → Anchors).`));
}
function refmodCard(ctx, c) {
  const p = ctx.p;
  if (partOf(p, c)) return null; // a part's pictures go into its character's subject
  const all = ctx.eph.models?.refmods, list = Array.isArray(all) ? all : [];
  const edit = (fn, label) => ctx.actions.edit(q => { const x = findCast(q, c.id); if (x) fn(x); }, { label });
  const take = (which, name) => edit(x => {
    const f = list.find(m => m.name === name);
    x[which] = { name, strength: name ? (x[which]?.strength ?? 1) : 1, members: f ? f.members.map(m => ({ ...m })) : [] };
  }, name ? `${c.name}: RefMod ${name}` : `${c.name}: no ${which === "refmod" ? "" : "voice "}RefMod`);
  const row = (which, visual) => {
    const r = c[which] || { name: "", strength: 1, members: [] };
    const fits = m => m.members.some(x => (visual ? x.kind === "image" || x.kind === "video" : x.kind === "audio"));
    const opts = list.filter(fits).map(m => ({ value: m.name, label: `${m.name} · ${membersText(m.members)}` }));
    const file = r.name && list.find(m => m.name === r.name);
    const parts = refmodParts(r, visual);
    const key = `${which}-${c.id}`;
    let state = null;
    if (r.name && Array.isArray(all) && !file) {
      state = h("div", { class: "rw-note warn small", help: "cast.refmod.missing" }, icon("warn", 12),
        h("span", null, `${r.name} is not in models/refmods (anymore): scenes that send it cannot render. Put the file back, or pick another.`));
    } else if (file && !sameMembers(file.members, r.members)) {
      state = h("div", { class: "rw-note warn small", help: "cast.refmod.update" }, icon("warn", 12),
        h("span", { class: "grow" }, `The file has changed since it was picked (it holds ${membersText(file.members)} now): scenes that send it cannot render until you update.`),
        button({ label: "Update", small: true, key: `${key}-update`, help: "cast.refmod.update", onClick: () => take(which, r.name) }));
    } else if (r.name && !parts.length) {
      state = h("div", { class: "small rw-c-warn", help: "cast.refmod" }, r.strength > 0
        ? `It holds no ${visual ? "picture or video" : "audio"}, so nothing of it is sent.` : "Strength 0: not sent.");
    } else if (parts.length) {
      const tokens = parts.reduce((n, [, m]) => n + refmodTokens(m), 0);
      const what = parts.map(([, m]) => (m.kind === "image" ? `a ${m.w * 16}×${m.h * 16} picture`
        : m.kind === "video" ? `a ${refmodFrames(m.t)}-frame video` : `${refmodSeconds(m).toFixed(1)} s of audio`)).join(", ");
      state = h("div", { class: "rw-dim small", help: visual ? "cast.refmod" : "cast.voiceRefmod" }, visual
        ? `Sends ${what} (${tokens.toLocaleString("en-US")} reference tokens) instead of the anchors.`
        : `Sends ${what} instead of the Voice sample, in the passes where ${c.name} speaks.`);
    }
    return [
      field(visual ? "Look" : "Voice", h("span", { class: "rw-row" },
        select({ options: opts, value: r.name, placeholder: "none", mono: true, width: "340px", key: `${key}-name`, help: visual ? "cast.refmod" : "cast.voiceRefmod",
          onChange: v => take(which, v) }),
        r.name && number({ value: r.strength, min: 0, max: 1, step: 0.05, width: "70px", key: `${key}-strength`, help: "cast.refmod.strength",
          onChange: v => edit(x => { x[which].strength = Math.min(1, Math.max(0, v ?? 1)); }, `${c.name}: RefMod strength`) })),
      { help: visual ? "cast.refmod" : "cast.voiceRefmod" }),
      state,
    ];
  };
  return section({
    title: "RefMod", help: "cast.refmod",
    actions: button({ label: "Refresh", icon: "refresh", small: true, variant: "ghost", key: `refmod-refresh-${c.id}`, help: "cast.refmod.refresh",
      onClick: async () => { await ctx.actions.refreshModels(); ctx.actions.toast(`${(ctx.store.eph.models?.refmods || []).length} RefMods in models/refmods.`, "ok"); } }),
    children: [
      ...row("refmod", true),
      ...(c.kind === "character" ? row("voice_refmod", false) : []),
      all === null ? h("div", { class: "rw-dim small", help: "cast.refmod" }, "The backend is offline, so the list of RefMods is not loaded.")
        : Array.isArray(all) && !list.length && h("div", { class: "rw-empty sm", help: "cast.refmod" },
          "No RefMods in models/refmods yet. Make one from pictures with ComfyUI-MiniMaxH3Mod (Create H3 RefMod, or Create H3 RefMod Master for a voice too), then press Refresh."),
    ],
  });
}

function profileCard(ctx, c) {
  const p = ctx.p;
  const edit = fn => ctx.actions.edit(q => { const x = findCast(q, c.id); if (x) fn(x, q); }, { label: `Edit ${c.name}` });
  const audio = p.assets.filter(a => a.kind === "audio").map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file}`, pre: assetGroupName(p, a) }));
  const loras = ctx.eph.models?.loras || [];
  return section({
    title: c.kind === "character" ? "Character" : c.kind === "location" ? "Location" : "Prop", help: "cast.profile",
    actions: button({ icon: "trash", small: true, variant: "danger-ghost", label: "Delete", help: "cast.delete", onClick: async () => {
      const scenes = p.scenes.filter(s => s.cast.some(x => x.id === c.id)).length;
      const lines = p.scenes.reduce((n, s) => n + s.dialogue.filter(d => d.speaker === c.id).length, 0);
      const what = [scenes && `${scenes} scene${scenes === 1 ? "" : "s"}`, lines && `${lines} dialogue line${lines === 1 ? "" : "s"} lose${lines === 1 ? "s" : ""} their speaker`].filter(Boolean);
      if (!(await confirmDialog(ctx.root, { title: `Delete “${c.name}”?`, confirmLabel: "Delete",
        message: `${scenes ? `It is removed from ${what[0]}` : "It is in no scene"}${lines ? `, and ${what[what.length - 1]}` : ""}. Its anchor pictures stay in Assets. Ctrl+Z undoes this.` }))) return;
      ctx.actions.edit(q => { q.cast = q.cast.filter(x => x.id !== c.id); for (const s of q.scenes) { s.cast = s.cast.filter(x => x.id !== c.id); for (const d of s.dialogue) if (d.speaker === c.id) d.speaker = ""; } }, { label: `Delete ${c.name}` });
      ctx.store.setEph({ selectedCast: "" });
    } }),
    children: [
      field("Name", text({ value: c.name, key: "cast-name-" + c.id, help: "cast.name", onChange: v => edit(x => { x.name = v; }) }), { help: "cast.name" }),
      field("Kind", segmented({ small: true, value: c.kind, help: "cast.kind", options: KINDS.map(([k]) => k), onChange: v => edit(x => { x.kind = v; }) }), { help: "cast.kind" }),
      partOfField(ctx, c, edit),
      (() => {
        const d = castDescription(p, c);
        return h("div", { class: "rw-field wide" }, h("span", { class: "rw-field-label", help: "cast.description" }, "Description"),
          h("div", { class: "grow", style: { display: "flex", "flex-direction": "column", gap: "4px", "min-width": "0" } },
            textarea({ value: c.description, rows: 3, key: "cast-desc-" + c.id, help: "cast.description",
              placeholder: d.asset ? `Empty: uses ${d.asset.code}'s description, "${d.text}"` : "Woman, early 30s, short auburn hair, navy pea coat with brass buttons.",
              onChange: v => edit(x => { x.description = v; }) }),
            d.asset ? h("div", { class: "rw-dim small", help: "cast.description.fromAnchor" }, `Using ${d.asset.code}'s description (its first described anchor). Type here to override it.`) : null));
      })(),
      (c.anchors.length > 0 || anchorClips(p, c).length > 0) && h("div", { class: "rw-field wide" }, h("span", { class: "rw-field-label", help: "cast.describe" }, "From anchors"),
        describeBox(ctx, {
          key: "cast-" + c.id, ids: c.anchors.slice(0, 4), clips: anchorClips(p, c), help: "cast.describe",
          defaultPrompt: c.kind === "character" ? `Describe ${c.name || "this person"}: build, face, hair, clothing and accessories.`
            : c.kind === "location" ? "Describe this place: setting, architecture, materials, lighting and time of day."
              : "Describe the main object: what it is, shape, material, colour and condition.",
          apply: (t, mode) => edit(x => { x.description = mode === "append" && x.description ? x.description.replace(/[.\s]*$/, "") + "; " + t : t; }),
        })),
      c.kind === "character" && field("Voice", h("span", { class: "rw-row" },
        select({ options: audio, value: c.voice, placeholder: "no voice reference", help: "cast.voice", key: "cast-voice-" + c.id, onChange: v => edit(x => { x.voice = v; }) }),
        button({ label: ctx.eph.voiceCut === c.id ? "Cutting…" : "From a take…", icon: "audio", small: true, help: "cast.voiceFromTake", key: "cast-voice-take-" + c.id,
          disabled: ctx.eph.voiceCut === c.id, onClick: () => voiceFromTake(ctx, c) })), { help: "cast.voice" }),
      c.kind === "character" && c.voice && refmodParts(c.voice_refmod, false).length > 0 && h("div", { class: "rw-dim small", help: "cast.voiceRefmod" },
        `Not sent while the voice RefMod ${c.voice_refmod.name} is set (RefMod → Voice).`),
      c.kind === "character" && h("div", { class: "rw-field wide" }, h("span", { class: "rw-field-label", help: "cast.voiceDesc" }, "Voice description"),
        h("div", { class: "grow", style: { display: "flex", "flex-direction": "column", gap: "4px", "min-width": "0" } },
          textarea({ value: c.voice_desc || "", rows: 2, key: "cast-voice-desc-" + c.id, help: "cast.voiceDesc", placeholder: "a deep, warm male voice, slow and measured",
            onChange: v => edit(x => { x.voice_desc = v.trim(); }) }),
          p.global.continuity.describe_voices === false && (c.voice_desc || "").trim()
            ? h("div", { class: "rw-dim small", help: "cast.rules.describeVoices" }, "Not written into the prompts: Describe voices is off in the continuity rules below.") : null)),
      c.kind === "character" && field("Language", select({ options: STABLE_LANGUAGES, value: c.language, free: true, help: "cast.language", onChange: v => edit(x => { x.language = v; }) }), { help: "cast.language" }),
      field("Identity LoRA", h("span", { class: "rw-row" },
        select({ options: loras, value: c.lora.name, placeholder: "none", mono: true, help: "cast.lora", onChange: v => edit(x => { x.lora.name = v; }) }),
        number({ value: c.lora.strength, min: -4, max: 4, step: 0.05, width: "74px", help: "cast.lora.strength", onChange: v => edit(x => { x.lora.strength = v ?? 0.8; }) })), { help: "cast.lora" }),
      c.lora.name && field("Trigger word", triggerInput({ value: c.lora.trigger, key: "cast-lora-trigger-" + c.id, help: "cast.lora.trigger",
        onChange: v => edit(x => { x.lora.trigger = triggerText(v); }) }), { help: "cast.lora.trigger" }),
      h("div", { class: "rw-row" },
        button({ label: "Export training set", icon: "download", small: true, help: "cast.export", onClick: async () => {
          try { const r = await rw.castExport(p, c.id); ctx.actions.toast(`Exported ${r.files?.length ?? 0} files to ${r.folder}.`, "ok"); }
          catch (err) { ctx.actions.toast("Export failed: " + err.message, "error"); }
        } })),
    ],
  });
}

// A prop can be part of a character (a beer belly, a tattoo, a prosthetic arm). H3 puts every
// subject in the shot as a separate thing, so a prop of its own showing a body part became a second person.
// A part's pictures and description go into its character's subject in the scenes where both are in the cast.
function partOf(p, c) {
  const id = partOwner(c, new Map(p.cast.map(x => [x.id, x])));
  return id ? findCast(p, id) : null;
}
function partOfField(ctx, c, edit) {
  const p = ctx.p;
  if (c.kind === "prop") {
    const chars = p.cast.filter(x => x.kind === "character" && x.id !== c.id).map(x => ({ value: x.id, label: x.name || "Unnamed" }));
    const owner = partOf(p, c);
    const alone = owner ? p.scenes.filter(s => s.cast.some(e => e.id === c.id) && !s.cast.some(e => e.id === owner.id) && !s.dialogue.some(d => d.speaker === owner.id)).length : 0;
    return h("div", { class: "rw-field wide" }, h("span", { class: "rw-field-label", help: "cast.partOf" }, "Part of"),
      h("div", { class: "grow rw-col-tight" },
        select({ options: chars, value: owner ? c.part_of : "", placeholder: "nobody: a thing of its own", key: "cast-part-" + c.id, help: "cast.partOf",
          onChange: v => edit(x => { x.part_of = v; }) }),
        h("div", { class: "small rw-dim", help: "cast.partOf" }, owner
          ? `Its pictures and description go into ${owner.name}'s subject, in the scenes where both are in the cast. Write @${c.name.includes(" ") ? "{" + c.name + "}" : c.name} for “${owner.name}'s ${c.name}”.`
          : chars.length ? "A thing of its own in the shot (a cup, a car). For something that belongs to a character's body or look (a belly, a tattoo, a scar), pick the character."
            : "A thing of its own in the shot. Add a character to make this prop part of them."),
        alone ? h("div", { class: "small rw-c-warn", help: "cast.partOf" }, `${alone} scene${alone === 1 ? " has" : "s have"} it without ${owner.name}: it is left out there.`) : null));
  }
  if (c.kind !== "character") return null;
  const parts = p.cast.filter(x => partOf(p, x)?.id === c.id);
  return parts.length ? field("Parts", h("span", { class: "rw-row wrap" }, parts.map(x => button({ label: x.name || "Unnamed", icon: "cast", small: true, variant: "ghost",
    help: "cast.parts", key: "cast-partlink-" + x.id, onClick: () => ctx.store.setEph({ selectedCast: x.id }) }))), { help: "cast.parts" }) : null;
}

// Pictures of an outfit (or a prop's variant): sent with the anchors in the scenes that pick
// it, as the same subject (a look: other clothes, a beard, a belly). Before, only a project file could hold them.
function outfitPictures(ctx, c, o, editO) {
  const p = ctx.p;
  const pics = o.assets.map(id => findAsset(p, id)).filter(a => a?.kind === "image");
  const images = p.assets.filter(a => a.kind === "image" && !o.assets.includes(a.id) && !c.anchors.includes(a.id))
    .map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file}`, pre: assetGroupName(p, a) }));
  return h("div", { class: "rw-outfit-pics", help: "cast.outfits.pictures" },
    pics.map(a => h("div", { class: "rw-anchor sm" },
      h("img", { src: viewURL(a.file, "input"), alt: a.name }),
      h("span", { class: "rw-anchor-label" }, h("b", { class: "mono rw-c-pic" }, a.code)),
      h("button", { type: "button", class: "rw-anchor-x", "aria-label": "Remove picture", help: "cast.outfits.pictureRemove", key: "outfit-pic-x-" + o.id + "-" + a.id,
        onClick: () => editO(o.id, y => { y.assets = y.assets.filter(z => z !== a.id); }) }, icon("close", 11)))),
    h("div", { class: "rw-col-tight grow" },
      images.length ? select({ options: images, value: "", placeholder: "+ Add picture…", key: "outfit-pic-add-" + o.id, help: "cast.outfits.pictureAdd",
        onChange: v => { if (v) editO(o.id, y => { if (!y.assets.includes(v)) y.assets.push(v); }); } }) : null,
      h("div", { class: "rw-dim small" }, pics.length ? `Sent with the anchors in scenes that pick “${o.name || "this"}”.` : "No pictures of its own: the anchors show this look.")));
}

// The video anchors Describe looks at (the first 2, each its From–To part)
function anchorClips(p, c) {
  return (c.video_anchors || []).filter(va => findAsset(p, va.asset)?.kind === "video").slice(0, 2)
    .map(va => ({ asset: va.asset, in: Number(va.in) || 0, out: va.out ?? null }));
}

// Delete an outfit; scenes that wore it fall back to the default outfit (their entry's outfit
// becomes "", which follows the default), so no scene keeps pointing at an outfit that is gone
export function removeOutfit(ctx, c, o) {
  const users = ctx.p.scenes.filter(s => s.cast.some(x => x.id === c.id && x.outfit === o.id)).length;
  ctx.actions.edit(q => {
    const x = findCast(q, c.id);
    if (!x) return;
    x.outfits = x.outfits.filter(y => y.id !== o.id);
    if (x.default_outfit === o.id) x.default_outfit = x.outfits[0]?.id || "";
    for (const s of q.scenes) for (const e of s.cast) if (e.id === c.id && e.outfit === o.id) e.outfit = "";
  }, { label: `Delete outfit “${o.name}”` });
  if (users) ctx.actions.toast(`${users} scene${users === 1 ? "" : "s"} wore “${o.name}”; ${users === 1 ? "it now uses" : "they now use"} the default outfit. Ctrl+Z undoes this.`, "info");
}

function outfitsCard(ctx, c) {
  const edit = fn => ctx.actions.edit(q => { const x = findCast(q, c.id); if (x) fn(x); }, { label: `Outfits of ${c.name}` });
  const editO = (id, fn) => edit(x => { const o = x.outfits.find(y => y.id === id); if (o) fn(o); });
  return section({
    title: c.kind === "character" ? "Outfits" : "Variants", help: "cast.outfits",
    actions: button({ label: "Add", icon: "plus", small: true, help: "cast.outfits.add", onClick: () => edit(x => {
      // a character's later outfits change its look: keep the face and hair, not the anchors' clothes
      const changes = x.outfits.length > 0 && x.kind === "character";
      const o = { id: newId("o"), name: x.outfits.length ? "Outfit " + (x.outfits.length + 1) : "Default",
        retention: changes ? "partially_preserved" : "fully_preserved", keep: changes ? ["face", "hair"] : [], assets: [] };
      x.outfits.push(o);
      if (!x.default_outfit) x.default_outfit = o.id;
    }) }),
    children: c.outfits.length ? c.outfits.map(o => h("div", { class: "rw-outfit" },
      h("div", { class: "rw-row" },
        h("button", { type: "button", class: ["rw-radio-btn", c.default_outfit === o.id && "on"], help: "cast.outfits.default", "aria-label": "Default outfit", onClick: () => edit(x => { x.default_outfit = o.id; }) }),
        text({ value: o.name, key: "outfit-" + o.id, help: "cast.outfits.name", onChange: v => editO(o.id, y => { y.name = v; }) }),
        select({ options: VISUAL_RETENTION, value: o.retention, key: "outfit-ret-" + o.id, mono: true, help: "cast.outfits.retention", onChange: v => editO(o.id, y => { y.retention = v; }) }),
        button({ icon: "trash", small: true, variant: "ghost", help: "cast.outfits.remove", onClick: () => removeOutfit(ctx, c, o) })),
      keepChips({ values: o.keep, help: "cast.outfits.keep", key: "outfit-keep-" + o.id, onChange: v => editO(o.id, y => { y.keep = v; }) }),
      outfitPictures(ctx, c, o, editO)))
      : h("div", { class: "rw-empty sm", help: "cast.outfits" }, c.kind === "character" ? "One look everywhere. Add an outfit when the character's look changes: other clothes, a beard, a belly." : "One look everywhere. Add a variant when it changes."),
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
  const set = fn => ctx.actions.edit(q => fn(q.global.continuity), { label: "Continuity setting" });
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
      field("Continuation", toggle({ value: g.name_continuation !== false, label: "Name it in the prompt", key: "rules-name-cont", help: "cast.rules.nameContinuation",
        onChange: v => ctx.actions.edit(q => { q.global.continuity.name_continuation = v; }, { label: v ? "Name the continuation" : "Don't name the continuation" }) }),
      { help: "cast.rules.nameContinuation" }),
      field("Voices", toggle({ value: g.describe_voices !== false, label: "Describe them in every pass", key: "rules-describe-voices", help: "cast.rules.describeVoices",
        onChange: v => ctx.actions.edit(q => { q.global.continuity.describe_voices = v; }, { label: v ? "Describe voices" : "Don't describe voices" }) }),
      { help: "cast.rules.describeVoices" }),
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
        h("span", { class: "rw-flex" })),
      anchorsCard(ctx, c), videoAnchorsCard(ctx, c), refmodCard(ctx, c), profileCard(ctx, c), outfitsCard(ctx, c), appearances(ctx, c))
      : h("div", { class: "rw-col wide" }, section({ title: "Story bible", help: "cast.bible", children: [
        h("div", { class: "rw-empty" }, "Add a character, location or prop. Its anchors are sent to every scene it appears in, which keeps it looking the same."),
        h("div", { class: "rw-row" }, KINDS.map(([k, label]) => button({ label: "New " + label.slice(0, -1).toLowerCase(), icon: "plus", help: "cast.add." + k, onClick: () => addEntry(ctx, k) }))),
      ] })),
    h("div", { class: "rw-col mid" }, rulesCard(ctx)));
}
