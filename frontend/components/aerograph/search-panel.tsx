"use client"

import { AlertTriangle, Clock, Loader2, MapPin, ScanSearch } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, visualSearch } from "@/lib/aerograph/client"
import { useHealth } from "@/lib/aerograph/hooks"
import { formatDateTime } from "@/lib/aerograph/format"
import type { VisualSearchResponse } from "@/lib/aerograph/types"
import { EmptyState } from "./empty-state"

function relevance(distance: number): number {
  // Cosine distance ~[0,2] → rough 0-100% similarity.
  return Math.max(0, Math.min(100, Math.round((1 - distance / 2) * 100)))
}

export function SearchPanel() {
  const { health } = useHealth()
  const [query, setQuery] = useState("")
  const [location, setLocation] = useState("")
  const [nResults, setNResults] = useState(5)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<VisualSearchResponse | null>(null)

  async function run() {
    const q = query.trim()
    if (!q) return
    setBusy(true)
    setResult(null)
    try {
      const res = await visualSearch(q, {
        location_name: location.trim() || undefined,
        n_results: nResults,
      })
      setResult(res)
      if (res.error) {
        toast.message("Visual search is warming up", { description: res.error })
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Search failed"
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const clipLoading = health && !health.clip_loaded

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-xl border border-border bg-card p-4">
        <Label htmlFor="visual-query" className="mb-1.5 block font-semibold">
          Search remembered scenes
        </Label>
        <p className="mb-3 text-sm text-muted-foreground">
          Find past moments by description using CLIP visual similarity. No
          active session required.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            id="visual-query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.nativeEvent.isComposing &&
                e.keyCode !== 229
              ) {
                run()
              }
            }}
            placeholder="e.g. a cluttered desk with a mug"
            className="h-11 flex-1 text-base"
            disabled={busy}
          />
          <Button
            className="h-11"
            onClick={run}
            disabled={busy || !query.trim()}
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <ScanSearch className="size-4" aria-hidden />
            )}
            Search
          </Button>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="search-location">Location filter (optional)</Label>
            <Input
              id="search-location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Any location"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="n-results">Results: {nResults}</Label>
            <input
              id="n-results"
              type="range"
              min={1}
              max={20}
              value={nResults}
              onChange={(e) => setNResults(Number(e.target.value))}
              className="mt-2 accent-[var(--primary)]"
            />
          </div>
        </div>

        {clipLoading && (
          <p className="mt-3 flex items-center gap-2 rounded-md bg-warning/15 p-2.5 text-sm text-warning">
            <AlertTriangle className="size-4 shrink-0" aria-hidden />
            The CLIP model loads lazily on the first search and can take ~2
            minutes. Your first query may return empty.
          </p>
        )}
      </div>

      {!result ? (
        <EmptyState
          icon={ScanSearch}
          title="Search your spatial memory"
          description="Describe a scene in plain language to retrieve visually similar moments captured across all sessions."
        />
      ) : result.results.length === 0 ? (
        <EmptyState
          icon={ScanSearch}
          title="No matches found"
          description={
            result.error
              ? result.error
              : `Nothing matched "${result.query}". Try a broader description.`
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            {result.total} result{result.total === 1 ? "" : "s"} for{" "}
            <span className="font-semibold text-foreground">
              &ldquo;{result.query}&rdquo;
            </span>
          </p>
          <ul className="grid gap-3 sm:grid-cols-2">
            {result.results.map((r) => {
              const objects = r.metadata.objects
                ? r.metadata.objects.split(",").map((o) => o.trim()).filter(Boolean)
                : []
              return (
                <li
                  key={r.id}
                  className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge className="bg-primary/15 text-primary">
                      {relevance(r.distance)}% match
                    </Badge>
                    <span className="font-mono text-xs text-muted-foreground">
                      d={r.distance.toFixed(3)}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {objects.length ? (
                      objects.map((o, i) => (
                        <Badge key={`${o}-${i}`} variant="secondary" className="capitalize">
                          {o}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        No object tags
                      </span>
                    )}
                  </div>
                  <div className="mt-auto flex flex-wrap items-center gap-3 border-t border-border pt-2 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <MapPin className="size-3.5" aria-hidden />
                      {r.metadata.location_name}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="size-3.5" aria-hidden />
                      {formatDateTime(r.metadata.timestamp)}
                    </span>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
