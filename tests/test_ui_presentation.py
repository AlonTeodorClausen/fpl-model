from fpl_model.ui.presentation import pitch_html


def test_public_dates_are_human_readable_without_raw_ids(tmp_path):
    import json
    from fpl_model.ui.presentation import friendly_time, snapshot_option

    snapshot = tmp_path / '2026-10-14_203823637878Z_335c6e1eee6044f5b2e2498f153c875f'
    snapshot.mkdir()
    (snapshot / 'manifest.json').write_text(json.dumps({
        'completed_at': '2026-10-14T20:44:00Z',
    }))
    assert friendly_time('2026-10-17T10:00:00Z') == '17. oktober kl. 12.00'
    label = snapshot_option(snapshot)
    assert label == '14. oktober kl. 22.44'
    assert '335c6e' not in label and 'snapshot' not in label.lower()


def test_saved_comparison_label_hides_artifact_folder_id(tmp_path):
    from fpl_model.ui.presentation import saved_comparison_option

    report = tmp_path / '20261014T204633767361Z_4feceef1' / 'report.json'
    report.parent.mkdir()
    assert saved_comparison_option(report) == 'Beregnet 14. oktober kl. 22.46'


def test_squad_is_not_presented_as_a_selected_lineup_and_escapes_names():
    html=pitch_html([dict(id=1,name='<script>alert(1)</script>',position=1,detail='A&B')])
    assert 'ikke en startellever' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'A&amp;B' in html
    assert 'xP' not in html and 'BÆNK' not in html


def test_lineup_preserves_captain_bench_order_and_exact_forecast_values():
    rows=[dict(id=i,name=f'Player{i}',position=1 if i<3 else 2,detail='£4.5m',xp=4.123,minutes=60) for i in range(1,5)]
    html=pitch_html(rows,lineup=dict(starters=[1,3],bench=[2,4],captain=3,vice_captain=1))
    assert '4.12 xP · 60 min' in html
    assert html.count('lab-badge')==2
    bench=html.split('BÆNK · PRIORITERET RÆKKEFØLGE')[1]
    assert bench.index('Player2')<bench.index('Player4')
    assert 'Reservekeeper' in bench and 'Bænk 1' in bench


def test_week_plan_is_readable_and_escapes_player_names():
    from fpl_model.ui.presentation import week_plan_html

    steps = [
        dict(event=7, out=[], **{'in': []}, bank_after=5, used=0, remaining=1, hits=0, chip=None),
        dict(event=8, out=[1], **{'in': [2]}, bank_after=3, used=1, remaining=0, hits=0, chip=None),
    ]
    names = lambda ids: ', '.join({1: '<script>', 2: 'Mbeumo'}[i] for i in ids)
    html = week_plan_html(steps, names, {})
    assert 'GW7' in html and 'Behold holdet' in html
    assert 'GW8' in html and '&lt;script&gt;' in html and 'Mbeumo' in html
    assert '<script>' not in html
    assert '£0.3m' in html and '1 gratis transfer brugt' in html
