// Help catalog. `tip` is the hover tooltip; `title` + `more` fill the "?"
// popover (paragraphs separated by blank lines). Every data-help id in the UI
// must exist here; the harness test checks that.

const H = {};
const tip = (id, text) => { H[id] = { ...(H[id] || {}), tip: text }; };
const more = (id, title, text, tipText) => { H[id] = { tip: tipText || (H[id]?.tip ?? title), title, more: text }; };

// ---------- Tabs ----------
more("tab.timeline", "Timeline", "The whole film at a glance. The Scenes lane shows every scene as a block: drag its right edge to change its length, drag the small white triangles inside it to move shot cuts, and click the round chip between two scenes to change how the second one starts (fresh, from the last frame, or from a tail clip).\n\nThe lanes below show what each scene sends to H3: pictures and keyframes (diamonds), video and audio references, dialogue, camera wording and LoRAs. The asset bin on the left lets you drag assets straight onto a scene.\n\nShortcuts: Space play/pause, J back 1 s, K stop, L play, ←/→ one frame (Shift: 1 s), I/O set a loop, M add a marker, S split at the playhead, D duplicate, N new scene, Delete remove, +/− zoom, Ctrl+Z / Ctrl+Shift+Z undo/redo, ? this help.", "Overview of every scene and lane. Press ? for shortcuts.");
more("tab.scene", "Scene", "Everything that defines one scene: its length, how it starts, references, cast, shots, dialogue, prompt, LoRAs and any Global settings it overrides.\n\nA hollow dot means the setting follows the Global tab; a coral dot means this scene overrides it. Use the arrows or the strip at the top to move between scenes.", "Edit the selected scene.");
more("tab.assets", "Assets", "Pictures, videos and audio clips the project can use as references. Each asset gets a short code (P1, V1, A1) that you can type in prompts as @P1. Defaults set here (role, retention, features to keep) apply wherever the asset is used, unless a scene overrides them.\n\nH3 accepts per generation pass up to 9 pictures, 3 videos and 3 audio clips (2–15 s each, 15 s in total per type) and 12 files overall. The budget table shows where a scene goes over.", "Upload and manage reference images, videos and audio.");
more("tab.cast", "Cast", "The story bible: characters, locations and props that appear across scenes. A character's anchor pictures, description, voice and identity LoRA are sent to every scene it is tagged in.\n\nThis is how a subject from scene 1 still looks the same in scene 10: identity always comes from the same anchors, never from a chain of rendered frames, so nothing in between can make it drift.", "Characters, locations and props shared across scenes.");
more("tab.render", "Render", "Renders only what changed. Every scene has a cache key built from everything that affects its pixels; scenes whose key matches a take on disk are reused, even after a restart.\n\nEach scene is written to its own MP4 as soon as it finishes and its frames are dropped from memory. Merge scenes joins the starred takes into one film without re-rendering anything.", "Render, takes, memory and merging.");
more("tab.global", "Global", "Settings every scene inherits: models, LoRAs, output size, sampling, draft quality, defaults for new scenes, long-scene splitting and the LLM used by the prompt rewriter. Any scene can override most of them on the Scene tab.", "Project-wide settings that scenes inherit.");

