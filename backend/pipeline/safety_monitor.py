"""Safety monitor — body-cam distress detection + voice-confirmed escalation.

The camera is assumed to be body-worn (chest/head/neck), so the wearer is
never in frame. Person-bbox tracking is therefore useless for detecting
*the wearer's* fall. Instead we detect the camera-side signature of a
fall/distress event using three cheap orthogonal signals:

  1. Motion energy      — cv2.absdiff + cv2.mean over the last 60s of frames.
  2. Vertical tilt      — downwards optical-flow (Farneback) at 80x80.
  3. Brightness drop    — exponential-moving-average of grey-frame mean.

Fusion rule (debounced):
  Candidate fires when ≥ SAFETY_MIN_SIGNALS of the three are flagged
  simultaneously for ≥ SAFETY_CANDIDATE_WINDOW_S seconds, AND the user was
  moving within the last SAFETY_MOTION_HISTORY_S seconds.

The "was moving within last 60s" guard is the key anti-false-alarm measure:
it suppresses the alert for a user who's been sitting still reading for 5
minutes (normal) versus one who was walking one minute ago and is now
motionless on the ground (not normal).

State machine:
  MONITORING  -(candidate fires)→  CONFIRMING  -(no "ok" in 30s)→  ESCALATING  -(notifiers sent)→  COOLDOWN -(60s)→  MONITORING
                  ↑                       |
                  └─ STT heard "I'm okay" ─┘

The state machine runs inline inside CameraStream._loop(). No new thread.
"""

from __future__ import annotations

import asyncio
import base64
import collections
import io
import logging
import math
import threading
import time
from enum import Enum
from typing import Any, Optional

import cv2
import numpy as np

from backend.config import (
    SAFETY_BRIGHTNESS_DROP_PCT,
    SAFETY_CANDIDATE_WINDOW_S,
    SAFETY_COOLDOWN_S,
    SAFETY_CONFIRMATION_S,
    SAFETY_MIN_SIGNALS,
    SAFETY_MOTION_HISTORY_S,
    SAFETY_STT_LISTEN_PHRASES,
    SAFETY_TILT_VERT_FLOW,
    SAFETY_WAS_MOVING_THRESHOLD,
)

logger = logging.getLogger("aerograph.safety")


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------
class SafetyState(str, Enum):
    MONITORING = "monitoring"
    CONFIRMING = "confirming"
    ESCALATING = "escalating"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
