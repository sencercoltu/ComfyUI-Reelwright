// Help catalog. `tip` is the hover tooltip; `title` + `more` fill the "?"
// popover (paragraphs separated by blank lines). Every data-help id in the UI
// must exist here; the harness test checks that.

const H = {};
const tip = (id, text) => { H[id] = { ...(H[id] || {}), tip: text }; };
const more = (id, title, text, tipText) => { H[id] = { tip: tipText || (H[id]?.tip ?? title), title, more: text }; };

// ---------- Tabs ----------
// [OLD 2026-11-03 v0.4.3->v0.5.0] more("tab.timeline", "Timeline", "The whole film at a glance. The Scenes lane shows every scene as a block: drag its right edge to change its length, drag the small white triangles inside it to move shot cuts, and click the round chip between two scenes to change how the second one starts (fresh, from the last frame, or from a tail clip).\n\nThe lanes below show what each scene sends to H3: pictures and keyframes (diamonds), video and audio references, dialogue, camera wording and LoRAs. The asset bin on the left lets you drag assets straight onto a scene.\n\nShortcuts: Space play/pause, J back 1 s, K stop, L play, ←/→ one frame (Shift: 1 s), I/O set a loop, M add a marker, S split at the playhead, D duplicate, N new scene, Delete remove, +/− zoom, Ctrl+Z / Ctrl+Shift+Z undo/redo, ? this help.", "Overview of every scene and lane. Press ? for shortcuts.");
// added 2026-11-03 v0.5.0: soundtrack lanes
// [OLD 2026-11-03 v0.5.1->v0.6.0] more("tab.timeline", "Timeline", "The whole film at a glance. The Scenes lane shows every scene as a block: drag its right edge to change its length, drag the small white triangles inside it to move shot cuts, and click the round chip between two scenes to change how the second one starts (fresh, from the last frame, or from a tail clip).\n\nThe lanes below show what each scene sends to H3: pictures and keyframes (diamonds), video and audio references, dialogue, camera wording and LoRAs. The asset bin on the left lets you drag assets straight onto a scene.\n\nSoundtrack lanes (under the scenes) hold audio files laid on the film, such as the song a music video is cut to: drop an audio asset on the Soundtrack lane, drag it into place and trim it there.\n\nShortcuts: Space play/pause, J back 1 s, K stop, L play, ←/→ one frame (Shift: 1 s), I/O set a loop, M add a marker, S split at the playhead, D duplicate, N new scene, Delete remove, +/− zoom, Ctrl+Z / Ctrl+Shift+Z undo/redo, ? this help.", "Overview of every scene and lane. Press ? for shortcuts.");
// added 2026-11-03 v0.6.0: beats, auto-roll, Delete on the selection
// [OLD 2026-11-05 v0.6.1->v0.7.0] more("tab.timeline", "Timeline", "The whole film at a glance. The Scenes lane shows every scene as a block: drag its right edge to change its length, drag the small white triangles inside it to move shot cuts, and click the round chip between two scenes to change how the second one starts (fresh, from the last frame, or from a tail clip).\n\nThe lanes below show what each scene sends to H3: pictures and keyframes (diamonds), video and audio references, dialogue, camera wording and LoRAs. The asset bin on the left lets you drag assets straight onto a scene.\n\nSoundtrack lanes (under the scenes) hold audio files laid on the film, such as the song a music video is cut to: drop an audio asset on the Soundtrack lane, drag it into place and trim it there. Beats shows the song's beats on its lane (yellow lines start a bar); Snap to beats makes scene edges, shot cuts and track moves stick to them. While a soundtrack sets the timing, Auto-roll keeps every later scene on the song when you change a scene's length.\n\nShortcuts: Space play/pause, J back 1 s, K stop, L play, ←/→ one frame (Shift: 1 s), I/O set a loop, M add a marker, S split at the playhead, D duplicate, N new scene, Delete removes what is selected (a marker, a track, else the scene), +/− zoom, Ctrl+Z / Ctrl+Shift+Z undo/redo, ? this help.", "Overview of every scene and lane. Press ? for shortcuts.");
// added 2026-11-05 v0.7.0: the strip shows the take's real frames; transition and fade marks
// [OLD 2026-11-06 v0.8.0->v0.9.0] more("tab.timeline", "Timeline", "The whole film at a glance. The Scenes lane shows every scene as a block: drag its right edge to change its length, drag the small white triangles inside it to move shot cuts, and click the round chip between two scenes to change how the second one starts (fresh, from the last frame, or from a tail clip). A rendered scene shows the frames of its starred take at their times; small marks show a transition into a scene and fades at its edges (set on the Scene tab, In the cut).\n\nThe lanes below show what each scene sends to H3: pictures and keyframes (diamonds), video and audio references, dialogue, camera wording and LoRAs. The asset bin on the left lets you drag assets straight onto a scene.\n\nSoundtrack lanes (under the scenes) hold audio files laid on the film, such as the song a music video is cut to: drop an audio asset on the Soundtrack lane, drag it into place and trim it there. Beats shows the song's beats on its lane (yellow lines start a bar); Snap to beats makes scene edges, shot cuts and track moves stick to them. While a soundtrack sets the timing, Auto-roll keeps every later scene on the song when you change a scene's length.\n\nShortcuts: Space play/pause, J back 1 s, K stop, L play, ←/→ one frame (Shift: 1 s), I/O set a loop, M add a marker, S split at the playhead, D duplicate, N new scene, Delete removes what is selected (a marker, a track, else the scene), +/− zoom, Ctrl+Z / Ctrl+Shift+Z undo/redo, ? this help.", "Overview of every scene and lane. Press ? for shortcuts.");
// [OLD 2026-11-06 v0.9.0->v0.10.0] captions timed to the speech, full lines on hover
// more("tab.timeline", "Timeline", "The whole film at a glance, in three panels: the monitor with its transport (top left), the selected scene's inspector and summary (top right) and the timeline (below). Drag the bars between them to resize the panels; double-click a bar to reset it.\n\nThe Scenes lane shows every scene as a block: drag its right edge to change its length, drag the small white triangles inside it to move shot cuts, and click the round chip between two scenes to change how the second one starts (fresh, from the last frame, or from a tail clip). A rendered scene shows the frames of its starred take at their times; small marks show a transition into a scene and fades at its edges (set on the Scene tab, In the cut).\n\nThe lanes below show what each scene sends to H3: pictures and keyframes (diamonds), video and audio references, dialogue, camera wording and LoRAs. Add references in the Scene tab; upload and sort assets in the Assets tab.\n\nSoundtrack lanes (under the scenes) hold audio files laid on the film, such as the song a music video is cut to: press + on the Soundtrack lane to add an audio asset, drag it into place and trim it there. Beats shows the song's beats on its lane (yellow lines start a bar); Snap to beats makes scene edges, shot cuts and track moves stick to them. While a soundtrack sets the timing, Auto-roll keeps every later scene on the song when you change a scene's length.\n\nThe monitor shows the spoken lines as captions (CC turns them off) and has its own volume; neither changes the merge.\n\nShortcuts: Space play/pause, J back 1 s, K stop, L play, ←/→ one frame (Shift: 1 s), I/O set a loop, M add a marker, S split at the playhead, D duplicate, N new scene, Delete removes what is selected (a marker, a track, else the scene), +/− zoom, Ctrl+Z / Ctrl+Shift+Z undo/redo, ? this help.", "Overview of every scene and lane. Press ? for shortcuts.");  // added 2026-11-06 v0.9.0: panels, no asset bin, captions and volume
// [/OLD]
// [OLD 2026-11-12 v0.13.0->v0.13.1] more("tab.timeline", "Timeline", "The whole film at a glance, in three panels: the monitor with its transport (top left), the selected scene's inspector and summary (top right) and the timeline (below). Drag the bars between them to resize the panels; double-click a bar to reset it.\n\nThe Scenes lane shows every scene as a block: drag its right edge to change its length, drag the small white triangles inside it to move shot cuts, and click the round chip between two scenes to change how the second one starts (fresh, from the last frame, or from a tail clip). A rendered scene shows the frames of its starred take at their times; small marks show a transition into a scene and fades at its edges (set on the Scene tab, In the cut).\n\nThe lanes below show what each scene sends to H3: pictures and keyframes (diamonds), video and audio references, dialogue, camera wording and LoRAs. Add references in the Scene tab; upload and sort assets in the Assets tab.\n\nSoundtrack lanes (under the scenes) hold audio files laid on the film, such as the song a music video is cut to: press + on the Soundtrack lane to add an audio asset, drag it into place and trim it there. Beats shows the song's beats on its lane (yellow lines start a bar); Snap to beats makes scene edges, shot cuts and track moves stick to them. While a soundtrack sets the timing, Auto-roll keeps every later scene on the song when you change a scene's length.\n\nThe monitor shows the spoken lines as captions (CC turns them off) and has its own volume; neither changes the merge. Captions follow the speech heard in a rendered take, like the merge's subtitles (Render → Merge → Subtitle times). Hover a dialogue or camera bar to read it in full; right-click it to copy it.\n\nShortcuts: Space play/pause, J back 1 s, K stop, L play, ←/→ one frame (Shift: 1 s), I/O set a loop, M add a marker, S split at the playhead, D duplicate, N new scene, Delete removes what is selected (a marker, a track, else the scene), +/− zoom, Ctrl+Z / Ctrl+Shift+Z undo/redo, ? this help.", "Overview of every scene and lane. Press ? for shortcuts.");  // added 2026-11-06 v0.9.0: panels, no asset bin, captions and volume; v0.10.0: captions timed to the speech, full text on hover
more("tab.timeline", "Timeline", "The whole film at a glance, in three panels: the monitor with its transport (top left), the selected scene's inspector and summary (top right) and the timeline (below). Drag the bars between them to resize the panels; double-click a bar to reset it.\n\nThe Scenes lane shows every scene as a block: drag it left or right to move it to another place in the order, drag its right edge to change its length, drag the small white triangles inside it to move shot cuts, and click the round chip between two scenes to change how the second one starts (fresh, from the last frame, or from a tail clip). A rendered scene shows the frames of its starred take at their times; small marks show a transition into a scene and fades at its edges (set on the Scene tab, In the cut).\n\nThe lanes below show what each scene sends to H3: pictures and keyframes (diamonds), video and audio references, dialogue, camera wording and LoRAs. Add references in the Scene tab; upload and sort assets in the Assets tab.\n\nSoundtrack lanes (under the scenes) hold audio files laid on the film, such as the song a music video is cut to: press + on the Soundtrack lane to add an audio asset, drag it into place and trim it there. Beats shows the song's beats on its lane (yellow lines start a bar); Snap to beats makes scene edges, shot cuts and track moves stick to them. While a soundtrack sets the timing, Auto-roll keeps every later scene on the song when you change a scene's length.\n\nThe monitor shows the spoken lines as captions (CC turns them off) and has its own volume; neither changes the merge. Captions follow the speech heard in a rendered take, like the merge's subtitles (Render → Merge → Subtitle times). Hover a dialogue or camera bar to read it in full; right-click it to copy it.\n\nShortcuts: Space play/pause, J back 1 s, K stop, L play, ←/→ one frame (Shift: 1 s), I/O set a loop, M add a marker, S split at the playhead, D duplicate, N new scene, Delete removes what is selected (a marker, a track, else the scene), +/− zoom, Ctrl+Z / Ctrl+Shift+Z undo/redo, ? this help.", "Overview of every scene and lane. Press ? for shortcuts.");  // added 2026-11-06 v0.9.0: panels, no asset bin, captions and volume; v0.10.0: captions timed to the speech, full text on hover // added 2026-11-12 v0.13.1: drag a scene to reorder
more("tab.scene", "Scene", "Everything that defines one scene: its length, how it starts, references, cast, shots, dialogue, prompt, LoRAs and any Global settings it overrides.\n\nA hollow dot means the setting follows the Global tab; a coral dot means this scene overrides it. Use the arrows or the strip at the top to move between scenes.", "Edit the selected scene.");
more("tab.assets", "Assets", "Pictures, videos and audio clips the project can use as references. Each asset gets a short code (P1, V1, A1) that you can type in prompts as @P1. Defaults set here (role, retention, features to keep) apply wherever the asset is used, unless a scene overrides them.\n\nH3 accepts per generation pass up to 9 pictures, 3 videos and 3 audio clips (2–15 s each, 15 s in total per type) and 12 files overall. The budget table shows where a scene goes over.", "Upload and manage reference images, videos and audio.");
more("tab.cast", "Cast", "The story bible: characters, locations and props that appear across scenes. A character's anchor pictures, description, voice and identity LoRA are sent to every scene it is tagged in.\n\nThis is how a subject from scene 1 still looks the same in scene 10: identity always comes from the same anchors, never from a chain of rendered frames, so nothing in between can make it drift.", "Characters, locations and props shared across scenes.");
more("tab.render", "Render", "Renders only what changed. Every scene has a cache key built from everything that affects its pixels; scenes whose key matches a take on disk are reused, even after a restart.\n\nEach scene is written to its own MP4 as soon as it finishes and its frames are dropped from memory. Merge scenes joins the starred takes into one film without re-rendering anything.", "Render, takes, memory and merging.");
more("tab.global", "Global", "Settings every scene inherits: models, LoRAs, output size, sampling, draft quality, defaults for new scenes, long-scene splitting and the LLM used by the prompt rewriter. Any scene can override most of them on the Scene tab.", "Project-wide settings that scenes inherit.");

