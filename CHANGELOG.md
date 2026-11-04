# Changelog

## v0.6.0 — 2026-11-03

Fixes from a full code review, and the features it proposed. Merges that failed, renders stuck on "rendering", lost takes and damaged project files are fixed. Finished passes are kept and reused. New: pass retakes, variants, draft and range merges, audio stems, beat markers and a named undo history.

### What you will notice after updating

- **Some scenes render again once.** What they send to H3 changed:
  - a cast member's voice sample goes only to the passes where that character speaks;
  - a first-frame, last-frame or keyframe picture named in the text goes only to the pass it guides, and its subject line reads "is the keyframe of [Shot 1]" (was "is keyframe of");
  - a video guide is tagged *video continuation* (was *keyframe completion*), and a video guide named in the text is also sent as a reference video;
  - a pass prompt edited by hand, a Split prompt or a raw prompt gets its task tags once, in the summary;
  - written `[Shot N]` lines in a long scene go only to the pass that holds that shot;
  - a tail start past the re-anchor limit is planned as a last-frame start;
  - dialogue, shots and keyframes at the very start or end of a scene now land in a pass.

  Continuing scenes do **not** all go stale. A take rendered before v0.6.0 keeps counting until the scene it continues from gets a newer take. Seeds don't change: every existing scene keeps the seed it had.
- **Auto-roll is on while a soundtrack sets the timing.** Changing a scene's length takes the time from the next scene, so later scenes stay on the song. The **Auto-roll** toggle on the timeline toolbar turns it off.
- **Undo no longer changes the view.** Ctrl+Z, Ctrl+Y and the History menu keep the tab, zoom, snap, playhead and selection.
- **Each new node saves into its own folder**, `untitled-xxxx` (4 random letters and digits). The first rename moves it to the name's folder, as before.
- **A pasted or duplicated node becomes a separate project.** It gets a new project id, a folder `<slug>-2` (or `-3`…) and new scene ids, and a toast says so. Its renders start fresh; the original node keeps its takes. This also holds for a node pasted into another workflow (Ctrl+V, Paste, Duplicate, Clone, Alt-drag). A workflow opened twice, or saved under another name, still opens the same project. Two nodes of an older workflow that share a project but already use different folders keep their folders, scene ids and renders; only their project ids are made unique.

### The most important fixes

- **Merges no longer fail after a plain cut.** A crossfade, dip or continuing scene that came after a plain cut, a slate or a pass seam failed in ffmpeg ("Failed to inject frame"). Each scene in the merge is now also exactly its length in frames, so a take that is one frame short no longer shifts later scenes against the soundtrack.
- **Merges with a soundtrack are frame-exact.** Scenes whose length is not a whole number of frames (7.3 s) are cut on the film's frame grid, so the merge no longer flashes one-frame dark slates or drifts from the song, and a crossfade late in the film keeps its whole picture. A take one frame short holds its last frame instead of a slate.
- **The editor no longer stays on "rendering".** Stop, a check that fails before the render starts, or a ComfyUI error all end the run in the editor. The end of a run says how many scenes rendered, failed or were skipped.
- **One failing scene no longer stops the render.** The other scenes go on. Scenes that continue from the failed one are skipped. The failure shows at once, and ComfyUI shows the error when the run ends.
- **Reopening a workflow shows the project's own takes.** They were read for the "untitled" folder before the project loaded, and a rename then moved the project's folder away from its renders.
- **Project files are no longer damaged by two saves at once.** Every write goes through its own temporary file, and every change to a take list, `project.json` or the cut numbers holds a lock for the project. A damaged take list is rebuilt from the takes' `meta.json`; a damaged `project.json` falls back to the newest autosaved version.
- **The tail clip holds the last 124 frames of the scene**, across its passes. A 73- or 90-frame tail overlap, or a scene whose last pass is short, used to get fewer guide frames than the merge trims.
- **A continuing scene goes stale when the scene before gets a new take.** Its cache key now includes the take it continues from (before, "New take" on scene 1 left scene 2 cached). The Render tab says "Continues from a different take", with one click to render it and the scenes after it again.
- **Ctrl+Z no longer reaches the ComfyUI workflow** after picking from a dropdown with Enter or Escape, after clicking a video's or audio's controls, or while a dialog is open. On a checkbox or slider, Ctrl+Z undoes the editor.
- **Dialogs: Enter presses the button that has focus.** Enter on Cancel used to confirm. Delete dialogs open with Cancel focused, and Tab stays in the dialog. Every confirmation (render everything, delete a take, a version or a cast member) is now a dialog; the inline bars vanished when a render redrew the screen.
- **`@soundtrack` in a pass that gets no part of the song no longer blocks the render.** It is written as "the soundtrack".
- **Next, Previous and Loop work on continuing scenes.** They go to where each scene first shows new content. The Scene tab's "In" shows that time too.
- **Split keeps the film's length** (the second half was one frame short). Split, Duplicate and paste give the new scene its own seed.
- **Broken or hand-edited project files no longer break the editor or the render.** Bad values fall back to defaults, and the browser and the server repair them the same way. A duration typed as text can't hang the browser. Duplicate scene ids and duplicate asset codes ("p1" next to "P1") are repaired.
- **The last edit is no longer lost** when you switch workflows or remove the node. ComfyUI marks the workflow as changed after editor edits. Ctrl+S waits for the save and says when it fails.

### Rendering

