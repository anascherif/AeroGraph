# AeroGraph API Reference

**Base URL:** `http://localhost:8000`  
**Prefix:** All endpoints under `/v1` unless noted.

---

## 1. Health

### `GET /health`

Service health check. Returns status of each pipeline component.

**Response 200:**
```json
{
  "status": "ok",
  "yolo_loaded": true,
  "chroma_ready": true,
  "clip_loaded": false,
  "spatial_graph_ready": true,
  "camera_streaming": false,
  "safety_monitor_ready": true,
  "notifier_bus_ready": true,
  "telegram_enabled": false,
  "whatsapp_enabled": true,
  "twilio_enabled": false
}
```

**Fields:**
| Field | Type | Meaning |
|-------|------|---------|
| `status` | string | Always `"ok"` if server responds |
| `yolo_loaded` | bool | YOLO11n detector loaded and ready |
| `chroma_ready` | bool | ChromaDB directory exists |
| `clip_loaded` | bool | CLIP RN50 model loaded (lazy — flips to `true` on first query) |
| `spatial_graph_ready` | bool | SpatialGraph initialised (JSON manifest loaded) |
| `camera_streaming` | bool | At least one WebSocket subscriber connected to stream |
| `safety_monitor_ready` | bool | SafetyMonitor initialised and running in `monitoring` state |
| `notifier_bus_ready` | bool | NotifierBus (Telegram + WhatsApp + Twilio) constructed on startup |
| `telegram_enabled` | bool | `TELEGRAM_BOT_TOKEN` env var is set |
| `whatsapp_enabled` | bool | `WHATSAPP_BRIDGE_URL` points at a reachable Baileys bridge |
| `twilio_enabled` | bool | `TWILIO_SID`, `TWILIO_TOKEN`, and `TWILIO_FROM` all set |

---

## 2. Session Management

All endpoints under `/v1/session`.

### `POST /v1/session/start`

Begin a new capture session at a named location.

**Request:**
```json
{
  "location_name": "kitchen"
}
```

**Response 200:**
```json
{
  "session_id": "session_a1b2c3d4e5f6",
  "location_name": "kitchen",
  "started_at": 1721308800.123
}
```

**Errors:** 500 if SpatialGraph not initialised.

---

### `POST /v1/session/{session_id}/stop`

Finish a session. Persists manifest + objects to disk.

**Response 200:**
```json
{
  "session_id": "session_a1b2c3d4e5f6",
  "location_name": "kitchen",
  "object_count": 12,
  "scene_count": 8,
  "stopped_at": 1721308920.456
}
```

**Errors:** 404 if session not found.

---

### `GET /v1/session/{session_id}/objects`

List deduplicated objects for a session (one entry per physical object, with co-occurrence neighbour lists).

**Response 200:**
```json
{
  "session_id": "session_a1b2c3d4e5f6",
  "location_name": "kitchen",
  "objects": [
    {
      "class": "cup",
      "total_frames": 12,
      "first_seen": 1721308800.123,
      "last_seen": 1721308850.789,
      "last_bbox": [300, 220, 340, 260],
      "last_centroid": [320, 240],
      "frame_w": 640,
      "frame_h": 480,
      "avg_confidence": 0.92,
      "co_occurred_with": ["obj_3", "obj_7"]
    }
  ]
}
```

**Errors:** 404 if session not found.

---

### `GET /v1/session/{session_id}/scenes`

List raw scenes (3-second windows) with frame-level detections.

**Response 200:**
```json
{
  "session_id": "session_a1b2c3d4e5f6",
  "scenes": [
    {
      "index": 0,
      "start": 1721308800.123,
      "end": 1721308845.789,
      "sightings": {
        "cup": {
          "first_seen": 1721308800.123,
          "last_seen": 1721308845.789,
          "frame_count": 15,
          "first_bbox": [300, 220, 340, 260],
          "last_bbox": [305, 225, 345, 265],
          "first_centroid": [320, 240],
          "last_centroid": [325, 245],
          "avg_confidence": 0.92,
          "frame_w": 640,
          "frame_h": 480
        },
        "bottle": {
          "first_seen": 1721308810.0,
          "last_seen": 1721308840.0,
          "frame_count": 8,
          "first_bbox": [400, 180, 450, 250],
          "last_bbox": [405, 185, 455, 255],
          "first_centroid": [425, 215],
          "last_centroid": [430, 220],
          "avg_confidence": 0.87,
          "frame_w": 640,
          "frame_h": 480
        }
      },
      "persist_counter": 3
    }
  ]
}
```

