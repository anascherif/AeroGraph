"use client"

import { getApiBase } from "./config"
import type {
  DiffResponse,
  Health,
  ObjectsResponse,
  QueryResponse,
  ScenesResponse,
  SessionsResponse,
  SessionStart,
  SessionStop,
  Snapshot,
  VisualSearchResponse,
  VoiceQueryResponse,
  SafetyStatus,
  SafetyContact,
  SafetyIncident,
} from "./types"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = "ApiError"
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiBase()
  let res: Response
  try {
    res = await fetch(`${base}${path}`, {
      ...init,
      headers: {
        ...(init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...getAuthHeaders(),
        ...init?.headers,
      },
    })
  } catch (err) {
    throw new ApiError(
      0,
      `Cannot reach the AeroGraph backend at ${base}. Is it running?`,
    )
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      // ignore parse errors
    }
    throw new ApiError(res.status, detail)
  }

  return res.json() as Promise<T>
}

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {}
  const token = window.localStorage.getItem("aerograph:auth-token")
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

// ---- Health ----
export const getHealth = () => request<Health>("/health")

// ---- Sessions ----
export const listSessions = () =>
  request<SessionsResponse>("/v1/sessions")

export const startSession = (location_name: string) =>
  request<SessionStart>("/v1/session/start", {
    method: "POST",
    body: JSON.stringify({ location_name }),
  })

export const stopSession = (sessionId: string) =>
  request<SessionStop>(`/v1/session/${sessionId}/stop`, { method: "POST" })

export const getSessionObjects = (sessionId: string) =>
  request<ObjectsResponse>(`/v1/session/${sessionId}/objects`)

export const getSessionScenes = (sessionId: string) =>
  request<ScenesResponse>(`/v1/session/${sessionId}/scenes`)

export const getSnapshot = (sessionId: string, includeFrame = true) =>
  request<Snapshot>(
    `/v1/session/${sessionId}/snapshot?include_frame=${includeFrame}`,
  )

// ---- Diff ----
export const diffCompare = (
  reference_session_id: string,
  current_session_id: string,
) =>
  request<DiffResponse>("/v1/diff/compare", {
    method: "POST",
    body: JSON.stringify({ reference_session_id, current_session_id }),
  })

export const diffLocation = (location_name: string, current_session_id: string) =>
  request<DiffResponse>("/v1/diff/location", {
    method: "POST",
    body: JSON.stringify({ location_name, current_session_id }),
  })

// ---- Query ----
export const queryText = (
  question: string,
  opts?: { session_id?: string; location_name?: string },
) =>
  request<QueryResponse>("/v1/query", {
    method: "POST",
    body: JSON.stringify({ question, ...opts }),
  })

export const queryVoice = (
  audio: Blob,
  opts?: { session_id?: string; location_name?: string; speak?: boolean },
) => {
  const form = new FormData()
  form.append("audio", audio, "recording.webm")
  if (opts?.session_id) form.append("session_id", opts.session_id)
  if (opts?.location_name) form.append("location_name", opts.location_name)
  const endpoint = opts?.speak ? "/v1/query/speak" : "/v1/query/voice"
  return request<VoiceQueryResponse>(endpoint, {
    method: "POST",
    body: form,
  })
}

export const visualSearch = (
  query_text: string,
  opts?: { location_name?: string; n_results?: number },
) =>
  request<VisualSearchResponse>("/v1/query/visual_search", {
    method: "POST",
    body: JSON.stringify({ query_text, ...opts }),
  })

// ---- Safety ----
export const getSafetyStatus = () =>
  request<SafetyStatus>("/v1/safety/status")

export const getSafetyContacts = () =>
  request<{ contacts: SafetyContact[] }>("/v1/safety/contacts").then(
    (r) => r.contacts,
  )

export const createSafetyContact = (contact: Omit<SafetyContact, "id" | "created_at">) =>
  request<SafetyContact>("/v1/safety/contacts", {
    method: "POST",
    body: JSON.stringify(contact),
  })

export const deleteSafetyContact = (id: string) =>
  request<{ deleted: boolean; contact_id: string }>(
    `/v1/safety/contacts/${id}`,
    { method: "DELETE" },
  )

export const testSafetyAlert = () =>
  request<{ triggered: boolean; state: string }>("/v1/safety/test_alert", {
    method: "POST",
  })

export const cancelSafetyAlert = () =>
  request<{ cancelled: boolean; state: string }>("/v1/safety/cancel", {
    method: "POST",
  })

export const voiceHeard = (text: string) =>
  request<{ queued: boolean; state: string }>("/v1/safety/voice_heard", {
    method: "POST",
    body: JSON.stringify({ text }),
  })

export const getSafetyIncidents = (limit = 50) =>
  request<{ incidents: SafetyIncident[]; total_returned: number }>(
    `/v1/safety/incidents?limit=${limit}`,
  )
