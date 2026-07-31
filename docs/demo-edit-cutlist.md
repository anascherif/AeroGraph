# AeroGraph Demo — Edit Cut List

Software-agnostic edit decision list (EDL) for fusing the chest-cam video + screen recording + tripod-phone video into a 150–180 second polished demo. Designed for **CapCut Web** but adaptable to any NLE (Kdenlive, Clipchamp, Resolve).

> **Before you start:** You should have three raw clips in a `demo-raw/` folder:
> 1. `chest-cam.mp4` — what AeroGraph saw (from IP Webcam)
> 2. `screen-record.mp4` — the dashboard with bounding boxes, TTS waveforms, safety state machine
> 3. `tripod-phone.mov` — footage of you + the laptop screen for judges
>
> **Sync point:** A single sharp clap visible in both cameras at a known timestamp. Find it first (see Step 2 below).

Final video target specs:

- Duration: 150–180 seconds (2:30–3:00)
- Resolution: 1920×1080
- Frame rate: 30 fps
- Codec: H.264, ~10–15 Mbps
- Audio: 48kHz stereo, -14 LUFS (loud but not clipping)
- Export format: MP4

---

## Step 1 — Import the three clips into CapCut Web

1. Go to [capcut.com](https://www.capcut.com) and sign in (Google account works).
2. Click **Create project** → **New project** (9:16 or 1:1 won't fit; choose **16:9** for a 1920×1080 canvas).
3. Click **Import** in the top-left, drag in all three files from `demo-raw/`.
4. They'll appear in the media panel. Don't drag them onto the timeline yet.

---

## Step 2 — Find the sync clap in each clip

This is the most important step. The clap aligns the two cameras frame-accurately.

1. Double-click `tripod-phone.mov` in the media panel to preview it in the preview window.
2. Scrub the timeline slowly until you see and hear the clap (your hands coming together).
3. Note the timestamp (e.g. `00:08`). Write it down.
4. Repeat for `chest-cam.mp4` — you'll see the hands clapping from the chest-phone's POV. Note the timestamp.
5. For `screen-record.mp4`, the clap won't be visible — but it usually lines up **3 seconds after** you started the screen recording (assuming you started the screen record first and did the clap ~3s in). Estimate from there.

**Example sync times (yours will differ — these are placeholders):**

| Clip | Clap timestamp |
|------|---------------|
| `tripod-phone.mov` | 00:12 |
| `chest-cam.mp4` | 00:08 |
| `screen-record.mp4` | 00:03 |

The clap is **T=0** for the final edit. Everything before it gets trimmed away.

---

## Step 3 — Build the main timeline (tripod phone as base layer)

The tripod-phone footage is your **base layer** — it catches both you and the laptop screen in one frame, which is the ground truth for judges. Place it on **Track V1** first.

1. Drag `tripod-phone.mov` onto the timeline (= Track V1).
2. Trim the **left edge** to your noted clap timestamp (e.g. `00:12`). Everything before the clap is gone.
3. Trim the **right edge** to where you say *"This is AeroGraph"* + 2 seconds of hold. This shave off any post-take fiddling.
4. Mute the audio on V1 (we'll add it back as a separate audio track — see Step 6).

---

## Step 4 — Add the chest-cam as overlay (PIP — picture-in-picture)

The chest-cam is what AeroGraph saw — judges need to see this *alongside* the dashboard.

1. Drag `chest-cam.mp4` onto **Track V2** (above V1).
2. Trim its left edge to the chest-cam clap timestamp (e.g. `00:08`). Trim its right edge to match the end of V1.
3. With the chest-cam clip selected in the timeline, click **Edit** in the toolbar → **Transform**:
   - Position: **top-right corner**
   - Scale: **32%** (about 615×346 px on a 1920×1080 frame — large enough to read clearly, small enough not to block the laptop screen in V1)
   - Position X: `1296` (1920 - 615 - 9 margin)
   - Position Y: `40` (top margin — leaves room for a title card underneath if you want)
4. Add a **subtle border** so the PIP doesn't blend with the laptop screen behind it:
   - Right-click the clip → **Border**
   - Color: `#00ffcc` (cyan — matches the deck)
   - Width: `3px`
   - Softness: `2px`

The result: tripod-phone fills the frame, the chest-cam sits as a cyan-bordered PIP in the top-right, showing the world from AeroGraph's POV.

---

## Step 5 — Add the screen recording as a second PIP (small, bottom-right)

The screen recording is the *proof* the dashboard logged what you said it logged. Keep it small but visible.

1. Drag `screen-record.mp4` onto **Track V3**.
2. Trim its left edge to its clap timestamp (e.g. `00:03`). Trim the right edge to match V1/V2.
3. With the clip selected → **Edit** → **Transform**:
   - Position: **bottom-right corner**
   - Scale: **22%** (about 422×238 px)
   - Position X: `1480`
   - Position Y: `800` (40px from bottom)
4. Border: same as V2 — cyan `#00ffcc`, 2px, softness 1px.

Now the frame has three layers: you + laptop screen (full frame), chest-cam PIP (top-right), dashboard screen-rec PIP (bottom-right).

---

## Step 6 — Audio

The tripod-phone recorded your voice and the laptop's TTS. This is your primary audio track.

1. Right-click the V1 tripod-phone clip → **Detach Audio**. The audio drops onto Track A1.
2. Delete the V1 video clip (we already muted it in Step 3, but now we don't need it muted — we just need the audio).
   - Actually, *don't* delete the video — just keep the detached audio on A1.
3. Listen through A1 end-to-end. Mark any moments of clipping, coughs, or TTS-too-quiet — those go on the **voiceover** track.

**Voiceover track (A2):** record 3–4 short voiceover lines in a quiet room, for moments where the live audio is unclear. Suggested VO lines (sync them to the respective timestamps):

| Timestamp (relative to clap) | Voiceover line | Why |
|------------------------------|---------------|-----|
| ~0:08 | *"AeroGraph is watching what I see."* | Sets context if live audio started quiet |
| ~0:50 | *"It detects 49 object classes on CPU alone."* | Reinforces tech detail over a quiet TTS moment |
| ~1:00 | *"A production unit uses always-listening wake-word detection — no screen, no buttons."* | Reinforces the accessibility framing if your live spoken line got stepped on |
| ~1:20 | *"It answers in natural language."* | Bridges the silence while STT + LLM are processing (~3s) |
| ~3:20 | *"Telegram just delivered a text and a voice note to my family."* | If the live TTS announcement was drowned out |

4. Import your voiceover audio into CapCut, drag it onto Track A2, align the lines to the right timestamps by nudging in 50ms increments.
5. Mix A2 about **-6dB quieter** than A1 — VO is support, not lead.

---

## Step 7 — Act transitions (crossfades)

Mark the boundaries between acts (using the teleprompter's timestamps as a guide):

- **Act 1 → Act 2 boundary** (~01:00 relative to clap): you leaving the frame
- **Act 2 → Act 3 boundary** (~02:10 relative): end of "voice RAG" line
- **Act 3 → Closing boundary** (~03:50 relative): last beat before *"Detect. Remember. Respond."*

For each of the three boundaries:

1. Split V1, V2, V3 at the boundary timestamp (CapCut shortcut: `Ctrl+B` with the playhead at the cut, or right-click → **Split**).
2. Select the right-hand clip and drag it so there's a 0.5s overlap with the left clip.
3. Right-click the overlap → **Add transition** → **Cross dissolve** (or **Dissolve** — same thing).
4. Set transition duration to **500ms** (0.5s).
5. Do this on V1, V2, and V3 so all three tracks crossfade together.

The result: smooth visual fades between acts instead of hard cuts. PIP layers re-establish their position cleanly.

---

## Step 8 — Title cards

Text overlays matching the pitch deck's neon-cyan aesthetic. CapCut calls these **Text** elements.

**Title card 1 — Opening (before Act 1, 3 seconds)**

1. Playhead at `0:00` on the timeline.
2. Add a 3-second black slug on a new track at the start:
   - Click **Effects** → **Solid color** → black, 3 seconds long
3. Add text on top:
   - Click **Text** → **Add text**
   - Content: **"AeroGraph"**
   - Font: any geometric sans (Inter, Outfit, or "Bebas Neue" if available)
   - Size: 120px
   - Color: `#ffffff`
   - Position: centered
4. Add a second text line just below:
   - Content: **"Spatial-temporal memory for visually impaired users"**
   - Size: 28px
   - Color: `#94a3b8` (slate)
   - Position: centered, 80px below the title
5. Duration: 3 seconds, fades in 500ms, fades out 500ms.

**Act divider titles (each is a 1.5s overlay before the act starts)**

Add these as text overlays at each act boundary — appearing *during* the crossfade:

| Time | Text | Color |
|------|------|-------|
| 00:03 (start of Act 1) | `DETECT` | `#00ffcc` |
| 01:00 (start of Act 2) | `REMEMBER` | `#ffaa00` |
| 02:10 (start of Act 3) | `RESPOND` | `#ff0064` |

Formatting for each:

- Font: Clash Display or geometric sans, 800 weight
- Size: 72px
- Letter-spacing: 4px (uppercase, generous spacing)
- Position: centered, vertically about 1/3 from the top
- Duration: 1.5 seconds
- Fade in 300ms, hold 900ms, fade out 300ms

**Title card 2 — Closing (after Act 3, 4 seconds)**

1. Playhead at end of timeline.
2. Add a 4-second black slug.
3. Text line 1: **"Detect. Remember. Respond."** — white, 80px, centered
4. Text line 2: **"github.com/anomalyco/AeroGraph"** — cyan `#00ffcc`, 24px, centered, 60px below line 1
5. Fades in 800ms, holds 2.5s, fades out 700ms.

---

## Step 9 — Trim the 30-second safety confirmation window

Act 3 has a 30-second silence while you wait for the safety state machine to escalate. In the final video, this feels too long. Cut it down:

1. Playhead at the moment the TTS first says *"Are you okay?"* (around 2:35 relative to clap).
2. Split V1, V2, V3 here.
3. Playhead forward to ~5 seconds later (when the TTS says it a second time — around 2:40).
4. Split again here. Delete the middle 5–10s segment.
5. Add a short crossfade (300ms) joining the two outer segments.

The result: viewers see the first TTS prompt, a brief beat, then the escalation. About 4 seconds total instead of 30.

**Optional:** add a small text overlay during this trimmed beat: *"30 seconds with no response"* in 18px slate text, top-center, fades in/out with the segment. This preserves the "30s escalation" mental model without making viewers wait.

---

## Step 10 — Subtle polish

These three refinements take 10 minutes each and elevate the video considerably:

### Jump-cut on the chest-cam

When a new object is detected, do a 0.5s **freeze-frame** of the chest-cam PIP at the moment the bounding box first locks on. This emphasizes the detection. CapCut: right-click the V2 clip at that timestamp → **Split**, right-click the right half → **Add speed** → set to 1% (effectively freeze), trim the frozen segment to 0.5s.

### Slight zoom-in on the Telegram arrival

When you bring your phone into frame showing the Telegram notification (around 3:15 relative), animate the V1 layer to scale from 100% → 130% over 1s, then back down. CapCut: select V1, click **Keyframes** at that timestamp, set Scale 100% → and 1s later Scale 130% → and 1.5s later Scale 100%. This draws the eye toward your phone screen.

### Subtle background music

Very low-volume ambient pad underneath the whole track. Pick something sparse — avoid anything that fights the TTS voice. Suggested free source: YouTube Audio Library, "Ambient" genre, around -25 LUFS so it sits well under your voice. Set it on Track A3 at -18 dB. Fade in 1s at start, fade out 2s at end.

---

## Step 11 — Export

1. Click **Export** in the top-right of CapCut Web.
2. Settings:
   - Resolution: **1920×1080**
   - Frame rate: **30 fps**
   - Format: **MP4 (H.264)**
   - Bitrate: **High** (10–15 Mbps) or **Original** if CapCut offers it
3. Filename: `AeroGraph-demo.mp4`
4. Click **Export**. Wait — browser-rendered exports take roughly the same time as the video duration (so expect ~3 minutes of rendering for a 3-minute video, depending on your laptop).

---

## Step 12 — Upload to YouTube (unlisted)

1. Go to [youtube.com/upload](https://www.youtube.com/upload).
2. Sign in with the Google account tied to the project.
3. Select `AeroGraph-demo.mp4`.
4. Visibility: **Unlisted** (not public — only people with the link can watch).
5. Title: **"AeroGraph — Assistive Innovation Challenge 2026 Demo"**
6. Description:
   ```
   AeroGraph is a spatial-temporal memory engine for visually impaired users.
   Detects objects via a body-worn camera, remembers changes across visits,
   and escalates to family contacts if the user doesn't respond.

   Built for the Assistive Innovation Challenge 2026.
   GitHub: https://github.com/anomalyco/AeroGraph
   ```
7. Wait for processing (a 3-minute 1080p video processes in 2–5 minutes).
8. Copy the **share link**.

---

## Step 13 — Update the pitch deck + Devpost

Once you have the YouTube link, two small updates:

### Pitch deck (`docs/pitch-deck.html`)

Open slide 12 (the "Thank you" closing). Find this line:

```html
GitHub: <a href="https://github.com/anomalyco/AeroGraph" ...>github.com/anomalyco/AeroGraph</a>
```

Add a paragraph above it:

```html
<p class="subtitle reveal" style="margin-top: 12px;">
  Demo video: <a href="https://youtu.be/YOUR_VIDEO_ID" target="_blank" style="color: var(--accent);">youtu.be/YOUR_VIDEO_ID</a>
</p>
```

### Devpost submission

Paste the YouTube link into the demo video field of your Devpost submission. Also paste the GitHub repo URL.

---

## Quick reference — the final cut timeline

| Time | Layer | What's happening |
|------|-------|-----------------|
| 0:00–0:03 | Title | "AeroGraph / Spatial-temporal memory…" black title card, fades in/out |
| 0:03–0:06 | Title transition | `DETECT` text overlay (cyan), crossfade in |
| 0:03–1:00 | Act 1 — Detect | V1 tripod fills frame; V2 chest-cam PIP top-right; V3 dashboard PIP bottom-right. You walk into frame, objects get bounding boxes, TTS speaks. Act 1 ends when you walk out of frame. |
| 1:00–1:01 | Transition | `REMEMBER` text overlay (amber). |
| 1:01–1:35 | Act 2a — Temporal diff | You return, keys moved, dashboard Memory tab shows "keys moved 1.2m", TTS announces the change. |
| 1:35–2:10 | Act 2b — Voice query | You acknowledge the dashboard is a demo view, click mic, ask "are the keys here?", ~3s pause, TTS answers in natural language, you point at the Q&A log. |
| 2:10–2:11 | Transition | `RESPOND` text overlay (magenta). |
| 2:11–2:35 | Act 3 setup | You explain the three signals, freeze, cover camera. |
| 2:35–2:39 | TTS prompts scroll | TTS asks "Are you okay?" — keep just the first prompt, trim the rest. |
| 2:39–3:15 | Escalation | State machine escalates, you bring phone into frame (V1 zoom to 130%), Telegram text + voice note arrive, you hold. |
| 3:15–3:45 | Wrap | "Telegram sent a text and mention", fallback tiers (WhatsApp, Twilio), uncover camera, last fades. |
| 3:45–3:50 | Crossfade | To closing title card. |
| 3:50–3:55 | Closing | "Detect. Remember. Respond." + GitHub link. Fade out. |
| **Total** | ~3:55 | Within the 150–180s target. |

---

## Variables you'll need to fill in

After recording, replace these placeholders with your actual values:

- `SYNC_CLAP_TIMESTAMP_TRIPOD` — when the clap lands on the tripod phone (e.g. `00:12`)
- `SYNC_CLAP_TIMESTAMP_CHEST` — when the clap lands on the chest-cam (e.g. `00:08`)
- `SYNC_CLAP_TIMESTAMP_SCREEN` — approximate clap landing on screen record (e.g. `00:03`)
- `ACT1_END` — when you leave frame at the end of Act 1 (e.g. `01:00`)
- `ACT2A_END` — when you finish the temporal-diff beat (e.g. `01:35`)
- `ACT2B_VOICE_CLICK` — when you click the mic button (e.g. `01:50`)
- `ACT2B_ANSWER_HEARD` — when the TTS finishes speaking the answer (e.g. `02:05`)
- `ACT2_END` — when you finish the "voice RAG" line (e.g. `02:10`)
- `ACT3_TTS_FIRST_PROMPT` — when TTS first says "Are you okay?" (e.g. `02:35`)
- `ACT3_ESCALATION` — when the state machine escalates (e.g. `02:39`)
- `ACT3_PHONE_IN_FRAME` — when you bring the phone into frame (e.g. `02:45`)
- `ACT3_END` — when you uncover the camera (e.g. `03:45`)

For every timestamp above, note it relative to the **sync clap** as T=0, not relative to the raw clip start.

---

## Common issues and fixes

| Issue | Fix |
|-------|-----|
| The PIP chest-cam is jittery because you were walking | Apply **stabilization** to V2 only (CapCut: right-click → Stabilize → smoothness 60%). Don't stabilize V1 — that's the "real world" frame. |
| TTS audio is too quiet in the final mix | Select the A1 audio clip → Adjust → **Volume** → boost +6dB. If it still clips the mix, add a compressor (Effect → Compressor, ratio 4:1, threshold -20dB). |
| The chest-cam and tripod phone are out of sync by ~1 second | Find the clap frame-by-frame by stepping with the arrow keys. CapCut's frame step is 1 frame at 30fps = 33ms. Trim the longer clip by 1s + 0/1/2 frames until they align. |
| A title card text is cut off on small screens | CapCut's safe area isn't shown by default. Keep all text within the central 80% of the frame — avoid the leftmost/rightmost 10%. |
| Export fails in CapCut Web | Reload the page (your project auto-saves). If it still fails, try **Clipchamp** as a fallback with the same cut list — the EDL is software-agnostic. |