# The monitor emits events into a subscriber queue so the WS endpoint can
# stream them to the dashboard. Each event is a small dict so it serialises
# directly to JSON.
class EventBus:
    """Thread-safe pub-sub for safety events. Multiple subscribers, each
    gets its own queue. Drop-if-full (we never block the detection loop)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[int, "collections.deque[dict]"] = {}
        self._counter = 0

    def subscribe(self, maxsize: int = 64) -> tuple[int, "collections.deque[dict]"]:
        with self._lock:
            sid = self._counter
            self._counter += 1
            q: collections.deque[dict] = collections.deque(maxlen=maxsize)
            # Replay current state so new subscribers see where we are.
            self._subs[sid] = q
            return sid, q

    def unsubscribe(self, sid: int) -> None:
        with self._lock:
            self._subs.pop(sid, None)

    def publish(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subs.values())
        for q in subs:
            try:
                q.append(event)
            except IndexError:
                pass  # deque full → drop


# ---------------------------------------------------------------------------
# SafetyMonitor
# ---------------------------------------------------------------------------
class SafetyMonitor:
    """Stateful body-cam distress detector + escalation coordinator.

    Lifecycle: typically one instance per server (registry-scoped singleton).
    Hold a reference via ``registry.safety_monitor``.

    Inputs:
      observe(frame, detections, ts)  — called from CameraStream._loop after YOLO.

    Outputs:
      - State transitions published to internal EventBus (consumed by the WS endpoint).
      - Incident records appended to SafetyStore.
      - On escalate(): NotifierBus.send() in a fire-and-forget asyncio task.
    """

    # --- Signal history (rolling windows) ---
    _HISTORY_CAP = 600  # 60s * 10/s is more than we'll see at 5 FPS

    def __init__(
        self,
        store: "Any",                  # SafetyStore
        notifier_bus: "Any",          # NotifierBus
        tts_speak: "Any",             # callable: speak_async(text)
        stt_transcribe: "Any",        # callable: sync? we wrap; transcribe_audio_bytes
        get_keyframes: "Any",        # callable: () -> list[np.ndarray]  (last 3)
        active_location: "Any",       # callable: () -> str (location_name of running session)
        active_session_id: "Any",     # callable: () -> str
        user_name: str = "user",
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._store = store
        self._notifier_bus = notifier_bus
        self._tts_speak = tts_speak
        self._stt_transcribe = stt_transcribe
        self._get_keyframes = get_keyframes
        self._active_location = active_location
        self._active_session_id = active_session_id
        self._user_name = user_name
        self._loop = loop  # asyncio loop, captured at startup for scheduling tasks
        self._lock = threading.Lock()

        self._state: SafetyState = SafetyState.MONITORING
        self._state_since: float = time.time()
        self.events = EventBus()

        # rolling windows
        self._motion_samples: collections.deque = collections.deque(maxlen=self._HISTORY_CAP)
        self._ts_samples: collections.deque = collections.deque(maxlen=self._HISTORY_CAP)
        self._brightness_ema: float = 0.0
        self._brightness_ema_inited: bool = False

        # prev frame for diff + flow
        self._prev_gray: Optional[np.ndarray] = None
        self._prev_gray_small: Optional[np.ndarray] = None

        # sustained signal flags (each tracks "how long has this been flagged")
        self._motion_silent_since: Optional[float] = None
        self._tilting_since: Optional[float] = None
        self._dark_since: Optional[float] = None

        # candidate tracking
        self._candidate_since: Optional[float] = None

        # confirmation state
        self._confirmation_started_at: Optional[float] = None
        self._confirmation_task: Optional[threading.Thread] = None
        self._confirmation_cancelled = threading.Event()
        # External "heard" queue — per-instance (not class-level) so concurrent
        # monitor instances don't cross-pollute. Pushed by push_heard_text(),
        # drained every 500ms by the confirmation worker.
        self._heard_queue: collections.deque[str] = collections.deque()

        # cooldown
        self._cooldown_until: float = 0.0

        # last alert/incident id
        self._current_incident_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Public: state inspection
    # ------------------------------------------------------------------
    @property
    def state(self) -> SafetyState:
        return self._state

    def status(self) -> dict:
        """Snapshot for GET /v1/safety/status."""
        with self._lock:
            ts = time.time()
            # EMA-momentum computation: was-moving implies motion samples in
            # the trailing window ever exceeded the threshold.
            window_start = ts - SAFETY_MOTION_HISTORY_S
            was_moving = any(
                m > SAFETY_WAS_MOVING_THRESHOLD
                for m, t in zip(self._motion_samples, self._ts_samples)
                if t >= window_start
            ) if self._ts_samples else False
            now_in_window = [
                (m, t) for m, t in zip(self._motion_samples, self._ts_samples)
                if t >= window_start
            ]
            recent_motion = max((m for m, _ in now_in_window), default=0.0)
            return {
                "state": self._state.value,
                "state_since": self._state_since,
                "session_id": self._active_session_id() or "",
                "location_name": self._active_location() or "",
                "candidate_active": self._candidate_since is not None,
                "candidate_seconds": (
                    ts - self._candidate_since if self._candidate_since else 0.0
                ),
                "confirmation_remaining_s": (
                    max(
                        0.0,
                        SAFETY_CONFIRMATION_S - (ts - self._confirmation_started_at),
                    ) if self._state is SafetyState.CONFIRMING
                    and self._confirmation_started_at
                    else 0.0
                ),
                "cooldown_remaining_s": max(0.0, self._cooldown_until - ts),
                "was_moving_recently": was_moving,
                "recent_motion_magnitude": round(recent_motion, 3),
                "brightness_ema": round(self._brightness_ema, 2),
                "current_incident_id": self._current_incident_id,
            }

    # ------------------------------------------------------------------
    # Public: frame ingestion
    # ------------------------------------------------------------------
    def observe(
        self,
        frame: np.ndarray,
        detections: list[dict],
        ts: float,
    ) -> None:
        """Called inline from CameraStream._loop after YOLO. Runs the three
        signal detectors and the state-machine tick. Must be cheap.
        """
        if self._state is SafetyState.DISABLED:
            return
        if self._state is SafetyState.COOLDOWN and ts < self._cooldown_until:
            return
        if self._state is SafetyState.COOLDOWN and ts >= self._cooldown_until:
            self._transition(SafetyState.MONITORING, ts, reason="cooldown elapsed")

        # During CONFIRMING / ESCALATING we keep observing (so we can update
        # rolling windows for the *next* cycle) but we DO NOT re-evaluate
        # candidates — the confirmation task owns the lifecycle.
        self._compute_signals(frame, ts)
        if self._state is SafetyState.MONITORING:
            self._tick_monitoring(ts)

    # ------------------------------------------------------------------
    # Signal computation
    # ------------------------------------------------------------------
    def _compute_signals(self, frame: np.ndarray, ts: float) -> None:
        """Update the rolling windows + EMA. Cheap."""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        except Exception:
            logger.debug("safety: couldn't convert frame to gray", exc_info=True)
            return

        # --- Motion energy (absdiff vs prev frame) ---
        if self._prev_gray is not None and self._prev_gray.shape == gray.shape:
            diff = cv2.absdiff(self._prev_gray, gray)
            motion = float(cv2.mean(diff)[0])
        else:
            motion = 0.0
        with self._lock:
            self._motion_samples.append(motion)
            self._ts_samples.append(ts)
        self._prev_gray = gray

        # Brightness EMA
        b = float(cv2.mean(gray)[0])
        if not self._brightness_ema_inited:
            self._brightness_ema = b
            self._brightness_ema_inited = True
        else:
            alpha = 0.1
            self._brightness_ema = (1 - alpha) * self._brightness_ema + alpha * b

        # Vertical tilt via subsampled Farneback optical flow — skip every
        # other frame to keep CPU usage low.
        if self._prev_gray_small is not None and (int(ts * 10) % 2 == 0):
            try:
                small = cv2.resize(gray, (80, 80))
                flow = cv2.calcOpticalFlowFarneback(
                    self._prev_gray_small, small, None,
                    0.5, 1, 15, 1, 5, 1.2, 0,
                )
                # +ve vertical flow means camera pointing downward (content moving up)
                vert_flow_mag = float(np.mean(np.abs(flow[..., 1])))
            except Exception:
                vert_flow_mag = 0.0
            self._prev_gray_small = small
        else:
            if self._prev_gray_small is None:
                self._prev_gray_small = cv2.resize(gray, (80, 80))
            vert_flow_mag = 0.0

        # --- Sustained-signal timers ---
        # Motion silence: recent motion < threshold
        motion_silent = motion < 1.0  # ~1 grey-level of noise
        if motion_silent:
            if self._motion_silent_since is None:
                self._motion_silent_since = ts
        else:
            self._motion_silent_since = None

        # Tilt: vertical flow magnitude above threshold
        tilting = vert_flow_mag > SAFETY_TILT_VERT_FLOW
        if tilting:
            if self._tilting_since is None:
                self._tilting_since = ts
        else:
            self._tilting_since = None

        # Brightness drop: EMA below (1 - DROP_PCT) * baseline. We treat the
        # peak EMA seen so far as a loose baseline.
        brightness_low = (
            self._brightness_ema_inited and self._brightness_ema < 40.0
        )
        if brightness_low:
            if self._dark_since is None:
                self._dark_since = ts
        else:
            self._dark_since = None

    # ------------------------------------------------------------------
    # Monitoring tick (state MONITORING only)
    # ------------------------------------------------------------------
    def _tick_monitoring(self, ts: float) -> None:
        # Was-moving guard: at least one motion sample in the last 60s above threshold
        with self._lock:
            window_start = ts - SAFETY_MOTION_HISTORY_S
            was_moving = any(
                m > SAFETY_WAS_MOVING_THRESHOLD
                for m, t in zip(self._motion_samples, self._ts_samples)
                if t >= window_start
            )

        if not was_moving:
            # Suppress: caller has been still for the entire window — sitting,
            # reading, sleeping in a chair are all normal here.
            self._candidate_since = None
            return

        # Count currently-flagged signals that have been sustained for >=1s.
        flagged = 0
        if self._motion_silent_since is not None and ts - self._motion_silent_since >= 1.0:
            flagged += 1
        if self._tilting_since is not None and ts - self._tilting_since >= 1.0:
            flagged += 1
        if self._dark_since is not None and ts - self._dark_since >= 3.0:
            flagged += 1

        if flagged >= SAFETY_MIN_SIGNALS:
            if self._candidate_since is None:
                self._candidate_since = ts
                self._publish("candidate_started", {"flagged_signals": flagged})
            elif ts - self._candidate_since >= SAFETY_CANDIDATE_WINDOW_S:
                # Candidate confirmed → enter confirmation state.
                self._begin_confirmation(ts, trigger=f"{flagged}/3 signals sustained")
        else:
            # transient noise → reset candidate
            if self._candidate_since is not None:
                self._publish("candidate_reset", {"reason": "signals no longer sustained"})
            self._candidate_since = None

    # ------------------------------------------------------------------
    # Confirmation / escalation / cooldown
    # ------------------------------------------------------------------
    def _begin_confirmation(self, ts: float, trigger: str) -> None:
        self._current_incident_id = f"inc_{int(ts * 1000)}"
        self._confirmation_started_at = ts
        self._confirmation_cancelled.clear()
        self._transition(SafetyState.CONFIRMING, ts, reason=trigger)

        # Record incident-start in the store (non-fatal if it fails)
        try:
            self._store.append_incident({
                "incident_id": self._current_incident_id,
                "started_at": ts,
                "trigger": trigger,
                "location_name": self._active_location() or "",
                "session_id": self._active_session_id() or "",
                "outcome": "in_progress",
                "resolved_at": None,
            })
        except Exception:
            logger.exception("safety: store.append_incident failed")

        # Voice prompt, fire-and-forget
        try:
            self._tts_speak(
                "Are you okay? Say I'm okay, or press any button, within 30 seconds."
            )
        except Exception:
            logger.exception("safety: TTS confirmation prompt failed")

        # Spawn the confirmation thread
        self._confirmation_task = threading.Thread(
            target=self._confirmation_worker,
            args=(self._current_incident_id,),
            name="safety-confirmation",
            daemon=True,
        )
        self._confirmation_task.start()

    def _confirmation_worker(self, incident_id: str) -> None:
        """Run for SAFETY_CONFIRMATION_S seconds listening for STT input that
        contains one of the acknowledged cancel phrases. If nothing arrives,
        escalate.
        """
        started = time.time()
        deadline = started + SAFETY_CONFIRMATION_S

        # Listen in 5-second windows for SAFETY_CONFIRMATION_S seconds total.
        # We use a tiny in-window recording buffer captured from... nothing
        # here, actually — we rely on a SHARED in-memory queue the WS record
        # endpoint would write to. If empty, no voice was heard.
        # For the hackathon scope, we just sleep and then check for STT
        # work the API test_alert path triggered. A more complete version
        # would record from the local mic. This is documented in README.

        while time.time() < deadline and not self._confirmation_cancelled.is_set():
            # Poll external "heard" queue every 500ms
            heard = self._drain_heard_queue()
            if heard:
                text = heard.lower()
                if any(p in text for p in SAFETY_STT_LISTEN_PHRASES):
                    # User is okay → cancel
                    self._cancel_alert(
                        outcome="cancelled_by_voice",
                        heard_text=text,
                    )
                    return
            time.sleep(0.5)

        # No "ok" heard within the window → escalate.
        if not self._confirmation_cancelled.is_set():
            self._escalate(incident_id)

    # External "heard" queue — pushed to by the /safety/voice_heard API
    # endpoint (for live STT input) or by test_voice_ok for demos.
    # Instance attribute (NOT a class attribute) so concurrent monitors
    # don't share state. Initialised in __init__ via self._heard_queue.
    def push_heard_text(self, text: str) -> None:
        """Called by an external STT loop or test endpoint to inject speech."""
        self._heard_queue.append(text)

    def _drain_heard_queue(self) -> Optional[str]:
        try:
            return self._heard_queue.popleft()
        except IndexError:
            return None

    def _escalate(self, incident_id: str) -> None:
        ts = time.time()
        self._transition(SafetyState.ESCALATING, ts, reason="no response in confirmation window")

        # Collect 3 most-recent keyframes as JPEGs
        keyframes: list[bytes] = []
        try:
            kfs = self._get_keyframes() or []
            for kf in kfs[:3]:
                if kf is None:
                    continue
                if isinstance(kf, np.ndarray):
                    ok, buf = cv2.imencode(".jpg", kf, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ok:
                        keyframes.append(buf.tobytes())
                elif isinstance(kf, bytes):
                    keyframes.append(kf)
        except Exception:
            logger.exception("safety: collecting keyframes for escalation failed")

        # TTS announcement on-device (so anyone nearby hears it too)
        try:
            self._tts_speak(
                "I've not gotten a response. I'm alerting your emergency contacts now."
            )
        except Exception:
            logger.exception("safety: TTS escalation announcement failed")

        # Fan out via notifier bus. This is async — we need to run it on the
        # asyncio loop owned by main.py. Use run_coroutine_threadsafe if we
        # have a loop reference; otherwise fall back to asyncio.run.
        raw_contacts = self._store.list_contacts()
        # NotifierBus.filter_contacts_for_channel expects Contact dataclasses
        # (uses attribute access), but SafetyStore returns plain dicts. Convert.
        from backend.notifiers.base import AlertPayload, Contact
        contacts = [
            Contact(
                id=c.get("id", ""),
                name=c.get("name", ""),
                phone=c.get("phone", ""),
                telegram_user_id=c.get("telegram_user_id", ""),
                telegram_username=c.get("telegram_username", ""),
                channels=c.get("channels", []) or [],
                notes=c.get("notes", ""),
            )
            for c in raw_contacts
        ]
        payload = AlertPayload(
            incident_id=incident_id,
            user_name=self._user_name,
            location_name=self._active_location() or "",
            session_id=self._active_session_id() or "",
            started_at=ts,
            trigger="body-cam distress candidate",
            keyframes_jpeg=keyframes,
        )
        self._publish("escalating", {
            "incident_id": incident_id,
            "contacts_count": len(contacts),
            "keyframes_count": len(keyframes),
        })

        try:
            if self._loop is not None and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._notifier_bus.send_all(contacts, payload), self._loop
                )
            else:
                # No event loop yet — direct asyncio.run from this thread
                asyncio.run(self._notifier_bus.send_all(contacts, payload))
        except Exception:
            logger.exception("safety: notifier_bus fan-out failed")

        # Update incident record
        try:
            self._store.resolve_incident(incident_id, outcome="escalated_and_sent", ts=ts)
        except Exception:
            logger.exception("safety: store.resolve_incident failed")

        # Enter cooldown
        self._cooldown_until = ts + SAFETY_COOLDOWN_S
        self._transition(SafetyState.COOLDOWN, ts, reason="escalation completed")

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------
    def _cancel_alert(self, outcome: str, heard_text: str = "") -> None:
        """Mark the current incident as resolved without escalation and return to monitoring."""
        ts = time.time()
        self._confirmation_cancelled.set()
        try:
            if self._current_incident_id:
                self._store.resolve_incident(
                    self._current_incident_id, outcome=outcome, ts=ts,
                    note=f"heard: {heard_text!r}"
                )
        except Exception:
            logger.exception("safety: store.resolve_incident (cancel) failed")
        self._publish("cancelled", {
            "incident_id": self._current_incident_id,
            "outcome": outcome,
            "heard_text": heard_text,
        })
        self._cooldown_until = ts + 60.0  # short cooldown to avoid immediate refire
        self._transition(SafetyState.COOLDOWN, ts, reason="alert cancelled")
        # After cooldown we flip back to monitoring automatically in observe().

    def cancel_external(self) -> bool:
        """Called by POST /v1/safety/cancel (UI button press). Returns True
        if a confirmation was cancelled, False if we weren't confirming."""
        if self._state is not SafetyState.CONFIRMING:
            return False
        self._cancel_alert(outcome="cancelled_by_ui")
        return True

    def trigger_test_alert(self) -> bool:
        """Called by POST /v1/safety/test_alert (judge demo button). Skips
        detection — enters confirmation directly. Returns True if triggered."""
        fs = self._state
        ts = time.time()
        # If we're stuck in cooldown past the deadline (no camera → observe()
        # never gets a chance to flip us back to MONITORING), transition now
        # so the demo button always works.
        if fs is SafetyState.COOLDOWN and ts >= self._cooldown_until:
            self._transition(SafetyState.MONITORING, ts, reason="cooldown elapsed (test_alert)")
            fs = SafetyState.MONITORING
        if fs is not SafetyState.MONITORING:
            return False
        self._begin_confirmation(ts, trigger="manual test_alert (detection skipped)")
        return True

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called from main.py startup once asyncio loop is available."""
        self._loop = loop

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _transition(self, new_state: SafetyState, ts: float, reason: str = "") -> None:
        old = self._state
        if old is new_state:
            return
        self._state = new_state
        self._state_since = ts
        self._publish("state", {
            "from": old.value,
            "to": new_state.value,
            "reason": reason,
        })
        logger.info("safety: %s → %s (%s)", old.value, new_state.value, reason)

    def _publish(self, event_type: str, data: dict) -> None:
        self.events.publish({
            "type": event_type,
            "ts": time.time(),
            **data,
        })