- **Finished passes are kept** in a pass cache per scene (`scenes/<id>/passes/`), for long and short scenes. After Stop or an error, the next render starts where it stopped. Moving a short scene's kept window only re-trims it. Pass files of takes made with v0.5.1 are reused when they match.
- **A check before the GPU starts.** A render first checks the H3 nodes, the folder name, every reference, anchor, voice, song and guide file, the model files, the take each continuing scene starts from, that video guides fit their pass, and ffmpeg. It lists every problem at once.
- **Pass retake** (Render tab, one button per pass of a long scene): a new seed for that pass only. Earlier passes come from the pass cache; later passes joined by an overlap are rendered again; passes after a shot cut are kept.
- **Variants** (Render tab): render 2–8 takes of the selected scene in one run. With the face check on, the best match is starred; otherwise the first new take is. "Compare vN and vM" opens the two newest in the A/B view.
- **Time estimates** for each scene and for the pending queue ("≈ 20 min + 1 scene without history"), learned from earlier renders with the same quality, size and steps. Passes already in the pass cache are shown ("· 2 kept").
- **"why?"** next to a stale scene shows how its prompt changed since the starred take, pass by pass.
- **A continuing scene whose tail clip would be too short is refused before rendering.** When the take it continues from (a hand-picked, locked or older take) is shorter than the planned overlap, the guide used to be shorter and the seam about 13 frames off. The plan warns, and the render asks you to render the scene before again or to shorten the overlap.
- **A failed drift retake or extra variant is a warning.** The scene keeps its new take, the scenes that continue from it still render, and the toast and the Render tab's last-run note list the warning.
- **Variants show their real progress:** take k of n in the node title and the Render tab.
- **A take you star by hand stays starred.** A render no longer moves the star back to the take that matches. The Render tab marks a hand-picked star.
- **After a render, failed and skipped scenes are listed** with the reason and a **Render them again** button. A render that never started says why. A pass taken from the pass cache shows "from cache".
- **Video guides are placed to fit.** A video used as a last frame, or as a keyframe near the end of a pass, no longer stops the render: a last-frame clip ends on the guided frame, other clips are shortened to the room left. The Issues list says how much of the clip is used and how to keep all of it.
- **Continuation follows one rule everywhere** (planning, trimming, timeline, merge). A tail start past the re-anchor limit is a last-frame start. The tail overlap is at most 124 frames and never longer than the scene before; next to a scene shorter than 5 frames, a tail start becomes a last-frame start.
- **"+1 per scene" seeds stay with their scene.** Adding, removing or moving scenes no longer changes other scenes' seeds.
- Reference videos are read only up to 15 s instead of decoded whole; voice files are cut to 15 s.
- Face check: a drift retake is starred only when it matches better; frames without the character no longer count as drift; a face-model setup that failed is tried again on the next render.
- Changing the long-scene crossfade now re-renders the long scenes that use overlap seams (takes made with v0.6.0 and later).
- Memory is freed after every scene, also after a failure.
- Reelwright loads in a ComfyUI without the MiniMax H3 nodes. Global → About says why they are missing, and a render is refused with that reason.
- A render into a folder that holds another project is refused with a clear message.
- The node's `video` output is the newest full cut, never a draft or range merge.
- A double click on a render button queues one render. A sampler's preview inside a subgraph is no longer shown as Reelwright's.

### Merge and export

- **One merge per project at a time.** A second one is refused with a clear message. A running merge can be stopped (**Stop merging**), including the automatic merge after a render; a stopped merge removes the files it wrote.
- **Draft merges, ranges and stems** (Render → Merge card → *This merge*; not saved with the project):
  - *Draft*: half size, fast x264 preset, CRF 28, file `<slug>_cut_vN_draft.mp4`;
  - *From … to*: only those scenes, file `…_cut_vN_sAA-BB.mp4` (scene numbers);
  - *Stems*: `…_stems/` with `scenes.wav`, `mix.wav` and `track_<id>.wav`, plus an EBU R128 loudness report (`…_loudness.json`, shown in the card: integrated loudness, loudness range and true peak; above −1 dBTP is highlighted).
- **ffmpeg can't hang the merge.** Its output is read as it comes, and the filter graph goes in a file, so long films also merge on Windows.
- **Cut numbers are never reused**, so "older cuts" always means older.
- **OTIO and Final Cut Pro XML** get the soundtrack tracks and the timeline markers. Titles with quotes no longer break the FCPXML; slates and missing scenes are gaps; OTIO clips no longer drift by a frame.
- Subtitles: a line at the very start of a last-frame scene is no longer dropped; a blank line inside a line no longer breaks the cue; an empty line no longer cuts the previous cue short.

### Soundtrack and timeline

- **Beat markers.** Soundtrack lanes show the song's beats and bar starts, and the clip shows its tempo (BPM). **Snap to beats** makes scene edges, shot cuts and moved tracks stick to them (Alt: free).
- **Shots on the beat** (Scene tab → Shots → *On the beat*) proposes shot start times on the beat; **Apply** moves them in one undo step.
- **What goes stale.** While you drag a soundtrack track that is sent to H3, the scenes and passes that would render again are outlined, and the drag tip counts them.
- **Listen** (Scene tab → What H3 receives) plays the part of the song a pass is sent.
- Looping over a rendered take loops the picture and the soundtrack (the video used to play on).
- Deleting or undoing the scene that is playing no longer stops playback with a broken playhead.
- **Delete removes what is selected:** a marker or a soundtrack track (Ctrl+Z brings it back), otherwise the scene (it asks). Clicking a scene closes the marker panel.
- **The timeline stays fast on long films.** A render step updates only its progress bar, and only the part of the timeline near the view is built. At 300 scenes a progress update took about 0.25 s; now a few milliseconds.
- Loop repeats of a track are drawn as one pattern that ends with the film. A waveform that failed to load can be retried.
- Shot cuts can't be dragged into the trimmed start of a continuing scene; "+ Line" never makes a negative time; shot and resize drags end cleanly when the button is released outside the editor, and survive a redraw in the middle.
- Each editor on the page has its own playback and audio.

