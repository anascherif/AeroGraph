"""Safety monitor — body-cam distress detection + voice-confirmed escalation.

The camera is assumed to be body-worn (chest/head/neck), so the wearer is
never in frame. Person-bbox tracking is therefore useless for detecting
*the wearer's* fall. Instead we detect the camera-side signature of a
fall/distress event using three cheap orthogonal signals:

  1. Motion energy      — cv2.absdiff + cv2.mean over the last 60s of frames.
  2. Vertical tilt      — downwards optical-flow (Farneback) at 80x80.
  3. Brightness drop    — exponential-moving-average of grey-frame mean.

Fusion rule (debounced):
  Candidate fires when >= SAFETY_MIN_SIGNALS of the three are flagged
  simultaneously for >= SAFETY_CANDIDATE_WINDOW_S seconds, AND the user was
  moving within the last SAFETY_MOTION_HISTORY_S seconds.

The "was moving within last 60s" guard is the key anti-false-alarm measure:
it suppresses the alert for a user who's been sitting still reading for 5
minutes (normal) versus one who was walking one minute ago and is now
motionless on the ground (not normal).

State machine:
  MONITORING  -(candidate fires)->  CONFIRMING  -(no "ok" in 30s)->  ESCALATING  -(notifiers sent)->  COOLDOWN -(60s)->  MONITORING
                  ^                       |
                  +-- STT heard "I'm okay" --+

The state machine runs inline inside CameraStream._loop(). No new thread.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import re
import threading
import time
import uuid
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
# Module-level constants
# ---------------------------------------------------------------------------
# Word-boundary regex for STT phrase matching (MAJOR #19 — replaces naive `in`).
_STT_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(p) for p in SAFETY_STT_LISTEN_PHRASES)
    + r")\b"
)

# Motion silence threshold (CRITICAL #13 — was hardcoded 1.0).
_MOTION_SILENCE_THRESHOLD = 1.0  # ~1 grey-level of noise


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------
class SafetyState(str, Enum):
    MONITORING = "monitoring"
    CONFIRMING = "confirming"
    ESCALATING = "escalating"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"


# Valid state transitions (BLOCKER #6 — _transition validates source state).
_VALID_TRANSITIONS: dict[SafetyState, set[SafetyState]] = {
    SafetyState.MONITORING: {SafetyState.CONFIRMING},
    SafetyState.CONFIRMING: {SafetyState.ESCALATING, SafetyState.COOLDOWN},
    SafetyState.ESCALATING: {SafetyState.COOLDOWN},
    SafetyState.COOLDOWN: {SafetyState.MONITORING},
    SafetyState.DISABLED: set(),
}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
class EventBus:
    """Thread-safe pub-sub for safety events. Multiple subscribers, each
    gets its own queue. Drop-if-full (we never block the detection loop)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[int, collections.deque[dict]] = {}
        self._counter = 0

    def subscribe(self, maxsize: int = 64) -> tuple[int, collections.deque[dict]]:
        with self._lock:
            sid = self._counter
            self._counter += 1
            q: collections.deque[dict] = collections.deque(maxlen=maxsize)
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
                pass  # deque full -> drop


