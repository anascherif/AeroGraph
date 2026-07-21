# AeroGraph

**A spatial memory engine for visually impaired users.**

AeroGraph gives visually impaired users a "photographic memory" of their physical environment. It detects objects, remembers where they were, notices what's changed since the last visit, and answers natural-language questions about recent visual history — all through voice interaction. A body-worn safety monitor watches for distress signatures and escalates to emergency contacts across Telegram, WhatsApp, and optional Twilio voice calls when the user doesn't respond to a voice check.

Built for the [Assistive Innovation Challenge 2026](https://devpost.com).

---

## Features

### Memory engine

- **Continuous Object Detection** — Real-time CV pipeline identifies structural anchors (doors, desks, chairs) and temporary hazards (boxes, obstacles) from a live camera feed.
- **Spatial Graphing** — Detected objects are embedded into a local vector database, building a mathematical map of the physical space per session.
- **Temporal Diffing** — On return visits, the system compares live detections against stored maps and flags moved objects, new hazards, and missing items with displacement info.
- **Voice-Based RAG Querying** — Ask spoken questions like "where did I leave my keys?" and get grounded, directional answers based on retrieved keyframes and metadata.

### Safety monitor

- **Body-Cam Distress Detection** — Three cheap orthogonal signals (motion energy, vertical tilt via optical flow, brightness EMA drop) fused into a debounced candidate. The "was-moving-within-60s" guard suppresses false alarms for someone sitting still reading, versus someone who was walking a minute ago and is now motionless.
- **Voice-Confirmed Escalation** — 30-second voice confirmation window ("Are you okay? Say I'm okay"). If no reply, the state machine escalates to family contacts.
- **Three-Tier Multi-Channel Alerting** — Telegram (primary, free, works worldwide), WhatsApp via a local Baileys bridge (free, works in Tunisia), optional Twilio voice call (env-guarded, dry-run by default; Tunisia not currently supported for outbound voice).
- **Strict Safe-by-Default Channels** — A contact with no channel preference gets Telegram + WhatsApp (reversible, no-cost). Phone calls require explicit opt-in to avoid TCPA-style consent violations.

### Platform

- **Companion Dashboard** — A Next.js + React dashboard for judges and family to see, in real time, what the camera sees, what the assistant is saying, and what the safety state is. The blind user interacts entirely via voice; the dashboard is a secondary view.
- **Live WebSocket Streams** — Real-time detection frames, snapshots, and safety state events over WebSockets.
- **Fully Local & Free** — No paid APIs, no GPU required. Runs on a CPU-only laptop.

---

## Architecture

```
Camera Feed (phone/laptop/body-worn)
         │
         ▼
┌─────────────────────────────┐
│  Stage 1: Detection         │  YOLO11n (ONNX, CPU)
│  - Structural anchors        │
│  - Temporary hazards        │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Stage 2: Spatial Graph      │  ChromaDB (local vector DB)
│  - Per-session mapping       │
│  - Object embedding          │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Stage 3: Temporal Diff     │  Class + proximity matching
│  - Moved objects             │
│  - New hazards               │
│  - Displacement info         │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Stage 4: RAG Query          │  CLIP + NVIDIA NIM (LLM)
│  - Keyframe retrieval        │
│  - Natural language          │
│  - Spoken answer (TTS)       │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Stage 5: Safety Monitor    │  Motion + Tilt + Brightness
│  - Distress candidate        │
│  - Voice confirmation (30s)  │
│  - Multi-channel escalation  │
└─────────────────────────────┘
```

---

## Tech Stack

| Component | Tool | Notes |
|-----------|------|-------|
| Object Detection | YOLO11n (ONNX) | ~5–15 FPS on CPU |
| Vector Database | ChromaDB | Embedded, local, no server |
| Keyframe Embeddings | CLIP ViT-B/32 | Via `open_clip` |
| LLM Reasoning | NVIDIA NIM (GLM 5.1) | Free tier, OpenAI-compatible |
| Speech-to-Text | Groq Whisper | Free tier, no credit card |
| Text-to-Speech | pyttsx3 / espeak-ng | Fully offline |
| Backend | FastAPI | REST + WebSocket endpoints, `/v1` prefix |
| Frontend | Next.js 16 + React 19 + shadcn/ui + SWR | Tailwind v4, TypeScript, 6-tab dashboard |
| WhatsApp Bridge | `@whiskeysockets/baileys` | Node.js HTTP bridge on port 7878, QR-scan auth |
| Safety Signals | OpenCV (`cv2.absdiff`, Farneback optical flow, EMA) | 3 orthogonal signals fused, CPU-only |

---

## Getting Started

**Prerequisites:** Python 3.10+, Node.js 18+, pnpm, a phone with an IP camera app (or laptop webcam).

### 1. Backend

```bash
# Clone
git clone https://github.com/anascherif/AeroGraph.git
cd AeroGraph

# Install Python dependencies
pip install -r backend/requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys (NVIDIA NIM, Groq, Telegram, Twilio — see .env.example)

# Run the server
uvicorn backend.main:app --reload
```

API docs available at `http://localhost:8000/docs` once running. Full reference in `backend/API_REFERENCE.md`.

### 2. Frontend (companion dashboard)

```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:3000`. The dashboard shows live detections, sessions, diffs, voice query, visual search, and the Safety tab (test controls, contacts, incident log).

### 3. WhatsApp bridge (optional — free Tunisian WhatsApp alerts)

```bash
cd notifier-whatsapp
npm install
node index.js
```

Scan the QR code printed to the terminal with the WhatsApp account you want to send alerts from. Auth state is persisted under `notifier-whatsapp/auth/`. The bridge exposes `POST /send` on port 7878; the backend's `WHATSAPP_BRIDGE_URL` env var points at it.

### 4. Twilio voice calls (optional — paid, env-guarded)

Add `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM` to `.env`. Without these, Twilio runs in dry-run mode and returns `success=True` without making any real calls. Tunisia is not currently supported for outbound Twilio voice calls.

---

## API Overview

All endpoints are versioned under `/v1`. Full schema at `/docs` and in `backend/API_REFERENCE.md`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/session/start` | POST | Start a new capture session |
| `/v1/session/{id}/stop` | POST | Save session to vector DB |
| `/v1/session/{id}/stream` | WS | Live detection stream (JSON frames) |
| `/v1/diff/compare` | POST | Compare current session against stored map |
| `/v1/query` | POST | Ask a question (text) |
| `/v1/query/voice` | POST | Ask a question (audio upload) |
| `/v1/query/speak` | POST | Speak an answer aloud (TTS) |
| `/v1/visual_search` | POST | CLIP image search over keyframes |
| `/health` | GET | Service health check (all subsystems) |
| `/v1/safety/status` | GET | Current safety state + signals snapshot |
| `/v1/safety/contacts` | GET/POST | List / add emergency contacts |
| `/v1/safety/contacts/{id}` | DELETE | Remove a contact |
| `/v1/safety/test_alert` | POST | Trigger a demo alert (skips detection) |
| `/v1/safety/cancel` | POST | Cancel an in-progress confirmation |
| `/v1/safety/voice_heard` | POST | Inject a heard phrase into the STT queue |
| `/v1/safety/incidents` | GET | Recent incident log |
| `/v1/safety/events` | WS | Live safety state-event stream |

---

## Safety Monitor

The body-worn camera signature of a fall or distress event — sudden motion silence + downward tilt + brightness drop — is detected by three cheap orthogonal signals fused into a debounced candidate:

- **Motion energy** — `cv2.absdiff` + `cv2.mean` over a 60s rolling window.
- **Vertical tilt** — Farneback optical flow on an 80×80 subsampled frame (skipped every other frame for CPU budget).
- **Brightness drop** — exponential moving average of the grey-frame mean.

**Fusion rule:** ≥2 of 3 signals flagged for ≥8s, AND the user was moving within the last 60s → candidate fires. The "was moving" guard is the key anti-false-alarm measure: a user sitting still reading for 5 minutes is normal; a user who was walking a minute ago and is now motionless is not.

**State machine:**

```
MONITORING  ──(candidate fires)──►  CONFIRMING  ──(no "ok" in 30s)──►  ESCALATING  ──►  COOLDOWN ──(60s)──►  MONITORING
                  ▲                       │
                  └── STT heard "I'm okay" ─┘
```

The confirmation worker runs in a daemon thread and is wrapped in a try/finally watchdog so an unhandled exception recovers to COOLDOWN — the monitor never wedges in CONFIRMING.

State transitions are lock-guarded and source-state-validated: illegal transitions (e.g., ESCALATING → MONITORING) are rejected with a warning instead of silently wedging the state machine.

---

## Frontend Dashboard

The dashboard is a secondary view for judges and family. The blind user interacts entirely via voice (`/v1/query/voice`, `/v1/query/speak`).

**Six tabs:**

1. **Live** — Real-time camera feed with bounding boxes
2. **Sessions** — Browse past walkthroughs
3. **Compare** — Temporal diff between two sessions
4. **Ask** — Voice query interface
5. **Search** — CLIP visual search
6. **Safety** — Test controls, emergency contacts, incident log with live state updates

Built with Next.js 16, React 19, shadcn/ui, and Tailwind v4 (CSS-first config with custom success/warning/danger tokens). SWR for data fetching.

---

## Project Structure

```
AeroGraph/
├── backend/
│   ├── main.py                     # FastAPI app entrypoint
│   ├── config.py                   # Settings: camera, detection, safety, notifiers
│   ├── api/
│   │   ├── session.py              # Session start/stop/objects/scenes
│   │   ├── stream.py               # WebSocket live stream + snapshot
│   │   ├── diff.py                 # Temporal diff endpoints
│   │   ├── query.py                # Text/voice query, TTS, visual search
│   │   └── safety.py               # Safety status, contacts, test_alert, events
│   ├── pipeline/
│   │   ├── detector.py             # YOLO11n ONNX inference
│   │   ├── camera_stream.py        # CameraStream singleton (one camera, many subs)
│   │   ├── spatial_graph.py        # ChromaDB storage + matching
│   │   ├── temporal_diff.py        # Displacement/hazard comparison
│   │   ├── keyframe_index.py       # CLIP embedding + retrieval
│   │   ├── llm_client.py           # NVIDIA NIM API wrapper
│   │   ├── stt.py                  # Groq Whisper
│   │   ├── tts.py                  # pyttsx3
│   │   ├── safety_monitor.py       # Body-cam distress state machine
│   │   └── safety_store.py         # JSON-backed contacts + incident log
│   ├── notifiers/
│   │   ├── base.py                 # AlertPayload, Contact, filter_contacts_for_channel
│   │   ├── notifier_bus.py         # Parallel fan-out (gather + return_exceptions)
│   │   ├── telegram.py             # Photos + voice (sendMediaGroup + sendVoice)
│   │   ├── whatsapp.py             # HTTP client to Baileys bridge
│   │   └── twilio.py               # Twilio voice calls (dry-run by default)
│   ├── test_temporal_diff.py       # 4 regression tests
│   ├── test_pipeline_bugfixes.py   # 2 regression tests
│   ├── test_api_reference_shape.py # 1 shape-drift test
│   ├── test_safety.py             # 18 safety regression tests
│   ├── API_REFERENCE.md           # 890-line full API reference
│   └── requirements.txt
├── frontend/
│   ├── app/                        # Next.js 16 app directory
│   ├── components/aerograph/       # Dashboard, panels, safety, settings
│   ├── lib/aerograph/              # Client API functions, hooks, types
│   └── package.json                # Next.js 16, React 19, shadcn/ui, SWR
├── notifier-whatsapp/
│   ├── index.js                    # Baileys HTTP bridge (port 7878)
│   └── package.json
├── .env.example
├── data/                           # ChromaDB, sessions, safety (gitignored)
└── README.md
```

---

## Tests

21 regression tests across 4 test files, all passing on a CPU-only laptop:

| Test file | Tests | Coverage |
|-----------|-------|----------|
| `test_temporal_diff.py` | 5 statuses + displacement formula + shared-neighbor gate + location autodiff | Temporal diff engine correctness |
| `test_pipeline_bugfixes.py` | Keyframe + CLIP shape | Pipeline regression fixes |
| `test_api_reference_shape.py` | API response shapes vs docs | Docs/backend drift detection |
| `test_safety.py` | 18 tests | Store CRUD, signals, state machine, transitions, audit fixes |

The safety suite includes regression tests for an internal audit that hardened the state machine: invalid state transitions are rejected, incident IDs use uuid4 not millisecond timestamps, the "heard" queue is bounded to prevent memory exhaustion, STT phrase matching uses word boundaries so "ok" no longer matches "Oklahoma", and the confirmation worker recovers to COOLDOWN on unhandled exceptions.

---

## License

MIT
