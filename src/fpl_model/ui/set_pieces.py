"""Explicit role assumptions and read-only comparison; never downloads data."""
from pathlib import Path
import json
import pandas as pd
import streamlit as st
from fpl_model.set_piece_roles import SetPieceConfig


def set_piece_controls(paths):
    st.warning('Følsomhedsvariant: vi mangler non-penalty xG og dødboldsopdelt xA. '
        'Der omfordeles en antaget del af eksisterende mål/assists; ingen ekstra mål lægges til. Ikke en kalibreret dødboldsmodel.')
    source=st.selectbox('Officielt snapshot til dødboldsroller',paths,format_func=lambda p:p.name)
    with st.expander('Dødboldsantagelser – kan ændres',expanded=True):
        penalty=st.number_input('Straffesparksrolle: del af målbudget (%)',min_value=0.,max_value=50.,value=10.,step=1.)/100
        direct=st.number_input('Direkte frisparksrolle: del af målbudget (%)',min_value=0.,max_value=50.,value=2.,step=1.)/100
        indirect=st.number_input('Hjørne/indirekte frispark: del af assistbudget (%)',min_value=0.,max_value=100.,value=15.,step=1.)/100
        confidence=st.number_input('Vægt på rolleordenen (%)',min_value=0.,max_value=100.,value=50.,step=5.)/100
        st.caption('Standarderne 10/2/15% og 50% vægt er valgte scenarieantagelser, ikke målte frekvenser. '
            '0% vægt genskaber den eksisterende angrebsoddsmodel. Roller gælder kun, når spilleren forventes på banen; '
            'ukendt eller modstridende orden bevarer den hidtidige fordeling. Ingen automatisk kombination med den nye minutmodel.')
    return SetPieceConfig(penalty,direct,indirect,confidence),source


def show_set_piece_comparison(root):
    with st.expander('Dødboldsroller · gemt følsomhedssammenligning'):
        paths=sorted((Path(root)/'artifacts/set_piece_forecasts').glob('*/comparison.json'),reverse=True)
        if not paths:st.info('Ingen gemt sammenligning. Kør scripts/compare_set_pieces.py på eksisterende snapshots.');return
        chosen=st.selectbox('Gemt dødboldssammenligning',paths,format_func=lambda p:p.parent.name)
        from fpl_model.prediction_evaluation import load_forecasts
        try:
            saved,_=load_forecasts(chosen.parent)
            report=json.loads(chosen.read_text())
        except (OSError,ValueError) as exc:st.error(str(exc));return
        st.warning('Scenarie med reelle rolleordener og odds, men antaget omfordeling. '
            'Prognoseforskel, ikke dokumentation for forbedret præcision. Ingen non-penalty xG-opdeling.')
        st.write(f"GW{saved['event']} · {saved['forecast_origin_at']} · deadline {saved['deadline_at']}")
        st.caption(f"{report['draws']} scenarier · seed {report['seed']} · odds {report['usable_fixtures']}/{report['expected_fixtures']} kampe")
        sources=saved['input_sources']
        st.write('Roller observeret:',sources['set_piece_roles']['available_at'])
        st.write('Spillerhistorik/priser:',sources['history']['available_at'])
        st.write('Odds observeret:',saved['coverage']['source']['available_at'])
        st.caption('Oprindelige tidspunkter bevares. Rolleopdateringens publikationstid er ukendt; gamle data bliver ikke nye ved genkørsel.')
        st.json(saved['set_piece_config'])
        st.write('**Spillerændringer mod samme angrebsoddsmodel uden rolleomfordeling**')
        st.dataframe(pd.DataFrame(report['player_changes']),hide_index=True)
        st.write('**Afstemning og rolledækning pr. hold/kamp**')
        st.dataframe(pd.DataFrame(report['team_budgets']),hide_index=True)
        names={r['player_id']:r['name'] for r in report['player_changes']}
        pid=st.selectbox('Spiller – dødboldsforklaring',sorted(names,key=names.get),format_func=names.get)
        st.json(saved['variants'][report['model_version']]['explanations'][str(pid)]['fixtures'])
        st.download_button('Download dødboldssammenligning',chosen.read_bytes(),'set_piece_comparison.json','application/json')
