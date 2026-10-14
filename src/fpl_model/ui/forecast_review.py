"""Practical post-GW review of local forecasts, without data or model refreshes."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import streamlit as st

from fpl_model.forecast_review import (
    event_readiness, read_official_context, review_forecast, reviewable_forecasts,
)
from fpl_model.label_contracts import utc
from fpl_model.io import SnapshotIntegrityError
from fpl_model.prediction_evaluation import _sha
from fpl_model.prototype_data import snapshot_paths


def metric_rows(variants,group=None):
    rows=[]
    for name,v in variants.items():
        values=v if group is None else v['by_history_group'][group]
        points=values.get('points') or {};minutes=values.get('minutes') or {};dnp=values.get('dnp') or {}
        rows.append(dict(model=name,n=values['n'],minut_bias=minutes.get('bias'),minut_MAE=minutes.get('mae'),
            minut_RMSE=minutes.get('rmse'),point_MAE=points.get('mae'),point_RMSE=points.get('rmse'),
            DNP_Brier=dnp.get('brier'),DNP_forudsagt=dnp.get('predicted'),DNP_observeret=dnp.get('observed'),CRPS=points.get('crps')))
    return rows


@st.cache_data(show_spinner=False)
def _catalog(root,fingerprint):
    return reviewable_forecasts(root)


def show_forecast_review(root,data):
    with st.expander('Efter runden · sammenlign gemte prognoser med resultater'):
        files=list((Path(root)/'artifacts/defensive_odds').glob('*/comparison.json'))
        files+=list((Path(root)/'artifacts/model_forecasts').glob('*/forecast.json'))
        fingerprint=tuple(sorted((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in files))
        choices=_catalog(str(root),fingerprint)
        if not choices:
            st.info('Ingen gemte reelle prognoser til efterkontrol endnu.');return
        now=datetime.now(timezone.utc)
        # Prefer the latest forecast for the most recent elapsed deadline, not a best-scoring run.
        past=[i for i,c in enumerate(choices) if utc(c['deadline_at'])<=now]
        index=past[-1] if past else len(choices)-1
        chosen=st.selectbox('Prognose til efterkontrol',choices,index=index,
            format_func=lambda c:f"GW{c['event']} · {c['origin']} · {'gemte simulationer' if c['format']=='saved_scenarios' else 'gemte nøgletal'}",key='review_forecast_choice')
        st.caption(f"Prognosetid: {chosen['origin']} · officiel deadline i prognosen: {chosen['deadline_at']}. Ingen genberegning af prognoser eller automatiske downloads.")
        context=None
        try:
            paths=snapshot_paths(Path(root)/'data/raw')
            if paths:context=read_official_context(paths[0])
        except (ValueError,OSError,KeyError,SnapshotIntegrityError) as exc:
            st.error(f'Kampkontekst kunne ikke verificeres: {exc}')
        if context:
            readiness=event_readiness(context,chosen['event'])
            st.write(f"**Officiel rundestatus:** {readiness['finished']}/{readiness['fixtures']} kampe endelige · "
                     f"{readiness['provisionally_finished']} foreløbigt afsluttede · GW datakontrolleret: {'ja' if readiness['event_data_checked'] else 'nej'}")
            st.caption(f"Rundestatus observeret {context['source']['available_at']} · snapshot {context['source']['snapshot_id']}")
            if readiness['status']=='awaiting_official_finality':
                st.warning('Afventer officielle slutresultater. Afsluttede kampe og forløbet kamptid er ikke tilstrækkelige til endelige labels.')
            else:st.info('Kampkonteksten er endelig. Spillerhistorikker skal også være hentet med endelige labels før evaluering.')
            unfinished=[f for f in readiness['remaining'] if not f['finished_provisional']]
            if unfinished:st.dataframe(pd.DataFrame(unfinished),hide_index=True)
        else:st.warning('Ingen verificeret lokal kampkontekst til rundestatus.')
        source={k:data.get(k) for k in ('snapshot_id','snapshot_path','manifest_sha256','as_of_at')}
        st.caption(f"Udfald læses fra det valgte officielle datagrundlag: {source['snapshot_id']} · observeret {source['as_of_at'] or 'ukendt'}. En nyere kampkontekst opgraderer ikke ældre spillerlabels.")
        if chosen['format']=='legacy_summary':
            st.caption('Ældre prognose: middelværdier, DNP og percentiler er gemt; fulde scenarier mangler. Derfor vises CRPS som manglende. Oprindelig oprettelsestid er deklareret, ikke uafhængigt bevist.')
        if st.button('Efterkontrollér gemt prognose'):
            try:
                out,_=review_forecast(chosen['path'],data['histories'],Path(root)/'artifacts/forecast_reviews',
                    season=data.get('season','2026-2027'),context=context,outcome_source=source)
                st.success(f'Ny efterkontrol gemt lokalt: {out.name}')
            except (ValueError,OSError,KeyError,SnapshotIntegrityError) as exc:st.error(f'Efterkontrol afvist: {exc}')
        # Read local persisted results; do not silently reuse scores against different outcomes.
        checks=sorted((Path(root)/'artifacts/forecast_reviews').glob('*/report.json'),reverse=True)
        result=None;forecast_sha=_sha(chosen['path'])
        for p in checks:
            try:r=json.loads(p.read_bytes())
            except (ValueError,OSError):continue
            if r.get('forecast_sha256')==forecast_sha and r.get('outcome_source')==source:
                result=r;break
        if result is None:
            st.info('Ingen efterkontrol gemt for denne prognose og det valgte udfaldssnapshot.');return
        total=len(next(iter(result['variants'].values()))['pending'])+len(result['same_player_ids'])
        st.info(f"{len(result['same_player_ids'])} spillere med komplette endelige udfald af {total}. Samme evalueringsrækker for alle varianter.")
        st.caption(f"Efterkontrol gemt {result['created_at']} · proveniens: {result['provenance_status']}. Manglende/provisoriske rækker er aldrig DNP.")
        st.dataframe(pd.DataFrame(metric_rows(result['variants'])),hide_index=True)
        st.caption('Bias = prognose − observeret. Negative minutter betyder undervurdering. CRPS kræver gemte scenarier. En enkelt eller ufuldstændig runde dokumenterer ikke en bedre model.')
        st.write('**Regelmæssige spillere ud fra historikken på prognosetidspunktet**')
        st.caption(result['regular_rule']+' Ufuldstændigt historikgrundlag vises særskilt.')
        st.dataframe(pd.DataFrame(metric_rows(result['variants'],'regular')),hide_index=True)
        with st.expander('Dækning, positioner og spillerfejl'):
            for name,v in result['variants'].items():
                st.write(name,'Afventer:',v['pending_reasons'])
                st.dataframe(pd.DataFrame(v['by_position']),hide_index=True)
                st.write('Andre spillere og uafklaret historik:',{k:v['by_history_group'][k] for k in ('other','unresolved')})
                if v['rows']:st.dataframe(pd.DataFrame(v['rows']),hide_index=True)
                if v['pending']:st.dataframe(pd.DataFrame(v['pending']),hide_index=True)