### Prompt and LLM

- **Tags:** e-mail addresses are text; `@@` writes a literal `@`; names may have accents, apostrophes, hyphens and dots (`@Ömer`, `@O'Brien`); `@Mara's` works. An unknown `@name` is a warning (written as plain text); a mistyped asset code like `@P9` is an error.
- **Task tags once.** A pass edited by hand, a Split prompt or a raw prompt gets the task tags exactly once, at the start of the summary. A raw prompt that starts with `[Shot 1]` gets them too.
- **Written `[Shot N]` lines go only to the pass that holds that shot**, renumbered and with the pass's times. Rewrite keeps them.
- **Guides per pass.** A first-frame, last-frame or keyframe picture named in the text is sent only to the pass it guides; other passes name it in words. A video guide named in the text is sent as a reference video and described by its place ("the opening clip of [Shot 1]").
- **Voices per pass.** A character's voice sample is sent only to the passes where they speak.
- **Issues:**
  - a missing file is an error on every scene that uses it;
  - a video guide longer than the room in its pass says how much of it is used;
  - dialogue or a shot inside a trimmed tail overlap, before 0 s or in no pass is a warning;
  - a prompt written for a pass the scene no longer has is flagged;
  - the reference budget counts a video's own sound as audio, a voice only where its character speaks and the song only where it is sent. The editor and the render check now agree.
- **LLM:**
  - a reply that has `</think>` without `<think>` is read correctly;
  - a raw Rewrite cut off at the token limit is retried with a bigger budget (up to 32,768 tokens);
  - "busy" (HTTP 429) answers are retried after the wait the server asks for (up to 60 s);
  - context-window errors are explained and not retried;
  - a base URL without `http://`, or with a pasted `/chat/completions`, works;
  - a web page instead of JSON says to check the base URL.
- **Script import** fixes sloppy JSON and wrong types, or leaves the item out with a warning; the warnings are listed under the draft. An opening scene before the first heading is no longer lost. Every imported scene gets its own seed. Split accepts "pass 2" or "02" keys and object values.
- Stop during Rewrite or Split is no longer lost.
- Building the prompts for the plan is about 4× faster on long projects (one shared context); the whole plan request gains less.

### Editor

- **History menu** (clock button next to Undo/Redo): every edit by name. Click a step to go back or forward to it.
- **Folder conflicts.** When a project's folder holds another project, the footer shows "Folder in use" and a toast says so; the project is not written to disk until you choose. Click the footer, press Ctrl+S, Render or Merge to choose: **Use a separate project** (a new folder `<slug>-2`…), **Take over this folder**, or **Decide later** (selected first, so a key press while typing can't pick for you).
- **Typing is no longer disturbed by updates.** While you type in a field, the tab is not redrawn under you, so a minus sign, a selection or a half-typed value is no longer lost when a render, plan or autosave update arrives (Tab into the height and typing 512 used to give 768512). Typing a value another field also holds no longer moves the cursor there, and after Enter a field shows the value that was stored (1000 → 992 on the 32-pixel grid).
- Typing with an input method (Japanese, Chinese, Korean) no longer garbles text. Typing "-" or "1e" in a number field no longer resets it.
- Typing a shot or line time that re-sorts the list keeps the cursor in the same shot's field.
- **Restoring an autosaved version first shows what it changes** (scenes, lengths, prompt text, Global settings).
- The A/B compare and the asset preview keep playing while a render reports progress.
- Deleting an outfit moves the scenes that wore it to the default outfit. Deleting an asset file in the Files tab also removes its soundtrack tracks.
- Renaming a project no longer moves its folder away from its renders when they haven't been listed yet.
- Project folder names drop accents ("Ömer" becomes "omer") and are at most 64 characters; a name with no Latin letters gets "untitled".
- The Scene tab shows the reference budget per pass for long scenes, and notes a re-anchored or shortened tail start.
- A Global profile saved before v0.5.0 no longer brings its old score back silently: it becomes a soundtrack track, with a note. The Global tab no longer asks for profiles again while the first request is on its way.
- "From ComfyUI" closed while files are being added no longer comes back as an empty card.
- Removing a node releases everything its editor used (listeners, timers, players).

### Files tab

- **Repair** rebuilds the take lists from the takes on disk (their `meta.json`).
- Each scene's **pass cache** is listed with its own label and quick selection.
- Another project's scene folders are labelled and never picked as leftovers.
- The server refuses to delete what a running render or merge uses, a take's own files and the cut counter, and the tab shows the reason. A linked project folder is unlinked, never followed.
- Draft and range cuts and their stems are grouped with their cut.
- Uploads are checked (unreadable files are refused) and streamed to disk. Importing a file with the same name and size as another no longer attaches the wrong one.

### For developers

