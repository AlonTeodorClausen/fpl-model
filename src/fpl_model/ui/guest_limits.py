"""Small in-process admission gate for anonymous, expensive UI actions.

This bounds one Streamlit process; it is not an IP-based or multi-worker limit.
"""

from math import ceil
from threading import Lock
from time import monotonic
from uuid import uuid4

import streamlit as st


class GuestLimitError(ValueError):
    """An anonymous action was declined before network or computation began."""


class _Permit:
    def __init__(self, gate, action):
        self.gate = gate
        self.action = action
        self.released = False

    def release(self):
        with self.gate._lock:
            if not self.released:
                self.gate._active[self.action] -= 1
                self.released = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.release()


class GuestJobGate:
    """Per-session cooldowns plus small process-wide spacing/concurrency caps."""

    def __init__(self, *, clock=monotonic, import_session_cooldown=30,
                 import_min_spacing=2, import_concurrency=2,
                 comparison_session_cooldown=60, comparison_concurrency=1):
        self._clock = clock
        self._cooldown = {'import': import_session_cooldown,
                          'comparison': comparison_session_cooldown}
        self._capacity = {'import': import_concurrency,
                          'comparison': comparison_concurrency}
        self._import_spacing = import_min_spacing
        if any(not isinstance(v, (int, float)) or v < 0 for v in
               (*self._cooldown.values(), self._import_spacing)) or any(
                   not isinstance(v, int) or v < 1 for v in self._capacity.values()):
            raise ValueError('Invalid guest job limits')
        self._lock = Lock()
        self._last_session = {}
        self._last_import = None
        self._active = {'import': 0, 'comparison': 0}

    def acquire(self, action, session_id):
        if action not in self._cooldown:
            raise ValueError('Unknown guest action')
        if not session_id:
            raise ValueError('Guest session ID is required')
        with self._lock:
            now = self._clock()
            # Long-running processes should not retain abandoned session IDs forever.
            oldest = now - max(self._cooldown.values(), default=0)
            self._last_session = {k: v for k, v in self._last_session.items() if v > oldest}
            previous = self._last_session.get((action, session_id))
            if previous is not None and now - previous < self._cooldown[action]:
                wait = ceil(self._cooldown[action] - (now - previous))
                raise GuestLimitError(f'Prøv igen om cirka {wait} sekunder; vent mellem gæstehandlinger.')
            if action == 'import' and self._last_import is not None and now - self._last_import < self._import_spacing:
                wait = ceil(self._import_spacing - (now - self._last_import))
                raise GuestLimitError(f'FPL-importen er netop brugt; vent cirka {wait} sekunder.')
            if self._active[action] >= self._capacity[action]:
                raise GuestLimitError('En anden beregning eller import kører allerede. Prøv igen, når den er færdig.')
            self._last_session[(action, session_id)] = now
            if action == 'import':
                self._last_import = now
            self._active[action] += 1
            return _Permit(self, action)


GUEST_GATE = GuestJobGate()


def claim_guest_job(action):
    if '_guest_session_id' not in st.session_state:
        st.session_state['_guest_session_id'] = uuid4().hex
    return GUEST_GATE.acquire(action, st.session_state['_guest_session_id'])
