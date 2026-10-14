"""Read-only previous-season attack-prior comparison and individual provenance."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st


def show_season_prior_comparison(root):
    root=Path(root)/'artifacts/season_priors'
    with st.expander('Spillerprior fra sidste sæson · xG/xA'):
        st.caption('Et separat eksperiment: sidste sæsons xG/xA udglattes mod positionen og bruges som svagt prior for årets rater. Spilletid, bonus og forsvar bevares. Baseline er standard.')
        paths=sorted((root/'development').glob('*/report.json'),reverse=True)
        if paths:
            chosen=st.selectbox('Gemt sæsonprior-evaluering',paths,format_func=lambda p:p.parent.name)
            try:r=json.loads(chosen.read_text())
            except (OSError,ValueError) as exc:st.error(str(exc));return
            st.warning('Retrospektive udviklingsdata. Senere hentede historiske rækker er ikke dokumentation for tilgængelighed ved gamle deadlines. Ingen aktuelle odds i historisk evaluering.')
            st.write(f"GW {', '.join(map(str,r['gameweeks']))} · {r['summary'][0]['n']} observationer · {r['summary'][0]['players']} spillere · {r['draws']} scenarier · seed {r['seed']} + GW")
            st.caption(f"Observeret {r['data_available_at']} · snapshot {r['snapshot_id']}")
            st.dataframe(pd.DataFrame(r['summary']).round(4),hide_index=True)
            st.caption('baseline = uændret model · previous_season = kun xG/xA-prior ændret · prior_average = tidligere pointgennemsnit. Lavere fejl er bedre.')
            st.write('Dækning blandt evalueringsrækker:',r['prior_coverage'])
            st.caption('Regelmæssige spillere: '+r['regular_rule'])
            st.dataframe(pd.DataFrame(r['by_prior_history']).round(4),hide_index=True)
            with st.expander('Fordelt på position, GW og prior-dækning'):
                for key in ('by_position','by_gameweek','by_prior_coverage'):
                    st.dataframe(pd.DataFrame(r[key]).round(4),hide_index=True)
        else:st.info('Ingen gemt sammenligning. Kør scripts/compare_season_priors.py på eksisterende snapshots.')
        paths=sorted((root/'forecasts').glob('*/comparison.json'),reverse=True)
        if paths:
            from fpl_model.prediction_evaluation import load_forecasts
            chosen=st.selectbox('Gemt sæsonprior-prognose',paths,format_func=lambda p:p.parent.name)
            try:
                saved,_=load_forecasts(chosen.parent);c=json.loads(chosen.read_text())
            except (OSError,ValueError) as exc:st.error(str(exc));return
            st.write(f"GW{saved['event']} · prognose {saved['forecast_origin_at']} · deadline {saved['deadline_at']}")
            st.warning('Prognoseforskel, ikke dokumenteret forbedring. Ældre spillerdata/odds er genbrugt ved deres oprindelige hentetid.')
            st.caption(f"William Hill · {c['usable_fixtures']}/{c['expected_fixtures']} kampe · odds observeret {saved['coverage']['source']['available_at']}")
            st.write('Sæsonprior-dækning (spillere):',c['prior_coverage'])
            st.write('Fallbackårsager:',c['fallback_reasons'])
            st.caption('used = xG og xA anvendt · partial = kun ét felt · position_fallback = intet spillerprior. Holdkammerater uden eget prior kan påvirkes, når oddsfordelingen ændres.')
            columns=['name','reference_xp','previous_season_xp','xp_delta','goal_delta','assist_delta','expected_minutes']
            st.dataframe(pd.DataFrame(c['player_changes'])[columns].round(3),hide_index=True)
            by_id={r['player_id']:r for r in c['player_changes']}
            pid=st.selectbox('Spiller · sidste sæsons prior',sorted(by_id,key=lambda pid:by_id[pid]['name']),format_func=lambda pid:by_id[pid]['name'])
            r=by_id[pid];prior=r['prior']
            st.write(f"Status: {prior['status']} · sæson: {prior.get('season_name','ukendt')} · tidligere minutter: {prior.get('minutes','ukendt')}")
            if prior.get('reason'):st.caption('Fallback: '+prior['reason'])
            st.dataframe(pd.DataFrame([dict(rate=k,**v) for k,v in r['rates'].items()]),hide_index=True)
            with st.expander('Tidligere rater, udglatning og præcise kildereferencer'):
                st.json(prior);st.json(saved['input_sources']);st.json(saved['season_prior_config'])
        st.caption('Ingen prior for starter/DNP fra sæsonsummer. Tidligere klub, rolle og position kan være anderledes. Ingen ny assistdefinition eller kombination med bonuseksperimentet.')
