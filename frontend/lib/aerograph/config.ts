"use client"

// The AeroGraph backend base URL. Defaults to the documented localhost host,
// but can be overridden at runtime (persisted in localStorage) so the UI can
// point at a backend running elsewhere without a rebuild.

const DEFAULT_BASE =
  process.env.NEXT_PUBLIC_AEROGRAPH_API?.replace(/\/$/, "") ||
  "http://localhost:8000"

const STORAGE_KEY = "aerograph:base-url"

export function getApiBase(): string {
  if (typeof window === "undefined") return DEFAULT_BASE
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return (stored || DEFAULT_BASE).replace(/\/$/, "")
}

export function setApiBase(url: string) {
  if (typeof window === "undefined") return
  const clean = url.trim().replace(/\/$/, "")
  if (clean) {
    window.localStorage.setItem(STORAGE_KEY, clean)
  } else {
    window.localStorage.removeItem(STORAGE_KEY)
  }
  window.dispatchEvent(new Event("aerograph:base-url-changed"))
}

export function getDefaultBase(): string {
  return DEFAULT_BASE
}

/** Build the ws:// or wss:// URL for the stream endpoint from the REST base. */
export function getWsBase(): string {
  const base = getApiBase()
  return base.replace(/^http/, "ws")
}
