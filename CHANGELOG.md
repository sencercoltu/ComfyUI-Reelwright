# Changelog

## v0.10.1 — 2026-11-06

- **Fixed:** on the Global tab, the LLM card's **Limits** and **Script import** rows were squeezed to a few pixels, so their labels drifted out of the card to the left. The fold arrow that v0.10.0 added to the Scene tab's cards used the same style name as these rows. It has a name of its own now (`.rw-card-fold`, `.rw-card-fold-sum`).
- Nothing renders again; only the editor's styles changed.
- **Tests:** `web-test/interact.py` checks that the Global tab's fold rows span their card.

## v0.10.0 — 2026-11-06

Spoken lines stay in their own pass and are said once. A narrator or character keeps one voice from pass to pass. Subtitles and the monitor's captions follow the speech heard in each take. A project can be exported and imported as JSON. Tooltips show cut-off lines and camera text in full, cards fold away, and any text can be copied with a right-click.

### What you will notice after updating

- **Most scenes don't render again.** A prompt changes only for characters you give a voice description (Cast tab). Script import now asks the LLM for each speaking character's voice and fills it in, so scenes from a new import carry it.
- **Subtitles move to where the line is actually heard.** H3 is told when each shot starts, but not when each line is spoken inside a shot. The merge's .srt and the monitor's captions now follow the speech found in the take. Render → Merge → Subtitle times → Planned times gives the old timing.
- **Lines past a seam now come with quick fixes.** The seams stay where they are; you choose which lines to move.
- **The Prompt rewriter works on one pass.** In a scene of several passes it is hidden on Whole scene; open a pass tab to rewrite that pass.

### Lines past a seam, repeats and voices (Script import, Write prompts)

- **Repeated and foreign lines are removed.** When Write prompts gets a spoken line that belongs to another pass, or the same line twice, the line and its sentence are taken out, with a warning. (H3 would say every `<d>` line it is given, so such a line was heard twice.) The request also marks the previous pass's last line as already spoken.
- **Seam quick fixes (Scene tab, Dialogue):** the note under a line that runs past a pass seam has two buttons.
  - **Start after the seam** moves the line just past the seam, so the next pass says all of it.
  - **End before the seam** moves it earlier so it ends just before the seam, when its pass has room. When there is no room the button is off, and its tooltip says why.
  - **Fix N at seams** in the card's head moves every such line, each the smaller way, as one undo step. A line past the scene's end gets *End before the scene's end*.
- **Voice description (Cast tab):** how a character sounds, for example *a deep, warm male voice, slow and measured*. It is written at the character's first line in every pass, as H3's guide asks when a speaker first appears ("…, with a deep, warm male voice, slow and measured, says …"). Each pass is a separate render and H3 does not remember the voice it chose before, so without it the voice could change between passes.
  - Script import fills it in when the LLM gives one (narrators included).
  - Write prompts lists the voices and asks the LLM to describe each one at the speaker's first line.
  - **Continuity rules → Voices: Describe them in every pass** turns it off for the whole project.
- **Voice from a take (Cast tab, Voice → From a take…):** cuts the character's lines out of a scene's starred take, found by listening to it (up to 15 s, at least 2 s). They are saved as a WAV in the project's input folder and become the character's voice reference, sent as audio in every scene they speak in. One undo step; the audio asset stays in the Assets tab.
- **Issues** warns about a character heard in two or more passes with no voice reference and no voice description.

### Subtitles and captions timed to the speech

- The merge listens to each take and finds where speech starts and stops: the level in the speech band, with held tones and hum left out. Each line, in its order, is moved to the nearest start of speech within 4 s. A subtitle stays up while that speech goes on, up to the next line. A line with no speech near it keeps its planned time.
- The Timeline monitor's captions use the same timing (asked once per take and kept).
- **Render → Merge → Subtitle times:** Follow the speech (new default) or Planned times.

### Timeline

- **Full text on hover:** dialogue bars show the whole line, who says it and how, and when. Camera bars show the full camera direction, the words H3 gets and the shot's text. Shot marks show their camera and text.
- **Right-click a bar → Copy text** copies the line or the camera words.

### Scene tab

- **Shots, Dialogue and What H3 receives fold** to their title (the arrow, or a click on the title). A folded card shows a count (*2 shots*, *3 lines · 1 past a seam*). Folded cards stay folded in every scene (`ui.collapsed`, no undo step).
- **Prompt rewriter per pass:** on a pass tab it rewrites that pass's own sections, with your instruction. It uses Write prompts' request for that pass, so it sees the pass's shots and lines and the passes around it. You accept, edit or discard the diff. It is hidden on Whole scene of a scene with several passes; scenes of one pass and raw prompts keep it as before.
- **Copy prompt** on each pass in What H3 receives.

### Copying text

- Text in the editor often can't be selected, because ComfyUI's canvas takes the mouse. **Right-click → Copy text** now works almost anywhere: an issue, a note, a row, a prompt preview, a field label. With text selected you get **Copy selection** too. Text fields keep the browser's own menu.
- **Issues → Copy all** copies every issue, one per line.
- ComfyUI on a LAN address is plain http, where the browser's clipboard API is off; Reelwright falls back to the older copy command there.

### Global tab → Project

- **Export** downloads the whole project as `<folder>.reelwright.json`.
- **Copy JSON** puts the same text on the clipboard.
- **Import…** reads a .json file or pasted JSON: an Export, a saved version, or a bundle's project file. You see what it holds and confirm first.
  - It replaces the project in this node; Ctrl+Z brings the previous one back.
  - When its folder differs from this node's, choose: keep this node's folder, or use the imported one (and the renders made for it on this ComfyUI).
  - Pictures, sounds and renders are files in ComfyUI's input and output folders: the JSON names them but does not carry them.

### Render tab

