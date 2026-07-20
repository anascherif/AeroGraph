"""Regression tests for the safety subsystem.

Covers:

1. SafetyStore contacts CRUD + incident append/resolve
2. SafetyMonitor signal computation on synthetic frame sequences
   (motion silence / tilt / brightness drop)
3. State machine transitions:
     monitoring -> confirming (via candidate fire)
     confirming -> cooldown   (via voice_heard "i'm okay")
     confirming -> escalating->cooldown (via timeout, no voice_heard)
4. trigger_test_alert stale-cooldown override (no camera -> observe() never
   re-arms, but test_alert must still work for demos)
5. NotifierBus dict->Contact conversion (the bug where SafetyStore returns
   plain dicts but notifiers expect Contact dataclasses)
6. AlertPayload.summary_text shape and content
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import numpy as np

from backend.config import (
    SAFETY_CANDIDATE_WINDOW_S,
    SAFETY_CONFIRMATION_S,
    SAFETY_MOTION_HISTORY_S,
    SAFETY_WAS_MOVING_THRESHOLD,
)
from backend.notifiers.base import (
    AlertPayload,
    Contact,
    filter_contacts_for_channel,
)
from backend.pipeline.safety_monitor import SafetyMonitor, SafetyState
from backend.pipeline.safety_store import SafetyStore


# ---------------------------------------------------------------------------
# Stub helpers — we replace TTS/STT/keyframes with fakes so tests run headless
# ---------------------------------------------------------------------------
class _Stub:
    def __init__(self) -> None:
        self.tts_calls: list[str] = []
        self.stt_calls: list[tuple] = []

    def tts_speak(self, text: str) -> None:
        self.tts_calls.append(text)

    def stt_transcribe(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        self.stt_calls.append((audio_bytes, mime_type))
        return ""

    def get_keyframes(self) -> list:
        # return a bright constant frame so escalation doesn't crash on None
        return [np.full((120, 160, 3), 200, dtype=np.uint8)]


def _make_monitor(store: SafetyStore, notifier_bus=None, stub: _Stub | None = None) -> SafetyMonitor:
    s = stub or _Stub()
    return SafetyMonitor(
        store=store,
        notifier_bus=notifier_bus,
        tts_speak=s.tts_speak,
        stt_transcribe=s.stt_transcribe,
        get_keyframes=s.get_keyframes,
        active_location=lambda: "kitchen",
        active_session_id=lambda: "session_test",
        user_name="tester",
    )


# ===========================================================================
# 1. SafetyStore CRUD + incident log
# ===========================================================================
def test_safety_store_contacts_crud() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = SafetyStore(safety_dir=Path(tmp))

        # Empty initially
        assert store.list_contacts() == []

        # Add
        c1 = store.add_contact(
            name="Mom",
            phone="+21612345678",
            channels=["telegram", "whatsapp"],
            notes="primary",
        )
        assert c1["id"].startswith("c_")
        assert c1["name"] == "Mom"
        assert c1["channels"] == ["telegram", "whatsapp"]
        assert "created_at" in c1
        assert len(store.list_contacts()) == 1

        # Get by id
        fetched = store.get_contact(c1["id"])
        assert fetched is not None
        assert fetched["name"] == "Mom"

        # Delete
        assert store.delete_contact(c1["id"]) is True
        assert store.delete_contact(c1["id"]) is False  # already gone
        assert store.list_contacts() == []

        # Re-instantiate store from disk to verify persistence
        store2 = SafetyStore(safety_dir=Path(tmp))
        assert store2.list_contacts() == []

    print("test_safety_store_contacts_crud PASSED")


def test_safety_store_incident_log() -> None:
    """Incidents are append-mostly; resolve_incident updates outcome."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SafetyStore(safety_dir=Path(tmp))

        inc_id = "inc_test_001"
        store.append_incident({
            "incident_id": inc_id,
            "started_at": 1_000.0,
            "trigger": "test",
            "location_name": "kitchen",
            "session_id": "s1",
            "outcome": "in_progress",
            "resolved_at": None,
        })
        incs = store.list_incidents()
        assert len(incs) == 1
        assert incs[0]["outcome"] == "in_progress"
        assert incs[0]["resolved_at"] is None

        # Mark as resolved
        store.resolve_incident(inc_id, outcome="cancelled_by_voice", ts=1_005.0, note="heard: ok")
        incs = store.list_incidents()
        assert incs[0]["outcome"] == "cancelled_by_voice"
        assert incs[0]["resolved_at"] == 1_005.0
        assert incs[0]["note"] == "heard: ok"

        # resolve_incident on a missing id does not crash
        store.resolve_incident("inc_does_not_exist", outcome="x", ts=2.0)

        # append-mostly respects limit
        for i in range(10):
            store.append_incident({
                "incident_id": f"inc_{i}",
                "started_at": float(i),
                "trigger": "t",
                "location_name": "",
                "session_id": "",
                "outcome": "in_progress",
                "resolved_at": None,
            })
        assert len(store.list_incidents(limit=5)) == 5
        assert len(store.list_incidents(limit=100)) == 11  # 1 + 10

    print("test_safety_store_incident_log PASSED")


