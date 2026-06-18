"""Backend attentiveness monitoring aggregation.

The browser captures face/gaze samples and posts them here. The backend is the
authority for final attentiveness and eye-contact scores passed to the AI module.
"""

from __future__ import annotations


def _clamp(value: float) -> float:
    return float(max(0.0, min(100.0, round(value, 2))))


def empty_monitoring_state() -> dict:
    return {
        'samples': [],
        'events': {
            'tab_switches': 0,
            'window_blur_events': 0,
            'screenshot_attempted': 0,
            'device_detected': 0,
            'gaze_off_over_20s': 0,
            'english_only_violation': 0,
        },
        'flags': {
            'camera_available': 1,
            'mic_available': 1,
            'terminated_by_violation': False,
        },
    }


def merge_monitoring_state(existing: dict | None, incoming: dict) -> dict:
    """Merge incremental monitoring payloads into session state."""
    state = empty_monitoring_state()
    if existing:
        state['samples'] = list(existing.get('samples') or [])
        state['events'] = {**state['events'], **(existing.get('events') or {})}
        state['flags'] = {**state['flags'], **(existing.get('flags') or {})}

    for sample in incoming.get('samples') or []:
        if isinstance(sample, dict):
            state['samples'].append(sample)

    for key in state['events']:
        if key in (incoming.get('events') or {}):
            state['events'][key] = int((incoming.get('events') or {}).get(key, 0))

    for key in state['flags']:
        if key in (incoming.get('flags') or {}):
            state['flags'][key] = (incoming.get('flags') or {}).get(key, state['flags'][key])

    # Cap stored samples to keep JSON bounded (~15 min @ 800ms ≈ 1125 samples).
    if len(state['samples']) > 1500:
        state['samples'] = state['samples'][-1500:]

    return state


def compute_monitoring_scores(state: dict | None) -> dict:
    """Compute final attentiveness / eye-contact scores from stored samples."""
    state = state or empty_monitoring_state()
    samples = [s for s in (state.get('samples') or []) if isinstance(s, dict)]

    if not samples:
        return {
            'attentiveness_score': 100.0,
            'eye_contact_score': 100.0,
            'events': state.get('events') or {},
            'flags': state.get('flags') or {},
        }

    attentive_hits = sum(1 for s in samples if s.get('attentive'))
    eye_hits = sum(1 for s in samples if s.get('eye_contact'))
    total = len(samples)

    return {
        'attentiveness_score': _clamp((attentive_hits / total) * 100),
        'eye_contact_score': _clamp((eye_hits / total) * 100),
        'events': state.get('events') or {},
        'flags': state.get('flags') or {},
    }


def build_session_meta_from_monitoring(
    state: dict | None,
    *,
    avg_answer_seconds: float | None = None,
) -> dict:
    """Shape monitoring state for evaluate_interview_session session_meta."""
    scores = compute_monitoring_scores(state)
    events = scores['events']
    flags = scores['flags']
    return {
        'attentiveness_score': scores['attentiveness_score'],
        'eye_contact_score': scores['eye_contact_score'],
        'tab_switches': int(events.get('tab_switches', 0)),
        'window_blur_events': int(events.get('window_blur_events', 0)),
        'screenshot_attempted': int(events.get('screenshot_attempted', 0)),
        'device_detected': int(events.get('device_detected', 0)),
        'gaze_off_over_20s': int(events.get('gaze_off_over_20s', 0)),
        'english_only_violation': int(events.get('english_only_violation', 0)),
        'camera_available': int(flags.get('camera_available', 1)),
        'mic_available': int(flags.get('mic_available', 1)),
        'terminated_by_violation': bool(flags.get('terminated_by_violation', False)),
        'avg_answer_seconds': avg_answer_seconds,
    }
