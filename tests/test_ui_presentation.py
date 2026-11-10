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


def test_list_view_keeps_xi_bench_and_captain_distinct_without_tiny_pitch_cards():
    from fpl_model.ui.presentation import team_html

    rows = [dict(id=i, name=name, position=pos, detail='MCI', xp=4.5, minutes=72)
            for i, name, pos in [(1, '<script>Keeper</script>', 1), (2, 'Saka', 3),
                                 (3, 'Reserve', 3)]]
    lineup = dict(starters=[1, 2], bench=[3], captain=2, vice_captain=1)
    html = team_html(rows, lineup=lineup, view='Liste')
    assert 'Startellever' in html and 'Bænk · rækkefølge' in html
    assert html.index('Saka') < html.index('Reserve')
    assert 'Anfører' in html and 'Viceanfører' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '4.50 xP' in html
    assert 'lab-pitch' not in html
    assert 'lab-pitch' in team_html(rows, lineup=lineup, view='Bane')


def test_official_media_uses_bootstrap_codes_and_never_accepts_arbitrary_urls():
    from fpl_model.ui.presentation import official_media, team_html

    media = official_media(
        [dict(id=411, code=223094, team=15, web_name='Haaland')],
        [dict(id=15, code=11, short_name='MCI')],
    )
    assert media[411] == dict(photo_code=223094, club_code=11, club_short='MCI')
    html = team_html([dict(id=411, name='Haaland', position=4, detail='MCI', **media[411])])
    assert 'https://resources.premierleague.com/premierleague25/photos/players/110x140/223094.png' in html
    assert 'https://resources.premierleague.com/premierleague/badges/70/t11.png' in html
    assert 'Haaland' in html and 'MCI' in html
    pitch = team_html([dict(id=411, name='Haaland', position=4, detail='MCI', **media[411])], view='Bane')
    assert '/223094.png' in pitch and 't11.png' in pitch

    unsafe = team_html([dict(id=1, name='A', position=2, detail='B',
                             photo_code='1);alert(1)', club_code='https://evil.test', club_short='<x>')])
    assert 'evil.test' not in unsafe and 'alert(1)' not in unsafe
    assert '&lt;x&gt;' in unsafe
    assert 'lab-list-avatar' in unsafe  # Initial fallback is always present.


def test_report_lineup_can_use_current_official_media_without_changing_forecasts(monkeypatch):
    from fpl_model.ui.presentation import show_lineup
    rendered = []
    monkeypatch.setattr('fpl_model.ui.presentation.st.html', rendered.append)
    monkeypatch.setattr('fpl_model.ui.presentation.st.caption', lambda *_: None)
    lookup = {411: dict(name='Haaland', position=4, price=140, fixture_ids=[1],
                        xp=5.25, expected_minutes=80)}
    lineup = dict(starters=[411], bench=[], captain=411, vice_captain=411)
    show_lineup(lookup, lineup, media_by_id={411: dict(photo_code=223094,
                                                      club_code=11, club_short='MCI')})
    assert '/223094.png' in rendered[0] and 't11.png' in rendered[0]
    assert '5.25 xP' in rendered[0]


def test_owned_player_cards_link_to_details_in_both_views_only_when_enabled():
    from fpl_model.ui.presentation import team_html

    players = [dict(id=411, name='Haaland', position=4, detail='MCI')]
    for view in ('Liste', 'Bane'):
        plain = team_html(players, view=view)
        linked = team_html(players, view=view, clickable=True)
        assert '?player_id=411' not in plain
        assert '<a ' in linked and 'href="?player_id=411"' in linked
        assert 'Se prognose for Haaland' in linked
    bad = team_html([dict(id='1" onclick="alert(1)', name='A', position=2)], clickable=True)
    assert 'onclick' not in bad and 'href=' not in bad


def test_decision_card_shows_actual_comparison_and_escapes_player_names():
    from fpl_model.ui.presentation import decision_card_html

    decision = dict(count=1, out=[7], **{'in': [8]}, next_gw_gain=2.34,
                    horizon_gain=5.67, bank_after=12, hits=0)
    html = decision_card_html(decision, event=8,
                              names=lambda ids: {7: '<Bruno>', 8: 'Saka'}[ids[0]])
    assert 'GW8' in html and '+2.34' in html and '+5.67' in html
    assert '&lt;Bruno&gt;' in html and '<Bruno>' not in html
    assert '£1.2m' in html and '0 pointfradrag' in html


