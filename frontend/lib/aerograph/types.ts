// Types mirror the AeroGraph backend contract exactly.

export type Bbox = [number, number, number, number] // [x1, y1, x2, y2]
export type Centroid = [number, number] // [cx, cy]

export interface Health {
  status: string
  yolo_loaded: boolean
  chroma_ready: boolean
  clip_loaded: boolean
  spatial_graph_ready: boolean
  camera_streaming: boolean
  safety_monitor_ready: boolean
  notifier_bus_ready: boolean
  telegram_enabled: boolean
  whatsapp_enabled: boolean
  twilio_enabled: boolean
}

export interface SessionStart {
  session_id: string
  location_name: string
  started_at: number
}

export interface SessionStop {
  session_id: string
  location_name: string
  object_count: number
  scene_count: number
  stopped_at: number
}

export interface SessionSummary {
  session_id: string
  location_name: string
  started_at: number
  stopped_at: number | null
  object_count: number
  scene_count: number
}

export interface SessionsResponse {
  sessions: SessionSummary[]
}

export interface TrackedObject {
  class: string
  total_frames: number
  first_seen: number
  last_seen: number
  last_bbox: Bbox
  last_centroid: Centroid
  frame_w: number
  frame_h: number
  avg_confidence: number
  co_occurred_with: string[]
}

export interface ObjectsResponse {
  session_id: string
  location_name: string
  objects: TrackedObject[]
}

export interface Sighting {
  first_seen: number
  last_seen: number
  frame_count: number
  first_bbox: Bbox
  last_bbox: Bbox
  first_centroid: Centroid
  last_centroid: Centroid
  avg_confidence: number
  frame_w: number
  frame_h: number
}

export interface Scene {
  index: number
  start: number
  end: number
  sightings: Record<string, Sighting>
  persist_counter: number
}

export interface ScenesResponse {
  session_id: string
  scenes: Scene[]
}

export type DiffStatus =
  | 'new'
  | 'missing'
  | 'moved'
  | 'context_changed'
  | 'unchanged'

export type DiffCategory = 'anchor' | 'hazard' | 'personal'

export type DiffDirection =
  | 'left'
  | 'right'
  | 'closer'
  | 'further'
  | 'in_place'

export interface DiffChange {
  object: string
  status: DiffStatus
  category: DiffCategory
  displacement_m: number | null
  direction?: DiffDirection
  co_occurrence_before: string[]
  co_occurrence_after: string[]
  note: string
}

export interface DiffSummary {
  new: number
  missing: number
  moved: number
  context_changed: number
  unchanged: number
}

export interface DiffResponse {
  reference_session: Record<string, unknown>
  current_session: Record<string, unknown>
  location_name: string
  changes: DiffChange[]
  summary: DiffSummary
}

export interface QueryResponse {
  answer: string
  session_id: string
  location_name: string
}

export interface VoiceQueryResponse {
  answer: string
  transcription: string
  session_id: string
  spoken?: boolean
}

export interface VisualSearchResult {
  id: string
  metadata: {
    session_id: string
    timestamp: number
    location_name: string
    objects: string // comma-joined, NOT an array
  }
  distance: number
}

export interface VisualSearchResponse {
  query: string
  results: VisualSearchResult[]
  total: number
  error?: string
}

// WebSocket stream messages
export interface Detection {
  class: string
  bbox: Bbox
  confidence: number
}

export interface StreamStatusMessage {
  type: 'status'
  session_id: string
  streaming: boolean
  include_frame: boolean
}

export interface StreamFrameMessage {
  type: 'frame'
  timestamp: number
  frame_shape: [number, number] // [height, width]
  detections: Detection[]
  roll: number
  frame_b64?: string
}

export type StreamMessage = StreamStatusMessage | StreamFrameMessage

export interface Snapshot {
  available: boolean
  detail?: string
  timestamp?: number
  frame_shape?: [number, number]
  detections?: Detection[]
  roll?: number
  frame_b64?: string
}

// ---------------------------------------------------------------------------
// Safety subsystem
// ---------------------------------------------------------------------------
export type SafetyState = "monitoring" | "confirming" | "escalating" | "cooldown" | "disabled"

export interface SafetyStatus {
  state: SafetyState
  state_since: number
  session_id: string
  location_name: string
  candidate_active: boolean
  candidate_seconds: number
  confirmation_remaining_s: number
  cooldown_remaining_s: number
  was_moving_recently: boolean
  recent_motion_magnitude: number
  brightness_ema: number
  current_incident_id: string
}

export type SafetyChannel = "telegram" | "whatsapp" | "call"

export interface SafetyContact {
  id: string
  name: string
  phone: string
  telegram_user_id: string
  telegram_username: string
  channels: SafetyChannel[]
  notes: string
  created_at: number
}

export interface SafetyIncident {
  incident_id: string
  started_at: number
  trigger: string
  location_name: string
  session_id: string
  outcome: "in_progress" | "cancelled_by_voice" | "cancelled_by_ui" | "escalated_and_sent" | "false_alarm"
  resolved_at: number | null
  note?: string
}

// Safety WebSocket event (partial — matches backend EventBus payload)
export interface SafetyWsEvent {
  type: string
  ts: number
  [key: string]: unknown
}
