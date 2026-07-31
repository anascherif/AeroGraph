# AeroGraph Demo Recording Setup

Pre-flight checklist for capturing the chest-cam + screen-record video that becomes the edited 150–180s demo.

Two cameras, two purposes:

| Camera | Role | Where it lives |
|--------|------|---------------|
| **Phone #1 (chest)** | Feeds AeroGraph — the system sees what *you* see | Mounted on chest, IP Webcam streaming to the laptop |
| **Phone #2 (tripod)** | Films *you + the laptop screen* for the judges | 3–4 feet away, 3/4 angle catching both your body and the dashboard |

The dashboard is the demo — never hide it. The final edited video combines the chest-cam (full-frame, what AeroGraph sees) with the screen recording (PIP, what the dashboard shows).

---

## T-minus 30 minutes — backend & frontend

### 1. Start the backend

```powershell
cd backend
python -m uvicorn api.main:app --port 8000
```

Wait for `Uvicorn running on http://127.0.0.1:8000`. Hit `http://127.0.0.1:8000/v1/health` in a browser — expect a 200.

### 2. Start the frontend dashboard

```powershell
cd frontend
npm run dev
```

Open `http://localhost:3000`. Confirm:

- **Live tab** — shows the camera feed with bounding boxes when you move objects in frame
- **Memory tab** — shows a session list (or empty if no sessions stored yet)
- **Safety tab** — shows `monitoring` state

### 3. WhatsApp bridge (if QR cooled down)

Only run this if it's been ≥24 hours since your last link attempt. If WhatsApp says *"couldn't link device"* on the QR scan, skip WhatsApp entirely — Telegram alone is enough for the demo.

```powershell
cd notifier-whatsapp
node index.js
```

Scan the QR code that prints in the terminal (or hits `http://127.0.0.1:7878/qr` as a PNG). Wait for `Client is ready!`.

Verify with:

```powershell
curl http://127.0.0.1:7878/health
```

Expect `{"authenticated": true}`. If `false`, the bridge didn't pair — proceed without WhatsApp.

### 4. Telegram sanity check

Send a test message to your Telegram bot (`@AnasAeroGraphbot`) from your personal account. Confirm the bot responds. Also confirm the contact `Mom` has `telegram_user_id: "6408232953"` in `data/safety/contacts.json`.

Trigger a fake safety incident once (cover the camera for 8s, wait 30s) to confirm Telegram receives both the text message and the voice note. Then delete the test incident file under `data/safety/incidents/` so it doesn't clutter the real demo run.

---

## T-minus 10 minutes — cameras

### 5. Chest-phone (IP Webcam)

Open **IP Webcam** on the chest-phone. Configure:

- Video resolution: **1280×720** (or 1920×1080 if your phone handles it)
- Frame rate: **30 fps**
- Audio: disable (we only need video from this source)
- Start the server → note the URL it prints (e.g. `http://192.168.1.5:8080/video`)

On the laptop:

- Verify `backend/config.py` points to this URL (or whichever env var the CameraStream singleton reads)
- Hit the URL in a browser — confirm you see the live feed
- Open the dashboard Live tab — bounding boxes should appear when objects move in frame

**Mount on chest:** Use a phone chest-harness or simply tuck the phone into a shirt pocket with the lens facing forward. The lens should sit at about sternum height, angled slightly downward (so it catches objects on a desk/table in front of you).

Test by walking toward a table with a bottle on it. The bounding box should lock on the bottle within ~1 second.

### 6. Tripod-phone (or second phone on a stand)

Position a second phone **3–4 feet away** from where you'll be standing, mounted on a tripod or stable surface. The angle should catch:

- **Your full upper body** (so judges see you walking, covering the camera, gesturing)
- **The laptop screen** (so the dashboard with bounding boxes is visible in the same frame)

Phone #2 settings:

- Video resolution: **1920×1080**
- Frame rate: **30 fps**
- Audio recording: **on** (this is the primary sync source + your spoken voice)
- Exposure: lock it if your phone allows — auto-exposure drifting mid-take is hard to edit

### 7. Screen recording on the laptop

**Option A — Xbox Game Bar (simplest, built into Windows 10/11)**

