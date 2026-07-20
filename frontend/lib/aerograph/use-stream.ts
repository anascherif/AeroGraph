"use client"

import { useEffect, useRef, useState } from "react"
import { getWsBase } from "./config"
import type { StreamFrameMessage, StreamMessage } from "./types"

export type StreamState =
  | "idle"
  | "connecting"
  | "open"
  | "closed"
  | "not_found"
  | "error"

interface UseStreamResult {
  state: StreamState
  frame: StreamFrameMessage | null
  fps: number
  connect: () => void
  disconnect: () => void
}

/**
 * Subscribes to WS /v1/session/{id}/stream. Pass enabled=false to stay
 * disconnected. Changing sessionId or includeFrame reconnects.
 */
export function useStream(
  sessionId: string | null,
  includeFrame: boolean,
  enabled: boolean,
): UseStreamResult {
  const [state, setState] = useState<StreamState>("idle")
  const [frame, setFrame] = useState<StreamFrameMessage | null>(null)
  const [fps, setFps] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)
  const manualClose = useRef(false)
  const frameTimes = useRef<number[]>([])

  useEffect(() => {
    if (!enabled || !sessionId) {
      manualClose.current = true
      wsRef.current?.close(1000)
      wsRef.current = null
      setState("idle")
      setFrame(null)
      setFps(0)
      return
    }

    manualClose.current = false
    setState("connecting")
    setFrame(null)
    frameTimes.current = []

    const url = `${getWsBase()}/v1/session/${sessionId}/stream?include_frame=${includeFrame}`
    let ws: WebSocket
    try {
      ws = new WebSocket(url)
    } catch {
      setState("error")
      return
    }
    wsRef.current = ws

    ws.onopen = () => setState("open")

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as StreamMessage
        if (msg.type === "status") {
          setState("open")
        } else if (msg.type === "frame") {
          setFrame(msg)
          const now = performance.now()
          const times = frameTimes.current
          times.push(now)
          while (times.length > 0 && now - times[0] > 1000) times.shift()
          setFps(times.length)
        }
      } catch {
        // ignore malformed messages
      }
    }

    ws.onclose = (event) => {
      if (manualClose.current) {
        setState("idle")
      } else if (event.code === 4004) {
        setState("not_found")
      } else {
        setState("closed")
      }
    }

    ws.onerror = () => {
      if (!manualClose.current) setState("error")
    }

    return () => {
      manualClose.current = true
      ws.close(1000)
    }
  }, [sessionId, includeFrame, enabled])

  const connect = () => setState((s) => (s === "idle" ? "connecting" : s))
  const disconnect = () => {
    manualClose.current = true
    wsRef.current?.close(1000)
  }

  return { state, frame, fps, connect, disconnect }
}
