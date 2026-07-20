"use client"

import { Boxes, Clapperboard, History, MapPin, Radio } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useSessions } from "@/lib/aerograph/hooks"
import { formatDateTime, formatDuration, relativeTime } from "@/lib/aerograph/format"
import { useSession } from "@/lib/aerograph/session-context"
import { cn } from "@/lib/utils"
import { EmptyState } from "./empty-state"
import { ObjectList } from "./object-list"
import { ScenesTimeline } from "./scenes-timeline"

export function SessionsPanel() {
  const { data, error, isLoading } = useSessions()
  const { selectedSessionId, setSelectedSessionId, active } = useSession()

  const sessions = data?.sessions ?? []
  const sorted = [...sessions].sort((a, b) => b.started_at - a.started_at)
  const selected = sorted.find((s) => s.session_id === selectedSessionId)

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 font-bold">
            <History className="size-4 text-primary" aria-hidden />
            Session history
          </h3>
          {sessions.length > 0 && (
            <Badge variant="secondary">{sessions.length}</Badge>
          )}
        </div>

        {isLoading ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-20 w-full rounded-xl" />
            ))}
          </div>
        ) : error ? (
          <EmptyState
            icon={History}
            title="Could not load sessions"
            description={error.message ?? "The backend returned an error."}
          />
        ) : sorted.length === 0 ? (
          <EmptyState
            icon={History}
            title="No sessions yet"
            description="Start a walking session to build spatial memory of a location."
          />
        ) : (
          <ul className="flex flex-col gap-2" aria-label="Sessions">
            {sorted.map((s) => {
              const isActive = active?.sessionId === s.session_id
              const isSelected = selectedSessionId === s.session_id
              return (
                <li key={s.session_id}>
                  <button
                    type="button"
                    onClick={() => setSelectedSessionId(s.session_id)}
                    aria-pressed={isSelected}
                    className={cn(
                      "w-full rounded-xl border p-3 text-left transition-colors",
                      isSelected
                        ? "border-primary bg-primary/10"
                        : "border-border bg-card hover:bg-accent",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 font-bold">
                        <MapPin
                          className="size-4 text-muted-foreground"
                          aria-hidden
                        />
                        {s.location_name}
                      </span>
                      {isActive ? (
                        <Badge className="gap-1 bg-danger/15 text-danger">
                          <Radio className="size-3 animate-pulse" aria-hidden />
                          Live
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {relativeTime(s.started_at)}
                        </span>
                      )}
                    </div>
                    <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Boxes className="size-3.5" aria-hidden />
                        {s.object_count} objects
                      </span>
                      <span className="flex items-center gap-1">
                        <Clapperboard className="size-3.5" aria-hidden />
                        {s.scene_count} scenes
                      </span>
                      {s.stopped_at && (
                        <span className="ml-auto font-mono">
                          {formatDuration(s.started_at, s.stopped_at)}
                        </span>
                      )}
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div>
        {!selected ? (
          <EmptyState
            icon={History}
            title="Select a session"
            description="Choose a session from the list to explore the objects it remembers and the scenes it captured."
          />
        ) : (
          <div className="flex flex-col gap-4">
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="flex items-center gap-2 text-xl font-bold">
                  <MapPin className="size-5 text-primary" aria-hidden />
                  {selected.location_name}
                </h2>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span>{formatDateTime(selected.started_at)}</span>
                  {selected.stopped_at ? (
                    <Badge variant="outline">
                      {formatDuration(selected.started_at, selected.stopped_at)}
                    </Badge>
                  ) : (
                    <Badge className="bg-danger/15 text-danger">In progress</Badge>
                  )}
                </div>
              </div>
              <p className="mt-1 font-mono text-xs text-muted-foreground">
                {selected.session_id}
              </p>
            </div>

            <Tabs defaultValue="objects">
              <TabsList>
                <TabsTrigger value="objects">
                  <Boxes className="size-4" aria-hidden />
                  Objects ({selected.object_count})
                </TabsTrigger>
                <TabsTrigger value="scenes">
                  <Clapperboard className="size-4" aria-hidden />
                  Scenes ({selected.scene_count})
                </TabsTrigger>
              </TabsList>
              <TabsContent value="objects" className="mt-4">
                <ObjectList sessionId={selected.session_id} />
              </TabsContent>
              <TabsContent value="scenes" className="mt-4">
                <ScenesTimeline sessionId={selected.session_id} />
              </TabsContent>
            </Tabs>
          </div>
        )}
      </div>
    </div>
  )
}
