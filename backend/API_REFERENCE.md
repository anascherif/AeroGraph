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
  "camera_streaming": false
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