"use client"

import {
  Loader2,
  MessagesSquare,
  Mic,
  Send,
  Server,
  Square,
  User,
  Volume2,
} from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { ApiError, queryText, queryVoice } from "@/lib/aerograph/client"
import { useSession } from "@/lib/aerograph/session-context"
import { useRecorder } from "@/lib/aerograph/use-recorder"
import { speak, ttsAvailable } from "@/lib/aerograph/tts"
import { cn } from "@/lib/utils"

interface Entry {
  id: string
  question: string
  answer: string
  voice?: boolean
  spokenOnServer?: boolean
}

const SUGGESTIONS = [
  "What's in front of me?",
  "Is there anything on the table?",
  "Where did I leave my cup?",
  "Are there any hazards nearby?",
]

export function QueryPanel() {
  const { active } = useSession()
  const recorder = useRecorder()
  const [question, setQuestion] = useState("")
  const [location, setLocation] = useState("")
  const [serverSpeak, setServerSpeak] = useState(false)
  const [autoSpeak, setAutoSpeak] = useState(false)
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState<Entry[]>([])

  const scope = () => {
    const opts: { session_id?: string; location_name?: string } = {}
    if (active) opts.session_id = active.sessionId
    if (location.trim()) opts.location_name = location.trim()
    return opts
  }

  async function ask(q: string) {
    const text = q.trim()
    if (!text) return
    setBusy(true)
    try {
      const res = await queryText(text, scope())
      const entry: Entry = {
        id: crypto.randomUUID(),
        question: text,
        answer: res.answer,
      }
      setLog((l) => [entry, ...l])
      setQuestion("")
      if (autoSpeak && ttsAvailable()) speak(res.answer)
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Query failed"
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  async function toggleRecording() {
    if (recorder.isRecording) {
      const blob = await recorder.stop()
      if (!blob) {
        toast.error("No audio captured")
        return
      }
      setBusy(true)
      try {
        const res = await queryVoice(blob, { ...scope(), speak: serverSpeak })
        const entry: Entry = {
          id: crypto.randomUUID(),
          question: res.transcription,
          answer: res.answer,
          voice: true,
          spokenOnServer: res.spoken,
        }
        setLog((l) => [entry, ...l])
        if (autoSpeak && !serverSpeak && ttsAvailable()) speak(res.answer)
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : "Voice query failed"
        toast.error(msg)
      } finally {
        setBusy(false)
      }
    } else {
      try {
        await recorder.start()
      } catch {
        toast.error("Microphone permission denied")
      }
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="flex flex-col gap-4">
        <div className="rounded-xl border border-border bg-card p-4">
          <Label htmlFor="question" className="mb-1.5 block font-semibold">
            Ask about the environment
          </Label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.nativeEvent.isComposing &&
                  e.keyCode !== 229
                ) {
                  ask(question)
                }
              }}
              placeholder="e.g. What's on my left?"
              className="h-11 flex-1 text-base"
              disabled={busy}
            />
            <div className="flex gap-2">
              <Button
                className="h-11 flex-1 sm:flex-none"
                onClick={() => ask(question)}
                disabled={busy || !question.trim()}
              >
                {busy && !recorder.isRecording ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <Send className="size-4" aria-hidden />
                )}
                Ask
              </Button>
              {recorder.supported && (
                <Button
                  variant={recorder.isRecording ? "destructive" : "outline"}
                  size="icon"
                  className="size-11 shrink-0"
                  onClick={toggleRecording}
                  disabled={busy && !recorder.isRecording}
                  aria-label={
                    recorder.isRecording ? "Stop recording" : "Ask by voice"
                  }
                >
                  {recorder.isRecording ? (
                    <Square className="size-4 fill-current" aria-hidden />
                  ) : (
                    <Mic className="size-4" aria-hidden />
                  )}
                </Button>
              )}
            </div>
          </div>

          {recorder.isRecording && (
            <p
              className="mt-2 flex items-center gap-2 text-sm font-medium text-danger"
              aria-live="assertive"
            >
              <span className="size-2 animate-pulse rounded-full bg-danger" />
              Recording… {recorder.seconds}s — tap the square to send
            </p>
          )}

          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => ask(s)}
                disabled={busy}
                className="rounded-full border border-border px-3 py-1 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {log.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-14 text-center">
            <MessagesSquare
              className="size-8 text-muted-foreground"
              aria-hidden
            />
            <p className="text-sm text-muted-foreground">
              Answers to your questions appear here.
            </p>
          </div>
        ) : (
          <ul className="flex flex-col gap-3" aria-live="polite">
            {log.map((e) => (
              <li
                key={e.id}
                className="rounded-xl border border-border bg-card p-4"
              >
                <p className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                  {e.voice ? (
                    <Mic className="size-4" aria-hidden />
                  ) : (
                    <User className="size-4" aria-hidden />
                  )}
                  {e.question || "(no transcription)"}
                </p>
                <p className="mt-2 text-pretty text-lg leading-relaxed">
                  {e.answer}
                </p>
                <div className="mt-2 flex items-center gap-2">
                  {e.spokenOnServer && (
                    <Badge variant="secondary" className="gap-1">
                      <Server className="size-3" aria-hidden />
                      Spoken on server
                    </Badge>
                  )}
                  {ttsAvailable() && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => speak(e.answer)}
                    >
                      <Volume2 className="size-4" aria-hidden />
                      Read aloud
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <aside className="flex h-fit flex-col gap-4 rounded-xl border border-border bg-card p-4">
        <div>
          <h3 className="font-bold">Query scope</h3>
          <p className="text-xs text-muted-foreground">
            Where the answer is drawn from.
          </p>
        </div>
        <div className="rounded-lg bg-secondary/60 p-3 text-sm">
          {active ? (
            <p>
              Using active session{" "}
              <span className="font-semibold">{active.locationName}</span>.
            </p>
          ) : (
            <p className="text-muted-foreground">
              No active session — the backend uses its current context or the
              location below.
            </p>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="scope-location">Location (optional)</Label>
          <Input
            id="scope-location"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g. Kitchen"
          />
        </div>

        <div className="border-t border-border pt-3">
          <h3 className="mb-2 font-bold">Speech</h3>
          <div className="flex items-center justify-between gap-2 py-1.5">
            <Label htmlFor="auto-speak" className="cursor-pointer">
              Read answers aloud
              <span className="block text-xs font-normal text-muted-foreground">
                In this browser
              </span>
            </Label>
            <Switch
              id="auto-speak"
              checked={autoSpeak}
              onCheckedChange={setAutoSpeak}
            />
          </div>
          <div className="flex items-center justify-between gap-2 py-1.5">
            <Label htmlFor="server-speak" className="cursor-pointer">
              Speak on server
              <span className="block text-xs font-normal text-muted-foreground">
                Voice queries use /speak
              </span>
            </Label>
            <Switch
              id="server-speak"
              checked={serverSpeak}
              onCheckedChange={setServerSpeak}
            />
          </div>
        </div>
      </aside>
    </div>
  )
}