- **New routes:** `POST /reelwright/merge/cancel`, `POST /reelwright/storage/repair`, `GET /reelwright/beats`, `POST /reelwright/soundtrack/excerpt`. **Changed:** `/merge` (draft, range, stems, job; 409 busy), `/autosave` (409 `slug_conflict` unless `force`), `/plan` (upstream, estimate, prompt fields), `/info` (`h3_error`), `/upload` (streamed, checked). Wrong input types answer 400. See `docs/ARCHITECTURE.md`.
- **Events:** `reelwright.run` has `run_id` and phases `start`, `end` (always sent; `rendered`, `failed`, `skipped`, `warnings`, `interrupted`) and `rejected`. `reelwright.progress` adds the phases `reuse`, `error` and `skipped`, and `warning: true` on a `done` whose extra take failed. New plan issue code `short_upstream_tail`. `reelwright.merge` events carry `job`.
- **Run actions:** `pass_retake` `{scene_id, pass}` and `variants` `{scene_ids, n}`.
- **Takes** record `prompts`, `upstream`, `pass_keys`, `offsets`, `render_seconds`, `face_score` and more; `index.json` gains `auto_star` and `project_id`.
- **Disk:** `scenes/<id>/passes/<key>.mp4|.json` (pass cache; takes no longer have `passes/`), `cuts/.next`, `_draft` / `_sAA-BB` cut names, `_stems/`, `_loudness.json`, `input/reelwright/.uploads/`, `user/reelwright/cache/beats/`.
- **Project:** `project_id`, per-scene `seed_n`, view settings `ui.beats`, `ui.beatSnap`, `ui.autoRoll`.
- New `reelwright/jobs.py` (per-project locks, one merge at a time) and `reelwright/beats.py`. `model.effective_start`, `scene_overlap_at`, `visible_start` and `scene_media_counts` have exact JS twins, checked by `tests/test_model_parity.py` (runs `web/rw/model.js` under node). `prompt.prepare(p)` builds a shared context for `build_pass` and `lint_project`.
- Store: `update(fn, {label})`, `history()`, `jumpTo(k)`, `flush()`, `dispose()`; tabs can export `onProgress(ctx, d)`.

## v0.5.1 — 2026-11-03

- **Ctrl+Z no longer blanks the node.** ComfyUI watches every key press on the page and runs its own workflow undo on Ctrl+Z unless a text field has focus. Its undo rebuilds the whole graph, so pressing Ctrl+Z in the editor undid the workflow as well as the edit. With Nodes 2.0 on, the rebuilt node then showed nothing, because Vue kept showing the old node's emptied element.
  - Keyboard focus in the editor now sits on a hidden read-only field that ComfyUI leaves alone. Ctrl+Z, Ctrl+Y and Ctrl+Shift+Z only undo and redo the editor, and the other shortcuts work as before.
  - Focus stays in the editor after a click on a button that the editor redraws (Add scene, a tab, a toggle). Before, focus fell to the page, so the next Ctrl+Z went to ComfyUI.
  - When ComfyUI's own undo does rebuild the node (Ctrl+Z with the canvas focused), the editor moves into the element Vue is showing, so it stays visible.
- **The LLM's Limits and Script import settings fold away** (Global → Prompt rewriter). Both groups start closed and show their values on one line (for example "stall 120 s · give up 900 s · 2 retries · context from the server"); click the heading to open or close a group.

## v0.5.0 — 2026-11-03

- **Soundtrack lanes: cut a film to a song.** Audio files can now be laid on the timeline, each on its own lane under the scenes, with its waveform. Add as many as you like:
  - drop an audio asset from the bin on the **Soundtrack** lane, or use its **+**;
  - drag a clip to move it (it sticks to scene cuts, the playhead and markers; Alt places it freely);
  - drag its edges to trim the start or end of the file;
  - click it to edit the rest in the inspector: start, in, out, level, fades, mute, loop, and the two switches below.
- **Send to H3** (on by default). Every pass of every scene the track sounds under gets exactly the part of the song that pass covers, cut to the pass's generated frames (up to 15 s, silence where the track does not play). It goes to H3 as an audio reference, marked `fully_copy` unless you pick another marker, so singing lips, gestures, movement and cuts follow the vocals and beat.
  - The prompt says so: `<Audio N> is the song this part of the film is cut to…`, a retention line for it, and `@soundtrack` in your own text becomes that `<Audio N>`.
  - Cast voice samples are not sent while a scene gets the song (it carries the singing).
  - The WAV for each pass is made once, under `output/reelwright/<project>/soundtrack/`.
  - Moving or trimming the track makes only the passes it covers stale; its level and fades don't.
- **In the cut** (on by default). The track plays unchanged in the merged film: no loudness normalisation, no ducking unless you ask, at its own level and fades (0 dB and none by default).
  - The scenes' own sound is **off** under a soundtrack by default (H3 copies the song into the scenes, so mixing both would double it).
  - Render → Merge → **Scene sound** turns it on, with a level (−12 dB by default). Loudness normalisation then applies to the scenes' sound only. A track can duck under it.
  - The monitor plays the tracks with the takes, at the same levels.
- **The timeline is the cut.** A scene that continues the one before (tail clip or last frame) now starts inside it, over the frames it repeats, exactly where the merge puts it. Before, the timeline laid scenes end to end and the finished cut was shorter, so a song laid on the timeline would have drifted. The scene blocks start where each scene becomes visible; the tail clip is drawn under the end of the scene it repeats.
- **While a soundtrack sets the timing, every scene keeps its place in the merge.**
  - Crossfades and dips into fresh scenes play as a dip through black inside the two scenes instead of overlapping them.
  - Scenes not rendered yet merge as slates of their length (unless the merge is set to Block).
  - A take of another length (rendered before the scene changed) is trimmed or followed by a slate.
