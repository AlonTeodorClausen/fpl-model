import numpy as np
import pytest


def sample_bundle():
    return dict(
        players=[dict(id=7), dict(id=2)],
        rows={8: [dict(player_id=2, name='A', xp=5.0),
                  dict(player_id=7, name='B', xp=3.0)]},
        planning_scenarios={8: dict(points=np.array([[0, 3], [5, 3], [10, 3]]))},
    )


def test_selected_player_must_be_an_owned_canonical_id():
    from fpl_model.ui.player_detail import selected_owned_id

    assert selected_owned_id('7', [2, 7]) == 7
    assert selected_owned_id('2', [2, 7]) == 2
    assert selected_owned_id('8', [2, 7]) is None
    assert selected_owned_id('7<script>', [2, 7]) is None
    assert selected_owned_id('⁷', [2, 7]) is None


def test_comparison_uses_one_gw_and_one_forecast_bundle_without_reordering():
    from fpl_model.ui.player_detail import comparison_rows, point_distribution

    bundle = sample_bundle()
    rows = comparison_rows(bundle, 8, 7, [2, 2])
    assert [r['player_id'] for r in rows] == [7, 2]
    assert [r['xp'] for r in rows] == [3.0, 5.0]
    assert point_distribution(bundle, 8, 2) == [(0, pytest.approx(1/3)),
                                                 (5, pytest.approx(1/3)),
                                                 (10, pytest.approx(1/3))]
    assert bundle['rows'][8][0]['xp'] == 5.0
    with pytest.raises(ValueError, match='spiller'):
        comparison_rows(bundle, 8, 7, [999])
    with pytest.raises(ValueError, match='GW'):
        comparison_rows(bundle, 9, 7, [])


def test_saved_report_detail_uses_matching_cache_or_report_rows_without_simulation(tmp_path):
    from fpl_model.ui.player_detail import bundle_for_report
    report=dict(forecast=dict(cache_key='a'*64,model_version='saved-model',snapshot_id='old-official',
                              forecast_origin_at='2026-10-01T10:00:00+00:00'),
                players_by_event={'8':[dict(player_id=7,name='Saved',xp=4.5)]})
    unrelated=dict(metadata=dict(cache_key='b'*64),rows={8:[dict(player_id=7,xp=99.)]})
    detail=bundle_for_report(report,unrelated,tmp_path)
    assert detail['rows'][8][0]['xp']==4.5
    assert detail['metadata']['model_version']=='saved-model'
    assert detail['planning_scenarios']=={}
    matching=dict(metadata=dict(cache_key='a'*64),rows={8:[dict(player_id=7,xp=4.5)]},
                  planning_scenarios={8:dict(points=np.array([[4]]))})
    matching['metadata'].update(model_version='saved-model',
                                snapshot_id='old-official',
                                forecast_origin_at='2026-10-01T10:00:00+00:00')
    assert bundle_for_report(report,matching,tmp_path) is matching
    mismatched=dict(matching,metadata=dict(matching['metadata'],model_version='different'))
    with pytest.raises(ValueError,match='identity'):
        bundle_for_report(report,mismatched,tmp_path)
    wrong_data=dict(matching,metadata=dict(matching['metadata'],snapshot_id='new-official'))
    with pytest.raises(ValueError,match='identity'):
        bundle_for_report(report,wrong_data,tmp_path)
