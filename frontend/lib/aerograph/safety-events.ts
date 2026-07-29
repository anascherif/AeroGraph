"use client"

import { useEffect, useRef, useState } from "react"
import type { SafetyStatus } from "./types"

export type SafetyWsEvent =
  | { type: "snapshot"; ts: number; data: SafetyStatus }
  | { type: "state"; ts: number; data: { state: string } }
  | { type: "incident"; ts: number; data: { incident_id: string; outcome?: string } }
  | { type: "stt"; ts: number; data: { text: string } }
  | { type: string; ts: number; data: unknown }

export interface UseSafetyEventsResult {
  connected: boolean
  lastEvent: SafetyWsEvent | null
  error: string | null
}

function getApiBase(): string {
  if (typeof window === "undefined") return ""
  const env = process.env.NEXT_PUBLIC_API_BASE
  if (env) return env.replace(/\/$/, "")
  const host = window.location.hostname
  return `http://${host}:8000`
}

export function useSafetyEvents(
  onEvent?: (evt: SafetyWsEvent) => void,
): UseSafetyEventsResult {
  const [connected, setConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<SafetyWsEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Hold the latest onEvent callback without re-creating the WS on every
  // parent re-render (which would tear down the connection constantly).
  const onEventRef = useRef(onEvent)
  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  useEffect(() => {
    const base = getApiBase()
    if (!base) return
    const wsBase = base.replace(/^http/, "ws")
    const token =
      typeof window !== "undefined"
        ? window.localStorage.getItem("aerograph:auth-token") || ""
        : ""
    const qs = token ? `?token=${encodeURIComponent(token)}` : ""
    let ws: WebSocket | null = null
    let reconnectTimer: number | null = null
    let cancelled = false

    const connect = () => {
      if (cancelled) return
      try {
        ws = new WebSocket(`${wsBase}/v1/safety/events${qs}`)
      } catch (e) {
        setError(String(e))
        return
      }
      ws.onopen = () => {
        setConnected(true)
        setError(null)
      }
      ws.onmessage = (msg) => {
        try {
          const evt = JSON.parse(msg.data) as SafetyWsEvent
          setLastEvent(evt)
          onEventRef.current?.(evt)
        } catch {
          // ignore non-JSON frames (heartbeats etc.)
        }
      }
      ws.onerror = () => {
        setError("websocket error")
      }
      ws.onclose = () => {
        setConnected(false)
        if (cancelled) return
        // 2s reconnect — short enough for casual failures, gentle enough
        // not to hammer the server if it's down.
        reconnectTimer = window.setTimeout(connect, 2000)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      if (ws && ws.readyState <= WebSocket.OPEN) ws.close()
    }
  }, [])

  return { connected, lastEvent, error }
}