- **The old merge score is now a soundtrack track.** A project with a score track opens with it as a looping track, in the cut and not sent to H3, with the same level and ducking. Scene sound stays on, as it was under a score.
- New route `GET /reelwright/waveform?file=&per_second=` (peak levels of an input audio file). `merge.build_command` takes `tracks` and `scene_audio`; segments can carry `vfade_in` / `vfade_out`.
- Deleting an audio asset removes its soundtrack tracks (Ctrl+Z brings both back). The Files tab counts soundtrack use, and the Merge card no longer prints a stray "0" when no scene sets its own cut.

## v0.4.3 — 2026-11-03

- **Imported scenes no longer have shots after their end.** A scene made from several timed rows of a script could come back with the wrong length: for example a 68 s chorus came back as 30 s, with shots starting up to 61.8 s. Those shots were never rendered.
  - Import now asks for each shot's duration, and the scene lasts the sum of its shots. Each shot starts where the one before it ends. Durations are easier for a model to copy from a table than running start times, so they win over the given starts and the given scene length.
  - Without durations, the shots are sorted and a scene that is too short is lengthened; its last shot gets the scene's typical shot length (the median gap between shots). A dialogue line after the end lengthens the scene to the line plus 2 s.
  - The review list notes each scene whose length was changed ("length set from its shots (68.04 s; the LLM gave 30.00 s)").
- **Fixing existing scenes:**
  - the Shots card says how many shots or lines start after the end and offers **Lengthen to …** (make the scene long enough) or **Fit into …** (keep the length and move every shot and line closer together in proportion);
  - the Issues list has **Lengthen them to fit** for every such scene at once.

  All three can be undone with Ctrl+Z, and focus stays in the editor so Ctrl+Z works right away.
- **Shot length beside each shot's start** ("for 8.42 s"). A shot lasts until the next one starts; the last one runs to the end of the scene ("· end"). A shot after the end says so.

## v0.4.2 — 2026-11-03

- **Script import works for long scripts: it sends them in parts.** The whole script used to go out as one request with a 6,000-token budget and a fixed 180 s timeout. A 46-shot table answers with roughly 15,000 tokens of JSON, so the answer was cut off (unreadable JSON) or timed out. A timeout showed no message at all, because the error had no text.
  - The script is cut at its own structure: screenplay scene headings (INT. / EXT., Fountain `.HEADING`), table rows, Markdown headings, "Scene N" lines, or paragraphs when there are none. Parts are about **Part size** characters (default 3,000); a scene is cut only if it is more than twice that.
  - Text before the first scene (a premise or style note) and a table's column headings go with every part. Each part also gets the cast found so far, so names stay the same. Cast is merged by name across parts.
  - The Import card lists the parts with live progress ("writing · ≈3,120 tokens of 16,384 · 48 s"). **Stop** keeps the finished parts and **Continue** picks up the rest. A failed part can be retried on its own, and the other parts' scenes are kept.
  - A part whose answer is cut off at the token budget is split in two and sent again automatically.
- **New LLM limits** (Global → Prompt rewriter → Limits; saved with the project and in profiles):
  - *Stall timeout* (120 s): no data for this long ends a request.
  - *Give up after* (900 s): the longest a request may take, even while text keeps arriving.
  - *Retries* (2): after a timeout, a dropped connection, a server error or unreadable JSON. A wrong model name or a prompt too big for the context window is not retried.
  - *Context window* (0 = ask the server): vLLM and SGLang report it on `/models`, and Test connection shows it. When it is known, the answer budget is lowered so prompt + answer fit, and a request that can't fit is refused before it is sent, with the numbers.
  - Script import: *Part size*, *Max tokens* per part (16,384), *Thinking* (same as above, or off for Import only), and *H3 guides* (off by default: Import writes scenes, not H3 prompts, so this saves about 10,000 prompt tokens per part).
- **Every LLM request streams its answer.** A slow model that is still writing is no longer mistaken for a dead server. Servers that ignore streaming and answer with one JSON body still work.
  - Rewrite and Split show the same progress line and have a Stop button.
  - Stopping a request closes the connection, so SGLang and vLLM stop generating too.
- **Errors say what happened**, for example "No answer from … for 120 s; raise Stall timeout", "Gave up after 900 s with about 9,800 tokens received", or "cut off at 16,384 tokens before its JSON was complete". Any route error without a message now reports the error type.
- New routes: `POST /reelwright/llm/script/parts`, `POST /reelwright/llm/cancel`; `/reelwright/llm/script` takes one part (`part`, `parts`, `notes`, `known_cast`, `job`, `can_split`); `reelwright.llm` progress events.

## v0.4.1 — 2026-11-03

- **"What H3 receives" no longer repeats sections after a rewrite.** With subject definitions, retention or shot lines set to automatic, a rewritten section used to be added after the automatic lines instead of replacing them, so the same subject or shot appeared twice. Now:
  - a written `<Subject N>` line or `[Shot N]` replaces the automatic line with the same label; lines with new labels follow;
  - the rewriter's reply is tidied before it is shown: a whole prompt returned in one field is split back into its sections, `summary:`-style labels are removed, `<Picture N>`-style names are turned back into the `@` tags they stand for, and sections the editor writes automatically keep their previous text;
  - leading task tags in a written summary are not doubled.