**Errors:** 404 if session not found.

---

### `GET /v1/sessions`

List every known session across all locations.

**Response 200:**
```json
{
  "sessions": [
    {
      "session_id": "session_a1b2c3d4e5f6",
      "location_name": "kitchen",
      "started_at": 1721308800.123,
      "stopped_at": 1721308920.456,
      "object_count": 12,
      "scene_count": 8
    }
  ]
}
```

---

## 3. Temporal Diff

Endpoints under `/v1/diff`. Compare two sessions and surface changes.

### `POST /v1/diff/compare`

Diff two explicit sessions.

**Request:**
```json
{
  "reference_session_id": "session_a1b2c3d4e5f6",
  "current_session_id": "session_f6e5d4c3b2a1"
}
```

**Response 200:**
```json
{
  "reference_session": { "session_id": "...", "location_name": "kitchen", ... },
  "current_session": { "session_id": "...", "location_name": "kitchen", ... },
  "location_name": "kitchen",
  "changes": [
    {
      "object": "cup",
      "status": "moved",
      "category": "personal",
      "displacement_m": 0.42,
      "direction": "right",
      "co_occurrence_before": ["fridge"],
      "co_occurrence_after": ["fridge"],
      "note": "The cup moved about 0.42 meters to your right."
    },
    {
      "object": "keys",
      "status": "new",
      "category": "personal",
      "displacement_m": null,
      "co_occurrence_before": [],
      "co_occurrence_after": ["wallet"],
      "note": "The keys appeared in the current session."
    }
  ],
  "summary": {
    "new": 1,
    "missing": 0,
    "moved": 1,
    "context_changed": 0,
    "unchanged": 10
  }
}
```

**Status values:**
| Status | Meaning |
|--------|---------|
| `new` | Object only in current session |
| `missing` | Object only in reference session |
| `moved` | Same object_id, centroid shifted > threshold, **and** shares ≥1 neighbour with reference |
| `context_changed` | Object present but neighbour set changed significantly (anchors moved/removed) |
| `unchanged` | Same position, same neighbours |

**Errors:** 404 if either session not found.

---

### `POST /v1/diff/location`

Auto-find the previous session at a location and diff against current.

**Request:**
```json
{
  "location_name": "kitchen",
  "current_session_id": "session_f6e5d4c3b2a1"
}
```

**Response:** Same as `/diff/compare`.  
**Errors:** 404 if no previous session at that location, or current session not found.

---

## 4. Query

Endpoints under `/v1/query`. Natural-language questions about the environment.

### `POST /v1/query`

Answer a text question. Uses spatial graph + LLM (glm-5.1 via NVIDIA NIM).

**Request:**
```json
{
  "question": "Where are my keys?",
  "session_id": "session_f6e5d4c3b2a1",
  "location_name": "kitchen"
}
```

**Fields:**
| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| `question` | yes | — | 1–500 chars |
| `session_id` | no | latest session | If empty, uses most recent session |
| `location_name` | no | "" | Optional filter for visual search |

**Response 200:**
```json
{
  "answer": "Your keys are on the kitchen counter, next to the coffee maker.",
  "session_id": "session_f6e5d4c3b2a1",
  "location_name": "kitchen"
}
```

**Notes:**
- Returns 503 if LLM unavailable (NVIDIA_API_KEY not set or NIM down).
- Returns 400 if no sessions exist.

---

### `POST /v1/query/voice`

Upload audio → transcribe (Groq Whisper → local faster-whisper fallback) → answer.

**Request:** `multipart/form-data`
| Field | Type | Required |
|-------|------|----------|
| `audio` | file | yes |
| `session_id` | string | no |
| `location_name` | string | no |

