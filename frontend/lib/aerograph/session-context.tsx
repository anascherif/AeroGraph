"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"

interface ActiveSession {
  sessionId: string
  locationName: string
  startedAt: number
}

interface SessionContextValue {
  active: ActiveSession | null
  setActive: (session: ActiveSession | null) => void
  /** Session currently selected for browsing (history/objects/diff). */
  selectedSessionId: string | null
  setSelectedSessionId: (id: string | null) => void
}

const SessionContext = createContext<SessionContextValue | null>(null)

const STORAGE_KEY = "aerograph:active-session"

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [active, setActiveState] = useState<ActiveSession | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    null,
  )

  // Restore an in-progress session on reload.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as ActiveSession
        setActiveState(parsed)
        setSelectedSessionId(parsed.sessionId)
      }
    } catch {
      // ignore
    }
  }, [])

  const setActive = useCallback((session: ActiveSession | null) => {
    setActiveState(session)
    try {
      if (session) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
      } else {
        window.localStorage.removeItem(STORAGE_KEY)
      }
    } catch {
      // ignore
    }
  }, [])

  const value = useMemo(
    () => ({ active, setActive, selectedSessionId, setSelectedSessionId }),
    [active, setActive, selectedSessionId],
  )

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  )
}

export function useSession() {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error("useSession must be used within SessionProvider")
  return ctx
}
