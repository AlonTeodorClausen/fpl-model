"""Session-only storage boundary for a future anonymous public deployment."""
import os
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st


def guest_mode():
    return os.environ.get('FPL_PUBLIC_GUEST_MODE') == '1'


def guest_root():
    """Keep visitor-specific imports and forecast caches out of shared files."""
    if '_guest_temp_directory' not in st.session_state:
        st.session_state['_guest_temp_directory'] = TemporaryDirectory(prefix='fpl_guest_')
    return Path(st.session_state['_guest_temp_directory'].name)


def parse_guest_profile_bytes(raw):
    """Reject unexpectedly large visitor files before JSON/profile validation."""
    if len(raw) > 64 * 1024:
        raise ValueError('Holdfilen er for stor (maksimalt 64 KB).')
    try:
        profile = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise ValueError('Holdfilen indeholder ugyldig JSON.') from None
    if not isinstance(profile, dict):
        raise ValueError('Holdfilens JSON skal være et objekt.')
    return profile