# ---------------------------------------------------------------------------
# SafetyMonitor
# ---------------------------------------------------------------------------
class SafetyMonitor:
    """Stateful body-cam distress detector + escalation coordinator.

    Lifecycle: typically one instance per server (registry-scoped singleton).
    Hold a reference via ``registry.safety_monitor``.

    Inputs:
      observe(frame, detections, ts)  -- called from CameraStream._loop after YOLO.

    Outputs:
      - State transitions published to internal EventBus (consumed by the WS endpoint).
      - Incident records appended to SafetyStore.
      - On escalate(): NotifierBus.send() in a fire-and-forget asyncio task.
    """

    _HISTORY_CAP = 600  # 60s * 10/s is more than we'll see at 5 FPS

    def __init__(
        self,
        store: Any,
        notifier_bus: Any,
        tts_speak: Any,
        stt_transcribe: Any,
        get_keyframes: Any,
        active_location: Any,
        active_session_id: Any,
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
        self._loop = loop

        # --- State lock (protects _state, _state_since, _cooldown_until) ---
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

        # sustained signal flags
        self._motion_silent_since: Optional[float] = None
        self._tilting_since: Optional[float] = None
        self._dark_since: Optional[float] = None

        # candidate tracking
        self._candidate_since: Optional[float] = None

        # confirmation state
        self._confirmation_started_at: Optional[float] = None
        self._confirmation_task: Optional[threading.Thread] = None
        # BLOCKER #3/#5: per-worker cancellation token (not shared across invocations)
        self._worker_cancel: Optional[threading.Event] = None

        # External "heard" queue — bounded (MAJOR #18) to prevent memory exhaustion.
        self._heard_queue: collections.deque[str] = collections.deque(maxlen=32)

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
        """Snapshot for GET /v1/safety/status.

        CRITICAL #11: snapshots deques under lock, releases lock *before*
        computing the return dict so no closures or external code runs
        under self._lock (avoids deadlock if closures touch the monitor).
        """
        with self._lock:
            ts = time.time()
            current_state = self._state
            state_since = self._state_since
            cooldown_until = self._cooldown_until
            candidate_since = self._candidate_since
            confirmation_started_at = self._confirmation_started_at
            incident_id = self._current_incident_id

            # Snapshot motion/brightness windows into local lists
            window_start = ts - SAFETY_MOTION_HISTORY_S
            motion_snap = [
                (m, t)
                for m, t in zip(self._motion_samples, self._ts_samples)
                if t >= window_start
            ]
            brightness_ema = self._brightness_ema

        # --- Lock released: compute everything from local snapshots ---
        was_moving = (
            any(m > SAFETY_WAS_MOVING_THRESHOLD for m, _ in motion_snap)
            if motion_snap
            else False
        )
        recent_motion = max((m for m, _ in motion_snap), default=0.0)

        return {
            "state": current_state.value,
            "state_since": state_since,
            "session_id": self._active_session_id() or "",
            "location_name": self._active_location() or "",
            "candidate_active": candidate_since is not None,
            "candidate_seconds": (
                ts - candidate_since if candidate_since else 0.0
            ),
            "confirmation_remaining_s": (
                max(
                    0.0,
                    SAFETY_CONFIRMATION_S - (ts - confirmation_started_at),
                ) if current_state is SafetyState.CONFIRMING
                and confirmation_started_at
                else 0.0
            ),
            "cooldown_remaining_s": max(0.0, cooldown_until - ts),
            "was_moving_recently": was_moving,
            "recent_motion_magnitude": round(recent_motion, 3),
            "brightness_ema": round(brightness_ema, 2),
            "current_incident_id": incident_id,
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
        """Called inline from CameraStream._loop after YOLO."""
        if self._state is SafetyState.DISABLED:
            return
        if self._state is SafetyState.COOLDOWN and ts < self._cooldown_until:
            return
        if self._state is SafetyState.COOLDOWN and ts >= self._cooldown_until:
            self._transition(SafetyState.MONITORING, ts, reason="cooldown elapsed")

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

        # Vertical tilt via subsampled Farneback optical flow
        if self._prev_gray_small is not None and (int(ts * 10) % 2 == 0):
            try:
                small = cv2.resize(gray, (80, 80))
                flow = cv2.calcOpticalFlowFarneback(
                    self._prev_gray_small, small, None,
                    0.5, 1, 15, 1, 5, 1.2, 0,
                )
                vert_flow_mag = float(np.mean(np.abs(flow[..., 1])))
            except Exception:
                vert_flow_mag = 0.0
            self._prev_gray_small = small
        else:
            if self._prev_gray_small is None:
                self._prev_gray_small = cv2.resize(gray, (80, 80))
            vert_flow_mag = 0.0

        # --- Sustained-signal timers ---
        # CRITICAL #13: use named constant instead of magic 1.0
        motion_silent = motion < _MOTION_SILENCE_THRESHOLD
        if motion_silent:
            if self._motion_silent_since is None:
                self._motion_silent_since = ts
        else:
            self._motion_silent_since = None

        tilting = vert_flow_mag > SAFETY_TILT_VERT_FLOW
        if tilting:
            if self._tilting_since is None:
                self._tilting_since = ts
        else:
            self._tilting_since = None

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
        with self._lock:
            window_start = ts - SAFETY_MOTION_HISTORY_S
            was_moving = any(
                m > SAFETY_WAS_MOVING_THRESHOLD
                for m, t in zip(self._motion_samples, self._ts_samples)
                if t >= window_start
            )

        if not was_moving:
            self._candidate_since = None
            return

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
                self._begin_confirmation(ts, trigger=f"{flagged}/3 signals sustained")
        else:
            if self._candidate_since is not None:
                self._publish("candidate_reset", {"reason": "signals no longer sustained"})
            self._candidate_since = None

    # ------------------------------------------------------------------
    # Confirmation / escalation / cooldown
    # ------------------------------------------------------------------
    def _begin_confirmation(self, ts: float, trigger: str) -> None:
        # BLOCKER #6: validate source state
        if self._state is not SafetyState.MONITORING:
            logger.warning(
                "safety: _begin_confirmation called in state %s, ignoring",
                self._state.value,
            )
            return

        # CRITICAL #15: uuid4 for incident IDs (was ms-timestamp — collision risk)
        self._current_incident_id = f"inc_{uuid.uuid4().hex[:12]}"
        self._confirmation_started_at = ts

        # BLOCKER #3/#5: per-worker cancellation token
        worker_cancel = threading.Event()
        self._worker_cancel = worker_cancel

        self._transition(SafetyState.CONFIRMING, ts, reason=trigger)

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

        try:
            self._tts_speak(
                "Are you okay? Say I'm okay, or press any button, within 30 seconds."
            )
        except Exception:
            logger.exception("safety: TTS confirmation prompt failed")

        self._confirmation_task = threading.Thread(
            target=self._confirmation_worker,
            args=(self._current_incident_id, worker_cancel),
            name="safety-confirmation",
            daemon=True,
        )
        self._confirmation_task.start()

    def _confirmation_worker(
        self, incident_id: str, cancel_token: threading.Event
    ) -> None:
        """BLOCKER #4: try/finally watchdog — on unhandled exception,
        transition to COOLDOWN so the monitor never wedges in CONFIRMING.
        """
        try:
            deadline = time.time() + SAFETY_CONFIRMATION_S

            while time.time() < deadline and not cancel_token.is_set():
                heard = self._drain_heard_queue()
                if heard:
                    text = heard.lower()
                    # MAJOR #19: word-boundary regex instead of naive `in`
                    if _STT_PATTERN.search(text):
                        self._cancel_alert(
                            outcome="cancelled_by_voice",
                            heard_text=text,
                        )
                        return
                time.sleep(0.5)

            # No "ok" heard within the window -> escalate.
            if not cancel_token.is_set():
                self._escalate(incident_id)
        except Exception:
            logger.exception(
                "safety: confirmation worker crashed — recovering to COOLDOWN"
            )
            # BLOCKER #4 watchdog: ensure we never stay wedged in CONFIRMING
            ts = time.time()
            with self._lock:
                if self._state is SafetyState.CONFIRMING:
                    self._cooldown_until = ts + SAFETY_COOLDOWN_S
                    self._state = SafetyState.COOLDOWN
                    self._state_since = ts
                    old_state = SafetyState.CONFIRMING
                else:
                    old_state = None
            if old_state is not None:
                self._publish("state", {
                    "from": old_state.value,
                    "to": SafetyState.COOLDOWN.value,
                    "reason": "confirmation worker exception — watchdog recovery",
                })

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
        self._transition(
            SafetyState.ESCALATING, ts, reason="no response in confirmation window"
        )

        # Collect keyframes
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

        try:
            self._tts_speak(
                "I've not gotten a response. I'm alerting your emergency contacts now."
            )
        except Exception:
            logger.exception("safety: TTS escalation announcement failed")

        raw_contacts = self._store.list_contacts()
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

        # MAJOR #17: check whether notifiers actually succeeded before
        # recording "escalated_and_sent". Was: always recorded, even on total
        # notifier failure (giving a false sense of successful escalation).
        any_success = False
        try:
            if self._loop is not None and self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._notifier_bus.send_all(contacts, payload), self._loop
                )
                results = future.result(timeout=30.0)
                any_success = any(
                    not isinstance(r, Exception) for r in results
                )
            else:
                results = asyncio.run(self._notifier_bus.send_all(contacts, payload))
                any_success = any(
                    not isinstance(r, Exception) for r in results
                )
        except Exception:
            logger.exception("safety: notifier_bus fan-out failed")

        outcome = "escalated_and_sent" if any_success else "escalation_attempted"
        try:
            self._store.resolve_incident(incident_id, outcome=outcome, ts=ts)
        except Exception:
            logger.exception("safety: store.resolve_incident failed")

        self._cooldown_until = ts + SAFETY_COOLDOWN_S
        self._transition(SafetyState.COOLDOWN, ts, reason="escalation completed")

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------
    def _cancel_alert(self, outcome: str, heard_text: str = "") -> None:
        ts = time.time()
        # BLOCKER #5: set per-worker cancel token so the running worker exits
        if self._worker_cancel is not None:
            self._worker_cancel.set()
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
        # CRITICAL #14: use SAFETY_COOLDOWN_S instead of hardcoded 60.0
        self._cooldown_until = ts + SAFETY_COOLDOWN_S
        self._transition(SafetyState.COOLDOWN, ts, reason="alert cancelled")

    def cancel_external(self) -> bool:
        """Called by POST /v1/safety/cancel (UI button press). Returns True
        if a confirmation was cancelled, False if we weren't confirming."""
        with self._lock:
            if self._state is not SafetyState.CONFIRMING:
                return False
        self._cancel_alert(outcome="cancelled_by_ui")
        return True

    def trigger_test_alert(self) -> bool:
        """Called by POST /v1/safety/test_alert (judge demo button). Skips
        detection — enters confirmation directly. Returns True if triggered."""
        with self._lock:
            fs = self._state
            ts = time.time()
            # If we're stuck in cooldown past the deadline (no camera → observe()
            # never gets a chance to flip us back to MONITORING), transition now
            # so the demo button always works.
            if fs is SafetyState.COOLDOWN and ts >= self._cooldown_until:
                self._state = SafetyState.MONITORING
                self._state_since = ts
                old_state = SafetyState.COOLDOWN
            else:
                old_state = None
            if fs is SafetyState.COOLDOWN and old_state is not None:
                fs = SafetyState.MONITORING
            if fs is not SafetyState.MONITORING:
                return False
        if old_state is SafetyState.COOLDOWN:
            self._publish("state", {
                "from": SafetyState.COOLDOWN.value,
                "to": SafetyState.MONITORING.value,
                "reason": "cooldown elapsed (test_alert)",
            })
        self._begin_confirmation(ts, trigger="manual test_alert (detection skipped)")
        return True

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called from main.py startup once asyncio loop is available."""
        self._loop = loop

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _transition(self, new_state: SafetyState, ts: float, reason: str = "") -> None:
        """BLOCKER #6: validate source state. Rejects invalid transitions
        (e.g., ESCALATING -> MONITORING) with a warning log instead of
        silently flipping state and wedging the state machine."""
        with self._lock:
            old = self._state
            if old is new_state:
                return
            valid_targets = _VALID_TRANSITIONS.get(old, set())
            if new_state not in valid_targets:
                logger.warning(
                    "safety: ignoring invalid transition %s -> %s (%s)",
                    old.value, new_state.value, reason,
                )
                return
            self._state = new_state
            self._state_since = ts
        # Publish outside lock to avoid holding it during subscriber I/O
        self._publish("state", {
            "from": old.value,
            "to": new_state.value,
            "reason": reason,
        })
        logger.info("safety: %s -> %s (%s)", old.value, new_state.value, reason)

    def _publish(self, event_type: str, data: dict) -> None:
        self.events.publish({
            "type": event_type,
            "ts": time.time(),
            **data,
        })
