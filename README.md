# AeroGraph

**A spatial memory engine for visually impaired users.**

AeroGraph gives visually impaired users a "photographic memory" of their physical environment. It detects objects, remembers where they were, notices what's changed since the last visit, and answers natural-language questions about recent visual history — all through voice interaction.

Built for the [Assistive Innovation Challenge 2026](https://devpost.com).

---

## Features

- **Continuous Object Detection** — Real-time CV pipeline identifies structural anchors (doors, desks, chairs) and temporary hazards (boxes, obstacles) from a live camera feed.
- **Spatial Graphing** — Detected objects are embedded into a local vector database, building a mathematical map of the physical space per session.
- **Temporal Diffing** — On return visits, the system compares live detections against stored maps and flags moved objects, new hazards, and missing items with displacement info.
- **Voice-Based RAG Querying** — Ask spoken questions like "where did I leave my keys?" and get grounded, directional answers based on retrieved keyframes and metadata.
- **Fully Local & Free** — No paid APIs, no GPU required. Runs on a CPU-only laptop.

---

## Architecture

```
Camera Feed (phone/laptop)
        │
        ▼
┌─────────────────────────┐
│  Stage 1: Detection     │  YOLO11n (ONNX, CPU)
│  - Structural anchors   │
│  - Temporary hazards    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Stage 2: Spatial Graph │  ChromaDB (local vector DB)
│  - Per-session mapping  │
│  - Object embedding     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Stage 3: Temporal Diff │  Class + proximity matching
│  - Moved objects        │
│  - New hazards          │
│  - Displacement info    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Stage 4: RAG Query     │  CLIP + NVIDIA NIM (LLM)
│  - Keyframe retrieval   │
│  - Natural language     │
│  - Spoken answer (TTS)  │
└─────────────────────────┘
```

---

## Tech Stack

| Component | Tool | Notes |
|-----------|------|-------|
| Object Detection | YOLO11n (ONNX) | ~5–15 FPS on CPU |
| Vector Database | ChromaDB | Embedded, local, no server |
| Keyframe Embeddings | CLIP ViT-B/32 | Via `open_clip` |
| LLM Reasoning | NVIDIA NIM (GLM 5.1) | Free tier, OpenAI-compatible |
| Speech-to-Text | Groq Whisper / faster-whisper | Free tier, no credit card |
| Text-to-Speech | pyttsx3 / espeak-ng | Fully offline |
| Backend | FastAPI | REST + WebSocket endpoints |

---

## Getting Started

**Prerequisites:** Python 3.10+, a phone with an IP camera app (or laptop webcam)

```bash
# Clone
git clone https://github.com/your-username/aerograph.git
cd aerograph

# Install dependencies
pip install -r backend/requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys (NVIDIA NIM, Groq)

# Export YOLO model to ONNX (one-time)
# See backend/models/ for instructions

# Run the server
uvicorn backend.main:app --reload
```

API docs available at `http://localhost:8000/docs` once running.

---

## API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/session/start` | POST | Start a new capture session |
| `/session/{id}/stop` | POST | Save session to vector DB |
| `/session/{id}/stream` | WS | Live detection stream (JSON frames) |
| `/diff/compare` | POST | Compare current session against stored map |
| `/query` | POST | Ask a question (text or audio) |
| `/health` | GET | Service health check |

Full schema auto-generated at `/docs` (Swagger UI).

---

## Project Structure

```
aerograph/
├── backend/
│   ├── main.py                 # FastAPI app entrypoint
│   ├── api/
│   │   ├── session.py
│   │   ├── stream.py
│   │   ├── diff.py
│   │   └── query.py
│   ├── pipeline/
│   │   ├── detector.py         # YOLO11n ONNX inference
│   │   ├── spatial_graph.py    # ChromaDB storage + matching
│   │   ├── temporal_diff.py    # Displacement/hazard logic
│   │   ├── keyframe_index.py   # CLIP embedding + retrieval
│   │   ├── llm_client.py       # NVIDIA NIM API wrapper
│   │   ├── stt.py              # Speech-to-text
│   │   └── tts.py              # Text-to-speech
│   ├── models/                 # ONNX model files
│   ├── config.py
│   └── requirements.txt
├── .env.example
├── data/                       # ChromaDB storage, session recordings
└── README.md
```

---

## Frontend

The frontend is still being designed. The backend exposes a full REST/WebSocket API ready to be consumed by any client.

---

## License

MIT
