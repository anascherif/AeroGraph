"use client"

export function speak(text: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  utter.rate = 1
  utter.pitch = 1
  window.speechSynthesis.speak(utter)
}

export function speakSequence(lines: string[]) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return
  window.speechSynthesis.cancel()
  for (const line of lines) {
    const utter = new SpeechSynthesisUtterance(line)
    utter.rate = 1
    window.speechSynthesis.speak(utter)
  }
}

export function stopSpeaking() {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return
  window.speechSynthesis.cancel()
}

export function ttsAvailable(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window
}
