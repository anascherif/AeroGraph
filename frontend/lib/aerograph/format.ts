// Backend timestamps are Unix epoch. They may be seconds (float) or ms.
function toMs(ts: number): number {
  return ts < 1e12 ? ts * 1000 : ts
}

export function formatTime(ts: number | null | undefined): string {
  if (ts == null) return "—"
  return new Date(toMs(ts)).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

export function formatDateTime(ts: number | null | undefined): string {
  if (ts == null) return "—"
  return new Date(toMs(ts)).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function formatDuration(
  start: number | null | undefined,
  end: number | null | undefined,
): string {
  if (start == null || end == null) return "—"
  const seconds = Math.max(0, (toMs(end) - toMs(start)) / 1000)
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

export function relativeTime(ts: number | null | undefined): string {
  if (ts == null) return "—"
  const diff = Date.now() - toMs(ts)
  const sec = Math.round(diff / 1000)
  if (sec < 60) return `${sec}s ago`
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const d = Math.round(hr / 24)
  return `${d}d ago`
}

export function formatConfidence(c: number): string {
  return `${Math.round(c * 100)}%`
}