// ---------- App frame ----------
tip("app.brand", "Reelwright: a timeline editor for MiniMax H3 ref2va inside one ComfyUI node.");
tip("app.backend", "Whether the Reelwright server routes answer. Without them you can still edit, but statuses, prompt previews, uploads and merging are unavailable.");
tip("app.undo", "Undo the last edit (Ctrl+Z). Selection and zoom changes are not part of the history.");
tip("app.redo", "Redo (Ctrl+Shift+Z or Ctrl+Y).");
more("app.issues", "Issues", "Problems found in the project: references over H3's limits, unknown @tags, dialogue without a language, shots after the end of a scene, missing files, a continuation without a previous scene and more. Errors stop a render; warnings and notes do not.\n\nClick an issue to jump to its scene.", "Problems that may stop or degrade a render. Click to list them.");
tip("app.issueItem", "Open the scene this issue belongs to.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] merge moved into the Render tab: tip("app.merge", "Join the starred take of every rendered scene into one film, with seams, audio fades and extras from the Render tab. Nothing is re-rendered.");
tip("app.merge", "Join the starred (or latest) take of every rendered scene into one film, using the Merge scenes settings on the right. Nothing is re-rendered.");
tip("app.renderPending", "Queue a render of every scene that is new or stale. Scenes whose cache key matches a take on disk are reused.");
tip("footer.issues", "The first issue in the project, or confirmation that every scene is within H3's limits.");
tip("footer.output", "Output size and quality from the Global tab. H3 always renders 24 fps video with 32 kHz stereo audio.");
tip("footer.status", "How many scenes have a matching take on disk, are stale (changed since their take) or have never been rendered.");
tip("footer.running", "The scene, pass and sampling step being rendered right now.");
tip("footer.length", "Number of scenes, total timeline length, and the length of the final cut after continuation overlaps are trimmed.");
tip("footer.save", "Edits are written into the workflow immediately and autosaved to output/reelwright/<project>/ every few seconds.");

// ---------- Common ----------
tip("common.close", "Close.");
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
tip("timeline.monitor", "Plays the starred take of the scene under the playhead, or shows a storyboard picture when the scene has not been rendered.");
tip("timeline.monitor.format", "Output size and frame rate from the Global tab.");
tip("timeline.monitor.take", "Showing the starred take. STALE means the scene changed since it was rendered.");
tip("timeline.monitor.storyboard", "Not rendered yet: showing the first picture reference or anchor as a storyboard.");
tip("timeline.timecode", "Playhead position (minutes:seconds.milliseconds).");
tip("timeline.transport.prev", "Jump to the start of this scene, or the previous scene if already at its start.");
tip("timeline.transport.play", "Play or pause (Space). Rendered scenes play their starred take; others advance over the storyboard.");
tip("timeline.transport.next", "Jump to the start of the next scene.");
tip("timeline.transport.loop", "Loop the scene under the playhead. I and O set a custom loop range at the playhead.");
tip("timeline.transport.cut", "Length of the final cut: the timeline minus the overlaps that tail-clip continuations trim away.");
tip("timeline.inspector.index", "Scene number in timeline order.");
tip("timeline.inspector.duration", "Target length on the timeline, in seconds and frames at 24 fps.");
tip("timeline.inspector.passes", "How H3 generates this scene: one pass (124–362 frames), several passes for long scenes, or one minimum pass trimmed down for short scenes.");
tip("timeline.inspector.overrides", "How many Global settings this scene overrides. Edit them on the Scene tab.");
tip("timeline.inspector.prompt", "The prompt of the first pass exactly as H3 receives it, with @tags turned into <Picture n>, <Subject n>, <Video n> and <Audio n>.");
tip("timeline.inspector.open", "Open this scene on the Scene tab.");
tip("timeline.inspector.render", "Queue this scene now, even if its take is up to date.");
tip("timeline.inspector.take", "Render another take of this scene with a new seed. The old takes stay on disk; star the one you like.");
tip("timeline.chip.cast", "A cast member in this scene. Their anchors are sent as references.");
tip("timeline.chip.ref", "A reference sent with this scene, with its role or retention.");
tip("timeline.chip.none", "Drag assets from the bin onto the scene block to add references.");
tip("timeline.addScene", "Add a new scene after the selected one (N). It starts the way the Global defaults say.");
tip("timeline.split", "Split the selected scene at the playhead (S). Shots, dialogue and keyframes go to the side they fall on; the second part continues from the first's last frame.");
tip("timeline.duplicate", "Duplicate the selected scene (D), including references, shots, dialogue and overrides.");
tip("timeline.delete", "Delete the selected scene (Delete). Undo brings it back; its takes stay on disk.");
tip("timeline.moveLeft", "Move the selected scene one place earlier.");
tip("timeline.moveRight", "Move the selected scene one place later.");
tip("timeline.snap", "When on, dragging a scene edge snaps to H3's 17k+5 frame grid, so the scene needs no trimming. Off: any whole frame.");
tip("timeline.ripple", "Ripple: lengthening a scene pushes the later scenes along. Roll: the next scene shrinks by the same amount, so the total stays the same.");
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
tip("timeline.scene", "A scene. Click to select, double-click to open it on the Scene tab, right-click for split, duplicate, move, lock and delete, drop an asset on it to add a reference.");
tip("timeline.scene.resize", "Drag to change the scene's length. Long scenes split into several H3 passes automatically; short ones are trimmed from a minimum pass.");
tip("timeline.scene.shot", "A shot cut. Drag to move it; the prompt writes it as [ShotN] At mm:ss.fff, cut to …");
tip("timeline.scene.passes", "This scene is longer than one H3 pass (15.08 s), so it renders as several passes joined in the cut.");
tip("timeline.scene.short", "Shorter than the shortest H3 pass (5.17 s): rendered at 124 frames and trimmed to the window set on the Scene tab.");
tip("timeline.scene.seam.cut", "Pass seam on a shot cut: a plain cut, nothing to blend.");
tip("timeline.scene.seam.overlap", "Mid-shot pass seam: the next pass starts from the previous pass's tail and the overlap is crossfaded.");
tip("timeline.scene.progress", "Live render progress: phase, pass and sampling step.");
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
tip("timeline.lane.vidRef", "A video reference (motion, camera or edit source). Uses one of the 3 video slots.");
tip("timeline.lane.audRef", "An audio reference with its retention label. Uses one of the 3 audio slots.");
tip("timeline.lane.soundtrack", "The soundtrack of a video reference, sent as its own <Audio n>.");
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
tip("scene.duration.in", "Where the scene starts on the timeline.");
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
more("scene.prompt", "Prompt", "Structured mode follows the MiniMax H3 reference prompt guide. It has six sections: subject definitions, summary, retention analysis, detailed description, soundscape and music. Subjects, retention lines, shots and dialogue can be filled in automatically from the scene's cast, references, shots and dialogue lists.\n\nRefer to assets as @P1, @V2 or @A1, to cast members as @Mara or @{Old Keeper}, and to the previous scene's tail as @tail. Each pass renumbers them into <Picture k>, <Video k>, <Audio k> and <Subject n> in the order H3 receives references: images, then videos (a video's soundtrack takes an <Audio> number just before it), then standalone audio.\n\nRaw mode sends your text as written, after the @tags are replaced.", "The prompt for this scene.");
tip("scene.prompt.mode", "Structured: six guided sections. Raw: one free text.");
tip("scene.prompt.structured", "Six sections following the H3 reference prompt guide, with automatic parts.");
tip("scene.prompt.raw", "One free-form prompt. @tags are still renumbered.");
tip("scene.prompt.rawEditor", "The whole prompt. Type @ for a list of assets, cast members and @tail.");
tip("scene.prompt.tasks", "Task tags put at the start of the summary. They are worked out from the references and how the scene starts, as the H3 guide recommends.");
tip("scene.prompt.unknown", "These @tags match no asset code, cast name or @tail, so they would reach H3 as plain text.");
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
more("scene.shots", "Shots", "Each shot becomes a line in the prompt: [Shot1] for the first, [Shot2] At 00:05.000, cut to … for later ones. Timestamps mark cuts, not how long an action takes, so keep each shot to one achievable action.\n\nIn long scenes, passes split on shot cuts whenever possible, so a cut is also the cleanest place for a seam. With no shots, the scene is described as one continuous take.", "Shot cuts inside this scene.");
tip("scene.shots.add", "Add a shot. Its start time is a cut in the prompt.");
tip("scene.shots.index", "How the shot is labelled in the prompt.");
tip("scene.shots.time", "When the shot starts, in seconds from the start of the scene.");
tip("scene.shots.camera", "Camera wording, such as shot size and movement. Pick a preset or type your own.");
tip("scene.shots.text", "What happens in this shot. Use @tags for assets and cast.");
tip("scene.shots.remove", "Remove this shot.");
// [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are per clip now: more("scene.dialogue", "Dialogue", "Each line is written as <Subject n> (S1) says <d>[English] …</d>. The speaker ID (S1, S2) stays the same for a character across the whole project, and their voice sample is sent as an audio reference so the voice matches.\n\nH3 speaks 11 languages reliably: Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian and Spanish.", "Spoken lines in this scene.");
more("scene.dialogue", "Dialogue", "Each line is written as <Subject n> (S1) says, <d>[English] …</d>. As MiniMax's guide asks, speaker IDs follow speaking order inside each clip: whoever speaks first is S1, the next new voice S2, and so on. The character's voice sample is sent as an audio reference so the voice matches across scenes.\n\nH3 speaks 11 languages reliably: Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian and Spanish. You can type any other language name; it is sent as written.", "Spoken lines in this scene.");
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
more("scene.preview", "What H3 receives", "The final prompt of every pass, built by the backend in MiniMax's Ref2VA format: six labelled sections in order (subject_definitions, summary, retention_analysis, detailed_description, overall_soundscape, non_diegetic_music), each label on its own line.\n\nReference pictures that define a character, place, prop or style become <Subject N> lines; standalone <Picture N> is kept for frame anchors. Shots are written as [Shot 1] …, [Shot 2] At 00:06.000, the shot cuts to …, and speakers are numbered S1, S2… in speaking order.\n\nLong scenes have one prompt per pass, with shots and dialogue re-based to the start of each pass. Split with LLM can write the per-pass prompts, and you can edit any pass by hand.", "The exact prompt sent for each pass, in Ref2VA format.");
tip("scene.preview.pass", "Show the prompt of this pass: its time range, frame count and the seam before it. A coral dot means the pass prompt was edited by hand.");
tip("scene.preview.splitLlm", "Ask the LLM to write one prompt per pass, keeping tags and dialogue as written. Runs only when you click.");
tip("scene.preview.splitAuto", "Drop the hand-written pass prompts and go back to the automatic split.");
tip("scene.preview.override", "Edit this pass's prompt by hand. It replaces the automatic one for this pass only.");
more("scene.rewrite", "Prompt rewriter", "Sends this scene's prompt to the OpenAI-compatible LLM set on the Global tab and shows the proposed changes as a diff. You accept, edit or discard them.\n\nIt runs only when you press Rewrite, never while rendering. Asset tags and <d>…</d> lines are checked after the rewrite; any that changed are reported as warnings.", "Improve the prompt with an LLM, on demand.");
tip("scene.rewrite.instruction", "Optional instruction for the rewrite, for example: make shot 2 more intimate.");
tip("scene.rewrite.run", "Send the prompt to the LLM and show a diff. Nothing changes until you accept.");
tip("scene.rewrite.diff", "Green lines are added, red lines are removed.");
tip("scene.rewrite.accept", "Apply the rewrite. Ctrl+Z undoes it.");
tip("scene.rewrite.edit", "Edit the proposed text before applying it.");
tip("scene.rewrite.discard", "Throw the proposal away.");
more("scene.budget", "Reference budget", "What this scene sends per pass. H3 ref2va accepts up to 9 pictures, 3 videos (2–15 s each, 15 s in total), 3 audio clips (same limits) and 12 files overall.\n\nGuides (first frame, last frame, keyframes and continuation clips) are not references and do not count. Packing a character's anchors into one sheet uses a single picture slot.", "How many reference slots this scene uses.");
tip("scene.budget.pictures", "Picture references plus anchor sheets. Max 9.");
tip("scene.budget.videos", "Video references, and their total length. Max 3 videos and 15 s.");
tip("scene.budget.audio", "Audio references, video soundtracks and voice samples, with their total length. Max 3 and 15 s.");
more("scene.refs", "References", "Assets this scene sends to H3. A picture can be a reference for the whole scene, or a guide pinned as the first frame, the last frame or a keyframe at a set time. Videos and audio are always references.\n\nEach reference has a retention label telling H3 how closely to follow it, and a list of features to keep. Values that differ from the asset's defaults are marked with a coral dot.", "Assets sent with this scene.");
tip("scene.refs.role", "reference: guides the whole scene. first_frame / last_frame / keyframe: pins this picture at that exact frame.");
tip("scene.refs.time", "When the keyframe is pinned, in seconds from the start of the scene.");
tip("scene.refs.retention", "How closely H3 should follow this reference.");
tip("scene.refs.description", "The asset's description as this scene uses it. It lives on the asset: click to edit it in the Assets tab, and every scene follows.");
tip("scene.cast.description", "The description this character's subject line uses: its own, or its first described anchor picture's.");
tip("scene.refs.keep", "Features to keep, written into the retention line (face, hair, coat …). Press Enter to add.");
tip("scene.refs.soundtrack", "Also send this video's audio as its own <Audio n>, numbered just before the video.");
tip("scene.refs.remove", "Remove this reference from the scene.");
tip("scene.refs.add", "Add an asset as a reference with its default role and retention.");
tip("scene.refs.overridden", "This reference differs from the asset's defaults.");
more("scene.cast", "Cast in this scene", "Characters, locations and props from the story bible. Their anchors, description, voice and identity LoRA are added automatically. Pick an outfit to change clothes while keeping the face.", "Story-bible entries in this scene.");
tip("scene.cast.add", "Add a character, location or prop from the Cast tab.");
tip("scene.cast.outfit", "Which outfit or variant they wear in this scene.");
tip("scene.cast.remove", "Remove from this scene.");
more("scene.loras", "Scene LoRAs", "Add to Global applies the Global LoRA stack first and then this scene's LoRAs. Replace Global uses only this scene's LoRAs.\n\nYou can also change the strength of a Global LoRA for this scene only. Identity LoRAs of cast members are added automatically and shown in blue.", "LoRAs for this scene.");
tip("scene.loras.mode", "Add to the Global stack, or replace it for this scene.");
tip("scene.loras.add", "Use the Global LoRAs and add this scene's on top.");
tip("scene.loras.replace", "Ignore the Global LoRAs in this scene.");
tip("scene.loras.strength", "Strength for this scene. Set it back to the Global value to remove the override.");
tip("scene.loras.name", "LoRA file (from ComfyUI's loras folder).");
tip("scene.loras.remove", "Remove this LoRA from the scene.");
tip("scene.loras.addItem", "Add a LoRA for this scene only.");
tip("scene.loras.cast", "Added automatically because a cast member with an identity LoRA is in this scene.");

// ---------- Assets ----------
tip("assets.filter", "Show all assets, or only pictures, videos or audio.");
tip("assets.search", "Filter by code, name, category or file name.");
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
tip("assets.card", "Select to edit its defaults. Drag onto a scene on the Timeline to use it.");
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
tip("cast.kind", "Character, location or prop.");
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
// [OLD 2026-11-02 v0.1.0->v0.2.0] free-text language: tip("cast.language", "Default language for this character's new lines.");
tip("cast.language", "Default language for this character's new lines. Pick one of H3's stable languages or type another.");
tip("cast.lora", "Identity LoRA, added automatically to every scene this entry appears in.");
tip("cast.lora.strength", "Strength of the identity LoRA.");
tip("cast.export", "Copy the anchors and starred frames of this entry into a folder ready for ai-toolkit LoRA training.");
tip("cast.delete", "Delete this entry and remove it from every scene.");
more("cast.outfits", "Outfits", "Looks this character wears. Each outfit has its own retention (for example partially_preserved keeping face and hair) so the face stays while the clothes change. Pick the outfit per scene in the Scene tab.", "Different looks for this entry.");
tip("cast.outfits.add", "Add an outfit or variant.");
tip("cast.outfits.default", "Default outfit for new scenes.");
tip("cast.outfits.name", "Outfit name.");
tip("cast.outfits.retention", "How strictly the anchors are followed with this outfit.");
tip("cast.outfits.keep", "Features to keep with this outfit (face, hair …). Press Enter to add.");
tip("cast.outfits.remove", "Delete this outfit.");
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
tip("render.preview", "Latent preview of the scene being sampled, updated every sampler step. ComfyUI's preview setting decides its quality (Latent2RGB or TAESD) or turns it off. If a preview can't be decoded, the last good one stays.");
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
more("render.merge", "Merge scenes", "Joins one take of every scene into a single film. Nothing is re-rendered, so it takes seconds and you can merge again whenever a scene changes.\n\nContinuation seams trim the overlap and crossfade inside it; hard cuts use the transition you choose. Audio gets a short fade at every seam and can be loudness-normalised. A score track can run under the whole film and duck under dialogue. Extras: subtitles from dialogue, a chapter per scene, OpenTimelineIO and FCPXML timelines for Resolve or Premiere, and a project bundle.", "Join the rendered scenes into one film.");
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
tip("render.merge.normalize", "Normalise loudness of the whole film (EBU R128).");
tip("render.merge.loudness", "Target integrated loudness. −16 LUFS suits online video; −23 broadcast.");
tip("render.merge.score", "Optional music asset that plays under the whole film. Useful because each H3 pass makes its own music.");
tip("render.merge.scoreVolume", "Level of the score track.");
tip("render.merge.duck", "Lower the score while scenes have sound or speech.");
tip("render.merge.color", "Match each scene's average colour to a reference scene, to smooth jumps between passes or VAEs.");
tip("render.merge.colorRef", "Scene the others are matched to.");
tip("render.merge.codec", "Video codec of the merged file.");
tip("render.merge.crf", "Quality: lower is better and larger. 16–20 is visually lossless for H.264.");
tip("render.merge.subtitles", "Write an .srt file from the dialogue lines, timed to the final cut.");
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
tip("render.versions.restore", "Replace the current project with this version.");
// added 2026-11-02 v0.3.6
tip("render.versions.delete", "Delete this version file. It cannot be undone; the project itself is not affected.");
tip("render.versions.deleteAll", "Delete every autosaved version of this project. The project and its latest autosave stay.");

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
more("global.project", "Project", "The project name, and the folder its renders and uploads go to. Changing the folder after rendering points the project at a new, empty render folder.", "Project name and folder.");
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
tip("global.loras.order", "Move up in the stack.");
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
more("global.defaults", "New scenes and long scenes", "Defaults for new scenes (length, how they start, language) and how scenes longer than one pass are split.\n\nThe longest pass can be up to 362 frames (15.08 s). Seams go on shot cuts when a cut falls within the snap window; otherwise the next pass starts from the previous pass's tail (the overlap) and the two are crossfaded in the cut.", "Defaults for new scenes and long-scene splitting.");
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
tip("global.llm.maxTokens", "Maximum length of the LLM's answer, thinking included. Rewrite, Split and Import use at least 6000; Describe uses at least 6000 too (600 with thinking off).");
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
more("global.script", "Import a script", "Paste a screenplay, in Fountain or plain text. The LLM proposes characters, locations and scenes with shots and dialogue; tick the ones you want and add them. Existing cast with the same names is reused.", "Turn a screenplay into scenes.");
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
tip("files.pick.passes", "Select the per-pass videos of long scenes. The take's video is already assembled from them, so they are not needed any more.");
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
tip("files.kind.passes", "Videos of each generation pass of a long scene; the take's video was assembled from them.");
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

export const HELP = H;
