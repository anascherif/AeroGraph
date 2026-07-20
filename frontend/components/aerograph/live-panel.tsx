"use client"

import { CameraOff, Radar, Video, WifiOff } from "lucide-react"
import { useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Switch } from "@/components/ui/switch"
import { useSession } from "@/lib/aerograph/session-context"
import { useStream } from "@/lib/aerograph/use-stream"
import { formatConfidence } from "@/lib/aerograph/format"
import { cn } from "@/lib/utils"
import { DetectionCanvas } from "./detection-canvas"
import { EmptyState } from "./empty-state"

export function LivePanel() {
  const { active } = useSession()
  const [showCamera, setShowCamera] = useState(false)
  const { state, frame, fps } = useStream(
    active?.sessionId ?? null,
    showCamera,
    Boolean(active),
  )

  const detections = frame?.detections ?? []
  const frameShape: [number, number] = frame?.frame_shape ?? [720, 1280]

  const counts = useMemo(() => {
    const map = new Map<string, number>()
    for (const d of detections) map.set(d.class, (map.get(d.class) ?? 0) + 1)
    return [...map.entries()].sort((a, b) => b[1] - a[1])
  }, [detections])

  if (!active) {
    return (
      <EmptyState
        icon={Radar}
        title="No active session"
        description="Start a walking session above to begin live object detection. The camera starts automatically when you connect."
      />
    )
  }

  const connLabel: Record<string, string> = {
    idle: "Idle",
    connecting: "Connecting…",
    open: "Live",
    closed: "Disconnected",
    not_found: "Session not found",
    error: "Connection error",
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={cn(
                "gap-1.5 border-transparent px-2.5 py-1 text-sm",
                state === "open" && "bg-success/15 text-success",
                (state === "connecting" || state === "idle") &&
                  "bg-warning/15 text-warning",
                (state === "closed" ||
                  state === "not_found" ||
                  state === "error") &&
                  "bg-danger/15 text-danger",
              )}
            >
              <span
                className={cn(
                  "size-2 rounded-full",
                  state === "open" && "animate-pulse bg-success",
                  (state === "connecting" || state === "idle") && "bg-warning",
                  (state === "closed" ||
                    state === "not_found" ||
                    state === "error") &&
                    "bg-danger",
                )}
                aria-hidden
              />
              {connLabel[state]}
            </Badge>
            {state === "open" && (
              <span className="font-mono text-sm text-muted-foreground tabular-nums">
                {fps} fps · frame #{frame?.roll ?? 0}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Switch
              id="show-camera"
              checked={showCamera}
              onCheckedChange={setShowCamera}
            />
            <Label htmlFor="show-camera" className="cursor-pointer text-sm">
              {showCamera ? (
                <span className="flex items-center gap-1.5">
                  <Video className="size-4" aria-hidden /> Camera feed
                </span>
              ) : (
                <span className="flex items-center gap-1.5">
                  <Radar className="size-4" aria-hidden /> Radar view
                </span>
              )}
            </Label>
          </div>
        </div>

        <div className="relative aspect-video overflow-hidden rounded-xl border border-border bg-[oklch(0.13_0.012_248)]">
          {state === "not_found" || state === "error" ? (
            <div className="flex size-full flex-col items-center justify-center gap-2 text-danger">
              <WifiOff className="size-8" aria-hidden />
              <p className="font-semibold">
                {state === "not_found"
                  ? "Session not found on backend"
                  : "Stream connection failed"}
              </p>
            </div>
          ) : showCamera ? (
            frame?.frame_b64 ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`data:image/jpeg;base64,${frame.frame_b64}`}
                alt={`Live camera frame with ${detections.length} detected objects`}
                className="size-full object-contain"
              />
            ) : (
              <div className="flex size-full flex-col items-center justify-center gap-2 text-muted-foreground">
                <CameraOff className="size-8" aria-hidden />
                <p>Waiting for camera frames…</p>
              </div>
            )
          ) : (
            <DetectionCanvas detections={detections} frameShape={frameShape} />
          )}
          <div className="pointer-events-none absolute left-3 top-3 rounded-md bg-background/70 px-2 py-1 font-mono text-xs text-muted-foreground backdrop-blur">
            {frameShape[1]}×{frameShape[0]}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-bold">Detected now</h3>
          <Badge variant="secondary">{detections.length}</Badge>
        </div>
        <p className="sr-only" aria-live="polite">
          {counts.length
            ? `Detecting ${counts.map(([c, n]) => `${n} ${c}`).join(", ")}`
            : "No objects detected"}
        </p>
        {counts.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No objects in view.
          </p>
        ) : (
          <ScrollArea className="h-[360px] pr-3">
            <ul className="flex flex-col gap-1.5">
              {counts.map(([cls, n]) => (
                <li
                  key={cls}
                  className="flex items-center justify-between rounded-md bg-secondary/60 px-3 py-2"
                >
                  <span className="font-medium capitalize">{cls}</span>
                  <Badge variant="outline">×{n}</Badge>
                </li>
              ))}
            </ul>
            <div className="mt-3 border-t border-border pt-3">
              <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Confidence
              </h4>
              <ul className="flex flex-col gap-1">
                {detections.slice(0, 12).map((d, i) => (
                  <li
                    key={`${d.class}-${i}`}
                    className="flex items-center justify-between font-mono text-xs text-muted-foreground"
                  >
                    <span className="capitalize">{d.class}</span>
                    <span>{formatConfidence(d.confidence)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  )
}
