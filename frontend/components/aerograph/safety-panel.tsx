"use client"

import { useEffect, useState } from "react"
import { Loader2, Plus, ShieldAlert, Trash2, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useSafetyStatus } from "@/lib/aerograph/hooks"
import {
  cancelSafetyAlert,
  createSafetyContact,
  deleteSafetyContact,
  getSafetyContacts,
  getSafetyIncidents,
  testSafetyAlert,
  voiceHeard,
} from "@/lib/aerograph/client"
import type { SafetyChannel, SafetyContact, SafetyIncident, SafetyState, SafetyStatus } from "@/lib/aerograph/types"
import { useSafetyEvents } from "@/lib/aerograph/safety-events"

const STATE_COLORS: Record<SafetyState, string> = {
  monitoring: "text-success",
  confirming: "text-warning",
  escalating: "text-danger",
  cooldown: "text-muted-foreground",
  disabled: "text-danger",
}

const STATE_LABELS: Record<SafetyState, string> = {
  monitoring: "Monitoring — protecting you",
  confirming: "Confirming — listening for response",
  escalating: "Escalating — contacting family",
  cooldown: "Cooldown — resting",
  disabled: "Disabled",
}

function ContactsTab() {
  const [contacts, setContacts] = useState<SafetyContact[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  // Form state
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")
  const [telegramUsername, setTelegramUsername] = useState("")
  // MINOR #26: channels is now a Set so the user can pick multiple at once
  // (e.g. [telegram, whatsapp]). The previous <Select> only allowed one.
  const [channels, setChannels] = useState<Set<string>>(new Set(["telegram"]))

  const toggleChannel = (ch: string) => {
    setChannels((prev) => {
      const next = new Set(prev)
      if (next.has(ch)) next.delete(ch)
      else next.add(ch)
      return next
    })
  }

  const load = async () => {
    setLoading(true)
    setError("")
    try {
      const data = await getSafetyContacts()
      setContacts(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  // Load on mount (MINOR #24 — useEffect, not render-time call, which
  // would re-fire on every render and risk an infinite loop on network failure)
  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleAdd = async () => {
    if (!name.trim()) return
    try {
      const newContact = await createSafetyContact({
        name: name.trim(),
        phone,
        telegram_user_id: "",
        telegram_username: telegramUsername.startsWith("@")
          ? telegramUsername
          : telegramUsername ? `@${telegramUsername}` : "",
        channels: Array.from(channels) as SafetyChannel[],
        notes: "",
      })
      setContacts((prev) => [...prev, newContact])
      setName("")
      setPhone("")
      setTelegramUsername("")
      setChannels(new Set(["telegram"]))
    } catch (e) {
      setError(String(e))
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteSafetyContact(id)
      setContacts((prev) => prev.filter((c) => c.id !== id))
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Emergency contacts</CardTitle>
          <CardDescription>
            These people will be alerted if you do not respond to a safety check.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <Loader2 className="mx-auto size-6 animate-spin text-muted-foreground" />
          ) : contacts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No contacts added yet.</p>
          ) : (
            <ul className="space-y-2">
              {contacts.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                >
                  <span>
                    <span className="font-medium">{c.name}</span>
                    {c.phone && (
                      <span className="ml-2 text-muted-foreground">{c.phone}</span>
                    )}
                    <div className="flex gap-1">
                      {c.channels.map((ch) => (
                        <span
                          key={ch}
                          className="mt-0.5 rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground"
                        >
                          {ch}
                        </span>
                      ))}
                    </div>
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDelete(c.id)}
                    aria-label={`Delete ${c.name}`}
                  >
                    <Trash2 className="size-4 text-danger" />
                  </Button>
                </li>
              ))}
            </ul>
          )}

          <div className="space-y-2 border-t pt-4">
            <h4 className="text-sm font-semibold">Add contact</h4>
            <div className="grid gap-2">
              <div>
                <Label htmlFor="contact-name">Name</Label>
                <Input
                  id="contact-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Mom"
                />
              </div>
              <div>
                <Label htmlFor="contact-phone">Phone (for WhatsApp / Twilio)</Label>
                <Input
                  id="contact-phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+216..."
                />
              </div>
              <div>
                <Label htmlFor="contact-telegram">Telegram username</Label>
                <Input
                  id="contact-telegram"
                  value={telegramUsername}
                  onChange={(e) => setTelegramUsername(e.target.value)}
                  placeholder="@mom"
                />
              </div>
              <div>
                <Label>Alert channels</Label>
                <p className="mb-2 text-xs text-muted-foreground">
                  Pick one or more. Each contact is alerted on every chosen channel.
                </p>
                <div className="space-y-2">
                  {[
                    { id: "telegram", label: "Telegram" },
                    { id: "whatsapp", label: "WhatsApp" },
                    { id: "call", label: "Voice call (Twilio)" },
                  ].map((opt) => (
                    <label
                      key={opt.id}
                      className="flex items-center gap-2 text-sm cursor-pointer rounded-md border px-3 py-2 hover:bg-accent"
                    >
                      <input
                        type="checkbox"
                        className="size-4 accent-primary"
                        checked={channels.has(opt.id)}
                        onChange={() => toggleChannel(opt.id)}
                      />
                      <span>{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <Button onClick={handleAdd} disabled={!name.trim()}>
                <Plus className="mr-1 size-4" />
                Add contact
              </Button>
            </div>
          </div>

          {error && (
            <p className="text-xs text-danger">Error: {error}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Alert channels</CardTitle>
          <CardDescription>
            Each channel requires configuration in your <code>.env</code> file.
            See <code>.env.example</code> for details.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {[
            {
              name: "Telegram",
              hint: "Free, works worldwide. Requires TELEGRAM_BOT_TOKEN.",
              ready: true, // determined at runtime from health endpoint
            },
            {
              name: "WhatsApp",
              hint: "Free, works in Tunisia. Requires whatsapp-web.js bridge (node index.js).",
              ready: true,
            },
            {
              name: "Twilio voice",
              hint: "Paid outbound calls. TWILIO_* env vars. Tunisia not supported.",
              ready: false,
            },
          ].map((ch) => (
            <div
              key={ch.name}
              className="flex items-center justify-between rounded-md border px-3 py-2"
            >
              <div className="flex flex-col">
                <span className="font-medium">{ch.name}</span>
                <span className="text-xs text-muted-foreground">{ch.hint}</span>
              </div>
              <span
                className={`text-xs font-semibold ${ch.ready ? "text-success" : "text-muted-foreground"}`}
              >
                {ch.ready ? "Configured" : "Not set"}
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

function TestTab() {
  const { safety: polled } = useSafetyStatus()
  const [statusMsg, setStatusMsg] = useState("")
  const [testing, setTesting] = useState(false)
  // MINOR #30: subscribe to the safety WS for sub-second state updates and
  // an "incidents" toast. We prefer the WS snapshot over the polled SWR data
  // when the WS is connected; the polled value is the fallback if WS is down.
  const [wsSafety, setWsSafety] = useState<SafetyStatus | undefined>(polled)
  const { connected: wsConnected } = useSafetyEvents((evt) => {
    if (evt.type === "snapshot") {
      setWsSafety(evt.data as SafetyStatus)
    } else if (evt.type === "state") {
      const next = (evt as { data: { state: string } }).data.state
      setWsSafety((prev) => (prev ? { ...prev, state: next as SafetyState } : prev))
    }
  })
  const safety: SafetyStatus | undefined = wsConnected && wsSafety ? wsSafety : polled
  const state = (safety?.state ?? "unknown") as SafetyState

  const handleTestAlert = async () => {
    setTesting(true)
    setStatusMsg("")
    try {
      const result = await testSafetyAlert()
      setStatusMsg(`Test alert triggered — state is now: ${result.state}`)
    } catch (e) {
      setStatusMsg(`Failed: ${e}`)
    } finally {
      setTesting(false)
    }
  }

  const handleImOkay = async () => {
    setStatusMsg("")
    try {
      await voiceHeard("i'm okay")
      setStatusMsg("Response sent — alert cancelled if in confirmation window.")
    } catch (e) {
      setStatusMsg(`Failed: ${e}`)
    }
  }

  const handleCancel = async () => {
    setStatusMsg("")
    try {
      const result = await cancelSafetyAlert()
      setStatusMsg(`Cancelled: ${result.cancelled}, state: ${result.state}`)
    } catch (e) {
      setStatusMsg(`Failed: ${e}`)
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            Current state
            <span
              className={`text-xs font-normal ${
                wsConnected ? "text-success" : "text-muted-foreground"
              }`}
              title="Live event stream from /v1/safety/events WebSocket"
            >
              {wsConnected ? "● live (WebSocket)" : "○ polling"}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-4">
            <span className={`text-2xl font-bold ${STATE_COLORS[state] ?? ""}`}>
              {state}
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            {STATE_LABELS[state] ?? ""}
          </p>
          {safety && safety.confirmation_remaining_s > 0 && (
            <p className="mt-2 text-sm">
              Confirmation window:{" "}
              <strong>{Math.round(safety.confirmation_remaining_s)}s</strong> remaining
            </p>
          )}
          {safety && safety.cooldown_remaining_s > 0 && (
            <p className="mt-2 text-sm">
              Cooldown: <strong>{Math.round(safety.cooldown_remaining_s)}s</strong> remaining
            </p>
          )}
          {safety?.was_moving_recently !== undefined && (
            <p className="mt-2 text-sm">
              User was moving recently:{" "}
              <strong>{safety.was_moving_recently ? "Yes" : "No"}</strong>
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Test controls</CardTitle>
          <CardDescription>
            Trigger or cancel a safety alert for demo purposes.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Button
            onClick={handleTestAlert}
            disabled={testing || state !== "monitoring"}
            className="w-full"
          >
            <Zap className="mr-2 size-4" />
            {testing ? "Triggering…" : "Test alert (30s countdown)"}
          </Button>

          <Button
            onClick={handleImOkay}
            disabled={state !== "confirming"}
            className="w-full"
            variant="outline"
          >
            I'm okay — cancel alert
          </Button>

          <Button
            onClick={handleCancel}
            disabled={state !== "confirming"}
            className="w-full"
            variant="outline"
          >
            Cancel (same as "I'm okay")
          </Button>

          {statusMsg && (
            <p className="text-sm text-muted-foreground">{statusMsg}</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function IncidentsTab() {
  const [incidents, setIncidents] = useState<SafetyIncident[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getSafetyIncidents(50)
      setIncidents(data.incidents)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  // Load on mount (MINOR #24 — useEffect instead of render-time call)
  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Incident log</CardTitle>
        <CardDescription>
          Recent safety events — escalations and cancellations.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Loader2 className="mx-auto size-6 animate-spin text-muted-foreground" />
        ) : incidents.length === 0 ? (
          <p className="text-sm text-muted-foreground">No incidents recorded yet.</p>
        ) : (
          <ul className="space-y-2">
            {incidents.map((inc) => (
              <li
                key={inc.incident_id}
                className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              >
                <div className="flex flex-col">
                  <span className="font-medium">{inc.incident_id}</span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(inc.started_at * 1000).toLocaleString()} — {inc.trigger}
                  </span>
                  {inc.location_name && (
                    <span className="text-xs text-muted-foreground">
                      {inc.location_name}
                    </span>
                  )}
                </div>
                <span
                  className={`text-xs font-semibold ${
                    inc.outcome === "escalated_and_sent"
                      ? "text-danger"
                      : inc.outcome === "cancelled_by_voice"
                        ? "text-success"
                        : "text-muted-foreground"
                  }`}
                >
                  {inc.outcome}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export function SafetyPanel() {
  return (
    <Tabs defaultValue="test">
      <TabsList>
        <TabsTrigger value="test">Test</TabsTrigger>
        <TabsTrigger value="contacts">Contacts</TabsTrigger>
        <TabsTrigger value="incidents">Incidents</TabsTrigger>
      </TabsList>
      <TabsContent value="test" className="mt-4">
        <TestTab />
      </TabsContent>
      <TabsContent value="contacts" className="mt-4">
        <ContactsTab />
      </TabsContent>
      <TabsContent value="incidents" className="mt-4">
        <IncidentsTab />
      </TabsContent>
    </Tabs>
  )
}