1. Press `Win + G` to open Game Bar
2. Click the **capture widget** (camera icon)
3. Set to record video, **include microphone audio**
4. Press `Win + Alt + R` to start recording
5. A small timer appears in the top-right when recording

**Option B — OBS Studio (more control)**

If you want the screen recording to look cleaner (no Game Bar widget visible in the capture):

1. Open OBS, create a new scene
2. Add **Display Capture** for the dashboard (or **Window Capture** limited to the browser running the dashboard)
3. Add **Audio Input Capture** for your laptop's microphone
4. Settings → Output → Recording → format MP4, 1920×1080, 30fps
5. Click **Start Recording**

**Important:** before officially starting, do a 10-second test recording with both phones and the screen record running. Play it back to confirm:

- Dashboard bounding boxes are visible in the screen recording
- Audio isn't clipping (laptop mic isn't too loud)
- Tripod phone is in focus at the distance you'll stand

---

## T-minus 2 minutes — the sync clap

### 8. Open the teleprompter

On a second monitor, tablet, or phone (propped where the tripod phone *can't* see it), open:

```
docs/demo-script.html
```

Arrow keys or swipe scroll it. Font is sized large enough to glance-read from 2–3 feet away.

### 9. Start both recordings

- Start the screen recording (`Win+Alt+R` or OBS)
- Start the tripod phone recording
- Wait **3 seconds of silence** on all sources (gives the editor clean room to splice)

### 10. Sync clap

Stand in front of the tripod phone so your full upper body is in frame. Hold your hands up, palms out, where the chest-phone and the tripod phone can both clearly see them.

**Clap once, sharply and loudly.** A single loud *smack*.

This is the sync point. The clap audio appears on the tripod phone's audio track, and the visual hand-clap appears on both the chest-cam video and the tripod phone video. The editor uses this single moment to align both videos to within a few milliseconds.

After the clap:

- Count silently: *"rolling… three, two, one, action"*
- Begin **Act 1 — Detect** from the teleprompter

---

## During the take

Follow the teleprompter. Key principles:

- **Speak slowly.** The viewer is reading context off the dashboard while you talk. Err on the side of slower.
- **Pause after every line** for 1–2 seconds. This gives you room to trim in the edit without cutting off a word.
- **When an action is in the right-rail of the teleprompter (`Do:`), do it as you finish speaking the line** — not before.
- **If something fails, don't restart the take.** Keep going. Use the fallback line for that beat. You can always re-record just that act later and splice it in.
- **Don't narrate silence.** When you're waiting for the 30-second confirmation window in Act 3, stay quiet. The silence is dramatic and lets the TTS prompts ("Are you okay?") breathe.

---

## After the take

1. **Stop both recordings.**
2. **Watch both clips end-to-end once** before doing anything else.
3. **Note the timestamp on the chest-cam** where each act starts (Act 1 begins, Act 2 begins, Act 3 begins, closing). Do the same for the screen recording and the tripod phone.
4. **Note where the sync clap lands** in each clip's timeline (e.g. "sync clap at 00:08 on chest-cam, 00:12 on tripod phone").
5. **Transfer the files to the laptop** in a folder like `demo-raw/`:
   - `demo-raw/chest-cam.mp4`
   - `demo-raw/tripod-phone.mov` (or `.mp4`)
   - `demo-raw/screen-record.mp4`
6. **Open `docs/demo-edit-cutlist.md`** and follow it.

---

## Quick checklist before you press record

- [ ] Backend running on port 8000 — `/v1/health` returns 200
- [ ] Frontend running on port 3000 — dashboard Live tab shows bounding boxes
- [ ] WhatsApp bridge paired (or skipped — Telegram only)
- [ ] Telegram test message received successfully
- [ ] Chest-phone IP Webcam URL reachable from laptop
- [ ] Chest-phone mounted at sternum height, lens pointing forward
- [ ] Tripod phone 3–4 feet away, framing both you and the laptop screen
- [ ] Screen recording software open (Game Bar or OBS)
- [ ] Teleprompter open on second monitor/phone
- [ ] Three distinct objects ready for Act 2 (keys, bottle, book — or whatever's in the room)
- [ ] Phone with Telegram installed and notifications enabled (for Act 3 demo)
- [ ] Backup plan: dashboard "Safety" tab showing the previous verified incident log (`inc_ebfb4714528b`) in case Telegram is slow live
