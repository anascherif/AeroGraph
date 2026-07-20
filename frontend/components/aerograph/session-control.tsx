"use client"

import { MapPin, Play, Radio, Square } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useSWRConfig } from "swr"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, startSession, stopSession } from "@/lib/aerograph/client"
import { useSession } from "@/lib/aerograph/session-context"
import { cn } from "@/lib/utils"

function ElapsedTimer({ startedAt }: { startedAt: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const startMs = startedAt < 1e12 ? startedAt * 1000 : startedAt
  const secs = Math.max(0, Math.floor((now - startMs) / 1000))
  const mm = String(Math.floor(secs / 60)).padStart(2, "0")
  const ss = String(secs % 60).padStart(2, "0")
  return (
    <span className="font-mono tabular-nums" aria-label={`Elapsed ${mm} minutes ${ss} seconds`}>
      {mm}:{ss}
    </span>
  )
}

export function SessionControl() {
  const { active, setActive, setSelectedSessionId } = useSession()
  const { mutate } = useSWRConfig()
  const [location, setLocation] = useState("")
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleStart() {
    const name = location.trim()
    if (!name) {
      inputRef.current?.focus()
      toast.error("Enter a location name to start a session")
      return
    }
    setBusy(true)
    try {
      const res = await startSession(name)
      setActive({
        sessionId: res.session_id,
        locationName: res.location_name,
        startedAt: res.started_at,
      })
      setSelectedSessionId(res.session_id)
      setLocation("")
      mutate("sessions")
      toast.success(`Session started at ${res.location_name}`)
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to start session"
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  async function handleStop() {
    if (!active) return
    setBusy(true)
    try {
      const res = await stopSession(active.sessionId)
      toast.success(`Session ended at ${res.location_name}`, {
        description: `${res.object_count} objects across ${res.scene_count} scenes captured.`,
      })
      setActive(null)
      mutate("sessions")
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to stop session"
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  if (active) {
    return (
      <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span
            className="flex size-11 items-center justify-center rounded-full bg-danger/15 text-danger"
            aria-hidden
          >
            <Radio className="size-5 animate-pulse" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-danger">
              Recording
            </p>
            <p className="flex items-center gap-1.5 text-lg font-bold leading-tight">
              <MapPin className="size-4 text-muted-foreground" aria-hidden />
              {active.locationName}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Elapsed</p>
            <p className="text-lg font-bold">
              <ElapsedTimer startedAt={active.startedAt} />
            </p>
          </div>
          <Button
            variant="destructive"
            size="lg"
            onClick={handleStop}
            disabled={busy}
          >
            <Square className="size-4 fill-current" aria-hidden />
            End session
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:flex-row sm:items-end">
      <div className="flex-1">
        <label
          htmlFor="location-name"
          className="mb-1.5 block text-sm font-semibold"
        >
          Location name
        </label>
        <Input
          id="location-name"
          ref={inputRef}
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.nativeEvent.isComposing &&
              e.keyCode !== 229
            ) {
              handleStart()
            }
          }}
          placeholder="e.g. Kitchen, Office, Front hallway"
          className={cn("h-11 text-base")}
          disabled={busy}
        />
      </div>
      <Button size="lg" className="h-11" onClick={handleStart} disabled={busy}>
        <Play className="size-4 fill-current" aria-hidden />
        Start walking session
      </Button>
    </div>
  )
}
