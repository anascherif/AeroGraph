"use client"

import {
  GitCompareArrows,
  History,
  MessagesSquare,
  Radar,
  ScanSearch,
  ShieldCheck,
} from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { SessionProvider } from "@/lib/aerograph/session-context"
import { ApiSettings } from "./api-settings"
import { DiffPanel } from "./diff-panel"
import { HealthIndicator } from "./health-indicator"
import { LivePanel } from "./live-panel"
import { QueryPanel } from "./query-panel"
import { SafetyPanel } from "./safety-panel"
import { SearchPanel } from "./search-panel"
import { SessionControl } from "./session-control"
import { SessionsPanel } from "./sessions-panel"

const TABS = [
  { value: "live", label: "Live", icon: Radar },
  { value: "sessions", label: "Sessions", icon: History },
  { value: "compare", label: "Compare", icon: GitCompareArrows },
  { value: "ask", label: "Ask", icon: MessagesSquare },
  { value: "search", label: "Search", icon: ScanSearch },
  { value: "safety", label: "Safety", icon: ShieldCheck },
]

export function Dashboard() {
  return (
    <SessionProvider>
      <div className="min-h-screen">
        <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
            <div className="flex items-center gap-3">
              <span
                className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"
                aria-hidden
              >
                <Radar className="size-6" />
              </span>
              <div>
                <h1 className="text-lg font-bold leading-tight">AeroGraph</h1>
                <p className="text-xs text-muted-foreground">
                  Spatial-temporal memory engine
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <HealthIndicator />
              <ApiSettings />
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          <div className="mb-6">
            <SessionControl />
          </div>

          <Tabs defaultValue="live">
            <TabsList className="grid w-full grid-cols-5 sm:w-auto sm:inline-grid">
              {TABS.map(({ value, label, icon: Icon }) => (
                <TabsTrigger key={value} value={value} className="gap-1.5">
                  <Icon className="size-4" aria-hidden />
                  <span className="hidden sm:inline">{label}</span>
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="live" className="mt-6">
              <LivePanel />
            </TabsContent>
            <TabsContent value="sessions" className="mt-6">
              <SessionsPanel />
            </TabsContent>
            <TabsContent value="compare" className="mt-6">
              <DiffPanel />
            </TabsContent>
            <TabsContent value="ask" className="mt-6">
              <QueryPanel />
            </TabsContent>
            <TabsContent value="search" className="mt-6">
              <SearchPanel />
            </TabsContent>
            <TabsContent value="safety" className="mt-6">
              <SafetyPanel />
            </TabsContent>
          </Tabs>
        </main>
      </div>
    </SessionProvider>
  )
}