- **A subject keeps its picture reference.** A written `<Subject N>` line that names none of the subject's pictures or videos gets ", shown in `<Picture k>`" added, so H3 still knows which reference it is. A rewritten `[Shot N]` that drops a spoken `<d>` line gets it back word for word.
- **Anchor sheets: Auto, One sheet or Separate.** Each character with several anchors has a three-way choice (new characters default to Auto):
  - *Auto* packs the anchors into one sheet only when the pass would not fit H3's 9 pictures otherwise; when they fit, each anchor is sent on its own at full size;
  - *One sheet* always packs (existing characters keep this, as before); *Separate* never packs.

  The Cast tab shows the actual sheet the render sends and how many pixels each anchor gets in it, and the Scene tab's cast avatar shows the sheet when it is packed (it used to show the first anchor, which looked as if only that one was sent). Sheets have no 3×3 limit: the grid is ceil(√n) columns, as many rows as needed, and cells take the median shape of the pictures, so portrait anchors are no longer letterboxed into square cells. Each anchor gets less of the picture as the grid grows; the size note says how much.
- **Files tab: preview.** Click a file's name, or the eye on any row, to see it next to the tree: pictures, videos (a take or cut shows its video), audio, and text files (`.srt`, `.json`, `.otio`, `.fcpxml`, logs; the first 200 KB). The preview stays put while the tree refreshes and has open-in-tab, delete and close buttons.
- **Typing in a text field during a render no longer scrambles letters.** Progress events re-render the editor many times a second. A field without its own key was rebuilt, focus moved to the new copy, and the caret ended up in the wrong place, so "Sencer" became "Seernc". The focused field is now found again by its help id and position, and keeps what you typed and the caret.
- **A failed face check no longer fails the render.** insightface 0.7.x imports `albumentations` on load, and a mismatched `albumentations`/`albucore` pair raised `ImportError: cannot import name 'median_blur' from 'albucore'` after the take was saved. Reelwright now:
  - retries loading insightface without that part (face analysis does not use it);
  - if the check still can't run, keeps the take, logs a warning and shows "face check skipped" in the render progress;
  - shows the load error in Global → About instead of just "face checks off".
- New route `GET /reelwright/sheet?files=[...]&cell=` returns a sheet as JPEG; `/reelwright/info` adds `insightface_error`.

## v0.4.0 — 2026-11-03

- **New Files tab: disk use, and deleting.** Everything Reelwright wrote to disk, for every project on the server (the open one first), as a tree:
  - each project, then its scenes and takes (starred take marked; pass videos as their own folder);
  - merged cuts grouped by version (video plus side files), autosaved versions, cast training sets;
  - the project's asset folder, each file marked used, unused or not in the project.

  Every row shows its size, its share of the folder above, the number of files and the date. Rows can be sorted in timeline order or largest first. Files can be opened in a new tab.
- **Deleting:** tick rows (a folder or a take takes everything in it) and press Delete, or use a row's bin. Quick selections add common clean-ups: unstarred takes, pass videos, older cuts, autosaves, and things the project no longer lists. The confirmation shows the total and what it means for the open project.
  - A deleted take is also removed from its scene's take list; if it was starred, the newest remaining take becomes starred.
  - Asset files the open project uses are also removed from the project (Ctrl+Z restores the project entries, not the files).
  - Whole projects other than the open one can be deleted (output and input folders).
- **Safety:**
  - only `output/reelwright/<slug>` and `input/reelwright/<slug>` can be named, and the server checks every id again;
  - the open project can't be deleted as a whole, and every `project.json` is kept;
  - a symlink is removed, never its target, and hard links are counted as freeing nothing;
  - the open project's rows are locked while it renders.
- New routes `GET /reelwright/storage` and `POST /reelwright/storage/delete` (`reelwright/files.py`).
- Confirmation dialogs keep line breaks in their message.

## v0.3.9 — 2026-11-02

- **Render-tab preview works with VideoHelperSuite's animated previews turned on.** VHS's "Display animated previews when sampling" setting replaces ComfyUI's `latent_preview.get_previewer`. Its previewer sends its own animated frames to the frontend for whichever node is running, and returns no image. For Reelwright this meant:
  - a preview reappeared under the node after v0.3.5;
  - from v0.3.7 the Render tab caught those frames, which start with 24 bytes of VHS's own data before the JPEG, so they showed as "preview could not be decoded";
  - Reelwright's own preview got nothing (ComfyUI log: "no latent preview … cannot unpack non-iterable NoneType").

  Reelwright now asks ComfyUI's own previewer underneath any wrapper (`render.stock_previewer`, following `__wrapped__`), so VHS is not involved in its preview at all. VHS's animated previews for other nodes are unchanged.
- The preview window drops any header in front of a JPEG, PNG or WebP picture it receives, and its console warning now shows the first bytes of anything it can't decode.
- A previewer that returns no image is reported by name in the ComfyUI log instead of as an unpacking error.

## v0.3.8 — 2026-11-02

- **The Render tab's preview no longer shows a broken image.** The window used to be rebuilt on every re-render straight from the event's URL, and a picture that failed to load stayed on screen as a broken-image icon. It is now one element that lives as long as the editor:
  - each new preview is decoded off-screen and swapped in only once it has loaded;
  - if one can't be decoded, the last good picture stays (or an empty frame says so) and the browser console gets one warning;
  - every preview is shown through a `blob:` URL, the same kind ComfyUI uses for its own node previews; the backend's base64 JPEG is converted in the browser, so nothing depends on `data:` images being allowed;
  - an object URL is released only after its replacement is on screen.
- **Previews follow every sampler step.** The backend's gap between previews went from one second to 0.25 s, and a new preview updates the window in place without re-rendering the tab.
- A preview that can't be made (for example a missing TAESD file) is now a warning in the ComfyUI console, once per pass, instead of a hidden debug line.