**Response 200:**
```json
{
  "answer": "Your keys are on the kitchen counter.",
  "transcription": "where are my keys",
  "session_id": "session_f6e5d4c3b2a1"
}
```

**Errors:** 400 empty audio, 422 transcription failed, 503 LLM/STT unavailable.

---

### `POST /v1/query/speak`

Upload audio → transcribe → answer → speak aloud (pyttsx3, non-blocking).

**Request:** Same as `/voice` (`multipart/form-data`).

**Response 200:**
```json
{
  "answer": "Your keys are on the kitchen counter.",
  "transcription": "where are my keys",
  "session_id": "session_f6e5d4c3b2a1",
  "spoken": true
}
```

**Notes:** Audio plays on server machine (not streamed back). Returns immediately after queuing speech.

---

### `POST /v1/query/visual_search`

Search CLIP keyframe index by text description (e.g., "red mug on table").

**Request:**
```json
{
  "query_text": "red mug on table",
  "location_name": "kitchen",
  "n_results": 5
}
```

**Response 200:**
```json
{
  "query": "red mug on table",
  "results": [
    {
      "id": "kf_session_a1b2c3d4e5f6_1721308830000",
      "metadata": {
        "session_id": "session_a1b2c3d4e5f6",
        "timestamp": 1721308830.0,
        "location_name": "kitchen",
        "objects": "cup,bottle"
      },
      "distance": 0.23
    }
  ],
  "total": 1
}
```

**Notes:**
- Returns empty results + error message if CLIP not loaded yet (first query triggers ~2 min download).
- Does not require `session_id`; searches across all locations or filtered by `location_name`.

---

## 5. Live Stream

Endpoints under `/v1/session/{session_id}/`.

### `WS /v1/session/{session_id}/stream`

WebSocket. Subscribes to live camera + detection loop for a session.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `include_frame` | boolean | `false` | If true, includes base64 JPEG (`frame_b64`) in each frame message |

**Connection:**
- Validates session exists (closes with code 4004 if not).
- Gets/creates shared `CameraStream` singleton, binds it to the session.
- Sends initial status ack, then one message per detection pass (~5 FPS).

**Messages (server → client):**

**Status ack (first message after accept):**
```json
{
  "type": "status",
  "session_id": "session_a1b2c3d4e5f6",
  "streaming": true,
  "include_frame": false
}
```

**Frame message (repeated):**
```json
{
  "type": "frame",
  "timestamp": 1721308850.123,
  "frame_shape": [480, 640],
  "detections": [
    { "class": "cup", "bbox": [300,220,340,260], "confidence": 0.91 },
    { "class": "bottle", "bbox": [400,180,450,250], "confidence": 0.85 }
  ],
  "roll": 0,
  "frame_b64": "/9j/4AAQSkZJRgABAQ..."  // only if include_frame=true
}
```

**Close codes:**
| Code | Reason |
|------|--------|
| 4004 | Session not found |
| 1000 | Normal closure (client disconnected) |

**Notes:**
- Single `CameraStream` instance shared across all WS connections (subscriber model).
- Camera auto-starts on first subscriber, auto-stops when last unsubscribes.
- `roll` field reserved for future IMU integration (currently 0.0).

---

### `GET /v1/session/{session_id}/snapshot`

One-shot REST snapshot of latest frame + detections.

**Query params:**
| Param | Type | Default |
|-------|------|---------|
| `include_frame` | boolean | `true` |

**Response 200:**
```json
{
  "available": true,
  "timestamp": 1721308850.123,
  "frame_shape": [480, 640],
  "detections": [
    { "class": "cup", "bbox": [300,220,340,260], "confidence": 0.91 }
  ],
  "roll": 0,
  "frame_b64": "/9j/4AAQSkZJRgABAQ..."
}
```

**Response if camera not running:**
```json
{
  "available": false,
  "detail": "Detection loop not running."
}
```

---

## 6. Runtime States (from `/health`)

