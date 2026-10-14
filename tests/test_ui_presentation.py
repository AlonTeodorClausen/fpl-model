from fpl_model.ui.presentation import pitch_html


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
