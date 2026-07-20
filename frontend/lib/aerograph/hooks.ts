"use client"

import useSWR from "swr"
import {
  getHealth,
  getSafetyStatus,
  getSessionObjects,
  getSessionScenes,
  listSessions,
} from "./client"

export function useHealth() {
  const { data, error, isLoading } = useSWR("health", getHealth, {
    refreshInterval: 5000,
    shouldRetryOnError: true,
    dedupingInterval: 2000,
  })
  return { health: data, error, isLoading, reachable: !error && !!data }
}

export function useSafetyStatus() {
  const { data, error, isLoading } = useSWR("safety-status", getSafetyStatus, {
    refreshInterval: 2000,
    shouldRetryOnError: false,
    dedupingInterval: 1000,
  })
  return { safety: data, error, isLoading, reachable: !error && !!data }
}

export function useSessions() {
  return useSWR("sessions", listSessions, { refreshInterval: 10000 })
}

export function useSessionObjects(sessionId: string | null) {
  return useSWR(sessionId ? ["objects", sessionId] : null, () =>
    getSessionObjects(sessionId as string),
  )
}

export function useSessionScenes(sessionId: string | null) {
  return useSWR(sessionId ? ["scenes", sessionId] : null, () =>
    getSessionScenes(sessionId as string),
  )
}
