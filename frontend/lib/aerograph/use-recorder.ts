"use client"

import { useCallback, useEffect, useRef, useState } from "react"

interface UseRecorderResult {
  isRecording: boolean
  seconds: number
  supported: boolean
  start: () => Promise<void>
  stop: () => Promise<Blob | null>
  cancel: () => void
}

export function useRecorder(): UseRecorderResult {
  const [isRecording, setIsRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [supported, setSupported] = useState(true)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    setSupported(
      typeof navigator !== "undefined" &&
        !!navigator.mediaDevices &&
        typeof window !== "undefined" &&
        "MediaRecorder" in window,
    )
  }, [])

  const cleanup = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    recorderRef.current = null
    chunksRef.current = []
  }, [])

  const start = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    streamRef.current = stream
    chunksRef.current = []
    const recorder = new MediaRecorder(stream)
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }
    recorder.start()
    recorderRef.current = recorder
    setIsRecording(true)
    setSeconds(0)
    timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000)
  }, [])

  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = recorderRef.current
      if (!recorder) {
        resolve(null)
        return
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        })
        cleanup()
        setIsRecording(false)
        resolve(blob.size > 0 ? blob : null)
      }
      recorder.stop()
    })
  }, [cleanup])

  const cancel = useCallback(() => {
    const recorder = recorderRef.current
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null
      recorder.stop()
    }
    cleanup()
    setIsRecording(false)
    setSeconds(0)
  }, [cleanup])

  useEffect(() => () => cleanup(), [cleanup])

  return { isRecording, seconds, supported, start, stop, cancel }
}
