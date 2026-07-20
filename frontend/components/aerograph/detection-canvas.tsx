"use client"

import { useEffect, useRef } from "react"
import type { Detection } from "@/lib/aerograph/types"

// Accessible, distinct box palette (no purple).
const PALETTE = [
  "#f5b73d", // amber
  "#5cc8ff", // sky
  "#5fd6a0", // green
  "#ff8a5c", // orange
  "#ff6b6b", // red
  "#8ad6d0", // teal
  "#e6d15c", // yellow
]

function colorForClass(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  }
  return PALETTE[hash % PALETTE.length]
}

interface Props {
  detections: Detection[]
  frameShape: [number, number] // [height, width]
}

/**
 * Abstract "radar" rendering of detections: bounding boxes on a dark grid,
 * scaled to the frame dimensions. No camera imagery is shown.
 */
export function DetectionCanvas({ detections, frameShape }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [fh, fw] = frameShape

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !fw || !fh) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const W = rect.width
    const H = rect.height
    const sx = W / fw
    const sy = H / fh

    ctx.clearRect(0, 0, W, H)

    // grid
    ctx.strokeStyle = "rgba(255,255,255,0.06)"
    ctx.lineWidth = 1
    const step = W / 12
    for (let x = step; x < W; x += step) {
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, H)
      ctx.stroke()
    }
    for (let y = step; y < H; y += step) {
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(W, y)
      ctx.stroke()
    }

    // center crosshair
    ctx.strokeStyle = "rgba(255,255,255,0.12)"
    ctx.beginPath()
    ctx.moveTo(W / 2, 0)
    ctx.lineTo(W / 2, H)
    ctx.moveTo(0, H / 2)
    ctx.lineTo(W, H / 2)
    ctx.stroke()

    ctx.font =
      "600 13px var(--font-atkinson), ui-sans-serif, system-ui, sans-serif"
    ctx.textBaseline = "bottom"

    for (const d of detections) {
      const [x1, y1, x2, y2] = d.bbox
      const rx = x1 * sx
      const ry = y1 * sy
      const rw = (x2 - x1) * sx
      const rh = (y2 - y1) * sy
      const color = colorForClass(d.class)

      ctx.fillStyle = `${color}22`
      ctx.fillRect(rx, ry, rw, rh)
      ctx.strokeStyle = color
      ctx.lineWidth = 2.5
      ctx.strokeRect(rx, ry, rw, rh)

      const label = `${d.class} ${Math.round(d.confidence * 100)}%`
      const metrics = ctx.measureText(label)
      const padX = 6
      const labelH = 20
      const labelW = metrics.width + padX * 2
      const ly = ry > labelH ? ry : ry + rh + labelH
      ctx.fillStyle = color
      ctx.fillRect(rx, ly - labelH, labelW, labelH)
      ctx.fillStyle = "#141414"
      ctx.fillText(label, rx + padX, ly - 4)
    }
  }, [detections, fw, fh])

  return (
    <canvas
      ref={canvasRef}
      className="size-full"
      role="img"
      aria-label={`Radar view showing ${detections.length} detected objects`}
    />
  )
}
