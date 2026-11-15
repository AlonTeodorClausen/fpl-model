"""Bound expensive guest actions without changing the local owner's workflow."""

import pytest


def gate_at(clock):
    from fpl_model.ui.guest_limits import GuestJobGate

    return GuestJobGate(clock=lambda: clock[0], import_session_cooldown=30,
                        import_min_spacing=2, import_concurrency=2,
                        comparison_session_cooldown=60, comparison_concurrency=1)


def test_import_has_session_cooldown_and_process_spacing():
    from fpl_model.ui.guest_limits import GuestLimitError

    now = [100.0]
    gate = gate_at(now)
    gate.acquire('import', 'visitor-a').release()
    with pytest.raises(GuestLimitError, match='vent'):
        gate.acquire('import', 'visitor-a')
    with pytest.raises(GuestLimitError, match='vent'):
        gate.acquire('import', 'visitor-b')
    now[0] += 2
    gate.acquire('import', 'visitor-b').release()
    now[0] += 28
    gate.acquire('import', 'visitor-a').release()


def test_comparison_allows_only_one_active_job_and_releases_on_exception():
    from fpl_model.ui.guest_limits import GuestLimitError

    now = [100.0]
    gate = gate_at(now)
    with pytest.raises(RuntimeError, match='failed'):
        with gate.acquire('comparison', 'visitor-a'):
            with pytest.raises(GuestLimitError, match='anden'):
                gate.acquire('comparison', 'visitor-b')
            raise RuntimeError('failed')
    gate.acquire('comparison', 'visitor-b').release()
    with pytest.raises(GuestLimitError, match='vent'):
        gate.acquire('comparison', 'visitor-b')


def test_denial_does_not_consume_cooldown_and_unknown_actions_fail():
    from fpl_model.ui.guest_limits import GuestLimitError

    now = [100.0]
    gate = gate_at(now)
    first = gate.acquire('import', 'visitor-a')
    with pytest.raises(GuestLimitError):
        gate.acquire('import', 'visitor-b')
    first.release()
    now[0] += 2
    gate.acquire('import', 'visitor-b').release()
    with pytest.raises(ValueError, match='Unknown'):
        gate.acquire('download', 'visitor-a')


def test_guest_ui_blocks_repeated_import_before_a_second_network_capture(monkeypatch, tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from test_my_team_app import setup

    setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')
    import fpl_model.ui.team_import as importer
    import fpl_model.ui.guest_limits as limits

    now = [100.0]
    monkeypatch.setattr(limits, 'GUEST_GATE', gate_at(now))
    calls = []

    def capture(value, _root):
        calls.append(value)
        raise ValueError('FPL unavailable')

    monkeypatch.setattr(importer, 'capture_team', capture)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
    next(w for w in app.text_input if w.label == 'Hold-ID eller FPL-link').set_value('3533723')
    next(b for b in app.button if b.label == 'Hent hold fra FPL').click().run(timeout=30)
    next(b for b in app.button if b.label == 'Hent hold fra FPL').click().run(timeout=30)
    assert calls == ['3533723']
    assert any('vent' in w.value for w in app.warning)


def test_guest_ui_blocks_repeated_comparison_before_a_second_forecast(monkeypatch, tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from test_my_team_app import setup
    from test_my_team import profile

    ui = setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')
    import fpl_model.ui.guest_limits as limits

    now = [100.0]
    monkeypatch.setattr(limits, 'GUEST_GATE', gate_at(now))
    original = ui.forecast_bundle
    calls = []

    def forecast(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(ui, 'forecast_bundle', forecast)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
    app.session_state['team_draft'] = profile()
    app.run(timeout=30)
    next(b for b in app.button if b.label == 'Sammenlign transferforslag').click().run(timeout=60)
    next(b for b in app.button if b.label == 'Sammenlign transferforslag').click().run(timeout=30)
    assert not app.exception and calls == [1]
    assert any('vent' in w.value for w in app.warning)


def test_guest_ui_excludes_the_largest_simulation_setting(monkeypatch, tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from test_my_team_app import setup

    setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
    choices = next(w for w in app.selectbox if w.label == 'Scenarier').options
    assert choices == ['3000', '1000', '500']


def test_guest_profile_upload_has_a_small_payload_limit():
    from fpl_model.ui.guest_state import parse_guest_profile_bytes

    assert parse_guest_profile_bytes(b'{"bank": 5}') == {'bank': 5}
    with pytest.raises(ValueError, match='for stor'):
        parse_guest_profile_bytes(b' ' * (64 * 1024 + 1))
    with pytest.raises(ValueError, match='JSON'):
        parse_guest_profile_bytes(b'{broken')