## v0.3.7 — 2026-11-02

- **No latent preview under the node, whatever sends it.** v0.3.5 stopped Reelwright's backend from handing previews to ComfyUI, but a backend that hadn't been restarted (or anything else reporting previews for the node) still made ComfyUI paint them under the node. The extension now intercepts ComfyUI's preview stream (`b_preview_with_metadata`, and `b_preview` while a Reelwright node is executing) for Reelwright nodes only and shows those images in the Render tab's preview window. Other nodes keep their previews.

## v0.3.6 — 2026-11-02

- **Autosaved versions can be deleted** (Render tab): a delete button on each row, and **Delete all** in the card header (with confirmation). Only the version snapshots are removed; the project and its latest autosave stay.
- Each version is one line: date and time (from the file name), size, Restore and Delete; the file name is in the tooltip.
- README: why ComfyUI Manager's list doesn't show Reelwright and how to update it.

## v0.3.5 — 2026-11-02

- **Latent preview moves to the Render tab.** ComfyUI painted each sampling step's preview over the whole node. Reelwright now sends the preview to its own Render tab instead: a 200 px window next to the progress bars, about once a second, with the scene, pass and step. ComfyUI's progress bar still updates, and its preview setting (Latent2RGB, TAESD or none) still decides the image. The preview disappears when the run ends.

## v0.3.4 — 2026-11-02

