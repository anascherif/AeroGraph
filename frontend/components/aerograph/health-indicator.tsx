"use client"

import { Activity, AlertTriangle, CircleCheck, Loader2 } from "lucide-react"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { useHealth } from "@/lib/aerograph/hooks"
import type { Health } from "@/lib/aerograph/types"
import { cn } from "@/lib/utils"

const SERVICE_LABELS: { key: keyof Health; label: string; hint: string }[] = [
  { key: "yolo_loaded", label: "Detector", hint: "YOLO object detector" },
  { key: "chroma_ready", label: "Memory", hint: "ChromaDB vector store" },
  {
    key: "clip_loaded",
    label: "Visual search",
    hint: "CLIP model (lazy-loads on first query, ~2 min)",
  },
  {
    key: "spatial_graph_ready",
    label: "Spatial graph",
    hint: "Position/relationship graph",
  },
  {
    key: "camera_streaming",
    label: "Camera",
    hint: "Live while a subscriber is connected",
  },
]

const SAFETY_LABELS: { key: keyof Health; label: string; hint: string }[] = [
  {
    key: "safety_monitor_ready",
    label: "Safety monitor",
    hint: "Body-cam distress detector + escalation state machine",
  },
  {
    key: "notifier_bus_ready",
    label: "Alert bus",
    hint: "Telegram + WhatsApp + Twilio fan-out",
  },
]

const CHANNEL_LABELS: { key: keyof Health; label: string; hint: string }[] = [
  {
    key: "telegram_enabled",
    label: "Telegram",
    hint: "TELEGRAM_BOT_TOKEN set",
  },
  {
    key: "whatsapp_enabled",
    label: "WhatsApp",
    hint: "Baileys bridge reachable at WHATSAPP_BRIDGE_URL",
  },
  {
    key: "twilio_enabled",
    label: "Twilio voice",
    hint: "TWILIO_* env vars set (dry-run if absent)",
  },
]

export function HealthIndicator() {
  const { health, isLoading, reachable } = useHealth()

  const state = !reachable
    ? "offline"
    : isLoading
      ? "loading"
      : "online"

  return (
    <Popover>
      <PopoverTrigger
        className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm font-medium transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={`Backend status: ${state}. Open details.`}
      >
        <span className="relative flex size-2.5">
          {state === "online" && (
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
          )}
          <span
            className={cn(
              "relative inline-flex size-2.5 rounded-full",
              state === "online" && "bg-success",
              state === "loading" && "bg-warning",
              state === "offline" && "bg-danger",
            )}
          />
        </span>
        <span className="hidden sm:inline">
          {state === "online"
            ? "Backend online"
            : state === "loading"
              ? "Connecting…"
              : "Backend offline"}
        </span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72">
        <div className="mb-3 flex items-center gap-2">
          <Activity className="size-4 text-primary" aria-hidden />
          <h3 className="font-bold">Backend services</h3>
        </div>
        {!reachable ? (
          <div className="flex items-start gap-2 rounded-md bg-danger/15 p-3 text-sm text-danger">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p>
              Cannot reach the backend. Check that the AeroGraph server is
              running and the API URL is correct.
            </p>
          </div>
        ) : (
          <>
            <ul className="flex flex-col gap-1.5" aria-label="Service statuses">
              {SERVICE_LABELS.map(({ key, label, hint }) => {
                const ok = Boolean(health?.[key])
                return (
                  <li
                    key={key}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm"
                  >
                    <span className="flex flex-col">
                      <span className="font-medium">{label}</span>
                      <span className="text-xs text-muted-foreground">
                        {hint}
                      </span>
                    </span>
                    {isLoading ? (
                      <Loader2
                        className="size-4 animate-spin text-muted-foreground"
                        aria-hidden
                      />
                    ) : ok ? (
                      <span className="flex items-center gap-1 text-xs font-semibold text-success">
                        <CircleCheck className="size-4" aria-hidden />
                        <span className="sr-only">Ready</span>
                      </span>
                    ) : (
                      <span className="text-xs font-semibold text-muted-foreground">
                        Idle
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>

            <div className="mb-2 mt-3 flex items-center gap-2">
              <Activity className="size-4 text-primary" aria-hidden />
              <h3 className="font-bold">Safety</h3>
            </div>
            <ul className="mb-3 flex flex-col gap-1.5" aria-label="Safety service statuses">
              {SAFETY_LABELS.map(({ key, label, hint }) => {
                const ok = Boolean(health?.[key])
                return (
                  <li
                    key={key}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm"
                  >
                    <span className="flex flex-col">
                      <span className="font-medium">{label}</span>
                      <span className="text-xs text-muted-foreground">
                        {hint}
                      </span>
                    </span>
                    {isLoading ? (
                      <Loader2
                        className="size-4 animate-spin text-muted-foreground"
                        aria-hidden
                      />
                    ) : ok ? (
                      <span className="flex items-center gap-1 text-xs font-semibold text-success">
                        <CircleCheck className="size-4" aria-hidden />
                        <span className="sr-only">Ready</span>
                      </span>
                    ) : (
                      <span className="text-xs font-semibold text-muted-foreground">
                        Unavailable
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>

            <div className="mb-2 flex items-center gap-2">
              <Activity className="size-4 text-primary" aria-hidden />
              <h3 className="font-bold">Alert channels</h3>
            </div>
            <ul className="flex flex-col gap-1.5" aria-label="Alert channel statuses">
              {CHANNEL_LABELS.map(({ key, label, hint }) => {
                const enabled = Boolean(health?.[key])
                return (
                  <li
                    key={key}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm"
                  >
                    <span className="flex flex-col">
                      <span className="font-medium">{label}</span>
                      <span className="text-xs text-muted-foreground">
                        {hint}
                      </span>
                    </span>
                    {isLoading ? (
                      <Loader2
                        className="size-4 animate-spin text-muted-foreground"
                        aria-hidden
                      />
                    ) : enabled ? (
                      <span className="flex items-center gap-1 text-xs font-semibold text-success">
                        <CircleCheck className="size-4" aria-hidden />
                        <span className="sr-only">Configured</span>
                      </span>
                    ) : (
                      <span className="text-xs font-semibold text-muted-foreground">
                        Not set
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}