def test_saved_decision_is_visibly_marked_when_current_inputs_differ():
    from fpl_model.ui.presentation import decision_card_html

    decision = dict(count=0, out=[], **{'in': []}, next_gw_gain=0,
                    horizon_gain=0, bank_after=0, hits=0)
    html = decision_card_html(decision, event=8, names=lambda _: '', stale=True)
    assert 'GEMT FORSLAG' in html
    assert 'Genberegn' in html


def test_decision_with_stale_source_data_is_not_shown_as_fresh_advice():
    from fpl_model.ui.presentation import decision_card_html

    decision = dict(count=0,out=[],**{'in': []},next_gw_gain=0,
                    horizon_gain=0,bank_after=5,hits=0)
    html = decision_card_html(decision,event=8,names=lambda _: '',data_attention=True)
    assert 'DATA SKAL KONTROLLERES' in html
    assert 'Opdatér data' in html
    assert 'lab-decision-stale' in html


def test_decision_card_attributes_chip_gain_to_chip_not_a_transfer():
    from fpl_model.ui.presentation import decision_card_html

    decision = dict(count=0, out=[], **{'in': []}, next_gw_gain=8.74,
                    horizon_gain=14.86, bank_after=0, hits=0)
    html = decision_card_html(decision, event=7, names=lambda _: '', chip='Triple Captain')
    assert 'Behold truppen · Triple Captain' in html
    assert '+8.74 point' in html
    assert '+8.74 xP' not in html


def test_readiness_reasons_are_explained_without_internal_codes():
    from fpl_model.ui.presentation import readiness_message

    message = readiness_message(['context_stale', 'history_refresh_required'])
    assert 'Opdatér spillerpriser og kampplan' in message
    assert 'Hent opdateret kampvis spillerhistorik' in message
    assert 'context_stale' not in message


def test_decision_overview_shows_same_plan_alternatives_and_week_points():
    from fpl_model.ui.presentation import decision_overview_html

    decision = dict(count=0, out=[], **{'in': []}, next_gw_gain=0,
                    horizon_gain=1.25, bank_after=5, hits=0)
    html = decision_overview_html(
        decision, event=8, names=lambda _: '',
        alternatives=[dict(label='<Én transfer>', next_gw_gain=-.3,
                           total_gain=.4, hits=0)],
        weeks=[dict(event=8, mean=56.8, gain=0),
               dict(event=9, mean=54.2, gain=1.25)])
    assert 'ANDRE VALG' in html and '&lt;Én transfer&gt;' in html
    assert '<Én transfer>' not in html
    assert 'GW8' in html and '56.8 point' in html
    assert 'GW9' in html and '54.2 point' in html
    assert '0.4' in html and '1.25' in html


def test_next_step_card_distinguishes_missing_team_from_missing_finances():
    from fpl_model.ui.presentation import next_step_card_html

    missing_players=next_step_card_html(player_count=0, profile_error='mangler')
    missing_finances=next_step_card_html(player_count=15, profile_error='bank mangler')
    ready=next_step_card_html(player_count=15, profile_error=None)
    assert 'Hent dit hold' in missing_players
    assert 'Færdiggør dit hold' in missing_finances
    assert 'bank, gratis transfers' in missing_finances
    assert 'Klar til forslag' in ready
    assert 'Klar til forslag' not in missing_finances


def test_next_step_card_never_claims_ready_when_data_or_budget_needs_review():
    from fpl_model.ui.presentation import next_step_card_html

    stale=next_step_card_html(player_count=15,profile_error=None,
                              readiness_status='attention',can_refresh=True)
    blocked=next_step_card_html(player_count=15,profile_error=None,
                                readiness_status='blocked')
    estimated=next_step_card_html(player_count=15,profile_error=None,
                                  price_estimates=True)
    assert 'Opdatér data' in stale and 'Hent seneste data' in stale
    assert 'lab-decision-attention' in stale
    assert 'Nye forslag er blokeret' in blocked
    assert 'salgsværdier' in estimated.lower()
    assert all('Klar til forslag' not in card for card in (stale,blocked,estimated))


def test_next_step_card_marks_incomplete_data_as_provisional():
    from fpl_model.ui.presentation import next_step_card_html

    provisional=next_step_card_html(player_count=15,profile_error=None,
                                    readiness_status='limited')
    assert 'foreløbig' in provisional.lower()
    assert 'Klar til forslag' not in provisional