- **Asset descriptions reach characters too.** Scenes already read an asset's description live when it is a scene reference, but a character's subject line only used the Cast tab description, so describing an anchor picture changed nothing. A cast member with no description of its own now uses the description of its first anchor picture that has one, in every scene it appears in, in the LLM's scene context and in the training-set caption. A character's own description still wins.
- The asset inspector shows **where the description is used**: scene prompts (with links), the characters it describes, and why it isn't used where it isn't (the character has its own description, an earlier anchor is used, guide frames only send it when @mentioned, outfit pictures use the outfit's name).
- Scene tab: each reference shows its asset's description (click to edit it in the Assets tab; empty ones are flagged), and each cast member shows the description its subject line uses.
- Cast tab: an empty description shows which anchor's description is used instead.
- Rewrite and Split now give the LLM each reference's description, not only its name.
- New lint: a character with no description and no described anchor.

## v0.3.3 — 2026-11-02

- **Mouse wheel scrolls the timeline sideways** when the scenes don't fit. Shift + wheel scrolls up and down; Alt + wheel still zooms.
- **The playhead only moves where you click** (the ruler or an empty part of a lane). It no longer follows the mouse: the ruler's drag tracking used window listeners that could miss the button release inside ComfyUI and keep running. Drags now track the button state and always end.
- **Dragging the timeline pans it**, from the ruler, an empty lane or a scene block; the playhead stays put and the press doesn't select a scene or drag the node. To scrub, drag the playhead's time label.
- Timeline mouse maths (click, pan, scrub, shot ticks, scene resize, dropping an asset) now account for ComfyUI's canvas zoom; at zoom levels other than 100 % they were off.

## v0.3.2 — 2026-11-02

- **Describe with thinking models** (Qwen3 and similar on SGLang or vLLM): Describe gave the model only 400 tokens. A model that reasons first often used them all on reasoning, so the reply had no answer and Describe said "The model returned no text. Is it a vision model?". How long the reasoning runs varies per picture and per try, which is why it worked sometimes.
  - Describe now allows max(Max tokens, 6000) tokens. If the model still runs out while thinking, it asks once more with thinking off and says so under the answer.
  - New **Thinking** setting (Global → Prompt rewriter): *Model default* or *Off*. Off sends `chat_template_kwargs: {"enable_thinking": false}`, which SGLang and vLLM pass to Qwen3-style chat templates; faster, and Describe then uses 600 tokens.
  - Every LLM call reads the reasoning (`reasoning_content`, `reasoning` or an unclosed `<think>`) and `finish_reason`, so a cut-off reply says "used all N tokens thinking" instead of "no text". The "Is it a vision model?" hint only appears when the model really answered with nothing.
  - Test connection notes when the model thinks before answering.

## v0.3.1 — 2026-11-02

- Script import (Global → Import a script) asks where the proposed scenes go: **at the end**, **after the selected scene**, or **replace all scenes**. Replacing asks first; cast, assets and Global settings stay, and rendered takes stay on disk. The first imported scene is selected, the film's first scene always starts fresh, and Ctrl+Z undoes the import.

## v0.3.0 — 2026-11-02

- **Profiles** (Global tab): save the Global settings under a name, apply them to any project, update or delete them, and mark one as the default for new nodes. They live in `user/reelwright/profiles.json` and are shared by every Reelwright node. A new node starts with the default profile and shows a banner to pick another one.
- **Per-scene quality**: a scene can render as Draft or Final regardless of the Global switch (Scene tab → Generation → Quality, or the scene's right-click menu). Draft scenes get a tag on the timeline. Quality is part of the cache key.
- **Per-scene transitions**: a scene that starts fresh can set its own cut, crossfade or dip, its length and its audio fade (Scene tab → Starts from → Cut into this scene). The Merge card's values are now the defaults.
- Deleting a scene asks first. Deleting the only scene resets it to an empty scene instead of leaving it unchanged.
- **Assets can be deleted** from the inspector or their right-click menu (asset cards and the timeline bin), with confirmation. They are removed from every scene, cast anchor, voice, outfit and the score track; the file stays on disk.
- Ctrl + wheel over the node zooms the ComfyUI canvas, as the wheel does over empty space. Over text fields and lists it does nothing. Alt + wheel still zooms the timeline.
- Render progress: the Render tab shows "Scene k of n" with a bar for the scene and one for the whole run, and the node title shows `rendering k/n · NN%`.
- LLM **Test connection** now reports its result under the button and as a message, and gives up after 20 seconds instead of appearing to do nothing. It tests the URL and model shown on the tab.

## v0.2.2 — 2026-11-02

- Right-click inside the editor no longer opens ComfyUI's node menu, where Delete removed the whole node. Scenes, on the timeline and on the Scene tab strip, get their own menu: open, render, new take, split at playhead, duplicate, move, lock and delete. Text fields keep the browser's copy/paste menu.
- Mouse wheel inside the editor scrolls the editor instead of zooming the canvas. This mostly affected ComfyUI's "Nodes 2.0" mode. Alt or Ctrl + wheel on the timeline still zooms the timeline.
- Dropdown lists stay open when you press or drag their scrollbar, and keep what you typed. The list scrollbar is now always visible.

## v0.2.1 — 2026-11-02

Fixes a crash after a render when the automatic merge failed.

- Merge: the final audio is pinned to 48 kHz stereo (`aformat` plus `-ac 2`). Newer ffmpeg builds (for example conda-forge's) failed with "Cannot select channel layout for the link between filters … and format_out".
- Merge writes to `<cut>.partial.mp4` and renames it only on success, so a failed merge no longer leaves a broken `<slug>_cut_vN.mp4`.
- Node: after a failed merge it outputs the last scene's take instead of the newest cut, and skips any video ffprobe can't read. `merge.probe` now raises a readable `MergeError` instead of `CalledProcessError`.
- Editor: a failed automatic merge now shows a toast and the error in the Merge card.

## v0.2.0 — 2026-11-02

Prompts now follow MiniMax's official Ref2VA guide, and the editor gets searchable pickers, ComfyUI file browsing and vision descriptions.

- Prompt format (MiniMax H3 `ref-en.txt`):
  - six labelled sections, each label on its own line: `subject_definitions:`, `summary:`, `retention_analysis:`, `detailed_description:`, `overall_soundscape:`, `non_diegetic_music:` (empty ones are `N/A`);
  - reference pictures that define a character, place, prop or style become `<Subject N>`, with a subject line from the asset's new description;
  - retention lines name the shots a subject appears in;
  - shots read `[Shot 1] A wide shot: …` and `[Shot 2] At 00:06.000, the shot cuts to …`;
  - speaker IDs follow speaking order in each clip (S1, S2…), so the Cast tab no longer has a Speaker ID field;
  - info lints for a short detailed description, an empty soundscape and an undescribed reference asset.
- LLM:
  - **Download** MiniMax's official H3 guides (Ref2VA and base) into `user/reelwright/guides/`; they are sent with rewrite, split and script import when *H3 guides* is on, otherwise a built-in summary is sent;
  - Rewrite now sees the built pass-1 prompt;
  - **Describe with LLM** for assets (picture, or three video frames) and **From anchors** for cast entries, with your own question; the answer is a suggestion you can use or append.
- Assets: **From ComfyUI** browses ComfyUI's input and output folders (filter by path and kind, multi-select); output files are linked into the project's input folder.
- Pickers: every drop-down is a type-to-filter combobox. Language and LLM model also accept typed values.
- Help: **?** popovers open beside their icon, stay inside the node at any canvas zoom, and can be dragged by the header; tooltips are clamped to the node.
- Render tab: **Merge** moved from the tab bar to the scenes-and-takes table, with a link to the last cut; a **File** column shows each scene's rendered video.
- Take videos are named `<project>_<NN>_<scene title>_<take>.mp4` instead of `video.mp4` (older takes keep their names).
- New routes: `/reelwright/llm/guides`, `/reelwright/llm/describe`, `/reelwright/files`, `/reelwright/import`.

## v0.1.0 — 2026-11-02

First version.

- Reelwright node with an editor inside it: Timeline, Scene, Assets, Cast, Render and Global tabs.
- Scenes of any length: planner on the H3 17k+5 grid (124–362 frames per pass).
  - Long scenes are split at shot cuts or with guided overlaps.
  - Short scenes are trimmed from the shortest pass, keeping handles.
- Scene starts: fresh, last frame of the previous scene, or tail clip of the previous scene (`MiniMaxH3AddGuide` clip and audio).
- Global settings with per-scene overrides: models, VAEs, LoRA stack (add or replace), seed, steps, sampler, size.
- Cast: anchor sheets, outfits, voice, speaker IDs, identity LoRA.
  - Re-anchor rule.
  - Optional insightface drift check.
- References, renumbered per pass in native order:
  - retention labels, keyframes, first and last frames;
  - video soundtracks;
  - budget warnings.
- Structured six-section prompt editor with `@tags`, auto subjects, retention, shots and dialogue, and a per-pass preview.
- Render:
  - content cache keys, takes and stars;
  - resume, lock;
  - render scopes (pending, selected, from playhead, all, new take);
  - draft/final;
  - memory policies, encode-first;
  - live progress.
- Merge (ffmpeg):
  - cut, crossfade, dip, continuation crossfades;
  - loudnorm, ducked score track, colour match;
  - SRT, chapters, OTIO, FCPXML, bundle.
- OpenAI-compatible prompt rewriter, pass splitter and script import. Runs only on click.
- Autosave with versions, undo and redo, keyboard shortcuts, a tooltip and **?** help for every control.