- **The Passes light explains itself:** hover it for what the colour means and each continuing pass's numbers. Green: close to the footage it continues. Amber: worth a look. Red: likely visible at the seam. Each pass in a take's row does the same.

### Look and feel

- **Tab headers stand out:** the tab bar has its own background, every tab a visible border, and the open tab the accent colour. The Prompt card's pass tabs are set off the same way.
- **Less flicker during renders:** other tabs no longer redraw on every sampling step. Pictures in the Scene and Assets tabs (reference thumbnails, the cast's pictures and anchor sheets, asset cards) are kept between redraws instead of being loaded again.

### For developers

- **Project data** (model.py and model.js, `tests/test_model_parity.py`):
  - cast `voice_desc` (text);
  - `global.continuity.describe_voices` (default true);
  - `global.merge.subtitle_timing`: `"speech"` (default) or `"planned"` (`SUBTITLE_TIMING`);
  - `ui.collapsed` (`{shots|dialogue|h3: true}`).
- **Backend:**
  - New `reelwright/speech.py` (numpy; ffmpeg decodes to 16 kHz mono): `segments`, `align` (in-order dynamic programming, WINDOW 4 s, MISS 2.5), `take_segments` (cached by path, size and mtime) and `timed_lines`.
  - `assemble.speech_timed` feeds the .srt.
  - Routes: `POST /reelwright/speech` (`{file, lines, start?, end?}` → `{lines, segments}`) and `POST /reelwright/voice_from_take` (`{slug, scene_id, take_id, cast_id, lines}` → `{asset, used, seconds}`).
  - `prompt.voice_phrase` and `_dialogue_sentence(…, voiced)`; `llm.drop_foreign_lines` (used by `tidy_pass`) and `llm.pass_voices`; `validate._voice_issues`.
- **Frontend:**
  - `ui.kept(ctx, slot, src, make)` keeps media elements between renders.
  - `section({collapse: {ctx, id, summary}})`.
  - The `detail` prop / `data-detail` is shown first in the tooltip; `data-copy` is the text for Copy text.
  - `copyText`, `copyWithToast`, `copyButton`, `copyMenuItems`; `button({detail})`.
  - `passes.seamFixes` / `seamFixTime`; `global.parseProjectText` / `importProject`.
  - `root.__rwToast`.
- **Tests:**
  - `tests/test_speech.py`, `tests/test_voices.py`; updated `test_llm.py`.
  - `web-test/interact.py` runs a new `v0100_checks()`.
  - The mock has `/reelwright/speech` (lines heard `speechShift` s late) and `/reelwright/voice_from_take`.

## v0.9.0 — 2026-11-06

The Timeline tab is three panels you can resize, without the asset bin. Captions in the monitor follow the film again, and the monitor has a volume control. In the Scene tab a pass tab shows only that pass. Shot and dialogue lists scroll in boxes you can resize. Assets can be put in groups with a description and given tags.

### What you will notice after updating

- **Nothing renders again.** None of these changes touch a prompt, a plan or a cache key. Asset groups and tags only sort the Assets tab.
- **The Timeline tab has no asset bin.** Upload and sort assets in the Assets tab; add them to a scene in the Scene tab (References → Add a reference), with the + on the Soundtrack lane, or with an asset's right-click menu (Add to the current scene).
- **Captions show in the monitor again while the film plays.** Since v0.8.0 the spoken line and the frame count only changed when the tab was redrawn, so they stood still during playback. They now follow the playhead on every frame.

### Timeline tab

- **Three panels:** the monitor with its transport (top left), the selected scene's inspector and summary (top right), and the timeline (below).
  - Drag the bar between the monitor and the inspector to share the width, and the bar under them to set their height. Double-click a bar to reset it. Arrow keys move a focused bar.
  - The sizes are kept in the project, like the zoom (no undo step).
  - The monitor fills its panel; the picture keeps its shape inside.
- **The inspector shows a summary:** the scene's summary (in a scene of several passes, the whole-scene note), then what is on screen at the playhead: the pass (long scenes, with its own summary when it has one), the shot and the spoken line. That part follows the playhead while the film plays. The Render scene / New take row stays visible at the bottom of the panel.
- **Captions:** the spoken line at the playhead is a caption at the bottom of the picture, with the speaker's name. It is timed like the merge's .srt: from the line's time for its own length (Scene tab), or for its reading time, and never past the next line or the scene's end. Before, the bottom-right badge showed a line for 3.5 s whatever its length. **CC** on the transport turns captions off and on.
- **Monitor volume:** a mute button and a volume slider on the transport. They change the take and the soundtrack tracks together, only in the monitor; the merge never reads them.

### Scene tab

- **A pass tab shows only its pass.** On a pass tab the scene's Shots and Dialogue cards are hidden (the pass's own shots and lines are in the tab). Whole scene shows them as before.
- **What H3 receives follows the Prompt card's tabs.** Its own row of pass tabs is gone. Whole scene shows every pass in turn, each with its range, frames and seam, its song excerpt and "Edit this pass by hand"; a pass tab shows that pass. Raw prompts show every pass.
- **Shot and dialogue lists scroll inside a box.** Drag the grip under a list to make it taller or shorter; double-click it to reset. All shot lists share one height and all dialogue lists another, in the scene's cards and in the pass tabs.

### Assets tab

- **Groups:** a group has a name and a description (for example *Harbor set: night exteriors of the harbor: pier, lamps, boats*).
  - **+ Group** makes one; **Edit** renames it and sets its description; ↑ and ↓ order the groups; the arrow folds a group away; deleting a group keeps its assets (they have no group then, and Ctrl+Z brings it back).
  - Put an asset in a group by dragging its card onto the group, with the **Group** field in its settings (type a new name to make a group), or with its right-click menu (Move to group).
  - **By group / By kind:** by group lists your groups in their order, then the assets in no group (pictures, videos, then audio in each). By kind is the old view, with each card's group before its name. A project with groups opens by group.