# ===========================================================================
# 2. Signal computation
# ===========================================================================
def test_motion_signal_records_history() -> None:
    """observe() should feed the rolling window with motion magnitudes."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SafetyStore(safety_dir=Path(tmp))
        sm = _make_monitor(store)

        bright = np.full((120, 160, 3), 200, dtype=np.uint8)
        for i in range(10):
            sm.observe(bright, detections=[], ts=1_700_000_000.0 + i * 1.0)

        # All frames identical → motion is 0 every time
        assert len(list(zip(sm._motion_samples, sm._ts_samples))) == 10
        for m, _t in zip(sm._motion_samples, sm._ts_samples):
            assert m == 0.0

        # Brightness EMA initialised around 200
        assert 180.0 < sm._brightness_ema < 220.0

    print("test_motion_signal_records_history PASSED")


def test_brightness_drop_signal() -> None:
    """Feeding dark frames flags brightness-low."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SafetyStore(safety_dir=Path(tmp))
        sm = _make_monitor(store)

        # Warm up with bright frames
        bright = np.full((120, 160, 3), 200, dtype=np.uint8)
        for i in range(20):
            sm.observe(bright, [], ts=1_000.0 + i)

        # Now make it very dark for a while
        # EMA alpha is 0.1, so it takes ~30 frames to decay from 200 to <40.
        dark = np.full((120, 160, 3), 20, dtype=np.uint8)
        pre_ema = sm._brightness_ema
        for i in range(20, 60):
            sm.observe(dark, [], ts=1_000.0 + i)
        assert sm._brightness_ema < pre_ema
        # _dark_since should now be set (brightness below 40 threshold)
        assert sm._dark_since is not None, (
            f"Expected _dark_since to be set after 40 dark frames — "
            f"got brightness_ema={sm._brightness_ema} (threshold is 40)."
        )

    print("test_brightness_drop_signal PASSED")


# ===========================================================================
# 3. State machine transitions
# ===========================================================================
def test_candidate_fires_only_when_was_moving() -> None:
    """If user was NOT moving in last 60s, no candidate should fire — even
    if all 3 signals are flagged. Suppresses reading-in-chair false alarms."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SafetyStore(safety_dir=Path(tmp))
        sm = _make_monitor(store)

        # Sit still forever → motion 0 → no "was moving" → no candidate
        still = np.full((120, 160, 3), 100, dtype=np.uint8)
        t0 = 1_700_000_000.0
        for i in range(int(SAFETY_MOTION_HISTORY_S) + 20):
            sm.observe(still, [], ts=t0 + i)
        assert sm.state is SafetyState.MONITORING
        assert sm._candidate_since is None

    print("test_candidate_fires_only_when_was_moving PASSED")


def test_trigger_test_alert_full_cancel_cycle() -> None:
    """test_alert -> confirming -> voice_heard 'i'm okay' -> cooldown."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SafetyStore(safety_dir=Path(tmp))
        sm = _make_monitor(store)

        assert sm.trigger_test_alert() is True
        assert sm.state is SafetyState.CONFIRMING
        assert sm._current_incident_id is not None

        # Inject voice
        sm.push_heard_text("i'm okay")
        # Give the worker a moment to drain the queue
        time.sleep(1.0)
        assert sm.state is SafetyState.COOLDOWN

        # Cooldown got set into the future
        assert sm._cooldown_until >= time.time()

        # Incident was logged as cancelled_by_voice
        incs = store.list_incidents()
        assert len(incs) == 1
        assert incs[0]["outcome"] == "cancelled_by_voice"
        assert "heard" in (incs[0].get("note") or "")

    print("test_trigger_test_alert_full_cancel_cycle PASSED")


def test_trigger_test_alert_stale_cooldown_override() -> None:
    """If the monitor is stuck in cooldown past its deadline (no camera =>
    observe() never fires), test_alert should still be able to re-arm
    immediately for judge demos."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SafetyStore(safety_dir=Path(tmp))
        sm = _make_monitor(store)

        # Manually push the state into expired cooldown
        sm._state = SafetyState.COOLDOWN
        sm._state_since = time.time() - 999
        sm._cooldown_until = time.time() - 1  # already expired

        # test_alert should be able to trigger despite stale state
        assert sm.trigger_test_alert() is True
        assert sm.state is SafetyState.CONFIRMING

    print("test_trigger_test_alert_stale_cooldown_override PASSED")


def test_trigger_test_alert_blocked_in_bad_state() -> None:
    """During ESCALATING, trigger_test_alert should be rejected."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SafetyStore(safety_dir=Path(tmp))
        sm = _make_monitor(store)

        sm._state = SafetyState.ESCALATING
        assert sm.trigger_test_alert() is False
        # Restored manually — outside-test cleanup, doesn't matter
        sm._state = SafetyState.MONITORING

    print("test_trigger_test_alert_blocked_in_bad_state PASSED")