| State | When `true` | When `false` |
|-------|-------------|--------------|
| `yolo_loaded` | YOLO ONNX loaded at startup | Model export/load failed |
| `chroma_ready` | ChromaDB path exists | First run, dir not created |
| `clip_loaded` | First query triggered CLIP load (lazy) | Not yet loaded (startup) |
| `spatial_graph_ready` | SpatialGraph initialised | JSON load failed |
| `camera_streaming` | ≥1 WS subscriber connected | No active subscribers |

---

## 7. Common Error Shapes

**404 Not Found:**
```json
{ "detail": "Session 'session_xxx' not found." }
```

**503 Service Unavailable:**
```json
{ "detail": "LLM not available. Check NVIDIA_API_KEY." }
```
```json
{ "detail": "CLIP model not available" }
```

**400 Bad Request:**
```json
{ "detail": "No active session. Start one first." }
```

**422 Unprocessable Entity:**
```json
{ "detail": "Could not transcribe the audio" }
```

---

## 8. Environment Variables (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `NVIDIA_API_KEY` | Yes (for LLM) | NVIDIA NIM API key for `glm-5.1` |
| `GROQ_API_KEY` | Yes (for STT) | Groq API key for Whisper transcription |
| `CAMERA_SOURCE` | No | Camera index or URL (default `0`) |

---

## 9. Quick curl Examples

```bash
# Health
curl http://localhost:8000/health

# Start session
curl -X POST http://localhost:8000/v1/session/start \
  -H "Content-Type: application/json" \
  -d '{"location_name": "kitchen"}'

# Query text
curl -X POST http://localhost:8000/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Where are my keys?", "session_id": "session_xxx"}'

# Diff by location
curl -X POST http://localhost:8000/v1/diff/location \
  -H "Content-Type: application/json" \
  -d '{"location_name": "kitchen", "current_session_id": "session_yyy"}'

# Snapshot
curl "http://localhost:8000/v1/session/session_xxx/snapshot?include_frame=true"
```

---

## 10. WebSocket Client Example (Python)

```python
import asyncio
import websockets
import json

async def listen():
    uri = "ws://localhost:8000/v1/session/session_xxx/stream?include_frame=false"
    async with websockets.connect(uri) as ws:
        print(await ws.recv())  # status ack
        async for msg in ws:
            data = json.loads(msg)
            if data["type"] == "frame":
                print(f"Frame {data['timestamp']}: {len(data['detections'])} detections")

asyncio.run(listen())
```

---

## 11. Safety Monitor

All endpoints under `/v1/safety`.

### Overview

The safety subsystem detects body-cam distress signals (motion silence + downward tilt + brightness drop), prompts the user with TTS ("Are you okay?"), waits 30 seconds for a voice/STT response, and escalates to family contacts (Telegram, WhatsApp, optional Twilio voice call) if no confirmation is received.

**State machine:**
```
MONITORING ─(candidate fires)→ CONFIRMING ─(timeout, no "ok")→ ESCALATING ─(notifiers)→ COOLDOWN
     ↑                                                                  │
     └─────────────── STT heard "i'm okay" / cancel button ────────────┘
```

**Detection signals (3-signal fusion, at least 2 must flag):**
- Motion energy — `cv2.absdiff` between consecutive greyscale frames, rolling 60s window
- Vertical tilt — Farneback optical flow at 80×80, flags when mean `|vy|` > 4px/frame
- Brightness drop — EMA of grey-frame mean falls below 40 (out of 255)

**Anti-false-alarm guard:** candidate fires only if the user was physically moving within the last 60 seconds (motion energy > threshold in the trailing window). A user who has been sitting still for 5 minutes does not trigger an alert.

**Contacts** are stored in `data/safety/contacts.json`. **Incidents** are append-only in `data/safety/incidents.json`.

---

### `GET /v1/safety/status`

Current monitor state and live signal values. Safe to poll from a dashboard every 2–5 seconds.

**Response 200:**
```json
{
  "state": "monitoring",
  "state_since": 1721308800.123,
  "session_id": "session_a1b2c3",
  "location_name": "kitchen",
  "candidate_active": false,
  "candidate_seconds": 0.0,
  "confirmation_remaining_s": 0.0,
  "cooldown_remaining_s": 0.0,
  "was_moving_recently": true,
  "recent_motion_magnitude": 8.3,
  "brightness_ema": 142.5,
  "current_incident_id": ""
}
```