- **Tags:** free words on an asset (Tags field in its settings, Enter after each). A new tag takes the spelling the project already uses. The tag row above the list filters by a tag; the search field finds groups and tags too.
- **Pickers show the group first** (visual only): "Harbor set · P2 · Harbor plate" in the reference, anchor, voice, soundtrack and score pickers, the soundtrack's + menu and the @ list in prompt fields.
- **Fixed:** the audio cards' waveform pictures were drawn at the top of the tab, over the toolbar, instead of in their cards. A style rule of the soundtrack lane's waveform also matched them.

### Files tab

- **The file list and the preview have a bar between them:** drag it to set the preview's width, double-click to reset. A wider preview shows pictures and videos larger.

### For developers

- **Project data** (model.py and model.js normalise it the same way, `tests/test_model_parity.py`):
  - `asset_groups: [{id, name, description}]`, in order; ids are unique (`g_…` for new ones).
  - asset `group`: a group id or `""` (an unknown id becomes `""`); asset `tags`: strings, runs of spaces, tabs and line breaks made one space, cut to 60 characters, trimmed, empty and repeated ones dropped (`model.asset_tags` / `assetTags`).
  - `ui` keys kept as they are (not normalised; the editor clamps them): `tl_top` (px), `tl_mon` (share 0.15–0.85), `files_prev` (px), `shots_h`, `lines_h` (px), `captions` (bool), `mon_volume` (0–1), `mon_muted` (bool).
- **Frontend:** `ui.splitter({dir, onStart, onMove, onEnd, onReset, sign})`, `ui.resizableList({height, scroll, onResize, children})`, `ui.uiNum`, `ui.rootScale`; a combobox option's `pre` is shown before its label and searched; `model.assetGroupName`; `soundtrack.monitorGain`; `scene.promptTabOf`; `assets.addGroup`. The monitor's `m.overlay(scene, local)` sets the caption and frame count; `setPlayhead` calls it on every frame. Assets added in the editor (upload, ComfyUI files, promoted frames) get `group: ""` and `tags: []`.
- **Tests:** `web-test/interact.py` runs a new `v090_checks()`; parity fixtures for groups and tags.

## v0.8.0 — 2026-11-06

Each pass of a long scene has its own prompt now, and the LLM can write it. New settings work against the loss that builds up at pass seams, and a drift meter measures it. Shot and dialogue rows show their start, end and length. The camera picker has the 20 camera moves of MiniMax's H3 guide, with amplitude, speed and framing. The timeline follows the playhead while the film plays.

### What you will notice after updating

- **Long scenes with a written scene summary render again once.** A scene of several passes no longer sends its summary to every pass: that made every pass play the whole scene's action. Each pass now gets a summary made from its own shots and lines.
  - This affects scenes of several passes in Structured mode whose summary is not empty: every pass without a hand-edited or Split pass prompt. Scenes that continue from them follow, as for any change upstream.
  - A guide picture or clip named only in such a summary is no longer sent to its pass as a reference. It is still anchored.
  - Nothing else renders again. Single-pass scenes, long scenes with an empty summary, raw prompts and hand-edited pass prompts keep their prompts and keys. Shots without the new camera fields are written exactly as before. Every new setting starts at v0.7.0's behaviour, and no other cache key changes.
- **The Prompt card has a tab per pass** (Scene tab) in a scene of several passes: **Whole scene**, then **Pass 1 · 00:00.000–00:14.375**, **Pass 2 · …** in scene times. Single-pass scenes have no tabs.
- **Script import writes longer shots.** Each shot is 2–4 sentences, and each scene's summary is a note on the whole scene. The default token budget per part is 24,576 (was 16,384), because the answers are about 1.5 times as long. A project saved before keeps the budget it has: raise it in Global → Prompt rewriter → Script import → Max tokens if parts get cut off.
- **The timeline follows the playhead while the film plays.** The playhead stays in the middle of the view; at the film's start and end the view stops. Scrolling, a sideways wheel or dragging the lanes pauses following. It comes back when you press Play, click **Follow** on the transport, or when the playhead reaches the middle of the view again.
- **New entries in the Issues list.** A long scene whose passes have no summary of their own gets one warning that lists them. A dialogue line that runs past a pass seam or the scene's end gets a warning. A long scene joined by overlap seams with no shot cuts gets a tip. None of these blocks a render.
- **More camera presets.** A project saved before gets H3's 20 camera moves added once. Your own presets stay first and unchanged. No shot changes, because a shot keeps its own copy of the camera words.

### Each pass has its own prompt

- **Scene tab → Prompt, a tab per pass.**
  - **Whole scene:** the summary is a *whole-scene note* for you and the LLM; it is not sent. The other five sections are *shared by every pass*.
  - **Pass k:** its range, length, frames and seam kind, its own six sections, its shots and its dialogue. An empty section uses the shared text, or the automatic one, and shows it greyed as the placeholder. Each section says where its text comes from (*pass k only*, *shared*, *automatic*); **Use shared** clears the pass's own text.
  - A dot on a tab means the pass has text of its own. Picking a tab also opens that pass in **What H3 receives**.
  - When a pass's own hand-edited or Split prompt replaces it, the tab says so.
- **How a pass is built.** Each section is the pass's own text when written, else the scene's shared text (what every pass got before).
  - The summary: the pass's own when written. A single-pass scene still sends the scene summary. A pass of a longer scene without its own summary gets one made from its shots: who is in it, how many shots, the first sentence of each of its shots, who speaks, then the voice, song and continuation sentences. When the scene summary is empty, the pass gets the v0.7.0 automatic summary, unchanged.
  - The detailed description: a pass's own text is used as written, with `[Shot 1]` its own first shot and times in pass time. Without it, the scene's text is split per pass as before.