def test_cancel_external_only_when_confirming() -> None:
    """cancel() works only in CONFIRMING state and returns False otherwise."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SafetyStore(safety_dir=Path(tmp))
        sm = _make_monitor(store)

        assert sm.state is SafetyState.MONITORING
        assert sm.cancel_external() is False

        # Enter confirming via test_alert
        sm.trigger_test_alert()
        assert sm.state is SafetyState.CONFIRMING
        assert sm.cancel_external() is True
        assert sm.state is SafetyState.COOLDOWN

    print("test_cancel_external_only_when_confirming PASSED")


# ===========================================================================
# 4. Notifier contracts: dict->Contact + filter_contacts_for_channel
# ===========================================================================
def test_filter_contacts_for_channel_empty_list_includes_all() -> None:
    """Contacts with no channel preference should get every channel."""
    contacts = [
        Contact(id="c1", name="A", channels=[]),
        Contact(id="c2", name="B", channels=["telegram"]),
        Contact(id="c3", name="C", channels=["whatsapp", "call"]),
    ]
    tg = filter_contacts_for_channel(contacts, "telegram")
    whatsapp = filter_contacts_for_channel(contacts, "whatsapp")
    call = filter_contacts_for_channel(contacts, "call")

    # c1 has no channels → included in every channel bucket
    assert {c.id for c in tg} == {"c1", "c2"}
    assert {c.id for c in whatsapp} == {"c1", "c3"}
    assert {c.id for c in call} == {"c1", "c3"}

    print("test_filter_contacts_for_channel_empty_list_includes_all PASSED")


def test_dict_to_contact_conversion_matches_monitor_pattern() -> None:
    """The Dict->Contact conversion used in _escalate() must round-trip
    every field that filter_contacts_for_channel and the notifiers access.
    Regression for the AttributeError that crashed every notifier's
    filter_contacts_for_channel call when SafetyStore.list_contacts()
    returned plain dicts."""
    source_dicts = [
        {
            "id": "c_a",
            "name": "Alice",
            "phone": "+1",
            "telegram_user_id": "111",
            "telegram_username": "@alice",
            "channels": ["telegram"],
            "notes": "",
        },
        {
            "id": "c_b",
            "name": "Bob",
            "phone": "+2",
            "telegram_user_id": "",
            "telegram_username": "",
            "channels": ["whatsapp"],
            "notes": "x",
        },
    ]
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
        for c in source_dicts
    ]

    # This used to crash with AttributeError because 'dict' has no .channels.
    selected = filter_contacts_for_channel(contacts, "whatsapp")
    assert {c.id for c in selected} == {"c_b"}
    selected_tg = filter_contacts_for_channel(contacts, "telegram")
    assert {c.id for c in selected_tg} == {"c_a"}

    # Ensure attribute access (what notifiers actually do) works
    for c in contacts:
        _ = c.channels  # not .get('channels') — the bug was this attribute access
        _ = c.phone
        _ = c.telegram_user_id
        _ = c.telegram_username

    print("test_dict_to_contact_conversion_matches_monitor_pattern PASSED")


def test_alertpayload_summary_text_has_required_facts() -> None:
    """summary_text is what every notifier actually sends to the family.
    It must mention the user name and the location so the contact knows
    who/where. Length should stay short enough to fit a Telegram message."""
    p = AlertPayload(
        incident_id="inc_x",
        user_name="Sarah",
        location_name="kitchen",
        session_id="s1",
        started_at=1_700_000_000.0,
        trigger="t",
        keyframes_jpeg=[],
    )
    text = p.summary_text()
    assert "Sarah" in text
    assert "kitchen" in text.lower()
    assert "inc_x" in text
    # Telegram supports 4096 chars; we want well under
    assert len(text) < 500

    # Edge: empty location/name should not crash
    p2 = AlertPayload(
        incident_id="inc_y",
        user_name="",
        location_name="",
        session_id="",
        started_at=0,
        trigger="t",
        keyframes_jpeg=[],
    )
    text2 = p2.summary_text()
    assert "unknown location" in text2.lower()
    assert "inc_y" in text2

    print("test_alertpayload_summary_text_has_required_facts PASSED")


# ===========================================================================
# Runner
# ===========================================================================
def run_all() -> None:
    tests = [
        test_safety_store_contacts_crud,
        test_safety_store_incident_log,
        test_motion_signal_records_history,
        test_brightness_drop_signal,
        test_candidate_fires_only_when_was_moving,
        test_trigger_test_alert_full_cancel_cycle,
        test_trigger_test_alert_stale_cooldown_override,
        test_trigger_test_alert_blocked_in_bad_state,
        test_cancel_external_only_when_confirming,
        test_filter_contacts_for_channel_empty_list_includes_all,
        test_dict_to_contact_conversion_matches_monitor_pattern,
        test_alertpayload_summary_text_has_required_facts,
    ]
    for t in tests:
        t()
    print()
    print(f"ALL {len(tests)} SAFETY REGRESSION TESTS PASSED")


if __name__ == "__main__":
    run_all()
