"use client"

import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  CircleHelp,
  GitCompareArrows,
  Minus,
  MoveRight,
  Plus,
  Video,
  Volume2,
} from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ApiError, diffCompare, diffLive, diffLocation } from "@/lib/aerograph/client"
import { useSessions } from "@/lib/aerograph/hooks"
import { speak, speakSequence, ttsAvailable } from "@/lib/aerograph/tts"
import type { DiffChange, DiffResponse, DiffStatus } from "@/lib/aerograph/types"
import { cn } from "@/lib/utils"
import { EmptyState } from "./empty-state"

const STATUS_META: Record<
  DiffStatus,
  { label: string; className: string; icon: typeof Plus }
> = {
  new: { label: "New", className: "bg-info/15 text-info", icon: Plus },
  missing: { label: "Missing", className: "bg-danger/15 text-danger", icon: Minus },
  moved: { label: "Moved", className: "bg-warning/15 text-warning", icon: MoveRight },
  context_changed: {
    label: "Context changed",
    className: "bg-context/15 text-context",
    icon: GitCompareArrows,
  },
  unchanged: {
    label: "Unchanged",
    className: "bg-success/15 text-success",
    icon: CircleHelp,
  },
}

const DIRECTION_ICON = {
  left: ArrowLeft,
  right: ArrowRight,
  closer: ArrowDown,
  further: ArrowUp,
  in_place: MoveRight,
}

