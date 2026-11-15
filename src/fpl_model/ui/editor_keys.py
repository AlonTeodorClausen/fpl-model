"""Widget keys for the team editor, shared by Mit hold and the transfer lab."""
import streamlit as st


def editor_key(name):
    """Session-scoped widget key for the team editor.

    The transfer lab renders the same editor as Mit hold. Sharing widget keys
    across the two views let the browser send empty values for them after a
    page switch, so the lab uses its own prefix.
    """
    return st.session_state.get('_editor_key_prefix','')+name
