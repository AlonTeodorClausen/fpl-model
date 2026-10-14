"""Saved assist-correction results; no downloads, refits or simulations in UI."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st


def show_assist_comparison(root):
    root=Path(root)/'artifacts/assist_correction'
    with st.expander('FPL-assists · xA-korrektion'):
        st.caption('Separat eksperiment: fælles FPL-assist/xA-faktor udglattet mod 1. Minutter, mål, bonus og defensive point er uændrede. Baseline er stadig standard.')
        st.caption('FPL-assists kan komme fra returer, selvmål og vundne straffespark. Faktoren er ikke en ren regelkorrektion: afslutningsheld og stikprøvestøj indgår også. Ingen event-baseret genkendelse af ekstra assists.')
        paths=sorted((root/'development').glob('*/report.json'),reverse=True)
        if paths:
            chosen=st.selectbox('Gemt assist-evaluering',paths,format_func=lambda p:p.parent.name)
            try:r=json.loads(chosen.read_text())
            except (OSError,ValueError) as exc:st.error(str(exc));return
            st.warning('Retrospektive udviklingsdata, ikke uafhængig test. Faktoren genberegnes før hver GW på tidligere færdige kampe. Ingen aktuelle odds eller senere kampe bruges som historiske inputs.')
            st.write(f"GW {', '.join(map(str,r['gameweeks']))} · {r['summary'][0]['n']} observationer · {r['summary'][0]['players']} spillere · {r['draws']} scenarier · seed {r['seed']} + GW")
            st.caption(f"Data observeret {r['data_available_at']} · snapshot {r['snapshot_id']}")
            columns=['model','assist_MAE','assist_RMSE','assist_bias','point_MAE','point_RMSE','CRPS']
            st.dataframe(pd.DataFrame(r['summary'])[columns].round(4),hide_index=True)
            st.caption('Assistfejl måles i antal assists, pointfejl i FPL-point. Bias > 0 er overvurdering. prior_average er tidligere gennemsnit på de samme rækker; assist_correction ændrer kun assists.')
            fits=r['evaluations']['assist_correction']['assist_fits']
            st.write('Faktor og træningsgrundlag pr. forecast-GW')
            st.dataframe(pd.DataFrame([dict(GW=e,**{k:f[k] for k in ('status','factor','fpl_assists','expected_assists','training_rows','training_gameweeks','reason')}) for e,f in fits.items()]).round(4),hide_index=True)
            st.caption('Regelmæssige spillere: '+r['regular_rule'])
            st.dataframe(pd.DataFrame(r['by_prior_history'])[['model','group','n','assist_MAE','point_MAE','point_RMSE','CRPS']].round(4),hide_index=True)
            with st.expander('Assistdiagnostik pr. position og GW'):
                for k in ('by_position','by_gameweek'):st.dataframe(pd.DataFrame(r[k]).round(4),hide_index=True)
                st.json(r['assist_config'])
        else:st.info('Ingen gemt sammenligning. Kør scripts/compare_assists.py på eksisterende snapshots.')
        paths=sorted((root/'forecasts').glob('*/comparison.json'),reverse=True)
        if paths:
            from fpl_model.prediction_evaluation import load_forecasts
            chosen=st.selectbox('Gemt assist-prognose',paths,format_func=lambda p:p.parent.name)
            try:
                saved,_=load_forecasts(chosen.parent);c=json.loads(chosen.read_text())
            except (OSError,ValueError) as exc:st.error(str(exc));return
            st.write(f"GW{saved['event']} · prognose {saved['forecast_origin_at']} · deadline {saved['deadline_at']}")
            st.warning('Prognoseforskel, ikke dokumenteret forbedring. Genbrugte odds og spillerdata beholder de oprindelige hentetidspunkter.')
            source=saved['coverage']['source'];history=saved['input_sources'].get('history',{})
            st.caption(f"William Hill · {c['usable_fixtures']}/{c['expected_fixtures']} kampe · odds observeret {source['available_at']} · spillerdata {history.get('available_at','se inputreferencer')}")
            st.write(f"Fælles assistfaktor: {c['factor']:.4f}. Med odds begrænser det eksisterende holdmålbudget effekten; målrater og relative assistandele er uændrede.")
            st.dataframe(pd.DataFrame(c['player_changes'])[['name','reference_xp','assist_correction_xp','xp_delta','reference_assist_points','corrected_assist_points']].round(3),hide_index=True)
            names={r['player_id']:r['name'] for r in c['player_changes']}
            pid=st.selectbox('Spiller · assistforklaring',sorted(names,key=names.get),format_func=names.get)
            for name,v in saved['variants'].items():
                if not v.get('assist_model'):continue
                e=v['explanations'][str(pid)];m=v['assist_model']
                st.write(f"Træning: {m['training_rows']} spillede rækker · {m['fpl_assists']} FPL-assists / {m['expected_assists']:.2f} xA · {m['status']}")
                st.json(e['assist_correction'])
                with st.expander('Kampvise assistandele og inputreferencer'):
                    st.json(e['fixtures']);st.json(saved['input_sources']);st.json(saved['assist_config'])
        st.caption('En fælles faktor kan ikke omfordele retur-/straffesparks-assists til bestemte spillertyper. Sæsonprior, præstationsbonus og rollemodeller kombineres ikke med dette forsøg.')
