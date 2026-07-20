"use client"

import { Clapperboard, Clock } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useSessionScenes } from "@/lib/aerograph/hooks"
import { formatConfidence, formatDuration, formatTime } from "@/lib/aerograph/format"
import { EmptyState } from "./empty-state"

export function ScenesTimeline({ sessionId }: { sessionId: string }) {
  const { data, error, isLoading } = useSessionScenes(sessionId)

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <EmptyState
        icon={Clapperboard}
        title="Could not load scenes"
        description={error.message ?? "The backend returned an error."}
      />
    )
  }

  const scenes = data?.scenes ?? []
  if (scenes.length === 0) {
    return (
      <EmptyState
        icon={Clapperboard}
        title="No scenes captured"
        description="Scenes group co-occurring objects over a slice of time. They appear as the session progresses."
      />
    )
  }

  return (
    <ol className="relative flex flex-col gap-4 pl-6">
      <span
        className="absolute bottom-2 left-2 top-2 w-px bg-border"
        aria-hidden
      />
      {scenes.map((scene) => {
        const entries = Object.entries(scene.sightings)
        return (
          <li key={scene.index} className="relative">
            <span
              className="absolute -left-[1.15rem] top-4 size-3 rounded-full border-2 border-background bg-primary"
              aria-hidden
            />
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="flex items-center gap-2 font-bold">
                  <Clapperboard className="size-4 text-primary" aria-hidden />
                  Scene {scene.index}
                </h4>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Clock className="size-3.5" aria-hidden />
                    {formatTime(scene.start)}
                  </span>
                  <span className="font-mono">
                    {formatDuration(scene.start, scene.end)}
                  </span>
                  <Badge variant="outline">persist {scene.persist_counter}</Badge>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {entries.length === 0 ? (
                  <span className="text-sm text-muted-foreground">
                    No sightings.
                  </span>
                ) : (
                  entries
                    .sort((a, b) => b[1].frame_count - a[1].frame_count)
                    .map(([cls, s]) => (
                      <Badge
                        key={cls}
                        variant="secondary"
                        className="gap-1.5 capitalize"
                        title={`${s.frame_count} frames · ${formatConfidence(
                          s.avg_confidence,
                        )} confidence`}
                      >
                        {cls}
                        <span className="font-mono text-[10px] opacity-70">
                          ×{s.frame_count}
                        </span>
                      </Badge>
                    ))
                )}
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