// ---------- App frame ----------
tip("app.brand", "Reelwright: a timeline editor for MiniMax H3 ref2va inside one ComfyUI node.");
tip("app.backend", "Whether the Reelwright server routes answer. Without them you can still edit, but statuses, prompt previews, uploads and merging are unavailable.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("app.undo", "Undo the last edit (Ctrl+Z). Selection and zoom changes are not part of the history.");
tip("app.undo", "Undo the last edit (Ctrl+Z). Undo never changes the view: the tab, zoom, snap, playhead and selection stay as they are.");
tip("app.redo", "Redo (Ctrl+Shift+Z or Ctrl+Y).");
// added 2026-11-03 v0.6.0: named undo history, folder conflicts
tip("app.history", "History: every edit by name. Click a step to go back (or forward) to it.");
tip("app.history.item", "Go to the project as it was right after this edit. Steps after it stay in the list until you make a new edit.");
tip("app.history.start", "Go back to the project as it was before every edit in the list.");
more("app.conflict", "Folder in use", "Each project saves into its own folder under output/reelwright/. This project's folder already holds a different project, for example because a node was copied in an older version or two projects got the same name.\n\nUse a separate project: this project moves to a new folder (name-2, name-3 …) and keeps every edit; its renders start fresh there.\n\nTake over this folder: this project's file replaces the other one's. Do this only when the other project is an older copy of this one.\n\nDecide later: nothing is written to disk until you choose; the workflow keeps your edits.", "This project's folder holds another project.");
tip("app.conflict.separate", "Save this project in a new folder of its own. Its renders start fresh there.");
tip("app.conflict.takeover", "Write this project into the folder anyway. Only if the other project is an older copy of this one.");
tip("app.conflict.later", "Don't write to disk for now. Click “Folder in use” in the footer to decide.");
more("app.issues", "Issues", "Problems found in the project: references over H3's limits, unknown @tags, dialogue without a language, shots after the end of a scene, missing files, a continuation without a previous scene and more. Errors stop a render; warnings and notes do not.\n\nClick an issue to jump to its scene.", "Problems that may stop or degrade a render. Click to list them.");
tip("app.issueItem", "Open the scene this issue belongs to.");
tip("app.issues.copy", "Copy every issue as text, one per line. Right-click an issue to copy only that one."); // added 2026-11-06 v0.10.0
tip("app.issues.fitShots", "Lengthen every scene whose shots or dialogue start after its end, so they fit (the last shot gets the scene's typical shot length). Ctrl+Z undoes it."); // added 2026-11-03 v0.4.3
// [OLD 2026-11-02 v0.1.0->v0.2.0] merge moved into the Render tab: tip("app.merge", "Join the starred take of every rendered scene into one film, with seams, audio fades and extras from the Render tab. Nothing is re-rendered.");
tip("app.merge", "Join the starred (or latest) take of every rendered scene into one film, using the Merge scenes settings on the right. Nothing is re-rendered.");
tip("app.renderPending", "Queue a render of every scene that is new or stale. Scenes whose cache key matches a take on disk are reused.");
tip("footer.issues", "The first issue in the project, or confirmation that every scene is within H3's limits.");
tip("footer.output", "Output size and quality from the Global tab. H3 always renders 24 fps video with 32 kHz stereo audio.");
tip("footer.status", "How many scenes have a matching take on disk, are stale (changed since their take) or have never been rendered.");
tip("footer.running", "The scene, pass and sampling step being rendered right now.");
tip("footer.merging", "A merge is running: one you started, or the one after a render (Render → Merge → Merge after each render). Render → Stop merging stops it."); // added 2026-11-06 v0.10.2
// [OLD 2026-11-03 v0.4.3->v0.5.0] tip("footer.length", "Number of scenes, total timeline length, and the length of the final cut after continuation overlaps are trimmed.");
tip("footer.length", "Number of scenes, timeline length and the length of the final cut. They match: a scene that continues the one before starts inside it, over the frames it repeats, so the timeline already is the cut.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("footer.save", "Edits are written into the workflow immediately and autosaved to output/reelwright/<project>/ every few seconds.");
tip("footer.save", "Edits are written into the workflow immediately and autosaved to output/reelwright/<project>/ a few seconds later. Ctrl+S saves now and says if it failed.");
tip("footer.saveConflict", "Autosave is paused: this project's folder holds another project. Click to choose a separate folder or to take this one over."); // added 2026-11-03 v0.6.0

// ---------- Common ----------
tip("common.close", "Close.");
// added 2026-11-06 v0.10.0: copying text, folding cards
tip("common.copy", "Copy this text to the clipboard.");
tip("common.copySelection", "Copy the selected text.");
tip("common.copyText", "Copy the text of what you right-clicked (a spoken line or camera phrase in full, an issue, a note, a row).");
// [OLD 2026-11-12 v0.14.0->v0.14.1] tip("common.collapse", "Fold this card to its title. It stays folded in every scene until you open it again.");
// [OLD 2026-11-12 v0.14.0->v0.14.1] tip("common.expand", "Open this card.");
// added 2026-11-12 v0.14.1: every card folds; right-click and Alt+click fold every card of the tab
tip("common.collapse", "Fold this card to its title (or click the title). It stays folded, in every scene too, until you open it again. Alt+click folds every card on this tab; right-click the title for more.");
tip("common.expand", "Open this card. Alt+click opens every card on this tab; right-click the title for more.");
tip("common.collapseBlock", "Fold this part to its line (or click its name). It stays folded until you open it again. Alt+click folds every part; right-click for more.");
tip("common.expandBlock", "Open this part. Alt+click opens every part; right-click for more.");
tip("common.foldAll", "Fold every card on this tab to its title (every part, on the Timeline). Folding is not an edit: it is not undone with Ctrl+Z.");
tip("common.unfoldAll", "Open every card on this tab (every part, on the Timeline).");
tip("common.cancel", "Cancel and keep things as they are.");
tip("common.confirm", "Yes, do it. You can still undo with Ctrl+Z.");
tip("common.remove", "Remove this item.");
tip("common.reset", "Reset to the value inherited from the Global tab.");
tip("common.dot.global", "Hollow dot: this follows the Global tab.");
tip("common.dot.override", "Coral dot: this scene overrides the Global setting.");
tip("common.dot.auto", "Blue dot: added automatically (for example a cast member's identity LoRA).");
tip("common.dot.ok", "On disk and up to date.");
tip("common.dot.warn", "Needs attention: stale or over a limit.");
tip("common.dot.busy", "Rendering now.");
tip("common.dot.empty", "Not rendered yet.");
tip("common.dot.err", "The last render failed.");

for (const [k, t] of Object.entries({
  cached: "On disk: a take matches this scene's current cache key, so it will be reused.",
  locked: "Locked: the starred take is kept even if an earlier scene it continues from changes.",
  stale: "Stale: the scene changed since its take was rendered (or an earlier scene it continues from did). It renders again with Render pending.",
  pending: "Not rendered yet.",
  missing: "Not rendered yet, or its take was deleted.",
  queued: "Waiting in the ComfyUI queue.",
  rendering: "Rendering now; the bar on the timeline block shows the pass and step.",
  error: "The last render of this scene failed. Check the ComfyUI console.",
  unknown: "Render status unknown: the Reelwright backend did not answer.",
})) tip("status." + k, t);

for (const [k, t] of Object.entries({
  fully_preserved: "fully_preserved: keep this subject exactly (face, hair, clothing, shape). Use for the main identity reference.",
  partially_preserved: "partially_preserved: keep the listed features, allow the rest to change (for example same face, different clothes).",
  attribute_transfer: "attribute_transfer: borrow a quality (colour palette, material, lighting, style) without copying the subject.",
  weak_reference: "weak_reference: only the general idea or atmosphere is kept.",
  fully_copy: "fully_copy: the whole audio clip becomes the soundtrack of the target video.",
  partially_copy: "partially_copy: keep selected layers of the audio (for example the music), change the rest.",
  reference: "reference: the audio is not copied; its traits (voice timbre, delivery, rhythm) guide the new sound.",
})) tip("retention." + k, t);

// ---------- Timeline ----------
more("timeline.bin", "Asset bin", "All project assets, grouped by kind. Drag one onto a scene block on the timeline to add it to that scene with its default role and retention; drop it where you want a keyframe to land.\n\nDrop files from your computer on the bin to upload them. Double-click an asset to open it in the Assets tab.", "Project assets. Drag onto a scene to use them.");
tip("timeline.bin.upload", "Upload images, videos or audio into input/reelwright/<project>/. Each file gets a code such as P3 or A2.");
tip("timeline.bin.item", "Drag onto a scene to add it as a reference. Double-click to edit its defaults.");
// [OLD 2026-11-12 v0.12.0->v0.13.0] tip("timeline.monitor", "Plays the starred take of the scene under the playhead, or shows a storyboard picture when the scene has not been rendered.");
tip("timeline.monitor", "Plays the starred take of the scene under the playhead, or shows a storyboard picture when the scene has not been rendered. A take rendered while the film plays takes over at the same moment. Double-click (or F) for full screen.");  // added 2026-11-12 v0.13.0
tip("timeline.monitor.format", "Output size and frame rate from the Global tab.");
tip("timeline.monitor.take", "Showing the starred take. STALE means the scene changed since it was rendered.");
tip("timeline.monitor.storyboard", "Not rendered yet: showing the first picture reference or anchor as a storyboard.");
tip("timeline.timecode", "Playhead position (minutes:seconds.milliseconds).");
tip("timeline.transport.prev", "Jump to the start of this scene, or the previous scene if already at its start.");
tip("timeline.transport.play", "Play or pause (Space). Rendered scenes play their starred take; others advance over the storyboard.");
tip("timeline.transport.next", "Jump to the start of the next scene.");
tip("timeline.transport.loop", "Loop the scene under the playhead. I and O set a custom loop range at the playhead.");
// [OLD 2026-11-03 v0.4.3->v0.5.0] tip("timeline.transport.cut", "Length of the final cut: the timeline minus the overlaps that tail-clip continuations trim away.");
tip("timeline.transport.cut", "Length of the final cut. The timeline is the cut: a scene that continues the one before starts inside it, over the frames it repeats.");
tip("timeline.inspector.index", "Scene number in timeline order.");
tip("timeline.inspector.duration", "Target length on the timeline, in seconds and frames at 24 fps.");
tip("timeline.inspector.passes", "How H3 generates this scene: one pass (124–362 frames), several passes for long scenes, or one minimum pass trimmed down for short scenes.");
tip("timeline.inspector.overrides", "How many Global settings this scene overrides. Edit them on the Scene tab.");
tip("timeline.inspector.details", "The scene's length, how H3 generates it, its overrides and what it starts from."); // added 2026-11-12 v0.14.1
tip("timeline.inspector.refs", "The cast and references this scene sends to H3, each clip with its tag and range. Edit them on the Scene tab."); // added 2026-11-12 v0.14.1
tip("timeline.inspector.prompt", "The prompt of the first pass exactly as H3 receives it, with @tags turned into <Picture n>, <Subject n>, <Video n> and <Audio n>.");
tip("timeline.inspector.open", "Open this scene on the Scene tab.");
tip("timeline.inspector.render", "Queue this scene now, even if its take is up to date.");
tip("timeline.inspector.take", "Render another take of this scene with a new seed. The old takes stay on disk; star the one you like.");
tip("timeline.chip.cast", "A cast member in this scene. Their anchors are sent as references.");
tip("timeline.chip.ref", "A reference sent with this scene, with its role or retention.");
tip("timeline.chip.none", "Drag assets from the bin onto the scene block to add references.");
tip("timeline.addScene", "Add a new scene after the selected one (N). It starts the way the Global defaults say.");
tip("timeline.split", "Split the selected scene at the playhead (S). Shots, dialogue and keyframes go to the side they fall on; the second part continues from the first's last frame.");
// [OLD 2026-11-12 v0.13.0->v0.13.1] tip("timeline.duplicate", "Duplicate the selected scene (D), including references, shots, dialogue and overrides.");
tip("timeline.duplicate", "Duplicate the selected scene (D), including references, shots, dialogue, pass texts and overrides. To make a different scene from the copy, change its shots and dialogue too: they become the [Shot N] lines H3 follows."); // added 2026-11-12 v0.13.1
tip("timeline.delete", "Delete the selected scene (Delete). Undo brings it back; its takes stay on disk.");
tip("timeline.moveLeft", "Move the selected scene one place earlier.");
tip("timeline.moveRight", "Move the selected scene one place later.");
tip("timeline.snap", "When on, dragging a scene edge snaps to H3's 17k+5 frame grid, so the scene needs no trimming. Off: any whole frame.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("timeline.ripple", "Ripple: lengthening a scene pushes the later scenes along. Roll: the next scene shrinks by the same amount, so the total stays the same.");
tip("timeline.ripple", "Ripple: lengthening a scene pushes the later scenes along. Roll: the next scene shrinks by the same amount, so the total stays the same. While Auto-roll is on, it always rolls."); // added 2026-11-03 v0.6.0
tip("timeline.addMarker", "Add a marker at the playhead (M). Markers are notes for you and are not sent to H3.");
// [OLD 2026-11-02 v0.2.2->v0.3.0] Ctrl + wheel now zooms the ComfyUI canvas, like the wheel outside the node
// tip("timeline.zoom", "Timeline zoom in pixels per second. Ctrl or Alt + mouse wheel also zooms; + and − on the keyboard too.");
// [OLD 2026-11-02 v0.3.2->v0.3.3] tip("timeline.zoom", "Timeline zoom in pixels per second. Alt + mouse wheel over the lanes also zooms; + and − on the keyboard too. Ctrl + wheel anywhere on the node zooms the ComfyUI canvas (except over a text field).");
tip("timeline.zoom", "Timeline zoom in pixels per second. Alt + mouse wheel over the lanes also zooms; + and − on the keyboard too. The mouse wheel scrolls the timeline sideways (Shift + wheel: up and down), and dragging an empty spot pans it. Ctrl + wheel anywhere on the node zooms the ComfyUI canvas (except over a text field).");
tip("timeline.fit", "Zoom so the whole film fits the width.");
// [OLD 2026-11-02 v0.3.2->v0.3.3] tip("timeline.ruler", "Click or drag to move the playhead.");
tip("timeline.ruler", "Click to move the playhead here. Drag to pan the timeline; drag the playhead's time label to scrub.");
tip("timeline.playhead", "Drag to scrub through the film.");
tip("timeline.marker", "A marker. Click to edit its text and colour.");
tip("timeline.marker.text", "Marker text, shown on the ruler.");
tip("timeline.marker.color", "Marker colour.");
tip("timeline.marker.jump", "Move the playhead to this marker.");
tip("timeline.marker.delete", "Delete this marker.");
// [OLD 2026-11-02 v0.2.1->v0.2.2] right-click menu added: tip("timeline.scene", "A scene. Click to select, double-click to open it on the Scene tab, drop an asset on it to add a reference.");
// [OLD 2026-11-12 v0.13.0->v0.13.1] tip("timeline.scene", "A scene. Click to select, double-click to open it on the Scene tab, right-click for split, duplicate, move, lock and delete, drop an asset on it to add a reference.");
tip("timeline.scene", "A scene. Click to select, double-click to open it on the Scene tab, drag left or right to move it in the order (Esc cancels), right-click for split, duplicate, move, lock and delete, drop an asset on it to add a reference."); // added 2026-11-12 v0.13.1
tip("timeline.scene.resize", "Drag to change the scene's length. Long scenes split into several H3 passes automatically; short ones are trimmed from a minimum pass.");
tip("timeline.scene.shot", "A shot cut. Drag to move it; the prompt writes it as [ShotN] At mm:ss.fff, cut to …");
tip("timeline.scene.passes", "This scene is longer than one H3 pass (15.08 s), so it renders as several passes joined in the cut.");
tip("timeline.scene.short", "Shorter than the shortest H3 pass (5.17 s): rendered at 124 frames and trimmed to the window set on the Scene tab.");
tip("timeline.scene.seam.cut", "Pass seam on a shot cut: a plain cut, nothing to blend.");
tip("timeline.scene.seam.overlap", "Mid-shot pass seam: the next pass starts from the previous pass's tail and the overlap is crossfaded.");
tip("timeline.scene.progress", "Live render progress: phase, pass and sampling step.");
// added 2026-11-05 v0.7.0: the real frames of the starred take, and marks for the cut settings (Scene tab → In the cut)
tip("timeline.scene.film", "The starred take's frames: each picture is the frame at that time of the scene.");
tip("timeline.scene.transition", "The transition into this scene and its length (Scene tab → In the cut).");
tip("timeline.scene.transitionDip", "The transition into this scene plays as a dip through its colour: a soundtrack sets the timing, so scenes may not overlap.");
tip("timeline.scene.fadeIn", "The picture fades in from this colour (Scene tab → In the cut).");
tip("timeline.scene.fadeOut", "The picture fades out to this colour (Scene tab → In the cut).");
tip("timeline.join.fresh", "This scene starts fresh (hard cut). Click to change to last-frame continuation.");
tip("timeline.join.last_frame", "This scene starts from the previous scene's last frame. Click to change to tail-clip continuation.");
tip("timeline.join.tail", "This scene continues from the previous scene's tail clip and audio. Click to change to a fresh start.");
tip("timeline.lane.scenes", "Scene blocks. Status dot: green on disk, amber stale, hollow not rendered, blue rendering.");
tip("timeline.lane.pictures", "Picture references (bars) and keyframes (diamonds). A hollow diamond is the previous scene's last frame used as frame 0.");
tip("timeline.lane.video", "Video references, and the hatched tail clip a continuing scene starts from.");
tip("timeline.lane.audio", "Audio references, voice samples of speaking cast and video soundtracks.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are per clip now: tip("timeline.lane.dialogueLane", "Dialogue lines at their time in the scene, with speaker ID and language.");
tip("timeline.lane.dialogueLane", "Dialogue lines at their time in the scene, with speaker and language.");
tip("timeline.lane.cameraLane", "Camera wording of each shot.");
tip("timeline.lane.loras", "Top bar: the Global LoRA stack. Below: scene LoRAs, Global strengths a scene overrides (coral) and cast identity LoRAs (blue).");
tip("timeline.lane.castAnchors", "A cast member's anchor pictures, sent as one sheet or separately.");
tip("timeline.lane.picRef", "A picture reference sent for the whole scene, with its retention label.");
tip("timeline.lane.keyframe.first_frame", "A picture pinned as frame 0 of the scene.");
tip("timeline.lane.keyframe.last_frame", "A picture pinned as the last frame of the scene.");
tip("timeline.lane.keyframe.keyframe", "A picture pinned at this exact time (keyframe completion).");
tip("timeline.lane.lastFrameAuto", "The previous scene's last frame, used as this scene's frame 0.");
// [OLD 2026-11-12 v0.13.1->v0.14.0] tip("timeline.lane.vidRef", "A video reference (motion, camera or edit source). Uses one of the 3 video slots.");
tip("timeline.lane.vidRef", "A video reference (motion, camera or edit source) as the clip it sends: its tag (V1, V1.2 …), the part of the file and its length. Uses one of the 3 video slots."); // added 2026-11-12 v0.14.0
// [OLD 2026-11-12 v0.13.1->v0.14.0] tip("timeline.lane.audRef", "An audio reference with its retention label. Uses one of the 3 audio slots.");
tip("timeline.lane.audRef", "An audio reference as the clip it sends, with its retention label. Uses one of the 3 audio slots."); // added 2026-11-12 v0.14.0
// [OLD 2026-11-12 v0.13.1->v0.14.0] tip("timeline.lane.soundtrack", "The soundtrack of a video reference, sent as its own <Audio n>.");
tip("timeline.lane.soundtrack", "The sound of a video clip (With sound on), sent as its own <Audio n>."); // added 2026-11-12 v0.14.0
tip("timeline.lane.voice", "Voice sample of a speaking cast member, sent so their lines keep the same voice.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are per clip now: tip("timeline.lane.dialogue", "A spoken line. Written into the prompt as <Subject n> (S1) says <d>[Language] …</d>.");
tip("timeline.lane.dialogue", "A spoken line. Written into the prompt as <Subject n> (S1) says, <d>[Language] …</d>, with S1, S2… in speaking order.");
tip("timeline.lane.camera", "Camera wording written into this shot's line.");
tip("timeline.lane.lora.global", "LoRAs from the Global tab, applied to every scene first.");
tip("timeline.lane.lora.override", "A Global LoRA whose strength this scene changes.");
tip("timeline.lane.lora.scene", "A LoRA only this scene uses.");
tip("timeline.lane.lora.cast", "A cast member's identity LoRA, added automatically to every scene they are in.");

// ---------- Scene ----------
tip("scene.nav.prev", "Previous scene.");
tip("scene.nav.next", "Next scene.");
// [OLD 2026-11-02 v0.2.1->v0.2.2] right-click menu added: tip("scene.nav.strip", "All scenes, sized by length. Click to switch. The bottom stripe shows status: green on disk, amber stale.");
tip("scene.nav.strip", "All scenes, sized by length. Click to switch, right-click for the scene menu. The bottom stripe shows status: green on disk, amber stale.");
tip("scene.title", "Scene title, used on the timeline, in chapters and in file names.");
more("scene.duration", "Duration", "Scenes can be any length. H3 generates 124 to 362 frames per pass (5.17–15.08 s at 24 fps), always on its 17k+5 frame grid (124, 141, 158 … 362).\n\nLonger scenes are split into several passes, joined on shot cuts where possible and with short overlaps elsewhere. Shorter scenes render one 124-frame pass and keep the window you choose; the rest stays on disk so you can move the window later. Lengths between grid points render one grid step longer and are trimmed exactly.", "How long the scene is on the timeline.");
tip("scene.duration.step", "Move to the previous or next 17k+5 grid length (one step is 17 frames, 0.71 s).");
tip("scene.duration.input", "Type any length in seconds; it is rounded to whole frames at 24 fps.");
tip("scene.duration.bar", "Where this length sits relative to H3's single-pass range. The green zone is the trained range (124–362 frames).");
tip("scene.duration.trained", "H3 was trained on 124–362 frames per generation.");
tip("scene.duration.plan", "How this length will be generated: one pass, several passes, or a trimmed minimum pass.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("scene.duration.in", "Where the scene starts on the timeline.");
tip("scene.duration.in", "Where the scene first shows new content in the cut. A continuing scene starts a little earlier, inside the scene before (the repeated tail or last frame)."); // added 2026-11-03 v0.6.0
tip("scene.duration.out", "Where the scene ends on the timeline.");
tip("scene.trim.keep", "Which part of the 5.17 s minimum pass to keep.");
tip("scene.trim.start", "Keep the beginning of the generated pass.");
tip("scene.trim.middle", "Keep the middle of the generated pass.");
tip("scene.trim.end", "Keep the end of the generated pass.");
tip("scene.trim.custom", "Choose the in-point yourself.");
tip("scene.trim.window", "The kept window (coral) inside the generated 124-frame pass. The hatched parts stay on disk as handles.");
tip("scene.trim.in", "Where the kept window starts inside the generated pass. Changing it later needs no re-render.");
more("scene.start", "Starts from", "Fresh start is a hard cut: nothing is carried over.\n\nLast frame pins the previous scene's final frame as guide frame 0 (fully preserved), so the new scene begins exactly where the old one ended. It costs no reference slot.\n\nTail clip pins the previous scene's last N frames and their audio at the start of this scene. Motion, light and sound carry across, and the overlap is trimmed in the final cut. N snaps to H3's 17k+5 clip lengths (22, 39, 56 …).\n\nIdentity is not passed along this way: cast anchors are always sent, so long chains do not drift.", "How this scene begins relative to the previous one.");
tip("scene.start.fresh", "Hard cut. Nothing from the previous scene is used.");
tip("scene.start.last_frame", "The previous scene's last frame becomes guide frame 0 of this scene (fully preserved).");
tip("scene.start.tail", "The previous scene's last frames and audio guide the start of this scene; the overlap is trimmed in the cut.");
more("scene.transition", "Cut into this scene", "How the merge joins this scene to the previous one when this scene starts fresh (a hard cut). By default it uses the Merge scenes settings on the Render tab; set a value here to use a different transition, length or audio fade for this seam only.\n\nScenes that start from the last frame or a tail clip are joined seamlessly, so these settings do not apply to them.", "This scene's transition in the final cut.");
tip("scene.transition.mode", "Cut, crossfade or dip to black at the seam before this scene. Default follows Render → Merge scenes.");
tip("scene.transition.frames", "Length of the crossfade or dip into this scene, in frames at 24 fps.");
tip("scene.transition.audioFade", "Audio fade-in at the start of this scene (and fade-out at the end of the previous one), in frames.");
tip("scene.start.overlap", "How many frames of the previous scene's tail guide this scene. Longer overlaps carry motion better but cost generation time.");
// added 2026-11-05 v0.7.0: "In the cut" (scene.merge): the join, fades, sound and colour of each scene in the merge
more("scene.cut", "In the cut", "How the merge puts this scene into the film. Nothing here changes the render: it is applied when the scenes are joined, so you can change it and merge again in seconds.\n\nJoin: how this scene follows the one before when it starts fresh: a plain cut, or a transition (crossfade, dip to a colour, dissolve, wipe, slide, circle, pixelize, radial, zoom) of a length you choose. A scene that continues the one before (last frame or tail clip) always joins by its continuation.\n\nStart and End: fade the picture in from a colour or out to a colour, and fade the sound in or out, inside the scene (its length does not change).\n\nSound: the level of the scene's own sound, or mute it. Colour: match the scene's colour to the scene before or to a scene you choose (useful when the light or the setting changes), and adjust brightness, contrast and saturation.\n\nApply to all copies these settings to every scene, or to the scenes after this one, in one undo step.", "How the merge joins, fades, levels and grades this scene.");
tip("scene.cut.join", "How this scene follows the one before in the merged film.");
tip("scene.cut.transition", "How this scene joins the one before when it starts fresh: a plain cut or an overlapping transition. Scenes that continue the one before join by their continuation, so this is not used for them.");
tip("scene.cut.direction", "The direction a wipe or slide moves in.");
tip("scene.cut.frames", "Length of the transition, in frames at 24 fps. The end of the scene before and the start of this one play over each other for this long.");
tip("scene.cut.color", "The colour a dip goes through. With a soundtrack setting the timing every transition plays as a dip through this colour.");
// [OLD 2026-11-05 v0.7.0 lead review] tip("scene.cut.audio", "Audio crossfade over a transition, or the short fade out and in at a plain cut (avoids clicks), in frames.");
tip("scene.cut.audio", "The short fade out and in of the sound at a plain cut or a dip that keeps the timing (avoids clicks), in frames. On a crossfade, wipe or other overlapping transition the sound crossfades over the whole transition.");
tip("scene.cut.continuation", "This scene continues the one before (last frame or tail clip), so the merge joins them seamlessly: a tail overlap is crossfaded (Global → Long scenes → Crossfade), a repeated last frame is dropped.");
tip("scene.cut.first", "The first scene has nothing before it to join to.");
tip("scene.cut.locked", "A soundtrack sets the timing (Timeline tab), so scenes may not overlap: every transition plays as a dip through its colour inside both scenes and each scene stays on the song.");
tip("scene.cut.start", "How the scene begins in the cut: a picture fade from a colour and a sound fade.");
tip("scene.cut.fadeIn", "Fade the picture in from a colour over the scene's first frames (0 = no fade). The scene's length does not change.");
tip("scene.cut.fadeInColor", "The colour the picture fades in from.");
tip("scene.cut.audioFadeIn", "Fade the scene's sound in over its first frames (0 = none).");
tip("scene.cut.fadeInWarn", "A continuing scene is meant to flow on from the one before; a fade in at its start interrupts that.");
tip("scene.cut.end", "How the scene ends in the cut: a picture fade to a colour and a sound fade.");
tip("scene.cut.fadeOut", "Fade the picture out to a colour over the scene's last frames (0 = no fade). The scene's length does not change.");
tip("scene.cut.fadeOutColor", "The colour the picture fades out to.");
tip("scene.cut.audioFadeOut", "Fade the scene's sound out over its last frames (0 = none).");
tip("scene.cut.fadeOutWarn", "The next scene continues from this scene's last frame as it was rendered, before the fade, so the film jumps back to the picture.");
tip("scene.cut.sound", "The scene's own sound in the merged film.");
tip("scene.cut.volume", "Level of this scene's own sound in the cut, in dB (0 = as rendered). A soundtrack is set on the Timeline tab.");
tip("scene.cut.mute", "Leave this scene's own sound out of the cut.");
tip("scene.cut.colour", "Colour correction of this scene in the cut.");
tip("scene.cut.colorMatch", "Match this scene's colour to another scene, to smooth jumps between scenes, passes or VAEs. Off keeps it as rendered.");
tip("scene.cut.colorMatch.previous", "Match the scene before it in the cut (after that scene's own correction).");
tip("scene.cut.colorMatch.scene", "Match a scene you choose: its starred take is measured, even when a range merge leaves it out.");
tip("scene.cut.colorRef", "The scene this one is matched to.");
tip("scene.cut.brightness", "Brightness in the cut: −1 to +1, 0 = unchanged.");
tip("scene.cut.contrast", "Contrast in the cut: 0 to 2, 1 = unchanged.");
tip("scene.cut.saturation", "Colour saturation in the cut: 0 (grey) to 3, 1 = unchanged.");
tip("scene.cut.reset", "Back to the value a new scene gets.");
tip("scene.cut.resetAll", "Put every setting of this card back to a new scene's values. Ctrl+Z undoes it.");
tip("scene.cut.applyAll", "Copy this card's settings to other scenes: all of them, or the scenes after this one. One undo step.");
tip("scene.cut.applyAfter", "Copy the settings to the scenes after this one only.");
more("scene.overrides", "Generation", "Settings this scene uses instead of the Global ones. A hollow dot follows Global; a coral dot is overridden here, and the reset button brings back the Global value.\n\nPer-scene VAEs are safe: every scene is decoded to a file, and continuations pass pixels (a frame or a clip), never latents, so a different VAE in one scene affects nothing else.", "Settings this scene overrides.");
tip("scene.override.seed", "Seed for this scene. Without an override it is the Global seed (plus the scene index in +1 mode). Long scenes add the pass index.");
tip("scene.override.steps", "Sampling steps. The native H3 workflow uses 20; turbo LoRAs need about 8.");
tip("scene.override.sampler", "Sampler. H3's native workflow uses res_multistep.");
tip("scene.override.scheduler", "Scheduler. H3's native workflow uses simple.");
tip("scene.override.width", "Output width in pixels (multiple of 32). H3 targets about 1 MP with a 768-pixel short edge.");
tip("scene.override.height", "Output height in pixels (multiple of 32).");
tip("scene.override.diffusion", "A different diffusion model (for example a fine-tune) for this scene only.");
tip("scene.override.text_encoder", "A different text encoder file for this scene. Its CLIP type stays minimax.");
tip("scene.override.video_vae", "A different video VAE for this scene. Safe: scenes hand over pixels, not latents.");
tip("scene.override.audio_vae", "A different audio VAE for this scene.");
tip("scene.override.quality", "Render this scene as Draft or Final regardless of the Global quality switch. Handy for keeping approved scenes at Final while you iterate on the rest in Draft. Part of the cache key, so draft and final takes are kept apart.");
tip("scene.override.resetAll", "Clear every override in this scene so it follows the Global tab again.");
tip("scene.lock", "Keep the starred take even when a scene this one continues from changes. A locked scene never goes stale on its own.");
tip("scene.color", "Tint for this scene's block on the timeline. Only for you.");
tip("scene.notes", "Notes for yourself. Not sent to H3.");
more("scene.misc", "Scene", "Title, lock, timeline tint and private notes. None of these change what is rendered, except that a locked scene keeps its take.", "Title, lock, tint and notes.");
// [OLD 2026-11-05 v0.7.0->v0.8.0] no pass tabs or Write prompts: more("scene.prompt", "Prompt", "Structured mode follows the MiniMax H3 reference prompt guide. It has six sections: subject definitions, summary, retention analysis, detailed description, soundscape and music. Subjects, retention lines, shots and dialogue can be filled in automatically from the scene's cast, references, shots and dialogue lists.\n\nRefer to assets as @P1, @V2 or @A1, to cast members as @Mara or @{Old Keeper}, and to the previous scene's tail as @tail. Each pass renumbers them into <Picture k>, <Video k>, <Audio k> and <Subject n> in the order H3 receives references: images, then videos (a video's soundtrack takes an <Audio> number just before it), then standalone audio.\n\nRaw mode sends your text as written, after the @tags are replaced.", "The prompt for this scene.");
// added 2026-11-05 v0.8.0: a tab per pass, Write prompts
more("scene.prompt", "Prompt", "Structured mode follows the MiniMax H3 reference prompt guide. It has six sections: subject definitions, summary, retention analysis, detailed description, soundscape and music. Subjects, retention lines, shots and dialogue can be filled in automatically from the scene's cast, references, shots and dialogue lists.\n\nA scene longer than one pass gets a tab per pass. Every pass does part of the scene's action, so each one can have its own six sections: an empty section of a pass uses the scene's shared text (or the automatic one), shown greyed in the field. The scene's summary becomes a note on the whole scene for you and the LLM: H3 gets each pass's own summary, or one made from that pass's shots and dialogue.\n\nWrite prompts asks the LLM to write the sections of every pass, one request per pass, about 350–500 words of detailed description each. Each scene's answer is one undo step.\n\nRefer to assets as @P1, @V2 or @A1, to cast members as @Mara or @{Old Keeper}, and to the previous scene's tail as @tail. Each pass renumbers them into <Picture k>, <Video k>, <Audio k> and <Subject n> in the order H3 receives references: images, then videos (a video's soundtrack takes an <Audio> number just before it), then standalone audio.\n\nRaw mode sends your text as written, after the @tags are replaced.", "The prompt for this scene, per pass in a long scene.");
tip("scene.prompt.mode", "Structured: six guided sections. Raw: one free text.");
tip("scene.prompt.structured", "Six sections following the H3 reference prompt guide, with automatic parts.");
tip("scene.prompt.raw", "One free-form prompt. @tags are still renumbered.");
tip("scene.prompt.rawEditor", "The whole prompt. Type @ for a list of assets, cast members and @tail.");
tip("scene.prompt.tasks", "Task tags put at the start of the summary. They are worked out from the references and how the scene starts, as the H3 guide recommends.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("scene.prompt.unknown", "These @tags match no asset code, cast name or @tail, so they would reach H3 as plain text.");
tip("scene.prompt.unknown", "These @names match no cast member or asset, so H3 gets them as plain text. That is fine for an @handle; write @@ for a literal @."); // added 2026-11-03 v0.6.0
tip("scene.prompt.auto.subjects", "Write a <Subject n> line for every cast member in the scene, from their description and anchors.");
tip("scene.prompt.auto.retention", "Write one retention line per reference: label (fully_preserved, weak_reference …) plus the features to keep.");
tip("scene.prompt.auto.shots", "Write the shots list ([Shot1], [Shot2] At 00:05.000 …) and the dialogue lines into the description, in time order.");
for (const [k, t] of Object.entries({
  subject_definitions: "Who and what appears. Cast entries add <Subject n>: <Picture k> — description automatically; add anything extra here.",
  summary: "One or two sentences on what happens. The task tags are put in front automatically.",
  retention_analysis: "What must stay the same from each reference. Retention labels of the references are added automatically.",
  detailed_description: "Look, staging and action. Shots and dialogue from the lists below are appended automatically. One main action per shot works best.",
  overall_soundscape: "Diegetic sound that exists in the scene: room tone, footsteps, props. Keep dialogue out of it.",
  non_diegetic_music: "Score for the audience only: instruments, tempo, mood, mix level. Write N/A for none.",
})) tip("scene.prompt.section." + k, t);
// [OLD 2026-11-05 v0.7.0->v0.8.0] no start/end/length row, camera picker or seam notes: more("scene.shots", "Shots", "Each shot becomes a line in the prompt: [Shot1] for the first, [Shot2] At 00:05.000, cut to … for later ones. Timestamps mark cuts, not how long an action takes, so keep each shot to one achievable action.\n\nIn long scenes, passes split on shot cuts whenever possible, so a cut is also the cleanest place for a seam. With no shots, the scene is described as one continuous take.", "Shot cuts inside this scene.");
// added 2026-11-05 v0.8.0: start, end and length per row; the camera picker; pass seams
more("scene.shots", "Shots", "Each shot becomes a line in the prompt: [Shot 1] for the first, [Shot 2] At 00:05.000, the camera cuts to … for later ones. Timestamps mark cuts, not how long an action takes, so keep each shot to one achievable action.\n\nEach row shows when the shot starts and ends and how long it lasts, all in scene time. Change the length to move the next shot's start; the last shot's length is the scene's length.\n\nThe camera picker offers the moves H3 knows (Push In, Pan Left, Arc Shot …) with an amplitude and a speed, written as one sentence such as \"The camera pushes in with small amplitude at slow speed\", and a framing (wide, close-up, low angle …). Medium amplitude and normal speed are left out, as MiniMax's guide advises. You can still type your own camera words.\n\nIn long scenes, passes split on shot cuts whenever possible, so a cut is also the cleanest place for a seam: a row says when a pass seam falls inside its shot. With no shots, the scene is described as one continuous take.", "Shot cuts inside this scene.");
tip("scene.shots.add", "Add a shot. Its start time is a cut in the prompt.");
// added 2026-11-12 v0.14.2: shots and spoken lines taken from the description
// [OLD 2026-11-12 v0.14.2->v0.14.3] more("scene.shots.fill", "Shots from the description", "The detailed description holds [Shot N] lines or spoken lines (<d>…</d>) while the scene has no shots on the timeline, so the Shots and Dialogue lists, the timeline lanes, captions and subtitles show none of it.\n\nThis puts each [Shot N] on the timeline as a shot (its \"At MM:SS\" is its start) and each spoken line as a dialogue line: the speaker is the @name or (S1) before it, the language its [Language], the delivery the verb (\"mutters\"). Lines are timed one after another inside their shot; adjust them if you like. The description keeps only the style sentences before [Shot 1], because with \"auto shots + dialogue\" on the editor writes the shots and lines back into the prompt.\n\nWrite prompts and the Prompt rewriter do this by themselves for a scene made in one pass that has no shots yet. One undo step.", "Put the shots and spoken lines written in the description on the timeline.");
more("scene.shots.fill", "Shots from the description", "The detailed description holds [Shot N] lines or spoken lines (<d>…</d>) while the scene has no shots on the timeline, so the Shots and Dialogue lists, the timeline lanes, captions and subtitles show none of it.\n\nThis puts each [Shot N] on the timeline as a shot (its \"At MM:SS\" is its start; a framing at its start, such as \"A medium shot:\", and its camera move, such as \"The camera slowly pushes in.\", go into the shot's framing, camera, amplitude and speed) and each spoken line as a dialogue line: the speaker is the @name or (S1) before it, the language its [Language], the delivery the verb (\"mutters\"). Lines are timed one after another inside their shot; adjust them if you like. The description keeps only the style sentences before [Shot 1], because with \"auto shots + dialogue\" on the editor writes the shots and lines back into the prompt.\n\nWrite prompts and the Prompt rewriter do this by themselves for a scene made in one pass that has no shots yet. One undo step.", "Put the shots and spoken lines written in the description on the timeline."); // added 2026-11-12 v0.14.3: framing and camera move
tip("scene.shots.index", "How the shot is labelled in the prompt.");
tip("scene.shots.time", "When the shot starts, in seconds from the start of the scene.");
// [OLD 2026-11-05 v0.7.0->v0.8.0] free text with presets only: tip("scene.shots.camera", "Camera wording, such as shot size and movement. Pick a preset or type your own.");
tip("scene.shots.camera", "The camera move: one of H3's moves (Push In, Pan Left, Arc Shot, Static Shot …), a preset of your own, or your own words. Type to filter."); // added 2026-11-05 v0.8.0
tip("scene.shots.text", "What happens in this shot. Use @tags for assets and cast.");
tip("scene.shots.remove", "Remove this shot.");
// added 2026-11-03 v0.4.3: shot length and shots after the end
// [OLD 2026-11-05 v0.7.0->v0.8.0] the length is a field now; this note is for shots after the end: tip("scene.shots.length", "How long the shot lasts: until the next shot starts. The last shot runs to the end of the scene (· end); a shot that starts after the end is never rendered.");
tip("scene.shots.length", "This shot starts at or after the end of the scene, so it is never rendered."); // added 2026-11-05 v0.8.0
more("scene.shots.overrun", "Shots after the end", "A shot or dialogue line that starts at or after the end of the scene is never rendered.\n\nLengthen: the scene gets longer so everything fits; the last shot gets the scene's typical shot length (the middle of its shot lengths), a dialogue line 2 s. Later scenes move along on the timeline.\n\nFit into: the scene keeps its length and every shot and line moves closer to the start, in proportion.\n\nBoth can be undone with Ctrl+Z. The Issues list has a button that lengthens every such scene at once.", "Shots or lines start after the scene ends.");
tip("scene.shots.lengthen", "Make the scene long enough for every shot and line. Ctrl+Z undoes it.");
tip("scene.shots.squeeze", "Keep the scene's length and move every shot and line closer together, in proportion.");
tip("global.script.fitNote", "The LLM's scene length did not match its shots, so it was changed to fit them.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are per clip now: more("scene.dialogue", "Dialogue", "Each line is written as <Subject n> (S1) says <d>[English] …</d>. The speaker ID (S1, S2) stays the same for a character across the whole project, and their voice sample is sent as an audio reference so the voice matches.\n\nH3 speaks 11 languages reliably: Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian and Spanish.", "Spoken lines in this scene.");
// [OLD 2026-11-05 v0.7.0->v0.8.0] no end, length or seam note: more("scene.dialogue", "Dialogue", "Each line is written as <Subject n> (S1) says, <d>[English] …</d>. As MiniMax's guide asks, speaker IDs follow speaking order inside each clip: whoever speaks first is S1, the next new voice S2, and so on. The character's voice sample is sent as an audio reference so the voice matches across scenes.\n\nH3 speaks 11 languages reliably: Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian and Spanish. You can type any other language name; it is sent as written.", "Spoken lines in this scene.");
// added 2026-11-05 v0.8.0: end and length per line, seam notes
more("scene.dialogue", "Dialogue", "Each line is written as <Subject n> (S1) says, <d>[English] …</d>. As MiniMax's guide asks, speaker IDs follow speaking order inside each clip: whoever speaks first is S1, the next new voice S2, and so on. The character's voice sample is sent as an audio reference so the voice matches across scenes.\n\nEach row shows when the line starts and ends, in scene time. Its length is estimated from the words (about 2.5 words a second) until you type one. A line that runs past a pass seam is cut off where the next pass takes over, so the row warns about it: move it, shorten it, or put a shot cut there.\n\nH3 speaks 11 languages reliably: Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian and Spanish. You can type any other language name; it is sent as written.", "Spoken lines in this scene.");
tip("scene.dialogue.add", "Add a spoken line.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are now per clip: tip("scene.dialogue.speaker", "Who speaks. Characters come from the Cast tab.");
tip("scene.dialogue.speaker", "Who speaks. Type to filter; characters come from the Cast tab. Speaker IDs (S1, S2…) are given in speaking order in each clip, as H3's guide asks.");
tip("scene.dialogue.time", "When the line starts, in seconds from the start of the scene.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] free-text language: tip("scene.dialogue.language", "Language tag written as <d>[Language] …</d>.");
tip("scene.dialogue.language", "Language tag written as <d>[Language] …</d>. Type to filter the list, or type any language name and press Enter to use it.");
tip("scene.dialogue.delivery", "How it is said: whispers, shouts, says calmly …");
tip("scene.dialogue.text", "The words, exactly as they should be spoken.");
tip("scene.dialogue.remove", "Remove this line.");
tip("scene.dialogue.noCast", "Lines need a speaker from the story bible.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] describes the Ref2VA layout: more("scene.preview", "What H3 receives", "The final prompt of every pass, built by the backend from the sections, shots, dialogue, cast and references, with @tags renumbered for that pass.\n\nLong scenes have one prompt per pass. By default, shots and dialogue are assigned to the pass that contains them, with timestamps re-based to the start of the pass. Split with LLM can write the per-pass prompts for you, and you can edit any pass by hand.", "The exact prompt sent for each pass.");
tip("scene.preview.copy", "Copy this pass's prompt exactly as H3 receives it."); // added 2026-11-06 v0.10.0
more("scene.preview", "What H3 receives", "The final prompt of every pass, built by the backend in MiniMax's Ref2VA format: six labelled sections in order (subject_definitions, summary, retention_analysis, detailed_description, overall_soundscape, non_diegetic_music), each label on its own line.\n\nReference pictures that define a character, place, prop or style become <Subject N> lines; standalone <Picture N> is kept for frame anchors. Shots are written as [Shot 1] …, [Shot 2] At 00:06.000, the shot cuts to …, and speakers are numbered S1, S2… in speaking order.\n\nLong scenes have one prompt per pass, with shots and dialogue re-based to the start of each pass. Split with LLM can write the per-pass prompts, and you can edit any pass by hand.", "The exact prompt sent for each pass, in Ref2VA format.");
// [OLD 2026-11-06 v0.8.0->v0.9.0] tip("scene.preview.pass", "Show the prompt of this pass: its time range, frame count and the seam before it. A coral dot means the pass prompt was edited by hand.");
tip("scene.preview.pass", "This pass: its time range, frame count and the seam before it. The Prompt card's tabs choose the pass; Whole scene shows every pass in turn."); // added 2026-11-06 v0.9.0
tip("scene.preview.splitLlm", "Ask the LLM to write one prompt per pass, keeping tags and dialogue as written. Runs only when you click.");
tip("scene.preview.splitAuto", "Drop the hand-written pass prompts and go back to the automatic split.");
tip("scene.preview.override", "Edit this pass's prompt by hand. It replaces the automatic one for this pass only.");
// [OLD 2026-11-06 v0.9.0->v0.10.0] the rewriter works on one pass now
// more("scene.rewrite", "Prompt rewriter", "Sends this scene's prompt to the OpenAI-compatible LLM set on the Global tab and shows the proposed changes as a diff. You accept, edit or discard them.\n\nIt runs only when you press Rewrite, never while rendering. Asset tags and <d>…</d> lines are checked after the rewrite; any that changed are reported as warnings.", "Improve the prompt with an LLM, on demand.");
// [/OLD]
// added 2026-11-06 v0.10.0
more("scene.rewrite", "Prompt rewriter", "Sends a prompt to the OpenAI-compatible LLM set on the Global tab and shows the proposed changes as a diff. You accept, edit or discard them.\n\nIn a scene of one pass (or a raw prompt) it rewrites the scene's prompt. In a scene of several passes it works on one pass: open that pass's tab in the Prompt card and the rewriter rewrites the pass's own sections, with its shots, spoken lines and the passes around it in view (the same request as Write prompts, plus your instruction). On the Whole scene tab it is hidden; edit the shared texts there by hand or use Write prompts.\n\nIt runs only when you press Rewrite, never while rendering. Asset tags and <d>…</d> lines are checked after the rewrite; any that changed are reported as warnings.", "Improve the prompt with an LLM, on demand.");
tip("scene.rewrite.instruction", "Optional instruction for the rewrite, for example: make shot 2 more intimate.");
tip("scene.rewrite.run", "Send the prompt to the LLM and show a diff. Nothing changes until you accept.");
tip("scene.rewrite.diff", "Green lines are added, red lines are removed.");
tip("scene.rewrite.accept", "Apply the rewrite. Ctrl+Z undoes it.");
tip("scene.rewrite.edit", "Edit the proposed text before applying it.");
tip("scene.rewrite.discard", "Throw the proposal away.");
more("scene.budget", "Reference budget", "What this scene sends per pass. H3 ref2va accepts up to 9 pictures, 3 videos (2–15 s each, 15 s in total), 3 audio clips (same limits) and 12 files overall.\n\nWith Name the continuation on (Cast tab), the scene before's last frame (<Picture 1>) or tail clip (<Video 1>, with its sound when an audio slot is free) counts here too. A first-frame, last-frame or keyframe picture counts in the passes it guides. Packing a character's anchors into one sheet uses a single picture slot.", "How many reference slots this scene uses.");
// [OLD 2026-11-05 v0.7.0 lead review] the text above said guides and continuation clips never count
tip("scene.budget.pictures", "Picture references plus anchor sheets. Max 9.");
tip("scene.budget.videos", "Video references, and their total length. Max 3 videos and 15 s.");
tip("scene.budget.audio", "Audio references, video soundtracks and voice samples, with their total length. Max 3 and 15 s.");
// [OLD 2026-11-12 v0.13.1->v0.14.0] more("scene.refs", "References", "Assets this scene sends to H3. A picture can be a reference for the whole scene, or a guide pinned as the first frame, the last frame or a keyframe at a set time. Videos and audio are always references.\n\nEach reference has a retention label telling H3 how closely to follow it, and a list of features to keep. Values that differ from the asset's defaults are marked with a coral dot.", "Assets sent with this scene.");
more("scene.refs", "References", "Assets this scene sends to H3. A picture can be a reference for the whole scene, or a guide pinned as the first frame, the last frame or a keyframe at a set time. Videos and audio are always references, and each one sends a clip: the whole file or the part between its From and To. Add the same video or audio more than once to send different parts of it.\n\nEach reference has a retention label telling H3 how closely to follow it, and a list of features to keep. Values that differ from the asset's defaults are marked with a coral dot.", "Assets sent with this scene."); // added 2026-11-12 v0.14.0: clips
// [OLD 2026-11-12 v0.11.0->v0.12.0] tip("scene.refs.role", "reference: guides the whole scene. first_frame / last_frame / keyframe: pins this picture at that exact frame.");
// added 2026-11-12 v0.12.0: pose
tip("scene.refs.role", "reference: guides the whole scene. first_frame / last_frame / keyframe: pins this picture at that exact frame. pose: a character of this scene takes the body pose in this picture, in the shot at its time.");
more("scene.refs.pose", "Pose reference", "A picture whose body pose one character of this scene takes, in the shot at its time: a superhero landing, a way of sitting, a dance figure. Pick whose pose it is.\n\nOnly the pose is used: the prompt cites the picture in that character's line (\"<Subject 1> is Mara, …, whose pose in [Shot 2] comes from <Picture 3>\") and marks it attribute_transfer (\"the body pose is transferred to <Subject 1>; the person, clothing and setting in <Picture 3> do not appear\"), as MiniMax's Ref2VA guide does for a characteristic taken from one reference for another subject. It is never a subject of its own, so the person in the picture is not put in the shot.\n\nIt goes to the pass whose time span holds its time, and takes one of the 9 picture slots there. Say what happens in the shot text, for example \"@Mara strikes the pose from @P3\". H3 follows it from the prompt, not as an exact skeleton, so a clear, full-body picture works best.", "The character takes the body pose in this picture; the person in it does not appear.");
tip("scene.refs.poseCast", "The character of this scene who takes this pose.");
tip("scene.refs.poseTime", "When the pose is taken, in seconds from the start of the scene: it names the shot at that time, and the picture goes to the pass that holds it.");
tip("scene.refs.time", "When the keyframe is pinned, in seconds from the start of the scene.");
tip("scene.refs.retention", "How closely H3 should follow this reference.");
tip("scene.refs.description", "The asset's description as this scene uses it. It lives on the asset: click to edit it in the Assets tab, and every scene follows.");
tip("scene.cast.description", "The description this character's subject line uses: its own, or its first described anchor picture's.");
tip("scene.refs.keep", "Features to keep, written into the retention line (face, hair, coat …). Press Enter to add.");
// [OLD 2026-11-12 v0.13.1->v0.14.0] tip("scene.refs.soundtrack", "Also send this video's audio as its own <Audio n>, numbered just before the video.");
tip("scene.refs.soundtrack", "With sound: also send this clip's own sound as an <Audio n> of its own (it takes one of the 3 audio slots). Off: the picture only."); // added 2026-11-12 v0.14.0
// added 2026-11-12 v0.14.0: clips of video and audio references
more("scene.refs.clip", "Clip", "The part of the video or audio file this reference sends: From and To in the file (To empty = to its end). Add the same asset again under References to send another part of it: each reference is a clip of its own, with its own retention and, for a video, with or without its sound.\n\nType seconds (4.5), frames (108f) or a time (0:04.5). Times are kept on whole frames (24 fps). H3 takes 2-15 s per reference and 15 s of video (and of audio) per pass in all; only the first 15 s of a longer clip is sent.\n\nIn the prompt, the first reference of an asset is @V1, the next ones @V1.2, @V1.3 … (click the tag to copy it).", "The part of the file this reference sends.");
tip("scene.refs.token", "This clip's @ tag. @V1 is the first reference of V1 in this scene, @V1.2 the second and so on. Click to copy it.");
tip("scene.refs.clipFrom", "Where the clip starts in the file. Seconds (4.5), frames (108f) or a time (0:04.5).");
tip("scene.refs.clipTo", "Where the clip ends in the file. Empty: the end of the file.");
tip("scene.refs.clipLength", "The clip's length. Typing one moves To.");
tip("scene.refs.clipReset", "Send the whole file again (From 0, no To).");
tip("scene.refs.clipBar", "The whole file, with the clip marked. Drag either end to move From or To (on whole frames).");
tip("scene.refs.clipPreview", "Play the file here, to find where the clip should start and end.");
tip("scene.refs.clipHere", "Take the preview's position as From or To.");
tip("scene.refs.clipPlay", "Play the clip from From to To.");
tip("scene.refs.remove", "Remove this reference from the scene.");
// added 2026-11-12 v0.15.0: drag to reorder
more("scene.refs.order", "Reorder", "Drag the grip up or down to put this reference elsewhere in the list; ↑ / ↓ on the grip move it one place. Each move is one undo step.\n\nThe order is the order the references are sent in, after the cast's pictures, so it sets their numbers in the prompt (<Picture 2>, <Video 1> …).", "Drag to reorder.");
// [OLD 2026-11-12 v0.13.1->v0.14.0] tip("scene.refs.add", "Add an asset as a reference with its default role and retention.");
tip("scene.refs.add", "Add an asset as a reference with its default role and retention. A video or audio asset can be added more than once, to send different parts of it."); // added 2026-11-12 v0.14.0
tip("scene.refs.overridden", "This reference differs from the asset's defaults.");
more("scene.cast", "Cast in this scene", "Characters, locations and props from the story bible. Their anchors, description, voice and identity LoRA are added automatically. Pick an outfit to change clothes while keeping the face.", "Story-bible entries in this scene.");
tip("scene.cast.add", "Add a character, location or prop from the Cast tab.");
tip("scene.cast.outfit", "Which outfit or variant they wear in this scene.");
tip("scene.cast.remove", "Remove from this scene.");
// added 2026-11-12 v0.16.0: a sheet whose pictures are too small
more("scene.cast.smallSheet", "Sheet too small", "This cast member's pictures go to H3 as one sheet, and at this scene's size each picture reaches H3 at under 300 px: a face that small does not hold the identity well.\n\nKeep a sheet to about 4 pictures (a clear face and a full body), pick Separate or Auto under Cast → Anchors, or set Global → Output → Reference images to max (slower sampling).", "Each picture of the sheet is too small for identity.");
// added 2026-11-12 v0.15.0: drag to reorder
more("scene.cast.order", "Reorder", "Drag the grip up or down to put this cast member elsewhere in the list; ↑ / ↓ on the grip move them one place. Each move is one undo step.\n\nThe order is the order of the subjects in the prompt (<Subject 1>, <Subject 2> …) and of their pictures.", "Drag to reorder.");
more("scene.loras", "Scene LoRAs", "Add to Global applies the Global LoRA stack first and then this scene's LoRAs. Replace Global uses only this scene's LoRAs.\n\nYou can also change the strength of a Global LoRA for this scene only. Identity LoRAs of cast members are added automatically and shown in blue.", "LoRAs for this scene.");
tip("scene.loras.mode", "Add to the Global stack, or replace it for this scene.");
tip("scene.loras.add", "Use the Global LoRAs and add this scene's on top.");
tip("scene.loras.replace", "Ignore the Global LoRAs in this scene.");
tip("scene.loras.strength", "Strength for this scene. Set it back to the Global value to remove the override.");
tip("scene.loras.name", "LoRA file (from ComfyUI's loras folder).");
tip("scene.loras.remove", "Remove this LoRA from the scene.");
// added 2026-11-12 v0.15.0: drag to reorder
more("scene.loras.order", "Reorder", "Drag the grip up or down to put this LoRA elsewhere among the scene's own LoRAs; ↑ / ↓ on the grip move it one place. Each move is one undo step.\n\nLoRAs load in this order, after Global's (whose order is set on the Global tab).", "Drag to reorder.");
tip("scene.loras.addItem", "Add a LoRA for this scene only.");
tip("scene.loras.cast", "Added automatically because a cast member with an identity LoRA is in this scene.");

// ---------- Assets ----------
tip("assets.filter", "Show all assets, or only pictures, videos or audio.");
// [OLD 2026-11-06 v0.8.0->v0.9.0] tip("assets.search", "Filter by code, name, category or file name.");
tip("assets.search", "Filter by code, name, category, file name, group or tag. Several words must all match."); // added 2026-11-06 v0.9.0: group and tags
tip("assets.upload", "Upload images, videos or audio. Files are stored in input/reelwright/<project>/.");
// added 2026-11-02 v0.2.0: ComfyUI file browser and vision descriptions
more("assets.browse", "Files already in ComfyUI", "Pick pictures, videos or audio that are already in ComfyUI's input folder (files you imported before) or output folder (files ComfyUI generated), without uploading them again.\n\nInput files are used where they are. Output files are hard-linked (or copied when linking is not possible) into input/reelwright/<project>/from_output/, because H3 reads references from the input folder.", "Add files from ComfyUI's input or output folders.");
tip("assets.browse.root", "Input: files you imported into ComfyUI. Output: files ComfyUI generated.");
tip("assets.browse.kind", "Show only pictures, videos or audio.");
tip("assets.browse.search", "Filter by any part of the path; every word must match. Newest files are listed first.");
tip("assets.browse.tile", "Click to select; click again to unselect. Then press Add.");
tip("assets.browse.used", "Already an asset in this project.");
tip("assets.browse.clear", "Unselect everything.");
tip("assets.browse.add", "Add the selected files as assets.");
/* [OLD 2026-11-02 v0.3.3->v0.3.4] did not say that every scene and character picks it up
more("assets.description", "Description", "A short visual description of what this asset shows. When the asset is used as a reference, it becomes its subject line, e.g. \"<Subject 2> is the wooden pier at dusk, shown in <Picture 3>.\" Without it the line is generic, which H3's guide warns against.\n\nWrite it yourself, or ask a vision LLM below.", "Visual description used in subject_definitions.");
*/
more("assets.description", "Description", "A short visual description of what this asset shows. When the asset is used as a reference, it becomes its subject line, e.g. \"<Subject 2> is the wooden pier at dusk, shown in <Picture 3>.\" Without it the line is generic, which H3's guide warns against.\n\nThe description is stored once, on the asset. Every scene builds its prompt from it each time, so an edit here reaches all scenes at once (and marks their takes stale). A character with no description of its own uses the description of its first described anchor picture.\n\nWrite it yourself, or ask a vision LLM below.", "Visual description used in every scene that uses this asset.");
tip("assets.description.uses", "Where this description goes right now: scene prompts, and characters that use this picture as an anchor.");
tip("assets.description.scene", "Open this scene.");
tip("assets.description.cast", "Open this character in the Cast tab.");
more("assets.describe", "Describe with LLM", "Sends this picture (or three frames of this video) to the LLM set on the Global tab with your question, for example \"describe the person on the left of this picture\" or \"describe the couch\". The model must accept images (a vision model).\n\nThe answer appears as a suggestion: Use replaces the description, Append adds to it, Dismiss throws it away.", "Ask a vision LLM to describe this asset.");
tip("assets.describe.prompt", "What to ask about this asset. Empty uses the grey example. Enter sends it.");
tip("assets.describe.result", "The model's answer. Nothing changes until you press Use or Append.");
tip("assets.describe.use", "Replace the description with this answer.");
tip("assets.describe.append", "Add this answer to the end of the description.");
tip("assets.drop", "Drop files here to upload them.");
for (const [k, t] of Object.entries({
  image: ["Pictures", "Identity, locations, props, styles and keyframes. Up to 9 picture references per pass, plus any number of guide frames (first, last, keyframes). 'match' resizes references to the output area; 'max' keeps up to 2048 px for better identity at a speed cost (Global → Output)."],
  video: ["Videos", "Reference clips for motion, camera movement or as a source to edit. Up to 3 per pass, each 2–15 s and 15 s in total; H3 reads them at 24 fps and crops them to 17k+5 frames. A video's own soundtrack can be sent too."],
  audio: ["Audio", "Voices, ambience, music and sound effects. Up to 3 per pass, each 2–15 s and 15 s in total. Retention says whether the audio is copied (fully_copy, partially_copy) or only guides the sound (reference, weak_reference)."],
})) more("assets.kind." + k, t[0], t[1], t[0] + " in this project.");
// [OLD 2026-11-06 v0.8.0->v0.9.0] tip("assets.card", "Select to edit its defaults. Drag onto a scene on the Timeline to use it.");
tip("assets.card", "Select to edit its settings. Drag it onto a group to move it there; right-click to move it to a group or add it to the current scene."); // added 2026-11-06 v0.9.0: no asset bin; groups
more("assets.inspector", "Asset", "Name, code and category of the selected asset. The code (P1, V1, A1) is how you refer to it in prompts: @P1.", "The selected asset.");
tip("assets.code", "Short code used in prompts as @code. Picture codes start with P, videos with V, audio with A.");
tip("assets.name", "A readable name, used in lists and generated prompts.");
tip("assets.file", "Path inside ComfyUI's input folder.");
tip("assets.category", "What the asset is for. Categories help the prompt builder: edit_source videos make the scene a video edit, voice audio pairs with a speaker.");
more("assets.defaults", "Defaults", "How this asset is used unless a scene says otherwise: its role, retention label, features to keep and, for videos, whether the soundtrack is sent. Changing a default updates every scene that did not override it.", "Defaults every scene starts from.");
tip("assets.defaults.role", "Default role when the asset is added to a scene.");
tip("assets.defaults.retention", "Default retention label.");
tip("assets.defaults.keep", "Default features to keep. Press Enter to add one.");
tip("assets.defaults.soundtrack", "Send this video's audio along with it by default.");
tip("assets.notes", "Notes for yourself.");
more("assets.usage", "Usage", "Every scene that uses this asset, with the role and retention used there. A coral dot means the scene overrides the asset's defaults.", "Scenes that use this asset.");
tip("assets.usage.row", "Open this scene.");
tip("assets.usage.cast", "This asset is an anchor or voice of a cast member, so it is sent to every scene they appear in. Click to open them in the Cast tab.");
tip("assets.addToScene", "Add this asset to the selected scene with its defaults.");
tip("assets.pushDefaults", "Clear every scene's overrides for this asset so they all follow its defaults.");
tip("assets.delete", "Remove the asset from the project and from every scene, anchor and voice that uses it. The file stays on disk.");
more("assets.budget", "Reference budget per scene", "References per scene against H3's limits per pass: 9 pictures, 3 videos (15 s), 3 audio (15 s), 12 files. Going over is allowed (H3 still runs) but quality and identity may suffer, so the table marks those scenes.", "Reference slots used by every scene.");
tip("assets.budget.row", "Open this scene.");
tip("assets.budget.warn", "This scene goes over an H3 reference limit.");
more("assets.camera", "Camera presets", "Named camera moves. Picking one in a shot writes its wording into that shot's line. H3 has no camera parameter: camera is either described in words or given as a reference video, which uses a video slot.", "Reusable camera wording.");
tip("assets.camera.add", "Add a camera preset.");
tip("assets.camera.name", "Preset name shown in pickers.");
tip("assets.camera.text", "The exact wording written into the shot line.");
tip("assets.camera.remove", "Delete this preset.");

// ---------- Cast ----------
// [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are per clip now: more("cast.bible", "Story bible", "Characters, locations and props that recur. Tag one in a scene and its anchors, description, outfit, voice and identity LoRA are added to that scene automatically.\n\nSpeaker IDs (S1, S2 …) are unique per character and stay the same in every scene.", "Recurring characters, locations and props.");
more("cast.bible", "Story bible", "Characters, locations and props that recur. Tag one in a scene and its anchors, description, outfit, voice and identity LoRA are added to that scene automatically.\n\nIdentity stays the same through the anchors, description and voice sample; speaker IDs (S1, S2 …) are numbered per clip in speaking order.", "Recurring characters, locations and props.");
tip("cast.item", "Edit this entry.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are per clip now: tip("cast.add.character", "Add a character. It gets the next free speaker ID.");
tip("cast.add.character", "Add a character.");
tip("cast.add.location", "Add a recurring location.");
tip("cast.add.prop", "Add a recurring prop.");
// [OLD 2026-11-03 v0.4.0->v0.4.1] more("cast.anchors", "Anchors", "Pictures that define this subject: ideally front, three-quarter, profile and full body. They are sent to every scene the subject is in, so identity never depends on earlier renders.\n\nPack into one sheet combines the anchors into a single 2×2 or 3×3 image, which uses one of H3's 9 picture slots instead of several.", "Pictures that define this subject.");
more("cast.anchors", "Anchors", "Pictures that define this subject: ideally front, three-quarter, profile and full body. They are sent to every scene the subject is in, so identity never depends on earlier renders.\n\nSeveral anchors can be sent as one sheet: a grid of all of them (3 columns for 5-9 pictures, 4 for 10-16, and so on) that uses one of H3's 9 picture slots. H3 scales every reference picture to about the output's pixel count, so in a sheet each anchor gets only a share of it: the more anchors, the smaller each one arrives. Auto sends them separately while a scene's pictures fit in 9 slots and packs them only when they don't.", "Pictures that define this subject.");
tip("cast.anchors.add", "Add an uploaded picture as an anchor.");
// added 2026-11-12 v0.16.0: video anchors
more("cast.videoAnchors", "Video anchors", "Clips of this cast member that go to H3 with its pictures, as part of its subject: \"<Subject 1> is Mara, …, shown in <Picture 1> and in <Video 2>\". A clip shows how it moves, talks and looks from every side, which a picture cannot.\n\nThey go to every pass of every scene it is in, after the scene's own video references and the clip a scene continues from, while H3's budget has room: 3 videos, 15 s of video in all, 12 files. A clip is shortened to the seconds left when 2 s or more are; otherwise it is left out, and the issues list says so. The first ones in the list go first: drag the grips to choose.\n\nKeep them short (2–15 s, a few seconds is plenty), with the face and body clearly in view. A part of a character (Part of) sends its pictures with the character, not its video anchors.", "Clips that show this cast member to H3.");
more("cast.videoAnchors.add", "Add a video anchor", "Pick a video asset. It is added with its first 15 s; set From / To to the part that shows this cast member best. The same video can be added several times with different parts.", "Add a clip as an anchor.");
more("cast.videoAnchors.from", "From", "Where the clip starts in the video. Type seconds (4.5), frames (108f) or a time (0:04.5).", "Where the clip starts.");
more("cast.videoAnchors.to", "To", "Where the clip ends in the video; empty = the end of the video (only the first 15 s are sent). Type seconds, frames (108f) or a time.", "Where the clip ends.");
more("cast.videoAnchors.length", "Clip length", "How long the clip is that goes to H3: up to 15 s, and shorter when a pass has less of its 15 s of video left. H3 video references are 2–15 s.", "Length of the clip sent.");
more("cast.videoAnchors.sound", "With sound", "Also send the clip's sound, as the voice of this cast member (\"the voice timbre and delivery of <Subject 1> follow the sound of <Video 2>\"). Off by default: the clip then shows only how it looks and moves, and the voice comes from its voice sample.\n\nThe sound takes one of H3's 3 audio slots (and counts toward its 15 s of audio); when none is free the clip goes without it.", "Send the clip's sound as the voice.");
more("cast.videoAnchors.order", "Reorder", "Drag the grip up or down to put this video anchor elsewhere; ↑ / ↓ on the grip move it one place. The first ones go to H3 first when there is room for only some. Each move is one undo step.", "Drag to reorder.");
tip("cast.videoAnchors.remove", "Remove this video anchor (the asset stays in the project).");
// added 2026-11-12 v0.16.0
more("cast.anchors.small", "Sheet too small", "Packed into one sheet, each anchor reaches H3 at under 300 px at the output size, too small for a reliable identity. H3 scales the whole sheet to the output's pixel area (or to a 2048 px short edge with Reference images: max), so the more pictures in the sheet, the smaller each one.\n\nKeep a sheet to about 4 pictures (a clear face and a full body), pick Separate (each picture its own slot, up to 9 in all) or Auto, or set Global → Output → Reference images to max.", "Each picture of the sheet is too small for identity.");
tip("cast.anchors.remove", "Remove this anchor (the asset stays in the project).");
// [OLD 2026-11-03 v0.4.0->v0.4.1] tip("cast.anchors.sheet", "Combine the anchors into one grid image so they use a single picture slot.");
tip("cast.anchors.sheet", "How the anchors are sent: separately, or combined into one grid image that uses a single picture slot.");
tip("cast.anchors.sheet.auto", "Separate pictures while the scene fits in H3's 9 picture slots; one sheet in a scene that would not. Each anchor arrives larger when sent separately.");
tip("cast.anchors.sheet.on", "Always one grid image (any number of anchors). Saves picture slots; each anchor arrives smaller.");
tip("cast.anchors.sheet.off", "Always separate pictures, one slot each.");
tip("cast.anchors.size", "About how many pixels each anchor has when H3 sees it, at the final and the draft output size.");
tip("scene.cast.sheet", "This scene sends the character's anchors as one sheet (shown here as built).");
tip("cast.anchors.sheetPreview", "The sheet exactly as the renderer builds it. Click to open it full size.");
tip("cast.promote", "Turn the first or last frame of a scene's starred take into a new anchor, for example a good angle H3 produced.");
tip("cast.promote.scene", "Scene whose starred take provides the frame.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are per clip now: more("cast.profile", "Profile", "Name, speaker ID, description, voice, language and identity LoRA. The description is written into the subject definitions of every scene this entry is in.", "Details of this entry.");
more("cast.profile", "Profile", "Name, description, voice, language and identity LoRA. The description is written into the subject definitions of every scene this entry is in; Describe from anchors can draft it with a vision LLM.", "Details of this entry.");
tip("cast.name", "Name; in prompts write @Name, or @{Two Words} when it has spaces.");
// [OLD 2026-11-08 v0.10.3->v0.11.0] tip("cast.kind", "Character, location or prop.");
// added 2026-11-08 v0.11.0: a prop can be part of a character
tip("cast.kind", "Character, location or prop. A prop is a thing of its own in the shot, unless it is part of a character (Part of).");
more("cast.partOf", "Part of", "Pick the character this prop belongs to when it is part of their body or look: a beer belly, a tattoo, a scar, a prosthetic arm. In scenes where both are in the cast, its pictures and description go into the character's subject (\"<Subject 1> is Mara, …, with Beer belly (a big round beer belly) shown in <Picture 3>\"), and @{Beer belly} in a shot is written as \"<Subject 1>'s Beer belly\".\n\nNobody: the prop is a subject of its own, which H3 puts in the shot as a separate thing (a cup, a car). A prop of its own showing a body part becomes a second person.\n\nA part in a scene without its character is left out (the Issues list says so). When a part changes the body, give the character an outfit with retention partially_preserved keeping face and hair, so the anchors' body does not win.", "The character whose body or look this prop is part of.");
tip("cast.parts", "Props that are part of this character. Click one to open it.");
// added 2026-11-12 v0.13.0: Chat tab
more("tab.chat", "Chat", "Ask the LLM set in Global → Prompt rewriter general questions. The tab shows while an LLM base URL is set (this project's, or the one stored on the server).\n\nNothing from this project is sent: only your questions and the answers so far, with a short note that you are in Reelwright. The answer appears as it is written; Stop ends it and keeps what came. The conversation stays in this editor until you clear it or reload ComfyUI.\n\nIt uses the same model, Max tokens, Thinking and Limits as the rewriter (Global → Prompt rewriter).", "Ask the LLM general questions.");
tip("chat.log", "The conversation. Select text to copy it, or use the copy button under an answer.");
tip("chat.live", "The answer as the LLM writes it.");
tip("chat.input", "Your question. Enter sends it, Shift+Enter starts a new line.");
tip("chat.send", "Send the question (Enter).");
tip("chat.stop", "Stop the answer; what came so far is kept.");
tip("chat.clear", "Start a new conversation (the LLM forgets this one).");
tip("chat.copy", "Copy this answer as text.");
tip("chat.retry", "Ask the question again.");
tip("chat.model", "The model and server the questions go to (Global → Prompt rewriter).");
// added 2026-11-12 v0.13.0: the monitor full screen
more("timeline.fullscreen", "Full screen", "Show the monitor full screen: the takes, captions and badges as in the panel, with a bar for play/pause, the time, the scene and exit.\n\nThis button, a double-click on the monitor, or F switches it on. In full screen, click the picture or press Space to play or pause, ← / → to step, and Esc (or the × button) to come back.", "Show the monitor full screen (F, or double-click it).");
tip("timeline.fullscreen.play", "Play or pause (Space, or click the picture).");
tip("timeline.fullscreen.exit", "Leave full screen (Esc).");
tip("scene.cast.part", "This prop is part of a character: its pictures and description go into that character's subject. Without the character in the scene it is left out.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] speaker field removed from the UI: tip("cast.speaker", "Speaker ID used in dialogue: <Subject n> (S1). Keep it stable.");
tip("cast.speaker", "Older projects stored a fixed speaker ID here. H3's guide numbers speakers by speaking order in each clip, so the prompt builder now assigns S1, S2… itself.");
// [OLD 2026-11-02 v0.3.3->v0.3.4] tip("cast.description", "Short visual description written into every scene's subject definitions.");
tip("cast.description", "Short visual description written into every scene's subject definitions. Leave it empty to use the description of the first anchor picture that has one (Assets tab).");
tip("cast.description.fromAnchor", "This character has no description of its own, so its subject line uses this anchor picture's description. Edit it in the Assets tab, or type a description here to override it.");
// added 2026-11-02 v0.2.0
more("cast.describe", "Describe from anchors", "Sends up to four anchor pictures to the LLM set on the Global tab and asks your question, for example \"describe the person on the left\" or \"describe only the coat\". The model must accept images (a vision model).\n\nThe answer appears as a suggestion: Use replaces the description, Append adds to it, Dismiss throws it away. Nothing is sent during a render.", "Ask a vision LLM to describe this entry from its anchor pictures.");
tip("cast.describe.prompt", "What to ask about the anchor pictures. Empty uses the grey example. Enter sends it.");
tip("cast.describe.result", "The model's answer. Nothing changes until you press Use or Append.");
tip("cast.describe.use", "Replace the description with this answer.");
tip("cast.describe.append", "Add this answer to the end of the description.");
tip("cast.voice", "Voice sample, sent as an audio reference in scenes where this character speaks.");
// added 2026-11-06 v0.10.0: voices that stay the same from pass to pass
more("cast.voiceFromTake", "Voice from a take", "Cuts this character's spoken lines out of a starred take (up to 15 s, the lines found by listening to the take), saves them as a voice sample in the project's input folder and sets it as this character's Voice. Every later pass and scene then gets the same voice as an audio reference.\n\nPick a take whose voice you like. The sample also carries that take's background sound, so a quiet take works best. Undo puts the old voice back; the audio asset stays in the Assets tab.", "Make a voice sample from this character's lines in a rendered take.");
more("cast.voiceDesc", "Voice description", "How this character sounds, for example \"a deep, warm male voice, slow and measured\": gender, age, pitch, timbre and pace. H3's guide asks for this when a speaker first appears; Reelwright writes it at the character's first line in every pass, because each pass is a separate render and H3 does not remember the voice it chose before.\n\nScript import fills it in when the LLM gives one. Leave it empty to write nothing. Describe voices (Continuity rules, below) switches it off for the whole project.", "How this character sounds, written at their first line in every pass.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] free-text language: tip("cast.language", "Default language for this character's new lines.");
tip("cast.language", "Default language for this character's new lines. Pick one of H3's stable languages or type another.");
tip("cast.lora", "Identity LoRA, added automatically to every scene this entry appears in.");
tip("cast.lora.strength", "Strength of the identity LoRA.");
tip("cast.export", "Copy the anchors and starred frames of this entry into a folder ready for ai-toolkit LoRA training.");
tip("cast.delete", "Delete this entry and remove it from every scene.");
// [OLD 2026-11-08 v0.10.3->v0.11.0] more("cast.outfits", "Outfits", "Looks this character wears. Each outfit has its own retention (for example partially_preserved keeping face and hair) so the face stays while the clothes change. Pick the outfit per scene in the Scene tab.", "Different looks for this entry.");
// added 2026-11-08 v0.11.0: outfit pictures; looks other than clothes
more("cast.outfits", "Outfits", "Looks this character wears: other clothes, a beard, a belly. Pick the outfit per scene in the Scene tab.\n\nEach outfit has its own retention (for example partially_preserved keeping face and hair) so the face stays while the look changes, and can have pictures of its own: they are sent with the anchors in the scenes that pick it, as the same subject.\n\nThe name goes into the subject line as \"wearing <name>\"; a name that starts with with, in, without, wearing, holding or carrying is written as it is (\"with a big beer belly\"). An outfit named Default adds nothing.", "Different looks of this character, each with its own retention and pictures.");
tip("cast.outfits.add", "Add an outfit or variant.");
tip("cast.outfits.default", "Default outfit for new scenes.");
// [OLD 2026-11-08 v0.10.3->v0.11.0] tip("cast.outfits.name", "Outfit name.");
tip("cast.outfits.name", "Outfit name. Written as \"wearing <name>\", or as it is when it starts with with, in, without, wearing, holding or carrying.");  // added 2026-11-08 v0.11.0
tip("cast.outfits.pictures", "Pictures of this look, sent with the anchors in the scenes that pick it.");
tip("cast.outfits.pictureAdd", "Add a picture of this look.");
tip("cast.outfits.pictureRemove", "Remove this picture from the outfit (the asset stays in the project).");
tip("cast.outfits.retention", "How strictly the anchors are followed with this outfit.");
tip("cast.outfits.keep", "Features to keep with this outfit (face, hair …). Press Enter to add.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("cast.outfits.remove", "Delete this outfit.");  (scenes that wore it are changed too)
tip("cast.outfits.remove", "Delete this outfit. Scenes that wore it use the default outfit. Ctrl+Z undoes this.");
more("cast.appearances", "Appearances", "Every scene this entry is in. With the insightface package installed, Reelwright compares faces in each take against the anchors and shows a similarity score; scores under the threshold are marked as drift.", "Scenes this entry appears in, with face-match scores.");
tip("cast.appearances.open", "Open this scene.");
tip("cast.appearances.score", "Face similarity to the anchors (0–1). Below the threshold counts as drift.");
tip("cast.appearances.check", "Run the face check on this scene's starred take now.");
tip("cast.appearances.retake", "Queue a new take of this scene with a new seed.");
more("cast.rules", "Continuity rules", "Chaining scene to scene (each new scene copying the last frame of the one before) slowly drifts: small changes add up. Reelwright sends the same anchors to every scene instead, so scene 10 has exactly the same identity input as scene 2.\n\nContinuations still carry motion and light from one scene to the next. Re-anchor after N stops identity from being taken from frames after N chained scenes.", "Rules that keep subjects consistent.");
tip("cast.rules.anchors", "Chained identity drifts; anchored identity stays the same.");
tip("cast.rules.reanchor", "After this many chained continuations, the next scene takes identity only from the anchors (0 = always).");
tip("cast.rules.faceCheck", "Check face similarity after every render (needs the insightface package).");
tip("cast.rules.threshold", "Similarity below this counts as drift.");
tip("cast.rules.onDrift", "Flag the scene, or re-render it with a new seed (up to 2 extra takes).");
tip("cast.rules.vae", "Scenes pass frames and clips to each other as pixels, so per-scene VAEs cannot corrupt a subject.");
// added 2026-11-05 v0.7.0
tip("cast.rules.nameContinuation", "On: a continuing scene sends the previous scene's last frame as <Picture 1> (or its tail clip as <Video 1>) and the prompt says the scene starts from it. Off: the frame or clip only guides the start, as before v0.7.0.");
// added 2026-11-06 v0.10.0
tip("cast.rules.describeVoices", "On: each character's voice description is written at their first line in every pass, so H3 keeps the voice from pass to pass. Off: no voice descriptions in the prompts (a voice sample still goes as an audio reference).");

// ---------- Render ----------
tip("render.scope.pending", "Render every scene that is new or stale; reuse everything else.");
tip("render.scope.selected", "Render the selected scene now.");
tip("render.scope.from", "Render the scene under the playhead and every scene after it.");
tip("render.scope.all", "Re-render every scene, ignoring takes on disk.");
tip("render.scope.take", "Render another take of the selected scene with a new seed.");
tip("render.quality", "Draft renders smaller and faster with the same seeds; Final renders at full quality. Takes remember their quality.");
tip("render.quality.draft", "Fast preview: scaled resolution, fewer steps and the optional turbo LoRA (Global → Draft).");
tip("render.quality.final", "Full resolution and steps.");
tip("render.stop", "Interrupt the current ComfyUI run. Finished scenes stay on disk.");
// [OLD 2026-11-02 v0.2.2->v0.3.0] the banner now shows scene k of n and two progress bars
// tip("render.banner", "What is rendering right now.");
tip("render.banner", "What is rendering right now: which scene of the run, its pass and sampling step. The node title shows the same count and the overall percentage.");
// [OLD 2026-11-02 v0.3.7->v0.3.8] previews were throttled to one a second
// tip("render.preview", "Latent preview of the scene being sampled, about once a second. ComfyUI's preview setting decides its quality (Latent2RGB or TAESD) or turns it off.");
// [OLD 2026-11-12 v0.14.4->v0.15.0] tip("render.preview", "Latent preview of the scene being sampled, updated every sampler step. ComfyUI's preview setting decides its quality (Latent2RGB or TAESD) or turns it off. If a preview can't be decoded, the last good one stays.");
// added 2026-11-12 v0.15.0: the frame shown is the middle of the part the pass makes (the first frame is fixed by continuation and guides)
tip("render.preview", "Latent preview of the scene being sampled, updated every sampler step. It shows a frame from the middle of the part this pass generates (the first frames repeat the previous pass or a guide picture, so they barely change). ComfyUI's preview setting decides its quality (Latent2RGB or TAESD) or turns it off. If a preview can't be decoded, the last good one stays.");
tip("render.progress.scene", "Progress of the scene being rendered, across all of its passes.");
tip("render.progress.total", "Progress of the whole run. Scenes reused from disk are not counted.");
tip("render.refresh", "Reload takes and statuses from disk.");
// added 2026-11-02 v0.2.0
tip("render.table.file", "The rendered video the merge will use for this scene (starred take, or the newest when Merge uses latest takes). Click to open it.");
tip("render.take.file", "File name of this take in ComfyUI's output folder.");
tip("render.lastCut", "Open the last merged film.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] file column and merge button: more("render.table", "Scenes and takes", "Every render is kept as a take. The starred take is the one used for playback, continuation and merging. Click Takes to open the list, star another take, compare two with A and B, or delete one.\n\nThe cache key is a hash of everything that affects a scene's pixels, including the take it continues from.", "Every scene, its status and its takes.");
more("render.table", "Scenes and takes", "Every render is kept as a take. The starred take is the one used for playback, continuation and merging. Click Takes to open the list, star another take, compare two with A and B, or delete one.\n\nFile is the video of the take the merge will use, named project_scene#_title_take.mp4 in ComfyUI's output folder; click it to open. Merge joins those files using the settings in the Merge scenes card.\n\nThe cache key is a hash of everything that affects a scene's pixels, including the take it continues from.", "Every scene, its status, file and takes.");
tip("render.table.scene", "Select this scene.");
tip("render.table.takes", "Show this scene's takes. The starred one is used everywhere.");
tip("render.table.passes", "How many H3 passes this scene needs.");
tip("render.cacheKey", "Hash of model, LoRAs, VAEs, resolution, frames, steps, sampler, seed, quality, final prompt, reference file contents and the upstream take. Same key = reused.");
tip("render.take.star", "Use this take for playback, continuation and merging.");
tip("render.take.compareA", "Put this take on the left of the A/B compare.");
tip("render.take.compareB", "Put this take on the right of the A/B compare.");
tip("render.take.open", "Open the video file in a new browser tab.");
tip("render.take.delete", "Delete this take from disk.");
more("render.compare", "A/B compare", "Two takes side by side. Play both starts them together so you can compare motion and timing.", "Compare two takes.");
tip("render.compare.play", "Restart and play both takes together.");
more("render.chains", "What re-renders", "Scenes that continue from the previous one (last frame → or tail clip ⇢) form a chain. Changing a scene makes it stale, and every scene chained after it too, because they start from its pixels. Scenes after a fresh start are independent.", "Which scenes depend on which.");
tip("render.chains.chip", "Select this scene. Amber means stale.");
more("render.memory", "Memory", "Each scene is written to MP4 when it finishes and its frames are released, so a long film never has to sit in memory.\n\nFree cache keeps the models loaded but clears memory between scenes; Unload everything reloads the models for every scene (slow, but uses the least VRAM). Encoding all prompts first lets the 27 GB text encoder unload before sampling starts. Grouping lets scenes with the same LoRAs run back to back, as long as they do not depend on each other.", "Memory policy between scenes.");
tip("render.memory.policy", "What to free between scenes.");
tip("render.memory.keep", "Keep everything loaded: fastest, most VRAM.");
tip("render.memory.free_cache", "Keep models loaded, free caches and intermediate tensors between scenes.");
tip("render.memory.unload_all", "Unload all models between scenes: least VRAM, slowest.");
tip("render.memory.encodeFirst", "Run the text encoder for every pending pass first, then unload it before sampling.");
tip("render.memory.group", "Render independent scenes with the same LoRA stack back to back to avoid re-patching weights.");
more("render.seam", "Seam inspector", "The last frame of one scene next to the first frame of the next, side by side or blended. Use it to spot jumps in colour, framing or identity at a cut.", "Check the join between two scenes.");
tip("render.seam.pick", "Which pair of scenes to inspect.");
tip("render.seam.mode", "Side by side, or one frame over the other.");
tip("render.seam.mix", "Opacity of the second frame in onion-skin mode.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] more("render.merge", "Merge scenes", "Joins one take of every scene into a single film. Nothing is re-rendered, so it takes seconds and you can merge again whenever a scene changes.\n\nContinuation seams trim the overlap and crossfade inside it; hard cuts use the transition you choose. Audio gets a short fade at every seam and can be loudness-normalised. A score track can run under the whole film and duck under dialogue. Extras: subtitles from dialogue, a chapter per scene, OpenTimelineIO and FCPXML timelines for Resolve or Premiere, and a project bundle.", "Join the rendered scenes into one film.");  (the score is a soundtrack track now; draft, range, stems and Stop)
// [OLD 2026-11-05 v0.6.1->v0.7.0] more("render.merge", "Merge scenes", "Joins one take of every scene into a single film. Nothing is re-rendered, so it takes seconds and you can merge again whenever a scene changes.\n\nContinuation seams trim the overlap and crossfade inside it; hard cuts use the transition you choose. Audio gets a short fade at every seam and can be loudness-normalised. Soundtrack tracks (Timeline tab) play under the film. Extras: subtitles from dialogue, a chapter per scene, OpenTimelineIO and FCPXML timelines for Resolve or Premiere, and a project bundle.\n\nThis merge: a draft (half size, fast) to check timing, only a range of scenes, and audio stems with a loudness report. One merge of a project runs at a time; Stop ends it and removes its files.", "Join the rendered scenes into one film.");
// added 2026-11-05 v0.7.0: joins, fades and colour are per scene
more("render.merge", "Merge scenes", "Joins one take of every scene into a single film. Nothing is re-rendered, so it takes seconds and you can merge again whenever a scene changes.\n\nContinuation seams trim the overlap and crossfade inside it; fresh starts use each scene's own join, fades, sound level and colour match (Scene tab → In the cut). The film's audio can be loudness-normalised. Soundtrack tracks (Timeline tab) play under the film. Extras: subtitles from dialogue, a chapter per scene, OpenTimelineIO and FCPXML timelines for Resolve or Premiere, and a project bundle.\n\nThis merge: a draft (half size, fast) to check timing, only a range of scenes, and audio stems with a loudness report. One merge of a project runs at a time; Stop ends it and removes its files.", "Join the rendered scenes into one film.");
tip("render.merge.use", "Use each scene's starred take, or its newest take.");
tip("render.merge.missing", "What to do with scenes that have no take: skip them, insert a title slate of the same length, or refuse to merge.");
/* [OLD 2026-11-02 v0.2.2->v0.3.0] these are now defaults that each scene can override
tip("render.merge.hardCut", "Transition at fresh-start seams: plain cut, crossfade or dip to black.");
tip("render.merge.transition", "Length of crossfades and dips, in frames at 24 fps.");
tip("render.merge.audioFade", "Short audio fade at every seam, in frames, to avoid clicks.");
*/
tip("render.merge.hardCut", "Default transition at fresh-start seams: plain cut, crossfade or dip to black. A scene can choose its own on the Scene tab (Starts from → Cut into this scene).");
tip("render.merge.transition", "Default length of crossfades and dips, in frames at 24 fps. Scenes can override it.");
tip("render.merge.audioFade", "Default audio fade at every seam, in frames, to avoid clicks. Scenes that start fresh can override it.");
tip("render.merge.overrides", "How many scenes set their own transition, length or audio fade. Those scenes ignore the defaults above.");
// [OLD 2026-11-03 v0.4.3->v0.5.0] tip("render.merge.normalize", "Normalise loudness of the whole film (EBU R128).");
tip("render.merge.normalize", "Normalise loudness of the whole film (EBU R128). With a soundtrack in the cut only the scenes' own sound is normalised; the soundtrack plays as it is.");
tip("render.merge.loudness", "Target integrated loudness. −16 LUFS suits online video; −23 broadcast.");
tip("render.merge.score", "Optional music asset that plays under the whole film. Useful because each H3 pass makes its own music.");
tip("render.merge.scoreVolume", "Level of the score track.");
tip("render.merge.duck", "Lower the score while scenes have sound or speech.");
tip("render.merge.color", "Match each scene's average colour to a reference scene, to smooth jumps between passes or VAEs.");
tip("render.merge.colorRef", "Scene the others are matched to.");
// added 2026-11-05 v0.7.0: the cut settings moved to each scene
tip("render.merge.perScene", "Transitions, fades, each scene's sound level and colour matching are set per scene, on the Scene tab's In the cut card.");
tip("render.merge.perSceneOpen", "Open the selected scene's In the cut card.");
tip("render.merge.codec", "Video codec of the merged file.");
tip("render.merge.crf", "Quality: lower is better and larger. 16–20 is visually lossless for H.264.");
// [OLD 2026-11-06 v0.9.0->v0.10.0] subtitles now follow the speech found in each take
// tip("render.merge.subtitles", "Write an .srt file from the dialogue lines, timed to the final cut.");
// [/OLD]
// added 2026-11-06 v0.10.0: subtitles follow the speech
tip("render.merge.subtitles", "Write an .srt file from the dialogue lines, timed to the final cut. Subtitle times decides whether each line follows the speech heard in the take or keeps its planned time.");
more("render.merge.subtitleTiming", "Subtitle times", "H3 is told when each shot starts, but not when each line is spoken inside a shot, so a line is often heard a little earlier or later than its time on the timeline.\n\nFollow the speech: the merge listens to each take, finds where speech starts and stops, and moves every line (in its order) to the nearest start of speech within 4 seconds; a subtitle stays up while that speech goes on. A line with no speech near it keeps its planned time. The Timeline monitor's captions use the same timing.\n\nPlanned times: every line starts at its time on the timeline and stays up for its length, as before v0.10.0.", "Time subtitles to the speech heard in each take, or to the planned times.");
tip("render.merge.chapters", "Add one chapter per scene to the MP4.");
tip("render.merge.otio", "Write an OpenTimelineIO timeline that references the scene files.");
tip("render.merge.fcpxml", "Write an FCPXML timeline for Final Cut, Resolve or Premiere.");
tip("render.merge.bundle", "Zip the project file, the cut and the extras together.");
tip("render.merge.auto", "Merge automatically at the end of every render run, so the node's video output is always the full film.");
tip("render.merge.ready", "Which scenes have a take to merge (green) and which do not (dashed).");
tip("render.merge.run", "Merge now. The file appears in output/reelwright/<project>/cuts/.");
tip("render.merge.file", "Open this file.");
more("render.versions", "Autosaved versions", "The project is autosaved to disk while you edit, with a version kept every few minutes. Restoring a version replaces the current project; Ctrl+Z brings back what you had.", "Earlier versions of the project.");
tip("render.versions.load", "Load the list of saved versions.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("render.versions.restore", "Replace the current project with this version.");  (Restore shows a diff first; new text below)
// added 2026-11-02 v0.3.6
tip("render.versions.delete", "Delete this version file. It cannot be undone; the project itself is not affected.");
tip("render.versions.deleteAll", "Delete every autosaved version of this project. The project and its latest autosave stay.");
// added 2026-11-03 v0.6.0 (F2b): Render tab additions
tip("render.versions.restore", "Show what this version changes, then replace the current project with it. Ctrl+Z brings back what you had.");
tip("render.versions.diff", "What restoring changes, read as now → this version: scenes it brings back or removes, lengths, prompt text and Global settings.");
tip("render.estimate", "About how long the pending scenes take, learned from earlier renders with the same quality and size. Scenes without such renders are not counted.");
more("render.variants", "Variants", "Renders several takes of the selected scene in one run, each with its own seed. With face check on, the take that matches the cast best is starred; otherwise the first new take is.\n\nWhen they are done, the scene's take list opens: put two takes into the A/B compare to choose, and star the one you like.", "Render several takes of the selected scene at once.");
tip("render.variants.n", "How many takes to render (2 to 8).");
more("render.lastRun", "Last render", "Scenes that failed or were skipped in the last render. A scene that continues from a failed one is skipped, because its start is missing. The other scenes rendered as usual.\n\nRender them again once the cause is fixed. Close this note to hide it.", "What went wrong in the last render.");
tip("render.lastRun.retry", "Render the failed and skipped scenes again.");
tip("render.table.failed", "This scene failed in the last render. Hover to see why.");
tip("render.table.skipped", "This scene was skipped in the last render: the scene it continues from failed or was skipped.");
tip("render.table.estimate", "About how long a new take of this scene takes, from earlier renders.");
tip("render.table.cachedPasses", "Passes of this scene kept in the pass cache. A render uses them and samples only the rest.");
tip("render.table.manualStar", "You starred this take by hand. Renders keep your choice.");
tip("render.table.diff", "Why is this scene stale? Shows how its prompt differs from the prompt of its starred take.");
tip("render.diff", "The prompt a render would send now (+) against the prompt of the starred take (−), pass by pass.");
more("render.table.upstream", "Continues from a different take", "This scene continues from the scene before it (last frame or tail clip). That scene now has another starred take than the one this scene's take started from, so the seam no longer matches.\n\nRe-render this scene, and the scenes that continue from it, so they start from the new take.", "The scene before has a new take; this one started from the old one.");
tip("render.table.upstream.rerender", "Render this scene again, and every scene that continues from it.");
tip("render.passRetake", "Long scenes are made of passes. A pass retake gives one pass a new seed and keeps the others.");
tip("render.passRetake.pass", "New seed for this pass only. Earlier passes come from the pass cache; later passes that continue from it render again.");
tip("render.take.compareNewest", "Put the two newest takes into the A/B compare.");
tip("render.merge.draft", "Full: the cut at full size. Draft: half size, encoded fast at lower quality, to check timing quickly.");
tip("render.merge.draft.full", "Full size and quality.");
tip("render.merge.draft.on", "Half size and fast encoding. The file name ends in _draft.");
tip("render.merge.range", "Merge every scene, or only the scenes from one to another.");
tip("render.merge.range.all", "Every scene.");
tip("render.merge.range.some", "Only the scenes from one scene to another. The file name says which.");
tip("render.merge.rangeFrom", "First scene of the range.");
tip("render.merge.rangeTo", "Last scene of the range.");
tip("render.merge.stems", "Also write the sound as separate WAV files (the scenes, each soundtrack track, the mix) and measure their loudness (EBU R128).");
tip("render.merge.stemsFolder", "Folder with the stems: scenes.wav, one track_<id>.wav per soundtrack track, and mix.wav.");
tip("render.merge.stop", "Stop the merge. Its files are removed.");
more("render.merge.report", "Loudness report", "Measured with EBU R128 on the merged sound.\n\nIntegrated: the average loudness of the whole film, in LUFS. Online video aims at about −16, broadcast at −23.\n\nRange: how much the loudness varies, in LU. Small for a steady mix, larger for dynamic films.\n\nTrue peak: the highest level between samples, in dBTP. Above −1 it may clip after conversion to MP3 or AAC.", "Loudness of the mix and each stem.");

// ---------- Global ----------
// added 2026-11-02 v0.3.0: saved Global settings
more("global.profiles", "Profiles", "A profile is a saved copy of this tab: models, LoRAs, output, sampling, draft, defaults, merge, memory and LLM settings (never the API key). Profiles are stored in ComfyUI's user folder (user/reelwright/profiles.json) and shared by every Reelwright node on this server.\n\nApply copies a profile into this project (you can undo it). Mark one as 'Use for new nodes' and every new Reelwright node starts with it; a banner on a new node also lets you pick a different one.", "Save and reuse Global settings.");
tip("global.profiles.pick", "Choose a saved profile.");
tip("global.profiles.apply", "Replace this project's Global settings with the chosen profile. Ctrl+Z undoes it.");
tip("global.profiles.update", "Overwrite the chosen profile with the current Global settings.");
tip("global.profiles.default", "New Reelwright nodes start with this profile.");
tip("global.profiles.delete", "Delete the chosen profile. Projects that used it keep their settings.");
tip("global.profiles.name", "Name for a new profile.");
tip("global.profiles.save", "Save the current Global settings as a new profile.");
tip("global.profiles.banner", "This node is new. Pick a saved profile to fill in the Global settings, or close this to keep the defaults.");
// [OLD 2026-11-06 v0.9.0->v0.10.0] more("global.project", "Project", "The project name, and the folder its renders and uploads go to. Changing the folder after rendering points the project at a new, empty render folder.", "Project name and folder.");
// added 2026-11-06 v0.10.0: export and import
// [OLD 2026-11-07 v0.10.2->v0.10.3] more("global.project", "Project", "The project name, and the folder its renders and uploads go to. Changing the folder after rendering points the project at a new, empty render folder.\n\nExport saves the whole project (scenes, cast, assets list, settings) as a .json file; Copy JSON puts the same text on the clipboard, for example to paste into a message. Import reads such a file or pasted JSON back and replaces the project in this node; Ctrl+Z brings the previous one back. Pictures, sounds and renders are files in ComfyUI's input and output folders: the JSON names them but does not contain them.", "Project name and folder; export and import the project as JSON.");
// added 2026-11-07 v0.10.3: New project
more("global.project", "Project", "The project name, and the folder its renders and uploads go to. Changing the folder after rendering points the project at a new, empty render folder.\n\nNew project replaces the project in this node with an empty one (one scene) in a new folder. Nothing is deleted: the current project stays in its folder, and Ctrl+Z brings it back.\n\nExport saves the whole project (scenes, cast, assets list, settings) as a .json file; Copy JSON puts the same text on the clipboard, for example to paste into a message. Import reads such a file or pasted JSON back and replaces the project in this node; Ctrl+Z brings the previous one back. Pictures, sounds and renders are files in ComfyUI's input and output folders: the JSON names them but does not contain them.", "Project name and folder; start a new project; export and import the project as JSON.");
// added 2026-11-07 v0.10.3: New project
more("global.project.new", "New project", "Start an empty project (one scene) in this node, in a new folder of its own (untitled-xxxx; it follows the name you give the project until something is rendered). You confirm first.\n\nNothing is deleted: the current project is saved to its folder first and stays there with its uploads and renders, and Ctrl+Z brings it back to this node. To keep a copy as a file as well, Export it first.\n\nThe new project keeps this project's Global settings (models, quality, LLM, merge), or takes them from your default profile. Cast, assets, scenes and the soundtrack start empty.", "Replace this project with an empty one in a new folder (Ctrl+Z brings it back).");
tip("global.project.new.keep", "Start the new project with this project's Global settings.");
tip("global.project.new.profile", "Start the new project with the Global settings of your default profile.");
tip("global.project.export", "Download the whole project as a .json file.");
tip("global.project.copy", "Copy the whole project as JSON to the clipboard.");
more("global.project.import", "Import a project", "Paste a project's JSON or choose a .json file (an Export, a saved version, or the project file of a bundle). You see what it holds and confirm before anything changes. The import replaces the project in this node, as one undo step.\n\nWhen its folder differs from this node's, choose which to use: keep this node's folder (its renders and files stay with the node) or use the imported folder (to pick up renders made for that project on this ComfyUI).", "Replace this project with one from a .json file or pasted JSON.");
tip("global.project.import.keep", "Use the imported project in this node's folder.");
tip("global.project.import.theirs", "Use the imported project with its own folder (its renders on this ComfyUI come with it).");
tip("global.project.importText", "Paste a project's JSON here.");
tip("global.project.importFile", "Choose a .json project file to import.");
tip("global.project.importPasted", "Import the JSON pasted above. You confirm first.");
tip("global.project.name", "Project name.");
tip("global.project.slug", "Folder name under output/reelwright/ and input/reelwright/. Letters, digits and underscores.");
more("global.models", "Models", "The models every scene uses unless it overrides them. H3 needs a diffusion model (ref2va), the Qwen3-VL text encoder (CLIP type minimax), a video VAE and an audio VAE. The latent upscaler is only for a hires pass.\n\nIf the node's model, clip, vae or audio_vae input is wired, that input wins over the file chosen here for the whole run.", "Diffusion model, text encoder and VAEs.");
tip("global.models.rescan", "Reload the model lists from ComfyUI's folders.");
tip("global.models.wired", "This node input is connected, so the wired model replaces this choice.");
tip("global.models.diffusion", "H3 ref2va diffusion model, from models/diffusion_models.");
tip("global.models.dtype", "Weight dtype when loading the diffusion model. fp8 halves VRAM at some quality cost.");
tip("global.models.textEncoder", "Qwen3-VL-32B text encoder for H3, from models/text_encoders. Loaded with CLIP type minimax.");
tip("global.models.clipDevice", "Run the text encoder on the GPU (default) or the CPU to save VRAM.");
tip("global.models.videoVae", "H3 video VAE, from models/vae.");
tip("global.models.audioVae", "H3 audio VAE, from models/vae.");
tip("global.models.upscaler", "H3 latent upscaler for a hires pass, from models/latent_upscale_models. Leave empty for none.");
more("global.loras", "Global LoRA stack", "LoRAs applied to every scene, in order. Scenes can add their own, change a strength or replace the stack entirely.", "LoRAs every scene uses.");
tip("global.loras.enabled", "Turn this LoRA on or off for every scene.");
tip("global.loras.name", "LoRA file from models/loras.");
tip("global.loras.strength", "Model strength.");
// [OLD 2026-11-12 v0.14.4->v0.15.0] tip("global.loras.order", "Move up in the stack.");  (a button moved it up)
// added 2026-11-12 v0.15.0: drag to reorder
more("global.loras.order", "Reorder", "Drag the grip up or down to put this LoRA elsewhere in the stack; ↑ / ↓ on the grip move it one place. Each move is one undo step.\n\nLoRAs load in this order, before each scene's own.", "Drag to reorder.");
tip("global.loras.remove", "Remove from the stack.");
tip("global.loras.add", "Add a LoRA to the stack.");
more("global.output", "Output", "H3 renders at about 1 megapixel with a 768-pixel short edge, capped at 768×1344 pixels of area, with both sides multiples of 32. The aspect presets use exactly the native H3 canvas rule. Frame rate (24 fps) and audio (32 kHz stereo) are fixed by the model.\n\nReference images: 'match' scales each reference down to the output area; 'max' keeps up to 2048 px on the short edge for the best identity, but reference tokens go through every step, so it can be several times slower.", "Output size and reference resolution.");
tip("global.output.aspect", "Use H3's native canvas for this aspect ratio.");
tip("global.output.custom", "Type your own width and height.");
tip("global.output.size", "Width and height in pixels, multiples of 32.");
tip("global.output.fps", "H3 always renders 24 fps.");
tip("global.output.audio", "H3 always renders 32 kHz stereo audio.");
tip("global.output.refSize", "match: references are scaled to the output area. max: up to 2048 px short edge, best identity, slower.");
more("global.sampling", "Sampling", "H3 is CFG-distilled, so CFG is fixed at 1.0 and there is no negative prompt. The native ComfyUI workflow uses the res_multistep sampler, the simple scheduler and 20 steps.\n\nThe sigma shifts change how the video and audio noise schedules are spread; leave them off unless you know you need them.", "Steps, sampler, scheduler and seed.");
tip("global.sampling.steps", "Sampling steps. 20 is the native default; turbo LoRAs need about 8.");
tip("global.sampling.cfg", "H3 is CFG-distilled: CFG 1.0, no negative prompt.");
tip("global.sampling.sampler", "Sampler. res_multistep is the native H3 choice.");
tip("global.sampling.scheduler", "Scheduler. simple is the native H3 choice.");
tip("global.sampling.seed", "Base seed.");
tip("global.sampling.reroll", "Pick a new random base seed.");
tip("global.sampling.seedMode", "same: every scene uses the base seed. +1 per scene: base seed plus the scene index. random: a new seed per render.");
tip("global.sampling.shift", "Use ModelSamplingMiniMaxH3 with the video and audio shifts below.");
tip("global.sampling.shiftVideo", "Video flow shift (native default 12).");
tip("global.sampling.shiftAudio", "Audio flow shift (native default 3).");
more("global.draft", "Draft quality", "Draft renders use a smaller resolution, fewer steps and an optional turbo LoRA, with the same seeds as Final. Use them to check timing and staging quickly, then switch to Final for the scenes you approve.", "Fast preview renders.");
tip("global.draft.scale", "Resolution scale for drafts (0.5 = half width and height, a quarter of the pixels).");
tip("global.draft.steps", "Sampling steps for drafts.");
tip("global.draft.lora", "Optional turbo LoRA used only for drafts.");
tip("global.draft.loraStrength", "Strength of the draft turbo LoRA.");
// [OLD 2026-11-05 v0.7.0->v0.8.0] no continuity settings at pass seams: more("global.defaults", "New scenes and long scenes", "Defaults for new scenes (length, how they start, language) and how scenes longer than one pass are split.\n\nThe longest pass can be up to 362 frames (15.08 s). Seams go on shot cuts when a cut falls within the snap window; otherwise the next pass starts from the previous pass's tail (the overlap) and the two are crossfaded in the cut.", "Defaults for new scenes and long-scene splitting.");
// added 2026-11-05 v0.8.0: what carries across a pass seam
more("global.defaults", "New scenes and long scenes", "Defaults for new scenes (length, how they start, language) and how scenes longer than one pass are split.\n\nThe longest pass can be up to 362 frames (15.08 s). Seams go on shot cuts when a cut falls within the snap window; otherwise the next pass starts from the previous pass's tail (the overlap) and the two are crossfaded in the cut.\n\nAt an overlap seam the next pass is guided by the last frames of the pass before. Those frames are decoded and encoded again, and each round trip loses a little, so a scene of many passes can drift. The settings under Pass seams decide what is carried and how: a full-precision guide VAE, whether the sound and the <Video 1> clip go along, a lossless pass cache and an experimental latent hand-off. Shot cuts avoid the round trip altogether.", "Defaults for new scenes and long-scene splitting.");
tip("global.defaults.duration", "Length of new scenes, in seconds.");
tip("global.defaults.start", "How new scenes start.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] free-text language: tip("global.defaults.language", "Default dialogue language.");
tip("global.defaults.language", "Default dialogue language. Pick one of H3's stable languages or type another.");
tip("global.long.maxPass", "Longest single H3 pass in frames (on the 17k+5 grid, 124–362).");
tip("global.long.overlap", "Frames of the previous pass that guide the next one at a mid-shot seam (17k+5: 22, 39, 56 …).");
tip("global.long.crossfade", "Crossfade inside the overlap, in frames.");
tip("global.long.seams", "Auto: use shot cuts when possible, overlaps otherwise. Cuts only: always split on a cut. Overlap only: ignore cuts.");
tip("global.long.snap", "How far a seam may move to land on a shot cut.");
more("global.llm", "Prompt rewriter · LLM", "Any OpenAI-compatible server (/v1/chat/completions): a local SGLang, vLLM, llama.cpp or Ollama server, or a hosted API. The base URL and model are saved with the project; the API key is stored in ComfyUI's user folder and never written into the workflow.\n\nThe LLM is only called when you press Rewrite, Split or Import. It is never called during a render.", "OpenAI-compatible LLM settings.");
tip("global.llm.baseUrl", "Server base URL including /v1, for example http://localhost:30000/v1.");
tip("global.llm.key", "API key. Stored in ComfyUI's user folder, never in the workflow. Leave empty for local servers without auth.");
tip("global.llm.storeKey", "Save the API key on the ComfyUI server.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] model is a filterable combobox: tip("global.llm.model", "Model id the server expects.");
tip("global.llm.model", "Model id the server expects. Type to filter the listed models (e.g. minimax), or type any id and press Enter. ↻ lists what the server offers. Empty uses the server default.");
tip("global.llm.listModels", "Fetch the model list from the server's /models endpoint.");
tip("global.llm.temperature", "Creativity of the rewrite. 0.2–0.5 keeps it close to your text.");
// [OLD 2026-11-02 v0.3.1->v0.3.2] tip("global.llm.maxTokens", "Maximum length of the LLM's answer.");
// [OLD 2026-11-03 v0.4.1->v0.4.2] tip("global.llm.maxTokens", "Maximum length of the LLM's answer, thinking included. Rewrite, Split and Import use at least 6000; Describe uses at least 6000 too (600 with thinking off).");
tip("global.llm.maxTokens", "Maximum length of the LLM's answer for Rewrite and Split, thinking included. Describe uses at least 6000 (600 with thinking off); Script import has its own budget under Limits. With a known context window the budget is lowered so prompt + answer fit.");
// added 2026-11-03 v0.4.2: limits
// [OLD 2026-11-03 v0.5.0->v0.5.1] more("global.llm.limits", "Limits", "Every LLM request streams its answer, so Reelwright can tell a slow model that is still writing from a server that has stopped answering.\n\nStall timeout: no data at all for this long ends the request (the default 120 s also covers a long prompt being read before the first word).\n\nGive up after: the longest one request may take, even while text keeps arriving.\n\nRetries: how often a request is tried again after a timeout, a dropped connection, a server error (5xx) or an answer that is not valid JSON. Errors that won't change on a second try (a wrong model name, a prompt too big for the context window) are not retried.\n\nContext window: the model's maximum tokens for prompt plus answer. 0 asks the server (vLLM and SGLang report max_model_len on /models; Test connection shows it). When it is known, the answer budget is lowered so both fit, and a request that cannot fit is refused before it is sent.", "Timeouts, retries and the context window for every LLM request.");
// added 2026-11-03 v0.5.1: the group folds
more("global.llm.limits", "Limits", "Every LLM request streams its answer, so Reelwright can tell a slow model that is still writing from a server that has stopped answering.\n\nStall timeout: no data at all for this long ends the request (the default 120 s also covers a long prompt being read before the first word).\n\nGive up after: the longest one request may take, even while text keeps arriving.\n\nRetries: how often a request is tried again after a timeout, a dropped connection, a server error (5xx) or an answer that is not valid JSON. Errors that won't change on a second try (a wrong model name, a prompt too big for the context window) are not retried.\n\nContext window: the model's maximum tokens for prompt plus answer. 0 asks the server (vLLM and SGLang report max_model_len on /models; Test connection shows it). When it is known, the answer budget is lowered so both fit, and a request that cannot fit is refused before it is sent.", "Timeouts, retries and the context window for every LLM request. Click to show or hide.");
tip("global.llm.timeout", "Seconds without any data from the server before a request is ended. Raise it for slow servers or very long prompts.");
tip("global.llm.maxWait", "The longest one request may take, even while the answer is still arriving.");
tip("global.llm.retries", "Extra attempts after a timeout, a dropped connection, a server error or an unreadable answer (0–5).");
tip("global.llm.context", "The model's context window in tokens (prompt + answer). 0 asks the server.");
// [OLD 2026-11-03 v0.5.0->v0.5.1] more("global.llm.import", "Script import", "A long script makes a long answer: a table of 46 shots comes back as about 15,000 tokens of JSON. Sent in one request it often ran past the token budget or the timeout. Import now cuts the script into parts and sends each part as its own request.\n\nParts follow the script's own structure: screenplay scene headings (INT. / EXT.), table rows, Markdown headings or \"Scene N\" lines, and paragraphs when there are none. A scene is never cut in two unless it is twice the part size. Text before the first scene (a premise or style note) and a table's column headings go with every part, and each part sees the cast found so far, so names stay the same.\n\nA part whose answer is cut off at the token budget is split in two and tried again automatically. A part that fails can be retried on its own; the scenes from the other parts are kept.", "How a script is sent to the LLM.");
// added 2026-11-03 v0.5.1: the group folds
more("global.llm.import", "Script import", "A long script makes a long answer: a table of 46 shots comes back as about 15,000 tokens of JSON. Sent in one request it often ran past the token budget or the timeout. Import now cuts the script into parts and sends each part as its own request.\n\nParts follow the script's own structure: screenplay scene headings (INT. / EXT.), table rows, Markdown headings or \"Scene N\" lines, and paragraphs when there are none. A scene is never cut in two unless it is twice the part size. Text before the first scene (a premise or style note) and a table's column headings go with every part, and each part sees the cast found so far, so names stay the same.\n\nA part whose answer is cut off at the token budget is split in two and tried again automatically. A part that fails can be retried on its own; the scenes from the other parts are kept.", "How a script is sent to the LLM. Click to show or hide.");
tip("global.llm.importPart", "Characters per part. Smaller parts answer faster and fit a smaller token budget; 0 sends the whole script in one request.");
tip("global.llm.importTokens", "Maximum answer length per part, thinking included. A part that runs out is split in two and tried again.");
more("global.llm.importThinking", "Thinking for Import", "Same as above: use the Thinking setting above.\n\nOff: Import asks the server to skip the thinking step even when Rewrite and Describe use it. Turning scenes into JSON needs little reasoning, so this is much faster with thinking models.", "Thinking for Import only.");
tip("global.llm.importThinking.same", "Use the Thinking setting above.");
tip("global.llm.importThinking.off", "Skip the thinking step for Import (SGLang, vLLM with Qwen3-style models).");
tip("global.llm.importGuides", "Also send MiniMax's H3 guides with every part (about 10,000 tokens). Import writes scenes, not H3 prompts, so they are off by default.");
tip("global.llm.progress", "What the running LLM request is doing: waiting for the server, thinking or writing, tokens so far and seconds.");
// added 2026-11-02 v0.3.2
more("global.llm.thinking", "Thinking", "Thinking models (Qwen3 and its successors, DeepSeek-R1 and others) reason before they answer, and that reasoning counts against Max tokens. If the budget runs out mid-thought the reply has no answer at all.\n\nModel default: leave it to the model and the server. Reelwright gives these calls a large budget, and if Describe still runs out it asks once more with thinking off.\n\nOff: ask the server to skip the reasoning step (sends chat_template_kwargs enable_thinking=false, which SGLang and vLLM pass to Qwen3-style chat templates). Faster, and plenty for descriptions and rewrites. Servers that don't accept the field (for example OpenAI's API) answer with an error; switch back to Model default for those.", "Let the model think first, or skip it.");
tip("global.llm.thinking.auto", "Leave thinking to the model and server.");
tip("global.llm.thinking.off", "Ask the server to skip the thinking step (SGLang, vLLM with Qwen3-style models).");
tip("global.llm.preset", "System prompt style for rewrites.");
// added 2026-11-02 v0.2.0
more("global.llm.guides", "Official H3 prompt guides", "When on, Rewrite, Split and Import send MiniMax's own H3 prompt-writing guides to the LLM as part of its instructions: the Ref2VA guide (ref-en.txt) and the base guide (base-en.txt) from the MiniMax-H3 repository on GitHub.\n\nThe guides are under MiniMax's licence, so Reelwright does not ship them: press Download to fetch them into ComfyUI's user/reelwright/guides folder. Until then, a short built-in summary of the same rules is sent instead.\n\nTogether they are about 40 KB (roughly 10,000 tokens), so turn this off for small local models with short context windows.", "Send MiniMax's official prompt guides to the LLM.");
tip("global.llm.guidesStatus", "Whether the official guides are downloaded, and when.");
tip("global.llm.guidesFetch", "Download (or refresh) the official guides from the MiniMax-H3 GitHub repository.");
// [OLD 2026-11-02 v0.2.2->v0.3.0] now says where the result appears
// tip("global.llm.test", "Send a tiny request to check the URL, key and model.");
tip("global.llm.test", "Send a tiny request to check the URL, key and model. The result appears below the button and as a message; it gives up after 20 seconds.");
tip("global.llm.status", "Result of the last connection test.");
// [OLD 2026-11-03 v0.4.1->v0.4.2] more("global.script", "Import a script", "Paste a screenplay, in Fountain or plain text. The LLM proposes characters, locations and scenes with shots and dialogue; tick the ones you want and add them. Existing cast with the same names is reused.", "Turn a screenplay into scenes.");
more("global.script", "Import a script", "Paste a screenplay, in Fountain or plain text, or a shot list (a Markdown table works). The LLM proposes characters, locations and scenes with shots and dialogue; tick the ones you want and add them. Existing cast with the same names is reused.\n\nA long script is sent in parts (Global → Prompt rewriter → Script import). Each part shows its progress; Stop keeps what is finished, and a failed part can be retried on its own.", "Turn a screenplay into scenes.");
tip("global.script.text", "Paste the script here.");
tip("global.script.run", "Ask the LLM to propose scenes and cast. Nothing is added until you confirm.");
tip("global.script.pick", "Include this item when adding.");
// [OLD 2026-11-02 v0.3.0->v0.3.1] tip("global.script.apply", "Add the ticked cast and scenes to the project.");
tip("global.script.apply", "Add the ticked cast and scenes to the project, where 'Add scenes' says. Ctrl+Z undoes it.");
// added 2026-11-02 v0.3.1: where imported scenes go
more("global.script.mode", "Where the imported scenes go", "At the end: after the last scene.\n\nAfter the selected scene: right after the scene selected on the Timeline or Scene tab, so you can drop a new sequence into the middle of the film.\n\nReplace all scenes: the current scenes are removed and the imported ones take their place. Cast, assets and Global settings stay, and rendered takes stay on disk. You are asked to confirm, and Ctrl+Z undoes it.\n\nWhatever you choose, the first scene of the film always starts fresh.", "Where the imported scenes go.");
tip("global.script.mode.append", "Add the imported scenes after the last scene.");
tip("global.script.mode.insert", "Insert the imported scenes right after the selected scene.");
tip("global.script.mode.replace", "Remove the current scenes and use the imported ones instead (asks first).");
tip("global.script.discard", "Throw the proposal away.");
// added 2026-11-03 v0.4.2: import in parts
tip("global.script.stop", "Stop the running part. Finished parts are kept; Continue picks up the rest.");
tip("global.script.retry", "Run the parts that failed or were not reached yet. Finished parts are kept.");
tip("global.script.part", "One part of the script: its first line and what happened to it.");
// added 2026-11-03 v0.6.0 (F2b)
tip("global.script.warnings", "Things in the LLM's answer that were of the wrong kind (a list where text belongs, a number as a name …). They were fixed or left out. Check those scenes before adding them.");
tip("global.script.warnings.more", "Show every note, or only the first few.");
tip("global.script.notes", "Text from the start of the script (and table column headings) sent with every part so each part knows the story.");
tip("scene.rewrite.stop", "Stop the rewrite request.");
tip("scene.preview.splitStop", "Stop the split request.");
more("global.matrix", "Where scenes override Global", "Each row is a setting and each column a scene. A coral dot means that scene overrides the setting. Click a scene number to open it.", "Overrides at a glance.");
tip("global.matrix.scene", "Open this scene.");
tip("global.matrix.cell", "This scene overrides this setting.");
more("global.info", "About", "Versions and optional tools found on the ComfyUI server: the native MiniMax H3 nodes (required), ffmpeg (needed for merging) and insightface (optional face checks).", "Backend and tool status.");
tip("global.info.backend", "Reelwright server routes.");
tip("global.info.h3", "ComfyUI's native MiniMax H3 nodes, required for rendering.");
tip("global.info.ffmpeg", "ffmpeg on the server's PATH, needed for merging and seams.");
tip("global.info.insightface", "Optional package for face-match drift checks.");

// ---------- Files tab (added 2026-11-03 v0.4.0) ----------
more("tab.files", "Files", "Everything Reelwright wrote to disk, for every project on this ComfyUI server, as a tree with sizes: rendered takes and their intermediate pass videos, merged cuts, autosaved versions, cast training sets and each project's assets (uploads, promoted frames, files picked from the output folder).\n\nTick what you no longer need and delete it to get disk space back. Takes are removed from the scene's take list too (if it was the starred take, the next newest becomes starred). Asset files this project uses are also removed from the project.\n\nOnly output/reelwright and input/reelwright are shown. The open project can't be deleted as a whole, and its project file is always kept.", "Disk use of every project; delete takes, cuts, autosaves, assets or whole projects.");
more("files.card", "Files on disk", "The tree lists projects (the open one first), then what each holds. Sizes add up from the bottom; the bar shows a row's share of the level above.\n\nTicking a folder or a take selects everything in it. Rows that are part of something larger, like a take's video, can only go with it. Deleting is permanent: the files don't go to a trash folder.", "Everything Reelwright wrote, with sizes.");
// [OLD 2026-11-03 v0.4.0->v0.4.1] tip("files.tree", "Click a name or arrow to open it, tick rows to select them, the bin deletes one row.");
tip("files.tree", "Click a folder to open it and a file to preview it; tick rows to select them; the bin deletes one row.");
tip("files.check", "Select this for deleting. A folder or take takes everything inside with it.");
tip("files.expand", "Open or close this folder.");
tip("files.size", "Size on disk and number of files. The bar is its share of the folder above.");
tip("files.open", "Open the file in a new browser tab.");
// added 2026-11-03 v0.4.1: previews
tip("files.preview", "The selected file: pictures, videos and sound play here, text files (subtitles, timelines, project JSON) are shown as text.");
tip("files.preview.show", "Preview this here (a take or a cut shows its video).");
tip("files.preview.close", "Close the preview.");
tip("files.delete", "Delete this from disk (asks first).");
tip("files.total", "Disk used by every Reelwright project on this server.");
tip("files.current", "Disk used by the project open in this node.");
tip("files.selected", "What deleting the selection would remove.");
tip("files.clear", "Untick everything.");
tip("files.deleteSelected", "Delete every selected row from disk (asks first, shows the total).");
tip("files.scope", "Show every project on the server or only this one.");
tip("files.scope.all", "Every Reelwright project on this ComfyUI server.");
tip("files.scope.current", "Only the project open in this node.");
tip("files.order", "How rows inside a folder are ordered.");
tip("files.order.natural", "Scenes in timeline order, takes and cuts newest first.");
tip("files.order.size", "Biggest first, to find what takes the space.");
tip("files.pick", "Add common clean-ups to the selection; nothing is deleted until you press Delete.");
tip("files.pick.takes", "Select every take that isn't the starred one of its scene.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("files.pick.passes", "Select the per-pass videos of long scenes. The take's video is already assembled from them, so they are not needed any more.");  (the pass cache has its own pick now)
tip("files.pick.passes", "Select the per-pass videos inside older takes. The take's video is already assembled from them, so they are not needed any more.");
tip("files.pick.cache", "Select every scene's pass cache. Renders made since v0.6.0 keep finished passes there to resume after Stop or to retake one pass; deleting it only means those passes render again when needed."); // added 2026-11-03 v0.6.0
tip("files.pick.cuts", "Select every merged cut except the newest, and leftovers of merges that didn't finish.");
tip("files.pick.versions", "Select every autosaved version file. The project itself stays.");
tip("files.pick.orphans", "Select scenes, takes, cast sets and asset files the project no longer lists.");
tip("files.expandAll", "Open every folder down to takes and cuts.");
tip("files.collapseAll", "Close every folder.");
tip("files.refresh", "Read the folders again (other nodes or ComfyUI may have changed them).");
tip("files.kind.project", "A Reelwright project: its output folder and its input (assets) folder.");
tip("files.kind.group", "One part of the project's folder.");
tip("files.kind.scene", "A scene's folder: its takes and its take list.");
tip("files.kind.take", "One rendered take: video, first and last frame, tail clip, settings and pass videos.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("files.kind.passes", "Videos of each generation pass of a long scene; the take's video was assembled from them.");  (also the scene's pass cache now)
tip("files.kind.passes", "Videos of single generation passes: inside an older take, the passes it was assembled from; under a scene, the pass cache that renders re-use.");
tip("files.kind.cut", "One merged cut: the video and its subtitle, timeline and chapter files.");
tip("files.kind.version", "An autosaved copy of the project file.");
tip("files.kind.asset", "A file in the project's input folder, used as a reference picture, video or sound.");
tip("files.kind.dir", "A folder.");
tip("files.kind.file", "A file.");
tip("files.flag.current", "The project open in this node.");
tip("files.flag.starred", "The scene's starred take: merges use it, and the scene counts as rendered because of it.");
tip("files.flag.orphan", "The project doesn't list this any more (a deleted scene, cast member or asset).");
tip("files.flag.unused", "In the asset library but used by no scene, cast member or score.");
tip("files.flag.used", "Used by the project.");
tip("files.flag.unlisted", "A take folder missing from the scene's take list, usually from a render that stopped.");
tip("files.flag.newest", "The newest merged cut.");
tip("files.flag.unfinished", "A partial file left by a merge that didn't finish.");
tip("files.flag.linked", "A hard link: the same bytes are also elsewhere, so deleting this alone frees nothing.");
tip("files.flag.intermediate", "Only needed while the take was being assembled.");
// added 2026-11-03 v0.6.0 (F2b): new flags, Repair, refused deletes
tip("files.flag.other_project", "A scene folder of another project that once used this folder. It is not this project's leftover, so “Not in the project” never selects it.");
tip("files.flag.unknown_owner", "A scene folder this project doesn't list, and nothing says whose it is. Check before deleting it.");
tip("files.flag.cache", "Finished passes kept for re-use: a render after Stop, a pass retake or a moved keep window starts from them. Safe to delete; they are made again when needed.");
tip("files.flag.draft", "A draft merge: half size, fast encoding.");
tip("files.flag.range", "A merge of some of the scenes only.");
more("files.repair", "Repair", "Reads every take's settings file (meta.json) in this project's folder and rebuilds the take lists from them: a lost or damaged list is made again, takes missing from it come back, takes whose folder is gone are dropped, and a lost star moves to the newest take.\n\nUse it after files were moved or deleted by hand, or when a scene shows no takes although they are on disk. Nothing is deleted.", "Rebuild this project's take lists from the takes on disk.");
tip("files.repair.result", "What the last Repair found and changed.");
tip("files.refused", "What the server did not delete, and why. A running render or merge of this project keeps its files until it ends.");
tip("files.merging", "While a merge runs, the takes, cuts and assets it reads can't be deleted.");

// ---- soundtrack (added 2026-11-03 v0.5.0) ----
more("timeline.lane.track", "Soundtrack track", "An audio file laid on the film, on a lane of its own. Drag the clip to move it (it sticks to scene cuts, the playhead and markers; hold Alt to place it freely), drag its left or right edge to trim the start or end of the file, right-click for more. Click it to edit it in the inspector above.\n\nA track can do two things, each with its own switch:\n• In the cut — it plays unchanged in the merged film, at its level and fades. The scenes' own sound is off under it unless you turn it on (Render tab → Merge → Scene sound).\n• Send to H3 — every pass of every scene it sounds under gets exactly the part of it that pass covers (up to 15 s, silence where the track does not play), as an audio reference with the marker you pick (fully_copy by default). H3 then syncs lips, gestures, movement and cuts to it. Cast voice samples are not sent while a scene gets the song.\n\nWhile a soundtrack sets the timing, scenes keep their exact place: transitions into fresh scenes play as a dip through black inside the scenes, and scenes not rendered yet merge as slates of their length. Moving or trimming a track that is sent to H3 makes the passes it covers stale.", "A soundtrack track. Drag to move, drag an edge to trim, click to edit.");
tip("timeline.lane.addTrack", "Drop an audio asset from the bin here to lay it on the film where you drop it, or use + to pick one. Add as many tracks as you like.");
tip("timeline.track.add", "Add an audio asset to the soundtrack, starting at 0:00.");
// [OLD 2026-11-03 v0.5.1->v0.6.0] tip("timeline.track.clip", "Drag to move (sticks to cuts, the playhead and markers; Alt: free). Drag an edge to trim. Click to edit; right-click for more.");
tip("timeline.track.clip", "Drag to move (sticks to cuts, the playhead and markers; Alt: free). While you drag a track sent to H3, the passes whose song part would change are outlined. Drag an edge to trim. Click to edit; right-click for more."); // added 2026-11-03 v0.6.0
tip("timeline.track.trimIn", "Drag to trim the start of the file. The rest of the track stays where it is in the film.");
tip("timeline.track.trimOut", "Drag to trim the end of the file.");
tip("timeline.track.loop", "The track repeats here (Loop to the end is on).");
tip("timeline.track.mute", "Mute this track: it is not mixed, not sent to H3 and does not set the timing.");
tip("timeline.track.delete", "Remove this track from the soundtrack. The audio asset stays in the bin. Ctrl+Z brings it back.");
tip("timeline.track.asset", "The audio asset this track plays. Changing it resets the trim.");
tip("timeline.track.start", "Where the track starts in the film (seconds). Below 0 the start of the file is before the film and is not heard.");
tip("timeline.track.in", "Where in the file the track starts playing (seconds).");
tip("timeline.track.out", "Where in the file the track stops (seconds). 0 = the end of the file.");
tip("timeline.track.volume", "Level in the merged film. 0 dB leaves it untouched. The monitor cannot play above 0 dB; the merge can. The part sent to H3 is never changed in level.");
tip("timeline.track.fades", "Fade in at the track's start and fade out at its end, in the merged film only.");
tip("timeline.track.length", "How much of the file plays, and how long the file is.");
tip("timeline.track.mix", "Play this track, unchanged, in the merged film and in the monitor.");
tip("timeline.track.sync", "Send every pass the part of this track it covers, as an H3 audio reference, so singing, lips, movement and cuts follow it.");
tip("timeline.track.marker", "How H3 treats the song: fully_copy reuses it as the clip's audio (best for lip sync), partially_copy keeps parts of it, reference and weak_reference only take its feel.");
tip("timeline.track.duck", "Lower this track while the scenes' own sound is loud (needs Scene sound on in the Merge card).");
tip("timeline.track.loopToggle", "Repeat the trimmed part until the film ends (a sound bed or a score).");
tip("timeline.track.toPlayhead", "Move the track so it starts at the playhead.");
tip("timeline.track.trimHere", "Trim the track's start or end to the playhead.");
tip("timeline.track.audition", "Play the film from where this track starts.");
tip("timeline.chip.song", "This scene gets the part of the soundtrack each pass covers, as an audio reference.");
tip("render.merge.locked", "A soundtrack is on the timeline, so every scene must land at its timeline position for the song to stay in sync.");
tip("render.merge.soundtrack", "Soundtrack tracks marked In the cut. They play unchanged; edit them on the Timeline tab.");
tip("render.merge.sceneAudio", "The sound each scene was rendered with, under the soundtrack. Off by default for a music video: H3 copies the song into the scenes, so mixing both would double it.");
tip("render.merge.sceneLevel", "Level of the scenes' own sound under the soundtrack (loudness normalised first, then this).");
tip("scene.budget.song", "A soundtrack track is sent to H3 for this scene: each pass gets the part of the song it covers.");

// ---- added 2026-11-03 v0.6.0 (F2a: timeline, soundtrack, scene tabs) ----
tip("timeline.beats", "Show the soundtrack's beats on its lanes. Yellow lines start a bar; short ticks are the other beats.");
tip("timeline.beatSnap", "Scene edges, shot cuts and moved tracks stick to the nearest beat (within a few pixels). Hold Alt for free movement.");
more("timeline.autoRoll", "Auto-roll", "A soundtrack sets the timing here: each scene must stay where it is on the song.\n\nWith Auto-roll on, making a scene longer takes the time from the next scene, and making it shorter gives the time to the next scene. Every later scene keeps its place on the song, so the song parts of later passes do not change and they don't render again.\n\nTurn it off to push the later scenes along (Ripple).", "Changing a scene's length moves only the cut to the next scene, so later scenes stay on the song.");
tip("timeline.track.beats", "The file's tempo and beat grid, found by Reelwright. The beats show on the lane when Beats is on.");
tip("timeline.track.waveRetry", "The waveform or beats could not be read. Click to try again.");
tip("timeline.track.stale", "The song part of this pass would change, so the pass would render again.");
tip("scene.start.effective", "How this scene really starts. A tail start deeper than Global → Continuity allows, or next to a scene shorter than 5 frames, continues from the last frame only.");
tip("scene.shots.beat", "Suggest shot start times on the soundtrack's beats. You see the changes first and apply them with one click.");
tip("scene.shots.beatPlan", "The suggested time on the beat for this shot cut. Apply moves them all; Ctrl+Z undoes it.");
tip("scene.shots.beatApply", "Move these shot cuts onto the beat. Ctrl+Z undoes it.");
tip("scene.prompt.unknownCode", "This looks like an asset code, but no asset has it. The render stops until it is fixed.");
tip("scene.prompt.notInScene", "This cast member is not in this scene, so H3 gets only the name, not their pictures.");
tip("scene.preview.listen", "Build and play the part of the soundtrack this pass is sent, exactly as H3 gets it.");
tip("scene.preview.excerpt", "The part of the soundtrack this pass is sent: which tracks, where in the film and how H3 treats it.");
tip("scene.budget.pass", "What each pass of this long scene sends. A pass over a limit is marked.");

// ---- added 2026-11-05 v0.8.0: pass tabs, Write prompts, shot and dialogue rows, camera picker, follow playback,
// pass-seam continuity settings, drift ----
more("scene.prompt.tabs", "A tab per pass", "This scene is longer than one H3 pass, so it renders in passes. Whole scene holds the note on the whole scene and the sections every pass shares; each pass tab holds that pass's own sections, shots and dialogue. Times are scene times.", "The whole scene, or one of its passes.");
tip("scene.prompt.tab.scene", "The scene note and the sections every pass shares.");
tip("scene.prompt.tab.pass", "This pass: its own sections, shots and dialogue (scene times). A dot means it has text of its own.");
// added 2026-11-12 v0.15.0: the LLM output popup
more("llm.output", "LLM output", "Shows what the LLM sends back as it arrives, in a panel over the editor: its reasoning (Thinking: a thinking model's chain of thought, as far as the server passes it on) and the answer, for each request (each pass, part or try). Use it to see what a slow request is doing, or what one that timed out had got.\n\nWhile a batch runs, the panel follows it to the next scene or part. It stays open after the request ends; × or Esc closes it, and Output opens it again. Drag its corner to resize it. Copy puts the text on the clipboard.\n\nOnly requests made from this page show; nothing is kept after a reload.", "Show what the LLM thinks and writes.");
tip("llm.output.copy", "Copy the reasoning and the answers.");
// added 2026-11-12 v0.15.0: Reset scene
more("scene.prompt.reset", "Reset scene", "Clears this scene's six sections (subject definitions, summary, retention analysis, detailed description, soundscape, music) and every pass's own text, after asking. Shots, dialogue, references, cast, LoRAs, the raw prompt and the Write prompts brief stay.\n\nOne undo step: Ctrl+Z brings the sections back. Off while Write prompts runs or when there is nothing to clear.", "Clear the six sections (asks first).");
// added 2026-11-12 v0.15.0: the Write prompts brief
more("scene.prompt.brief", "Write prompts brief", "Your own words for Write prompts: what the scene should be, who does what, the mood, the lines to speak. The LLM gets it every time it writes this scene's prompt (Write prompts, Write this pass, the rewriter), and where it and the summary disagree, the brief wins.\n\nNothing the LLM writes goes here, so it stays the same from one Write prompts to the next, unlike the summary, which Write prompts replaces. It is not sent to H3.\n\nWhen a scene of one pass has no brief yet, the first Write prompts keeps the summary you wrote as its brief.", "Your words for the LLM; Write prompts never overwrites them.");
more("scene.prompt.briefToggle", "Brief", "Shows or hides the Write prompts brief on the Prompt card of every scene. The dot says this scene has a brief.\n\nThe brief is your own description for the LLM, kept between Write prompts runs.", "Show or hide the Write prompts brief.");
more("scene.prompt.sceneNote", "Scene note", "In a scene of several passes the summary is a note on the whole scene: for you and for the LLM when it writes the passes. It is not sent to H3, because each pass does only part of the action: each pass gets its own summary, or one made from its shots and dialogue.", "A note on the whole scene; not sent in a scene of several passes.");
tip("scene.prompt.shared", "Every pass uses this text unless it has its own.");
// added 2026-11-12 v0.13.1: what a shared section is really used for, and the shot lines sent with the description
tip("scene.prompt.sharedUse", "Which passes use this shared text. A pass with its own text for this section (its tab, or Write prompts) uses that instead, and a pass whose prompt is edited by hand (What H3 receives) uses neither, so editing here does not change those passes.");
tip("scene.prompt.sharedAll", "Clear this section in every pass that has its own text, so they all use the text here. Ctrl+Z undoes it.");
tip("scene.prompt.shotLines", "H3 also gets a [Shot N] line for each shot and the spoken lines of the Shots and Dialogue cards, after the description (auto shots + dialogue). They usually decide what happens on screen, so a duplicated scene keeps acting like the original until you change them.");
tip("scene.prompt.passOwn", "Where this section comes from: this pass's own text, the scene's shared text, or the automatic one.");
tip("scene.prompt.passSection", "This pass's own text for the section. Empty: the shared or automatic text (shown greyed) is used. Type @ for assets and cast.");
tip("scene.prompt.passClear", "Remove this pass's own text, so it uses the shared or automatic text again.");
tip("scene.prompt.passShots", "The shots this pass shows, at scene times. A shot that started in the pass before is marked continues.");
tip("scene.prompt.passLines", "The dialogue lines that start in this pass, at scene times.");
tip("scene.prompt.passAuto", "Drop the hand-edited prompt of this pass, so it is built from these sections again.");
// [OLD 2026-11-12 v0.14.3->v0.14.4] more("scene.prompt.write", "Write prompts", "Asks the LLM to write the six sections of every pass of this scene: one request per pass, each with the scene note, the pass's own shots and dialogue, the pass before and after it, and MiniMax's rules (350–500 words of detailed description).\n\nThe answer goes into the pass tabs as one undo step; Ctrl+Z takes it back. Runs only when you press it.", "Write every pass's sections with the LLM.");
more("scene.prompt.write", "Write prompts", "Asks the LLM to write the six sections of every pass of this scene: one request per pass, each with the scene note, the pass's own shots and dialogue, the pass before and after it, and MiniMax's rules (350–500 words of detailed description).\n\nThe answer goes into the pass tabs as one undo step; Ctrl+Z takes it back.\n\nWith \"auto shots + dialogue\" on, each shot that starts in a pass takes the text, framing and camera move that pass wrote for it (when the pass wrote one [Shot N] line per shot), and the line leaves the pass's description. A shot that runs on from the pass before keeps that pass's own line for its continuation. Runs only when you press it.", "Write every pass's sections with the LLM."); // added 2026-11-12 v0.14.4: the shots take what each pass writes
// [OLD 2026-11-12 v0.14.2->v0.14.3] more("scene.prompt.writeOne", "Write prompts", "Asks the LLM to write this scene's six sections from its note, shots, dialogue and references, following MiniMax's rules (350–500 words of detailed description). The answer replaces the sections as one undo step; Ctrl+Z takes it back.", "Write this scene's sections with the LLM.");
// [OLD 2026-11-12 v0.14.3->v0.14.4] more("scene.prompt.writeOne", "Write prompts", "Asks the LLM to write this scene's six sections from its note, shots, dialogue and references, following MiniMax's rules (350–500 words of detailed description). The answer replaces the sections as one undo step; Ctrl+Z takes it back.\n\nWith \"auto shots + dialogue\" on, the shots it writes go into the Shots list: each shot takes its written text, framing and camera move (amplitude and speed too), and a scene without shots gets them, with its spoken lines. The description keeps the style sentences.", "Write this scene's sections with the LLM."); // added 2026-11-12 v0.14.3: the shots take what is written
more("scene.prompt.writeOne", "Write prompts", "Asks the LLM to write this scene's six sections from its note, shots, dialogue and references, following MiniMax's rules (350–500 words of detailed description). The answer replaces the sections as one undo step; Ctrl+Z takes it back.\n\nWith \"auto shots + dialogue\" on, the shots it writes go into the Shots list: each shot takes its written text, framing and camera move (amplitude and speed too) and keeps its time; a shot it writes past the scene's last one joins the timeline at its written start, and a shot it does not write keeps its text. A scene without shots gets them, with its spoken lines. The description keeps the style sentences.", "Write this scene's sections with the LLM."); // added 2026-11-12 v0.14.4: any count of written shots
tip("scene.prompt.writePass", "Ask the LLM to write this pass's six sections. One undo step.");
tip("scene.prompt.writeProgress", "What the LLM is doing: which pass, tokens so far and time.");
tip("scene.prompt.writeStop", "Stop writing. Passes already written are kept.");
more("scene.prompt.layout", "Pass texts from another layout", "The pass texts were written for passes that started and ended at other times: the scene's length, its shots or Global → Long scenes changed since. Each pass shows the stored text it overlaps most.\n\nUse the new layout stores the texts for the passes as they are now. Writing in a pass tab does the same.", "The pass texts were written for another pass layout.");
tip("scene.prompt.useLayout", "Store the pass texts for the current passes (one undo step).");
more("scene.prompt.onePass", "Pass texts of a shorter scene", "This scene was longer and had pass texts. Now it renders in one pass, and that pass uses the stored text instead of the sections below.", "Stored pass texts are used for this one-pass scene.");
tip("scene.prompt.onePassMove", "Copy the pass texts into the scene's sections and drop them (one undo step).");
tip("scene.prompt.onePassDrop", "Drop the stored pass texts; the sections below are used (one undo step).");
// [OLD 2026-11-06 v0.9.0->v0.10.0] tip("scene.rewrite.passes", "In a scene of several passes Rewrite works on the scene's own sections; Write prompts writes the passes.");
tip("scene.rewrite.passes", "Rewrite works on the pass whose tab is open: only its own sections change."); // added 2026-11-06 v0.10.0
tip("scene.shots.end", "When the shot ends, in scene seconds: where the next shot starts, or the scene's end.");
tip("scene.shots.duration", "How long the shot lasts. A new length moves the start of the next shot.");
tip("scene.shots.lastLength", "How long the last shot lasts. A new length changes the scene's length (later scenes follow the timeline's Ripple or Roll setting).");
tip("scene.shots.amplitude", "How far the camera moves: small, medium (not written) or large. Needs a camera move; Static Shot, POV and the shakes have none.");
tip("scene.shots.speed", "How fast the camera moves: slow, normal (not written) or fast. Needs a camera move; Static Shot, POV and the shakes have none.");
tip("scene.shots.framing", "Shot size or angle, written before the camera move: wide, medium, close-up, low angle …");
more("scene.shots.seam", "Pass seam inside a shot", "A seam between two passes falls inside this shot. At an overlap seam the next pass continues from the last frames of the pass before, which is where long scenes lose quality. A shot cut close to the seam lets the planner join the passes at the cut instead (Global → Long scenes → Snap seam to cut).", "A pass seam falls inside this shot.");
tip("scene.shots.continuing", "This shot started in the pass before and goes on in this one.");
tip("scene.dialogue.end", "When the line ends, in scene seconds: its start plus its length.");
tip("scene.dialogue.duration", "How long the line takes to say. Empty: estimated from the words (shown greyed).");
// [OLD 2026-11-06 v0.9.0->v0.10.0] quick fixes added
// more("scene.dialogue.seam", "Line past a seam", "This line runs past the end of the pass it starts in (or past the scene's end). The next pass does not know it is still being spoken, so the words are cut off. Start it earlier, shorten it, or move a shot cut so the seam falls after it.", "The line runs past a pass seam or the scene's end.");
// [/OLD]
// added 2026-11-06 v0.10.0: the quick fixes
more("scene.dialogue.seam", "Line past a seam", "This line runs past the end of the pass it starts in (or past the scene's end). Each pass is rendered on its own and the next pass does not know the line is still being spoken, so the words are cut off (or said again).\n\nStart after the seam moves the line just past the seam, so the next pass says all of it. End before the seam moves it earlier so it ends just before the seam, when its pass has room. You can also shorten it, or move a shot cut so the seam falls after it. Fix lines at seams (Dialogue card) moves every such line the smaller way. The seams themselves stay where they are.", "The line runs past a pass seam or the scene's end.");
tip("scene.dialogue.seamLater", "Move the line to start just after the seam, so the next pass says all of it. Hover to see where it lands.");
tip("scene.dialogue.seamEarlier", "Move the line earlier so it ends just before the seam (or the scene's end). Off when the line is longer than the room in its pass.");
tip("scene.dialogue.seamFixAll", "Move every line that runs past a pass seam: each goes the smaller way, after the seam or before it. One undo step.");
more("global.script.write", "Write prompts for the imported scenes", "The import gives each scene a short outline. Write prompts then asks the LLM to write every pass of every imported scene in full (one request per pass), one scene after another. Each scene's answer is its own undo step. Stop ends it after the request that is running; Retry failed writes the scenes that failed.", "Write the passes of the imported scenes.");
tip("global.script.writeStop", "Stop after the request that is running. Scenes already written keep their prompts.");
tip("global.script.writeRetry", "Write the scenes that failed or were not reached.");
tip("global.script.writeDismiss", "Hide this list.");
tip("global.script.writeItem", "One imported scene: waiting, writing, written or failed.");
more("global.long.seamsHead", "Pass seams", "What the next pass of a long scene takes from the pass before at an overlap seam, and how. The defaults are how earlier versions worked.", "What carries across an overlap seam.");
more("global.long.guideVae", "Guide VAE", "The VAE that encodes everything a pass is shown: reference pictures and clips, the footage it continues from and the guide frames at seams. The video VAE still decodes.\n\nThe default int8 video VAE is quantised, so every encode loses a little detail, and a long scene encodes the end of each pass again for the next one. A full H3 video VAE (fp32 or bf16) keeps more over many passes, for some memory and time. It must be a MiniMax H3 video VAE (full, int8 or a LightVAE encoder): its latents must be the ones the video VAE decodes.\n\nEmpty: the video VAE encodes too, as before.", "The VAE that encodes references and guides; empty = the video VAE.");
more("global.long.carryAudio", "Carry sound across seams", "On: at an overlap seam the next pass is also guided by the sound of the overlap, so voices and ambience run on.\n\nOff: only the picture is carried; the pass's sound starts fresh and the two passes' sound is crossfaded over the whole overlap. Turn it off when the sound gets noisier pass by pass. The passes after overlap seams render again.", "Guide the next pass with the overlap's sound too.");
more("global.long.seamVideo", "Send the previous pass as a video", "On: at an overlap seam the next pass also gets the last frames of the pass before as <Video 1>, named in the prompt (needs Cast → Name the continuation). Off: the overlap frames still guide it, but nothing more is sent, which leaves a video slot free and avoids one more round trip.", "Send the pass before as <Video 1> at overlap seams.");
more("global.long.handoff", "Hand-off", "Pixels: the overlap frames are decoded and encoded again for the next pass (as before).\n\nLatent (experimental): the next pass gets the sampled latents of the overlap directly, with no decode and re-encode, so nothing is lost at the seam. It only works when both passes have the same size and settings; otherwise the render falls back to pixels.", "How the overlap reaches the next pass.");
tip("global.long.handoff.pixels", "Decode the overlap and encode it again (as before).");
tip("global.long.handoff.latent", "Hand the sampled latents over directly. Experimental; falls back to pixels when it can't.");
more("global.long.passCache", "Pass cache", "Every pass is kept on disk so a retake or a later change does not render it again. Near-lossless (H.264 at CRF 4) keeps it small; lossless keeps every frame and the tail clip exactly as decoded, which matters when a later pass continues from a pass read back from the cache.\n\nLossless files are about 4 times larger (a 4-pass scene about 3 GB). Use it while chasing drift or before many pass retakes, and delete the pass cache in the Files tab afterwards. Nothing renders again when you switch.", "How passes are kept on disk.");
tip("global.long.passCache.near", "Small files, very slightly lossy.");
tip("global.long.passCache.lossless", "Exact frames, larger files.");
more("render.take.drift", "Drift", "How faithfully each pass that continues from footage (an overlap seam, a tail or last-frame start) reproduced the frames it was anchored to, measured on three of them: the anchor difference (mean pixel difference, 0–255, lower is better), the colour shift (how far the mean colour moved) and the sharpness (generated detail against the guide's, 1.00 = the same). Hover a pass for the colour per channel and the hand-off.\n\nGreen is fine, amber is worth a look, red is likely visible. The trend over the passes matters more than one number: a rising anchor difference, falling sharpness or a colour creeping one way is the drift of a long scene. Global → New scenes and long scenes → Pass seams has the settings that reduce it.", "How much each continuing pass drifted from the footage it continues.");
tip("render.take.long", "Pass-seam settings this take was made with (Global → Pass seams), where they differ from the defaults.");
// [OLD 2026-11-06 v0.9.0->v0.10.0] tip("render.table.drift", "The worst drift of the starred take's continuing passes.");
more("render.table.drift", "Drift light", "How well the starred take's continuing passes (after an overlap seam, a tail or a last-frame start) kept to the footage they continue; the worst pass sets the colour.\n\nGreen: every continuing pass stayed close to it. Amber: at least one drifted enough to be worth a look (the face, the colour or the sharpness moved). Red: at least one drifted enough to be likely visible at the seam.\n\nNo light: the scene has one pass, or its take was made before drift was measured. Hover the light for each pass's numbers; the take's row (Takes) shows them too.", "Green: close to the footage. Amber: worth a look. Red: likely visible. Hover for each pass."); // added 2026-11-06 v0.10.0
more("timeline.follow", "Follow the playhead", "While the film plays, the timeline scrolls so the playhead stays in the middle. Scrolling or dragging the timeline pauses this until you press play again or the playhead reaches the middle of the view. Click to follow again now.", "Following is paused: click to follow the playhead again.");

// ---- added 2026-11-06 v0.9.0: Timeline panels, captions and volume; Scene tab lists; asset groups and tags; Files split ----
tip("timeline.split.monitor", "Drag to share the width between the monitor and the inspector. Double-click to reset.");
tip("timeline.split.height", "Drag to set the height of the monitor and inspector; the timeline gets the rest. Double-click to reset.");
tip("timeline.monitor.caption", "The spoken line at the playhead, timed like the merge's .srt: from its time for its own length (Scene tab), or for its reading time.");
tip("timeline.captions", "Show the spoken lines as captions in the monitor. The merge's subtitles are set on the Render tab.");
tip("timeline.volume", "The monitor's volume, for the take and the soundtrack together. It only changes what you hear here, not the merge.");
tip("timeline.volume.mute", "Mute or unmute the monitor.");
more("timeline.inspector.summary", "Summary", "The scene's summary as the Scene tab has it. In a scene of several passes it is the whole-scene note: each pass gets its own summary, written in its tab or made from its shots.", "The scene's summary (whole-scene note for long scenes).");
tip("timeline.inspector.now", "What is on screen at the playhead: the pass (long scenes), the shot and the spoken line. It follows the playhead while the film plays.");
tip("scene.list.resize", "Drag to set how tall the list is; it scrolls inside. Every scene's shot lists share one height, and dialogue lists another. Double-click to reset.");
tip("files.split", "Drag to set the preview's width. Double-click to reset.");
tip("assets.view", "By group: your groups in their order, then the assets in no group. By kind: pictures, videos and audio, with each asset's group before its name.");
more("assets.group", "Asset group", "A group keeps related assets together: a character's pictures and voice, a set, the music. Its description says what belongs in it.\n\nDrag cards onto a group to move them, or pick the group in an asset's settings. The arrow folds a group away; ↑ and ↓ change the order; deleting a group keeps its assets (they have no group then).\n\nGroups and tags only sort this tab. Pickers elsewhere show an asset's group before its name. Nothing is sent to H3 and nothing renders again.", "A group of assets. Drag cards here to move them.");
tip("assets.group.none", "Assets that are in no group.");
tip("assets.group.add", "Make a new group and name it.");
// [OLD 2026-11-12 v0.14.0->v0.14.1] tip("assets.group.collapse", "Fold the group away or open it.");
tip("assets.group.collapse", "Fold the group away or open it (or click its name). It stays that way until you change it. Alt+click folds or opens every group and card on this tab; right-click the group's title for more."); // added 2026-11-12 v0.14.1
tip("assets.group.edit", "Rename the group and write what belongs in it.");
tip("assets.group.name", "The group's name. Pickers show it before the asset.");
tip("assets.group.description", "What belongs in this group. Shown next to its name.");
tip("assets.group.move", "Move the group up or down the list.");
tip("assets.group.delete", "Remove the group. Its assets stay, in no group. Ctrl+Z undoes it.");
tip("assets.group.pick", "The asset's group. Type a new name to make a group with it.");
tip("assets.tags", "Free words to find assets by, such as night or identity. Press Enter after each one.");
tip("assets.tags.filter", "Click a tag to show only the assets with it; click it again to show all.");

export const HELP = H;