**Fields:**
| Field | Type | Meaning |
|-------|------|---------|
| `state` | string | `"monitoring"` \| `"confirming"` \| `"escalating"` \| `"cooldown"` \| `"disabled"` |
| `state_since` | float | Unix timestamp when current state began |
| `session_id` | string | Active capture session (empty if no session running) |
| `location_name` | string | Location of the active session |
| `candidate_active` | bool | True if ≥2 signals are flagged and the countdown is running |
| `candidate_seconds` | float | Seconds elapsed since candidate first fired |
| `confirmation_remaining_s` | float | Seconds left in the voice confirmation window (0 if not confirming) |
| `cooldown_remaining_s` | float | Seconds until the monitor re-arms (0 if not in cooldown) |
| `was_moving_recently` | bool | At least one motion sample above threshold in the last 60s |
| `recent_motion_magnitude` | float | Peak motion energy in the trailing 60s window |
| `brightness_ema` | float | Exponential-moving-average of grey-frame brightness (0–255) |
| `current_incident_id` | string | ID of the incident being processed (empty if idle) |

---

### `WS /v1/safety/events`

WebSocket stream of safety state transitions and alert lifecycle events. Connect to get real-time updates on the dashboard without polling.

**Connection:** `ws://localhost:8000/v1/safety/events`

On connect the server sends an initial snapshot:
```json
{"type": "snapshot", "ts": 1721308800.0, "data": {"state": "monitoring", ...}}
```

**Subsequent events (sent by the server):**

State transition (published whenever `state` changes):
```json
{"type": "state", "ts": 1721308900.0, "from": "confirming", "to": "cooldown", "reason": "alert cancelled"}
```

Candidate detected (≥2 signals flagged, 8s debounce running):
```json
{"type": "candidate_started", "ts": 1721308850.0, "flagged_signals": 2}
```

Candidate reset (signals dropped before debounce elapsed):
```json
{"type": "candidate_reset", "ts": 1721308860.0, "reason": "signals no longer sustained"}
```

Escalation begun:
```json
{"type": "escalating", "ts": 1721308900.0, "incident_id": "inc_xxx", "contacts_count": 2, "keyframes_count": 3}
```

Alert cancelled:
```json
{"type": "cancelled", "ts": 1721308900.0, "incident_id": "inc_xxx", "outcome": "cancelled_by_voice", "heard_text": "i'm okay"}
```

---

### `GET /v1/safety/contacts`

List all emergency contacts.

**Response 200:**
```json
{
  "contacts": [
    {
      "id": "c_840302774d74",
      "name": "Mom",
      "phone": "+21612345678",
      "telegram_user_id": "",
      "telegram_username": "@mom",
      "channels": ["telegram", "whatsapp"],
      "notes": "primary contact",
      "created_at": 1721308800.0
    }
  ]
}
```

---

### `POST /v1/safety/contacts`

Add a new emergency contact.

**Request:**
```json
{
  "name": "Mom",
  "phone": "+21612345678",
  "telegram_user_id": "123456789",
  "telegram_username": "",
  "channels": ["telegram", "whatsapp"],
  "notes": "primary contact"
}
```

`channels` is optional. If omitted the contact receives alerts on **all** channels. Valid channel values: `"telegram"`, `"whatsapp"`, `"call"`.

**Response 201:** Returns the created contact object (same shape as above, with `id` and `created_at` populated).

**Response 503:** Safety store unavailable.

---

### `DELETE /v1/safety/contacts/{contact_id}`

Remove a contact.

**Response 200:**
```json
{"deleted": true, "contact_id": "c_840302774d74"}
```

**Response 404:** Contact not found.

---

### `POST /v1/safety/test_alert`

Trigger the full alert cycle end-to-end, bypassing detection, for a judge demo or smoke test.

- Enters `confirming` state immediately (skips the 8s candidate debounce)
- Plays "Are you okay?" via TTS
- Waits 30s for a `voice_heard` call with "i'm okay"
- If no confirmation → escalates → fan-out to contacts → `cooldown`

