"""Latest local selection uses real verified captures without network requests."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from fpl_model.ui import my_team as ui
from test_quick_refresh import _snapshot

APP=str(Path(__file__).resolve().parents[1]/'app.py')


def local_app(monkeypatch,tmp_path):
    monkeypatch.setattr(ui,'LOCAL_ROOT',tmp_path)
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026,10,17,12,tzinfo=timezone.utc)
    monkeypatch.setattr(ui,'datetime',Clock)
    st.cache_data.clear()
    return AppTest.from_file(APP).run(timeout=30)


def test_latest_context_uses_earlier_complete_history_with_distinct_times(monkeypatch,tmp_path):
    history=_snapshot(tmp_path/'data/raw','2026-10-10T10:00:00Z',history=True)
    context=_snapshot(tmp_path/'data/raw','2026-10-17T10:00:00Z',history=False,player_price=62)
    app=local_app(monkeypatch,tmp_path)
    assert not app.exception and not app.error
    assert any(f'Kontekst: {context.name}\nHistorik: {history.name}' in c.value for c in app.code)
    assert any('17. okt' in c.value and '10. okt' in c.value for c in app.caption)
    assert any('Klar til GW2' in s.value for s in app.success)


def test_latest_context_can_use_compatible_anchor_before_incompatible_capture(monkeypatch,tmp_path):
    compatible=_snapshot(tmp_path/'data/raw','2026-10-10T10:00:00Z',history=True)
    _snapshot(tmp_path/'data/raw','2026-10-12T10:00:00Z',history=True,team_name='Wrong season identity')
    context=_snapshot(tmp_path/'data/raw','2026-10-17T10:00:00Z',history=False)
    app=local_app(monkeypatch,tmp_path)
    assert not app.exception and not app.error
    assert any(f'Kontekst: {context.name}\nHistorik: {compatible.name}' in c.value for c in app.code)
    assert any('12. okt' in w.value for w in app.warning)


@pytest.mark.parametrize('options,reason',[
    ({'missing_player_ids':(1,)},'spillerhistorik mangler'),
    ({'history_minutes':-1},'karantæne'),
])
def test_newest_partial_or_quarantined_capture_keeps_limited_acknowledgement(monkeypatch,tmp_path,options,reason):
    _snapshot(tmp_path/'data/raw','2026-10-10T10:00:00Z',history=True)
    latest=_snapshot(tmp_path/'data/raw','2026-10-17T10:00:00Z',history=True,**options)
    app=local_app(monkeypatch,tmp_path)
    assert not app.exception and not app.error
    assert any(f'Kontekst: {latest.name}' in c.value for c in app.code)
    assert any(reason in w.value for w in app.warning)
    assert not any('Klar til GW' in s.value for s in app.success)
    assert any(c.label=='Beregn med ufuldstændige data (foreløbig)' and not c.value for c in app.checkbox)


def test_corrupt_local_candidate_blocks_with_visible_message(monkeypatch,tmp_path):
    _snapshot(tmp_path/'data/raw','2026-10-10T10:00:00Z',history=True)
    corrupt=_snapshot(tmp_path/'data/raw','2026-10-17T10:00:00Z',history=False)
    (corrupt/'COMPLETE').write_text('broken checksum\n')
    app=local_app(monkeypatch,tmp_path)
    assert not app.exception
    assert any('Lokale data kunne ikke verificeres' in e.value for e in app.error)
    assert not any('Klar til GW' in s.value for s in app.success)


@pytest.mark.parametrize('options,reason',[
    ({'missing_player_ids':(1,)},'spillerhistorik mangler'),
    ({'history_minutes':-1},'karantæne'),
])
def test_context_after_failed_full_pool_preserves_latest_history_limits(monkeypatch,tmp_path,options,reason):
    _snapshot(tmp_path/'data/raw','2026-10-10T10:00:00Z',history=True)
    attempted=_snapshot(tmp_path/'data/raw','2026-10-16T10:00:00Z',history=True,**options)
    context=_snapshot(tmp_path/'data/raw','2026-10-17T10:00:00Z',history=False)
    app=local_app(monkeypatch,tmp_path)
    assert not app.exception and not app.error
    assert any(f'Kontekst: {context.name}\nHistorik: {attempted.name}' in c.value for c in app.code)
    assert any(reason in w.value for w in app.warning)
    assert not any('Klar til GW' in s.value for s in app.success)
    assert any(c.label=='Beregn med ufuldstændige data (foreløbig)' and not c.value for c in app.checkbox)