export function DiffPanel() {
  const { data } = useSessions()
  const sessions = useMemo(
    () =>
      [...(data?.sessions ?? [])].sort((a, b) => b.started_at - a.started_at),
    [data],
  )

  const [mode, setMode] = useState<"location" | "sessions" | "live">("location")
  const [current, setCurrent] = useState("")
  const [reference, setReference] = useState("")
  const [location, setLocation] = useState("")
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<DiffResponse | null>(null)

  const locations = useMemo(
    () => [...new Set(sessions.map((s) => s.location_name))],
    [sessions],
  )

  async function run() {
    setBusy(true)
    setResult(null)
    try {
      let res: DiffResponse
      if (mode === "location") {
        if (!location || !current) {
          toast.error("Select a location and a current session")
          return
        }
        res = await diffLocation(location, current)
      } else if (mode === "live") {
        if (!location) {
          toast.error("Select a location to compare the live camera against")
          return
        }
        res = await diffLive(location, current)
      } else {
        if (!reference || !current) {
          toast.error("Select both sessions to compare")
          return
        }
        res = await diffCompare(reference, current)
      }
      setResult(res)
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Comparison failed"
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="mb-4 inline-flex rounded-lg border border-border p-1">
          <ModeButton active={mode === "location"} onClick={() => setMode("location")}>
            Compare to last visit
          </ModeButton>
          <ModeButton active={mode === "sessions"} onClick={() => setMode("sessions")}>
            Compare two sessions
          </ModeButton>
          <ModeButton active={mode === "live"} onClick={() => setMode("live")}>
            <Video className="size-3.5 mr-1 inline-block" aria-hidden />
            Compare to live camera
          </ModeButton>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {mode === "location" ? (
            <>
              <Field label="Location">
                <Select value={location} onValueChange={setLocation}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose a location" />
                  </SelectTrigger>
                  <SelectContent>
                    {locations.map((l) => (
                      <SelectItem key={l} value={l}>
                        {l}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Current session">
                <SessionSelect
                  sessions={sessions}
                  value={current}
                  onChange={setCurrent}
                />
              </Field>
            </>
          ) : mode === "live" ? (
            <>
              <Field label="Location">
                <Select value={location} onValueChange={setLocation}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose a location" />
                  </SelectTrigger>
                  <SelectContent>
                    {locations.map((l) => (
                      <SelectItem key={l} value={l}>
                        {l}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Active session (optional)">
                <SessionSelect
                  sessions={sessions}
                  value={current}
                  onChange={setCurrent}
                />
              </Field>
            </>
          ) : (
            <>
              <Field label="Reference (earlier) session">
                <SessionSelect
                  sessions={sessions}
                  value={reference}
                  onChange={setReference}
                />
              </Field>
              <Field label="Current (later) session">
                <SessionSelect
                  sessions={sessions}
                  value={current}
                  onChange={setCurrent}
                />
              </Field>
            </>
          )}
        </div>

        <Button className="mt-4" size="lg" onClick={run} disabled={busy}>
          <GitCompareArrows className="size-4" aria-hidden />
          {busy ? "Comparing…" : mode === "live" ? "Compare live now" : "Detect changes"}
        </Button>
      </div>

      {result ? (
        <DiffResult result={result} />
      ) : (
        <EmptyState
          icon={mode === "live" ? Video : GitCompareArrows}
          title={
            mode === "live"
              ? "Compare live camera to last visit"
              : "Compare environment states"
          }
          description={
            mode === "live"
              ? "Snapshot what the camera sees right now and diff it against your last visit to the same place. Useful for catching what's been moved or left behind in real time."
              : "Detect what's new, missing, or moved between two visits to the same place. Notes are written to be read aloud."
          }
        />
      )}
    </div>
  )
}

function DiffResult({ result }: { result: DiffResponse }) {
  const order: DiffStatus[] = [
    "missing",
    "moved",
    "new",
    "context_changed",
    "unchanged",
  ]
  const changes = [...result.changes].sort(
    (a, b) => order.indexOf(a.status) - order.indexOf(b.status),
  )
  const summaryItems: { key: DiffStatus; value: number }[] = [
    { key: "new", value: result.summary.new },
    { key: "missing", value: result.summary.missing },
    { key: "moved", value: result.summary.moved },
    { key: "context_changed", value: result.summary.context_changed },
    { key: "unchanged", value: result.summary.unchanged },
  ]

  const notableNotes = changes
    .filter((c) => c.status !== "unchanged")
    .map((c) => c.note)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-bold">
          Changes at{" "}
          <span className="text-primary">{result.location_name}</span>
          {result.live && (
            <Badge className="ml-2 gap-1 bg-info/15 text-info" variant="outline">
              <span className="size-1.5 animate-pulse rounded-full bg-info" aria-hidden />
              LIVE
            </Badge>
          )}
        </h3>
        {ttsAvailable() && notableNotes.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => speakSequence(notableNotes)}
          >
            <Volume2 className="size-4" aria-hidden />
            Read all changes
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {summaryItems.map(({ key, value }) => {
          const meta = STATUS_META[key]
          return (
            <div
              key={key}
              className={cn(
                "flex flex-col items-center rounded-xl border border-border p-3",
                value > 0 ? meta.className : "text-muted-foreground",
              )}
            >
              <span className="text-2xl font-bold tabular-nums">{value}</span>
              <span className="text-xs font-medium">{meta.label}</span>
            </div>
          )
        })}
      </div>

      <ul className="flex flex-col gap-2">
        {changes.map((c) => (
          <ChangeRow key={`${c.object}-${c.status}`} change={c} />
        ))}
      </ul>
    </div>
  )
}

function ChangeRow({ change }: { change: DiffChange }) {
  const meta = STATUS_META[change.status]
  const Icon = meta.icon
  const DirIcon = change.direction ? DIRECTION_ICON[change.direction] : null
  return (
    <li className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span
            className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-lg",
              meta.className,
            )}
            aria-hidden
          >
            <Icon className="size-4" />
          </span>
          <div>
            <p className="flex items-center gap-2 font-bold capitalize">
              {change.object}
              <Badge variant="outline" className="capitalize">
                {change.category}
              </Badge>
            </p>
            <p className="mt-0.5 text-sm text-pretty text-muted-foreground">
              {change.note}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <Badge className={cn("gap-1", meta.className)}>{meta.label}</Badge>
              {change.direction && DirIcon && (
                <span className="flex items-center gap-1 text-muted-foreground">
                  <DirIcon className="size-3.5" aria-hidden />
                  {change.direction.replace("_", " ")}
                </span>
              )}
              {change.displacement_m != null && (
                <span className="font-mono text-muted-foreground">
                  {change.displacement_m.toFixed(2)} m
                </span>
              )}
            </div>
          </div>
        </div>
        {ttsAvailable() && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Read note for ${change.object} aloud`}
            onClick={() => speak(change.note)}
          >
            <Volume2 className="size-4" aria-hidden />
          </Button>
        )}
      </div>
    </li>
  )
}

function ModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
        active
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  )
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

function SessionSelect({
  sessions,
  value,
  onChange,
}: {
  sessions: { session_id: string; location_name: string; started_at: number }[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue placeholder="Choose a session" />
      </SelectTrigger>
      <SelectContent>
        {sessions.map((s) => (
          <SelectItem key={s.session_id} value={s.session_id}>
            {s.location_name} — {new Date((s.started_at < 1e12 ? s.started_at * 1000 : s.started_at)).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