- **Pass texts follow the scene when its passes move** (a longer scene, other seams). Each pass gets the text written for the time it covers most. The tab's times turn amber, the Issues list has a note, and **Use the new layout** stores the texts for the new passes (one undo step). Text that no pass gets any more is listed there, and is dropped when you use the new layout or type in a pass.
- **A single-pass scene that still has pass texts** from when it was longer shows them with **Move into the sections** and **Drop them**.
- **Rewrite** in a scene of several passes changes the note and the shared sections; the card says so. Write prompts (below) writes each pass.

### Shots and dialogue

- **Bigger text fields that grow** with the text, for shots and dialogue, in single-pass scenes too.
- **Each row shows its start, end and length in scene time.**
  - A shot's length can be typed. It moves the next shot's start. The last shot's length sets the scene's length, following the timeline's Ripple, Roll or Auto-roll rule.
  - A pass seam inside a shot shows as a chip ("seam 00:25.000"). Seams on shot cuts show none.
- **A dialogue line can have a length** in seconds. Empty, it is estimated from the words: 2.5 words a second (a Chinese, Japanese or Korean character counts as a quarter word), at least 1 s; the estimate is the placeholder.
  - A row warns when its line runs past a pass seam (it is cut off there) or past the scene's end. The Issues list has the same warnings.
  - Write prompts tells the LLM each line's length. The merge's `.srt` shows a line with its own length for that long (at least 0.3 s, still ending before the next line and at the scene's end); lines without one keep the reading-time length.
- In a pass tab, the rows are the pass's own: numbered per pass with the scene number beside them, in scene times, with a continuing shot marked.

### Long scenes: what carries across a pass seam

- **Why later passes got worse.** The VAEs keep no state between calls, so nothing in them gets corrupted. The loss builds up in round trips: at each overlap seam the end of the pass before is decoded to pixels and encoded again for the next pass. That is the anchored overlap (39 frames by default) and its sound, and since v0.7.0 also the last 124 frames as `<Video 1>`.
  - The default video VAE, `minimax_h3_video_vae_int8_convrot.safetensors`, is an int8 file, so every encode with it loses a little detail.
  - A pass read back from the pass cache went through H.264 at CRF 4 with 4:2:0 colour as well.
  - So each pass starts from a slightly worse copy of the pass before.
- **Seams on shot cuts avoid it.** A seam on a cut joins two passes with a plain cut, with no round trip. A long scene with overlap seams and no shot cuts gets a tip in the Issues list with the seam times: add cuts up to the snap distance before a seam, and with Seams on *Overlap only*, set it to Auto or Cuts.
- **New settings:** Global → New scenes and long scenes → **Pass seams**. At their defaults everything works as in v0.7.0.
  - **Guide VAE** (default: *Same as the video VAE*): the VAE that encodes everything a pass is shown: reference pictures and clips, the continuation `<Picture 1>` / `<Video 1>`, and every guide. The video VAE still decodes. Pick the full H3 video VAE (bf16 or fp32) to avoid the int8 encoder's loss. It must be a variant of the H3 video VAE with an encoder; anything else is refused when it loads. It applies to every scene, not only long ones, so setting it renders again nearly every scene.
  - **Carry sound** (on): off, the guide from the pass before is picture only, and the stitch crossfades the sound over the whole overlap instead of only over the picture's crossfade. A tail start keeps the sound of the scene before. The passes after overlap seams render again.
  - **`<Video 1>` at seams** (on): off, a pass after an overlap seam is anchored only, as before v0.7.0, with no 124-frame clip. The prompt, the reference budget and the render agree. It is greyed out while Cast tab → Continuity rules → Continuation → Name it in the prompt is off. The passes after overlap seams render again.
  - **Hand-off: Pixels / Latent · experimental** (Pixels): with Latent, a pass after an overlap seam is anchored with the pass before's own sampled latents for the overlap, with no decode and encode. It falls back to pixels when they don't fit: another canvas size, an overlap or pass not on the 17k+5 grid, or a pass before read from the pass cache without its latents (rendered before v0.8.0 or with Hand-off on Pixels). The sound, the `<Video 1>` clip and tail starts between scenes still go through pixels. The model was trained on guides encoded from pixels, so only real renders can tell whether it helps. The passes after overlap seams render again.
  - **Pass cache: Near-lossless / Lossless** (Near-lossless): Lossless writes pass files and `tail.mp4` as RGB H.264 at qp 0 with FLAC sound, read back bit for bit (a scene's `tail.mp4` is still cut from the joined video when its last pass doesn't hold all of it). It takes about 4 times the disk (a 362-frame pass about 0.7 GB in a test) and writes faster. Nothing renders again: new passes are written lossless, and cached passes are reused. Lossless files don't play in the Files tab's preview.
- **Drift meter** (Render tab). For each pass that continues from footage (an overlap seam, a tail start, a last-frame start), the render compares what the pass made with the footage it was anchored to, on up to 3 of the anchored frames (first, middle, last):
  - **anchor**: the mean pixel difference, 0–255 (ok below 8, bad from 16);
  - **colour**: how far the mean colour moved (ok below 4, bad from 10), with the shift per channel in the tooltip;
  - **sharpness**: generated against guide, 1 = as sharp (ok 0.8–1.25, bad below 0.6 or above 1.6).
  - Each take lists `● P2 4.2 · 1.1 · 0.95` per pass, with an ok / warn / bad light; the tooltip says what the pass continued from, the hand-off used and whether the pass came from the pass cache. The Passes column shows the starred take's worst light, and a take shows the pass-seam settings it was made with when they are not the defaults.
  - The limits are starting values. The trend over the passes matters more than one number.
- **Test it on your GPU.** An A/B on one long scene:
  1. Take a scene of about 50 s with no shot cuts. Set Seams to *Overlap only* (longest pass 362, overlap 39), so it renders in 4 passes. Turn the face check off. Press Render each time: a pending render keeps the seeds, while New take and Variants change them.
  2. Render with the defaults and note the drift of passes 2–4.
  3. Change one setting, render (only the passes it affects render), note the drift and switch it back: Guide VAE = the full H3 video VAE; Carry sound off; `<Video 1>` at seams off; Hand-off = Latent.
  4. Pass cache, once with each choice: delete the scene's pass cache in the Files tab, render and press Stop while pass 4 samples, then render again, so pass 4 starts from pass 3 read back. Compare pass 4's drift.
  5. Turn on what helped together and compare. A setting helps when passes 3–4 stay close to pass 2: anchor flat, sharpness near 1, the colour shift not creeping one way. Watch the seams in the video too.

### Script import and Write prompts

- **Script import asks for more.** Each shot is 2–4 sentences: the framing, who is where, the action, the camera and the sound; spoken words stay in the dialogue. The scene's summary is a note on the whole scene. Older one-line answers import as before. A shot answered in parts (composition, action, sound…) keeps all of them, joined in that order.
- **Write prompts.** The LLM writes each pass of a scene its own six sections, one request per pass, in order, so each pass sees the pass before as just written.
  - Each request gets the project and cast, the whole-scene note, the pass's range, its shots and lines with pass and scene times, lengths and camera, the references it sends, the pass before (its summary, last shot and line) and an outline of the pass after, and MiniMax's Ref2VA rules: 350–500 words of detailed description, `[Shot N]` counted from 1 in each pass, spoken lines word for word in `<d>…</d>`.
  - The answer is checked: when it has one `[Shot N]` per shot, they are numbered from 1 and their cut times set to the timeline's. Warnings say when the description is under 300 or over 650 words, a spoken line is missing or made up, a frame guide is not named, or a hand-edited pass prompt overrides the pass.
  - **Where:** **Write prompts** on the Prompt card (every pass), **Write this pass** on a pass tab, and after a script import **Write prompts for the N imported scenes** (Global → Import a script), one scene after another.
  - It shows which pass it is on ("pass 2 of 3"), and **Stop** keeps the passes already written. A failed scene can be retried; only its missing passes are asked again. Each scene's result is one undo step.
  - A single-pass scene's answer goes into its sections; an empty answered section keeps the scene's text. Raw-mode scenes can't be written this way (their raw text goes to every pass).
  - Budget per pass: Max tokens, at least 8,192 (4,096 with Thinking off); a cut-off answer is asked again with twice the budget, up to 32,768.
- **Split** stays for whole-text pass prompts. Such a prompt still replaces its pass's sections.

### Timeline

- **Follow during playback** (see above). The view moves in steps of 4 px; a 300-scene film plays as smoothly following as not.
- The Camera lane shows the framing, the move (the preset's name) and its amplitude and speed.
- Fixed: a lanes element replaced by a redraw could report a scroll and make the timeline rebuild on every frame.

### H3 camera moves

- **The camera presets are the 20 moves of MiniMax's H3 guide:** Zoom In / Out, Push In, Pull Out, Pan Left / Right, Truck Left / Right, Tilt Up / Down, Pedestal Up / Down, Arc Shot, Tracking Shot, Static Shot, Shake Slightly, Shake Strongly, POV, Roll Clockwise / Counterclockwise. Each puts a natural phrase into the shot, "the camera pushes in". New projects start with these 20 only.
- **Each shot can set the move's amplitude** (Small / Medium / Large) **and speed** (Slow / Normal / Fast). Medium and Normal write nothing. They are greyed out without a move and for Static Shot, POV and the two shakes; picking one of those clears them.
- **And a framing:** extreme wide, wide, medium wide, medium, medium close-up, close-up, extreme close-up, over-the-shoulder, two-shot, insert, low angle, high angle, overhead, Dutch angle.
- **The shot line follows the guide's form**, one sentence for the move: `[Shot 1] A close-up: The camera pushes in with small amplitude at slow speed. <text>.` and `[Shot 2] At 00:05.000, the shot cuts to a low-angle shot: The camera pans left with large amplitude. <text>.` A shot without a framing, amplitude or speed is written exactly as before. Camera words typed by hand work the same way.
- The camera picker lists H3's moves, then your own presets, and takes free text.

### For developers

- **Project data** (Python and JS normalise it the same way, `tests/test_model_parity.py`):
  - `scene.prompt.passes`: `[{start, end, sections: {six sections}}]`, index = pass number − 1; `start` / `end` are the pass's range in scene seconds when the text was written. A non-object item becomes an empty entry, so later indexes don't shift.
  - shot `camera_amp` (`"" | "small" | "large"`), `camera_speed` (`"" | "slow" | "fast"`), `framing` (`""` or one of `FRAMINGS`); other values become `""`. Planner pass shots carry them.
  - dialogue `duration`: seconds > 0 (at most 600), or `null` = estimated.
  - project `camera_version: 2`; below 2 the missing official moves are appended once.
  - `global.long`: `guide_vae: ""`, `carry_audio: true`, `seam_video_ref: true`, `handoff: "pixels" | "latent"`, `pass_cache: "near_lossless" | "lossless"` (unknown values reset). `global.llm.import_max_tokens` defaults to 24576.
- **Takes:** `drift: [{pass, source, frames, anchor_diff, color_shift, rgb_shift, sharpness, level, handoff?, handoff_reason?, pass_cache?}]` and `long` (the five settings) in `index.json`, `meta.json` and `/plan`'s takes. A pass cache `.json` gets `codec` and `drift`; with Latent hand-off a pass keeps `<file key>.latent.safetensors` beside it, pruned with it.
- **Routes:** `POST /reelwright/llm/passes {project, scene_id, passes: [1-based] | null, instruction?, job?}` → `{scene_id, pass_count, passes: [{index, start, end, sections}], warnings, tokens, ms}`; after a later pass fails, also `error`, `reason` and `failed`; `/llm/cancel` → `{cancelled: true, passes, …}`; 400 for a bad body or a raw-mode scene, 502 when the first pass fails. Its `reelwright.llm` events add `scene_id`, `pass`, `passes`, `item`, `items` and `completed`.
- **Model helpers**, each with a JS twin: `pass_texts` / `passTexts` → `{texts, moved, unused, same, stored, entry}`, `relayout_pass_texts` / `relayoutPassTexts`, `pass_sections` / `passSections` → `{own, used, source}`, `dialogue_seconds` / `dialogueSeconds`, `dialogue_spans` / `dialogueSpans`, `camera_sentence` / `cameraSentence`, `framing_phrase` / `framingPhrase`; constants `DEFAULT_CAMERA`, `CAMERA_VERSION`, `CAMERA_AMPS`, `CAMERA_SPEEDS`, `FRAMINGS`, `FRAMING_PHRASE`, `LONG_HANDOFF`, `LONG_PASS_CACHE`. JS only: `setPassSection`, `writePassTexts`, `migrateCamera`. `pass_continuation` / `passContinuation` read `seam_video_ref`.
- **Prompt and LLM:** `prompt.pass_summary`, `prompt._framed_shot`; `llm.write_passes`, `scene_builds`, `pass_request`, `tidy_pass`, `pass_budget`, `PASS_RULES`, `IMPORT_MAX_TOKENS`.
- **Render, cache and merge:** `cache.pass_key(…, extra=None)` with `cache.long_pass_extra` (empty at the defaults), `cache.scene_key(…, carry_audio=True)`; `analysis.long_settings`, `apply_long`, `drift_metrics`, `drift_level`, `DRIFT_LIMITS`; `render.Models.encoder_vae`, `check_guide_vae`, `add_latent_guide`, `save_handoff` / `load_handoff`; `media.save_video_lossless`, `load_video(exact=True)`; `assemble.pass_segments(…, carry_audio=True)` and the segment key `audio_lead_frames` in `merge.build_command`; `merge.subtitle_cues` reads a line's `duration`.
- **Frontend:** `web/rw/passes.js` (pass layout, pass texts, rows, camera options, the Write prompts runner), `rw.llmPasses(project, scene_id, passes, job, instruction)`, `ui.number({placeholder})`, `codeEditor({cls, spellcheck})`. The mock plans passes with model.js and serves `/llm/passes` and drift; `web-test/interact.py` runs `v080_checks()`.
- **Tests:** new `tests/test_pass_prompts.py` and `tests/test_long_continuity.py`; additions to `test_llm.py`, `test_routes.py`, `test_render_flow.py`, `test_continuation.py` and `test_model_parity.py`.

## v0.7.0 — 2026-11-05

A continuing scene now names the frame or clip it continues from in its prompt. Each scene sets how it sits in the merged film: its transition, fades, sound level and colour. The timeline shows the frame that is actually at each time.

### What you will notice after updating

- **Continuing scenes render again once.** Their prompt and references change: the frame or clip they continue from is now also sent as `<Picture 1>` or `<Video 1>` (see below).
  - This affects scenes that start from the last frame or the tail clip of the scene before, and the passes of a long scene that follow an overlap seam. The passes before the first overlap seam come from the pass cache.
  - Other fresh scenes keep their takes.
  - A pass prompt written by hand with fixed numbers (`<Picture 2>`, `<Video 1>`) is left as it was and keeps its take.
  - To keep every take, turn off **Cast tab → Continuity rules → Continuation → Name it in the prompt**. Prompts, references and cache keys are then exactly those of v0.6.1.
- **Transitions and colour match moved from the Merge card into each scene** (Scene tab → **In the cut**). Old projects are converted when they load and merge exactly as before:
  - each scene gets the transition, length and audio fade it used: its own "Cut into this scene" setting, or the Merge card's default;
  - with colour match on, every scene except the reference scene matches the reference scene (the first scene when none was chosen).
  - One difference: when a range merge leaves the reference scene out, v0.6.1 matched the range to its first scene. v0.7.0 measures the reference scene's own take.
- **The text encoder can load again in the middle of a run.** With *Encode all prompts first* on, a pass whose continuation reference is made in the same run can't be encoded up front. That is a pass after an overlap seam, or a continuing scene whose scene before renders in this run. These passes are encoded when they render, so the text encoder is loaded again (from disk once per run, then swapped in by ComfyUI for each of these passes). Turning the naming switch above off brings back the v0.6.1 order.
- When a pass of a long scene names the pass before, the render keeps that pass's last 124 frames in memory (about 1.5 GB at 1344×768) instead of only the overlap (39 frames by default).

### The continuation as a named reference

- **A continuing scene also sends what it continues from as reference 1, and the prompt names it**, as MiniMax's Ref2VA guide does for a first frame or a continued video. It is still anchored with `MiniMaxH3AddGuide`, as before.
  - Last-frame start (also a re-anchored tail start): the last frame of the scene before is `<Picture 1>`.
  - Tail start: the tail clip of the scene before is `<Video 1>`. That is its last 124 frames (fewer when the scene is shorter), with its sound as an `<Audio N>` when an audio slot is free.
  - A pass of a long scene after an overlap seam: the last 124 frames of the pass before, with their sound, are `<Video 1>`.
  - Every other picture, video and audio number moves up by one. `@tail` in your text becomes `<Picture 1>` or `<Video 1>` in such a pass.
- **The prompt defines it, keeps it and starts [Shot 1] from it.** A last-frame start, in v0.6.1 (lines left out are marked …):

  ```
  subject_definitions:
  <Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1>.
  …
  retention_analysis:
  <Subject 1> (appears in [Shot 1]): fully_preserved - identity and appearance are retained.
  …
  detailed_description:
  [Shot 1] A medium shot: <Subject 1> turns to the sea. <Subject 1> (S1) whispers, <d>[English] There you are.</d>
  ```

  and in v0.7.0:

  ```
  subject_definitions:
  <Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 2>.
  <Picture 1> is the first frame of [Shot 1], the last frame of the scene before.
  …
  retention_analysis:
  <Subject 1> (appears in [Shot 1]): fully_preserved - identity and appearance are retained.
  <Picture 1> ([Shot 1] first frame): fully_preserved - the target video starts on this frame and continues from it.
  …
  detailed_description:
  [Shot 1] The shot begins from <Picture 1>. A medium shot: <Subject 1> turns to the sea. <Subject 1> (S1) whispers, <d>[English] There you are.</d>
  ```

  The automatic summary adds "It starts on `<Picture 1>`, the last frame of the scene before." A tail start reads `<Video 1> is the end of the scene before; the target video continues from its final frames.` and `[Shot 1] The shot continues seamlessly from the final frames of <Video 1>.` The task tags add *keyframe completion* for the picture and *video continuation* for the clip (plus *audio reference* for its sound), never *reference generation*.
- **Written prompts get it too.** Sections you write yourself, raw prompts, pass prompts and Split answers get the definition line, the retention line and the [Shot 1] mention where they are missing. Text that uses fixed numbers (`<Picture 2>`, `<Video 1>`) is left as it was: the continuation is then only anchored, and an info issue suggests @tags.
- **It counts in the reference budget:** one picture, or one video with its seconds and an audio slot for its sound. The budget meters count it.
  - With *Auto* packing, cast pictures are packed into a sheet first.
  - A pass that would still send more than 9 pictures, 3 videos or 12 files only anchors the continuation, as before. The scene shows a warning.
  - When all 3 audio slots are taken, the clip goes without its sound (info).
- **Switch:** Cast tab → Continuity rules → **Continuation: Name it in the prompt** (on by default). Off: anchored only, exactly as in v0.6.1.

### Each scene sets how it sits in the cut

- **Scene tab → In the cut**, a new card under Starts from. It changes only the merge, never the render, so a change needs only a new merge.
  - **Join:** how the scene follows the one before when it starts fresh: Cut, Crossfade, Dip to colour, Dissolve, Wipe or Slide (left, right, up or down), Circle open, Pixelize, Radial or Zoom in. Set the length in frames (the seconds are shown) and, for a dip, its colour. A transition takes at most half of either scene.
  - A continuing scene joins by its continuation, as before, and the card says how: the tail overlap is crossfaded (Global → Long scenes → Crossfade), or the repeated last frame is dropped. Its transition can't be picked. The first scene has no join.
  - **Audio fade:** at a plain cut, the sound fades out and in over this many frames (6 by default). Across an overlapping transition it crossfades over the whole transition, as before.
  - **Start** and **End:** fade the picture in from a colour at the scene's first frame, or out to a colour at its last frame, and fade the scene's sound in or out. The scene's length doesn't change.
  - **Sound:** the level of the scene's own sound (−60 to +12 dB) or **Mute**. It applies before loudness normalisation and before the soundtrack's scene-sound level, and the stems include it.
  - **Colour:** match **Off**, **Previous** (the scene before it in the cut, after that scene's own match) or **A scene** (that scene's starred take, measured even when a range merge leaves it out). Then **Brightness** (−1 to 1), **Contrast** (0 to 2) and **Saturation** (0 to 3).
  - **Apply to all…** copies the card to all other scenes, or to the scenes after this one, in one undo step. Scenes that continue the one before keep joining by their continuation.
  - **Reset** puts the whole card back to a new scene's values, and each field has its own reset. Every change has its own name in the History menu.
- **With a soundtrack setting the timing, nothing overlaps.** Every transition other than a cut plays as a dip through the scene's dip colour, half inside each scene, so every scene keeps its place on the song. Before, crossfades and dips always went through black. The card says so, and the Issues list has a note for each such scene.
- **Render tab → Merge scenes** no longer has Hard cuts, Transition, Audio fade, Colour match and the colour reference scene. One line says these are set per scene, with a button that opens the scene's In the cut card.
- Restoring an autosaved version lists "in the cut" for each scene whose settings it changes.

### Timeline

- **A rendered scene shows the frame that is at each time**, not its first frame over and over.
  - The server makes a filmstrip of the starred take once: one row of small frames, one every 0.25 s (at most 600, spread over the whole video, for videos over 150 s). It is kept next to the video.
  - The timeline loads filmstrips only for the scenes near the view, three at a time, and keeps them while the take stays starred.
  - Until a filmstrip arrives, or when it fails, the strip shows the first frame as before. Scenes without a take keep their storyboard picture.
- **Marks for the cut.** A fresh scene with a transition shows a small tag at its top left ("dissolve 18f", "wipe → 16f"; a dip also shows its colour) and a band as long as the transition at its left edge. A fade shows a ramp towards its colour at the scene's edge.

### Issues

- New warnings: a fade-out on a scene that the next scene continues from (the next scene starts from the frame before the fade, so the picture jumps back), a fade-in on a continuing scene, and a colour match that names a scene not in the project.
- New notes: a transition that a soundtrack turns into a dip, one per scene (this replaces the project-wide line); a continuation that is only anchored because the text uses fixed numbers; a tail clip sent without its sound.
- A tail clip sent as `<Video 1>` that is shorter than 2 s gets the same 2–15 s warning as other reference videos.
- When a colour reference scene has no finished take, the scene that uses it is not colour matched. The merge answer (`warnings`) and the server log say so.

### Files tab

- A take's filmstrip (`<video>.filmstrip_54.jpg` and `.json`) is listed as a cache, "made again when needed", and can be deleted on its own.

### For developers

- **Project:** each scene has `merge` (`transition`, `direction`, `frames`, `color`, `audio_frames`, `fade_in` / `fade_out` `{frames, color}`, `audio_fade_in`, `audio_fade_out`, `volume_db`, `mute`, `color_match`, `color_ref`, `brightness`, `contrast`, `saturation`). `normalize_project` and `normalizeProject` build it for older scenes from `scene.transition` and Global → Merge, the same way in both (`tests/test_model_parity.py`). `scene.transition` and `global.merge.hard_cut`, `transition_frames`, `audio_fade_frames`, `color_match` and `color_ref_scene` stay in the JSON, but only that migration reads them. New `global.continuity.name_continuation` (default `true`).
- **Route:** `GET /reelwright/filmstrip?file=<output-relative video>&h=<16–256, default 54>` → `{file, url, interval, count, tile_w, tile_h, duration}`. The `/merge` answer has `warnings` (a list of text).
- **Disk:** `<video name>.filmstrip_<h>.jpg` and `.json` next to the video, made again when the video's size or mtime changes.
- **Merge:** `assemble.scene_merge(s, p)` and `assemble.color_match(result, store, segments)`. Segments carry `transition` / `transition_expr`, `vfade_in_color` / `vfade_out_color`, `edge_in` / `edge_out`, `afade_in` / `afade_out`, `volume_db`, `mute` and `eq`. New `merge.xfade_transition`, `merge.match_gain` and `merge.filmstrip`.
- **Model helpers**, each with a JS twin: `default_merge` / `defaultMerge`, `MERGE_TRANSITIONS`, `MERGE_DIRECTIONS`, `COLOR_MATCH_MODES`, `MERGE_MAX_FRAMES`, `pass_continuation` / `passContinuation`, `continuation_frames` / `continuationFrames`. `scene_media_counts(…, mode=None, continuation=True)` and `sceneBudget(project, scene, pass, continuation = true)` count the continuation and return `continuation` (`"picture"`, `"video"`, `"video_audio"` or `""`).
- **Prompt and render:** `build_pass` returns `continuation` (`{kind, source, frames, label, audio_number}` or `None`). Its entry in `images` or `videos` has `continuation: true` and a `source` (`prev_scene_last`, `prev_scene_tail` or `prev_pass_tail`) instead of an asset. `tag_map["@tail"]` is set in a pass that names it. `Renderer.encode(scene, sr, n, upstream=None, prev_pass=None)`.
- **Frontend:** `web/rw/cut.js` (transition list, `mergeOf`, `ensureMerge`, `joinOf`), `rw.filmstrip(file, h)`, and `viewURL(rel, type, version)`.

## v0.6.1 — 2026-11-04

Fixes from an outside review of v0.6.0. Each claim was checked and reproduced first; the ones that were not bugs are left as they were.

- **Autosave can no longer put an older copy over a newer one.** Only one save runs at a time. A save asked for meanwhile (the autosave after an edit, or Ctrl+S) waits for it and then saves the latest project. A late failure of an older save no longer shows "Autosave offline" after a newer save worked. The footer stays on "Saving…" until the newest save answers.
- **Shortcuts no longer take over browser keys.** Ctrl, Cmd or Alt combinations other than Ctrl+S, Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y go to the browser again: Ctrl+D no longer duplicates a scene, and Ctrl+J, Ctrl+L, Cmd+← and Ctrl+Home no longer move the playhead. Letter shortcuts no longer fire with Shift, so Shift+S no longer splits a scene; Caps Lock does not matter. Plain + and − still zoom the timeline; Ctrl+− and Ctrl+= zoom the page again.
- **Rewrite keeps hand-written subject definitions and retention lines** when the answer leaves them out and their automatic parts are off. They used to be emptied.
- **The node no longer fails after a good render** when the last take's `last.png` (or its video) is missing or unreadable. It outputs a blank frame instead.
- **Pre-flight:**
  - every missing reference file is listed (a code that starts like another's, such as P1 and P10, could be left out);
  - a take whose file paths point outside the output folder counts as missing files instead of stopping the check;
  - video guides are sized from the clip's picture, not from a longer audio track, and a "video" with no picture is refused before any GPU work.
- **Deleting a take while the take list is repaired or rebuilt no longer brings it back** or stars it. The folder is renamed (`.deleting-…`) under the project lock and removed after. A leftover from an interrupted delete shows in the Files tab and can be deleted.
- **Script import:**
  - keeps every shot row of a table that has a rule line between its rows (they vanished into "Table columns");
  - keeps blank lines between paragraphs and scenes in the text each part sends;
  - "Propose scenes" is disabled while the script is cut into parts, so a double click no longer starts two imports.
- **Splitting a scene** whose length lies exactly halfway between two frames no longer adds a frame to the film.
- **Promoting a take's frame to an anchor** while that cast member is being deleted adds the frame to the assets with a warning instead of failing. An edit that fails part-way is undone completely.
- **Smaller fixes:**
  - two version snapshots in the same second no longer overwrite each other;
  - a reference video with no decodable frames fails its scene with a clear message;
  - the Files tab no longer fails when a take folder disappears while it loads;
  - the Assets folder row no longer offers a delete that always failed;
  - a take whose "created" time is not a number (hand-edited `meta.json`) no longer breaks the plan or the Files tab;
  - updating a profile that was deleted elsewhere is refused (and the list reloads) instead of creating a duplicate;
  - uploads that are not multipart, unreadable anchor-sheet pictures and unreadable videos for "promote frame" answer 400 with a reason instead of 500;
  - closing the ComfyUI files browser right after typing in its filter no longer opens it again;
  - the prompt autocomplete highlights the best match again whenever the typed tag changes.
- **For developers:** duplicate explicit job ids are refused by `jobs.running()`; each `/llm/*` request only clears its own job entry and cancel mark; `merge.probe` also reports the video stream's frame count and duration; `cache.created_of()` reads a take's `created` safely; the `file_digest` memo is capped.

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