**Response 200:**
```json
{"triggered": true, "state": "confirming"}
```

**Response 409:** Monitor is not in `monitoring` state (e.g. already confirming or in cooldown). Use `GET /v1/safety/status` to check.

**Response 503:** Safety monitor not available.

---

### `POST /v1/safety/cancel`

Manually cancel the in-flight confirmation from the dashboard "I'm okay" button. Only works during `confirming` state.

**Response 200:**
```json
{"cancelled": true, "state": "cooldown"}
```

**Response 200 (no-op):** Returns `{"cancelled": false, "state": "monitoring"}` if not confirming.

---

### `POST /v1/safety/voice_heard`

Inject a text transcript into the confirmation listener. Used by:
- The dashboard "I'm okay" button (sends `"i'm okay"`)
- An external STT loop that pipes recognized speech

**Request:**
```json
{"text": "i'm okay"}
```

Recognised phrases (case-insensitive):
`"i'm okay"`, `"i am okay"`, `"im okay"`, `"okay"`, `"ok"`, `"yes"`, `"fine"`, `"cancel"`, `"stop"`, `"i'm fine"`, `"i am fine"`

**Response 200:**
```json
{"queued": true, "state": "confirming"}
```

**Response 503:** Safety monitor not available.

---

### `GET /v1/safety/incidents?limit=50`

Incident log (append-mostly). Each escalation or cancellation appends one record.

**Response 200:**
```json
{
  "incidents": [
    {
      "incident_id": "inc_1721308900",
      "started_at": 1721308800.0,
      "trigger": "manual test_alert (detection skipped)",
      "location_name": "kitchen",
      "session_id": "session_a1b2c3",
      "outcome": "cancelled_by_voice",
      "resolved_at": 1721308830.0,
      "note": "heard: \"i'm okay\""
    }
  ],
  "total_returned": 1
}
```

`outcome` values: `"in_progress"` | `"cancelled_by_voice"` | `"cancelled_by_ui"` | `"escalated_and_sent"` | `"false_alarm"`

**Query params:** `limit` (int, 1–500, default 50)

---

### Alert Fan-out

When escalation fires, the server sends to all three notifiers in parallel via `asyncio.gather(return_exceptions=True)`:

| Channel | Requirement | Content |
|---------|-------------|---------|
| **Telegram** | `TELEGRAM_BOT_TOKEN` env var | Text alert + up to 3 keyframe photos (sendMediaGroup) + TTS voice note (sendVoice) |
| **WhatsApp** | Baileys bridge at `WHATSAPP_BRIDGE_URL` (default `http://127.0.0.1:7878`) | Text + up to 3 base64 JPEG images |
| **Twilio** | `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM` all set | Outbound voice call reading the alert via TwiML `<Say>`. **Dry-run by default** (no real call unless env vars are present). **Note: Tunisia (+216) numbers are not supported for outbound Twilio voice calls.** |

If any notifier fails (network error, missing credentials, crashed), the others continue. No alert is silently dropped — the `GET /v1/safety/incidents` log records the outcome for every incident.

---

### WebSocket Event Shapes

Connect with JavaScript:

```javascript
const ws = new WebSocket("ws://localhost:8000/v1/safety/events");
ws.onmessage = (evt) => {
  const msg = JSON.parse(evt.data);
  if (msg.type === "snapshot") {
    renderSafetyStatus(msg.data);     // full status object
  } else if (msg.type === "state") {
    showStateTransition(msg.from, msg.to, msg.reason);
  } else if (msg.type === "escalating") {
    showEscalationAlert(msg.incident_id, msg.contacts_count);
  } else if (msg.type === "cancelled") {
    showCancelledBanner(msg.outcome, msg.heard_text);
  }
};
```

Connect with Python:

```python
import asyncio, websockets, json

async def listen():
    uri = "ws://localhost:8000/v1/safety/events"
    async with websockets.connect(uri) as ws:
        snapshot = json.loads(await ws.recv())
        print("snapshot:", snapshot["data"]["state"])
        async for msg in ws:
            data = json.loads(msg)
            print(f"event: {data['type']}", data)

asyncio.run(listen())
```