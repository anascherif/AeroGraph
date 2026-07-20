"use client"

import { Boxes, Link2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useSessionObjects } from "@/lib/aerograph/hooks"
import { formatConfidence, formatTime } from "@/lib/aerograph/format"
import { EmptyState } from "./empty-state"

export function ObjectList({ sessionId }: { sessionId: string }) {
  const { data, error, isLoading } = useSessionObjects(sessionId)

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-24 w-full rounded-xl" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <EmptyState
        icon={Boxes}
        title="Could not load objects"
        description={error.message ?? "The backend returned an error."}
      />
    )
  }

  const objects = data?.objects ?? []
  if (objects.length === 0) {
    return (
      <EmptyState
        icon={Boxes}
        title="No objects recorded"
        description="This session hasn't captured any objects yet. Objects appear as they're detected and tracked across frames."
      />
    )
  }

  const sorted = [...objects].sort((a, b) => b.total_frames - a.total_frames)

  return (
    <ul className="flex flex-col gap-3">
      {sorted.map((obj) => (
        <li
          key={obj.class}
          className="rounded-xl border border-border bg-card p-4"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex size-10 items-center justify-center rounded-lg bg-primary/15 text-primary">
                <Boxes className="size-5" aria-hidden />
              </span>
              <div>
                <p className="text-lg font-bold capitalize leading-tight">
                  {obj.class}
                </p>
                <p className="text-xs text-muted-foreground">
                  Seen {formatTime(obj.first_seen)} – {formatTime(obj.last_seen)}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Stat label="Frames" value={String(obj.total_frames)} />
              <Stat
                label="Confidence"
                value={formatConfidence(obj.avg_confidence)}
              />
              <Stat
                label="Position"
                value={`${Math.round(obj.last_centroid[0])}, ${Math.round(
                  obj.last_centroid[1],
                )}`}
                mono
              />
            </div>
          </div>
          {obj.co_occurred_with.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border pt-3">
              <span className="flex items-center gap-1 text-xs font-semibold text-muted-foreground">
                <Link2 className="size-3.5" aria-hidden />
                Near
              </span>
              {obj.co_occurred_with.map((c) => (
                <Badge key={c} variant="secondary" className="capitalize">
                  {c}
                </Badge>
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}

function Stat({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="rounded-lg bg-secondary/60 px-3 py-1.5 text-center">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`font-bold ${mono ? "font-mono text-sm" : ""}`}>{value}</p>
    </div>
  )
}
