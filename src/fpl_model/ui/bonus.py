"""Saved conditional-bonus diagnostics; read-only, no downloads or refits."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st


def bonus_notice(config,training=None):
    if config:
        st.warning('Præstationsafhængig bonus er valgt som eksperiment. Kun bonus ændres; ingen fælles BPS-rangering. '
            'Sparsom/manglende træningshistorik bevarer baseline-bonus.')
        st.caption(f"Fast regularisering {config['ridge']} · mindst {config['min_rows']} gyldige, spillede træningsrækker og fem bonusmodtagere. Ingen parametersøgning.")
        if training:st.dataframe(pd.DataFrame([dict(GW=e,**m) for e,m in training.items()]),hide_index=True)


def show_bonus_comparison(root):
    root=Path(root)/'artifacts/conditional_bonus'
    with st.expander('Bonus · præstationsafhængigt eksperiment'):
        st.caption('Samme spilletid, mål, assists og defensive hændelser. Den nye bonus afhænger af præstationen i hvert simuleret scenarie. Baseline er fortsat standard.')
        paths=sorted((root/'development').glob('*/report.json'),reverse=True)
        if paths:
            chosen=st.selectbox('Gemt bonusevaluering',paths,format_func=lambda p:p.parent.name)
            try:r=json.loads(chosen.read_text())
            except (ValueError,OSError) as exc:st.error(str(exc));return
            st.warning('Retrospektive udviklingsdata, ikke en uafhængig eller strikt prospektiv test. '
                'Trænes igen før hver GW på tidligere endelige kampe; ingen aktuelle odds i historiske prognoser.')
            st.write(f"GW {', '.join(map(str,r['gameweeks']))} · {r['draws']} scenarier · seed {r['seed']} + GW")
            st.caption(f"Data observeret {r['data_available_at']} · snapshot {r['snapshot_id']}")
            st.caption(f"{r['summary'][0]['n']} observationer · {r['summary'][0]['players']} spillere · identiske evalueringsrækker")
            columns=['model','bonus_MAE','bonus_RMSE','point_MAE','point_RMSE','CRPS']
            st.dataframe(pd.DataFrame(r['summary'])[columns].round(4),hide_index=True)
            st.caption('baseline = oprindelig model · conditional_bonus = kun bonus ændret · prior_average = tidligere point-/bonusgennemsnit på samme rækker. Lavere MAE/RMSE/CRPS er bedre. Bias > 0 er overvurdering.')
            st.write('Historikgruppe:',r['regular_rule'])
            st.dataframe(pd.DataFrame(r['by_prior_history'])[['model','group','n','bonus_MAE','point_MAE','point_RMSE','CRPS']].round(4),hide_index=True)
            with st.expander('Bonusdiagnostik pr. position/GW og træningsgrundlag'):
                st.dataframe(pd.DataFrame(r['summary']),hide_index=True)
                st.dataframe(pd.DataFrame(r['by_position']),hide_index=True)
                st.dataframe(pd.DataFrame(r['by_gameweek']),hide_index=True)
                fits=r['evaluations']['conditional_bonus'].get('bonus_fits',{})
                st.dataframe(pd.DataFrame([dict(event=e,**{k:f[k] for k in ('status','training_rows','sub60_rows','training_gameweeks','reason')}) for e,f in fits.items()]),hide_index=True)
                st.json(r['bonus_config'])
        else:st.info('Ingen gemt evaluering. Kør scripts/compare_bonus.py på eksisterende snapshots.')
        forecasts=sorted((root/'forecasts').glob('*/comparison.json'),reverse=True)
        if forecasts:
            from fpl_model.prediction_evaluation import load_forecasts
            chosen=st.selectbox('Gemt bonusprognose',forecasts,format_func=lambda p:p.parent.name)
            try:
                saved,_=load_forecasts(chosen.parent)
                comparison=json.loads(chosen.read_text())
            except (ValueError,OSError) as exc:st.error(str(exc));return
            st.write(f"GW{saved['event']} · prognosetidspunkt {saved['forecast_origin_at']} · deadline {saved['deadline_at']}")
            st.warning('Dette er en prognoseforskel, ikke dokumentation for forbedret præcision. Gamle odds bliver ikke nye ved genkørsel.')
            source=saved['coverage']['source']
            st.caption(f"William Hill · odds {comparison['usable_fixtures']}/{comparison['expected_fixtures']} kampe · observeret {source['available_at']} · {comparison['draws']} scenarier · seed {comparison['seed']}")
            sources=saved['input_sources'];history=sources.get('history',{})
            context=sources.get('official_context',{})
            st.caption(f"Spillerhistorik/priser: {history.get('available_at','ukendt')} · kampkontekst: "
                f"{max((f['retrieved_at'] for f in context.get('files',[])),default='ukendt')}")
            with st.expander('Præcise inputreferencer'):
                st.json(sources)
            st.dataframe(pd.DataFrame(comparison['player_changes'])[['name','reference_xp','conditional_bonus_xp','xp_delta','reference_bonus','conditional_bonus','expected_minutes']].round(3),hide_index=True)
            pool={r['player_id']:r['name'] for r in comparison['player_changes']}
            pid=st.selectbox('Spiller · bonusforklaring',sorted(pool,key=pool.get),format_func=pool.get)
            rows=[]
            for name,v in saved['variants'].items():
                e=v['explanations'][str(pid)]
                rows.extend(dict(model=name,komponent=k,point=n) for k,n in e['point_components'].items())
                if v.get('bonus_model'):
                    m=v['bonus_model']
                    st.write(f"Bonusmodel: {m['status']} · {m['training_rows']} spillede træningsrækker, heraf {m['sub60_rows']} under 60 minutter.")
                    if m['reason']:st.warning(f"Bonus-fallback: {m['reason']}")
                    with st.expander('Lærte bonuskoefficienter'):
                        st.json(dict(zip(m['feature_names'],m['coefficients'] or [])))
            st.dataframe(pd.DataFrame(rows),hide_index=True)
        st.caption('Begrænsning: spillerbonus simuleres separat; antal bonuspoint pr. kamp er ikke låst. '
            'Minutter er stadig uafhængige mellem spillere. Træningsgrundlaget er den aktuelle spillerpulje og få runder; '
            'tidligere sæsoner og en ny assistmodel indgår ikke i dette eksperiment.')
