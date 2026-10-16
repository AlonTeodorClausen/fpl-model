"""The model explanation is a read-only, understandable app destination."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from test_my_team_app import setup


APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def test_model_tab_explains_the_actual_standard_without_refetching(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    import fpl_model.prototype_data as source

    loaded = []
    original = source.load_data

    def tracked(path, **kwargs):
        loaded.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(source, 'load_data', tracked)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    before = len(loaded)
    next(w for w in app.radio if w.label == 'Side').set_value('Model').run(timeout=30)

    assert not app.exception
    assert len(loaded) == before
    assert any('Sådan virker modellen' in h.value for h in app.title)
    text = ' '.join(x.value for x in app.markdown)
    assert 'component_baseline_v1' in text
    assert 'Officiel FPL API' in text
    assert 'element-summary' in text
    assert 'odds' in text.lower()
    assert any('Spilletid' in e.label for e in app.expander)
    assert any('Begrænsninger' in e.label for e in app.expander)
    assert not any(b.label == 'Sammenlign transferforslag' for b in app.button)


def test_model_tab_identifies_the_version_of_an_open_report(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    app = AppTest.from_file(APP).run(timeout=30)
    app.session_state['transfer_result'] = {
        'forecast': {'model_version': 'component_attacking_odds_v1',
                     'odds_scope': 'attack_and_defence'},
    }
    next(w for w in app.radio if w.label == 'Side').set_value('Model').run(timeout=30)

    assert not app.exception
    text = ' '.join(x.value for x in app.markdown)
    assert 'component_attacking_odds_v1' in text
    assert 'angreb og forsvar' in text.lower()
    assert 'Standard på Mit hold' in text


def test_guest_can_read_model_explanation_without_shared_data(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')
    app = AppTest.from_file(APP).run(timeout=30)
    navigation = next(w for w in app.radio if w.label == 'Side')
    assert navigation.options == ['Mit hold', 'Model']
    navigation.set_value('Model').run(timeout=30)
    assert not app.exception
    assert any('Sådan virker modellen' in h.value for h in app.title)
